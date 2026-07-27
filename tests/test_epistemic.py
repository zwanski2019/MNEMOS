"""Epistemic memory: what MNEMOS believes, how it updates, and what it refuses.

Two halves. The pure arithmetic of belief is tested without a database, because
that is where subtle errors hide. The integration half asserts the product rule
that motivates the whole layer: **a system that remembers being wrong should not
make the same claim at full volume twice.**
"""

from __future__ import annotations

import os
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")

from mnemos_memory import Candidate, Memory, migrate  # noqa: E402
from mnemos_memory.embeddings import HashingEmbedder  # noqa: E402
from mnemos_memory.epistemic import (  # noqa: E402
    CONFIRMED_AT,
    FALSE_POSITIVE_PENALTY,
    MAX_CONFIDENCE,
    MIN_CONFIDENCE,
    RECALL_CONFIDENCE_CEILING,
    Belief,
    PriorLink,
    apply_false_positive_memory,
    derive_status,
    initial_confidence,
    on_recall,
    on_reobservation,
    update,
)

DSN = os.getenv("DATABASE_URL", "postgresql://root@localhost:26257/mnemos?sslmode=disable")


# ===========================================================================
# the arithmetic of belief — no database
# ===========================================================================
def test_evidence_moves_belief_in_the_right_direction():
    assert update(0.5, 3.0) > 0.5
    assert update(0.5, 0.3) < 0.5
    assert update(0.5, 1.0) == pytest.approx(0.5, abs=1e-9)


def test_belief_never_reaches_certainty():
    """A belief that cannot be moved by new evidence is not a belief."""
    overwhelming = update(0.5, *([1000.0] * 20))
    assert overwhelming <= MAX_CONFIDENCE
    crushing = update(0.5, *([0.001] * 20))
    assert crushing >= MIN_CONFIDENCE


def test_evidence_order_does_not_change_the_result():
    """Bayesian updating is commutative; if ours is not, it is not Bayesian."""
    a = update(0.4, 2.0, 0.5, 3.0)
    b = update(0.4, 3.0, 2.0, 0.5)
    assert a == pytest.approx(b, abs=1e-9)


def test_reliable_sources_start_higher_than_vague_ones():
    """A matched `pk_live_` prefix is a stronger claim than 'a host was named'."""
    secret = initial_confidence(source_kind="secret", analyst_certainty=None,
                                corroborating_priors=0)
    subdomain = initial_confidence(source_kind="subdomain", analyst_certainty=None,
                                   corroborating_priors=0)
    assert secret > subdomain


def test_analyst_hedging_lowers_confidence():
    confident = initial_confidence(source_kind="endpoint", analyst_certainty=0.95,
                                   corroborating_priors=0)
    unsure = initial_confidence(source_kind="endpoint", analyst_certainty=0.05,
                                corroborating_priors=0)
    assert confident > unsure


def test_corroborating_priors_have_diminishing_returns():
    """Twenty near-duplicates must not manufacture certainty."""
    one = initial_confidence(source_kind="endpoint", analyst_certainty=0.5,
                             corroborating_priors=1)
    twenty = initial_confidence(source_kind="endpoint", analyst_certainty=0.5,
                                corroborating_priors=20)
    assert twenty > one
    assert twenty < CONFIRMED_AT, "corroboration alone must not reach 'confirmed'"


def test_recall_cannot_manufacture_certainty():
    """Recall frequency tracks ranking, so unbounded updates would be circular."""
    belief = Belief(0.5, 1, "hypothesis")
    for _ in range(200):
        belief = on_recall(belief)
    assert belief.confidence <= RECALL_CONFIDENCE_CEILING
    assert belief.evidence_count == 201, "evidence is still counted past the ceiling"


def test_reobservation_can_exceed_the_recall_ceiling():
    """Only the scanner seeing it again is strong enough to confirm."""
    belief = Belief(RECALL_CONFIDENCE_CEILING, 3, "corroborated")
    for _ in range(6):
        belief = on_reobservation(belief, source_kind="secret")
    assert belief.confidence > RECALL_CONFIDENCE_CEILING
    assert belief.status == "confirmed"


