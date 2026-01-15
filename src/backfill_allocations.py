"""
Backfill script to populate payment_allocations from historical data.

This script reconstructs payment allocations from existing payments_log entries
by looking at the schedule tables to determine how each payment was allocated.

The key insight is that payments_log preserves the original payment_date,
so we can reconstruct the correct allocation dates even for partial payments
that were overwritten in the schedule tables.

Usage:
    python src/backfill_allocations.py [--dry-run]

Options:
    --dry-run    Show what would be inserted without actually inserting
"""

import os
import sys
import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from supabase import create_client

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_supabase_client():
    """Create Supabase client."""
    secret = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not secret:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY environment variable is required")
    return create_client(config.SUPABASE_URL, secret)


def fetch_all_processed_payments(supabase) -> List[Dict]:
    """Fetch all processed payments from payments_log."""
    all_payments = []
    page_size = 1000
    offset = 0

    logger.info("Fetching all processed payments from payments_log...")

    while True:
        result = (
            supabase.table("payments_log")
            .select("id, loan_id, payment_date, payment_amount")
            .eq("processed", True)
            .order("payment_date")
            .range(offset, offset + page_size - 1)
            .execute()
        )

        if not result.data:
            break

        all_payments.extend(result.data)

        if len(result.data) < page_size:
            break

        offset += page_size

    logger.info(f"Found {len(all_payments)} processed payments")
    return all_payments


def fetch_schedule_for_loan(supabase, loan_id: str) -> Optional[List[Dict]]:
    """Fetch the schedule for a specific loan."""
    try:
        table_name = f"schedule_{loan_id}"
        result = (
            supabase.table(table_name)
            .select("paymentnumber, duedate, scheduledinterest, scheduledprincipal, "
                    "actualpaymentdate, principalpaid, interestpaid, latefee, status")
            .order("paymentnumber")
            .execute()
        )
        return result.data or []
    except Exception as e:
        if 'does not exist' in str(e) or '42P01' in str(e):
            return None
        logger.warning(f"Failed to fetch schedule for loan {loan_id}: {e}")
        return None


def calculate_allocation_for_payment(
    payment_amount: Decimal,
    scheduled_interest: Decimal,
    scheduled_principal: Decimal,
    late_fee: Decimal
) -> Tuple[Decimal, Decimal, Decimal]:
    """
    Calculate how a payment should be allocated.

    Allocation priority: Interest -> Late Fee -> Principal

    Returns: (interest_allocated, late_fee_allocated, principal_allocated)
    """
    remaining = payment_amount

    # First: allocate to interest
    interest_allocated = min(remaining, scheduled_interest)
    remaining -= interest_allocated

    # Second: allocate to late fee
    late_fee_allocated = min(remaining, late_fee)
    remaining -= late_fee_allocated

    # Third: remainder goes to principal
    principal_allocated = remaining

    return interest_allocated, late_fee_allocated, principal_allocated


