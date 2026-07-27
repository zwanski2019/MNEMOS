-- MNEMOS — accounts, sessions, and entitlement.
--
-- Reading memory is public and always will be: the console is the funnel, and a
-- recon dashboard nobody can look at persuades nobody. Accounts exist to gate
-- *acting* — creating targets, launching scans, editing scope — because those
-- consume real money (Bedrock tokens, S3 storage, cluster RUs) and touch someone
-- else's infrastructure.
--
-- Trial policy lives in data, not in a constant in the application, so "how long
-- did this account actually have?" is answerable later — the same reasoning that
-- put scope in a table instead of a config file.

USE mnemos;

CREATE TABLE IF NOT EXISTS accounts (
    id            UUID        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    email         STRING      NOT NULL,
    -- scrypt output, never a reversible encoding. See auth.hash_password.
    password_hash STRING      NOT NULL,
    display_name  STRING,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ,
    disabled_at   TIMESTAMPTZ,
    UNIQUE (email)
);

-- Sessions store a *hash* of the bearer token. A dump of this table does not let
-- anyone log in, which is the same reasoning as never storing the password.
CREATE TABLE IF NOT EXISTS sessions (
    id           UUID        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    account_id   UUID        NOT NULL REFERENCES accounts (id),
    token_sha256 STRING      NOT NULL,
    user_agent   STRING,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at   TIMESTAMPTZ NOT NULL,
    revoked_at   TIMESTAMPTZ,
    UNIQUE (token_sha256),
    INDEX sessions_by_account (account_id, created_at DESC)
);

-- One row per account. `trial_ends_at` is written once at signup and never
-- recomputed, so extending a trial is an explicit, visible act rather than a
-- side effect of changing a constant.
CREATE TABLE IF NOT EXISTS subscriptions (
    id                     UUID        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    account_id             UUID        NOT NULL REFERENCES accounts (id),
    plan                   STRING      NOT NULL DEFAULT 'trial',
    status                 STRING      NOT NULL DEFAULT 'trialing',
    trial_started_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    trial_ends_at          TIMESTAMPTZ NOT NULL,
    -- Populated by the billing provider. No card data is ever stored here or
    -- anywhere else in this system; checkout happens on the provider's domain.
    provider_customer_id   STRING,
    provider_subscription_id STRING,
    current_period_end     TIMESTAMPTZ,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT plan_enum CHECK (plan IN ('trial', 'pro', 'none')),
    CONSTRAINT sub_status_enum CHECK (
        status IN ('trialing', 'active', 'past_due', 'expired', 'canceled')
    ),
    UNIQUE (account_id)
);

-- Which account did a thing. Nullable because the scanner and the demo run
-- unattended, and an audit row with no actor is better than no audit row.
ALTER TABLE audit_log  ADD COLUMN IF NOT EXISTS account_id UUID;
ALTER TABLE targets    ADD COLUMN IF NOT EXISTS owner_account_id UUID;
ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS account_id UUID;

CREATE INDEX IF NOT EXISTS targets_by_owner ON targets (owner_account_id);

-- The read-only web role must see entitlement state to render the paywall, but
-- must never see credentials. CockroachDB has no column-level GRANT, so the
-- boundary is a view: `password_hash` is not a column of `accounts_public`, and
-- the role is never granted the underlying table. The public console therefore
-- cannot select a password hash even if a page component asked it to.
CREATE VIEW IF NOT EXISTS accounts_public AS
    SELECT id, email, display_name, created_at, last_login_at, disabled_at
      FROM accounts;

GRANT SELECT ON accounts_public TO mnemos_web_ro;
GRANT SELECT ON TABLE subscriptions TO mnemos_web_ro;

GRANT SELECT, INSERT, UPDATE ON TABLE accounts      TO mnemos_agent;
GRANT SELECT, INSERT, UPDATE ON TABLE sessions      TO mnemos_agent;
GRANT SELECT, INSERT, UPDATE ON TABLE subscriptions TO mnemos_agent;
