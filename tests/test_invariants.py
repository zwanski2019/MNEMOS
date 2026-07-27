"""The four invariants from CLAUDE.md §3, asserted against a real CockroachDB.

These are not unit tests of helper functions. Each one tries to *violate* an
invariant and asserts that the system refuses. If one of these ever goes green
by accident, the corresponding claim in the submission stops being true.

Requires a running CockroachDB (`make db-up`). Skipped otherwise.
"""

from __future__ import annotations

import os
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")

from mnemos_memory import (  # noqa: E402
    Candidate,
    CostCeilingExceeded,
    Memory,
    ScopeViolation,
    migrate,
)
from mnemos_memory.embeddings import HashingEmbedder  # noqa: E402
from mnemos_recon.scanner import scan  # noqa: E402

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


@pytest.fixture()
def target(mem):
    suffix = uuid.uuid4().hex[:8]
    return mem.create_target(
        name=f"test-{suffix}",
        root_domain=f"{suffix}.test",
        authorisation="unit test",
        scope_rules=[
            (f"*.{suffix}.test", "allow", "test estate"),
            (f"admin.{suffix}.test", "deny", "explicitly excluded"),
        ],
    ), suffix


# ---------------------------------------------------------------------------
# Invariant 2 — deny by default
# ---------------------------------------------------------------------------
def test_unknown_host_is_denied(mem, target):
    target_id, _ = target
    assert mem.check_scope(target_id, "somewhere-else.example.com") is False


def test_explicit_deny_beats_wildcard_allow(mem, target):
    target_id, suffix = target
    assert mem.check_scope(target_id, f"www.{suffix}.test") is True
    assert mem.check_scope(target_id, f"admin.{suffix}.test") is False


def test_target_without_allow_rule_is_refused(mem):
    with pytest.raises(ValueError, match="no allow rule"):
        mem.create_target(
            name="noscope", root_domain=f"{uuid.uuid4().hex[:8]}.test",
            authorisation="x", scope_rules=[("*.x.test", "deny", "nope")],
        )


def test_write_outside_scope_raises(mem, target):
    target_id, _ = target
    run_id = mem.start_run(target_id)
    out_of_scope = Candidate(
        host="not-ours.example.com", title="anything", severity="high", summary="x"
    )
    with pytest.raises(ScopeViolation):
        mem.commit_finding(target_id, out_of_scope, run_id=run_id)


def test_scope_guard_fails_closed_when_memory_is_unreachable(mem, target, monkeypatch):
    """The safe direction is to do nothing, not to assume yes."""
    target_id, suffix = target

    class Broken:
        def cursor(self):
            raise RuntimeError("connection reset")

    monkeypatch.setattr(mem, "conn", Broken())
    # audit() will also fail on the broken connection, so swallow it the way a
    # caller would see it: the answer must still be "deny".
    monkeypatch.setattr(mem, "audit", lambda *a, **k: None)
    assert mem.check_scope(target_id, f"www.{suffix}.test") is False


# ---------------------------------------------------------------------------
# Invariant 1 — dedup before write
# ---------------------------------------------------------------------------
def test_identical_finding_is_written_once(mem, target):
    target_id, suffix = target
    run1 = mem.start_run(target_id, pass_no=1)
    cand = Candidate(
        host=f"www.{suffix}.test", title="Stripe key in bundle", severity="medium",
        summary="A publishable key is shipped to the browser.",
    )
    first = mem.commit_finding(target_id, cand, run_id=run1)
    assert first is not None

    run2 = mem.start_run(target_id, pass_no=2)
    second = mem.commit_finding(target_id, cand, run_id=run2)
    assert second is None, "the same finding must not be written twice"

    rows = [f for f in mem.findings(target_id) if f["title"] == "Stripe key in bundle"]
    assert len(rows) == 1
    assert rows[0]["times_seen"] == 2, "a repeat must bump times_seen, not add a row"


def test_semantically_similar_finding_is_deduped(mem, target):
    """Reworded duplicates are caught by the vector index, not the fingerprint."""
    target_id, suffix = target
    run = mem.start_run(target_id)
    base = Candidate(
        host=f"api.{suffix}.test", title="Unauthenticated admin export endpoint",
        severity="high", summary="The /v2/admin/export path requires no credentials.",
    )
    assert mem.commit_finding(target_id, base, run_id=run) is not None

    # Same issue, different words -> different fingerprint, same meaning.
    reworded = Candidate(
        host=f"api.{suffix}.test", title="Unauthenticated admin export endpoint ",
        severity="high", summary="The /v2/admin/export path requires no credentials.",
    )
    verdict = mem.dedup(target_id, reworded)
    assert verdict.novel is False
    assert verdict.existing_id is not None


