"""MNEMOS gateway — the single audited choke point.

Every write to memory in the whole system goes through this process. The scanner
and the analyst have no database credentials of their own in production; they call
here, and here is where scope is checked, duplicates are stopped, and the audit row
is written.

Read endpoints exist so Mission Control can show live state instead of fixtures.
They are strictly read-only: there is no route that mutates memory without passing
through :meth:`Memory.commit_finding`.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from mnemos_memory import (
    Candidate,
    CostCeilingExceeded,
    Memory,
    ScopeViolation,
    migrate,
)

log = logging.getLogger(__name__)

Severity = Literal["info", "low", "medium", "high", "critical"]


class ScopeRule(BaseModel):
    pattern: str = Field(..., examples=["*.sandbox.mnemos.test"])
    effect: Literal["allow", "deny"]
    reason: str


class TargetIn(BaseModel):
    name: str
    root_domain: str
    authorisation: str = Field(..., description="Written authorisation for testing this estate")
    scope_rules: list[ScopeRule]


class FindingIn(BaseModel):
    target_id: str
    run_id: str
    host: str
    title: str
    severity: Severity
    summary: str
    evidence: str = ""


class ScopeQuery(BaseModel):
    target_id: str
    host: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.getenv("MNEMOS_AUTO_MIGRATE", "1") == "1":
        try:
            migrate(verbose=False)
        except Exception as exc:  # pragma: no cover - startup diagnostics
            log.error("migrations failed at startup: %s", exc)
    yield


app = FastAPI(
    title="MNEMOS gateway",
    version="0.1.0",
    summary="Scope guard, dedup, and audit in front of CockroachDB",
    lifespan=lifespan,
)

# Mission Control is served from a different origin (Vercel), so the read model
# needs CORS. Writes are not exposed to the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in os.getenv("MNEMOS_CORS_ORIGINS", "*").split(",") if o],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def get_memory() -> Memory:
    mem = Memory()
    try:
        yield mem
    finally:
        mem.close()


@app.get("/health")
def health(mem: Memory = Depends(get_memory)) -> dict[str, Any]:
    """Liveness plus a real query, so a dead database fails the check."""
    try:
        stats = mem.stats()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"memory layer unreachable: {exc}") from exc
    return {"status": "ok", "memory": stats, "embedder": mem.embedder.model_id}


# ---------------------------------------------------------------------------
# writes — the guarded paths
# ---------------------------------------------------------------------------
@app.post("/targets", status_code=201)
def create_target(body: TargetIn, mem: Memory = Depends(get_memory)) -> dict[str, str]:
    try:
        target_id = mem.create_target(
            name=body.name,
            root_domain=body.root_domain,
            authorisation=body.authorisation,
            scope_rules=[(r.pattern, r.effect, r.reason) for r in body.scope_rules],
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"target_id": target_id}


@app.post("/runs", status_code=201)
def start_run(
    target_id: str, pass_no: int = 1, ceiling_usd: float = 5.0,
    mem: Memory = Depends(get_memory),
) -> dict[str, str]:
    return {"run_id": mem.start_run(target_id, pass_no=pass_no, ceiling_usd=ceiling_usd)}


@app.post("/scope/check")
def check_scope(body: ScopeQuery, mem: Memory = Depends(get_memory)) -> dict[str, Any]:
    """Fail-closed. A 200 with allowed=false is the expected answer, not an error."""
    return {"host": body.host, "allowed": mem.check_scope(body.target_id, body.host)}


@app.post("/findings", status_code=201)
def propose_finding(body: FindingIn, response: Response, mem: Memory = Depends(get_memory)) -> dict[str, Any]:
    """Propose a finding. The gateway decides whether it survives.

    409 means memory already knew — that is a success for the system, and the
    caller should treat it as "nothing new here", not as an error to retry.
    """
    candidate = Candidate(
        host=body.host, title=body.title, severity=body.severity,
        summary=body.summary, evidence=body.evidence,
    )
    try:
        finding_id = mem.commit_finding(body.target_id, candidate, run_id=body.run_id)
    except ScopeViolation as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except CostCeilingExceeded as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc

    if finding_id is None:
        response.status_code = 409
        return {"written": False, "reason": "duplicate — already in memory"}
    return {"written": True, "finding_id": finding_id}


# ---------------------------------------------------------------------------
# reads — Mission Control's live data
# ---------------------------------------------------------------------------
@app.get("/memory/recall")
def recall(target_id: str, q: str, k: int = 5, mem: Memory = Depends(get_memory)) -> dict[str, Any]:
    hits = mem.recall(target_id, q, k=k)
    return {
        "query": q,
        "results": [
            {"kind": h.kind, "content": h.content, "distance": h.distance,
             "run_id": h.run_id, "finding_id": h.finding_id}
            for h in hits
        ],
    }


@app.get("/findings")
def list_findings(target_id: str | None = None, limit: int = 100,
                  mem: Memory = Depends(get_memory)) -> list[dict[str, Any]]:
    return mem.findings(target_id, limit)


@app.get("/runs")
def list_runs(limit: int = 50, mem: Memory = Depends(get_memory)) -> list[dict[str, Any]]:
    return mem.runs(limit)


@app.get("/audit")
def audit(limit: int = 100, mem: Memory = Depends(get_memory)) -> list[dict[str, Any]]:
    return mem.audit_tail(limit)


@app.get("/stats")
def stats(mem: Memory = Depends(get_memory)) -> dict[str, int]:
    return mem.stats()
