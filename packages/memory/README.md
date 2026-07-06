# packages/memory — CockroachDB memory layer

The product. Schema, migrations, client, and vector ops for the agent's memory.

- Migrations for every table in `CLAUDE.md` §4 + both vector indexes
  (`embeddings_vec`, `findings_vec`).
- Audit-wrapped `execute()` so every DB touch lands in `audit_log`.
- Recall + dedup helpers (nearest-neighbor over the distributed vector index).

Status: **P1 — not yet implemented.** See root `CLAUDE.md` §4.
