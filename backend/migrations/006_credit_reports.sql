-- Migration: Credit Report tables for Metro 2 / Experian reporting
-- Description: Persists monthly credit-reporting run history, per-account
--              snapshots, operator decisions, validations, and raw CSV lineage.
-- Date: 2026-04-08
--
-- Purpose: Replaces the standalone metro2_generator.py CLI workflow with a
-- delegation-friendly web UI backed by durable state. The core design goal is
-- continuity: accounts reported in a prior cycle MUST continue to be reported
-- in subsequent cycles (Experian penalizes reporters who silently drop
-- accounts mid-reporting).
--
-- See /root/.claude/plans/swift-dancing-aho.md for the full design rationale.

-- ─── credit_report_uploads ────────────────────────────────────────────────
-- Raw CSV blobs uploaded per cycle. Stored as base64 text (Supabase Python
-- client has no bytea support). Provides lineage/forensics: if a prior-cycle
-- deal disappears from this cycle's upload, an engineer can reload the
-- original file to confirm whether MongoDB or mongoexport was at fault.
CREATE TABLE IF NOT EXISTS credit_report_uploads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kind VARCHAR(20) NOT NULL CHECK (kind IN ('deal', 'address')),
    original_filename VARCHAR(255) NOT NULL,
    byte_size BIGINT NOT NULL,
    sha256 CHAR(64) NOT NULL,
    row_count INT NOT NULL,
    content_b64 TEXT NOT NULL,
    uploaded_by UUID REFERENCES users(id) ON DELETE SET NULL,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cr_uploads_kind   ON credit_report_uploads(kind);
CREATE INDEX IF NOT EXISTS idx_cr_uploads_sha256 ON credit_report_uploads(sha256);

COMMENT ON TABLE credit_report_uploads IS
    'Raw CSV lineage for Credit Report uploads. Stores the mongoexport CSVs '
    'that produced each run so they can be re-fetched for forensics or reprocessing.';


-- ─── credit_report_runs ───────────────────────────────────────────────────
-- One row per cycle attempt. Drafts are scratchpads (unbounded, editable).
-- Finals are the immutable record of what was sent to Experian. A re-finalize
-- for the same cycle_month archives (never deletes) the prior final so
-- history is preserved.
CREATE TABLE IF NOT EXISTS credit_report_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Last day of the month being reported (e.g. 2026-03-31 for Mar 2026).
    cycle_month DATE NOT NULL,

    -- draft    = in-progress, can be edited / re-uploaded / decisions changed
    -- final    = locked, downloadable, used as continuity source for next cycle
    -- archived = superseded by a newer final for the same cycle_month
    status VARCHAR(20) NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'final', 'archived')),

    -- Metro 2 as-of date string (YYYYMMDD) used by the engine for this run.
    as_of_date_str CHAR(8) NOT NULL,

    -- Bucket counts captured at transform time so history lists are cheap.
    ready_count        INT NOT NULL DEFAULT 0,
    review_count       INT NOT NULL DEFAULT 0,
    excluded_count     INT NOT NULL DEFAULT 0,
    carried_over_count INT NOT NULL DEFAULT 0,

    -- Lineage to the raw CSVs that produced this run.
    deal_upload_id    UUID REFERENCES credit_report_uploads(id) ON DELETE SET NULL,
    address_upload_id UUID REFERENCES credit_report_uploads(id) ON DELETE SET NULL,

    -- Free-form audit note.
    note TEXT,

    created_by  UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finalized_by UUID REFERENCES users(id) ON DELETE SET NULL,
    finalized_at TIMESTAMPTZ,
    archived_at  TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_cr_runs_cycle  ON credit_report_runs(cycle_month DESC);
CREATE INDEX IF NOT EXISTS idx_cr_runs_status ON credit_report_runs(status);

-- Enforce at most one 'final' per cycle. Drafts and archived rows are unbounded.
CREATE UNIQUE INDEX IF NOT EXISTS idx_cr_runs_one_final_per_cycle
    ON credit_report_runs(cycle_month)
    WHERE status = 'final';

COMMENT ON TABLE credit_report_runs IS
    'One row per Credit Report cycle attempt (draft or final). Exactly one '
    'final per cycle_month; re-finalizing archives (never deletes) the prior '
    'final so history is preserved.';


