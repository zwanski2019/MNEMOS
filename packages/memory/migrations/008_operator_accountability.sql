-- MNEMOS — operator accountability.
--
-- Registration is a weapons-control surface. The controlling risk is not spam,
-- it is an unattributable operator pointing a scanner at systems that never
-- consented. So for any scan this system ever performs we must be able to produce
-- a signed chain: this human accepted this covenant at this time, asserted
-- authorisation for this scope, and this scan is bound to that record.
--
-- The enforcement that matters is at the bottom of this file. `agent_runs` gains
-- NOT NULL foreign keys to the authorising grant and receipt, so a scan that
-- cannot name its authorisation is rejected by the database rather than by an
-- `if` somebody can forget to write.

USE mnemos;

-- ---------------------------------------------------------------------------
-- A1. Tiers
--
-- pending  : signed up, verified email, can read its own dashboard. No scanning.
-- operator : covenant signed + scope attestation accepted. May scan scopes that
--            have a live grant, and only those.
-- admin    : granted out of band. Grant review, revocation, audit export.
-- ---------------------------------------------------------------------------
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS tier STRING NOT NULL DEFAULT 'pending';
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS tier_granted_at TIMESTAMPTZ;
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS tier_granted_by UUID;

ALTER TABLE accounts ADD CONSTRAINT IF NOT EXISTS account_tier_enum
    CHECK (tier IN ('pending', 'operator', 'admin'));

CREATE INDEX IF NOT EXISTS accounts_by_tier ON accounts (tier);

-- ---------------------------------------------------------------------------
-- A2. Covenant acceptance receipts — APPEND ONLY.
--
-- Revocation is a new row of type 'revocation', never a mutation of the original.
-- The application role is granted SELECT+INSERT and nothing else (see the bottom
-- of this file), so tampering is refused by CockroachDB, not by our code.
--
-- `payload` is the exact canonical-JSON document that was signed. Storing the
-- document rather than its parts means verification never has to reconstruct it
-- and get the reconstruction subtly wrong.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS covenant_receipts (
    id               UUID        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    operator_id      UUID        NOT NULL REFERENCES accounts (id),
    kind             STRING      NOT NULL DEFAULT 'acceptance',

    covenant_version STRING      NOT NULL,
    covenant_hash    STRING      NOT NULL,   -- sha256 of the exact text accepted

    -- The signed document, byte-for-byte as it was signed.
    payload          JSONB       NOT NULL,
    signature        STRING      NOT NULL,   -- base64url Ed25519 over canonical JSON
    key_id           STRING      NOT NULL,

    -- Supersedes an earlier receipt (revocations and re-acceptances point back).
    supersedes       UUID        REFERENCES covenant_receipts (id),

    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT receipt_kind_enum CHECK (kind IN ('acceptance', 'revocation')),
    INDEX receipts_by_operator (operator_id, created_at DESC),
    INDEX receipts_by_version (covenant_version)
);

-- ---------------------------------------------------------------------------
-- A3. Scope grants.
--
-- `expires_at` is mandatory and capped at 90 days by the application; the CHECK
-- here enforces that it is always after the grant, so a grant can never be born
-- already-eternal through a bad default.
--
-- `scope_spec` is fed to the *same* matcher the fail-closed scope engine uses.
-- There is deliberately no second, looser parser for the signup path.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scope_grants (
    id             UUID        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    operator_id    UUID        NOT NULL REFERENCES accounts (id),
    receipt_id     UUID        NOT NULL REFERENCES covenant_receipts (id),
    target_id      UUID        REFERENCES targets (id),

    scope_spec     STRING      NOT NULL,     -- host glob, same syntax as scope_decisions

    -- How the operator proved they may test this. One of:
    --   bounty:<program-url>#<sha256 of program snapshot>
    --   letter:<artifact sha256>
    --   self_owned:<dns txt proof token>
    evidence_kind  STRING      NOT NULL,
    evidence_ref   STRING      NOT NULL,
    evidence_verified_at TIMESTAMPTZ,

    granted_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at     TIMESTAMPTZ NOT NULL,
    granted_by     UUID        NOT NULL REFERENCES accounts (id),
    revoked_at     TIMESTAMPTZ,
    revoked_by     UUID        REFERENCES accounts (id),
    revocation_reason STRING,

    CONSTRAINT evidence_kind_enum CHECK (
        evidence_kind IN ('bounty', 'letter', 'self_owned')
    ),
    CONSTRAINT grant_must_expire CHECK (expires_at > granted_at),
    INDEX grants_by_operator (operator_id, expires_at DESC),
    INDEX grants_live (operator_id, revoked_at, expires_at)
);

