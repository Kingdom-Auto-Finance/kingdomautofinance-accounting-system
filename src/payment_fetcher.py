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
    Fetches payment data from the source sheet, filters duplicates,
    and inserts new payments into Supabase payments_log.
    Returns True on success, False on error.
    """
    # Determine logging mode
    if fetch_recent_days:
        run_mode_log = f"Recent {fetch_recent_days} days"
    elif fetch_all:
        run_mode_log = "All (checking duplicates)"
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
    # Use expected_headers to avoid duplicate header issues
    df_source = gutils.get_sheet_as_df(
        gs_client,
        source_sheet_id,
        SOURCE_SHEET_TAB_NAME,
        expected_headers=[SOURCE_LOAN_ID_COL, SOURCE_DATE_COL, SOURCE_AMOUNT_COL]
    )
    if df_source is None or df_source.empty:
        logger.warning(f"Source payment sheet ('{SOURCE_SHEET_TAB_NAME}') empty or unreadable.")
        return False

    # Verify required source columns
    required_source_cols = [SOURCE_LOAN_ID_COL, SOURCE_DATE_COL, SOURCE_AMOUNT_COL]
    missing_cols = [col for col in required_source_cols if col not in df_source.columns]
    if missing_cols:
        logger.error(
            f"Missing required columns: {missing_cols}. Found: {df_source.columns.tolist()}"
        )
        return False

    # --- 2. Load existing payments from Supabase for duplicate check ---
    # Fetch all relevant columns from Supabase
    res = supabase.from_("payments_log").select(
        "loan_id, payment_date, payment_amount"
    ).execute()
    
    # Create a set of tuples for quick lookups.
    # We round the amount to avoid floating-point comparison issues.
    existing_payments = set()
    if res.data:
        for row in res.data:
            # Ensure proper handling of potential None values and convert data types
            loan_id = str(row.get('loan_id', '')).lower()
            payment_date = row.get('payment_date')
            payment_amount = row.get('payment_amount')
            
            # Check for valid data before adding to the set
            if loan_id and payment_date and payment_amount is not None:
                # Use a tuple for the key to be hashable
                key = (loan_id, payment_date, round(payment_amount, 2))
                existing_payments.add(key)
    logger.info(f"Loaded {len(existing_payments)} existing payments from Supabase for duplicate check.")


    # --- 3. Parse, Transform, Filter source data ---
    new_payments = []
    parse_errors = duplicate_count = out_of_range_count = missing_loanid_count = 0

    # Determine date filter
    filter_start = filter_end = None
    if fetch_recent_days:
        try:
            filter_end = datetime.now().date()
            filter_start = filter_end - timedelta(days=int(fetch_recent_days) - 1)
            logger.info(f"Filtering FROM {filter_start} TO {filter_end}.")
        except (ValueError, TypeError):
            logger.error(
                f"Invalid fetch_recent_days: {fetch_recent_days}. No date filter applied."
            )
            fetch_all = True
    elif not fetch_all:
        try:
            if start_date_str:
                filter_start = datetime.strptime(
                    start_date_str, "%Y-%m-%d"
                ).date()
            if end_date_str:
                filter_end = datetime.strptime(
                    end_date_str, "%Y-%m-%d"
                ).date()
            logger.info(
                f"Filtering FROM {filter_start or 'beginning'} TO {filter_end or 'end'}."
            )
        except ValueError:
            logger.error(
                f"Invalid date format: {start_date_str}/{end_date_str}. No date filter applied."
            )
            fetch_all = True

    # Loop through source rows
    for index, row in df_source.iterrows():
        raw_id = row.get(SOURCE_LOAN_ID_COL)
        raw_date = row.get(SOURCE_DATE_COL)
        raw_amount = row.get(SOURCE_AMOUNT_COL)

        # Validate Loan ID
        loan_id = str(raw_id).strip() if pd.notna(raw_id) else ""
        if not loan_id or loan_id.lower() == 'nan':
            missing_loanid_count += 1
            continue
        loan_id = loan_id.lower()

        # Validate amount
        amount = safe_string_to_float(raw_amount, f"Row {index}")
        if pd.isna(amount) or amount <= 0:
            parse_errors += 1
            continue

        # Validate date
        if pd.isna(raw_date) or str(raw_date).strip() == "":
            parse_errors += 1
            continue
        try:
            payment_date_obj = pd.to_datetime(
                raw_date, format="%m/%d/%Y", errors="raise"
            ).date()
        except (ValueError, TypeError):
            try:
                payment_date_obj = pd.to_datetime(raw_date, errors="raise").date()
                logger.warning(
                    f"Row {index}: Non-standard date '{raw_date}', parsed generally."
                )
            except (ValueError, TypeError):
                parse_errors += 1
                continue

        # Apply date filter
        if not fetch_all:
            if filter_start and payment_date_obj < filter_start:
                out_of_range_count += 1
                continue
            if filter_end and payment_date_obj > filter_end:
                out_of_range_count += 1
                continue

        # Create a key for the current row using the same logic as the existing payments
        # The date must be a string in YYYY-MM-DD format for consistency with the Supabase date type
        payment_date_str = payment_date_obj.strftime("%Y-%m-%d")
        
        # We also round the amount to the same precision to ensure accurate comparison
        rounded_amount = round(amount, 2)
        
        # The key is now a tuple of the actual values, not a formatted string
        current_key = (loan_id, payment_date_str, rounded_amount)
        
        if current_key in existing_payments:
            duplicate_count += 1
            continue

        # Add the new payment to the list to be inserted
        new_payments.append({
            "loan_id":        loan_id,
            "payment_date":   payment_date_str,
            "payment_amount": rounded_amount,
            "processed":      False,
            "processed_at":   None,
        })
        
        # Add the new payment to the set to prevent duplicates within the same run
        existing_payments.add(current_key)


    # Log summary
    logger.info(f"Found {len(new_payments)} new payments.")
    if parse_errors:
        logger.warning(f"Skipped {parse_errors} rows due to parse errors.")
    if missing_loanid_count:
        logger.warning(f"Skipped {missing_loanid_count} rows missing LoanID.")
    if duplicate_count:
        logger.info(f"Skipped {duplicate_count} duplicates.")
    if out_of_range_count:
        logger.info(f"Skipped {out_of_range_count} out-of-range.")

    # --- 4. Insert new payments into Supabase ---
    if not new_payments:
        logger.info("No new valid payments to insert.")
        return True

    sup_res = supabase.from_("payments_log").insert(new_payments).execute()
    if hasattr(sup_res, "error") and sup_res.error:
        logger.error(f"Failed inserting payments: {sup_res.error}")
        return False

    logger.info(f"Inserted {len(new_payments)} payments into Supabase.")
    return True