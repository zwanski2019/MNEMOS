# MNEMOS Architecture

Two-layer pattern: a deterministic core plus a thin LLM analyst. The LLM never touches the network
and never decides scope; it reasons over memory.

```
                         ┌────────────────────────────────────────────┐
                         │              CockroachDB Cloud (AWS)         │
                         │  targets · assets · artifacts · embeddings   │
                         │  findings · agent_runs · audit_log ·         │
                         │  scope_decisions      [VECTOR INDEX]         │
                         └───────▲───────────────▲──────────────▲───────┘
                                 │ SQL           │ MCP (RO)      │ ccloud
                                 │               │               │ (provision/ops)
   ┌──────────────┐      ┌───────┴───────┐  ┌────┴─────────┐     │
   │ Go Scanner   │─────▶│ FastAPI       │◀─│ Analyst      │◀────┘
   │ Core         │ NATS │ Gateway       │  │ (Bedrock)    │
   │ (Lambda)     │◀────▶│ + Scope Guard │  │ recall/dedup │
   └──────┬───────┘      └───────┬───────┘  └──────────────┘
          │ raw blobs            │ events
          ▼                      ▼
     ┌─────────┐          ┌──────────────┐
     │   S3    │          │ Mission Ctrl │  (Next.js — apps/web)
     │artifacts│          │   UI (Next)  │
     └─────────┘          └──────────────┘
```

## One recon cycle

1. Operator adds a target + scope rules via the UI/API → written transactionally to `targets` +
   `scope_decisions`.
2. Gateway emits scan jobs to NATS. Deterministic Go scanners run as Lambda workers (subdomain /
   asset enum, JS bundle fetch, endpoint extraction). Raw blobs → S3, metadata → CRDB.
3. Bundle / endpoint text is chunked, embedded via **Bedrock Titan Embeddings V2 (1024-dim)**, and
   stored in `embeddings` with the **CockroachDB distributed vector index**.
4. The analyst is invoked per candidate finding. **Recall first**: vector-search `embeddings` +
   `findings` for prior/similar context across all sessions, via the **MCP server (read-only)**.
5. The analyst proposes a finding. The gateway runs **dedup** (vector similarity vs existing
   `findings`) and a **scope check** (`scope_decisions`, fail-closed). Only novel, in-scope
   findings persist.
6. Every step writes `agent_runs` (tokens, cost, latency) + `audit_log`. The UI streams it live.

## Invariants

- **Recall before reason, dedup before write.** Non-negotiable ordering.
- **Deny by default.** No allow rule → no action. Every decision is audited.
- **Cost ceiling** per run, enforced from the `agent_runs` running total.
