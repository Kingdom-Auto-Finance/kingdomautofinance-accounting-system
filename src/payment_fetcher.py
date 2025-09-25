import pandas as pd
from datetime import datetime, timedelta
import logging

import config
import gutils
from gutils import safe_string_to_float

from supabase import create_client
from google.cloud import secretmanager

import os
def get_supabase_key():
    return os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

def create_supabase_client():
    """Initialize Supabase client with URL and service-role key"""
    url = config.SUPABASE_URL
    key = get_supabase_key()
    return create_client(url, key)


logger = logging.getLogger(__name__)

# --- Constants for Column Names ---
SOURCE_LOAN_ID_COL = "LoanId"
SOURCE_DATE_COL = "Date"
SOURCE_AMOUNT_COL = "Amount"

# --- Constants for Target Column Names ---
TARGET_LOAN_ID_COL_LOWER = 'loanid'
TARGET_DATE_COL_LOWER = 'paymentdate'
TARGET_AMOUNT_COL_LOWER = 'paymentamount'

# --- CONSTANT FOR SOURCE SHEET TAB NAME ---
SOURCE_SHEET_TAB_NAME = "Payments"


def fetch_and_populate_payments(start_date_str=None, end_date_str=None, fetch_all=False, fetch_recent_days=None):
    """
    Fetches payment data from the source sheet, filters, compares counts with the database,
    and inserts only the new payments into Supabase payments_log.
    Returns True on success, False on error.
    """
    # Determine logging mode
    if fetch_recent_days:
        run_mode_log = f"Recent {fetch_recent_days} days"
    elif fetch_all:
        run_mode_log = "All (checking counts for duplicates)"
    elif start_date_str or end_date_str:
        run_mode_log = f"Range {start_date_str or 'any'} - {end_date_str or 'any'}"
    else:
        run_mode_log = "Default (Recent 7 days)"
    logger.info(f"Starting payment fetch. Mode: {run_mode_log}")

    # Initialize Google Sheets client
    try:
        gs_client = gutils.get_gspread_client()
    except ConnectionError as e:
        logger.error(f"Failed GS client init: {e}. Aborting fetch.")
        return False

    # Initialize Supabase client
    supabase = create_supabase_client()

    # --- 1. Read Source Sheet ---
    source_sheet_id = config.SOURCE_PAYMENTS_SHEET_ID
    logger.info(
        f"Reading source payment data from Sheet ID: {source_sheet_id}, Tab: '{SOURCE_SHEET_TAB_NAME}'"
    )
    df_source = gutils.get_sheet_as_df(
        gs_client,
        source_sheet_id,
        SOURCE_SHEET_TAB_NAME,
        expected_headers=[SOURCE_LOAN_ID_COL, SOURCE_DATE_COL, SOURCE_AMOUNT_COL]
    )
    if df_source is None or df_source.empty:
        logger.warning(f"Source payment sheet ('{SOURCE_SHEET_TAB_NAME}') empty or unreadable.")
        return False

    required_source_cols = [SOURCE_LOAN_ID_COL, SOURCE_DATE_COL, SOURCE_AMOUNT_COL]
    missing_cols = [col for col in required_source_cols if col not in df_source.columns]
    if missing_cols:
        logger.error(
            f"Missing required columns: {missing_cols}. Found: {df_source.columns.tolist()}"
        )
        return False

    # --- 2. Clean and preprocess source data for comparison ---
    df_source['loan_id'] = df_source[SOURCE_LOAN_ID_COL].astype(str).str.lower().str.strip()
    df_source['payment_date'] = pd.to_datetime(df_source[SOURCE_DATE_COL], errors='coerce').dt.strftime('%Y-%m-%d')
    df_source['payment_amount'] = df_source[SOURCE_AMOUNT_COL].apply(safe_string_to_float).round(2)

    df_source = df_source.dropna(subset=['loan_id', 'payment_date', 'payment_amount'])
    df_source = df_source[df_source['payment_amount'] > 0]
    
    if df_source.empty:
        logger.info("No valid payment rows found in the source sheet after cleaning.")
        return True

    # --- 3. Load and preprocess existing payments from Supabase ---
    res = supabase.from_("payments_log").select("loan_id, payment_date, payment_amount").execute()
    df_db = pd.DataFrame(res.data)
    
    if df_db.empty:
        db_counts = pd.Series(dtype='int64')
    else:
        df_db['loan_id'] = df_db['loan_id'].astype(str).str.lower().str.strip()
        df_db['payment_date'] = pd.to_datetime(df_db['payment_date'], errors='coerce').dt.strftime('%Y-%m-%d')
        df_db['payment_amount'] = df_db['payment_amount'].round(2)
        df_db = df_db.dropna(subset=['loan_id', 'payment_date', 'payment_amount'])
        
        df_db['payment_amount_str'] = df_db['payment_amount'].astype(str)
        db_counts = df_db.groupby(['loan_id', 'payment_date', 'payment_amount_str']).size()

    # --- 4. Count payments by a unique transaction key for comparison ---
    df_source['payment_amount_str'] = df_source['payment_amount'].astype(str)
    source_counts = df_source.groupby(['loan_id', 'payment_date', 'payment_amount_str']).size()

    # --- ADDED DEBUG LOGGING ---
    logger.info("\n--- DEBUG: CLEANED SOURCE DATA SAMPLES ---")
    logger.info(f"Source DataFrame Size: {len(df_source)}")
    if not df_source.empty:
        logger.info(df_source[['loan_id', 'payment_date', 'payment_amount_str']].head(5).to_string())
    
    logger.info("\n--- DEBUG: CLEANED DATABASE DATA SAMPLES ---")
    logger.info(f"Database DataFrame Size: {len(df_db)}")
    if not df_db.empty:
        logger.info(df_db[['loan_id', 'payment_date', 'payment_amount_str']].head(5).to_string())

    # --- 5. Determine which payments are new ---
    payments_to_insert = []
    
    for key, source_count in source_counts.items():
        db_count = db_counts.get(key, 0)
        
        num_to_insert = source_count - db_count
        
        if num_to_insert > 0:
            loan_id, payment_date, payment_amount_str = key
            new_payment = {
                "loan_id": loan_id,
                "payment_date": payment_date,
                "payment_amount": float(payment_amount_str),
                "processed": False,
                "processed_at": None,
            }
            payments_to_insert.extend([new_payment] * num_to_insert)

    logger.info(f"Found {len(payments_to_insert)} new payments to insert.")
    
    if not payments_to_insert:
        logger.info("No new payments to insert.")
        return True

    # --- 6. Insert new payments into Supabase ---
    sup_res = supabase.from_("payments_log").insert(payments_to_insert).execute()
    
    if hasattr(sup_res, "error") and sup_res.error:
        logger.error(f"Failed inserting payments: {sup_res.error}")
        return False

    logger.info(f"Successfully inserted {len(payments_to_insert)} payments into Supabase.")
    return True