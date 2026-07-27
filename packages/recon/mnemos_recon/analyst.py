"""The analyst.

Deliberately the thinnest layer in the system. It has no network access, no write
access, and no say over scope. It receives an observation plus whatever memory was
recalled for it, and returns a proposed finding that the gateway is free to reject.

Production runs Claude on Amazon Bedrock. The offline analyst is used when no AWS
credentials are configured so the test suite and `make demo` stay runnable; it
applies the same prompt contract deterministically and reports itself honestly in
`agent_runs.model`.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Protocol, Sequence

from mnemos_memory import Candidate, Recalled
from mnemos_memory.embeddings import aws_credentials_usable

from .scanner import Observation

log = logging.getLogger(__name__)

DEFAULT_MODEL = os.getenv("BEDROCK_ANALYST_MODEL", "us.anthropic.claude-sonnet-4-5-v1:0")

# Bedrock on-demand pricing for Claude Sonnet, USD per 1K tokens. Used to charge the
# run so the cost ceiling is enforced against real numbers rather than a guess.
PRICE_IN_PER_1K = 0.003
PRICE_OUT_PER_1K = 0.015

SYSTEM_PROMPT = """You are the analyst stage of MNEMOS, a reconnaissance agent.

You will be given ONE deterministic observation from a scanner, plus RECALLED
MEMORY: context and conclusions from previous runs against this same target.

Rules:
- You never browse, fetch, or execute anything. You only reason over what you are given.
- You do not decide scope. The gateway does that after you answer.
- If recalled memory shows this issue was already reported, say so plainly in the
  summary rather than inventing novelty.
- Be specific and short. A triage engineer reads this at 2am.

Reply with ONLY a JSON object:
{"title": str, "severity": "info|low|medium|high|critical", "summary": str}"""


@dataclass
class Proposal:
    candidate: Candidate
    input_tokens: int
    output_tokens: int
    cost_usd: float
    model: str


class Analyst(Protocol):
    model_id: str

    def propose(self, obs: Observation, recalled: Sequence[Recalled]) -> Proposal: ...


def _render_memory(recalled: Sequence[Recalled]) -> str:
    if not recalled:
        return "RECALLED MEMORY: none — this is the first time we have looked at this target."
    lines = ["RECALLED MEMORY (closest first):"]
    for item in recalled[:6]:
        lines.append(f"- [{item.kind} d={item.distance:.3f}] {item.content[:220]}")
    return "\n".join(lines)


def _user_prompt(obs: Observation, recalled: Sequence[Recalled]) -> str:
    return (
        f"OBSERVATION\n"
        f"  host:     {obs.host}\n"
        f"  kind:     {obs.kind}\n"
        f"  detail:   {obs.detail}\n"
        f"  severity: {obs.severity} (scanner's deterministic guess)\n"
        f"  evidence: {obs.evidence}\n\n"
        f"{_render_memory(recalled)}"
    )


class BedrockAnalyst:
    """Claude on Amazon Bedrock."""

    def __init__(self, model_id: str = DEFAULT_MODEL, region: str | None = None):
        import boto3

        self.model_id = model_id
        self._client = boto3.client(
            "bedrock-runtime", region_name=region or os.getenv("AWS_REGION", "us-east-1")
        )

    def propose(self, obs: Observation, recalled: Sequence[Recalled]) -> Proposal:
        resp = self._client.converse(
            modelId=self.model_id,
            system=[{"text": SYSTEM_PROMPT}],
            messages=[{"role": "user", "content": [{"text": _user_prompt(obs, recalled)}]}],
            inferenceConfig={"maxTokens": 512, "temperature": 0.0},
        )
        text = resp["output"]["message"]["content"][0]["text"].strip()
        usage = resp.get("usage", {})
        tin = int(usage.get("inputTokens", 0))
        tout = int(usage.get("outputTokens", 0))

        payload = _parse_json_object(text)
        return Proposal(
            candidate=Candidate(
                host=obs.host,
                title=payload.get("title") or obs.detail,
                severity=_coerce_severity(payload.get("severity"), obs.severity),
                summary=payload.get("summary") or obs.detail,
                evidence=obs.evidence,
            ),
            input_tokens=tin,
            output_tokens=tout,
            cost_usd=(tin / 1000) * PRICE_IN_PER_1K + (tout / 1000) * PRICE_OUT_PER_1K,
            model=self.model_id,
        )


class OfflineAnalyst:
    """Deterministic stand-in. Same contract, no model, clearly labelled."""

    model_id = "offline-analyst-v1"

    def propose(self, obs: Observation, recalled: Sequence[Recalled]) -> Proposal:
        prior = [r for r in recalled if r.kind == "finding" and r.distance < 0.25]
        if prior:
            summary = (
                f"{obs.detail} on {obs.host}. Memory shows related prior context "
                f"({len(prior)} matching finding(s) from earlier runs), so this is "
                f"most likely a recurrence rather than a new exposure."
            )
        else:
            summary = (
                f"{obs.detail} observed on {obs.host}. No prior context recalled for "
                f"this target, so treating it as newly surfaced. Evidence: {obs.evidence}"
            )
        prompt_len = len(SYSTEM_PROMPT) + len(_user_prompt(obs, recalled))
        return Proposal(
            candidate=Candidate(
                host=obs.host,
                title=obs.detail,
                severity=obs.severity,
                summary=summary,
                evidence=obs.evidence,
            ),
            # Charged so the ceiling logic is exercised identically offline.
            input_tokens=prompt_len // 4,
            output_tokens=len(summary) // 4,
            cost_usd=0.0,
            model=self.model_id,
        )


_SEVERITIES = {"info", "low", "medium", "high", "critical"}


def _coerce_severity(value: object, fallback: str) -> str:
    if isinstance(value, str) and value.lower() in _SEVERITIES:
        return value.lower()
    return fallback if fallback in _SEVERITIES else "info"


def _parse_json_object(text: str) -> dict:
    """Models sometimes wrap JSON in prose or a fence. Take the first object."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
    log.warning("analyst returned unparseable output; falling back to scanner detail")
    return {}


def get_analyst(force: str | None = None) -> Analyst:
    choice = (force or os.getenv("MNEMOS_ANALYST") or "auto").lower()
    if choice == "offline":
        return OfflineAnalyst()
    if choice == "bedrock":
        return BedrockAnalyst()

    # Same check the embedder uses: credentials that exist but are rejected must
    # degrade to the offline analyst rather than failing on the first observation.
    if aws_credentials_usable():
        try:
            return BedrockAnalyst()
        except Exception as exc:  # pragma: no cover
            log.warning("Bedrock analyst unavailable (%s)", exc)

    log.warning("No usable AWS credentials — using %s", OfflineAnalyst.model_id)
    return OfflineAnalyst()
