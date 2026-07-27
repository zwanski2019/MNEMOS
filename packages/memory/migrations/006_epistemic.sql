-- MNEMOS — epistemic state: what we believe about a finding, and why.
--
-- `findings.status` already exists and answers a different question: does this
-- thing still exist out there (open / fixed / regressed). That is the world's
-- state. This table is *our* state — how strongly we believe the finding is real,
-- how much evidence backs it, and which prior beliefs it descends from.
--
-- They are deliberately separate. A finding can be `open` in the world and
-- `false_positive` in our belief; conflating them would make one of those two
-- facts unrepresentable.
--
-- Nothing here is a dedup bypass. Epistemic state is metadata attached *after*
-- the scope guard and the dedup gate have both run, and it can never be the
-- reason a write is allowed.

USE mnemos;

CREATE TABLE IF NOT EXISTS finding_states (
    finding_id     UUID          NOT NULL PRIMARY KEY REFERENCES findings (id),

    -- Posterior probability the finding is real, in [0,1]. Never exactly 0 or 1:
    -- a belief that cannot be updated by new evidence is not a belief.
    confidence     DECIMAL(6,5)  NOT NULL DEFAULT 0.5,

    -- How many independent observations have borne on this belief. Corroboration
    -- and contradiction both count — this is evidence volume, not agreement.
    evidence_count INT           NOT NULL DEFAULT 1,

    status         STRING        NOT NULL DEFAULT 'hypothesis',

    -- Where the belief came from: the prior findings recalled at commit time and
    -- how close each was. This is the provenance link that makes a confidence
    -- score auditable rather than a magic number.
    --   [{"prior_finding_id": uuid, "similarity": 0.91, "at": "…", "effect": "…"}]
    epistemic_chain JSONB        NOT NULL DEFAULT '[]'::JSONB,

    created_at     TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ   NOT NULL DEFAULT now(),

    CONSTRAINT epistemic_status_enum CHECK (
        status IN ('hypothesis', 'corroborated', 'confirmed', 'deprecated', 'false_positive')
    ),
    CONSTRAINT confidence_is_a_probability CHECK (confidence >= 0 AND confidence <= 1),
    CONSTRAINT evidence_count_is_positive CHECK (evidence_count >= 0)
);

CREATE INDEX IF NOT EXISTS finding_states_by_status
    ON finding_states (status, confidence DESC);

-- Poisoning lookup: "have we previously decided something like this was wrong?"
-- reads this index to find nearby false positives before trusting a new finding.
CREATE INDEX IF NOT EXISTS finding_states_false_positives
    ON finding_states (status) WHERE status = 'false_positive';

GRANT SELECT, INSERT, UPDATE ON TABLE finding_states TO mnemos_agent;
GRANT SELECT ON TABLE finding_states TO mnemos_analyst_ro;
GRANT SELECT ON TABLE finding_states TO mnemos_web_ro;
