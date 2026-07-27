"""Confidence as a belief that updates, rather than a number someone picked.

Every function here is pure. The arithmetic of belief is the part most likely to
be subtly wrong, and it is much easier to argue about when it is not tangled up
with SQL.

The model is Bayesian updating in log-odds space. Each piece of evidence carries a
likelihood ratio — how much more likely we are to see this evidence if the finding
is real than if it is not — and evidence composes by addition in log space:

    logit(posterior) = logit(prior) + Σ log(LR_i)

Two deliberate constraints:

* **Confidence never reaches 0 or 1.** A belief that cannot be moved by new
  evidence is not a belief, it is a constant. Everything is clamped into
  [0.02, 0.98], which also keeps the log-odds finite.

* **Recall cannot manufacture certainty.** Being surfaced by a semantic query is
  weak evidence at best, and it is *self-reinforcing* — a finding that ranks
  highly gets recalled more, which would inflate its confidence, which is
  circular. Recall-driven updates therefore use a small likelihood ratio and are
  capped: they can carry a finding to `RECALL_CONFIDENCE_CEILING` and no further.
  Getting past that requires a genuine re-observation by the scanner.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Literal

EpistemicStatus = Literal[
    "hypothesis", "corroborated", "confirmed", "deprecated", "false_positive"
]

# Beliefs live strictly inside this interval. See module docstring.
MIN_CONFIDENCE = 0.02
MAX_CONFIDENCE = 0.98

# How reliable each kind of observation is, expressed as the prior probability
# that an observation of this kind reflects something real.
#
# These are ordered by how much interpretation stands between the bytes and the
# claim. A `pk_live_` prefix either is or is not in the file — almost no
# inference. "This host was referenced" is a true statement about the bytes but a
# weak claim about the world: the host may not exist, may not be ours, may be a
# placeholder in a comment.
SOURCE_RELIABILITY: dict[str, float] = {
    "secret": 0.90,     # a specific, high-entropy pattern matched
    "exposure": 0.80,   # a server told us something it should not have
    "endpoint": 0.65,   # a path appears in client code; existence not verified
    "subdomain": 0.45,  # a hostname was referenced; nothing else is implied
}
DEFAULT_SOURCE_RELIABILITY = 0.50

# Likelihood ratios for each kind of evidence.
LR_REOBSERVED = 3.0        # the scanner independently saw it again
LR_RECALLED = 1.12         # a later query surfaced it as relevant — weak, capped
LR_ANALYST_CONFIDENT = 2.0 # the analyst asserted high certainty
LR_ANALYST_UNSURE = 0.6    # the analyst hedged; that is evidence too

# Recall alone cannot push a belief past this. Only re-observation can.
RECALL_CONFIDENCE_CEILING = 0.75

# A prior finding this close (cosine distance) that was ruled a false positive
# poisons a new one. Deliberately looser than DEDUP_DISTANCE: dedup asks "is this
# literally the same finding?", poisoning asks "have we been wrong about this
# kind of thing here before?" — a broader and more forgiving question.
FALSE_POSITIVE_RADIUS = 0.35
FALSE_POSITIVE_PENALTY = 0.3   # multiplier, per the spec

# Thresholds for deriving a status from the belief.
CORROBORATED_AT = 0.55
CONFIRMED_AT = 0.85

# Once a human says "this is wrong" or "stop tracking this", automatic
# recomputation must not quietly undo it.
TERMINAL_STATUSES: frozenset[str] = frozenset({"false_positive", "deprecated"})


def _clamp(p: float) -> float:
    return max(MIN_CONFIDENCE, min(MAX_CONFIDENCE, p))


def _logit(p: float) -> float:
    p = _clamp(p)
    return math.log(p / (1.0 - p))


def _sigmoid(x: float) -> float:
    # Branch on sign to avoid overflow in exp for large |x|.
    if x >= 0:
        return _clamp(1.0 / (1.0 + math.exp(-x)))
    e = math.exp(x)
    return _clamp(e / (1.0 + e))


def update(prior: float, *likelihood_ratios: float) -> float:
    """Apply Bayesian evidence to a prior belief."""
    odds = _logit(prior)
    for lr in likelihood_ratios:
        if lr <= 0:
            raise ValueError("likelihood ratio must be positive")
        odds += math.log(lr)
    return _sigmoid(odds)


@dataclass(frozen=True)
class PriorLink:
    """One prior belief that bore on a new one."""

    finding_id: str
    similarity: float          # 1 - cosine distance, so 1.0 is identical
    status: str
    effect: str = ""           # human-readable note for the audit trail

    def as_json(self) -> dict[str, Any]:
        return {
            "prior_finding_id": self.finding_id,
            "similarity": round(self.similarity, 4),
            "prior_status": self.status,
            "effect": self.effect,
            "at": datetime.now(timezone.utc).isoformat(),
        }


@dataclass
class Belief:
    """A confidence, the evidence behind it, and where it came from."""

    confidence: float
    evidence_count: int
    status: EpistemicStatus
    chain: list[dict[str, Any]] = field(default_factory=list)


def initial_confidence(
    *,
    source_kind: str,
    analyst_certainty: float | None,
    corroborating_priors: int,
) -> float:
    """The belief a finding is born with, before any poisoning is applied.

    Three inputs, in decreasing order of trustworthiness:

    1. **Source reliability.** What kind of observation produced it. This is the
       prior, because it is the only input that does not depend on a model.
    2. **Analyst certainty.** Treated as evidence, not as the answer — a confident
       assertion raises the belief, a hedge lowers it, and neither replaces the
       prior outright.
    3. **Corroborating priors.** Similar findings already in memory. Each adds
       evidence with diminishing returns, so twenty near-duplicates cannot
       manufacture certainty that one good observation could not.
    """
    prior = SOURCE_RELIABILITY.get(source_kind, DEFAULT_SOURCE_RELIABILITY)
    ratios: list[float] = []

    if analyst_certainty is not None:
        # Map [0,1] certainty onto a likelihood ratio spanning unsure..confident.
        certainty = max(0.0, min(1.0, analyst_certainty))
        ratios.append(
            LR_ANALYST_UNSURE
            + (LR_ANALYST_CONFIDENT - LR_ANALYST_UNSURE) * certainty
        )

    # Diminishing returns: the nth corroboration is worth less than the first,
    # because near-duplicate observations are rarely independent.
    for n in range(min(corroborating_priors, 5)):
        ratios.append(1.0 + (0.35 / (n + 1)))

    return update(prior, *ratios)


def apply_false_positive_memory(
    confidence: float, poisoning: Iterable[PriorLink]
) -> tuple[float, list[PriorLink]]:
    """Discount a belief because we have been wrong about something like it here.

    This is the whole point of remembering mistakes. A scanner with no memory
    re-raises the same false positive every run and burns the operator's trust;
    one that remembers starts the same claim at a third of the confidence and
    labels it a hypothesis until something better arrives.

    Only the closest prior false positive applies. Stacking multipliers across
    several near-identical priors would drive the belief to zero for what is
    really one past mistake observed repeatedly.
    """
    applicable = [p for p in poisoning if p.status == "false_positive"]
    if not applicable:
        return confidence, []

    closest = max(applicable, key=lambda p: p.similarity)
    return _clamp(confidence * FALSE_POSITIVE_PENALTY), [
        PriorLink(
            finding_id=closest.finding_id,
            similarity=closest.similarity,
            status=closest.status,
            effect=(
                f"confidence x{FALSE_POSITIVE_PENALTY} — a finding this similar "
                f"was previously ruled a false positive"
            ),
        )
    ]


def derive_status(
    confidence: float, evidence_count: int, current: str | None = None
) -> EpistemicStatus:
    """Status follows from the belief, except where a human has overruled it.

    `false_positive` and `deprecated` are sticky. An operator saying "this is
    wrong" is itself evidence, and stronger than anything the pipeline produces —
    so recomputation must never quietly promote it back to `confirmed`.
    """
    if current in TERMINAL_STATUSES:
        return current  # type: ignore[return-value]

    if confidence >= CONFIRMED_AT and evidence_count >= 3:
        return "confirmed"
    if confidence >= CORROBORATED_AT and evidence_count >= 2:
        return "corroborated"
    return "hypothesis"


def on_reobservation(belief: Belief, *, source_kind: str) -> Belief:
    """The scanner independently saw it again. The strongest evidence we get."""
    reliability = SOURCE_RELIABILITY.get(source_kind, DEFAULT_SOURCE_RELIABILITY)
    # A re-observation from a flaky source is worth less than one from a precise
    # source, so the ratio is scaled by reliability rather than applied flat.
    lr = 1.0 + (LR_REOBSERVED - 1.0) * reliability
    confidence = update(belief.confidence, lr)
    evidence = belief.evidence_count + 1
    return Belief(confidence, evidence, derive_status(confidence, evidence, belief.status),
                  belief.chain)


def on_recall(belief: Belief) -> Belief:
    """A later query surfaced this as relevant.

    Weak, and capped. Recall frequency correlates with a finding's own ranking, so
    letting it drive confidence upward without limit is a feedback loop that
    manufactures certainty from popularity. Past the ceiling this records the
    evidence and leaves the belief alone.
    """
    evidence = belief.evidence_count + 1

    if belief.confidence >= RECALL_CONFIDENCE_CEILING:
        return Belief(belief.confidence, evidence,
                      derive_status(belief.confidence, evidence, belief.status),
                      belief.chain)

    confidence = min(RECALL_CONFIDENCE_CEILING, update(belief.confidence, LR_RECALLED))
    return Belief(confidence, evidence, derive_status(confidence, evidence, belief.status),
                  belief.chain)