-- ─── credit_report_run_items ──────────────────────────────────────────────
-- Per-account snapshot for a specific run. One row per deal_id per run.
-- This is the single source of truth for CSV rendering - ready/review/excluded
-- CSVs are regenerated from this table on demand.
CREATE TABLE IF NOT EXISTS credit_report_run_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES credit_report_runs(id) ON DELETE CASCADE,

    -- MongoDB deal _id - system-wide identifier for an account.
    deal_id VARCHAR(64) NOT NULL,

    -- ready    = will be in the metro2_ready CSV
    -- review   = needs manual decision, not exported unless approved
    -- excluded = not exported (with reason)
    -- carried  = pulled in from prior cycle even though missing from upload
    bucket VARCHAR(20) NOT NULL
        CHECK (bucket IN ('ready', 'review', 'excluded', 'carried')),

    -- Human-readable reason for review/excluded/carried buckets.
    reason TEXT,

    -- Snapshot of the merged deal+address input row (as JSONB).
    -- Used for UI preview and for re-building metro2_row after decisions.
    source_row JSONB NOT NULL,

    -- The computed Metro 2 row (42 fields as JSONB). NULL for non-ready
    -- buckets until a review approval promotes the row.
    metro2_row JSONB,

    -- Review-queue decision (nullable until operator acts).
    review_decision VARCHAR(20)
        CHECK (review_decision IN ('approve', 'exclude', 'defer') OR review_decision IS NULL),
    review_metro2_status_code VARCHAR(4),
    review_fcra_dofi CHAR(8),
    review_note TEXT,

    -- How the business-account flag was determined for THIS run item.
    -- auto        = regex BUSINESS_PATTERN matched
    -- manual_on   = operator manually flagged as business
    -- manual_off  = operator manually unflagged (override of regex match)
    business_flag_source VARCHAR(20)
        CHECK (business_flag_source IN ('auto', 'manual_on', 'manual_off') OR business_flag_source IS NULL),

    -- Continuity flags.
    was_in_prior_cycle  BOOLEAN NOT NULL DEFAULT FALSE,
    missing_from_upload BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (run_id, deal_id)
);

CREATE INDEX IF NOT EXISTS idx_cr_items_run    ON credit_report_run_items(run_id);
CREATE INDEX IF NOT EXISTS idx_cr_items_bucket ON credit_report_run_items(run_id, bucket);
CREATE INDEX IF NOT EXISTS idx_cr_items_deal   ON credit_report_run_items(deal_id);

COMMENT ON TABLE credit_report_run_items IS
    'Per-account snapshot for a specific Credit Report run. The single source '
    'of truth - CSVs are regenerated from this table on download.';


-- ─── credit_report_account_state ─────────────────────────────────────────
-- Durable cross-cycle memory. One row per deal_id, upserted on finalize.
-- Stores persistent business-flag overrides and the last review decision so
-- future cycles can auto-apply them.
CREATE TABLE IF NOT EXISTS credit_report_account_state (
    deal_id VARCHAR(64) PRIMARY KEY,

    -- Business override: NULL = fallback to regex, TRUE = permanently excluded,
    -- FALSE = permanently NOT business (regex match ignored).
    is_business_override BOOLEAN,
    business_flag_set_by UUID REFERENCES users(id) ON DELETE SET NULL,
    business_flag_set_at TIMESTAMPTZ,
    business_flag_note TEXT,

    -- Last finalized review decision. Auto-applied next cycle when the
    -- MongoDB statusName equals last_review_status_name (normalized).
    last_review_decision VARCHAR(20)
        CHECK (last_review_decision IN ('approve', 'exclude', 'defer') OR last_review_decision IS NULL),
    last_review_metro2_status_code VARCHAR(4),
    last_review_fcra_dofi CHAR(8),
    last_review_status_name VARCHAR(50),
    last_review_set_by UUID REFERENCES users(id) ON DELETE SET NULL,
    last_review_set_at TIMESTAMPTZ,
    last_review_note TEXT,

    -- Continuity tracking.
    last_reported_cycle DATE,
    last_reported_run_id UUID REFERENCES credit_report_runs(id) ON DELETE SET NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cr_state_business
    ON credit_report_account_state(is_business_override)
    WHERE is_business_override IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cr_state_last_cycle
    ON credit_report_account_state(last_reported_cycle DESC);

COMMENT ON TABLE credit_report_account_state IS
    'Persistent per-deal Credit Report state. Stores business-flag overrides '
    'and last review decisions so they auto-apply across cycles. Upserted '
    'only on finalize, never on draft edits.';


-- ─── credit_report_validations ────────────────────────────────────────────
-- Per-run validation findings (structured). Persisted so the history list
-- shows health at a glance without re-running validate().
CREATE TABLE IF NOT EXISTS credit_report_validations (
    id BIGSERIAL PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES credit_report_runs(id) ON DELETE CASCADE,
    severity VARCHAR(10) NOT NULL CHECK (severity IN ('FATAL', 'WARNING', 'INFO')),
    code VARCHAR(50) NOT NULL,
    message TEXT NOT NULL,
    affected_count INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cr_validations_run ON credit_report_validations(run_id);

COMMENT ON TABLE credit_report_validations IS
    'Per-run Metro 2 validation findings with machine-readable code field '
    'for UI severity rendering and jump-to-row links.';


-- ─── Triggers: updated_at auto-update ─────────────────────────────────────
-- Generic updated_at trigger function (reused by multiple tables).
CREATE OR REPLACE FUNCTION update_cr_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_cr_run_items_updated_at ON credit_report_run_items;
CREATE TRIGGER trigger_cr_run_items_updated_at
    BEFORE UPDATE ON credit_report_run_items
    FOR EACH ROW
    EXECUTE FUNCTION update_cr_updated_at();

DROP TRIGGER IF EXISTS trigger_cr_account_state_updated_at ON credit_report_account_state;
CREATE TRIGGER trigger_cr_account_state_updated_at
    BEFORE UPDATE ON credit_report_account_state
    FOR EACH ROW
    EXECUTE FUNCTION update_cr_updated_at();


-- Smoke check: verify all five tables exist.
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN (
    'credit_report_uploads',
    'credit_report_runs',
    'credit_report_run_items',
    'credit_report_account_state',
    'credit_report_validations'
  )
ORDER BY table_name;
