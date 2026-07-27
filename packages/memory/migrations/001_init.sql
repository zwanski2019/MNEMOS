-- MNEMOS memory core — initial schema.
--
-- Design rule: every table earns its place. Nothing here exists to look good in a
-- diagram; each one is read on a hot path during a recon cycle.
--
--   targets          what we are allowed to look at
--   scope_decisions  append-only authorisation ledger; the scope guard reads this
--   assets           what the deterministic scanners found
--   artifacts        content-addressed blobs (body lives in S3, address lives here)
--   embeddings       chunk vectors  -> cross-session RECALL
--   findings         finding vectors -> DEDUP before write
--   agent_runs       tokens / cost / latency -> the per-run cost ceiling
--   audit_log        one row per decision; nothing touches memory unaudited

SET CLUSTER SETTING feature.vector_index.enabled = true;

CREATE DATABASE IF NOT EXISTS mnemos;
USE mnemos;

-- ---------------------------------------------------------------------------
-- targets
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS targets (
    id            UUID        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    name          STRING      NOT NULL,
    root_domain   STRING      NOT NULL,
    authorisation STRING      NOT NULL,          -- program URL / written authorisation
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (root_domain)
);

-- ---------------------------------------------------------------------------
-- scope_decisions — APPEND ONLY.
--
-- Scope is data, not a config flag. A scope change is a new row, never a mutation,
-- so "what were we allowed to do at 14:02?" is answerable months later.
-- Immutability is enforced at the database level in 002_roles.sql: the application
-- role is granted SELECT+INSERT only, so an UPDATE or DELETE is rejected by
-- CockroachDB itself rather than by application code we could forget to write.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scope_decisions (
    id         UUID        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    target_id  UUID        NOT NULL REFERENCES targets (id),
    pattern    STRING      NOT NULL,             -- host glob, e.g. '*.example.com'
    effect     STRING      NOT NULL,             -- 'allow' | 'deny'
    reason     STRING      NOT NULL,
    decided_by STRING      NOT NULL,
    decided_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT effect_enum CHECK (effect IN ('allow', 'deny')),
    INDEX scope_by_target (target_id, decided_at DESC)
);

-- ---------------------------------------------------------------------------
-- assets
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS assets (
    id             UUID        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    target_id      UUID        NOT NULL REFERENCES targets (id),
    kind           STRING      NOT NULL,         -- subdomain | url | js_bundle | endpoint
    value          STRING      NOT NULL,
    first_seen_run UUID,
    discovered_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT asset_kind_enum CHECK (kind IN ('subdomain', 'url', 'js_bundle', 'endpoint')),
    UNIQUE (target_id, kind, value),
    INDEX assets_by_target (target_id, kind)
);

-- ---------------------------------------------------------------------------
-- artifacts — content-addressed. The bytes live in S3; the address lives here so
-- memory stays queryable and joinable next to the vectors and the audit trail.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS artifacts (
    id           UUID        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    target_id    UUID        NOT NULL REFERENCES targets (id),
    asset_id     UUID        REFERENCES assets (id),
    sha256       STRING      NOT NULL,
    s3_bucket    STRING,
    s3_key       STRING,
    byte_len     INT         NOT NULL DEFAULT 0,
    content_type STRING,
    fetched_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (sha256)
);

-- ---------------------------------------------------------------------------
-- agent_runs — the ledger the cost ceiling is enforced from.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_runs (
    id               UUID          NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    target_id        UUID          NOT NULL REFERENCES targets (id),
    pass_no          INT           NOT NULL DEFAULT 1,
    status           STRING        NOT NULL DEFAULT 'running',
    model            STRING,
    embed_model      STRING,
    input_tokens     INT           NOT NULL DEFAULT 0,
    output_tokens    INT           NOT NULL DEFAULT 0,
    cost_usd         DECIMAL(12,6) NOT NULL DEFAULT 0,
    cost_ceiling_usd DECIMAL(12,6) NOT NULL DEFAULT 5.0,
    halted_reason    STRING,
    recalled_count   INT           NOT NULL DEFAULT 0,
    deduped_count    INT           NOT NULL DEFAULT 0,
    written_count    INT           NOT NULL DEFAULT 0,
    started_at       TIMESTAMPTZ   NOT NULL DEFAULT now(),
    finished_at      TIMESTAMPTZ,
    CONSTRAINT run_status_enum CHECK (status IN ('running', 'complete', 'halted', 'failed')),
    INDEX runs_by_target (target_id, started_at DESC)
);

-- ---------------------------------------------------------------------------
-- embeddings — cross-session RECALL surface.
-- 1024 dims = Amazon Bedrock Titan Text Embeddings V2.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS embeddings (
    id          UUID        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    target_id   UUID        NOT NULL REFERENCES targets (id),
    artifact_id UUID        REFERENCES artifacts (id),
    run_id      UUID        REFERENCES agent_runs (id),
    chunk_idx   INT         NOT NULL DEFAULT 0,
    content     STRING      NOT NULL,
    embedding   VECTOR(1024) NOT NULL,
    model       STRING      NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    INDEX embeddings_by_target (target_id, created_at DESC)
);

-- ---------------------------------------------------------------------------
-- findings — DEDUP surface. `fingerprint` is the cheap exact gate; the vector
-- index is the semantic gate that catches the same issue reworded.
-- times_seen is why the second run is quiet instead of noisy.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS findings (
    id             UUID         NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    target_id      UUID         NOT NULL REFERENCES targets (id),
    asset_id       UUID         REFERENCES assets (id),
    title          STRING       NOT NULL,
    severity       STRING       NOT NULL,
    summary        STRING       NOT NULL,
    evidence       STRING,
    fingerprint    STRING       NOT NULL,
    embedding      VECTOR(1024) NOT NULL,
    first_seen_run UUID         REFERENCES agent_runs (id),
    last_seen_run  UUID         REFERENCES agent_runs (id),
    times_seen     INT          NOT NULL DEFAULT 1,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT severity_enum CHECK (severity IN ('info', 'low', 'medium', 'high', 'critical')),
    UNIQUE (target_id, fingerprint),
    INDEX findings_by_target (target_id, created_at DESC)
);

-- ---------------------------------------------------------------------------
-- audit_log — APPEND ONLY (see 002_roles.sql). One row per decision.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_log (
    id        UUID        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    run_id    UUID,
    target_id UUID,
    actor     STRING      NOT NULL,      -- gateway | analyst | scanner | operator
    action    STRING      NOT NULL,      -- scope_check | recall | dedup | write | halt
    resource  STRING,
    decision  STRING      NOT NULL,      -- allow | deny | hit | miss | ok
    detail    JSONB       NOT NULL DEFAULT '{}'::JSONB,
    at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    INDEX audit_by_run (run_id, at DESC),
    INDEX audit_by_time (at DESC)
);

-- ---------------------------------------------------------------------------
-- Distributed vector indexes (CockroachDB C-SPANN).
-- These are the two load-bearing paths: recall over `embeddings`, dedup over
-- `findings`. Cosine distance because Titan V2 output is normalised.
-- ---------------------------------------------------------------------------
CREATE VECTOR INDEX IF NOT EXISTS embeddings_vec ON embeddings (embedding vector_cosine_ops);
CREATE VECTOR INDEX IF NOT EXISTS findings_vec   ON findings   (embedding vector_cosine_ops);
