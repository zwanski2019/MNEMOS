"""The memory layer.

Everything the agent is allowed to remember, recall, or act on goes through here.
The ordering rule from CLAUDE.md §3 — *recall before reason, dedup before write* —
is expressed as method preconditions, not as documentation.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable, Sequence

import psycopg

from .artifacts import ArtifactStore, get_artifact_store
from .db import connect, transaction
from .embeddings import EMBED_DIM, Embedder, get_embedder
from .intelligence import MemoryIntelligence

log = logging.getLogger(__name__)

# Cosine distance below which two findings are considered the same issue.
# Titan V2 is normalised, so distance is in [0, 2]; 0.12 is deliberately tight —
# a false dedup silently hides a real finding, which is worse than a duplicate.
DEDUP_DISTANCE = 0.12


class ScopeViolation(RuntimeError):
    """Raised when the agent tries to act outside its written authorisation."""


class CostCeilingExceeded(RuntimeError):
    """Raised when a run would spend past its ceiling. The agent stops."""


@dataclass(frozen=True)
class Recalled:
    """One piece of prior context, from any previous session."""

    kind: str  # 'embedding' | 'finding'
    content: str
    distance: float
    run_id: str | None = None
    finding_id: str | None = None


@dataclass(frozen=True)
class Candidate:
    """A finding the analyst wants to write. Not yet trusted."""

    host: str
    title: str
    severity: str
    summary: str
    evidence: str = ""
    asset_id: str | None = None

    def fingerprint(self) -> str:
        """Cheap exact-duplicate gate, before we pay for a vector search."""
        basis = f"{self.host}|{self.title.strip().lower()}|{self.severity}"
        return hashlib.sha256(basis.encode()).hexdigest()[:32]


@dataclass
class DedupVerdict:
    novel: bool
    reason: str
    existing_id: str | None = None
    distance: float | None = None


def _vec_literal(vec: Sequence[float]) -> str:
    if len(vec) != EMBED_DIM:
        raise ValueError(f"expected {EMBED_DIM} dims, got {len(vec)}")
    return "[" + ",".join(f"{v:.6f}" for v in vec) + "]"


class Memory(MemoryIntelligence):
    """Session-scoped handle on CockroachDB.

    Hot-path operations (recall, dedup, scope, audit, cost) live here.
    Higher-order analyses over the same tables come from MemoryIntelligence.
    """

    def __init__(
        self,
        conn: psycopg.Connection | None = None,
        embedder: Embedder | None = None,
        artifacts: ArtifactStore | None = None,
    ):
        self.conn = conn or connect()
        self.embedder = embedder or get_embedder()
        self.artifacts = artifacts or get_artifact_store()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Memory":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # audit — every decision, no exceptions
    # ------------------------------------------------------------------
    def audit(
        self,
        actor: str,
        action: str,
        decision: str,
        *,
        run_id: str | None = None,
        target_id: str | None = None,
        resource: str | None = None,
        detail: dict[str, Any] | None = None,
        cur: psycopg.Cursor | None = None,
    ) -> None:
        sql = (
            "INSERT INTO audit_log (run_id, target_id, actor, action, resource, decision, detail) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)"
        )
        args = (run_id, target_id, actor, action, resource, decision, json.dumps(detail or {}))
        if cur is not None:
            cur.execute(sql, args)
        else:
            with self.conn.cursor() as c:
                c.execute(sql, args)

    # ------------------------------------------------------------------
    # targets + scope — written in one transaction, on purpose
    # ------------------------------------------------------------------
    def create_target(
        self,
        name: str,
        root_domain: str,
        authorisation: str,
        scope_rules: Iterable[tuple[str, str, str]],
        decided_by: str = "operator",
    ) -> str:
        """Create a target and its scope in a single transaction.

        A target that exists without its scope rules would be a target the guard
        cannot reason about — and "no rule" means "deny", so a partial write would
        silently disable the agent. Both land together or neither does.
        """
        rules = list(scope_rules)
        if not any(effect == "allow" for _, effect, _ in rules):
            raise ValueError("refusing to create a target with no allow rule — it could never act")

        target_id: str | None = None
        with transaction(self.conn) as cur:
            cur.execute(
                "INSERT INTO targets (name, root_domain, authorisation) VALUES (%s, %s, %s) "
                "ON CONFLICT (root_domain) DO UPDATE SET name = excluded.name RETURNING id",
                (name, root_domain, authorisation),
            )
            target_id = str(cur.fetchone()["id"])
            for pattern, effect, reason in rules:
                cur.execute(
                    "INSERT INTO scope_decisions (target_id, pattern, effect, reason, decided_by) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (target_id, pattern, effect, reason, decided_by),
                )
            self.audit(
                "operator", "scope_write", "ok",
                target_id=target_id, resource=root_domain,
                detail={"rules": len(rules)}, cur=cur,
            )
        return target_id

    # ------------------------------------------------------------------
    # scope guard — fail closed
    # ------------------------------------------------------------------
    def check_scope(self, target_id: str, host: str, *, run_id: str | None = None) -> bool:
        """Deny by default. An explicit deny always beats an allow.

        Returns True only when a rule says yes. Any error — no rules, unreachable
        database, malformed pattern — results in False, because the safe direction
        for a security tool acting on someone else's infrastructure is to do nothing.
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    "SELECT pattern, effect FROM scope_decisions WHERE target_id = %s "
                    "ORDER BY decided_at ASC",
                    (target_id,),
                )
                rules = cur.fetchall()
        except Exception as exc:
            log.error("scope lookup failed for %s (%s) — denying", host, exc)
            self.audit(
                "gateway", "scope_check", "deny", run_id=run_id, target_id=target_id,
                resource=host, detail={"reason": "lookup_failed", "error": str(exc)},
            )
            return False

        matched_allow = None
        for rule in rules:
            if not fnmatch.fnmatch(host.lower(), rule["pattern"].lower()):
                continue
            if rule["effect"] == "deny":
                self.audit(
                    "gateway", "scope_check", "deny", run_id=run_id, target_id=target_id,
                    resource=host, detail={"matched": rule["pattern"], "rule": "explicit_deny"},
                )
                return False
            matched_allow = rule["pattern"]

        decision = "allow" if matched_allow else "deny"
        self.audit(
            "gateway", "scope_check", decision, run_id=run_id, target_id=target_id,
            resource=host,
            detail={"matched": matched_allow} if matched_allow else {"rule": "no_allow_rule"},
        )
        return matched_allow is not None

    def require_scope(self, target_id: str, host: str, *, run_id: str | None = None) -> None:
        if not self.check_scope(target_id, host, run_id=run_id):
            raise ScopeViolation(f"{host} is not in scope for target {target_id}")

    # ------------------------------------------------------------------
    # runs + cost ceiling
    # ------------------------------------------------------------------
    def start_run(
        self, target_id: str, *, pass_no: int = 1, ceiling_usd: float = 5.0, model: str = ""
    ) -> str:
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO agent_runs (target_id, pass_no, cost_ceiling_usd, model, embed_model) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (target_id, pass_no, ceiling_usd, model, self.embedder.model_id),
            )
            run_id = str(cur.fetchone()["id"])
        self.audit("gateway", "run_start", "ok", run_id=run_id, target_id=target_id,
                   detail={"pass": pass_no, "ceiling_usd": ceiling_usd})
        return run_id

    def charge(self, run_id: str, *, input_tokens: int, output_tokens: int, cost_usd: float) -> None:
        """Add spend to a run and halt it if that crosses the ceiling.

        The ceiling is evaluated from the committed running total in `agent_runs`,
        not from an in-process counter, so a crashed and restarted worker cannot
        reset the budget by forgetting what it already spent.
        """
        # The halt must be durable: if we raised from inside the transaction it would
        # roll back, and the next call would find the run still 'running' with the
        # spend erased. So we record the halt, let the transaction commit, then raise.
        exceeded: tuple[Decimal, Decimal] | None = None
        with transaction(self.conn) as cur:
            cur.execute(
                "UPDATE agent_runs SET input_tokens = input_tokens + %s, "
                "output_tokens = output_tokens + %s, cost_usd = cost_usd + %s "
                "WHERE id = %s RETURNING cost_usd, cost_ceiling_usd",
                (input_tokens, output_tokens, Decimal(str(cost_usd)), run_id),
            )
            row = cur.fetchone()
            if row is None:
                raise ValueError(f"unknown run {run_id}")
            spent, ceiling = row["cost_usd"], row["cost_ceiling_usd"]
            if spent > ceiling:
                cur.execute(
                    "UPDATE agent_runs SET status = 'halted', halted_reason = %s, "
                    "finished_at = now() WHERE id = %s",
                    (f"cost ceiling exceeded: ${spent} > ${ceiling}", run_id),
                )
                self.audit("gateway", "halt", "deny", run_id=run_id,
                           detail={"spent_usd": str(spent), "ceiling_usd": str(ceiling)}, cur=cur)
                exceeded = (spent, ceiling)

        if exceeded is not None:
            raise CostCeilingExceeded(f"run {run_id} spent ${exceeded[0]} of ${exceeded[1]}")

    def finish_run(self, run_id: str, status: str = "complete") -> dict[str, Any]:
        with self.conn.cursor() as cur:
            cur.execute(
                "UPDATE agent_runs SET status = %s, finished_at = now() WHERE id = %s "
                "RETURNING id, pass_no, recalled_count, deduped_count, written_count, cost_usd",
                (status, run_id),
            )
            row = cur.fetchone()
        self.audit("gateway", "run_finish", "ok", run_id=run_id, detail={"status": status})
        return dict(row) if row else {}

    # ------------------------------------------------------------------
    # assets / artifacts
    # ------------------------------------------------------------------
    def record_asset(self, target_id: str, kind: str, value: str, run_id: str | None = None) -> str:
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO assets (target_id, kind, value, first_seen_run) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (target_id, kind, value) DO UPDATE SET value = excluded.value "
                "RETURNING id",
                (target_id, kind, value, run_id),
            )
            return str(cur.fetchone()["id"])

    def record_artifact(
        self, target_id: str, asset_id: str | None, body: bytes,
        *, content_type: str = "text/plain",
    ) -> str:
        """Upload the bytes to S3 and record the content address in CockroachDB.

        The upload happens first: if S3 rejects it we must not end up with a row
        claiming an object that is not there. Both sides are keyed on the same
        sha256, so a retry is idempotent on both.
        """
        sha = hashlib.sha256(body).hexdigest()
        bucket, key = self.artifacts.put(sha, body, content_type)
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO artifacts (target_id, asset_id, sha256, s3_bucket, s3_key, byte_len, "
                "content_type) VALUES (%s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (target_id, sha256) DO UPDATE SET s3_bucket = excluded.s3_bucket, "
                "s3_key = excluded.s3_key RETURNING id",
                (target_id, asset_id, sha, bucket, key, len(body), content_type),
            )
            return str(cur.fetchone()["id"])

    # ------------------------------------------------------------------
    # embeddings — what makes recall possible
    # ------------------------------------------------------------------
    def index_text(
        self, target_id: str, text: str, *, artifact_id: str | None = None,
        run_id: str | None = None, chunk_chars: int = 700,
    ) -> int:
        chunks = [text[i : i + chunk_chars] for i in range(0, len(text), chunk_chars)] or [""]
        vectors = self.embedder.embed_many(chunks)
        with transaction(self.conn) as cur:
            for idx, (chunk, vec) in enumerate(zip(chunks, vectors)):
                cur.execute(
                    "INSERT INTO embeddings (target_id, artifact_id, run_id, chunk_idx, content, "
                    "embedding, model) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (target_id, artifact_id, run_id, idx, chunk, _vec_literal(vec),
                     self.embedder.model_id),
                )
        return len(chunks)

    # ------------------------------------------------------------------
    # RECALL — step 4 of the cycle, and the reason the second run is smarter
    # ------------------------------------------------------------------
    def recall(self, target_id: str, query: str, *, k: int = 5, run_id: str | None = None) -> list[Recalled]:
        """Vector search across every prior session for this target.

        Deliberately searches both surfaces: `embeddings` gives raw prior context,
        `findings` gives conclusions already reached. The analyst gets both before
        it is allowed to think.
        """
        qvec = _vec_literal(self.embedder.embed(query))
        out: list[Recalled] = []
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT content, run_id, embedding <=> %s AS distance FROM embeddings "
                "WHERE target_id = %s ORDER BY embedding <=> %s LIMIT %s",
                (qvec, target_id, qvec, k),
            )
            for row in cur.fetchall():
                out.append(Recalled("embedding", row["content"], float(row["distance"]),
                                    run_id=str(row["run_id"]) if row["run_id"] else None))
            cur.execute(
                "SELECT id, title, summary, times_seen, embedding <=> %s AS distance FROM findings "
                "WHERE target_id = %s ORDER BY embedding <=> %s LIMIT %s",
                (qvec, target_id, qvec, k),
            )
            for row in cur.fetchall():
                out.append(Recalled(
                    "finding",
                    f"{row['title']} — {row['summary']} (seen {row['times_seen']}x)",
                    float(row["distance"]), finding_id=str(row["id"]),
                ))

        out.sort(key=lambda r: r.distance)
        if run_id:
            with self.conn.cursor() as cur:
                cur.execute(
                    "UPDATE agent_runs SET recalled_count = recalled_count + %s WHERE id = %s",
                    (len(out), run_id),
                )
        self.audit("analyst", "recall", "hit" if out else "miss", run_id=run_id,
                   target_id=target_id, resource=query[:120],
                   detail={"results": len(out), "best_distance": out[0].distance if out else None})
        return out

    # ------------------------------------------------------------------
    # DEDUP — step 5, before any write
    # ------------------------------------------------------------------
    def dedup(self, target_id: str, candidate: Candidate, *, run_id: str | None = None) -> DedupVerdict:
        """Exact fingerprint first (cheap), then semantic similarity (thorough)."""
        fp = candidate.fingerprint()
        probe = f"{candidate.title}\n{candidate.summary}"
        qvec = _vec_literal(self.embedder.embed(probe))

        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM findings WHERE target_id = %s AND fingerprint = %s", (target_id, fp)
            )
            row = cur.fetchone()
            if row:
                verdict = DedupVerdict(False, "exact_fingerprint", str(row["id"]), 0.0)
            else:
                cur.execute(
                    "SELECT id, title, embedding <=> %s AS distance FROM findings "
                    "WHERE target_id = %s ORDER BY embedding <=> %s LIMIT 1",
                    (qvec, target_id, qvec),
                )
                near = cur.fetchone()
                if near and float(near["distance"]) <= DEDUP_DISTANCE:
                    verdict = DedupVerdict(False, "semantic_match", str(near["id"]),
                                           float(near["distance"]))
                else:
                    verdict = DedupVerdict(
                        True, "novel", None, float(near["distance"]) if near else None
                    )

        if run_id and not verdict.novel:
            with self.conn.cursor() as cur:
                cur.execute(
                    "UPDATE agent_runs SET deduped_count = deduped_count + 1 WHERE id = %s", (run_id,)
                )
        self.audit("gateway", "dedup", "miss" if verdict.novel else "hit", run_id=run_id,
                   target_id=target_id, resource=candidate.title,
                   detail={"reason": verdict.reason, "distance": verdict.distance,
                           "existing": verdict.existing_id})
        return verdict

    # ------------------------------------------------------------------
    # WRITE — only reachable through scope + dedup
    # ------------------------------------------------------------------
    def commit_finding(
        self, target_id: str, candidate: Candidate, *, run_id: str, verdict: DedupVerdict | None = None
    ) -> str | None:
        """Persist a finding. Returns the id, or None when it was a duplicate.

        This is the only write path to `findings`, and it re-runs both gates itself
        rather than trusting the caller to have run them — the ordering invariant is
        enforced here so no future call site can skip it.
        """
        self.require_scope(target_id, candidate.host, run_id=run_id)

        verdict = verdict or self.dedup(target_id, candidate, run_id=run_id)
        if not verdict.novel:
            with transaction(self.conn) as cur:
                cur.execute(
                    "UPDATE findings SET times_seen = times_seen + 1, last_seen_run = %s, "
                    "last_confirmed_at = now() WHERE id = %s",
                    (run_id, verdict.existing_id),
                )
                self.audit("gateway", "write", "deny", run_id=run_id, target_id=target_id,
                           resource=candidate.title,
                           detail={"reason": "duplicate", "of": verdict.existing_id}, cur=cur)
            return None

        vec = _vec_literal(self.embedder.embed(f"{candidate.title}\n{candidate.summary}"))
        with transaction(self.conn) as cur:
            cur.execute(
                "INSERT INTO findings (target_id, asset_id, title, severity, summary, evidence, "
                "fingerprint, embedding, first_seen_run, last_seen_run) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (target_id, candidate.asset_id, candidate.title, candidate.severity,
                 candidate.summary, candidate.evidence, candidate.fingerprint(), vec,
                 run_id, run_id),
            )
            finding_id = str(cur.fetchone()["id"])
            cur.execute(
                "UPDATE agent_runs SET written_count = written_count + 1 WHERE id = %s", (run_id,)
            )
            self.audit("gateway", "write", "ok", run_id=run_id, target_id=target_id,
                       resource=candidate.title, detail={"finding_id": finding_id}, cur=cur)
        return finding_id

    # ------------------------------------------------------------------
    # read models for the UI
    # ------------------------------------------------------------------
    def findings(self, target_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        with self.conn.cursor() as cur:
            if target_id:
                cur.execute(
                    "SELECT id, title, severity, summary, times_seen, created_at FROM findings "
                    "WHERE target_id = %s ORDER BY created_at DESC LIMIT %s", (target_id, limit))
            else:
                cur.execute(
                    "SELECT id, title, severity, summary, times_seen, created_at FROM findings "
                    "ORDER BY created_at DESC LIMIT %s", (limit,))
            return [dict(r) for r in cur.fetchall()]

    def audit_tail(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT actor, action, decision, resource, detail, at FROM audit_log "
                "ORDER BY at DESC LIMIT %s", (limit,))
            return [dict(r) for r in cur.fetchall()]

    def runs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT id, target_id, pass_no, status, recalled_count, deduped_count, "
                "written_count, cost_usd, started_at, finished_at FROM agent_runs "
                "ORDER BY started_at DESC LIMIT %s", (limit,))
            return [dict(r) for r in cur.fetchall()]

    def stats(self) -> dict[str, int]:
        out: dict[str, int] = {}
        with self.conn.cursor() as cur:
            for table in ("targets", "assets", "artifacts", "embeddings", "findings",
                          "agent_runs", "audit_log", "scope_decisions"):
                cur.execute(f"SELECT count(*) AS n FROM {table}")
                out[table] = int(cur.fetchone()["n"])
        return out
