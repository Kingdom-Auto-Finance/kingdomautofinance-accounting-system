-- Migration: Native Metro 2 platform (Switch Labs parity)
-- Description: Adds the standing-ledger data model and supporting tables for
--              generating Experian Metro 2 .txt files natively inside our
--              platform, replacing the external Switch Labs dependency.
-- Date: 2026-04-14
--
-- See /root/.claude/plans/hazy-forging-pixel.md for the full design rationale.
--
-- Tables introduced (all prefixed metro2_):
--   metro2_records            - standing ledger, one row per reportable account
--   metro2_record_history     - append-only audit of every record field change
--   metro2_mapping_templates  - savable column-mapping presets for File Upload
--   metro2_upload_batches     - transient staging for the Map Fields flow
--   metro2_files              - generated .txt file metadata (binary in Storage)
--   metro2_transmissions      - operator-logged submissions to Experian STS
--   metro2_responses          - bureau response files and parsed outcomes
--   metro2_disputes           - dispute intake and resolution tracking


-- ─── metro2_records ───────────────────────────────────────────────────────
-- The standing ledger of every account being reported to Experian. Rows are
-- upserted by cycle finalization (origin='cycle') or inserted manually from
-- the File Upload / Records tab (origin='manual'). Manual edits on cycle-
-- originated rows flip origin to 'manual' to prevent the next cycle from
-- clobbering the operator's correction.
CREATE TABLE IF NOT EXISTS metro2_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Identity (uniqueness enforced below).
    subscriber_code VARCHAR(20) NOT NULL DEFAULT '3983542',
    consumer_account_number VARCHAR(30) NOT NULL,

    -- All 43 Metro 2 base-segment fields as typed columns.
    portfolio_type               CHAR(1)        NOT NULL DEFAULT 'I',
    account_type                 VARCHAR(2)     NOT NULL DEFAULT '00',
    date_opened                  DATE,
    credit_limit                 NUMERIC(11, 2) NOT NULL DEFAULT 0,
    highest_credit_or_orig_loan  NUMERIC(11, 2) NOT NULL DEFAULT 0,
    terms_duration               VARCHAR(3),
    terms_frequency              CHAR(1)        NOT NULL DEFAULT 'M',
    scheduled_payment_amt        NUMERIC(11, 2) NOT NULL DEFAULT 0,
    actual_payment_amt           NUMERIC(11, 2) NOT NULL DEFAULT 0,
    account_status               VARCHAR(2)     NOT NULL DEFAULT '11',
    payment_rating               CHAR(1),
    payment_history_profile      VARCHAR(24),
    special_comment              VARCHAR(2),
    compliance_condition_code    VARCHAR(2),
    current_balance              NUMERIC(11, 2) NOT NULL DEFAULT 0,
    amount_past_due              NUMERIC(11, 2) NOT NULL DEFAULT 0,
    original_chargeoff_amt       NUMERIC(11, 2) NOT NULL DEFAULT 0,
    date_of_account_info         DATE,
    fcra_dofi                    DATE,
    date_closed                  DATE,
    date_last_payment            DATE,
    interest_type                CHAR(1),
    surname                      VARCHAR(25),
    first_name                   VARCHAR(20),
    middle_name                  VARCHAR(20),
    generation_code              CHAR(1),
    ssn                          VARCHAR(9),
    date_of_birth                DATE,
    phone_number                 VARCHAR(10),
    ecoa_code                    CHAR(1)        NOT NULL DEFAULT '1',
    consumer_info_indicator      VARCHAR(2),
    country_code                 VARCHAR(2)     NOT NULL DEFAULT 'US',
    address_1                    VARCHAR(32),
    address_2                    VARCHAR(32),
    city                         VARCHAR(20),
    state                        VARCHAR(2),
    postal_code                  VARCHAR(9),
    address_indicator            CHAR(1)        NOT NULL DEFAULT 'C',
    residence_code               CHAR(1),

    -- Ledger metadata.
    -- origin='cycle'  → written by finalize_run; refreshable on next cycle.
    -- origin='manual' → written by operator; NOT overwritten by cycle refresh.
    origin VARCHAR(10) NOT NULL DEFAULT 'manual'
        CHECK (origin IN ('cycle', 'manual')),

    -- Links back to the cycle run that first created this row. NULL for
    -- rows added manually outside the cycle workflow.
    source_cycle_id UUID REFERENCES credit_report_runs(id) ON DELETE SET NULL,
    source_deal_id  VARCHAR(64),

    -- Soft-delete: is_active=false drops from next generated .txt file.
    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    -- Most recent validation result (Layers 2+3).
    last_validated_at     TIMESTAMPTZ,
    last_validated_status VARCHAR(10)
        CHECK (last_validated_status IN ('clean', 'warning', 'fatal')
               OR last_validated_status IS NULL),
    last_validation_issues JSONB,

    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    updated_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Uniqueness: one active record per (subscriber, account#).
    UNIQUE (subscriber_code, consumer_account_number)
);

