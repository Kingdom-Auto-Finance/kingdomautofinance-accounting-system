# src/daily_summary_reporter.py
import logging
from datetime import date

import config
from supabase import create_client
from google.cloud import secretmanager

logger = logging.getLogger(__name__)

# Supabase & Secret Manager helpers
def get_supabase_key():
    """Fetch Supabase service-role key from Secret Manager"""
    sm = secretmanager.SecretManagerServiceClient()
    resp = sm.access_secret_version(
        request={"name": config.SUPABASE_SERVICE_ROLE_SECRET_RESOURCE_NAME}
    )
    return resp.payload.data.decode("utf-8")


def create_supabase_client():
    """Initialize Supabase client with URL and service-role key"""
    url = config.SUPABASE_URL
    key = get_supabase_key()
    return create_client(url, key)


def generate_and_update_daily_summary(full_rebuild=False):
    """
    Generate and log a daily summary of processed payments for today.
    full_rebuild flag is accepted for CLI compatibility but not used.
    Returns a dict with date, count, and total amount.
    """
    today = date.today().isoformat()
    logger.info(f"Generating daily summary for {today} (full_rebuild={full_rebuild})")

    supabase = create_supabase_client()
    # Query processed payments for today
    resp = (
        supabase
        .from_("payments_log")
        .select("payment_amount", count="exact")
        .eq("processed", True)
        .eq("payment_date", today)
        .execute()
    )
    count = resp.count or 0
    total = sum(r.get("payment_amount") or 0.0 for r in (resp.data or []))

    summary = (
        f"\n--- Daily Summary for {today} ---\n"
        f"Payments Received: {count}\n"
        f"Total Amount     : {total:.2f}\n"
    )
    logger.info(summary)
    print(summary)

    return {"date": today, "count": count, "total": round(total, 2)}

if __name__ == "__main__":
    generate_and_update_daily_summary()
