import pandas as pd
from datetime import datetime
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import config
from supabase import create_client

logger = logging.getLogger(__name__)

# Optional config constant for which table holds loan IDs
LOANS_TABLE = getattr(config, "LOANS_TABLE", "loans")

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
    Fetch payment schedule rows from Supabase for all loans,
    filtered by date range unless all_dates=True.
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

    # 2) Discover loan IDs from the loans table
    try:
        resp = supabase.from_(LOANS_TABLE).select("loan_id").execute()
        loan_rows = resp.data or []
        loan_ids = [r["loan_id"] for r in loan_rows]
        if not loan_ids:
            logger.error(f"No loan IDs found in Supabase table '{LOANS_TABLE}'.")
            return pd.DataFrame()
    except Exception as e:
        logger.error(f"Failed to query loans table '{LOANS_TABLE}': {str(e)}")
        raise

    # 3) Query each loan schedule table IN PARALLEL for better performance
    rows = []

    # Validate date parameters before parallel execution
    if not all_dates and (not start_date or not end_date):
        raise ValueError("start_date and end_date must be provided when --all is not set")

    def query_loan_schedule(loan_id):
        """Query a single loan's schedule table."""
        try:
            table_name = f"schedule_{loan_id}"
            table = supabase.from_(table_name)
            query = table.select(
                "actualpaymentdate",
                "principalpaid",
                "interestpaid",
                "latefee"
            )

            if not all_dates:
                query = (
                    query
                        .gte("actualpaymentdate", f"{start_date}T00:00:00Z")
                        .lte("actualpaymentdate", f"{end_date}T23:59:59Z")
                )

            resp_sched = query.execute()
            data = resp_sched.data or []

            loan_rows = []
            for r in data:
                raw_date = r.get("actualpaymentdate")
                if raw_date is None:
                    continue
                payment_date = datetime.fromisoformat(raw_date.rstrip("Z")).date()
                # Format date as mm/dd/yyyy for CSV export
                formatted_date = payment_date.strftime("%m/%d/%Y")
                loan_rows.append({
                    "loan_id": loan_id,
                    "payment_date": formatted_date,
                    "principal_amount": float(r.get("principalpaid", 0.0)),
                    "interest_amount": float(r.get("interestpaid", 0.0)),
                    "fee_amount": float(r.get("latefee", 0.0)),
                })
            return loan_rows
        except Exception as e:
            logger.warning(f"Failed to query schedule for loan_id '{loan_id}': {str(e)}")
            return []

    # Execute queries in parallel with thread pool (max 10 concurrent requests)
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(query_loan_schedule, loan_id): loan_id for loan_id in loan_ids}
        for future in as_completed(futures):
            loan_rows = future.result()
            rows.extend(loan_rows)

    # 4) Build DataFrame
    df = pd.DataFrame(rows)
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
