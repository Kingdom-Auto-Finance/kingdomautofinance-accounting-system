# src/daily_summary_reporter.py
import logging
from datetime import date

import config
from supabase import create_client

logger = logging.getLogger(__name__)

# Supabase helper (no secret manager)
def create_supabase_client():
    """Initialize Supabase client with URL and service-role key (from environment)"""
    url = config.SUPABASE_URL
    key = config.SUPABASE_SERVICE_ROLE_KEY  # Now read directly from environment variable
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
