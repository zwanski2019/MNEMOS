-- MNEMOS — the agent knowing when it is confused.
--
-- Escalation is a success state. An agent that stops and says "these two things
-- cannot both be true, and I do not know which to believe" is worth far more than
-- one that picks whichever it saw last and writes a finding with a confident
-- summary. The second kind is how automated security tooling loses operator
-- trust, and trust is the only thing that makes any of this useful.
--
-- This table is the record of those moments: what confused it, how badly, what it
-- proposed, and who resolved it.

USE mnemos;

CREATE TABLE IF NOT EXISTS cognitive_states (
    id              UUID          NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    run_id          UUID          NOT NULL REFERENCES agent_runs (id),
    target_id       UUID          REFERENCES targets (id),

    -- 0 = coherent, 1 = cannot proceed. Above ESCALATION_THRESHOLD the cycle halts.
    confusion_score DECIMAL(6,5)  NOT NULL DEFAULT 0,

    -- Every signal that fired, with its own score and the evidence behind it:
    --   [{"signal": "...", "score": 0.8, "detail": {...}, "memory_refs": [...]}]
    -- Memory refs are finding/embedding ids, so an escalation can be adjudicated
    -- from the same evidence the agent had, rather than from its prose about it.
    reasons         JSONB         NOT NULL DEFAULT '[]'::JSONB,

    -- What the agent thinks the operator's options are, with support for each.
    proposals       JSONB         NOT NULL DEFAULT '[]'::JSONB,

    status          STRING        NOT NULL DEFAULT 'open',
    escalated_to    UUID          REFERENCES accounts (id),
    resolution      STRING,
    resolved_by     UUID          REFERENCES accounts (id),
    resolved_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),

    CONSTRAINT cognitive_status_enum CHECK (
        status IN ('open', 'acknowledged', 'resolved', 'timed_out')
    ),
    CONSTRAINT confusion_is_a_fraction CHECK (confusion_score >= 0 AND confusion_score <= 1),
    INDEX cognitive_open (status, created_at DESC),
    INDEX cognitive_by_run (run_id)
);

-- A run that stopped because it was confused is not a run that failed. The
-- distinction has to survive into the data or the dashboards will show a red
-- number for the system working exactly as designed.
ALTER TABLE agent_runs DROP CONSTRAINT IF EXISTS run_status_enum;
ALTER TABLE agent_runs ADD CONSTRAINT run_status_enum
    CHECK (status IN ('running', 'complete', 'halted', 'failed', 'escalated'));

GRANT SELECT, INSERT, UPDATE ON TABLE cognitive_states TO mnemos_agent;
GRANT SELECT ON TABLE cognitive_states TO mnemos_analyst_ro;
GRANT SELECT ON TABLE cognitive_states TO mnemos_web_ro;