CREATE INDEX IF NOT EXISTS idx_m2rec_active
    ON metro2_records(is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_m2rec_origin
    ON metro2_records(origin);
CREATE INDEX IF NOT EXISTS idx_m2rec_cycle
    ON metro2_records(source_cycle_id);
CREATE INDEX IF NOT EXISTS idx_m2rec_status
    ON metro2_records(account_status);
CREATE INDEX IF NOT EXISTS idx_m2rec_validation
    ON metro2_records(last_validated_status)
    WHERE last_validated_status IN ('warning', 'fatal');

COMMENT ON TABLE metro2_records IS
    'Standing ledger of all accounts being reported to Experian. Upserted '
    'by cycle finalization or edited manually from the Records tab. '
    'Source of truth for every generated Metro 2 .txt file.';


-- ─── metro2_record_history ────────────────────────────────────────────────
-- Append-only audit trail for per-record edits (the "History" drawer button).
CREATE TABLE IF NOT EXISTS metro2_record_history (
    id BIGSERIAL PRIMARY KEY,
    record_id UUID NOT NULL REFERENCES metro2_records(id) ON DELETE CASCADE,
    changed_by UUID REFERENCES users(id) ON DELETE SET NULL,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    change_type VARCHAR(20) NOT NULL
        CHECK (change_type IN ('create', 'update', 'deactivate', 'reactivate', 'cycle_refresh')),
    -- field_name/old_value/new_value are NULL when change_type is 'create';
    -- for 'update' we store one row per changed field.
    field_name VARCHAR(50),
    old_value TEXT,
    new_value TEXT,
    note TEXT
);

CREATE INDEX IF NOT EXISTS idx_m2hist_record
    ON metro2_record_history(record_id, changed_at DESC);


-- ─── metro2_mapping_templates ─────────────────────────────────────────────
-- Savable column-mapping presets used by the Map Fields modal (Layer 1).
CREATE TABLE IF NOT EXISTS metro2_mapping_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    -- Example: {"acct_num": "ConsumerAccountNumber", "bal": "CurrentBalance"}
    mapping JSONB NOT NULL,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Only one row may carry is_default=TRUE at a time.
CREATE UNIQUE INDEX IF NOT EXISTS idx_m2mapt_one_default
    ON metro2_mapping_templates(is_default) WHERE is_default = TRUE;


-- ─── metro2_upload_batches ────────────────────────────────────────────────
-- Transient staging for the File Upload flow. An operator uploads a CSV/XLSX,
-- the backend parses it into raw_rows, the Map Fields modal sets mapping_used,
-- the validator writes validation_report. On 'accepted' the rows are pushed
-- into metro2_records; on 'rejected' or 24h TTL the batch is dropped.
CREATE TABLE IF NOT EXISTS metro2_upload_batches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    original_filename VARCHAR(255) NOT NULL,
    byte_size BIGINT NOT NULL,
    sha256 CHAR(64) NOT NULL,
    row_count INT NOT NULL,
    headers JSONB NOT NULL,                -- original column headers from CSV
    raw_rows JSONB NOT NULL,               -- parsed rows, all as strings
    mapping_used JSONB,                    -- column → Metro 2 field
    validation_report JSONB,               -- {fatal:int, warning:int, rows:[...]}
    status VARCHAR(20) NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'validated', 'accepted', 'rejected')),
    uploaded_by UUID REFERENCES users(id) ON DELETE SET NULL,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    accepted_at TIMESTAMPTZ,
    rejected_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_m2batch_status
    ON metro2_upload_batches(status);
CREATE INDEX IF NOT EXISTS idx_m2batch_uploaded_at
    ON metro2_upload_batches(uploaded_at DESC);

COMMENT ON TABLE metro2_upload_batches IS
    'Transient staging for the File Upload tab Map Fields flow. Rows cleared '
    'on accept/reject. Cron can drop batches older than 24h in status draft.';


-- ─── metro2_files ─────────────────────────────────────────────────────────
-- Each generated .txt file. The binary lives in Supabase Storage; this table
-- holds metadata, SHA-256, and the exact list of record_ids frozen into the
-- file so we can re-render or audit it later.
CREATE TABLE IF NOT EXISTS metro2_files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename VARCHAR(64) NOT NULL,          -- NBTNU.MMDDYYYY.txt
    as_of_date DATE NOT NULL,
    record_count INT NOT NULL,
    total_current_balance NUMERIC(14, 2) NOT NULL DEFAULT 0,
    total_past_due NUMERIC(14, 2) NOT NULL DEFAULT 0,
    storage_path TEXT NOT NULL,             -- e.g. metro2-files/NBTNU.04142026.txt
    sha256 CHAR(64) NOT NULL,
    size_bytes BIGINT NOT NULL,
    header_snapshot JSONB NOT NULL,         -- parsed header fields
    trailer_snapshot JSONB NOT NULL,        -- parsed trailer totals
    record_ids UUID[] NOT NULL,             -- which metro2_records rows were frozen
    generated_by UUID REFERENCES users(id) ON DELETE SET NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_m2files_as_of
    ON metro2_files(as_of_date DESC);