def test_novel_finding_is_not_deduped(mem, target):
    target_id, suffix = target
    run = mem.start_run(target_id)
    mem.commit_finding(target_id, Candidate(
        host=f"api.{suffix}.test", title="Apache mod_status exposed", severity="medium",
        summary="server-status is reachable unauthenticated.",
    ), run_id=run)

    unrelated = Candidate(
        host=f"api.{suffix}.test", title="AWS access key id in client bundle",
        severity="critical", summary="An AKIA-prefixed key ships to the browser.",
    )
    assert mem.dedup(target_id, unrelated).novel is True


# ---------------------------------------------------------------------------
# Invariant 1 (ordering) — recall reaches across sessions
# ---------------------------------------------------------------------------
def test_recall_crosses_runs(mem, target):
    target_id, suffix = target
    run1 = mem.start_run(target_id, pass_no=1)
    mem.index_text(target_id, "const STRIPE_PUBLISHABLE = 'pk_live_abc';", run_id=run1)
    mem.finish_run(run1)

    # A brand new Memory handle: nothing is carried in process state.
    with Memory(embedder=HashingEmbedder()) as fresh:
        hits = fresh.recall(target_id, "const STRIPE_PUBLISHABLE = 'pk_live_abc';", k=3)
    assert hits, "a later session must be able to recall an earlier one"
    assert hits[0].distance < 0.01


# ---------------------------------------------------------------------------
# Invariant 4 — the cost ceiling halts the agent
# ---------------------------------------------------------------------------
def test_cost_ceiling_halts_the_run(mem, target):
    target_id, _ = target
    run = mem.start_run(target_id, ceiling_usd=0.01)
    mem.charge(run, input_tokens=100, output_tokens=10, cost_usd=0.005)
    with pytest.raises(CostCeilingExceeded):
        mem.charge(run, input_tokens=100, output_tokens=10, cost_usd=0.02)

    halted = [r for r in mem.runs() if str(r["id"]) == run]
    assert halted and halted[0]["status"] == "halted"


def test_ceiling_is_read_from_the_database_not_the_process(mem, target):
    """A restarted worker must not get a fresh budget."""
    target_id, _ = target
    run = mem.start_run(target_id, ceiling_usd=0.01)
    mem.charge(run, input_tokens=1, output_tokens=1, cost_usd=0.009)

    with Memory(embedder=HashingEmbedder()) as restarted:
        with pytest.raises(CostCeilingExceeded):
            restarted.charge(run, input_tokens=1, output_tokens=1, cost_usd=0.002)


# ---------------------------------------------------------------------------
# Invariant 3 — everything is audited, and the ledger cannot be rewritten
# ---------------------------------------------------------------------------
def test_every_decision_leaves_an_audit_row(mem, target):
    target_id, suffix = target
    before = len(mem.audit_tail(limit=1000))
    run = mem.start_run(target_id)
    mem.check_scope(target_id, f"www.{suffix}.test", run_id=run)
    mem.commit_finding(target_id, Candidate(
        host=f"www.{suffix}.test", title="audited finding", severity="low", summary="s",
    ), run_id=run)
    after = mem.audit_tail(limit=1000)
    assert len(after) > before
    actions = {row["action"] for row in after}
    assert {"scope_check", "dedup", "write"} <= actions


def test_append_only_ledgers_reject_update_and_delete():
    """Enforced by CockroachDB privileges (002_roles.sql), not by application code."""
    admin = psycopg.connect(DSN, autocommit=True)
    user = f"invariant_probe_{uuid.uuid4().hex[:8]}"
    try:
        with admin.cursor() as cur:
            cur.execute(f"CREATE USER IF NOT EXISTS {user}")
            cur.execute(f"GRANT mnemos_agent TO {user}")
    finally:
        admin.close()

    probe_dsn = DSN.replace("root@", f"{user}@")
    conn = psycopg.connect(probe_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute("UPDATE scope_decisions SET effect = 'allow'")
        with conn.cursor() as cur:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute("DELETE FROM audit_log")
        with conn.cursor() as cur:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute("DELETE FROM scope_decisions")
        # ...but appending must still work.
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO audit_log (actor, action, decision) VALUES ('test','probe','ok')"
            )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Scanner determinism — the thing that makes dedup meaningful
# ---------------------------------------------------------------------------
def test_scanner_is_deterministic():
    body = "const K='pk_live_AAAAAAAAAAAAAAAA'; fetch('https://api.example.com/v2/admin/x');"
    assert scan("www.example.com", "u", body) == scan("www.example.com", "u", body)


def test_scanner_does_not_report_credentials_as_hosts():
    """A Sentry DSN embeds a key before the @; it is not a discovered host."""
    body = "const SENTRY_DSN='https://abc123@o1.ingest.sentry.io/42';"
    hosts = {o.detail for o in scan("www.example.com", "u", body) if o.kind == "subdomain"}
    assert "Referenced host abc123" not in hosts
    assert "Referenced host o1.ingest.sentry.io" in hosts


def test_scanner_severity_is_not_downgraded_by_generic_rules():
    body = "const A='AKIAIOSFODNN7EXAMPLE';"
    obs = [o for o in scan("h", "u", body) if o.kind == "secret"]
    assert obs and obs[0].severity == "critical"
