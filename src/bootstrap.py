# bootstrap.py

import config
from supabase import create_client
import pandas as pd
import os

def get_supabase_key():
    return os.environ.get("supabase_service_role_key")


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


def get_all_loan_ids_from_local_folder():
    """List all CSV filenames in 'schedules_csv/' and extract loan_ids"""
    folder = "schedules_csv"
    return [
        os.path.splitext(f)[0]
        for f in os.listdir(folder)
        if f.endswith(".csv")
    ]


def get_local_schedule_df(loan_id):
    """Read CSV for given loan_id from schedules_csv/"""
    csv_path = os.path.join("schedules_csv", f"{loan_id}.csv")
    if not os.path.isfile(csv_path):
        print(f"⚠️ CSV file not found for loan {loan_id}")
        return None
    try:
        return pd.read_csv(csv_path)
    except Exception as e:
        print(f"⚠️ Failed to read CSV for {loan_id}: {e}")
        return None


def bootstrap_tables():
    """
    Create schedule tables and import amortization schedules from local CSV files,
    skipping tables that already have data, and record each loan in the master table.
    """
    supabase = create_supabase_client()
    loan_ids = get_all_loan_ids_from_local_folder()

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
        except Exception as e:
            print(f"Error creating {table_name}: {e}")
            continue

        # 2) Skip import if table already has data
        head_resp = supabase.from_(table_name).select("*", count="exact", head=True).execute()
        existing_count = head_resp.count or 0
        if existing_count > 0:
            print(f"Table {table_name} already has {existing_count} rows; skipping import.")
            record_new_loan(supabase, loan_id)
            continue

        # 3) Load amortization schedule from CSV
        df_sched = get_local_schedule_df(loan_id)
        if df_sched is None or df_sched.empty:
            print(f"⚠️ Schedule CSV for '{loan_id}' is empty or unreadable; skipping.")
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


if __name__ == "__main__":
    bootstrap_tables()
