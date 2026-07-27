# MNEMOS

**An autonomous reconnaissance agent whose memory is the product.**
Submission for the **CockroachDB × AWS Hackathon — Build with Agentic Memory**.

Point any autonomous scanner at a target twice and it re-reports the same subdomain,
the same leaked key, the same stale endpoint — because every run starts from zero.
Security teams are not drowning in missed findings. They are drowning in duplicates.

MNEMOS inverts that. CockroachDB is not a sink at the end of the pipeline; it is what
decides whether the agent is allowed to act at all. **Take the memory away and MNEMOS
does not degrade gracefully — it stops.**

**Live demo:** https://mnemos-mission-control.vercel.app

---

## See it in 60 seconds

```bash
make install     # web + python workspaces
make db-up       # CockroachDB v25.3 + NATS + MinIO
make demo        # two passes over the same authorised sandbox
```

`make demo` runs the identical recon cycle twice. The second pass sees one genuinely
new asset and an otherwise unchanged estate:

```
━━ 1 · first visit — nothing remembered yet ━━
    observations : 6
    written      : 6
    deduped      : 0

━━ 2 · second visit — same estate, one new bundle ━━
    observations : 10
    recalled     : 80   (prior context pulled from memory)
    written      : 4
    deduped      : 6    (blocked before write)

6 duplicate findings never reached the findings table.
They were stopped by a vector-similarity check against what pass 1 had
already written — recall from CockroachDB, not state held in this process.
```

Every number there is read back **out of CockroachDB** after the run. Nothing is
accumulated in process memory, because the database *is* the agent's memory.

### Against CockroachDB Cloud

The same command runs unchanged against a real cluster — only `DATABASE_URL` differs:

```bash
export DATABASE_URL='postgresql://user:pw@your-cluster.aws-eu-central-1.cockroachlabs.cloud:26257/mnemos?sslmode=verify-full'
make demo-cloud
```

Verified on **CockroachDB Cloud Basic, v26.2.1, AWS eu-central-1**: both migrations
apply, `embeddings_vec` and `findings_vec` are created as distributed vector indexes,
the append-only grants hold, and the full two-pass cycle completes in ~55s.

No AWS account? The demo still runs — it falls back to a clearly-labelled offline
embedder and analyst and says so, rather than failing halfway through a run.

---

## The cycle

```
scan → index → RECALL → reason → DEDUP → scope → write → audit
```

The ordering is the product, and it lives in exactly one function
([`cycle.run_cycle`](packages/recon/mnemos_recon/cycle.py)) so there is one thing to review.

1. **Target + scope** are written to `targets` and `scope_decisions` in a single
   transaction. Scope is immutable data, never a config flag.
2. **Deterministic scanners** enumerate assets and parse JS bundles. No model in the
   hot path — given the same bytes, the same observations, every time. That is what
   makes dedup meaningful: when pass 2 reports something new, the target changed.
3. **Embed** every chunk with Bedrock Titan Text Embeddings V2 (1024-dim) into
   `embeddings`, behind CockroachDB's distributed vector index.
4. **RECALL** — before the analyst is allowed to form an opinion, it vector-searches
   `embeddings` *and* `findings` across every prior session for this target.
5. **DEDUP then SCOPE then WRITE** — a cheap fingerprint gate, then a vector-similarity
   gate, then a fail-closed scope check. All three live inside `commit_finding`, which
   is the only write path to `findings`, so no future call site can skip them.
6. **Audit** — `agent_runs` (tokens, cost, latency) and `audit_log` on every decision.

See [`ARCHITECTURE.md`](./ARCHITECTURE.md) for the diagram.

---

## The four invariants, and how they are enforced

These are the judged thesis, so none of them are enforced by good intentions.

| Invariant | Enforced by | Proven by |
|---|---|---|
| Recall before reason, dedup before write | `commit_finding` re-runs both gates itself | `test_identical_finding_is_written_once`, `test_semantically_similar_finding_is_deduped` |
| Deny by default | `check_scope` returns `False` on *any* error, including an unreachable database | `test_unknown_host_is_denied`, `test_scope_guard_fails_closed_when_memory_is_unreachable` |
| Everything is audited | **CockroachDB privileges** — the app role has `SELECT, INSERT` on `audit_log` and `scope_decisions`. No `UPDATE`. No `DELETE`. | `test_append_only_ledgers_reject_update_and_delete` |
| Cost ceiling per run | Evaluated from the committed running total in `agent_runs`, not an in-process counter | `test_ceiling_is_read_from_the_database_not_the_process` |

That third row is the one worth pausing on. From
[`002_roles.sql`](packages/memory/migrations/002_roles.sql):

```sql
GRANT SELECT, INSERT ON TABLE scope_decisions TO mnemos_agent;
GRANT SELECT, INSERT ON TABLE audit_log       TO mnemos_agent;
```

