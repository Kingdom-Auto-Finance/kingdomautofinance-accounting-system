import pandas as pd
from datetime import datetime, timedelta
import logging
from . import config
# Import gutils and specific helpers needed
from . import gutils 
from .gutils import safe_string_to_float 

logger = logging.getLogger(__name__)

# --- Constants for Column Names ---
# ** ACTION: User MUST verify these match the exact headers in the SOURCE sheet **
SOURCE_LOAN_ID_COL = "Loan ID"       # Example Name
SOURCE_DATE_COL = "Payment Date"      # Example Name (MM/DD/YYYY)
SOURCE_AMOUNT_COL = "Amount Paid"     # Example Name ($XXX,XXX.XX)

# --- Constants for Target Column Names (Lowercase standard) ---
TARGET_LOAN_ID_COL_LOWER = 'loanid'
TARGET_DATE_COL_LOWER = 'paymentdate'
TARGET_AMOUNT_COL_LOWER = 'paymentamount'
# TARGET_STATUS_COL_LOWER = 'processedstatus' # Defined but not strictly needed here
# TARGET_TIMESTAMP_COL_LOWER = 'processedtimestamp' # Defined but not strictly needed here

# --- CONSTANT FOR SOURCE SHEET TAB NAME ---
SOURCE_SHEET_TAB_NAME = "Payments" # Use the correct tab name

def fetch_and_populate_payments(start_date_str=None, end_date_str=None, fetch_all=False, fetch_recent_days=None):
    """
    Fetches payment data from source ('Payments Received' tab), transforms, 
    checks duplicates, appends new valid payments (with LoanID) to target log.
    """
    # Determine run mode for logging
    run_mode_log = ""
    if fetch_recent_days: run_mode_log = f"Recent {fetch_recent_days} days"
    elif fetch_all: run_mode_log = "All (checking duplicates)"
    elif start_date_str or end_date_str: run_mode_log = f"Range {start_date_str or 'any'} - {end_date_str or 'any'}"
    else: run_mode_log = "Default (Recent 7 days)" 
    logger.info(f"Starting payment fetch. Mode: {run_mode_log}")

    gs_client = None
    try: gs_client = gutils.get_gspread_client()
    except ConnectionError as e: logger.error(f"Failed GS client init: {e}. Aborting fetch."); return False

    # --- 1. Read Source Sheet ---
    source_sheet_id = config.SOURCE_PAYMENTS_SHEET_ID
    logger.info(f"Reading source payment data from Sheet ID: {source_sheet_id}, Tab: '{SOURCE_SHEET_TAB_NAME}'")
    df_source = gutils.get_sheet_as_df(gs_client, source_sheet_id, SOURCE_SHEET_TAB_NAME) 

    if df_source is None or df_source.empty: