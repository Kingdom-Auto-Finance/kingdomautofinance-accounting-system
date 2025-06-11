import logging
from datetime import datetime, timedelta
from decimal import Decimal

import config
from amortization_calculator import calculate_principal_and_status
from supabase import create_client

# Tolerance for Payments
TOLERANCE = Decimal('10.00')       # allow up to $10 shortfall
THRESHOLD_RATIO = Decimal('0.90')  # require at least 90% of installment
### EXTRA_TOLERANCE = Decimal('20.00')  # only open next installment if at least $20 extra // Changed to 50% of the next installment on 5/22/2025.

# Suppress verbose Supabase/PostgREST HTTP logs for clarity
logging.getLogger("supabase._client").setLevel(logging.WARNING)
logging.getLogger("postgrest.request_builder").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

import os

def _get_supabase_client():
    secret = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not secret:
        raise RuntimeError("Missing SUPABASE_SERVICE_ROLE_KEY environment variable.")
    return create_client(config.SUPABASE_URL, secret)

_supabase = None

def _client():
    global _supabase
    if _supabase is None:
        _supabase = _get_supabase_client()
    return _supabase

def process_payments():
    """
    Processes unprocessed payments from payments_log, oldest first.
    Best Practice/Professional allocation:
      - Allocate each payment to up to MAX_FORWARD_INSTALLMENTS rows.
      - Each covered row receives its share of the payment (actualpaymentamount).
      - Each row's interest and principal are calculated for actual payment date (early/late payments are handled).
      - If payment exceeds cap, excess is principal prepayment on the last covered row.
    No other code or logic is changed.
    """
    sb = _client()

    # Step 1: Fetch all unprocessed payments, ordered by payment_date ascending
    resp = (
        sb.from_("payments_log")
          .select("id,loan_id,payment_date,payment_amount")
          .eq("processed", False)
          .order("payment_date")
          .execute()
    )
    payments = resp.data or []
    if not payments:
        logger.info("No payments to process.")
        return True

    missing = []

    for payment in payments:
        pid = payment["id"]
        loan_id = payment["loan_id"]
        pay_date_str = payment["payment_date"]  # Format: YYYY-MM-DD

        # Validate payment date
        try:
            pay_dt = datetime.strptime(pay_date_str, "%Y-%m-%d").date()
        except ValueError:
            logger.error(f"Payment {pid}: invalid date '{pay_date_str}'")
            continue

        # Validate payment amount
        raw_amount = payment["payment_amount"]
        try:
            payment_amt = Decimal(str(raw_amount))
            if payment_amt <= 0:
                logger.error(f"Payment {pid}: amount must be positive, got '{raw_amount}'")
                continue
        except Exception:
            logger.error(f"Payment {pid}: invalid amount '{raw_amount}'")
            continue

        # *** NEW: initialize remaining bucket for this payment ***
        remaining_amt = payment_amt

        table = f"schedule_{loan_id}"

        # Step 2: Fetch amortization schedule rows for this loan
        try:
            sched = (
                sb.from_(table)
                  .select(
                      "paymentnumber,duedate,scheduledbalance,adjustedbalance,scheduledpayment,actualpaymentdate,actualpaymentamount,scheduledprincipal,scheduledinterest,principalpaid,interestpaid,"
                      "latefee,creditapplied,scheduledfinalbalance,endingbalance,status"
                  )
                  .order("paymentnumber")
                  .execute().data or []
            )
        except Exception as e:
            err = str(e)
            if 'does not exist' in err or '42P01' in err:
                missing.append(loan_id)
                continue
            logger.error(f"Payment {pid}: cannot fetch {table}: {e}")
            continue

        if not sched:
            logger.warning(f"Payment {pid}: no schedule found for {table}")
            continue

        # --- Normalize cumulative fields to zero for all unpaid/partially paid rows ---
        for row in sched:
            if not row.get("actualpaymentdate") or str(row.get("status", "")).upper() not in ("PAID",):
                for field in ["interestpaid", "principalpaid", "latefee", "actualpaymentamount"]:
                    # If field is None, blank, 'null', or 'None', set to 0.0 (as float, to match your later code)
                    if not row.get(field) or str(row.get(field)).strip().lower() in ("", "none", "null"):
                        row[field] = 0.0

        # Step 3: Prepare for allocation
        allocation_done = False
        
        # --- Dynamically set max_rows based on payment frequency inferred from due date intervals ---
        schedule_due_dates = [datetime.strptime(row["duedate"], "%Y-%m-%d").date() for row in sched[:3] if row.get("duedate")]
        if len(schedule_due_dates) >= 2:
            interval_1 = (schedule_due_dates[1] - schedule_due_dates[0]).days
            interval_2 = (schedule_due_dates[2] - schedule_due_dates[1]).days if len(schedule_due_dates) > 2 else interval_1
            if 27 <= interval_1 <= 32 and 27 <= interval_2 <= 32:
                max_rows = 1  # Monthly
            elif 13 <= interval_1 <= 15 and 13 <= interval_2 <= 15:
                max_rows = 2  # Biweekly or Semi-monthly
            elif 6 <= interval_1 <= 8 and 6 <= interval_2 <= 8:
                max_rows = 2  # Weekly
            else:
                max_rows = config.MAX_FORWARD_INSTALLMENTS
        else:
            max_rows = config.MAX_FORWARD_INSTALLMENTS

        payment_rows = []

        # Find next unpaid/partially paid rows in schedule (oldest first)
        unpaid_rows = [
            (idx, row) for idx, row in enumerate(sched)
            if not row.get("actualpaymentdate") or str(row.get("status", "")).upper() not in ("PAID",)
        ]

        if not unpaid_rows:
            logger.info(f"Payment {pid}: all installments are paid for loan {loan_id}, treating as principal prepayment or extra.")
            continue

        # Fetch all unprocessed payments for this loan (outside the loop over unpaid_rows)
        all_unprocessed = (
            sb.from_("payments_log")
              .select("id,payment_date,payment_amount")
              .eq("loan_id", loan_id)
              .eq("processed", False)
              .order("payment_date")
              .execute()
        ).data or []

        # Step 4: Allocate the payment, row by row (up to max cap)
        for n, (idx, row) in enumerate(unpaid_rows):
            if n >= max_rows or remaining_amt <= 0:
                break  # Do not allocate to more than the max allowed

            # Prepare all scheduled values for this row
            due_dt = datetime.strptime(row["duedate"], "%Y-%m-%d").date()
            bb = Decimal(str(row.get("scheduledbalance") or 0.0))
            scheduled_interest = Decimal(str(row.get("scheduledinterest") or 0.0))
            scheduled_principal = Decimal(str(row.get("scheduledprincipal") or 0.0))
            scheduled_due = scheduled_interest + scheduled_principal
            prev_principal_paid = Decimal(str(row.get("principalpaid") or 0.0))
            prev_latefee = Decimal(str(row.get("latefee") or 0.0))
            prev_actual_paid = Decimal(str(row.get("actualpaymentamount") or 0.0))

            # Grace period and late fee logic
            grace_end = due_dt + timedelta(days=config.DEFAULT_GRACE_PERIOD_DAYS)
            if prev_latefee > 0 or pay_dt <= grace_end:
                fee_to_apply = Decimal('0')
            else:
                fee_to_apply = config.DEFAULT_LATE_FEE

            # Determine cumulative amount already paid (previously + this payment)
            cumulative_paid = prev_actual_paid + remaining_amt

            # Apply tolerances and thresholds using cumulative payments
            if cumulative_paid + TOLERANCE >= scheduled_due or cumulative_paid >= scheduled_due * THRESHOLD_RATIO:
                extra = cumulative_paid - scheduled_due

                # Check gap to next installment …
                if n < len(unpaid_rows) - 1:
                    next_row = unpaid_rows[n + 1][1]
                    next_due_date = datetime.strptime(next_row["duedate"], "%Y-%m-%d").date()
                    days_until_next = (next_due_date - due_dt).days

                    if 27 <= days_until_next <= 32:
                        dynamic_extra_tolerance = Decimal('Infinity')
                    else:
                        next_scheduled_interest = Decimal(str(next_row.get("scheduledinterest") or 0.0))
                        next_scheduled_principal = Decimal(str(next_row.get("scheduledprincipal") or 0.0))
                        next_scheduled_due = next_scheduled_interest + next_scheduled_principal
                        dynamic_extra_tolerance = next_scheduled_due * Decimal('0.50')
                else:
                    dynamic_extra_tolerance = Decimal('0.00')

                # If this is the last row to be allocated due to 50% rule, apply all remaining_amt.
                if (n == len(unpaid_rows) - 1) or (
                    n < len(unpaid_rows) - 1
                    and (cumulative_paid + TOLERANCE >= scheduled_due or cumulative_paid >= scheduled_due * THRESHOLD_RATIO)
                    and extra < dynamic_extra_tolerance
                ):
                    # This is the last allocation for this payment (either last row, or stopping by the 50% rule)
                    apply_amt = remaining_amt
                else:
                    needed_to_close = scheduled_due - prev_actual_paid
                    apply_amt = min(remaining_amt, needed_to_close)

                cumulative_total_paid = prev_actual_paid + apply_amt

                result = calculate_principal_and_status(
                    beginning_balance_float=float(bb),
                    interest_paid_prefilled_float=float(scheduled_interest),
                    actual_payment_amount_float=float(cumulative_total_paid),
                    due_date_str=row["duedate"],
                    actual_payment_date_str=pay_date_str,
                    grace_period_days=config.DEFAULT_GRACE_PERIOD_DAYS,
                    late_fee_amount_flat=fee_to_apply
                )
                if not result:
                    logger.error(
                        f"Payment {pid}: calculation failed on installment {row['paymentnumber']}"
                    )
                    continue

                total_interest_paid = Decimal(str(result.get("InterestPaid", 0)))
                total_latefee_paid = Decimal(str(result.get("LateFee", 0)))
                new_actual_paid = cumulative_total_paid
                new_interest_paid = total_interest_paid
                new_latefee = total_latefee_paid
                new_principal_paid = new_actual_paid - new_interest_paid - new_latefee


            # Always recalc ending balance as scheduledbalance - total principal paid (cumulative)
            ending_bal = bb - new_principal_paid

            # Status = PAID if paid within tolerance/threshold, otherwise PARTIAL
            new_status = "PAID" if (new_actual_paid + TOLERANCE >= scheduled_due or new_actual_paid >= scheduled_due * THRESHOLD_RATIO) else "PARTIAL"

            # Build and execute SQL to update this row
            sql = f'''
UPDATE public."{table}"
SET
    actualpaymentdate = {repr(pay_date_str)},
    actualpaymentamount = {float(new_actual_paid)},
    principalpaid = {float(new_principal_paid)},
    interestpaid = {float(new_interest_paid)},
    latefee = {float(new_latefee)},
    endingbalance = {float(ending_bal)},
    status = '{new_status}'
WHERE
    "paymentnumber" = {row['paymentnumber']};
'''
            upd = sb.rpc("run_sql", {"sql_text": sql}).execute()
            if hasattr(upd, 'error') and upd.error:
                logger.error(
                    f"Payment {pid}: failed updating installment {row['paymentnumber']}: {upd.error}"
                )
                continue

            # Also update the next installment with this ending balance as adjustedbalance
            next_paymentnumber = row["paymentnumber"] + 1
            adj_sql = f'''
            UPDATE public."{table}"
            SET
                adjustedbalance = {float(ending_bal)}
            WHERE
               "paymentnumber" = {next_paymentnumber};
            '''
            sb.rpc("run_sql", {"sql_text": adj_sql}).execute()

            # *** Modified: drain the bucket, break only when empty or by 50%-rule ***
            payment_rows.append(row['paymentnumber'])
            remaining_amt -= apply_amt  # Deduct what was just applied

            # stop if we truly ran out of money
            if remaining_amt <= 0:
                allocation_done = True
                break

            # =========================
            # ENFORCE 50% RULE HERE
            # =========================
            # If extra is less than the required threshold for the next row, stop further allocation
            if (cumulative_paid + TOLERANCE >= scheduled_due or cumulative_paid >= scheduled_due * THRESHOLD_RATIO):
                if n < len(unpaid_rows) - 1 and extra < dynamic_extra_tolerance:
                    allocation_done = True
                    break
            # =========================

        # Step 5: Mark payment processed only if at least one row was updated
        if allocation_done:
            sb.from_("payments_log").update({
                "processed": True,
                "processed_at": datetime.utcnow().isoformat()
            }).eq("id", pid).execute()

            logger.info(
                f"Payment {pid}: payment of {float(payment_amt)} allocated across rows {payment_rows}"
            )
        else:
            logger.info(f"Payment {pid}: no allocation done, leaving unprocessed")

    # Report missing schedules if any
    for lid in sorted(set(missing)):
        print(f"The {lid} doesn't have an amortization schedule yet.")

    return True

if __name__ == '__main__':
    process_payments()
