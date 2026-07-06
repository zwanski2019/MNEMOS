# apps/gateway — FastAPI control plane

The single choke point. Every agent action passes through here:

- **Scope guard** — fail-closed `scope_check(action)` against `scope_decisions`. Deny-by-default.
- **Dedup gate** — vector-similarity check vs existing `findings` before any insert.
- **Audit** — every DB touch logged to `audit_log` (actor, statement class, latency, rows).
- **Job emission** — scan jobs to NATS; results streamed to the web UI.

Status: **P2 — not yet implemented.** See root `CLAUDE.md` §7.