CREATE INDEX IF NOT EXISTS idx_m2files_generated_at
    ON metro2_files(generated_at DESC);

COMMENT ON TABLE metro2_files IS
    'Metadata for each Metro 2 .txt file generated. Binary stored in Supabase '
    'Storage at storage_path. Every file is content-addressed by sha256.';


-- ─── metro2_transmissions ─────────────────────────────────────────────────
-- Operator-logged submissions to Experian STS. No automation in v1 - the
-- operator downloads the .txt, uploads to data-eft.experian.com manually,
-- then records the transmission here for audit and to link responses.
CREATE TABLE IF NOT EXISTS metro2_transmissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_id UUID NOT NULL REFERENCES metro2_files(id) ON DELETE CASCADE,
    transmitted_at TIMESTAMPTZ NOT NULL,
    transmitted_by UUID REFERENCES users(id) ON DELETE SET NULL,
    method VARCHAR(20) NOT NULL DEFAULT 'manual_sts'
        CHECK (method IN ('manual_sts')),
    confirmation_ref VARCHAR(100),
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_m2tx_file ON metro2_transmissions(file_id);
CREATE INDEX IF NOT EXISTS idx_m2tx_date ON metro2_transmissions(transmitted_at DESC);


-- ─── metro2_responses ─────────────────────────────────────────────────────
-- Bureau response files (Experian returns one within ~48h per transmission).
-- Operator uploads the response .txt; parser writes parsed_summary and
-- raw_errors for drill-down.
CREATE TABLE IF NOT EXISTS metro2_responses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    transmission_id UUID REFERENCES metro2_transmissions(id) ON DELETE SET NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    uploaded_by UUID REFERENCES users(id) ON DELETE SET NULL,
    response_filename VARCHAR(255) NOT NULL,
    response_storage_path TEXT NOT NULL,
    response_sha256 CHAR(64) NOT NULL,
    -- {accepted:int, rejected:int, warnings:int, total:int}
    parsed_summary JSONB NOT NULL,
    -- [{account_number, error_code, message, line_no}, ...]
    raw_errors JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_m2resp_tx ON metro2_responses(transmission_id);
CREATE INDEX IF NOT EXISTS idx_m2resp_received ON metro2_responses(received_at DESC);


-- ─── metro2_disputes ──────────────────────────────────────────────────────
-- Dispute intake and resolution tracking. One row per dispute event.
CREATE TABLE IF NOT EXISTS metro2_disputes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    record_id UUID REFERENCES metro2_records(id) ON DELETE SET NULL,
    bureau VARCHAR(20) NOT NULL DEFAULT 'experian'
        CHECK (bureau IN ('experian')),
    dispute_code VARCHAR(10),               -- Metro 2 Compliance Condition Code
    received_at TIMESTAMPTZ NOT NULL,
    resolution_status VARCHAR(20) NOT NULL DEFAULT 'open'
        CHECK (resolution_status IN ('open', 'investigating', 'resolved', 'closed')),
    resolved_at TIMESTAMPTZ,
    notes TEXT,
    linked_response_id UUID REFERENCES metro2_responses(id) ON DELETE SET NULL,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_m2disp_record ON metro2_disputes(record_id);
CREATE INDEX IF NOT EXISTS idx_m2disp_status ON metro2_disputes(resolution_status);
CREATE INDEX IF NOT EXISTS idx_m2disp_received ON metro2_disputes(received_at DESC);


-- ─── Triggers: updated_at auto-update ─────────────────────────────────────
-- Reuses the update_cr_updated_at() function installed by migration 006.

DROP TRIGGER IF EXISTS trigger_m2rec_updated_at ON metro2_records;
CREATE TRIGGER trigger_m2rec_updated_at
    BEFORE UPDATE ON metro2_records
    FOR EACH ROW EXECUTE FUNCTION update_cr_updated_at();

DROP TRIGGER IF EXISTS trigger_m2mapt_updated_at ON metro2_mapping_templates;
CREATE TRIGGER trigger_m2mapt_updated_at
    BEFORE UPDATE ON metro2_mapping_templates
    FOR EACH ROW EXECUTE FUNCTION update_cr_updated_at();

DROP TRIGGER IF EXISTS trigger_m2disp_updated_at ON metro2_disputes;
CREATE TRIGGER trigger_m2disp_updated_at
    BEFORE UPDATE ON metro2_disputes
    FOR EACH ROW EXECUTE FUNCTION update_cr_updated_at();


-- ─── Smoke check ──────────────────────────────────────────────────────────
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN (
    'metro2_records',
    'metro2_record_history',
    'metro2_mapping_templates',
    'metro2_upload_batches',
    'metro2_files',
    'metro2_transmissions',
    'metro2_responses',
    'metro2_disputes'
  )
ORDER BY table_name;
