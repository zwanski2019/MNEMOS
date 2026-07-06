# infra — provisioning

- **ccloud/** — `ccloud` CLI scripts to provision the CockroachDB Cloud cluster, apply migrations,
  and configure the vector index. `make provision` wraps these. (P6)
- **lambda/** — SAM/CDK for the Go scanner workers + S3 bucket + IAM. (P6)
- **bedrock/** — Bedrock model access config + prompt templates for the analyst and embeddings. (P4/P5)

Status: **P6 — not yet implemented.** See root `CLAUDE.md` §5–§6.
