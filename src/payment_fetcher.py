# src/payment_fetcher.py
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
    try: gs_client = safe_gspread_request(gutils.get_gspread_client)
    except ConnectionError as e: logger.error(f"Failed GS client init: {e}. Aborting fetch."); return False

    # --- 1. Read Source Sheet ---
    source_sheet_id = config.SOURCE_PAYMENTS_SHEET_ID
    logger.info(f"Reading source payment data from Sheet ID: {source_sheet_id}, Tab: '{SOURCE_SHEET_TAB_NAME}'")
    df_source = safe_gspread_request(lambda: gutils.get_sheet_as_df(gs_client, source_sheet_id, SOURCE_SHEET_TAB_NAME))
    
    if df_source is None or df_source.empty:
        logger.warning(f"Source payment sheet ('{SOURCE_SHEET_TAB_NAME}' tab) empty/unreadable.")
        return False 

    # Verify required source columns exist using the defined constants
    required_source_cols = [SOURCE_LOAN_ID_COL, SOURCE_DATE_COL, SOURCE_AMOUNT_COL]
    missing_source_cols = [col for col in required_source_cols if col not in df_source.columns]
    if missing_source_cols:
        logger.error(f"Source sheet missing required columns: {missing_source_cols}. Headers: {df_source.columns.tolist()}. Aborting.")
        return False
        
    # --- 2. Read Target Payments Log (for duplicate check) ---
    target_sheet_id = config.PAYMENTS_LOG_SHEET_ID
    target_sheet_name = "Sheet1" # Assume target log is always Sheet1
    logger.info(f"Reading target log from Sheet ID: {target_sheet_id}, Tab: '{target_sheet_name}' for duplicate check.")
    df_target_log_raw = safe_gspread_request(lambda: gutils.get_sheet_as_df(gs_client, target_sheet_id, target_sheet_name))

    existing_payments = set() # Stores unique keys: LOANIDUPPER_YYYY-MM-DD_AmountString(XX.XX)
    if df_target_log_raw is not None and not df_target_log_raw.empty:
        df_target_log = df_target_log_raw.copy()
        target_header_map = {str(h).strip().lower(): h for h in df_target_log.columns}
        # Find original headers in target sheet using lowercase standard names
        target_loanid_hdr = target_header_map.get(TARGET_LOAN_ID_COL_LOWER)
        target_date_hdr = target_header_map.get(TARGET_DATE_COL_LOWER)
        target_amount_hdr = target_header_map.get(TARGET_AMOUNT_COL_LOWER)

        if target_loanid_hdr and target_date_hdr and target_amount_hdr:
             logger.debug(f"Using target log columns for duplicate check: '{target_loanid_hdr}', '{target_date_hdr}', '{target_amount_hdr}'")
             for index, target_row in df_target_log.iterrows():
                  # Parse target log data robustly for key creation
                  loan_id = str(target_row.get(target_loanid_hdr, '')).strip().upper()
                  date_str = None
                  try: 
                      # Read target date, try to parse as datetime, convert to YYYY-MM-DD string
                      dt_obj = pd.to_datetime(target_row.get(target_date_hdr), errors='coerce').date()
                      if pd.notna(dt_obj): date_str = dt_obj.strftime('%Y-%m-%d')
                  except Exception: pass # Ignore errors converting date for key generation

                  amount_fl = safe_string_to_float(target_row.get(target_amount_hdr), f"Target Log Row {index}")

                  # Only add key if all parts are valid
                  if loan_id and date_str and pd.notna(amount_fl):
                       amount_str_fmt = f"{amount_fl:.2f}" # Format amount consistently (e.g., 150.00)
                       key = f"{loan_id}_{date_str}_{amount_str_fmt}"
                       existing_payments.add(key)
                 
             logger.info(f"Created {len(existing_payments)} unique keys from existing target log.")
        else:
            missing_target_cols = [h for h_low, h in [(TARGET_LOAN_ID_COL_LOWER, target_loanid_hdr), (TARGET_DATE_COL_LOWER, target_date_hdr), (TARGET_AMOUNT_COL_LOWER, target_amount_hdr)] if not h]
            logger.warning(f"Target log missing required columns ({missing_target_cols}) for duplicate check. Proceeding without check.")
    else:
         logger.info("Target payments log empty/unreadable. Duplicate check skipped.")


    # --- 3. Parse, Transform, Filter, and Prepare Source Data ---
    new_payments_to_add_list = [] # Stores lists: [LoanIDUpper, DateStrISO, AmountStrFmt, Status, Timestamp]
    parse_errors = 0; duplicate_count = 0; out_of_range_count = 0; missing_loanid_count = 0
    
    # Determine date range filter
    filter_start_date = None; filter_end_date = None
    if fetch_recent_days:
        try:
            filter_end_date = datetime.now().date(); filter_start_date = filter_end_date - timedelta(days=int(fetch_recent_days)-1)
            logger.info(f"Filtering source data FROM {filter_start_date} TO {filter_end_date}.")
        except (ValueError, TypeError): logger.error(f"Invalid recent_days value: {fetch_recent_days}. No date filter applied."); fetch_all = True 
    elif not fetch_all: 
        try:
            if start_date_str: filter_start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            if end_date_str: filter_end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
            logger.info(f"Filtering source data FROM {filter_start_date or 'beginning'} TO {filter_end_date or 'end'}.")
        except ValueError: logger.error(f"Invalid date format in range: {start_date_str}/{end_date_str}. No date filter applied."); fetch_all = True 
            
    for index, source_row in df_source.iterrows():
        # Get raw values using constants
        raw_loan_id = source_row.get(SOURCE_LOAN_ID_COL)
        raw_date = source_row.get(SOURCE_DATE_COL)
        raw_amount = source_row.get(SOURCE_AMOUNT_COL)

        # --- Parse and Validate LoanID ---
        loan_id_orig = str(raw_loan_id).strip() if pd.notna(raw_loan_id) else ""
        loan_id_upper = loan_id_orig.upper()
        # ** Skip row if LoanID is missing or 'NAN' **
        if not loan_id_orig or loan_id_upper == 'NAN':
            logger.debug(f"Source Row {index}: Invalid or missing LoanID ('{raw_loan_id}'). Skipping row.")
            missing_loanid_count += 1
            continue 
            
        # --- Parse and Validate Amount ---
        amount_float = safe_string_to_float(raw_amount, f"Source Row {index}")
        if pd.isna(amount_float) or amount_float <= 0:
            logger.debug(f"Source Row {index}, LoanID {loan_id_orig}: Invalid/Non-positive Amount '{raw_amount}'. Skipping.")
            parse_errors += 1
            continue

        # --- Parse and Validate Date (MM/DD/YYYY specific) ---
        payment_date = pd.NaT # Represents date object or NaT
        if pd.isna(raw_date) or str(raw_date).strip() == "":
             logger.debug(f"Source Row {index}, LoanID {loan_id_orig}: Missing Date. Skipping.")
             parse_errors += 1
             continue
        try:
             payment_date = pd.to_datetime(raw_date, format='%m/%d/%Y', errors='raise').date() 
        except (ValueError, TypeError):
            try: 
                 payment_date = pd.to_datetime(raw_date, errors='raise').date()
                 logger.warning(f"Source Row {index}, LoanID {loan_id_orig}: Date '{raw_date}' not MM/DD/YYYY. Used general parser.")
            except (ValueError, TypeError):
                 logger.warning(f"Source Row {index}, LoanID {loan_id_orig}: Invalid date '{raw_date}'. Skipping.")
                 parse_errors += 1
                 continue 

        # --- Apply Date Filter (if not fetching all) ---
        if not fetch_all:
             if filter_start_date and payment_date < filter_start_date: out_of_range_count += 1; continue
             if filter_end_date and payment_date > filter_end_date: out_of_range_count += 1; continue

        # --- Check for Duplicates ---
        payment_date_str_iso = payment_date.strftime('%Y-%m-%d') 
        amount_str_fmt = f"{amount_float:.2f}"
        payment_key = f"{loan_id_upper}_{payment_date_str_iso}_{amount_str_fmt}" # Use uppercase ID for key consistent with target log check
        
        if payment_key in existing_payments:
            duplicate_count += 1
            logger.debug(f"Skipping duplicate payment: {payment_key}")
            continue

        # --- Prepare row for appending (matches TARGET sheet structure) ---
        # Order: LoanID, PaymentDate, PaymentAmount, ProcessedStatus, ProcessedTimestamp
        new_row_data = [
            loan_id_upper,              # Use standardized uppercase LoanID
            payment_date_str_iso,       # Use YYYY-MM-DD format
            f"{amount_float:.2f}",      # Use formatted amount string (USER_ENTERED will handle type)
            "Pending",                  # Default status
            ""                          # Empty timestamp
        ]
        new_payments_to_add_list.append(new_row_data)
        existing_payments.add(payment_key) # Add key to prevent duplicates from source in same run

    logger.info(f"Source data processing complete. Found {len(new_payments_to_add_list)} new payments to add.")
    if parse_errors > 0: logger.warning(f"Skipped {parse_errors} rows due to parsing errors (date/amount).")
    if missing_loanid_count > 0: logger.warning(f"Skipped {missing_loanid_count} rows due to missing/invalid LoanID.")
    if duplicate_count > 0: logger.info(f"Skipped {duplicate_count} duplicate payments found in target log.")
    if out_of_range_count > 0: logger.info(f"Skipped {out_of_range_count} payments outside specified date range.")


    # --- 4. Append New Payments to Target Log ---
    if not new_payments_to_add_list:
        logger.info("No new valid payments found to add to the log after filtering/duplicate checks.")
        return True # Success, nothing to add

    logger.info(f"Attempting to append {len(new_payments_to_add_list)} new payments to target log sheet '{target_sheet_name}'.")
    
    # Use gutils append function
    success = gutils.append_rows_to_sheet(gs_client, target_sheet_id, target_sheet_name, new_payments_to_add_list)

    if success:
        logger.info(f"Successfully appended {len(new_payments_to_add_list)} rows to Payments Log.")
        return True
    else:
        logger.error("Failed to append new payments to the Payments Log sheet.")
        return False