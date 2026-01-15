-- Migration: Payment Allocations Ledger
-- Description: Creates payment_allocations table for cash-basis reporting
-- Date: 2026-01-15
--
-- Purpose: This table records each payment's allocation breakdown at the time
-- of processing, preserving the original payment_date for accurate cash-basis
-- reporting. This solves the issue where partial payments spanning month
-- boundaries would appear in the wrong month's report.

-- Payment allocations ledger
CREATE TABLE IF NOT EXISTS payment_allocations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Link to original payment in payments_log
    payment_log_id UUID REFERENCES payments_log(id) ON DELETE SET NULL,

    -- Loan identifier
    loan_id VARCHAR(50) NOT NULL,

    -- The actual date money was received (from bank/Google Sheets)
    -- This is the key field - it NEVER gets overwritten, ensuring
    -- payments appear in the correct month's report
    payment_date DATE NOT NULL,

    -- Which installment (payment number) this allocation applies to
    payment_number INT NOT NULL,

    -- Allocation breakdown at time of processing
    -- These represent what THIS specific payment contributed
    principal_allocated DECIMAL(12,2) DEFAULT 0.00,
    interest_allocated DECIMAL(12,2) DEFAULT 0.00,
    late_fee_allocated DECIMAL(12,2) DEFAULT 0.00,
    total_allocated DECIMAL(12,2) GENERATED ALWAYS AS (
        principal_allocated + interest_allocated + late_fee_allocated
    ) STORED,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Prevent duplicate allocations for the same payment/installment combo
    UNIQUE(payment_log_id, payment_number)
);

-- Indexes for efficient reporting queries
CREATE INDEX IF NOT EXISTS idx_payment_allocations_date
    ON payment_allocations(payment_date);

CREATE INDEX IF NOT EXISTS idx_payment_allocations_loan_date
    ON payment_allocations(loan_id, payment_date);

CREATE INDEX IF NOT EXISTS idx_payment_allocations_payment_log
    ON payment_allocations(payment_log_id);

CREATE INDEX IF NOT EXISTS idx_payment_allocations_date_range
    ON payment_allocations(payment_date, loan_id);

-- Comment for documentation
COMMENT ON TABLE payment_allocations IS
    'Ledger tracking each payment allocation with preserved original payment_date for cash-basis reporting. '
    'Solves the partial payment month boundary issue where actualpaymentdate in schedule tables gets overwritten.';

COMMENT ON COLUMN payment_allocations.payment_date IS
    'Original date payment was received by bank (from payments_log). Never overwritten.';

COMMENT ON COLUMN payment_allocations.total_allocated IS
    'Auto-calculated sum of principal + interest + late_fee allocations.';
