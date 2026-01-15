-- Migration: 005_audit_trail_fix.sql
-- Description: Removes unique constraint on payment_allocations to allow for an append-only audit trail
-- and adds indexes for reporting performance.

-- 1. Remove the unique constraint that enforced one record per payment installment
-- This allows multiple allocation records (e.g., regular payment + extra principal) for a single payment.
ALTER TABLE payment_allocations 
DROP CONSTRAINT IF EXISTS payment_allocations_payment_log_id_payment_number_key;

-- 2. Add performance indexes for the Audit and Reporting pages
-- Index by payment_log_id for quick summation of allocations per transaction
CREATE INDEX IF NOT EXISTS idx_payment_allocations_log_id 
ON payment_allocations(payment_log_id);

-- Index by date and loan_id for efficient monthly/filtered reporting
CREATE INDEX IF NOT EXISTS idx_payment_allocations_date_loan 
ON payment_allocations(payment_date, loan_id);

-- Add a comment to the table to document the append-only nature
COMMENT ON TABLE payment_allocations IS 'Immutable ledger of payment allocations. Supports multiple entries per payment transaction for a full audit trail.';
