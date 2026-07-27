# `packages/mcp` — CockroachDB Cloud Managed MCP Server

How the analyst reads memory during execution: over MCP, read-only.

Giving the analyst MCP read access instead of a database connection means it
**structurally cannot write** to the memory it is reasoning over, so recall can never
contaminate the findings store or the audit trail. Config lives in
[`cockroachdb-cloud.json`](./cockroachdb-cloud.json).

```bash
claude mcp add cockroachdb-cloud https://cockroachlabs.cloud/mcp \
  --transport http --header "mcp-cluster-id: $CRDB_CLUSTER_ID"
```

Auth is OAuth against the CockroachDB Cloud session — there is no secret in the config
file, and the cluster id is an identifier rather than a credential.

## The same posture, locally

MCP is a cloud service, so the test suite and `make demo` cannot depend on it. Instead
[`002_roles.sql`](../memory/migrations/002_roles.sql) creates `mnemos_analyst_ro`, a
principal with `SELECT` on every table and nothing else. Dev and cloud therefore have
identical security properties, and `make verify-invariants` proves the read-only
boundary without needing a network round trip.

| | Production | Local |
|---|---|---|
| Analyst reads memory via | Cloud Managed MCP Server | `mnemos_analyst_ro` role |
| Analyst can write | No | No |
| Enforced by | CockroachDB Cloud | CockroachDB privileges |
