"""Decay, regression detection, correlation, and time travel.

These are the four things a findings table cannot do and a memory layer can, so
each one gets a test that would fail if the behaviour silently degraded into
"just store the row".
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

psycopg = pytest.importorskip("psycopg")

from mnemos_memory import Candidate, Memory, migrate  # noqa: E402
from mnemos_memory.embeddings import HashingEmbedder  # noqa: E402
from mnemos_memory.intelligence import (  # noqa: E402
    CONFIDENCE_HALF_LIFE_DAYS,
    MIN_CONFIDENCE,
    confidence_for,
)

DSN = os.getenv("DATABASE_URL", "postgresql://root@localhost:26257/mnemos?sslmode=disable")


def _cluster_reachable() -> bool:
    try:
        with psycopg.connect(DSN.replace("/mnemos?", "/defaultdb?"), connect_timeout=3):
            return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _cluster_reachable(), reason="no CockroachDB reachable; run `make db-up`"
)


@pytest.fixture(scope="session", autouse=True)
def _schema():
    migrate(verbose=False)


@pytest.fixture()
def mem():
    with Memory(embedder=HashingEmbedder()) as m:
        yield m


def _target(mem: Memory, prefix: str) -> tuple[str, str]:
    suffix = uuid.uuid4().hex[:8]
    tid = mem.create_target(
        name=f"{prefix}-{suffix}", root_domain=f"{suffix}.{prefix}.test",
        authorisation="unit test",
        scope_rules=[(f"*.{suffix}.{prefix}.test", "allow", "owned")],
    )
    return tid, suffix


# ---------------------------------------------------------------------------
# decay
# ---------------------------------------------------------------------------
def test_confidence_is_full_when_just_confirmed():
    assert confidence_for(datetime.now(timezone.utc)) == 1.0


def test_confidence_halves_over_one_half_life():
    then = datetime.now(timezone.utc) - timedelta(days=CONFIDENCE_HALF_LIFE_DAYS)
    assert confidence_for(then) == pytest.approx(0.5, abs=0.01)


def test_confidence_never_reaches_zero():
    """Memory does not fully forget — an old finding is untrusted, not invisible."""
    ancient = datetime.now(timezone.utc) - timedelta(days=3650)
    assert confidence_for(ancient) == MIN_CONFIDENCE


def test_confidence_decays_from_last_confirmation_not_creation(mem):
    """Re-confirming an old finding must restore full trust."""
    tid, suffix = _target(mem, "decay")
    run1 = mem.start_run(tid, pass_no=1)
    cand = Candidate(host=f"a.{suffix}.decay.test", title="stale thing",
                     severity="low", summary="s")
    mem.commit_finding(tid, cand, run_id=run1)

    # Backdate the confirmation as if it had not been seen for a month.
    with mem.conn.cursor() as cur:
        cur.execute(
            "UPDATE findings SET last_confirmed_at = now() - INTERVAL '30 days' "
            "WHERE target_id = %s", (tid,))
    aged = mem.findings_with_confidence(tid)[0]
    assert aged["confidence"] < 0.3

    # Seeing it again is a dedup hit, which must refresh last_confirmed_at.
    run2 = mem.start_run(tid, pass_no=2)
    assert mem.commit_finding(tid, cand, run_id=run2) is None
    refreshed = mem.findings_with_confidence(tid)[0]
    assert refreshed["confidence"] > 0.99


# ---------------------------------------------------------------------------
# regression detection
# ---------------------------------------------------------------------------
def test_finding_not_reobserved_becomes_fixed(mem):
    tid, suffix = _target(mem, "recon")
    run1 = mem.start_run(tid, pass_no=1)
    cand = Candidate(host=f"a.{suffix}.recon.test", title="temporary problem",
                     severity="medium", summary="s")
    mem.commit_finding(tid, cand, run_id=run1)
    mem.reconcile(tid, run1, [cand.fingerprint()])

    # Next pass sees an empty estate.
    run2 = mem.start_run(tid, pass_no=2)
    result = mem.reconcile(tid, run2, [])
    assert result.fixed == 1
    assert mem.findings_with_confidence(tid)[0]["status"] == "fixed"


def test_fixed_finding_that_returns_is_regressed(mem):
    """The most important row in the table: a fix that did not hold."""
    tid, suffix = _target(mem, "regress")
    cand = Candidate(host=f"a.{suffix}.regress.test", title="recurring problem",
                     severity="high", summary="s")

    run1 = mem.start_run(tid, pass_no=1)
    mem.commit_finding(tid, cand, run_id=run1)
    mem.reconcile(tid, run1, [cand.fingerprint()])

    run2 = mem.start_run(tid, pass_no=2)
    mem.reconcile(tid, run2, [])           # gone -> fixed

    run3 = mem.start_run(tid, pass_no=3)
    result = mem.reconcile(tid, run3, [cand.fingerprint()])   # back again

    assert result.regressed == 1
    row = mem.findings_with_confidence(tid)[0]
    assert row["status"] == "regressed"
    assert row["regression_count"] == 1
    assert any(r["title"] == "recurring problem" for r in mem.regressions())


def test_reobserved_finding_stays_open(mem):
    tid, suffix = _target(mem, "stable")
    cand = Candidate(host=f"a.{suffix}.stable.test", title="persistent problem",
                     severity="low", summary="s")
    run1 = mem.start_run(tid, pass_no=1)
    mem.commit_finding(tid, cand, run_id=run1)
    mem.reconcile(tid, run1, [cand.fingerprint()])

    run2 = mem.start_run(tid, pass_no=2)
    result = mem.reconcile(tid, run2, [cand.fingerprint()])
    assert result.confirmed == 1 and result.fixed == 0 and result.regressed == 0
    assert mem.findings_with_confidence(tid)[0]["status"] == "open"


# ---------------------------------------------------------------------------
# cross-target correlation
# ---------------------------------------------------------------------------
def test_identical_bytes_on_two_targets_correlate(mem):
    """The same vendor bundle on two estates is one problem, not two."""
    body = f"const SHARED = '{uuid.uuid4().hex}';".encode()
    tid_a, _ = _target(mem, "corra")
    tid_b, _ = _target(mem, "corrb")

    mem.record_artifact(tid_a, None, body)
    mem.record_artifact(tid_b, None, body)

    shared = [c for c in mem.correlations() if c.kind == "artifact"]
    assert shared, "identical bytes on two targets must correlate"
    assert any(len(c.targets) >= 2 for c in shared)


def test_same_bytes_on_one_target_does_not_correlate(mem):
    """Re-seeing a file on the same estate is dedup, not correlation."""
    body = f"const LOCAL = '{uuid.uuid4().hex}';".encode()
    tid, _ = _target(mem, "single")
    first = mem.record_artifact(tid, None, body)
    second = mem.record_artifact(tid, None, body)
    assert first == second, "same bytes, same target -> one row"


# ---------------------------------------------------------------------------
# time travel
# ---------------------------------------------------------------------------
def test_snapshot_reflects_the_past_not_the_present(mem):
    tid, suffix = _target(mem, "tt")
    before = mem.stats()["findings"]

    run = mem.start_run(tid)
    mem.commit_finding(tid, Candidate(
        host=f"a.{suffix}.tt.test", title="written after the snapshot",
        severity="low", summary="s"), run_id=run)
    after = mem.stats()["findings"]
    assert after > before

    # A snapshot from a few seconds ago must not contain the new row.
    past = mem.snapshot_at(datetime.now(timezone.utc) - timedelta(seconds=20))
    if past is None:
        pytest.skip("cluster GC window too short for a 20s snapshot")
    assert past["findings"] < after


def test_time_travel_outside_gc_window_returns_none_not_an_error(mem):
    """Being unable to look that far back is a real answer, not a crash."""
    ancient = datetime.now(timezone.utc) - timedelta(days=400)
    assert mem.snapshot_at(ancient) is None


def test_scope_at_answers_what_was_authorised(mem):
    tid, suffix = _target(mem, "scopeat")
    rules = mem.scope_at(datetime.now(timezone.utc) - timedelta(seconds=5))
    if rules is None:
        pytest.skip("cluster GC window too short")
    assert isinstance(rules, list)
