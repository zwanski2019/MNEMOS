"""Memory that reasons about its own age.

Four things a findings table cannot do, and a memory layer can:

* **Decay** — a finding last confirmed six weeks ago is not worth what it was the
  day it was written. Confidence is computed from `last_confirmed_at`, not from
  `created_at`, so re-confirming something restores full trust.
* **Regression** — a finding recorded as fixed that comes back is the single most
  important row in the table, and only memory can tell you it happened.
* **Correlation** — the same vendor bundle served from two estates is one problem,
  not two. That is a join on the content address.
* **Time travel** — CockroachDB can answer "what did the agent know at 14:02, and
  what was it authorised to do?" from the real historical state, using
  `AS OF SYSTEM TIME`. Not reconstructed from a log; the actual rows as they were.

All four live in the same SQL surface as recall and dedup. There is no second store
to keep consistent, which is the entire argument for this database.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

import psycopg

log = logging.getLogger(__name__)

# Half-life for confidence decay. After this long without re-observation a finding
# is worth half what it was. Recon findings go stale fast — a subdomain that existed
# a fortnight ago frequently does not today — so this is deliberately short.
CONFIDENCE_HALF_LIFE_DAYS = 14.0

# Floor: memory never fully forgets. A very old finding still ranks above nothing,
# and dropping to zero would make it invisible to the operator rather than merely
# untrusted.
MIN_CONFIDENCE = 0.05


def confidence_for(last_confirmed_at: datetime, *, now: datetime | None = None) -> float:
    """Exponential decay from the last time the agent actually saw it."""
    now = now or datetime.now(timezone.utc)
    if last_confirmed_at.tzinfo is None:
        last_confirmed_at = last_confirmed_at.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (now - last_confirmed_at).total_seconds() / 86400.0)
    decayed = math.pow(0.5, age_days / CONFIDENCE_HALF_LIFE_DAYS)
    return max(MIN_CONFIDENCE, round(decayed, 4))


@dataclass(frozen=True)
class Reconciliation:
    """What changed about the world between two visits."""

    confirmed: int = 0    # still there
    fixed: int = 0        # was there, now gone
    regressed: int = 0    # was gone, now back

    @property
    def changed(self) -> bool:
        return bool(self.fixed or self.regressed)


@dataclass(frozen=True)
class Correlation:
    """One thing that appears on more than one target."""

    kind: str             # 'artifact' | 'finding'
    key: str              # sha256, or the finding title
    targets: list[str]
    occurrences: int
    detail: str = ""


class MemoryIntelligence:
    """Mixin of higher-order reads over the memory tables.

    Kept separate from `Memory` because these are analyses, not the hot path: none
    of them may be called from inside a recon cycle's write path.
    """

    conn: psycopg.Connection

    # ------------------------------------------------------------------
    # decay
    # ------------------------------------------------------------------
    def findings_with_confidence(
        self, target_id: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        sql = (
            "SELECT id, title, severity, summary, status, times_seen, regression_count, "
            "last_confirmed_at, created_at FROM findings "
            + ("WHERE target_id = %s " if target_id else "")
            + "ORDER BY last_confirmed_at DESC LIMIT %s"
        )
        args = (target_id, limit) if target_id else (limit,)
        with self.conn.cursor() as cur:
            cur.execute(sql, args)
            rows = [dict(r) for r in cur.fetchall()]
        for row in rows:
            row["confidence"] = confidence_for(row["last_confirmed_at"])
        return rows

    # ------------------------------------------------------------------
    # regression detection
    # ------------------------------------------------------------------
    def reconcile(
        self, target_id: str, run_id: str, observed_fingerprints: Sequence[str]
    ) -> Reconciliation:
        """Compare what this run saw against what memory believed.

        Anything open that was not re-observed becomes `fixed`. Anything previously
        `fixed` that showed up again becomes `regressed` — which is the state worth
        paging someone about, because it means a fix did not hold.

        Called once at the end of a cycle, never mid-cycle: a partial observation set
        would mark live findings as fixed.
        """
        observed = list(dict.fromkeys(observed_fingerprints))
        result = Reconciliation()

        with self.conn.cursor() as cur:
            # Re-observed and previously fixed -> regressed.
            cur.execute(
                "UPDATE findings SET status = 'regressed', "
                "regression_count = regression_count + 1, "
                "last_confirmed_at = now(), last_seen_run = %s "
                "WHERE target_id = %s AND status = 'fixed' AND fingerprint = ANY(%s) "
                "RETURNING id",
                (run_id, target_id, observed),
            )
            regressed = cur.fetchall()

            # Re-observed and already open -> just refresh the clock.
            cur.execute(
                "UPDATE findings SET last_confirmed_at = now(), last_seen_run = %s "
                "WHERE target_id = %s AND status = 'open' AND fingerprint = ANY(%s) "
                "RETURNING id",
                (run_id, target_id, observed),
            )
            confirmed = cur.fetchall()

            # Open but not seen this time -> fixed.
            cur.execute(
                "UPDATE findings SET status = 'fixed', closed_by_run = %s "
                "WHERE target_id = %s AND status IN ('open', 'regressed') "
                "AND NOT (fingerprint = ANY(%s)) RETURNING id",
                (run_id, target_id, observed),
            )
            fixed = cur.fetchall()

            result = Reconciliation(
                confirmed=len(confirmed), fixed=len(fixed), regressed=len(regressed)
            )

        self.audit(  # type: ignore[attr-defined]
            "gateway", "reconcile", "ok", run_id=run_id, target_id=target_id,
            detail={"confirmed": result.confirmed, "fixed": result.fixed,
                    "regressed": result.regressed},
        )
        return result

    def regressions(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT f.id, f.title, f.severity, f.regression_count, f.last_confirmed_at, "
                "t.root_domain FROM findings f LEFT JOIN targets t ON t.id = f.target_id "
                "WHERE f.status = 'regressed' ORDER BY f.regression_count DESC, "
                "f.last_confirmed_at DESC LIMIT %s",
                (limit,),
            )
            return [dict(r) for r in cur.fetchall()]

    # ------------------------------------------------------------------
    # cross-target correlation
    # ------------------------------------------------------------------
    def correlations(self, limit: int = 20) -> list[Correlation]:
        """Things memory can see that no single scan can.

        Two angles: the same *bytes* (content address) reaching more than one estate,
        and the same *conclusion* (finding title) reached on more than one estate.
        The first catches a shared vendor bundle; the second catches a systemic
        misconfiguration rolled out everywhere.
        """
        out: list[Correlation] = []
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT a.sha256, count(DISTINCT a.target_id) AS n_targets, "
                "count(*) AS occurrences, "
                "array_agg(DISTINCT t.root_domain) AS domains, max(a.byte_len) AS bytes "
                "FROM artifacts a JOIN targets t ON t.id = a.target_id "
                "GROUP BY a.sha256 HAVING count(DISTINCT a.target_id) > 1 "
                "ORDER BY n_targets DESC, occurrences DESC LIMIT %s",
                (limit,),
            )
            for row in cur.fetchall():
                out.append(Correlation(
                    kind="artifact", key=row["sha256"],
                    targets=[d for d in row["domains"] if d],
                    occurrences=int(row["occurrences"]),
                    detail=f"identical {row['bytes']}-byte artifact on "
                           f"{row['n_targets']} estates",
                ))

            cur.execute(
                "SELECT f.title, f.severity, count(DISTINCT f.target_id) AS n_targets, "
                "count(*) AS occurrences, array_agg(DISTINCT t.root_domain) AS domains "
                "FROM findings f JOIN targets t ON t.id = f.target_id "
                "GROUP BY f.title, f.severity HAVING count(DISTINCT f.target_id) > 1 "
                "ORDER BY n_targets DESC, occurrences DESC LIMIT %s",
                (limit,),
            )
            for row in cur.fetchall():
                out.append(Correlation(
                    kind="finding", key=row["title"],
                    targets=[d for d in row["domains"] if d],
                    occurrences=int(row["occurrences"]),
                    detail=f"{row['severity']} finding reached independently on "
                           f"{row['n_targets']} estates",
                ))
        return out

    # ------------------------------------------------------------------
    # time travel
    # ------------------------------------------------------------------
    def snapshot_at(self, when: datetime | str) -> dict[str, Any] | None:
        """What memory held at a past instant, via CockroachDB AS OF SYSTEM TIME.

        This is not replayed from the audit log — it is the actual committed state of
        the rows at that timestamp, which is why it can answer the question that
        matters after an incident: *what was the agent authorised to do at 14:02, and
        what did it already know?*

        Returns None if the timestamp is outside the cluster's garbage-collection
        window, which is a real and expected answer rather than an error.
        """
        tables = ("targets", "assets", "artifacts", "embeddings", "findings",
                  "agent_runs", "audit_log", "scope_decisions")
        rows = self._as_of(
            when,
            [(t, f"SELECT count(*) AS n FROM {t}") for t in tables],
        )
        if rows is None:
            return None
        return {name: int(r[0]["n"]) for name, r in rows.items()}

    def _as_of(
        self, when: datetime | str, queries: list[tuple[str, str]]
    ) -> dict[str, list[dict[str, Any]]] | None:
        """Run several reads against one historical snapshot.

        ``AS OF SYSTEM TIME`` has to be a top-level clause, so it cannot be pushed
        into subqueries. Opening the *transaction* at a past timestamp gives every
        statement inside it the same consistent snapshot — which is what we want
        anyway: the counts must all be from the same instant, not from six instants
        a few milliseconds apart.
        """
        ts = when.isoformat() if isinstance(when, datetime) else when
        previous = self.conn.autocommit
        out: dict[str, list[dict[str, Any]]] = {}
        try:
            # autocommit must stay ON: psycopg opens its own transaction otherwise,
            # and BEGIN AS OF SYSTEM TIME has to be the statement that starts it.
            self.conn.autocommit = True
            with self.conn.cursor() as cur:
                cur.execute(f"BEGIN AS OF SYSTEM TIME '{ts}'")
                try:
                    for name, sql in queries:
                        cur.execute(sql)
                        out[name] = [dict(r) for r in cur.fetchall()]
                    cur.execute("COMMIT")
                except psycopg.errors.Error:
                    cur.execute("ROLLBACK")
                    raise
            return out
        except psycopg.errors.Error as exc:
            # Outside the GC window is a real answer, not a failure.
            log.warning("time-travel read rejected for %s: %s", ts, str(exc).strip())
            return None
        finally:
            self.conn.autocommit = previous

    def findings_at(self, when: datetime | str, limit: int = 50) -> list[dict[str, Any]] | None:
        """The findings table exactly as it stood at `when`."""
        rows = self._as_of(when, [(
            "findings",
            "SELECT id, title, severity, status, times_seen, created_at FROM findings "
            f"ORDER BY created_at DESC LIMIT {int(limit)}",
        )])
        return rows["findings"] if rows else None

    def scope_at(self, when: datetime | str) -> list[dict[str, Any]] | None:
        """What the agent was authorised to do at `when`. The post-incident question."""
        rows = self._as_of(when, [(
            "scope",
            "SELECT pattern, effect, reason, decided_by, decided_at FROM scope_decisions "
            "ORDER BY decided_at",
        )])
        return rows["scope"] if rows else None

    def diff_since(self, when: datetime | str) -> dict[str, int] | None:
        """How much memory has grown since `when`. The 'what changed' view."""
        past = self.snapshot_at(when)
        if past is None:
            return None
        now = self.stats()  # type: ignore[attr-defined]
        return {k: int(now.get(k, 0)) - past.get(k, 0) for k in past}


def gc_window_floor(hours: int = 4) -> datetime:
    """Conservative earliest timestamp a time-travel query is likely to accept."""
    return datetime.now(timezone.utc) - timedelta(hours=hours)