def test_operator_verdicts_are_sticky():
    """Recomputation must never quietly overturn a human saying 'this is wrong'."""
    assert derive_status(0.99, 99, current="false_positive") == "false_positive"
    assert derive_status(0.99, 99, current="deprecated") == "deprecated"
    assert derive_status(0.99, 99, current="hypothesis") == "confirmed"


def test_only_the_closest_false_positive_applies():
    """One past mistake seen three times is still one past mistake."""
    priors = [
        PriorLink("a", 0.90, "false_positive"),
        PriorLink("b", 0.88, "false_positive"),
        PriorLink("c", 0.85, "false_positive"),
    ]
    penalised, links = apply_false_positive_memory(0.8, priors)
    assert penalised == pytest.approx(0.8 * FALSE_POSITIVE_PENALTY, abs=1e-6)
    assert len(links) == 1 and links[0].finding_id == "a"


def test_non_false_positive_priors_do_not_penalise():
    unchanged, links = apply_false_positive_memory(
        0.8, [PriorLink("a", 0.95, "confirmed")]
    )
    assert unchanged == 0.8 and links == []


# ===========================================================================
# integration — requires CockroachDB
# ===========================================================================
def _cluster_reachable() -> bool:
    try:
        with psycopg.connect(DSN.replace("/mnemos?", "/defaultdb?"), connect_timeout=3):
            return True
    except Exception:
        return False


needs_db = pytest.mark.skipif(
    not _cluster_reachable(), reason="no CockroachDB reachable; run `make db-up`"
)


@pytest.fixture(scope="session", autouse=True)
def _schema():
    if _cluster_reachable():
        migrate(verbose=False)


@pytest.fixture()
def mem():
    with Memory(embedder=HashingEmbedder()) as m:
        yield m


@pytest.fixture()
def target(mem):
    suffix = uuid.uuid4().hex[:8]
    tid = mem.create_target(
        name=f"epi-{suffix}", root_domain=f"{suffix}.epi.test",
        authorisation="unit test",
        scope_rules=[(f"*.{suffix}.epi.test", "allow", "owned")],
    )
    return tid, suffix


@needs_db
def test_written_finding_gets_a_belief(mem, target):
    tid, suffix = target
    run = mem.start_run(tid)
    fid = mem.commit_finding(tid, Candidate(
        host=f"a.{suffix}.epi.test", title="AWS key in bundle", severity="critical",
        summary="An AKIA-prefixed key ships to the browser.",
        source_kind="secret", analyst_certainty=0.9,
    ), run_id=run)

    belief = mem.belief(fid)
    assert belief is not None
    assert 0 < belief.confidence < 1
    assert belief.evidence_count == 1
    assert belief.status in ("hypothesis", "corroborated", "confirmed")


@needs_db
def test_false_positive_memory_reduces_confidence(mem, target):
    """The test named in the spec, and the reason this layer exists.

    A scanner with no memory re-raises the same false positive every run and
    burns the operator's trust. One that remembers starts the same claim at a
    fraction of the confidence, labelled a hypothesis.
    """
    tid, suffix = target

    # Run 1: a finding is written, then an operator rules it wrong.
    run1 = mem.start_run(tid, pass_no=1)
    original = mem.commit_finding(tid, Candidate(
        host=f"a.{suffix}.epi.test",
        title="Hardcoded credential in vendor bundle",
        severity="high",
        summary="A credential-shaped string appears in a third-party script.",
        source_kind="secret", analyst_certainty=0.8,
    ), run_id=run1)
    baseline = mem.belief(original)
    assert baseline is not None

    mem.mark_false_positive(original, reason="vendor placeholder, not a live key")
    assert mem.belief(original).status == "false_positive"

    # Run 2: the same *kind* of claim, reworded, on a different host.
    #
    # The wording matters. Identical text embeds identically, so dedup would
    # (correctly) swallow it and there would be no second finding to discount.
    # This sits at ~0.23 cosine distance: past DEDUP_DISTANCE (0.12) so it is
    # genuinely novel, inside FALSE_POSITIVE_RADIUS (0.35) so memory of the
    # earlier mistake still reaches it. That gap is the whole mechanism.
    run2 = mem.start_run(tid, pass_no=2)
    repeat = mem.commit_finding(tid, Candidate(
        host=f"b.{suffix}.epi.test",
        title="Hardcoded credential in vendor bundle",
        severity="high",
        summary="A credential-like value is embedded in a third-party vendor script.",
        source_kind="secret", analyst_certainty=0.8,
    ), run_id=run2)
    assert repeat is not None and repeat != original, "must be a distinct finding"

    poisoned = mem.belief(repeat)
    assert poisoned is not None
    assert poisoned.confidence < baseline.confidence, (
        "a finding resembling a known false positive must start less trusted"
    )
    assert poisoned.status == "hypothesis"
    assert any(
        link.get("prior_finding_id") == original for link in poisoned.chain
    ), "the discount must be traceable to the prior it came from"


