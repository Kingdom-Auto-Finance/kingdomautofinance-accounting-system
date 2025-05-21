import logging
from datetime import datetime
from decimal import Decimal

import config
from amortization_calculator import calculate_principal_and_status
from supabase import create_client
from google.cloud import secretmanager

# Suppress verbose Supabase/PostgREST HTTP logs
logging.getLogger("supabase._client").setLevel(logging.WARNING)
logging.getLogger("postgrest.request_builder").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

def _get_supabase_client():
    """Create Supabase client with service-role key from Secret Manager."""
    sm = secretmanager.SecretManagerServiceClient()
    secret = sm.access_secret_version(
        request={"name": config.SUPABASE_SERVICE_ROLE_SECRET_RESOURCE_NAME}
    ).payload.data.decode("utf-8")
    return create_client(config.SUPABASE_URL, secret)

_supabase = None

def _client():
    global _supabase
    if _supabase is None:
        _supabase = _get_supabase_client()
    return _supabase

def process_payments():
    """
    Process each unprocessed payment from payments_log, oldest first.
    For each payment, update exactly one schedule_<loan_id> row:
      - the next unpaid installment (sorted by paymentnumber)
    and mark the payment processed.
    """
    sb = _client()

    # 1: fetch unprocessed payments ordered by payment_date asc
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
        pay_date = payment["payment_date"]  # YYYY-MM-DD
        raw_amount = payment["payment_amount"]
        try:
            amt = Decimal(str(float(raw_amount)))
        except Exception:
            logger.error(f"Payment {pid}: invalid amount '{raw_amount}'")
            sb.from_("payments_log").update({"processed": True}).eq("id", pid).execute()
            continue

        table = f"schedule_{loan_id}"

        # 2: fetch the schedule table; do not auto-create
        try:
            sched = (
                sb.from_(table)
                  .select(
                      "paymentnumber,duedate,beginningbalance,interestpaid,principal,actualpaymentdate"
                  )
                  .order("paymentnumber")
                  .execute().data or []
            )
        except Exception as e:
            err = str(e)
            if 'does not exist' in err or '42P01' in err:
                # schedule table missing for this loan
                missing.append(loan_id)
                continue
            logger.error(f"Payment {pid}: cannot fetch {table}: {e}")
            continue

        # 3: find next unpaid installment
        next_row = None
        for row in sched:
            if not row.get("actualpaymentdate"):
                next_row = row
                break

        if next_row is None:
            logger.warning(f"Payment {pid}: no unpaid installments in {table}")
            sb.from_("payments_log").update({"processed": True}).eq("id", pid).execute()
            continue

        # 4: calculate allocation
        bb = next_row.get("beginningbalance") or 0.0
        si = next_row.get("interestpaid") or 0.0
        result = calculate_principal_and_status(
            beginning_balance_float=bb,
            interest_paid_prefilled_float=si,
            actual_payment_amount_float=float(amt),
            due_date_str=next_row.get("duedate"),
            actual_payment_date_str=pay_date,
            grace_period_days=config.DEFAULT_GRACE_PERIOD_DAYS,
            late_fee_amount_flat=Decimal(str(config.DEFAULT_LATE_FEE))
        )
        if not result:
            logger.error(f"Payment {pid}: calculation returned no result")
            continue

        principal_paid = result["PrincipalPaid"]
        interest_paid = result.get("InterestPaid", Decimal("0"))
        late_fee = result["LateFee"]
        ending_bal = result["EndingBalance"]
        total_applied = principal_paid + interest_paid + late_fee
        if total_applied <= 0:
            logger.warning(f"Payment {pid}: zero allocation for installment {next_row['paymentnumber']}")
            sb.from_("payments_log").update({"processed": True}).eq("id", pid).execute()
            continue

        # 5: update the installment row
        sql = f'''
UPDATE public."{table}"
SET
    actualpaymentdate = '{pay_date}',
    actualpaymentamount = {float(amt)},
    principalpaid = {float(principal_paid)},
    latefee = {float(late_fee)},
    endingbalance = {float(ending_bal)},
    status = '{result["Status"]}'
WHERE
    "paymentnumber" = {next_row["paymentnumber"]};
'''        
        update_resp = sb.rpc("run_sql", {"sql_text": sql}).execute()
        if hasattr(update_resp, 'error') and update_resp.error:
            logger.error(
                f"Payment {pid}: failed updating installment {next_row['paymentnumber']}: {update_resp.error}"
            )
            continue

        # 6: mark payment processed
        sb.from_("payments_log").update({
            "processed": True,
            "processed_at": datetime.utcnow().isoformat()
        }).eq("id", pid).execute()

        logger.info(f"Payment {pid}: applied full amount {float(amt)} to installment {next_row['paymentnumber']}")

    logger.info("Done processing payments.")

    # Emit one line per loan missing an amortization schedule
    for lid in sorted(set(missing)):
        print(f"The {lid} doesn't have an amortization schedule yet.")

    return True


if __name__ == '__main__':
    process_payments()