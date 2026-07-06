# MNEMOS

**An autonomous reconnaissance agent whose memory is the product.**
Submission for the **CockroachDB × AWS Hackathon — Build with Agentic Memory**.

CockroachDB is the always-on, globally-consistent memory layer that lets the agent **dedup
findings across sessions and regions, recall prior context via distributed vector search, and
enforce scope as immutable transactional data with a full SQL audit trail.** Without that memory
the agent doesn't degrade — it stops.

**Live demo:** _not yet deployed_ — one-click deploy in [Deploy Mission Control](#deploy-mission-control) below.
<!-- After the first deploy, replace the line above with: **Live demo:** https://<project>.vercel.app -->

---

## Judging axes, one sentence each

- **Agentic Memory Design** — every table earns its place; the distributed vector index drives
  cross-session recall and dedup, not a demo query.
- **Technical Implementation** — deterministic Go scanner core + thin Bedrock analyst, with the
  gateway as the single audited choke point.
- **Real-World Impact** — a recon agent that remembers is the difference between signal and noise
  for security teams drowning in duplicate findings.
- **Production Readiness** — fail-closed scope guard, immutable scope decisions, and an audit row
  on every DB touch.
- **Creativity & Originality** — memory framed as the product, demonstrated live: the second run
  is smart *because* of the first.

## CockroachDB tools used

- **Distributed Vector Indexing** — `embeddings_vec` + `findings_vec` power recall and dedup.
- **Cloud Managed MCP Server** — the analyst reads memory read-only through MCP during execution.
- **`ccloud` CLI** — provisions the cluster, applies migrations, configures the vector index.

## AWS services used

- **Amazon Bedrock** — analyst (Claude) + Titan Text Embeddings V2 (1024-dim).
- **AWS Lambda** — Go scanner workers, event-driven off NATS/SQS.
- **Amazon S3** — content-addressed raw artifact storage.

---

## Repo layout

```
apps/
  web/        Mission Control UI — Next.js 15 (this is what runs today)
  gateway/    FastAPI: scope guard, dedup, audit           (P2)
  analyst/    Bedrock analyst + MCP recall                 (P5)
services/
  scanner/    Go deterministic core → Lambda               (P3/P6)
packages/
  memory/     CRDB schema, migrations, vector ops          (P1)
  mcp/        Cloud Managed MCP config + client            (P5)
  schemas/    shared pydantic/zod types
infra/        ccloud · lambda · bedrock provisioning       (P6)
```

See [`ARCHITECTURE.md`](./ARCHITECTURE.md) for the data-flow diagram and `CLAUDE.md` for the full
build contract.

---

## Run the Mission Control UI locally

Requires Node 20+ and pnpm.

```bash
pnpm install
pnpm dev          # → http://localhost:3000
```

Routes: `/` Overview · `/targets` · `/runs` Live Runs · `/findings` · `/memory` · `/scope` ·
`/audit`. The UI is currently wired to representative fixture data; it points at the live gateway
once P2 lands.

## Deploy Mission Control

The web app deploys to **Vercel** as-is — every route prerenders to static and runs on fixture
data, so no backend is required for the demo. Build settings live in
[`apps/web/vercel.json`](apps/web/vercel.json).

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2Fzwanski2019%2FMNEMOS&project-name=mnemos&root-directory=apps%2Fweb)

Or import manually: **Add New → Project → import `zwanski2019/MNEMOS`**, then set **Root Directory =
`apps/web`** (the pnpm workspace and Next.js are auto-detected). After the first deploy, put the
`*.vercel.app` URL in the **Live demo** link at the top of this file and in the repo's
**About → Website** field.

## Status

Mission Control UI (P7) is up. Memory core, scope guard, scanner, analyst, and cloud deploy
(P1–P6, P9) are scaffolded and tracked in `CLAUDE.md` §9. Build phases are committed in order.
