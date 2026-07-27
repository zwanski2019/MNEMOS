"""Knowing when to stop.

The invariant under test throughout: **escalation is a success state.** A run
that stopped and asked is the system working. These tests assert that the agent
notices genuine incoherence, that it does not cry wolf on ordinary disagreement,
and that stopping is recorded as `escalated` rather than `failed`.
"""

from __future__ import annotations

import os
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")

from mnemos_memory import Candidate, Memory, migrate  # noqa: E402
from mnemos_memory.cognition import (  # noqa: E402
    ESCALATION_THRESHOLD,
    Confusion,
    Signal,
    detect_ambiguous_scope,
    detect_budget_without_coverage,
    detect_contradiction,
    propose_resolutions,
    severity_gap,
)
from mnemos_memory.embeddings import HashingEmbedder  # noqa: E402

DSN = os.getenv("DATABASE_URL", "postgresql://root@localhost:26257/mnemos?sslmode=disable")


# ===========================================================================
# signal detection — no database
# ===========================================================================
def test_contradicting_a_confirmed_finding_is_a_strong_signal():
    signals = detect_contradiction(
        proposed_severity="info",
        proposed_title="Admin export endpoint",
        priors=[{"id": "p1", "title": "Admin export endpoint", "severity": "critical",
                 "distance": 0.05, "status": "confirmed"}],
    )
    assert [s.name for s in signals] == ["contradicts_confirmed"]
    assert Confusion(signals=signals).should_escalate


def test_disagreeing_with_an_unconfirmed_prior_is_weaker():
    """Hypotheses are supposed to die. Contradicting one is not a crisis."""
    signals = detect_contradiction(
        proposed_severity="info",
        proposed_title="Admin export endpoint",
        priors=[{"id": "p1", "title": "Admin export endpoint", "severity": "critical",
                 "distance": 0.05, "status": "hypothesis"}],
    )
    assert [s.name for s in signals] == ["confident_disagreement"]
    assert not Confusion(signals=signals).should_escalate


def test_contradicting_a_known_false_positive_is_not_confusion():
    """Disagreeing with something already ruled wrong is the correct outcome."""
    signals = detect_contradiction(
        proposed_severity="critical",
        proposed_title="Hardcoded credential",
        priors=[{"id": "p1", "title": "Hardcoded credential", "severity": "info",
                 "distance": 0.05, "status": "false_positive"}],
    )
    assert signals == []


def test_small_severity_disagreement_is_not_a_contradiction():
    """Reasonable analysts differ between medium and high. That is not confusion."""
    signals = detect_contradiction(
        proposed_severity="high",
        proposed_title="Exposed status page",
        priors=[{"id": "p1", "title": "Exposed status page", "severity": "medium",
                 "distance": 0.02, "status": "confirmed"}],
    )
    assert signals == []


def test_distant_priors_do_not_contradict():
    """Two unrelated findings disagreeing about severity means nothing."""
    signals = detect_contradiction(
        proposed_severity="info",
        proposed_title="Something else entirely",
        priors=[{"id": "p1", "title": "Unrelated", "severity": "critical",
                 "distance": 0.9, "status": "confirmed"}],
    )
    assert signals == []


def test_conflicting_scope_rules_are_flagged():
    signal = detect_ambiguous_scope("api.example.com", [
        {"pattern": "*.example.com", "effect": "allow", "reason": "estate"},
        {"pattern": "api.*", "effect": "deny", "reason": "shared infrastructure"},
    ])
    assert signal is not None
    assert signal.detail["resolved_as"] == "deny"


def test_agreeing_scope_rules_are_not_ambiguous():
    assert detect_ambiguous_scope("api.example.com", [
        {"pattern": "*.example.com", "effect": "allow", "reason": "estate"},
        {"pattern": "api.*", "effect": "allow", "reason": "also fine"},
    ]) is None


def test_budget_burn_with_low_coverage_is_flagged():
    signal = detect_budget_without_coverage(
        spent_usd=0.95, ceiling_usd=1.0, processed=5, total=100
    )
    assert signal is not None
    assert signal.score > 0.5


def test_budget_burn_with_good_coverage_is_fine():
    assert detect_budget_without_coverage(
        spent_usd=0.95, ceiling_usd=1.0, processed=90, total=100
    ) is None


def test_cheap_run_is_never_flagged_for_budget():
    assert detect_budget_without_coverage(
        spent_usd=0.01, ceiling_usd=1.0, processed=1, total=100
    ) is None


def test_signals_accumulate_without_exceeding_certainty():
    """Noisy-OR: independent doubts compound, but never past 1."""
    many = Confusion(signals=[Signal(f"s{i}", 0.6, {}) for i in range(20)])
    assert many.score <= 1.0
    two_weak = Confusion(signals=[Signal("a", 0.3, {}), Signal("b", 0.3, {})])
    assert 0.3 < two_weak.score < 0.6