@needs_db
def test_reobservation_raises_confidence(mem, target):
    tid, suffix = target
    cand = Candidate(
        host=f"a.{suffix}.epi.test", title="Apache mod_status exposed",
        severity="medium", summary="server-status is reachable unauthenticated.",
        source_kind="exposure", analyst_certainty=0.7,
    )
    run1 = mem.start_run(tid, pass_no=1)
    fid = mem.commit_finding(tid, cand, run_id=run1)
    before = mem.belief(fid).confidence

    # Seeing it again is a dedup hit — no new row, but stronger belief.
    run2 = mem.start_run(tid, pass_no=2)
    assert mem.commit_finding(tid, cand, run_id=run2) is None
    after = mem.belief(fid)

    assert after.confidence > before
    assert after.evidence_count > 1


@needs_db
def test_epistemic_state_is_not_a_dedup_bypass(mem, target):
    """The invariant. Belief is metadata; it can never authorise a write.

    A duplicate stays a duplicate no matter how confident anyone is about it, and
    an out-of-scope host is refused before belief is ever consulted.
    """
    tid, suffix = target
    cand = Candidate(
        host=f"a.{suffix}.epi.test", title="Duplicate under any confidence",
        severity="high", summary="s", source_kind="secret", analyst_certainty=1.0,
    )
    run1 = mem.start_run(tid, pass_no=1)
    first = mem.commit_finding(tid, cand, run_id=run1)
    assert first is not None

    run2 = mem.start_run(tid, pass_no=2)
    assert mem.commit_finding(tid, cand, run_id=run2) is None, (
        "maximum analyst certainty must not let a duplicate through"
    )

    rows = [f for f in mem.findings(tid) if f["title"] == "Duplicate under any confidence"]
    assert len(rows) == 1

    # And scope still runs first: no belief row is created for a refused write.
    from mnemos_memory import ScopeViolation

    run3 = mem.start_run(tid, pass_no=3)
    with pytest.raises(ScopeViolation):
        mem.commit_finding(tid, Candidate(
            host="not-ours.example.com", title="out of scope", severity="critical",
            summary="s", source_kind="secret", analyst_certainty=1.0,
        ), run_id=run3)


@needs_db
def test_recall_records_evidence_without_inflating_belief(mem, target):
    tid, suffix = target
    run = mem.start_run(tid)
    fid = mem.commit_finding(tid, Candidate(
        host=f"a.{suffix}.epi.test", title="Sentry DSN in client bundle",
        severity="low", summary="A DSN is embedded in a shipped script.",
        source_kind="secret", analyst_certainty=0.6,
    ), run_id=run)

    before = mem.belief(fid)
    for _ in range(5):
        mem.recall(tid, "Sentry DSN in client bundle", k=3)
    after = mem.belief(fid)

    assert after.evidence_count > before.evidence_count, "recall must count as evidence"

    # The claim is "recall cannot inflate belief", not "belief stays under the
    # ceiling". A finding can legitimately start above it on the strength of its
    # own evidence — a matched secret pattern the analyst was sure about. What
    # recall must never do is push it *higher*.
    if before.confidence >= RECALL_CONFIDENCE_CEILING:
        assert after.confidence == pytest.approx(before.confidence, abs=1e-6), (
            "recall must not move a belief that is already above the ceiling"
        )
    else:
        assert after.confidence <= RECALL_CONFIDENCE_CEILING
