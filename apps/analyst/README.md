# apps/analyst — Bedrock analyst (thin reasoning layer)

Never touches the network, never decides scope. It only reasons over memory.

- **Recall before reason** — vector-search `embeddings` + `findings` for prior/similar context
  across all sessions, read through the CockroachDB **MCP server in read-only mode**.
- **Propose findings** — Bedrock Claude produces candidate findings; writes go back through the
  audited gateway path, never directly.
- **Cost/latency** — every invocation records `agent_runs` (tokens, cost, latency).

Status: **P5 — not yet implemented.** See root `CLAUDE.md` §7.
