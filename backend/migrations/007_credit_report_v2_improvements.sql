-- Migration: Credit Report v2 improvements
-- Description: Adds 'skipped' bucket, 'skip' review decision, and
--              affected_deal_ids column on validations for drill-down from
--              validation findings into the preview table.
-- Date: 2026-04-10
--
-- See /root/.claude/plans/swift-dancing-aho.md for the design rationale.
--
-- The CHECK constraints in migration 006 were created inline and auto-named
-- by Postgres (e.g. credit_report_run_items_bucket_check). We look them up
-- via pg_constraint and drop/recreate so the migration is safe even if the
-- auto-generated name differs across environments.

-- ─── credit_report_run_items.bucket: add 'skipped' ───────────────────────
DO $$
DECLARE
    con_name text;
BEGIN
    FOR con_name IN
        SELECT conname FROM pg_constraint
        WHERE conrelid = 'credit_report_run_items'::regclass
          AND contype = 'c'
          AND pg_get_constraintdef(oid) ILIKE '%bucket%IN%'
    LOOP
        EXECUTE format(
            'ALTER TABLE credit_report_run_items DROP CONSTRAINT %I',
            con_name
        );
    END LOOP;
END $$;

ALTER TABLE credit_report_run_items
    ADD CONSTRAINT credit_report_run_items_bucket_check
    CHECK (bucket IN ('ready', 'review', 'excluded', 'carried', 'skipped'));


-- ─── credit_report_run_items.review_decision: add 'skip' ─────────────────
DO $$
DECLARE
    con_name text;
BEGIN
    FOR con_name IN
        SELECT conname FROM pg_constraint
        WHERE conrelid = 'credit_report_run_items'::regclass
          AND contype = 'c'
          AND pg_get_constraintdef(oid) ILIKE '%review_decision%IN%'
    LOOP
        EXECUTE format(
            'ALTER TABLE credit_report_run_items DROP CONSTRAINT %I',
            con_name
        );
    END LOOP;
END $$;

ALTER TABLE credit_report_run_items
    ADD CONSTRAINT credit_report_run_items_review_decision_check
    CHECK (
        review_decision IN ('approve', 'exclude', 'defer', 'skip')
        OR review_decision IS NULL
    );


-- ─── credit_report_account_state.last_review_decision: add 'skip' ────────
DO $$
DECLARE
    con_name text;
BEGIN
    FOR con_name IN
        SELECT conname FROM pg_constraint
        WHERE conrelid = 'credit_report_account_state'::regclass
          AND contype = 'c'
          AND pg_get_constraintdef(oid) ILIKE '%last_review_decision%IN%'
    LOOP
        EXECUTE format(
            'ALTER TABLE credit_report_account_state DROP CONSTRAINT %I',
            con_name
        );
    END LOOP;
END $$;

ALTER TABLE credit_report_account_state
    ADD CONSTRAINT credit_report_account_state_last_review_decision_check
    CHECK (
        last_review_decision IN ('approve', 'exclude', 'defer', 'skip')
        OR last_review_decision IS NULL
    );


-- ─── credit_report_validations.affected_deal_ids ─────────────────────────
-- Stores up to 200 deal_ids per finding so the UI can drill down from a
-- validation finding into the specific rows that triggered it.
ALTER TABLE credit_report_validations
    ADD COLUMN IF NOT EXISTS affected_deal_ids JSONB;

COMMENT ON COLUMN credit_report_validations.affected_deal_ids IS
    'Array of deal_id strings that triggered this finding. NULL for aggregate '
    'findings (MIN_ACCOUNTS, SSN_ZEROS, MISSING_COLUMN). Capped at 200 entries.';


-- ─── credit_report_runs.skipped_count ─────────────────────────────────────
-- Cached count of items in the 'skipped' bucket so the UI can render tab
-- counts without a separate query.
ALTER TABLE credit_report_runs
    ADD COLUMN IF NOT EXISTS skipped_count INT NOT NULL DEFAULT 0;

COMMENT ON COLUMN credit_report_runs.skipped_count IS
    'Number of items in the skipped bucket for this run. Updated by '
    '_recompute_run_counts on every mutation.';


-- ─── Verification ─────────────────────────────────────────────────────────
-- Confirm the new constraints are in place.
SELECT conname, pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid IN (
    'credit_report_run_items'::regclass,
    'credit_report_account_state'::regclass
  )
  AND contype = 'c'
  AND (
    conname LIKE '%bucket%'
    OR conname LIKE '%review_decision%'
  )
ORDER BY conname;