-- ---------------------------------------------------------------------------
-- A4. Structural audit binding — the point of the whole part.
--
-- A scan row that cannot name its authorising grant should be impossible, not
-- merely discouraged. These are NOT NULL foreign keys, so the database refuses
-- the insert. Enforcement that lives only in a handler is not enforcement.
--
-- Existing rows predate this model, so they are bound to an explicit bootstrap
-- grant rather than being silently exempted — "legacy, pre-accountability" is a
-- fact worth being able to query, and NULL would have hidden it.
-- ---------------------------------------------------------------------------
INSERT INTO accounts (id, email, password_hash, display_name, tier)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    'system@mnemos.invalid',
    'x-not-a-login-account',            -- cannot verify; no login path exists
    'MNEMOS system (pre-accountability)',
    'admin'
) ON CONFLICT (email) DO NOTHING;

INSERT INTO covenant_receipts (
    id, operator_id, kind, covenant_version, covenant_hash, payload, signature, key_id
) VALUES (
    '00000000-0000-0000-0000-000000000002',
    '00000000-0000-0000-0000-000000000001',
    'acceptance', 'bootstrap',
    'bootstrap-no-covenant-was-signed',
    '{"note":"synthetic receipt for rows created before operator accountability existed"}'::JSONB,
    'unsigned-bootstrap',
    'bootstrap'
) ON CONFLICT (id) DO NOTHING;

INSERT INTO scope_grants (
    id, operator_id, receipt_id, scope_spec, evidence_kind, evidence_ref,
    granted_at, expires_at, granted_by, revoked_at, revocation_reason
) VALUES (
    '00000000-0000-0000-0000-000000000003',
    '00000000-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000002',
    'legacy.pre-accountability.invalid',
    'letter', 'bootstrap:no-evidence',
    '1970-01-01T00:00:00Z', '1970-01-02T00:00:00Z',
    '00000000-0000-0000-0000-000000000001',
    '1970-01-02T00:00:00Z',
    'bootstrap grant — expired and revoked at creation so it can never authorise a scan'
) ON CONFLICT (id) DO NOTHING;

ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS grant_id UUID;
ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS receipt_id UUID;

UPDATE agent_runs
   SET grant_id = '00000000-0000-0000-0000-000000000003',
       receipt_id = '00000000-0000-0000-0000-000000000002'
 WHERE grant_id IS NULL OR receipt_id IS NULL;

ALTER TABLE agent_runs ALTER COLUMN grant_id SET NOT NULL;
ALTER TABLE agent_runs ALTER COLUMN receipt_id SET NOT NULL;

ALTER TABLE agent_runs ADD CONSTRAINT IF NOT EXISTS agent_runs_grant_fk
    FOREIGN KEY (grant_id) REFERENCES scope_grants (id);
ALTER TABLE agent_runs ADD CONSTRAINT IF NOT EXISTS agent_runs_receipt_fk
    FOREIGN KEY (receipt_id) REFERENCES covenant_receipts (id);

CREATE INDEX IF NOT EXISTS agent_runs_by_grant ON agent_runs (grant_id);

-- ---------------------------------------------------------------------------
-- Privileges.
--
-- covenant_receipts is append-only for the same reason audit_log and
-- scope_decisions are: the record of what someone consented to must survive
-- whoever holds the application's credentials.
-- ---------------------------------------------------------------------------
GRANT SELECT, INSERT ON TABLE covenant_receipts TO mnemos_agent;
GRANT SELECT, INSERT, UPDATE ON TABLE scope_grants TO mnemos_agent;

GRANT SELECT ON TABLE covenant_receipts TO mnemos_analyst_ro;
GRANT SELECT ON TABLE scope_grants TO mnemos_analyst_ro;

-- The public console shows grant state but must never read the receipt payload,
-- which carries the identity binding and IP hash.
CREATE VIEW IF NOT EXISTS scope_grants_public AS
    SELECT id, operator_id, target_id, scope_spec, evidence_kind, granted_at,
           expires_at, revoked_at
      FROM scope_grants;

GRANT SELECT ON scope_grants_public TO mnemos_web_ro;
