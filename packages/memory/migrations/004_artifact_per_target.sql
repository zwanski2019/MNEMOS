-- MNEMOS — an artifact is content-addressed, but *observing* it is per-target.
--
-- 001 put a global UNIQUE on artifacts.sha256, which conflated two different things:
-- the bytes (globally unique by definition, which is what content addressing means)
-- and the observation that those bytes were served from a particular estate.
--
-- With the global constraint, the same vendor bundle deployed to two properties
-- collapsed into a single row owned by whichever target was scanned first — so the
-- cross-target correlation that memory exists to surface could never fire, and the
-- second estate silently lost its provenance.
--
-- The S3 object stays deduplicated: the key is derived from the sha256, so identical
-- bytes are still uploaded exactly once. Only the *record* of who served them is
-- per-target, which is the thing we actually want to count.

USE mnemos;

DROP INDEX IF EXISTS artifacts_sha256_key CASCADE;

CREATE UNIQUE INDEX IF NOT EXISTS artifacts_target_sha
    ON artifacts (target_id, sha256);

-- Correlation reads this: "which estates served these exact bytes?"
CREATE INDEX IF NOT EXISTS artifacts_sha_lookup
    ON artifacts (sha256) STORING (target_id, s3_bucket, s3_key, byte_len);
