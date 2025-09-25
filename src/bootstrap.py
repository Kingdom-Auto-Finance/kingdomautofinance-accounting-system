# bootstrap.py

import config
from supabase import create_client
import pandas as pd
import os
import time
from postgrest.exceptions import APIError
import gutils
import logging

# Set up logging for the script
logger = logging.getLogger(__name__)

def _reload_pgrst_schema(supabase):
    """Ask PostgREST to refresh its schema cache (safe no-op if it’s not needed)."""
    try:
        supabase.rpc("run_sql", {"sql_text": "NOTIFY pgrst, 'reload schema';"}).execute()
    except Exception:
        # We never want schema reload to break the flow
        logger.warning("Failed to notify PostgREST to reload schema. This may cause a temporary delay in table availability.")


def _safe_row_count(supabase, table_name, retries=5, base_delay=0.4):
    """
    Robust count that avoids HEAD (uses GET with limit=1 + count) and retries
    while the schema cache catches up.
    """
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            resp = (
                supabase
                .from_(table_name)
                .select("paymentnumber", count="exact")
                .limit(1)
                .execute()
            )
            if hasattr(resp, "count") and resp.count is not None:
                return int(resp.count)
            return len(resp.data or [])
        except APIError as e:
            msg = str(e)
            if (
                "schema cache" in msg
                or "PGRST205" in msg
                or "Could not find the table" in msg
                or "JSON could not be generated" in msg
            ):
                time.sleep(base_delay * attempt)
                last_err = e
                continue
            raise
        except Exception as e:
            last_err = e
            time.sleep(base_delay * attempt)
            continue
    logger.warning(
        f"Could not count rows for {table_name} after {retries} attempts. "
        f"Proceeding as 0. Last error: {last_err}"
    )
    return 0


def get_supabase_key():
    return os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("supabase_service_role_key")


def create_supabase_client():
    """Initialize Supabase client with URL and service-role key"""
    url = config.SUPABASE_URL
    key = get_supabase_key()
    return create_client(url, key)


def record_new_loan(supabase, loan_id: str):
    """
    Upsert the given loan_id into the master loans table.
    Requires config.LOANS_TABLE to exist with loan_id as UNIQUE or PRIMARY KEY.
    """
    try:
        supabase.table(config.LOANS_TABLE) \
                .upsert({"loan_id": loan_id}, on_conflict="loan_id") \
                .execute()
        logger.info(f"Recorded loan ID {loan_id} in the master loans table.")
    except Exception as e:
        logger.error(f"Failed to record loan ID {loan_id}: {e}")


def sanitize_value(value, dtype):
    """Convert empty or invalid values to None, cast to correct types."""
    if pd.isna(value) or value == "":
        return None
    try:
        if dtype == 'int':
            return int(value)
        if dtype == 'float':
            return float(value)
        if dtype in ('date', 'str'):
            return str(value)
    except (ValueError, TypeError):
        return None
    return value


def get_all_loan_ids_from_drive():
    return gutils.get_loan_ids_from_drive_folder(config.AMORTIZATION_SCHEDULES_FOLDER_ID)


def get_google_sheet_df(loan_id):
    gs_client = gutils.get_gspread_client()
    sheet_id = gutils.find_sheet_id_by_loan_id_in_folder(loan_id)
    if not sheet_id:
        logger.warning(f"Sheet for loan ID '{loan_id}' not found in Drive.")
        return None
    df = gutils.get_sheet_as_df(gs_client, sheet_id, "Schedule")
    if df is None or df.empty:
        logger.warning(f"Sheet for loan ID '{loan_id}' is unreadable or empty.")
        return None
    return df


def bootstrap_tables():
    """
    Create schedule tables and import amortization schedules from Google Sheets,
    skipping tables that already have data, and record each loan in the master table.
    """
    supabase = create_supabase_client()
    loan_ids = get_all_loan_ids_from_drive()

    cols = [
        ('paymentnumber', 'int'), ('duedate', 'date'), ('scheduledbalance', 'float'),
        ('adjustedbalance', 'float'), ('scheduledpayment', 'float'),
        ('actualpaymentdate', 'date'), ('actualpaymentamount', 'float'),
        ('scheduledprincipal', 'float'), ('scheduledinterest', 'float'),
        ('principalpaid', 'float'), ('interestpaid', 'float'),
        ('latefee', 'float'), ('creditapplied', 'float'),
        ('scheduledfinalbalance', 'float'), ('endingbalance', 'float'), ('status', 'str'),
    ]

    for loan_id in loan_ids:
        try:
            table_name = f"schedule_{loan_id}"

            # 1) Ensure table exists and reload schema
            sql = f'CREATE TABLE IF NOT EXISTS "{table_name}" (LIKE amortization_template INCLUDING ALL);'
            supabase.rpc("run_sql", {"sql_text": sql}).execute()
            logger.info(f"Ensured table {table_name} exists.")
            _reload_pgrst_schema(supabase)

            # 2) Always record the loan in the master table first
            record_new_loan(supabase, loan_id)

            # 3) Skip import if table already has data
            row_count = _safe_row_count(supabase, table_name)
            if row_count > 0:
                logger.info(f"Table {table_name} already has {row_count} rows. Skipping import.")
                continue

            # 4) Load amortization schedule from Google Sheets
            df_sched = get_google_sheet_df(loan_id)
            if df_sched is None or df_sched.empty:
                logger.warning(f"Schedule for '{loan_id}' is empty or unreadable; skipping.")
                continue

            # 5) Prepare and sanitize rows for insertion
            rows_to_insert = []
            for _, row in df_sched.iterrows():
                record = {col_name: sanitize_value(row.get(col_name), dtype) for col_name, dtype in cols}
                rows_to_insert.append(record)

            # 6) Filter out rows missing primary key 'paymentnumber'
            before_count = len(rows_to_insert)
            rows_to_insert = [r for r in rows_to_insert if r.get('paymentnumber') is not None]
            removed = before_count - len(rows_to_insert)
            if removed > 0:
                logger.warning(f"Skipped {removed} rows with missing 'paymentnumber' in {table_name}.")

            # 7) Bulk insert into Supabase
            if rows_to_insert:
                ins = supabase.from_(table_name).insert(rows_to_insert).execute()
                if hasattr(ins, "error") and ins.error:
                    logger.error(f"Error inserting data into {table_name}: {ins.error}")
                else:
                    logger.info(f"Imported {len(rows_to_insert)} rows into {table_name}.")
            
        except Exception as e:
            logger.error(f"An unexpected error occurred processing loan ID {loan_id}: {e}")
        
        # Consistent delay to avoid API rate limits
        logger.info(f"Pausing for 1 second to respect API rate limits...")
        time.sleep(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # This section was causing the issue. The configuration is already handled
    # by your config.py file, so these lines were overwriting valid values with None.
    # config.SUPABASE_URL = os.getenv("SUPABASE_URL")
    # config.SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    bootstrap_tables()