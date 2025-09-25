# bootstrap.py

import config
from supabase import create_client
import pandas as pd
import os
import time
from postgrest.exceptions import APIError
import gutils


def _reload_pgrst_schema(supabase):
    """Ask PostgREST to refresh its schema cache (safe no-op if it’s not needed)."""
    try:
        supabase.rpc("run_sql", {"sql_text": "NOTIFY pgrst, 'reload schema';"}).execute()
    except Exception:
        # We never want schema reload to break the flow
        pass


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
                .select("paymentnumber", count="exact")  # <-- no head=True
                .limit(1)
                .execute()
            )
            # supabase-py exposes both .count and .data
            if hasattr(resp, "count") and resp.count is not None:
                return int(resp.count)
            return len(resp.data or [])
        except APIError as e:
            msg = str(e)
            # Typical transient signals while schema cache updates
            if (
                "schema cache" in msg
                or "PGRST205" in msg
                or "Could not find the table" in msg
                or "JSON could not be generated" in msg
            ):
                time.sleep(base_delay * attempt)  # backoff
                last_err = e
                continue
            raise
        except Exception as e:
            last_err = e
            time.sleep(base_delay * attempt)
            continue
    # Last resort: assume 0 and keep going, but note we tried
    print(
        f"[warn] Could not count rows for {table_name} after {retries} attempts. "
        f"Proceeding as 0. Last error: {last_err}"
    )
    return 0


def get_supabase_key():
    # Try uppercase first, fallback to lowercase (both supported in your envs)
    return os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("supabase_service_role_key")


def create_supabase_client():
    """Initialize Supabase client with URL and service-role key"""
    url = config.SUPABASE_URL
    key = get_supabase_key()
    return create_client(url, key)


# -------------------------------------------------------------------
# Helper to maintain master loans table
# -------------------------------------------------------------------

def record_new_loan(supabase, loan_id: str):
    """
    Upsert the given loan_id into the master loans table.
    Requires config.LOANS_TABLE to exist with loan_id as UNIQUE or PRIMARY KEY.
    """
    supabase.table(config.LOANS_TABLE) \
            .upsert({"loan_id": loan_id}, on_conflict="loan_id") \
            .execute()


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
        print(f"⚠️ Sheet '{loan_id}' not found in Drive.")
        return None
    df = gutils.get_sheet_as_df(gs_client, sheet_id, "Schedule")
    if df is None or df.empty:
        print(f"⚠️ Sheet '{loan_id}' is unreadable or empty.")
        return None
    return df


def bootstrap_tables():
    """
    Create schedule tables and import amortization schedules from Google Sheets,
    skipping tables that already have data, and record each loan in the master table.
    """
    supabase = create_supabase_client()
    loan_ids = get_all_loan_ids_from_drive()

    # Define column mapping and expected types
    cols = [
        ('paymentnumber', 'int'),
        ('duedate', 'date'),
        ('scheduledbalance', 'float'),
        ('adjustedbalance', 'float'),
        ('scheduledpayment', 'float'),
        ('actualpaymentdate', 'date'),
        ('actualpaymentamount', 'float'),
        ('scheduledprincipal', 'float'),
        ('scheduledinterest', 'float'),
        ('principalpaid', 'float'),
        ('interestpaid', 'float'),
        ('latefee', 'float'),
        ('creditapplied', 'float'),
        ('scheduledfinalbalance', 'float'),
        ('endingbalance', 'float'),
        ('status', 'str'),
    ]

    for loan_id in loan_ids:
        table_name = f"schedule_{loan_id}"

        # 1) Ensure table exists
        sql = f'CREATE TABLE IF NOT EXISTS "{table_name}" (LIKE amortization_template INCLUDING ALL);'
        try:
            supabase.rpc("run_sql", {"sql_text": sql}).execute()
            print(f"Ensured table {table_name} exists.")
            _reload_pgrst_schema(supabase)
        except Exception as e:
            print(f"Error creating {table_name}: {e}")
            continue

        # 2) Skip import if table already has data (but still record the loan)
        row_count = _safe_row_count(supabase, table_name)
        if row_count > 0:
            print(f"Table {table_name} already has {row_count} rows. Skipping import.")
            record_new_loan(supabase, loan_id)
            # Add a delay here as well, since this loop continues without a Google Sheets read.
            time.sleep(0.5)
            continue

        # 3) Load amortization schedule from Google Sheets
        df_sched = get_google_sheet_df(loan_id)
        if df_sched is None or df_sched.empty:
            print(f"⚠️ Schedule CSV for '{loan_id}' is empty or unreadable; skipping.")
            time.sleep(0.5)  # Delay even if a sheet is skipped
            continue

        # 4) Prepare rows for insertion with sanitized data
        rows_to_insert = []
        for _, row in df_sched.iterrows():
            record = {}
            for col_name, dtype in cols:
                raw = row.get(col_name)
                record[col_name] = sanitize_value(raw, dtype)
            rows_to_insert.append(record)

        # 5) Filter out rows missing primary key 'paymentnumber'
        before_count = len(rows_to_insert)
        rows_to_insert = [r for r in rows_to_insert if r.get('paymentnumber') is not None]
        removed = before_count - len(rows_to_insert)
        if removed > 0:
            print(f"Skipped {removed} rows with missing 'paymentnumber' in {table_name}.")

        # 6) Bulk insert into Supabase
        if rows_to_insert:
            ins = supabase.from_(table_name).insert(rows_to_insert).execute()
            if hasattr(ins, "error") and ins.error:
                print(f"Error inserting data into {table_name}: {ins.error}")
            else:
                print(f"Imported {len(rows_to_insert)} rows into {table_name}.")
                record_new_loan(supabase, loan_id)

        # --- FIX: ADDED DELAY TO AVOID GOOGLE SHEETS API RATE LIMITS ---
        print(f"Pausing for 1 second to respect Google Sheets API rate limits...")
        time.sleep(1)


if __name__ == "__main__":
    bootstrap_tables()