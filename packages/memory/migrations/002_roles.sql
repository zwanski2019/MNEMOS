-- MNEMOS — least-privilege roles.
--
-- The invariants in CLAUDE.md §3 are only worth something if they survive a
-- careless commit. Two of them are therefore enforced by CockroachDB, not by us:
--
--   "Scope decisions are immutable"  -> mnemos_agent has SELECT+INSERT on
--                                       scope_decisions. No UPDATE. No DELETE.
--   "Everything is audited"          -> same for audit_log. Rows can be written
--                                       and read, never rewritten or erased.
--
-- An attacker (or a bug) holding the application's credentials still cannot
-- rewrite the record of what the agent was allowed to do, or erase the evidence
-- of what it did. `make verify-invariants` asserts this from the outside.

USE mnemos;

CREATE ROLE IF NOT EXISTS mnemos_agent;

GRANT CONNECT ON DATABASE mnemos TO mnemos_agent;
GRANT USAGE ON SCHEMA public TO mnemos_agent;

-- Mutable working set: the agent owns its own operational data.
GRANT SELECT, INSERT, UPDATE ON TABLE targets    TO mnemos_agent;
GRANT SELECT, INSERT, UPDATE ON TABLE assets     TO mnemos_agent;
GRANT SELECT, INSERT, UPDATE ON TABLE artifacts  TO mnemos_agent;
GRANT SELECT, INSERT, UPDATE ON TABLE agent_runs TO mnemos_agent;
GRANT SELECT, INSERT, UPDATE ON TABLE findings   TO mnemos_agent;
GRANT SELECT, INSERT, UPDATE ON TABLE embeddings TO mnemos_agent;

-- Append-only ledgers. Deliberately no UPDATE, no DELETE.
GRANT SELECT, INSERT ON TABLE scope_decisions TO mnemos_agent;
GRANT SELECT, INSERT ON TABLE audit_log       TO mnemos_agent;

-- ---------------------------------------------------------------------------
-- The analyst is a separate principal and is READ ONLY everywhere. This is the
-- same posture the CockroachDB Cloud Managed MCP Server gives us in production:
-- the model can recall memory but is structurally incapable of writing to the
-- memory it is reasoning over, so recall can never contaminate the findings
-- store or the audit trail.
-- ---------------------------------------------------------------------------
CREATE ROLE IF NOT EXISTS mnemos_analyst_ro;

GRANT CONNECT ON DATABASE mnemos TO mnemos_analyst_ro;
GRANT USAGE ON SCHEMA public TO mnemos_analyst_ro;
GRANT SELECT ON TABLE targets, assets, artifacts, embeddings, findings,
                      agent_runs, audit_log, scope_decisions
      TO mnemos_analyst_ro;