def reconstruct_allocations_for_loan(
    supabase,
    loan_id: str,
    payments: List[Dict]
) -> List[Dict]:
    """
    Reconstruct allocation records for a single loan.

    This is a simplified reconstruction that:
    1. Looks at the schedule to understand the installment structure
    2. For each payment, estimates which installment(s) it was applied to
    3. Calculates the interest/principal split based on scheduled amounts
    """
    schedule = fetch_schedule_for_loan(supabase, loan_id)
    if not schedule:
        logger.warning(f"No schedule found for loan {loan_id}, skipping {len(payments)} payments")
        return []

    allocations = []

    # Sort payments by date
    sorted_payments = sorted(payments, key=lambda p: p["payment_date"])

    # Track cumulative paid per installment
    installment_paid: Dict[int, Decimal] = {}

    for payment in sorted_payments:
        payment_id = payment["id"]
        payment_date = payment["payment_date"]
        payment_amount = Decimal(str(payment["payment_amount"]))

        remaining = payment_amount

        # Find installments that could receive this payment
        # (rows with actualpaymentdate matching or close to payment_date, or unpaid rows)
        for row in schedule:
            if remaining <= 0:
                break

            payment_number = row["paymentnumber"]
            scheduled_interest = Decimal(str(row.get("scheduledinterest") or 0))
            scheduled_principal = Decimal(str(row.get("scheduledprincipal") or 0))
            scheduled_total = scheduled_interest + scheduled_principal

            # Get cumulative paid so far for this installment
            cumulative = installment_paid.get(payment_number, Decimal('0'))

            # Calculate how much more this installment needs
            needed = scheduled_total - cumulative
            if needed <= 0:
                continue

            # Allocate up to what's needed
            to_allocate = min(remaining, needed)

            # Calculate interest/principal split
            # First cover interest, then principal
            interest_remaining = max(Decimal('0'), scheduled_interest - cumulative)
            interest_allocated = min(to_allocate, interest_remaining)

            principal_allocated = to_allocate - interest_allocated

            # Late fee (check if row has late fee that hasn't been covered)
            row_latefee = Decimal(str(row.get("latefee") or 0))
            late_fee_allocated = Decimal('0')

            if to_allocate > 0:
                allocations.append({
                    "payment_log_id": payment_id,
                    "loan_id": loan_id,
                    "payment_date": payment_date,
                    "payment_number": payment_number,
                    "principal_allocated": float(principal_allocated),
                    "interest_allocated": float(interest_allocated),
                    "late_fee_allocated": float(late_fee_allocated),
                })

                # Update cumulative
                installment_paid[payment_number] = cumulative + to_allocate
                remaining -= to_allocate

        # If there's remaining amount, it might be extra principal on the last touched row
        if remaining > 0 and allocations:
            last_alloc = allocations[-1]
            last_alloc["principal_allocated"] = float(
                Decimal(str(last_alloc["principal_allocated"])) + remaining
            )

    return allocations


def backfill_allocations(dry_run: bool = False):
    """
    Main backfill function.

    Reconstructs payment_allocations from historical payments_log data.
    """
    supabase = get_supabase_client()

    # First, check if payment_allocations table exists and is empty
    try:
        existing = supabase.table("payment_allocations").select("id").limit(1).execute()
        if existing.data:
            logger.warning(
                f"payment_allocations table already has data. "
                f"Run with --force to clear and rebuild (not implemented yet). "
                f"Or manually truncate the table first."
            )
            return
    except Exception as e:
        logger.error(f"payment_allocations table may not exist. Run the migration first: {e}")
        return

    # Fetch all processed payments
    payments = fetch_all_processed_payments(supabase)

    if not payments:
        logger.info("No processed payments found. Nothing to backfill.")
        return

    # Group payments by loan_id
    payments_by_loan: Dict[str, List[Dict]] = {}
    for payment in payments:
        loan_id = payment["loan_id"]
        if loan_id not in payments_by_loan:
            payments_by_loan[loan_id] = []
        payments_by_loan[loan_id].append(payment)

    logger.info(f"Processing {len(payments)} payments across {len(payments_by_loan)} loans")

    # Process each loan
    all_allocations = []
    for loan_id, loan_payments in payments_by_loan.items():
        logger.info(f"Processing loan {loan_id} with {len(loan_payments)} payments")
        allocations = reconstruct_allocations_for_loan(supabase, loan_id, loan_payments)
        all_allocations.extend(allocations)

    logger.info(f"Reconstructed {len(all_allocations)} allocation records")

    if dry_run:
        logger.info("DRY RUN - Would insert the following allocations:")
        for alloc in all_allocations[:10]:  # Show first 10
            logger.info(f"  {alloc}")
        if len(all_allocations) > 10:
            logger.info(f"  ... and {len(all_allocations) - 10} more")
        return

    # Insert allocations in batches
    batch_size = 100
    inserted = 0

    for i in range(0, len(all_allocations), batch_size):
        batch = all_allocations[i:i + batch_size]
        try:
            supabase.table("payment_allocations").insert(batch).execute()
            inserted += len(batch)
            logger.info(f"Inserted {inserted}/{len(all_allocations)} allocations")
        except Exception as e:
            logger.error(f"Failed to insert batch starting at index {i}: {e}")
            # Continue with next batch

    logger.info(f"Backfill complete. Inserted {inserted} allocation records.")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        logger.info("Running in DRY RUN mode - no data will be inserted")

    backfill_allocations(dry_run=dry_run)
