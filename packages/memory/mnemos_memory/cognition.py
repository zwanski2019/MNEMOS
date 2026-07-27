"""Knowing when to stop.

An agent that cannot tell coherence from confusion will always produce output,
and some of that output will be confident nonsense. This module detects the
states where continuing is worse than stopping, and turns them into an escalation
an operator can adjudicate.

Escalation is a success state. `agent_runs.status = 'escalated'` is deliberately
distinct from `'failed'`, because a run that stopped and asked is the system
working, and a dashboard that colours it red will train people to suppress it.

Four signals, each scored in [0,1] with the evidence that produced it:

1. **Contradiction with a confirmed belief.** Memory holds a `confirmed` finding
   that is semantically almost identical to what the analyst just concluded, but
   the conclusion differs materially. One of the two is wrong and the agent
   cannot tell which.
2. **Confident disagreement.** Very high similarity to prior memory, yet the
   analyst reached a different severity. Weaker than (1) because the prior may
   not be confirmed, but the same shape of problem.
3. **Ambiguous authorisation.** More than one scope rule matches the host and
   they disagree. The guard resolves this safely (deny wins), but *safe* is not
   the same as *intended*, and a human wrote those rules meaning something.
4. **Burning budget without covering ground.** Spend is near the ceiling while
   most of the observation set is still unprocessed — the run will halt on cost
   having looked at a biased sample, and a partial sample presented as a result
   is misleading.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

# Above this the cycle stops and asks. Chosen so that a single moderate signal
# does not halt a run, but any strong signal or two moderate ones will.
ESCALATION_THRESHOLD = 0.7

# How close two findings must be before disagreeing about them is a contradiction
# rather than a coincidence. Tighter than the false-positive radius: this claims
# "these are the same thing", which is a stronger statement.
CONTRADICTION_DISTANCE = 0.18

# Severity ordering, for deciding whether two conclusions differ *materially*.
# One step apart is disagreement; two or more is a contradiction worth stopping
# for. Reasonable analysts differ between medium and high; nobody sane calls the
# same thing `info` and `critical`.
_SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
MATERIAL_SEVERITY_GAP = 2

SIGNAL_WEIGHTS = {
    "contradicts_confirmed": 0.75,
    "confident_disagreement": 0.35,
    "ambiguous_scope": 0.45,
    "budget_without_coverage": 0.40,
}


@dataclass
class Signal:
    """One reason the agent is unsure, and what it is unsure about."""

    name: str
    score: float
    detail: dict[str, Any]
    memory_refs: list[str] = field(default_factory=list)

    def as_json(self) -> dict[str, Any]:
        return {
            "signal": self.name,
            "score": round(self.score, 4),
            "detail": self.detail,
            "memory_refs": self.memory_refs,
        }


@dataclass
class Proposal:
    """A course of action the operator could take, and what supports it."""

    action: str
    rationale: str
    memory_refs: list[str] = field(default_factory=list)

    def as_json(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "rationale": self.rationale,
            "memory_refs": self.memory_refs,
        }


@dataclass
class Confusion:
    signals: list[Signal] = field(default_factory=list)
    proposals: list[Proposal] = field(default_factory=list)

    @property
    def score(self) -> float:
        """Combine signals so that independent doubts accumulate but cannot exceed 1.

        Noisy-OR rather than a sum: three weak signals should raise concern
        without three of them alone forcing a halt, and no number of signals
        should produce a score above certainty.
        """
        remaining = 1.0
        for signal in self.signals:
            remaining *= 1.0 - max(0.0, min(1.0, signal.score))
        return round(1.0 - remaining, 5)

    @property
    def should_escalate(self) -> bool:
        return self.score > ESCALATION_THRESHOLD

    def as_reasons(self) -> list[dict[str, Any]]:
        return [s.as_json() for s in self.signals]

    def as_proposals(self) -> list[dict[str, Any]]:
        return [p.as_json() for p in self.proposals]


def severity_gap(a: str, b: str) -> int:
    return abs(_SEVERITY_RANK.get(a, 0) - _SEVERITY_RANK.get(b, 0))


def detect_contradiction(
    *,
    proposed_severity: str,
    proposed_title: str,
    priors: Sequence[dict[str, Any]],
) -> list[Signal]:
    """Compare a fresh conclusion against what memory already believes.

    `priors` are rows carrying at least: id, title, severity, distance, and the
    epistemic status of the prior belief.
    """
    signals: list[Signal] = []

    for prior in priors:
        distance = float(prior.get("distance", 1.0))
        if distance > CONTRADICTION_DISTANCE:
            continue

        gap = severity_gap(proposed_severity, str(prior.get("severity", "info")))
        if gap < MATERIAL_SEVERITY_GAP:
            continue

        status = str(prior.get("status", "hypothesis"))
        # Contradicting something an operator confirmed is a much bigger deal than
        # contradicting an untested hypothesis — the latter is how hypotheses are
        # supposed to die.
        if status == "confirmed":
            signals.append(Signal(
                name="contradicts_confirmed",
                score=SIGNAL_WEIGHTS["contradicts_confirmed"],
                detail={
                    "proposed": {"title": proposed_title, "severity": proposed_severity},
                    "confirmed_prior": {
                        "title": prior.get("title"), "severity": prior.get("severity"),
                    },
                    "distance": round(distance, 4),
                    "severity_gap": gap,
                },
                memory_refs=[str(prior.get("id"))],
            ))
        elif status not in ("false_positive", "deprecated"):
            signals.append(Signal(
                name="confident_disagreement",
                score=SIGNAL_WEIGHTS["confident_disagreement"],
                detail={
                    "proposed_severity": proposed_severity,
                    "prior_severity": prior.get("severity"),
                    "prior_status": status,
                    "distance": round(distance, 4),
                },
                memory_refs=[str(prior.get("id"))],
            ))

    return signals


def detect_ambiguous_scope(host: str, matching_rules: Sequence[dict[str, Any]]) -> Signal | None:
    """More than one rule matches and they disagree about the answer.

    The guard still resolves this safely — an explicit deny always wins — but a
    human wrote both of those rules meaning something, and quietly picking one is
    how a tool ends up out of scope while technically following its config.
    """
    effects = {str(r.get("effect")) for r in matching_rules}
    if len(effects) < 2:
        return None

    return Signal(
        name="ambiguous_scope",
        score=SIGNAL_WEIGHTS["ambiguous_scope"],
        detail={
            "host": host,
            "matching_rules": [
                {"pattern": r.get("pattern"), "effect": r.get("effect"),
                 "reason": r.get("reason")}
                for r in matching_rules
            ],
            "resolved_as": "deny",
            "note": "deny wins, but the intent is unclear and should be made explicit",
        },
    )


def detect_budget_without_coverage(
    *, spent_usd: float, ceiling_usd: float, processed: int, total: int
) -> Signal | None:
    """Most of the budget gone, most of the target unlooked-at.

    The run is about to halt on cost having examined a biased slice — whatever
    happened to come first. Reporting that as a result implies a completeness the
    run does not have.
    """
    if ceiling_usd <= 0 or total <= 0:
        return None

    burn = spent_usd / ceiling_usd
    coverage = processed / total
    if burn < 0.7 or coverage >= 0.5:
        return None

    # Scale with how lopsided it is: 70% spent at 49% coverage is worth mentioning,
    # 95% spent at 10% coverage should stop the run on its own.
    severity = min(1.0, (burn - 0.7) / 0.3 * 0.5 + (0.5 - coverage) / 0.5 * 0.5)
    return Signal(
        name="budget_without_coverage",
        score=round(SIGNAL_WEIGHTS["budget_without_coverage"] + 0.5 * severity, 4),
        detail={
            "spent_usd": round(spent_usd, 4),
            "ceiling_usd": round(ceiling_usd, 4),
            "burn_fraction": round(burn, 3),
            "coverage_fraction": round(coverage, 3),
            "note": "run would halt on cost having seen a biased sample",
        },
    )


def propose_resolutions(confusion: Confusion) -> list[Proposal]:
    """Turn each signal into something an operator can actually decide.

    An escalation that says only "I am confused" wastes the interruption. Each
    proposal carries the memory references that support it so the operator can
    check the agent's reasoning rather than take its word.
    """
    proposals: list[Proposal] = []
    seen: set[str] = set()

    for signal in confusion.signals:
        if signal.name in seen:
            continue
        seen.add(signal.name)

        if signal.name == "contradicts_confirmed":
            prior = signal.detail.get("confirmed_prior", {})
            proposals.append(Proposal(
                action="uphold_prior",
                rationale=(
                    f"Keep the confirmed finding ({prior.get('severity')}) and discard "
                    f"this conclusion. Choose this if the earlier assessment was made "
                    f"with evidence this run did not have."
                ),
                memory_refs=signal.memory_refs,
            ))
            proposals.append(Proposal(
                action="supersede_prior",
                rationale=(
                    f"Accept the new conclusion "
                    f"({signal.detail.get('proposed', {}).get('severity')}) and mark the "
                    f"prior deprecated. Choose this if the target changed or the "
                    f"original was wrong."
                ),
                memory_refs=signal.memory_refs,
            ))
        elif signal.name == "confident_disagreement":
            proposals.append(Proposal(
                action="request_reobservation",
                rationale=(
                    "Re-scan this asset before deciding. The disagreement is with an "
                    "unconfirmed prior, so more evidence is cheaper than a judgement."
                ),
                memory_refs=signal.memory_refs,
            ))
        elif signal.name == "ambiguous_scope":
            proposals.append(Proposal(
                action="clarify_scope",
                rationale=(
                    "Add an explicit rule for this host. Two rules currently match with "
                    "opposite effects; the guard denied, which may not be what was meant."
                ),
            ))
        elif signal.name == "budget_without_coverage":
            proposals.append(Proposal(
                action="raise_ceiling_or_narrow_scope",
                rationale=(
                    "Either raise the per-run ceiling or reduce the asset set. Continuing "
                    "produces a partial result that reads like a complete one."
                ),
            ))

    return proposals
