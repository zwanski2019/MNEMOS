# CockroachDB verification findings

Part E said "do not trust remembered DDL — verify against live docs". These were
verified empirically against the live CockroachDB Cloud cluster (v26.2.1,
AWS eu-central-1), not from documentation or memory.

## E1 — advisory locks: the brief is *more* right than it states

> "`pg_advisory_lock` does not exist in CockroachDB."

Correct for the blocking variant:

```
SELECT pg_advisory_lock(1)   -> ERROR: unknown function: pg_advisory_lock()
```

But **`pg_try_advisory_lock` does exist — and is a no-op stub**:

```
conn A: SELECT pg_try_advisory_lock(42)  -> true
conn B: SELECT pg_try_advisory_lock(42)  -> true     <-- both hold "the lock"
```

Two independent connections acquired the same lock simultaneously. This is more
dangerous than the function being absent: code calling it compiles, runs, returns
`true`, and provides **no mutual exclusion whatsoever**. The failure only appears
under the concurrency a race test creates.

Any concurrency control here uses `UNIQUE` constraints,
`INSERT … ON CONFLICT DO NOTHING`, or `SELECT … FOR UPDATE` in an explicit
transaction. No advisory locks anywhere in the codebase.

## E2 — isolation and retries: confirmed

```
SHOW transaction_isolation  ->  serializable
```

`40001` retries are handled by `run_in_transaction()` in `packages/memory/db.py`
with jittered backoff. Note that `transaction()` itself is deliberately
single-attempt: a context manager cannot re-run its caller's block, so a retry
loop wrapped around `yield` would silently commit a partial attempt. That bug was
present earlier in this codebase and was fixed.

## E3 — primary keys: confirmed, and `gen_random_ulid` exists

`gen_random_uuid()` (v4) is used for every primary key. Sequential keys hotspot a
single range.

Worth noting: CockroachDB *does* provide `gen_random_ulid()`, which is
time-ordered and therefore has exactly the hotspotting property the brief warns
about. It is not used here.

## E4 — VECTOR: verified empirically, with a gotcha

`CREATE VECTOR INDEX` works but **fails on a stock cluster** until:

```sql
SET CLUSTER SETTING feature.vector_index.enabled = true;
```

This is in migration `001_init.sql`. It also requires **v25.2+** — the compose
file originally pinned v24.3, where the syntax does not exist at all.

Confirmed working: `VECTOR(1024)` columns, `CREATE VECTOR INDEX … (embedding
vector_cosine_ops)`, and `<=>` cosine distance ordering.

## E5 — trust domains

Recon findings are attacker-controlled text. They are never interpolated into
SQL (all queries are parameterised) and never reach a template. They *do* reach
the analyst prompt, which is the open exposure — see Part F row 14, not yet
tested.

## E6 — least privilege: confirmed working

Four roles: `mnemos_agent` (app), `mnemos_analyst_ro` (read-only),
`mnemos_web_ro` (public console, SELECT-only), plus per-test probe users.

CockroachDB has **no column-level `GRANT`**:

```
GRANT SELECT (id, email) ON accounts TO mnemos_web_ro
  -> ERROR: at or near "(": syntax error
```

The credential boundary is therefore a view (`accounts_public`) that omits
`password_hash`, with the underlying table never granted. Verified from outside:
the web role reads entitlement state and is refused both
`accounts.password_hash` and `sessions.token_sha256`.
