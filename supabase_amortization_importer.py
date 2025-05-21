import os
import pandas as pd
import re
from supabase import create_client, Client
import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build
from io import BytesIO
import csv

# --- Supabase setup ---
SUPABASE_URL = os.environ["https://puwcyhbjchkfvvaccacg.supabase.co"]
SUPABASE_KEY = os.environ["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InB1d2N5aGJqY2hrZnZ2YWNjYWNnIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc0NzIzMTY4MywiZXhwIjoyMDYyODA3NjgzfQ.X83DkCaFq2JUQO7EmfjLj3aeSnTkZ0ceNrTeF67eHlk"]  # must use service role to create tables
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)



import os
import pandas as pd
import re
from supabase import create_client, Client
import requests
from google.cloud import secretmanager
from google.oauth2 import service_account
from googleapiclient.discovery import build
from io import BytesIO
import json
import csv

# --- Supabase setup ---
SUPABASE_URL = os.environ["https://puwcyhbjchkfvvaccacg.supabase.co"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]  # must use service role to create tables
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- Google Secret Manager for service account ---
def get_service_account_credentials_from_secret_manager():
    secret_name = os.environ["SERVICE_ACCOUNT_SECRET_RESOURCE_NAME"]  # Full secret resource name
    sm_client = secretmanager.SecretManagerServiceClient()
    response = sm_client.access_secret_version(request={"name": secret_name})
    service_account_info = json.loads(response.payload.data.decode("UTF-8"))
    return service_account.Credentials.from_service_account_info(service_account_info, scopes=["https://www.googleapis.com/auth/drive.readonly"])

# --- Google Drive setup ---
GDRIVE_FOLDER_ID = os.environ["GDRIVE_FOLDER_ID"]
credentials = get_service_account_credentials_from_secret_manager()
drive_service = build("drive", "v3", credentials=credentials)

# --- Helpers ---
def extract_loan_id_from_filename(filename):
    match = re.match(r"(.*?)\s*-\s*Schedule\\.csv", filename)
    return match.group(1).strip() if match else None

def clean_numeric(val):
    try:
        return float(str(val).replace(",", "").strip())
    except:
        return None

def table_exists(table_name):
    query = f"""
    select to_regclass('public.{table_name}')
    """
    result = supabase.rpc("sql", {"q": query}).execute()
    return result.data[0]["to_regclass"] is not None

def create_table_from_template(new_table_name, template_table="amortization_template"):
    query = f"""
    CREATE TABLE IF NOT EXISTS {new_table_name} (LIKE {template_table} INCLUDING ALL);
    """
    return supabase.rpc("sql", {"q": query}).execute()

def download_csv_file(file_id):
    request = drive_service.files().get_media(fileId=file_id)
    file_data = request.execute()
    return BytesIO(file_data)

def process_amortization_files():
    results = drive_service.files().list(q=f"'{GDRIVE_FOLDER_ID}' in parents and mimeType='text/csv'",
                                        pageSize=1000, fields="files(id, name)").execute()
    for file in results.get("files", []):
        filename = file["name"]
        file_id = file["id"]
        loan_id = extract_loan_id_from_filename(filename)

        if not loan_id:
            print(f"Skipping file (invalid name): {filename}")
            continue

        table_name = f"schedule_{loan_id.lower()}"

        if table_exists(table_name):
            print(f"Table {table_name} already exists. Skipping...")
            continue

        print(f"Processing {filename} into table {table_name}")

        # Download and read CSV
        file_stream = download_csv_file(file_id)
        df = pd.read_csv(file_stream)

        # Clean and format
        numeric_columns = [
            "Beginning Balance", "Scheduled Payment", "Interest Paid",
            "Principal", "Actual Payment Amount", "Late Fee"
        ]
        for col in numeric_columns:
            if col in df.columns:
                df[col] = df[col].apply(clean_numeric)

        date_columns = ["Due Date", "Actual Payment Date"]
        for col in date_columns:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce').dt.date

        df.columns = [
            "payment_number", "due_date", "beginning_balance", "scheduled_payment",
            "interest_paid", "principal", "actual_payment_date", "actual_payment_amt",
            "late_fee", "status"
        ][:len(df.columns)]  # Adjusted header

        df["loan_id"] = loan_id

        # Create the table
        create_table_from_template(table_name)

        # Upload rows
        for _, row in df.iterrows():
            data = row.dropna().to_dict()
            supabase.table(table_name).insert(data).execute()

        print(f"Inserted {len(df)} rows into {table_name}")

if __name__ == "__main__":
    process_amortization_files()