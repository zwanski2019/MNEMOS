"""One recon cycle, in the fixed order the whole design rests on.

    scan -> index -> RECALL -> reason -> DEDUP -> scope -> write -> reconcile -> audit

The ordering is the product. `_cycle` is the only place that ordering is expressed,
so there is exactly one thing to review.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Sequence

from mnemos_memory import (
    Candidate,
    CostCeilingExceeded,
    Memory,
    Reconciliation,
    ScopeViolation,
)

from .analyst import Analyst, Proposal, get_analyst
from .sandbox import (
    AUTHORISATION,
    OUT_OF_SCOPE_PROBE,
    ROOT_DOMAIN,
    SCOPE_RULES,
    SECOND_AUTHORISATION,
    SECOND_ROOT_DOMAIN,
    SECOND_SCOPE_RULES,
    SandboxAsset,
    pass_assets,
    second_estate_assets,
)
from .scanner import Observation, scan

log = logging.getLogger(__name__)


@dataclass
class CycleResult:
    run_id: str
    pass_no: int
    observations: int = 0
    recalled: int = 0
    written: int = 0
    deduped: int = 0
    denied: int = 0
    halted: bool = False
    halt_reason: str = ""
    cost_usd: float = 0.0
    new_titles: list[str] = field(default_factory=list)
    reconciliation: Reconciliation = field(default_factory=Reconciliation)


def ensure_target(mem: Memory) -> str:
    """Create the sandbox target and its scope rules (idempotent)."""
    return mem.create_target(
        name="MNEMOS sandbox estate",
        root_domain=ROOT_DOMAIN,
        authorisation=AUTHORISATION,
        scope_rules=SCOPE_RULES,
    )


def ensure_second_target(mem: Memory) -> str:
    """The second estate, so cross-target correlation has something true to find."""
    return mem.create_target(
        name="Acme Labs estate",
        root_domain=SECOND_ROOT_DOMAIN,
        authorisation=SECOND_AUTHORISATION,
        scope_rules=SECOND_SCOPE_RULES,
    )


def run_cycle(
    mem: Memory,
    target_id: str,
    pass_no: int,
    *,
    analyst: Analyst | None = None,
    ceiling_usd: float = 5.0,
) -> CycleResult:
    """A visit to the primary sandbox estate."""
    return _cycle(
        mem, target_id, pass_no, pass_assets(pass_no),
        analyst=analyst, ceiling_usd=ceiling_usd, out_of_scope_probe=OUT_OF_SCOPE_PROBE,
    )


def run_second_estate(
    mem: Memory, target_id: str, *, analyst: Analyst | None = None, ceiling_usd: float = 5.0
) -> CycleResult:
    """One pass over the second estate, using the identical cycle.

    Nothing here is special-cased. It is the same code path, which is the point:
    correlation emerges from memory holding both estates, not from a bespoke query
    written to make the demo look good.
    """
    return _cycle(
        mem, target_id, 1, second_estate_assets(), analyst=analyst,
        ceiling_usd=ceiling_usd, out_of_scope_probe="payments.acme-labs.mnemos.test",
    )


def _cycle(
    mem: Memory,
    target_id: str,
    pass_no: int,
    assets: Sequence[SandboxAsset],
    *,
    analyst: Analyst | None,
    ceiling_usd: float,
    out_of_scope_probe: str,
) -> CycleResult:
    analyst = analyst or get_analyst()
    run_id = mem.start_run(
        target_id, pass_no=pass_no, ceiling_usd=ceiling_usd, model=analyst.model_id
    )
    result = CycleResult(run_id=run_id, pass_no=pass_no)
    observed_fingerprints: list[str] = []
    completed = False

    try:
        # 1-3. Deterministic scan, artifact addressing, and embedding.
        observations: list[Observation] = []
        for asset in assets:
            asset_id = mem.record_asset(target_id, asset.kind, asset.url, run_id=run_id)
            artifact_id = mem.record_artifact(
                target_id, asset_id, asset.body.encode(),
                content_type="application/javascript",
            )
            mem.index_text(target_id, asset.body, artifact_id=artifact_id, run_id=run_id)
            observations.extend(scan(asset.host, asset.url, asset.body))
        result.observations = len(observations)

        # The guard is exercised against something genuinely out of scope, so the
        # audit trail contains a real denial and not just a happy path.
        if not mem.check_scope(target_id, out_of_scope_probe, run_id=run_id):
            result.denied += 1

        for obs in observations:
            # 4. RECALL — before the analyst is allowed to form an opinion.
            recalled = mem.recall(target_id, f"{obs.detail} {obs.evidence}", k=4, run_id=run_id)
            result.recalled += len(recalled)

            # 5. Reason. The analyst sees memory; it does not get to write to it.
            proposal: Proposal = analyst.propose(obs, recalled)
            try:
                mem.charge(
                    run_id,
                    input_tokens=proposal.input_tokens,
                    output_tokens=proposal.output_tokens,
                    cost_usd=proposal.cost_usd,
                )
            except CostCeilingExceeded as exc:
                result.halted = True
                result.halt_reason = str(exc)
                log.warning("run %s halted: %s", run_id, exc)
                break

            observed_fingerprints.append(proposal.candidate.fingerprint())

            # 6. DEDUP, then scope, then write — all inside commit_finding.
            try:
                finding_id = mem.commit_finding(target_id, proposal.candidate, run_id=run_id)
            except ScopeViolation:
                result.denied += 1
                continue

            if finding_id:
                result.written += 1
                result.new_titles.append(proposal.candidate.title)
            else:
                result.deduped += 1
        else:
            completed = True

        # 7. Reconcile — only on a complete pass. A halted run saw a partial view of
        # the estate, and marking live findings as "fixed" off a partial observation
        # set would be worse than not reconciling at all.
        if completed:
            result.reconciliation = mem.reconcile(target_id, run_id, observed_fingerprints)

    finally:
        summary = mem.finish_run(run_id, status="halted" if result.halted else "complete")
        if summary:
            result.cost_usd = float(summary.get("cost_usd") or 0)

    return result
