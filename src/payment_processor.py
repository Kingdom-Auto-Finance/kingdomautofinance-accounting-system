# payment_processor.py
import os
import logging
from datetime import datetime, timedelta
from decimal import Decimal

import config
from amortization_calculator import calculate_principal_and_status
from supabase import create_client
from google.cloud import secretmanager

# -----------------------------
# Preserved configuration
# -----------------------------
TOLERANCE = Decimal('10.00')       # allow up to $10 shortfall
THRESHOLD_RATIO = Decimal('0.90')  # require at least 90% of installment
### EXTRA_TOLERANCE = Decimal('20.00')  # only open next installment if at least 20 extra
# (Changed to 50% of the next installment on 5/22/2025.)  # <-- preserved comment


# -----------------------------
# Payment Allocation Recording
# -----------------------------
def _record_allocation(sb, payment_log_id: str, loan_id: str, payment_date: str,
                       payment_number: int, principal_amt: Decimal,
                       interest_amt: Decimal, late_fee_amt: Decimal):
    """
    Record a payment allocation to the payment_allocations ledger.

    This preserves the original payment_date for cash-basis reporting,
    ensuring each payment appears in the correct month's report regardless
    of when it was processed or when the installment was fully paid.

    Args:
        sb: Supabase client
        payment_log_id: ID from payments_log table
        loan_id: Loan identifier
        payment_date: Original date payment was received (YYYY-MM-DD)
        payment_number: Which installment this allocation applies to
        principal_amt: Principal portion allocated from this payment
        interest_amt: Interest portion allocated from this payment
        late_fee_amt: Late fee portion allocated from this payment
    """
    try:
        # Use insert for an append-only audit trail
        sb.table("payment_allocations").insert({
            "payment_log_id": payment_log_id,
            "loan_id": loan_id,
            "payment_date": payment_date,
            "payment_number": payment_number,
            "principal_allocated": float(principal_amt),
            "interest_allocated": float(interest_amt),
            "late_fee_allocated": float(late_fee_amt),
        }).execute()
    except Exception as e:
        logger.warning(f"Failed to record allocation for payment {payment_log_id}: {e}")

logging.getLogger("supabase._client").setLevel(logging.WARNING)
logging.getLogger("postgrest.request_builder").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# -----------------------------
# Preserved client creation with ENV -> Secret Manager fallback
# -----------------------------
def _get_supabase_client():
    """
    Create Supabase client.

    PRESERVED:
      - Read SUPABASE_SERVICE_ROLE_KEY from environment.
      - If not present, fall back to Secret Manager.
      - If neither available, raise a clear error.
    """
    secret = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not secret:
        sm = secretmanager.SecretManagerServiceClient()
        try:
            secret = sm.access_secret_version(
                request={"name": config.SUPABASE_SERVICE_ROLE_SECRET_RESOURCE_NAME}
            ).payload.data.decode("utf-8")
        except Exception as e:
            raise RuntimeError("Missing SUPABASE_SERVICE_ROLE_KEY environment variable.") from e
    return create_client(config.SUPABASE_URL, secret)

_supabase = None

def _client():
    global _supabase
    if _supabase is None:
        _supabase = _get_supabase_client()
    return _supabase

