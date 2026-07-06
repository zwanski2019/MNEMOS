# services/scanner — Go deterministic core

Enumerates and fetches. Pure functions, testable, **no reasoning**.

- Subdomain / asset enumeration, JS bundle fetch, endpoint + param extraction.
- Raw blobs → S3 (minio locally); metadata → `assets` / `artifacts` with content-addressed dedup.
- Builds to a local binary first, then AWS Lambda workers driven off NATS/SQS.

Status: **P3 / P6 — not yet implemented.** See root `CLAUDE.md` §7.
