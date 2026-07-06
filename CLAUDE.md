# MNEMOS — Build Contract & Agent Directive

This file is the source of truth for how MNEMOS is built and how automated agents (Claude Code and
others) should work in this repo. `README.md` and `Makefile` reference it; keep §9 in sync with
reality as phases land.

> **MNEMOS** — an autonomous reconnaissance agent whose memory *is* the product. Submission for the
> **CockroachDB × AWS "Build with Agentic Memory" Hackathon**. **Deadline: Aug 18 2026, 5:00 PM ET.**

---

## 1. The one idea

CockroachDB is the always-on, globally-consistent memory layer that lets the agent dedup findings
across sessions and regions, recall prior context via distributed vector search, and enforce scope
as immutable transactional data with a full SQL audit trail. **Without that memory the agent does
not degrade — it stops.** Every design decision should make that sentence more true.

## 2. Architecture (see `ARCHITECTURE.md` for the diagram)

Two layers: a **deterministic core** plus a **thin LLM analyst**. The LLM never touches the network
and never decides scope; it reasons over memory.

- **Go Scanner Core** (`services/scanner`, → AWS Lambda) — deterministic subdomain/asset enum, JS
  bundle fetch, endpoint extraction. Raw blobs → S3, metadata → CockroachDB. Event-driven off NATS.
- **FastAPI Gateway** (`apps/gateway`) — the single audited choke point: scope guard (fail-closed),
  dedup, audit writes, job emission.
- **Analyst** (`apps/analyst`, Amazon Bedrock) — invoked per candidate finding; recalls memory
  read-only through the **Cloud Managed MCP server** before proposing anything.
- **Mission Control UI** (`apps/web`, Next.js 15) — operator console; streams runs/audit live.
- **Memory** (`packages/memory`) — CRDB schema, migrations, vector ops.

## 3. Invariants (non-negotiable, enforce in code + review)

1. **Recall before reason, dedup before write.** Fixed ordering; the analyst reads memory before it
   proposes, and the gateway dedups against existing findings before any write.
2. **Deny by default.** No explicit allow rule → no action. Scope decisions are immutable and
   written transactionally to `scope_decisions`.
3. **Everything is audited.** Every DB touch writes an `audit_log` row; every analyst invocation
   writes an `agent_runs` row (tokens, cost, latency).
4. **Cost ceiling per run**, enforced from the `agent_runs` running total — the agent stops when it
   would exceed budget.

## 4. Data model (`packages/memory`)

Core tables: `targets`, `assets`, `artifacts`, `embeddings`, `findings`, `agent_runs`, `audit_log`,
`scope_decisions`. Distributed **vector indexes** on the embedding columns (`embeddings_vec`,
`findings_vec`) drive cross-session recall and dedup. Embeddings are **1024-dim** (Bedrock Titan
Text Embeddings V2). Exact column definitions live in the migrations — treat those as authoritative.

## 5. One recon cycle

1. Operator adds a target + scope rules (UI/API) → `targets` + `scope_decisions`, transactionally.
2. Gateway emits scan jobs to NATS; Go scanners (Lambda) run; raw → S3, metadata → CRDB.
3. Bundle/endpoint text is chunked, embedded (Titan V2, 1024-dim), stored in `embeddings` with the
   vector index.
4. Analyst is invoked per candidate finding — **recall first** (vector search over `embeddings` +
   `findings` across all sessions, via MCP read-only).
5. Analyst proposes a finding → gateway runs **dedup** (vector similarity vs `findings`) and a
   **scope check** (fail-closed). Only novel, in-scope findings persist.
6. Every step writes `agent_runs` + `audit_log`; the UI streams it live.

## 6. Tech stack & external services

- **CockroachDB Cloud** — distributed vector indexing; Cloud Managed MCP server (read-only recall);
  `ccloud` CLI for provisioning, migrations, and vector-index config.
- **AWS** — Amazon Bedrock (Claude analyst + Titan Text Embeddings V2, 1024-dim); AWS Lambda (Go
  scanner workers); Amazon S3 (content-addressed raw artifacts).