def test_every_signal_produces_an_actionable_proposal():
    """An escalation that only says 'I am confused' wastes the interruption."""
    confusion = Confusion(signals=[
        Signal("contradicts_confirmed", 0.75,
               {"proposed": {"severity": "info"}, "confirmed_prior": {"severity": "high"}},
               memory_refs=["p1"]),
        Signal("ambiguous_scope", 0.45, {}),
        Signal("budget_without_coverage", 0.4, {}),
    ])
    proposals = propose_resolutions(confusion)
    actions = {p.action for p in proposals}
    assert {"uphold_prior", "supersede_prior", "clarify_scope",
            "raise_ceiling_or_narrow_scope"} <= actions
    assert all(p.rationale for p in proposals), "every option needs a reason"


def test_severity_gap_is_symmetric():
    assert severity_gap("info", "critical") == severity_gap("critical", "info") == 4


# ===========================================================================
# integration
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
        name=f"cog-{suffix}", root_domain=f"{suffix}.cog.test",
        authorisation="unit test",
        scope_rules=[(f"*.{suffix}.cog.test", "allow", "owned")],
    )
    return tid, suffix


@needs_db
def test_escalation_marks_the_run_escalated_not_failed(mem, target):
    """The whole point. A run that stopped and asked is not a broken run."""
    tid, _ = target
    run = mem.start_run(tid)
    confusion = Confusion(signals=[
        Signal("contradicts_confirmed", 0.75, {"note": "test"}, memory_refs=["x"])
    ])
    state_id = mem.escalate(run, tid, confusion, resource="test finding")
    assert state_id

    row = next(r for r in mem.runs() if str(r["id"]) == run)
    assert row["status"] == "escalated"
    assert row["status"] != "failed"


@needs_db
def test_escalation_records_reasons_and_proposals(mem, target):
    tid, _ = target
    run = mem.start_run(tid)
    confusion = Confusion(signals=detect_contradiction(
        proposed_severity="info", proposed_title="Admin export",
        priors=[{"id": str(uuid.uuid4()), "title": "Admin export", "severity": "critical",
                 "distance": 0.04, "status": "confirmed"}],
    ))
    mem.escalate(run, tid, confusion, resource="Admin export")

    open_states = [s for s in mem.open_escalations() if str(s["run_id"]) == run]
    assert open_states, "the escalation must be visible to an operator"
    state = open_states[0]
    assert float(state["confusion_score"]) > ESCALATION_THRESHOLD
    assert state["reasons"], "an escalation with no stated reason is useless"
    assert state["proposals"], "an escalation with no options is a dead end"
    assert state["reasons"][0]["memory_refs"], "proposals must cite the evidence"


@needs_db
def test_escalation_can_be_resolved(mem, target):
    tid, _ = target
    run = mem.start_run(tid)
    state_id = mem.escalate(
        run, tid, Confusion(signals=[Signal("ambiguous_scope", 0.8, {})])
    )

    mem.resolve_escalation(state_id, resolution="clarified scope with an explicit rule")
    still_open = [s for s in mem.open_escalations() if str(s["id"]) == state_id]
    assert not still_open


@needs_db
def test_ambiguous_scope_is_detected_from_real_rules(mem):
    """Two rules that both match and disagree, read out of the ledger."""
    suffix = uuid.uuid4().hex[:8]
    tid = mem.create_target(
        name=f"amb-{suffix}", root_domain=f"{suffix}.amb.test",
        authorisation="unit test",
        scope_rules=[
            (f"*.{suffix}.amb.test", "allow", "the estate"),
            (f"api.{suffix}.amb.test", "deny", "shared infrastructure"),
        ],
    )
    matching = mem.matching_scope_rules(tid, f"api.{suffix}.amb.test")
    assert len(matching) == 2

    signal = detect_ambiguous_scope(f"api.{suffix}.amb.test", matching)
    assert signal is not None

    # The guard still resolves it safely regardless of the ambiguity.
    assert mem.check_scope(tid, f"api.{suffix}.amb.test") is False


@needs_db
def test_similar_beliefs_carry_epistemic_status(mem, target):
    tid, suffix = target
    run = mem.start_run(tid)
    mem.commit_finding(tid, Candidate(
        host=f"a.{suffix}.cog.test", title="Exposed admin console",
        severity="critical", summary="An admin panel answers unauthenticated.",
        source_kind="exposure", analyst_certainty=0.9,
    ), run_id=run)

    priors = mem.similar_beliefs(tid, "Exposed admin console\nAn admin panel answers unauthenticated.")
    assert priors
    assert "status" in priors[0] and "distance" in priors[0]
