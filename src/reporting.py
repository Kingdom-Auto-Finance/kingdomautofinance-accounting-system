import pandas as pd
from datetime import datetime
import logging

import config
from supabase import create_client

logger = logging.getLogger(__name__)

import os
def get_supabase_key():
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not key:
        raise ValueError(
            "SUPABASE_SERVICE_ROLE_KEY environment variable is not set. "
            "Please configure this in your environment."
        )
    return key

def fetch_data(start_date: str = None, end_date: str = None, all_dates: bool = False) -> pd.DataFrame:
    """
    Fetch payment allocation data from the payment_allocations ledger.

    This queries the payment_allocations table which preserves the original
    payment_date for each payment, ensuring cash-basis reporting where
    payments appear in the month they were actually received by the bank.

    Returns a DataFrame with columns:
      - loan_id
      - payment_date (as string in mm/dd/yyyy format)
      - principal_amount (float)
      - interest_amount (float)
      - fee_amount (float)
    """

    # 1) Connect to Supabase
    try:
        url = config.SUPABASE_URL
        key = get_supabase_key()
        supabase = create_client(url, key)
    except Exception as e:
        logger.error(f"Failed to connect to Supabase: {str(e)}")
        raise

    # 2) Validate date parameters
    if not all_dates and (not start_date or not end_date):
        raise ValueError("start_date and end_date must be provided when --all is not set")

    # 3) Query payment_allocations table with pagination
    all_rows = []
    page_size = 1000
    offset = 0

    while True:
        try:
            query = supabase.from_("payment_allocations").select(
                "loan_id",
                "payment_date",
                "principal_allocated",
                "interest_allocated",
                "late_fee_allocated"
            )

            if not all_dates:
                query = query.gte("payment_date", start_date).lte("payment_date", end_date)

            result = query.order("payment_date").range(offset, offset + page_size - 1).execute()
            data = result.data or []

            if not data:
                break

            all_rows.extend(data)

            if len(data) < page_size:
                break

            offset += page_size

        except Exception as e:
            logger.error(f"Failed to query payment_allocations: {str(e)}")
            raise

    # 4) Build DataFrame with formatted dates
    rows = []
    for r in all_rows:
        raw_date = r.get("payment_date")
        if raw_date is None:
            continue

        # Parse date (could be string or date object)
        if isinstance(raw_date, str):
            # Handle both YYYY-MM-DD and ISO datetime formats
            date_str = raw_date[:10]  # Extract date portion
            payment_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        else:
            payment_date = raw_date

        # Format date as mm/dd/yyyy for CSV export
        formatted_date = payment_date.strftime("%m/%d/%Y")

        rows.append({
            "loan_id": r["loan_id"],
            "payment_date": formatted_date,
            "principal_amount": float(r.get("principal_allocated") or 0.0),
            "interest_amount": float(r.get("interest_allocated") or 0.0),
            "fee_amount": float(r.get("late_fee_allocated") or 0.0),
        })

    df = pd.DataFrame(rows)
    logger.info(f"Fetched {len(df)} allocation records from payment_allocations")
    return df


def generate_report(mode: str, start_date: str = None, end_date: str = None, all_dates: bool = False):
    """
    CLI entry point for generating reports.
    mode: one of "summary", "day", "loan", "full"
    start_date/end_date: YYYY-MM-DD (ignored if all_dates=True)
    all_dates: if True, ignores dates and fetches everything.
    Outputs CSV to stdout.
    """
    df = fetch_data(start_date=start_date, end_date=end_date, all_dates=all_dates)

    # If no data, emit empty headers or single blank line for summary
    if df.empty:
        if mode == "summary":
            print("total_principal,total_interest,total_fees")
        else:
            print()
        logger.warning("No data returned for the given parameters.")
        return

    if mode == "summary":
        total = df[["principal_amount", "interest_amount", "fee_amount"]].sum()
        out = pd.DataFrame([{
            "total_principal": round(total["principal_amount"], 2),
            "total_interest":  round(total["interest_amount"], 2),
            "total_fees":      round(total["fee_amount"], 2),
        }])
        # Ensure two decimal places
        print(out.to_csv(index=False, float_format="%.2f").strip())
        logger.info(f"Summary totals: {out.to_dict(orient='records')[0]}")
        return

    if mode == "day":
        df_day = (
            df.groupby("payment_date", as_index=False)
              .agg(
                  principal_amount=("principal_amount", "sum"),
                  interest_amount=("interest_amount", "sum"),
                  fee_amount=("fee_amount", "sum"),
              )
              .sort_values("payment_date")
        )
        print(df_day.to_csv(index=False, float_format="%.2f").strip())
        logger.info(f"Day breakdown rows: {len(df_day)}")
        return

    if mode == "loan":
        df_loan = (
            df.groupby("loan_id", as_index=False)
              .agg(
                  principal_amount=("principal_amount", "sum"),
                  interest_amount=("interest_amount", "sum"),
                  fee_amount=("fee_amount", "sum"),
              )
              .sort_values("loan_id")
        )
        print(df_loan.to_csv(index=False, float_format="%.2f").strip())
        logger.info(f"Loan breakdown rows: {len(df_loan)}")
        return

    if mode == "full":
        df_full = (
            df.groupby(["loan_id", "payment_date"], as_index=False)
              .agg(
                  principal_amount=("principal_amount", "sum"),
                  interest_amount=("interest_amount", "sum"),
                  fee_amount=("fee_amount", "sum"),
              )
              .sort_values(["loan_id", "payment_date"])
        )
        print(df_full.to_csv(index=False, float_format="%.2f").strip())
        logger.info(f"Full breakdown rows: {len(df_full)}")
        return

    # Unknown mode
    raise ValueError(f"Unknown report mode '{mode}'")


# --- Wrapper functions for CLI (src/main.py) ---

def generate_period_report(start_date: str = None, end_date: str = None):
    """
    Wrapper for 'summary' report in CLI.
    If start_date and end_date are both None, treat as all_dates.
    """
    all_dates = (start_date is None and end_date is None)
    return generate_report("summary", start_date, end_date, all_dates)


def generate_day_breakdown(start_date: str = None, end_date: str = None, all_dates: bool = False):
    """
    Wrapper for 'day-breakdown' report in CLI.
    """
    return generate_report("day", start_date, end_date, all_dates)


def generate_loan_breakdown(start_date: str = None, end_date: str = None, all_dates: bool = False):
    """
    Wrapper for 'loan-breakdown' report in CLI.
    """
    return generate_report("loan", start_date, end_date, all_dates)


def generate_full_breakdown(start_date: str = None, end_date: str = None, all_dates: bool = False):
    """
    Wrapper for 'full-breakdown' report in CLI.
    """
    return generate_report("full", start_date, end_date, all_dates)

# Allow standalone testing
if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    all_dates = "--all" in args
    tokens = [a for a in args if a != "--all"]
    if not tokens:
        mode = "summary"
        start = end = None
    elif len(tokens) == 1:
        mode = tokens[0]
        start = end = None
    elif len(tokens) == 2:
        mode = "summary"
        start, end = tokens
    else:
        mode, start, end = tokens[0], tokens[1], tokens[2]
    generate_report(mode, start_date=start, end_date=end, all_dates=all_dates)