- **Local dev** — `docker-compose.yml` runs CRDB + NATS + MinIO.

## 7. Repo layout

```
apps/
  web/        Mission Control UI — Next.js 15 + Tailwind v3    (P7 ✓)
  gateway/    FastAPI: scope guard, dedup, audit               (P2)
  analyst/    Bedrock analyst + MCP recall                     (P5)
services/
  scanner/    Go deterministic core → Lambda                   (P3/P6)
packages/
  memory/     CRDB schema, migrations, vector ops              (P1)
  mcp/        Cloud Managed MCP config + client                (P5)
  schemas/    shared pydantic/zod types
infra/        ccloud · lambda · bedrock provisioning           (P6)
```

## 8. Conventions

- **Monorepo:** pnpm workspaces, `pnpm@11.10.0`, Node 20+. Web app is `@mnemos/web`.
- **Entry points:** `make help`. `make demo` must provision, seed, and run an end-to-end scenario
  using **environment variables only** — no manual steps.
- **UI:** dark Material-Design-3 token system in `apps/web/tailwind.config.ts` (cyan primary, amber
  secondary); JetBrains Mono (data) + Inter (text). Icons are **lucide-react SVGs via the central
  `components/Icon.tsx`** — never icon fonts or emoji. Keep it PWA-offline-safe (no CDN fonts).
- **Secrets:** never commit. `.env.example` is the template; real values stay in `.env` (ignored).
- **Commits:** phases land in order, one logical change per commit, imperative subject.
- **Git:** this repo pushes to `git@github.com:zwanski2019/MNEMOS.git`. Account email privacy is on,
  so commits must use the GitHub noreply email (already set as the repo's `user.email`).

## 9. Build phases & status

| Phase | Scope | Status |
|-------|-------|--------|
| P0 | Monorepo scaffold + root docs (README, ARCHITECTURE, Makefile, docker-compose, LICENSE) | ✅ done |
| P1 | Memory core — CRDB schema, migrations, vector ops (`packages/memory`) | ⬜ scaffolded |
| P2 | Gateway — scope guard (fail-closed), dedup, audit (`apps/gateway`) | ⬜ scaffolded |
| P3 | Go scanner core — enum, fetch, endpoint extraction (`services/scanner`) | ⬜ scaffolded |
| P4 | Embeddings pipeline — chunk + Titan V2 (1024-dim) → vector index | ⬜ scaffolded |
| P5 | Analyst + MCP recall (`apps/analyst`, `packages/mcp`) | ⬜ scaffolded |
| P6 | Deploy — `ccloud` provisioning, Lambda, Bedrock (`infra`) | ⬜ scaffolded |
| P7 | Mission Control UI — 7 routes + settings, fixture data (`apps/web`) | ✅ done |
| P8 | Seed authorized sandbox + `make demo` end-to-end cycle | ⬜ todo |
| P9 | Public repo + live demo URL | 🔶 repo public; demo URL todo |
| P10 | < 3-minute demo video | ⬜ todo |

Transient UI states not yet built (low priority, add on request): reindex-progress splash,
cluster-investigation, correlation-rule-config, deep-scan, purge/deploy success splashes.

## 10. How agents should work here

- **Read this file + `ARCHITECTURE.md` first.** Respect §3 invariants — they are the judged thesis.
- **Ground before you build.** The UI runs on fixture data today; wire to the gateway only once P2
  exists. Don't invent table columns — read the migrations.
- **Verify before claiming done.** `pnpm build` (web) must pass; `make demo` is the acceptance test
  for the backend once P1–P6 land.
- **Keep the memory story front-and-center** in every demo artifact: the second run is smart
  *because* of the first.

## 11. Submission non-negotiables

- MIT `LICENSE` at repo root (present).
- Public repository (done — GitHub).
- `make demo` reproducible from env vars only.
- Judging axes: Agentic Memory Design · Technical Implementation · Real-World Impact · Production
  Readiness · Creativity. Every table must earn its place.
