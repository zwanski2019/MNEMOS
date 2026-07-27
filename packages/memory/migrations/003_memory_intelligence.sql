-- MNEMOS — memory that reasons about its own age.
--
-- Storing a finding is easy. The hard part is what memory should believe about a
-- finding it has not seen in three weeks, and what it should do when something it
-- recorded as fixed comes back.
--
-- Nothing here is a new store. These are columns on `findings` so that decay,
-- regression, and correlation are all answerable in the same SQL surface as recall
-- and dedup — no second system to keep consistent.

USE mnemos;

-- open      currently believed present
-- fixed     a later scan of the same estate did not re-observe it
-- regressed was fixed, then came back — the most important state in the table
ALTER TABLE findings ADD COLUMN IF NOT EXISTS status STRING NOT NULL DEFAULT 'open';

-- When the agent last actually observed this, as opposed to when the row was made.
-- Confidence decays from this, not from created_at, so a finding re-confirmed today
-- is fully trusted even if it was first written months ago.
ALTER TABLE findings ADD COLUMN IF NOT EXISTS last_confirmed_at TIMESTAMPTZ NOT NULL DEFAULT now();

-- Which run decided it was fixed, so the audit trail can be joined to the decision.
ALTER TABLE findings ADD COLUMN IF NOT EXISTS closed_by_run UUID;

-- How many times it has come back after being fixed. A finding that regresses
-- repeatedly is a process problem, not a bug, and memory is the only thing that
-- can tell you that.
ALTER TABLE findings ADD COLUMN IF NOT EXISTS regression_count INT NOT NULL DEFAULT 0;

ALTER TABLE findings ADD CONSTRAINT IF NOT EXISTS finding_status_enum
    CHECK (status IN ('open', 'fixed', 'regressed'));

CREATE INDEX IF NOT EXISTS findings_by_status ON findings (target_id, status, last_confirmed_at DESC);

-- Findings carry the asset they came from; correlating by title across targets is
-- the cheap version, by embedding distance the thorough one.
CREATE INDEX IF NOT EXISTS findings_by_title ON findings (title);