An attacker — or a bug — holding the application's credentials still cannot rewrite
the record of what the agent was allowed to do, or erase the evidence of what it did:

```
$ make verify-invariants
ERROR: user … does not have UPDATE privilege on relation scope_decisions
ERROR: user … does not have DELETE privilege on relation audit_log
```

The analyst is a separate principal (`mnemos_analyst_ro`) that is `SELECT`-only
everywhere — the same posture the CockroachDB Cloud Managed MCP Server gives us in
production. The model can recall memory but is structurally incapable of writing to
the memory it is reasoning over.

---

## CockroachDB tools used

- **Distributed Vector Indexing** — `embeddings_vec` and `findings_vec`
  (`vector_cosine_ops`, 1024-dim) carry two load-bearing paths: cross-session
  **recall** and pre-write **dedup**. Not a demo query — remove the index and the
  agent has nothing to compare against.
- **Cloud Managed MCP Server** — how the analyst reads memory during execution,
  read-only. Mirrored locally by the `mnemos_analyst_ro` role so the security posture
  is identical in dev and in cloud.
- **`ccloud` CLI** — provisions the cluster, applies migrations, configures the vector
  indexes, so `make demo-cloud` needs no manual console steps.
- **Agent Skills Repo** — vendored under [`.agents/skills`](.agents/skills) and used
  during development for schema review and cluster operations.

## AWS services used

- **Amazon Bedrock** — Claude as the analyst (`converse`), Titan Text Embeddings V2
  for every vector CockroachDB indexes.
- **Amazon S3** — content-addressed raw artifacts. Bytes go to S3, the **content
  address** goes to CockroachDB, so memory stays queryable and joinable in SQL next to
  the vectors and the audit trail while the blobs stay cheap. Keys are
  `artifacts/<sha[:2]>/<sha256>`, which makes the store idempotent: the same bundle
  served from ten hosts is uploaded once, and a re-scan that finds nothing changed
  uploads nothing at all. Buckets are created with public access blocked, SSE-AES256,
  and versioning on. **Verified end to end** against a live bucket.
- **AWS Lambda** — the deterministic Go scanner core, event-driven off NATS.

> **Bedrock status.** The code path is written and probed on every run
> (`BedrockTitanEmbedder`, `BedrockAnalyst`). On the submission account every Bedrock
> on-demand quota is currently `0`, so the probe fails and the run degrades to the
> labelled offline stand-ins rather than dying mid-cycle. S3 is real AWS regardless.
> Raise the quota and `MNEMOS_EMBEDDER=bedrock MNEMOS_ANALYST=bedrock` needs no code change.

---

## Repo layout

```
apps/
  web/        Mission Control — Next.js 15, 7 routes          deployed
  gateway/    FastAPI: scope guard, dedup, audit              built
packages/
  memory/     CRDB schema, migrations, vector ops, recall     built
  recon/      deterministic scanner, analyst, the cycle       built
services/
  scanner/    Go core → Lambda                                scaffolded
scripts/
  demo.py     the two-pass end-to-end                         built
tests/        22 tests, invariant-first                       built
```

## Running the pieces

```bash
make db-up            # CockroachDB v25.3 (v25.2+ required for vector indexing)
make migrate          # idempotent schema + roles
make demo             # the two-pass cycle
make test             # 22 tests
make verify-invariants
make gateway          # FastAPI on :8080, OpenAPI at /docs
make dev              # Mission Control on :3000
```

The gateway's interesting responses are its refusals: `403` for out of scope, `409`
for "memory already knew". The second one is a success for the system.

## Configuration

Copy `.env.example` to `.env`. Nothing in the codebase reads a secret from anywhere
else, and `make demo` runs from environment variables alone.

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | CockroachDB DSN. Defaults to the local cluster. |
| `MNEMOS_EMBEDDER` | `bedrock` \| `offline` \| `auto` (default) |
| `MNEMOS_ANALYST` | `bedrock` \| `offline` \| `auto` (default) |
| `AWS_REGION`, `BEDROCK_*` | Bedrock model selection |
| `MNEMOS_COST_CEILING_USD` | Per-run halt threshold |

`auto` probes AWS with a single STS call before choosing — credentials that exist but
are *rejected* degrade to the offline path instead of failing on the first observation.

## Scope and ethics

MNEMOS is built for authorised testing only. The demo ships an **offline fixture
corpus** ([`sandbox.py`](packages/recon/mnemos_recon/sandbox.py)) standing in for an
estate we own: the scanner parses it through exactly the code path it would use
against a live host, but no packet leaves the machine. Pointing it at a real target
requires writing an authorisation string and explicit allow rules into
`scope_decisions` first — and with no allow rule, the agent can do nothing at all.

## Licence

MIT — see [LICENSE](./LICENSE).