# -----------------------------
# Main processor (business logic preserved)
# -----------------------------
def process_payments():
    """
    Processes unprocessed payments from payments_log, oldest first.
    """
    sb = _client()

    # --- CRITICAL FIX: PAGINATED FETCH ---
    # Fetch all unprocessed payments in a loop to bypass the 1,000-row limit.
    all_unprocessed_payments = []
    page_size = 1000  # The Supabase default limit
    offset = 0

    logger.info("Fetching all unprocessed payments in batches...")
    while True:
        try:
            resp = (
                sb.from_("payments_log")
                .select("id,loan_id,payment_date,payment_amount")
                .eq("processed", False)
                .order("payment_date")
                .limit(page_size)
                .range(offset, offset + page_size - 1)
                .execute()
            )
            payments_batch = resp.data or []
            if not payments_batch:
                # No more data to fetch, so break the loop
                break

            all_unprocessed_payments.extend(payments_batch)
            offset += page_size
            logger.info(f"Fetched a batch of {len(payments_batch)} payments. Total fetched so far: {len(all_unprocessed_payments)}.")

        except Exception as e:
            logger.error(f"Error fetching payments from Supabase: {e}")
            return False

    payments = all_unprocessed_payments
    if not payments:
        logger.info("No payments to process.")
        return True

    missing = []

    for payment in payments:
        pid = payment["id"]
        loan_id = payment["loan_id"]
        pay_date_str = payment["payment_date"]  # Format: YYYY-MM-DD

        # ----------------------------
        # NEW: Atomic claim of this payment row
        # ----------------------------
        claimed = False
        finalized = False
        claim = (
            sb.from_("payments_log")
              .update({
                  "processed": True,  # claim it
              })
              .eq("id", pid)
              .eq("processed", False)  # only if still unprocessed
              .execute()
        )
        claimed_rows = getattr(claim, "data", None) or []
        if len(claimed_rows) == 0:
            logger.info(f"Payment {pid}: already claimed/processed elsewhere; skipping.")
            continue
        claimed = True

        try:
            # Validate date and amount (PRESERVED)
            try:
                pay_dt = datetime.strptime(pay_date_str, "%Y-%m-%d").date()
            except ValueError:
                logger.error(f"Payment {pid}: invalid date '{pay_date_str}'")
                continue

            raw_amount = payment["payment_amount"]
            try:
                payment_amt = Decimal(str(raw_amount))
                if payment_amt <= 0:
                    logger.error(f"Payment {pid}: amount must be positive, got '{raw_amount}'")
                    continue
            except Exception:
                logger.error(f"Payment {pid}: invalid amount '{raw_amount}'")
                continue

            table = f"schedule_{loan_id}"

            # Step 2: Fetch amortization schedule rows (PRESERVED)
            try:
                sched = (
                    sb.from_(table)
                      .select(
                          "paymentnumber,duedate,scheduledbalance,adjustedbalance,scheduledpayment,"
                          "actualpaymentdate,actualpaymentamount,scheduledprincipal,scheduledinterest,"
                          "principalpaid,interestpaid,latefee,creditapplied,scheduledfinalbalance,"
                          "endingbalance,status"
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

            # Normalize cumulative fields to zero for unpaid/partial rows (PRESERVED)
            for row in sched:
                if not row.get("actualpaymentdate") or str(row.get("status", "")).upper() not in ("PAID",):
                    for field in ["interestpaid", "principalpaid", "latefee", "actualpaymentamount"]:
                        if not row.get(field) or str(row.get(field)).strip().lower() in ("", "none", "null"):
                            row[field] = 0.0

            # Step 3: Prepare for allocation (PRESERVED)
            allocation_done = False
            remaining_amt = payment_amt          # PRESERVED
            applied_total = Decimal('0.00')      # NEW: for reconciliation

            # Infer cadence → cap rows (PRESERVED)
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

            # Next unpaid/partial rows (PRESERVED)
            unpaid_rows = [
                (idx, row) for idx, row in enumerate(sched)
                if not row.get("actualpaymentdate") or str(row.get("status", "")).upper() not in ("PAID",)
            ]

            if not unpaid_rows:
                logger.info(f"Payment {pid}: all installments are paid for loan {loan_id}, treating as principal prepayment or extra.")
                continue

            # --- NEW: Curtailment rule (pre-next-due & > 2x scheduledpayment) ---
            # If the payment date is BEFORE the next unpaid due date, and the amount is > 2x that row's scheduledpayment,
            # then add this entire payment as EXTRA PRINCIPAL to the LAST PAID row.
            try:
                next_unpaid_row = unpaid_rows[0][1]  # the next due that is still unpaid
                next_due_dt = datetime.strptime(next_unpaid_row["duedate"], "%Y-%m-%d").date()
                scheduled_payment_due = Decimal(str(next_unpaid_row.get("scheduledpayment") or 0))
            except Exception:
                next_due_dt = None
                scheduled_payment_due = Decimal('0')

            if (
                next_due_dt
                and pay_dt < next_due_dt                          # actualpaymentdate is BEFORE the next unpaid due date
                and scheduled_payment_due > 0
                and payment_amt > (scheduled_payment_due * Decimal('2'))  # strictly bigger than 2x scheduledpayment
            ):
                # Find the LAST row already marked as PAID
                last_paid_row = None
                for r in reversed(sched):  # sched is ordered by paymentnumber
                    if str(r.get("status", "")).upper() == "PAID":
                        last_paid_row = r
                        break

                if last_paid_row:
                    last_rownum = last_paid_row["paymentnumber"]
                    extra_principal = float(payment_amt)  # the whole payment becomes extra principal on the last PAID row

                    # 1) Add to actualpaymentamount and principalpaid; 2) reduce ending/adjusted balance by the same amount
                    prepay_sql = f'''
                    UPDATE public."{table}"
                    SET
                        actualpaymentamount = ROUND((COALESCE(actualpaymentamount, 0)::numeric + {extra_principal}::numeric), 2),
                        principalpaid       = ROUND((COALESCE(principalpaid,       0)::numeric + {extra_principal}::numeric), 2),
                        endingbalance       = GREATEST(
                                                0,
                                                ROUND((
                                                    COALESCE(adjustedbalance, endingbalance, scheduledbalance, 0)::numeric
                                                    - {extra_principal}::numeric
                                                )::numeric, 2)
                                            ),
                        adjustedbalance     = GREATEST(
                                                0,
                                                ROUND((
                                                    COALESCE(adjustedbalance, endingbalance, scheduledbalance, 0)::numeric
                                                    - {extra_principal}::numeric
                                                )::numeric, 2)
                                            )
                        -- status intentionally unchanged
                    WHERE "paymentnumber" = {last_rownum};
                    '''
                    sb.rpc("run_sql", {"sql_text": prepay_sql}).execute()

                    # Keep the chain in sync: make the NEXT row start from this updated ending balance
                    next_rownum = last_rownum + 1
                    adj_sql = f'''
                    UPDATE public."{table}"
                    SET adjustedbalance = (
                        SELECT endingbalance FROM public."{table}" WHERE "paymentnumber" = {last_rownum}
                    )
                    WHERE "paymentnumber" = {next_rownum};
                    '''
                    sb.rpc("run_sql", {"sql_text": adj_sql}).execute()

                    # Record allocation for cash-basis reporting
                    _record_allocation(
                        sb=sb,
                        payment_log_id=pid,
                        loan_id=loan_id,
                        payment_date=pay_date_str,
                        payment_number=last_rownum,
                        principal_amt=payment_amt,  # Entire payment is principal (curtailment)
                        interest_amt=Decimal('0'),
                        late_fee_amt=Decimal('0')
                    )

                    # Bookkeeping so the payment finalizes cleanly (no further allocation)
                    allocation_done = True
                    payment_rows.append(last_rownum)
                    applied_total += payment_amt
                    remaining_amt = Decimal('0.00')
            # --- END NEW Curtailment rule ---

            # (PRESERVED) Fetch other unprocessed payments for this loan (even if not used)
            _ = (
                sb.from_("payments_log")
                  .select("id,payment_date,payment_amount")
                  .eq("loan_id", loan_id)
                  .eq("processed", False)
                  .order("payment_date")
                  .execute()
            ).data or []

            # Step 4: Allocate the payment (PRESERVED business logic)
            for n, (idx, row) in enumerate(unpaid_rows):
                if n >= max_rows or remaining_amt <= 0:
                    break  # Do not allocate to more than the max allowed

                # Prepare scheduled values (PRESERVED)
                due_dt = datetime.strptime(row["duedate"], "%Y-%m-%d").date()
                scheduled_balance = Decimal(str(row.get("scheduledbalance") or 0.0))
                adjusted_balance  = Decimal(str(row.get("adjustedbalance")  or 0.0))
                bb = adjusted_balance if str(row.get("adjustedbalance")).strip().lower() not in ("", "none", "null") and row.get("adjustedbalance") is not None else scheduled_balance
                scheduled_interest = Decimal(str(row.get("scheduledinterest") or 0.0))
                scheduled_principal = Decimal(str(row.get("scheduledprincipal") or 0.0))
                scheduled_due = scheduled_interest + scheduled_principal
                prev_principal_paid = Decimal(str(row.get("principalpaid") or 0.0))
                prev_latefee = Decimal(str(row.get("latefee") or 0.0))
                prev_actual_paid = Decimal(str(row.get("actualpaymentamount") or 0.0))

                # Grace/late fee (PRESERVED)
                grace_end = due_dt + timedelta(days=config.DEFAULT_GRACE_PERIOD_DAYS)
                if prev_latefee > 0 or pay_dt <= grace_end:
                    fee_to_apply = Decimal('0')
                else:
                    fee_to_apply = config.DEFAULT_LATE_FEE

                cumulative_paid = prev_actual_paid + remaining_amt

                # PRESERVED: threshold/tolerance logic with dynamic extra rule
                if cumulative_paid + TOLERANCE >= scheduled_due or cumulative_paid >= scheduled_due * THRESHOLD_RATIO:
                    extra = cumulative_paid - scheduled_due

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

                    # PRESERVED: your exact decision condition
                    if (n == len(unpaid_rows) - 1) or (
                        n < len(unpaid_rows) - 1
                        and (cumulative_paid + TOLERANCE >= scheduled_due or cumulative_paid >= scheduled_due * THRESHOLD_RATIO)
                        and extra < dynamic_extra_tolerance
                    ):
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
                        logger.error(f"Payment {pid}: calculation failed on installment {row['paymentnumber']}")
                        continue

                    total_interest_paid = Decimal(str(result.get("InterestPaid", 0)))
                    total_latefee_paid = Decimal(str(result.get("LateFee", 0)))
                    new_actual_paid = cumulative_total_paid
                    new_interest_paid = total_interest_paid
                    new_latefee = total_latefee_paid
                    new_principal_paid = new_actual_paid - new_interest_paid - new_latefee

                    # Recompute ending balance and status the same way (IF branch)
                    ending_bal = bb - new_principal_paid
                    new_status = "PAID" if (new_actual_paid + TOLERANCE >= scheduled_due or new_actual_paid >= scheduled_due * THRESHOLD_RATIO) else "PARTIAL"

                    # UPDATE SQL (same structure as below-threshold branch)
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
                    sb.rpc("run_sql", {"sql_text": sql}).execute()

                    # Carry ending balance forward as adjustedbalance (same as below-threshold branch)
                    next_paymentnumber = row["paymentnumber"] + 1
                    adj_sql = f'''
                    UPDATE public."{table}"
                    SET
                        adjustedbalance = {float(ending_bal)}
                    WHERE
                    "paymentnumber" = {next_paymentnumber};
                    '''
                    sb.rpc("run_sql", {"sql_text": adj_sql}).execute()

                    # Record allocation for cash-basis reporting
                    # Calculate the INCREMENTAL amounts (what THIS payment contributed)
                    prev_interest_paid = Decimal(str(row.get("interestpaid") or 0))
                    incremental_principal = new_principal_paid - prev_principal_paid
                    incremental_interest = new_interest_paid - prev_interest_paid
                    incremental_latefee = new_latefee - prev_latefee

                    _record_allocation(
                        sb=sb,
                        payment_log_id=pid,
                        loan_id=loan_id,
                        payment_date=pay_date_str,
                        payment_number=row['paymentnumber'],
                        principal_amt=incremental_principal,
                        interest_amt=incremental_interest,
                        late_fee_amt=incremental_latefee
                    )

                    allocation_done = True
                    payment_rows.append(row['paymentnumber'])
                    applied_total += apply_amt
                    remaining_amt -= apply_amt

                else:
                    # Safe partial path: allocate below threshold with the same calculation steps
                    apply_amt = remaining_amt
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
                        logger.error(f"Payment {pid}: calculation failed on installment {row['paymentnumber']}")
                        continue

                    total_interest_paid = Decimal(str(result.get("InterestPaid", 0)))
                    total_latefee_paid = Decimal(str(result.get("LateFee", 0)))
                    new_actual_paid = cumulative_total_paid
                    new_interest_paid = total_interest_paid
                    new_latefee = total_latefee_paid
                    new_principal_paid = new_actual_paid - new_interest_paid - new_latefee

                    # Recompute ending balance and status the same way
                    ending_bal = bb - new_principal_paid
                    new_status = "PAID" if (new_actual_paid + TOLERANCE >= scheduled_due or new_actual_paid >= scheduled_due * THRESHOLD_RATIO) else "PARTIAL"

                    # UPDATE SQL (identical structure as the IF branch)
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
                    sb.rpc("run_sql", {"sql_text": sql}).execute()

                    # Carry ending balance forward as adjustedbalance (same as IF branch)
                    next_paymentnumber = row["paymentnumber"] + 1
                    adj_sql = f'''
                    UPDATE public."{table}"
                    SET
                        adjustedbalance = {float(ending_bal)}
                    WHERE
                    "paymentnumber" = {next_paymentnumber};
                    '''
                    sb.rpc("run_sql", {"sql_text": adj_sql}).execute()

                    # Record allocation for cash-basis reporting
                    # Calculate the INCREMENTAL amounts (what THIS payment contributed)
                    prev_interest_paid = Decimal(str(row.get("interestpaid") or 0))
                    incremental_principal = new_principal_paid - prev_principal_paid
                    incremental_interest = new_interest_paid - prev_interest_paid
                    incremental_latefee = new_latefee - prev_latefee

                    _record_allocation(
                        sb=sb,
                        payment_log_id=pid,
                        loan_id=loan_id,
                        payment_date=pay_date_str,
                        payment_number=row['paymentnumber'],
                        principal_amt=incremental_principal,
                        interest_amt=incremental_interest,
                        late_fee_amt=incremental_latefee
                    )

                    allocation_done = True
                    payment_rows.append(row['paymentnumber'])
                    applied_total += apply_amt
                    remaining_amt -= apply_amt

                # Enforce 50% rule stop (PRESERVED)
                if (cumulative_paid + TOLERANCE >= scheduled_due or cumulative_paid >= scheduled_due * THRESHOLD_RATIO):
                    try:
                        extra  # may be undefined in below-threshold branch
                    except NameError:
                        extra = Decimal('0')
                    try:
                        dynamic_extra_tolerance
                    except NameError:
                        dynamic_extra_tolerance = Decimal('0')
                    if n < len(unpaid_rows) - 1 and extra < dynamic_extra_tolerance:
                        break

            # If there is leftover money, post ALL of it as extra principal
            # on the LAST row we updated, then sync ONLY the next row's start.
            if allocation_done and remaining_amt > 0:
                last_rownum = payment_rows[-1]
                extra_principal = float(remaining_amt)

                # Post the remainder as extra principal to the last touched row
                prepay_sql = f'''
                UPDATE public."{table}"
                SET
                    actualpaymentamount = ROUND((COALESCE(actualpaymentamount, 0)::numeric + {extra_principal}::numeric), 2),
                    principalpaid       = ROUND((COALESCE(principalpaid,       0)::numeric + {extra_principal}::numeric), 2),
                    endingbalance       = GREATEST(
                                            0,
                                            ROUND((
                                                COALESCE(adjustedbalance, endingbalance, scheduledbalance, 0)::numeric
                                                - {extra_principal}::numeric
                                            )::numeric, 2)
                                        ),
                    -- keep adjusted in sync with the same new ending (for this row)
                    adjustedbalance     = GREATEST(
                                            0,
                                            ROUND((
                                                COALESCE(adjustedbalance, endingbalance, scheduledbalance, 0)::numeric
                                                - {extra_principal}::numeric
                                            )::numeric, 2)
                                        )
                WHERE "paymentnumber" = {last_rownum};
                '''
                sb.rpc("run_sql", {"sql_text": prepay_sql}).execute()

                # Sync ONLY the next row's starting balance to this row's new ending
                next_rownum = last_rownum + 1
                adj_sql = f'''
                UPDATE public."{table}" AS nxt
                SET adjustedbalance = (
                    SELECT endingbalance FROM public."{table}" WHERE "paymentnumber" = {last_rownum}
                )
                WHERE nxt."paymentnumber" = {next_rownum};
                '''
                sb.rpc("run_sql", {"sql_text": adj_sql}).execute()

                # Record the extra principal allocation for cash-basis reporting
                _record_allocation(
                    sb=sb,
                    payment_log_id=pid,
                    loan_id=loan_id,
                    payment_date=pay_date_str,
                    payment_number=last_rownum,
                    principal_amt=remaining_amt,  # Entire leftover is principal
                    interest_amt=Decimal('0'),
                    late_fee_amt=Decimal('0')
                )

                # Reconciliation counters
                applied_total += remaining_amt
                remaining_amt = Decimal('0.00')

            # ----------------------------
            # NEW: Reconciliation check
            # ----------------------------
            if allocation_done:
                if abs(applied_total - payment_amt) > Decimal('0.01'):
                    logger.error(
                        f"Payment {pid}: applied_total ({float(applied_total)}) != payment_amt ({float(payment_amt)}). "
                        f"Leaving as unprocessed for review."
                    )
                    continue  # finally will revert the claim

                # Finalize: already processed=True from claim; just (re)stamp processed_at
                sb.from_("payments_log").update({
                    "processed": True,   # enforce final state
                    "processed_at": datetime.utcnow().isoformat()
                }).eq("id", pid).execute()

                logger.info(
                    f"Payment {pid}: payment of {float(payment_amt)} allocated across rows {payment_rows}"
                )
                finalized = True
            else:
                logger.info(f"Payment {pid}: no allocation done, leaving unprocessed")

        finally:
            # If claimed but not finalized, revert the claim so it can be safely retried
            if claimed and not finalized:
                sb.from_("payments_log").update({
                    "processed": False,
                    "processed_at": None
                }).eq("id", pid).execute()

    # Report missing schedules (PRESERVED)
    for lid in sorted(set(missing)):
        print(f"The {lid} doesn't have an amortization schedule yet.")

    return True


if __name__ == '__main__':
    process_payments()