# bootstrap.py

import config
import gutils
from supabase import create_client
from google.cloud import secretmanager
import pandas as pd


def get_supabase_key():
    """Fetch Supabase service-role key from Secret Manager"""
    sm = secretmanager.SecretManagerServiceClient()
    response = sm.access_secret_version(
        request={"name": config.SUPABASE_SERVICE_ROLE_SECRET_RESOURCE_NAME}
    )
    return response.payload.data.decode("utf-8")


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


def bootstrap_tables():
    """
    Create schedule tables and import existing amortization schedules from Google Sheets,
    skipping tables that already have data, and record each loan in the master table.
    """
    supabase = create_supabase_client()
    gs_client = gutils.get_gspread_client()

    loan_ids = gutils.get_loan_ids_from_drive_folder(
        config.AMORTIZATION_SCHEDULES_FOLDER_ID
    )

    # Define column mapping and expected types
    cols = [
        ('paymentnumber', 'int'),
        ('duedate', 'date'),
        ('scheduledbalance', 'float'),   beginningbalance
        ('adjustedbalance', 'float'), new
        ('scheduledpayment',     'float'),
        ('actualpaymentdate', 'date'),
        ('actualpaymentamount', 'float'),
        ('scheduledprincipal', 'float'),    principal
        ('scheduledinterest', 'float'),        
        ('principalpaid', 'float'),
        ('interestpaid', 'float'),
        ('latefee', 'float'),
        ('creditapplied', 'float'),
        ('scheduledfinalbalance', 'float'), balance
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
        except Exception as e:
            print(f"Error creating {table_name}: {e}")
            continue

        # 2) Skip import if table already has data
        head_resp = supabase.from_(table_name).select("*", count="exact", head=True).execute()
        existing_count = head_resp.count or 0
        if existing_count > 0:
            print(f"Table {table_name} already has {existing_count} rows; skipping import.")
            # Still ensure loan is recorded
            record_new_loan(supabase, loan_id)
            continue

        # 3) Locate the sheet for this loan
        sheet_id = gutils.find_sheet_id_by_loan_id_in_folder(loan_id)
        if not sheet_id:
            print(f"⚠️ No spreadsheet named '{loan_id}' found; skipping import.")
            continue

        # 4) Read the 'Schedule' tab
        df_sched = gutils.get_sheet_as_df(gs_client, sheet_id, "Schedule")
        if df_sched is None or df_sched.empty:
            print(f"⚠️ Schedule sheet for '{loan_id}' is empty or unreadable; skipping.")
            continue

        # 5) Prepare rows for insertion with sanitized data
        rows_to_insert = []
        for _, row in df_sched.iterrows():
            record = {}
            for col_name, dtype in cols:
                raw = row.get(col_name)
                record[col_name] = sanitize_value(raw, dtype)
            rows_to_insert.append(record)

        # 6) Filter out rows missing primary key 'paymentnumber'
        before_count = len(rows_to_insert)
        rows_to_insert = [r for r in rows_to_insert if r.get('paymentnumber') is not None]
        removed = before_count - len(rows_to_insert)
        if removed > 0:
            print(f"Skipped {removed} rows with missing 'paymentnumber' in {table_name}.")

        # 7) Bulk insert into Supabase
        if rows_to_insert:
            ins = supabase.from_(table_name).insert(rows_to_insert).execute()
            if hasattr(ins, "error") and ins.error:
                print(f"Error inserting data into {table_name}: {ins.error}")
            else:
                print(f"Imported {len(rows_to_insert)} rows into {table_name}.")
                # Record successful import in master loans table
                record_new_loan(supabase, loan_id)


if __name__ == "__main__":
    bootstrap_tables()
