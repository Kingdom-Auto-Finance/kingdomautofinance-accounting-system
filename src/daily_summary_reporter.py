# src/daily_summary_reporter.py
import pandas as pd
from datetime import datetime, date 
import logging
from decimal import Decimal # Keep Decimal import if used by helpers (like safe_string_to_decimal)

# Import project modules using relative paths
from . import config 
from . import gutils 
# Import specific functions needed from gutils 
# Make sure these functions actually exist and are correctly defined in the latest gutils.py
from .gutils import safe_string_to_float, get_loan_ids_from_drive_folder, find_sheet_id_by_loan_id_in_folder, get_sheet_as_df 

logger = logging.getLogger(__name__)

# Helper functions like safe_string_to_float and get_loan_ids_from_drive_folder
# are assumed to be correctly imported from gutils.

def generate_and_update_daily_summary():
    """
    Generates a daily summary including payments, principal, interest, late fees, and credits,
    and updates a specific Google Sheet. Imports helpers from gutils.
    """
    logger.info("Starting Daily Summary Report generation (incl. Fees/Credits)...")
    all_payments_data = [] # List to hold DataFrames from each schedule

    # --- Initialize Google Sheets Client ---
    gs_client = None
    try: 
        gs_client = gutils.get_gspread_client()
    except ConnectionError as e: 
        logger.error(f"Failed GS client init for daily report: {e}. Aborting.")
        return False # Indicate failure

    # --- 1. Get Loan IDs from Configured Drive Folder ---
    folder_id = config.AMORTIZATION_SCHEDULES_FOLDER_ID
    if not folder_id or folder_id == "YOUR_GOOGLE_DRIVE_FOLDER_ID_HERE":
         logger.error("AMORTIZATION_SCHEDULES_FOLDER_ID not configured in config.py.")
         return False # Indicate failure
    
    # Use imported function from gutils
    loan_ids_to_process = get_loan_ids_from_drive_folder(folder_id) 
    if not loan_ids_to_process: 
        logger.warning("No LoanIDs (sheet names) found in configured Drive folder for daily report.")
        return False # Indicate nothing to process, but not necessarily an error

    # --- 2. Read and Process Data from All Schedules ---
    logger.info(f"Reading schedule data for {len(loan_ids_to_process)} loans...")
    for loan_id in loan_ids_to_process:
        # Use imported function from gutils to find sheet ID
        sheet_id = find_sheet_id_by_loan_id_in_folder(loan_id) 
        if not sheet_id: 
            # Warning logged by find_sheet_id... function
            logger.warning(f"Skipping LoanID '{loan_id}' for daily report (sheet not found).")
            continue # Skip to next loan

        logger.debug(f"Reading schedule for LoanID: {loan_id}, SheetID: {sheet_id}")
        # Use imported function from gutils to read sheet
        schedule_df_raw = get_sheet_as_df(gs_client, sheet_id, "Schedule") 
        if schedule_df_raw is None or schedule_df_raw.empty: 
            logger.warning(f"Empty or unreadable schedule for {loan_id}. Skipping.")
            continue
        
        schedule_df = schedule_df_raw.copy()
        # Standardize column headers to lowercase for reliable access
        schedule_df.columns = [str(col).strip().lower() for col in schedule_df.columns]

        # Define expected lowercase columns needed for summary
        ACTUAL_PMT_DATE_COL = 'actualpaymentdate'
        ACTUAL_PMT_AMT_COL = 'actualpaymentamount'
        PRINCIPAL_PAID_COL = 'principalpaid'
        INTEREST_PAID_COL = 'interestpaid'
        LATE_FEE_COL_SCHED = 'latefee' # Column name in the schedule sheet
        CREDIT_APPLIED_COL_SCHED = 'creditapplied' # Column name in the schedule sheet

        # Check if essential columns exist
        required_cols = [ACTUAL_PMT_DATE_COL, ACTUAL_PMT_AMT_COL, PRINCIPAL_PAID_COL, INTEREST_PAID_COL, LATE_FEE_COL_SCHED, CREDIT_APPLIED_COL_SCHED]
        missing_cols = [col for col in required_cols if col not in schedule_df.columns]
        if missing_cols:
             # Log warning but try to proceed if only optional cols (Fee/Credit) are missing
            essential_missing = [c for c in missing_cols if c in [ACTUAL_PMT_DATE_COL, ACTUAL_PMT_AMT_COL, PRINCIPAL_PAID_COL, INTEREST_PAID_COL]]
            if essential_missing:
                logger.warning(f"Schedule for {loan_id} missing ESSENTIAL columns: {essential_missing}. Skipping.")
                continue
            else:
                logger.warning(f"Schedule for {loan_id} missing optional columns: {missing_cols}. Will treat as 0.")
                # Add missing optional columns filled with 0
                if LATE_FEE_COL_SCHED in missing_cols: schedule_df[LATE_FEE_COL_SCHED] = 0.0
                if CREDIT_APPLIED_COL_SCHED in missing_cols: schedule_df[CREDIT_APPLIED_COL_SCHED] = 0.0


        # --- Data Type Conversion and Cleaning ---
        # Select only needed columns *after* checking/adding missing ones
        schedule_df = schedule_df[required_cols].copy() 
        
        # 1. Parse Date column
        schedule_df[ACTUAL_PMT_DATE_COL] = pd.to_datetime(schedule_df[ACTUAL_PMT_DATE_COL], errors='coerce').dt.date
        schedule_df.dropna(subset=[ACTUAL_PMT_DATE_COL], inplace=True) # Critical: drop rows where date is invalid

        # 2. Clean and parse Numeric columns using imported helper
        numeric_cols_to_parse = [ACTUAL_PMT_AMT_COL, PRINCIPAL_PAID_COL, INTEREST_PAID_COL, LATE_FEE_COL_SCHED, CREDIT_APPLIED_COL_SCHED]
        for col in numeric_cols_to_parse:
            schedule_df[col] = schedule_df[col].apply(lambda x: safe_string_to_float(x, context=f"Daily Report Col {col} for {loan_id}"))
            # Coerce to numeric again to ensure type, errors remain NA from helper
            schedule_df[col] = pd.to_numeric(schedule_df[col], errors='coerce') 

        # 3. Filter out rows without a valid positive payment amount
        schedule_df = schedule_df[schedule_df[ACTUAL_PMT_AMT_COL].notna() & (schedule_df[ACTUAL_PMT_AMT_COL] > 0)]
        
        if not schedule_df.empty: 
            all_payments_data.append(schedule_df)
        else: 
            logger.debug(f"No valid payment rows found for {loan_id} after cleaning/filtering.")

    # --- Handle case where no data was collected ---
    if not all_payments_data: 
        logger.warning("No valid payment data found across all loan schedules after processing.")
        # Update sheet with headers only to clear it? Or do nothing? Let's do nothing.
        return False # Indicate nothing was processed or written

    # --- 3. Aggregate Data by Date ---
    logger.info("Aggregating payment data by date...")
    try:
        combined_df = pd.concat(all_payments_data, ignore_index=True)
        
        # Group by date and sum the required columns
        # sum() skips NaN by default. Convert resulting NaNs in sums to 0.
        daily_summary = combined_df.groupby(ACTUAL_PMT_DATE_COL).agg(
            # Column name in agg matches the final desired column name
            PaymentsReceived=(ACTUAL_PMT_AMT_COL, 'sum'),
            PrincipalReceived=(PRINCIPAL_PAID_COL, 'sum'),
            InterestReceived=(INTEREST_PAID_COL, 'sum'),
            LateFeesReceived=(LATE_FEE_COL_SCHED, 'sum'), 
            CreditAdded=(CREDIT_APPLIED_COL_SCHED, 'sum') 
        ).fillna(0.0).reset_index() # Fill NaN sums with 0.0 and make date a column

        # Rename date column
        daily_summary.rename(columns={ACTUAL_PMT_DATE_COL: 'Date'}, inplace=True)
        # Format the Date column as YYYY-MM-DD string for writing
        daily_summary['Date'] = pd.to_datetime(daily_summary['Date']).dt.strftime('%Y-%m-%d') 
        
        # Ensure specific column order matching the sheet
        final_columns = ['Date', 'PaymentsReceived', 'PrincipalReceived', 'InterestReceived', 'LateFeesReceived', 'CreditAdded']
        # Reindex to add any missing columns (if aggregation was empty) and ensure order
        daily_summary = daily_summary.reindex(columns=final_columns, fill_value=0.0) 
                
        daily_summary = daily_summary.sort_values(by='Date', ascending=True)
        logger.info(f"Generated daily summary with {len(daily_summary)} date entries.")
    except Exception as agg_error: 
        logger.error(f"Error aggregating daily summary: {agg_error}", exc_info=True)
        return False # Indicate failure

    # --- 4. Update Target Google Sheet ---
    target_sheet_id = config.DAILY_SUMMARY_REPORT_SHEET_ID
    target_sheet_name = "Sheet1" # Default sheet name
    if not target_sheet_id or target_sheet_id == "YOUR_DAILY_SUMMARY_REPORT_SHEET_ID_HERE": 
        logger.error("Daily summary sheet ID not configured in config.py.")
        return False # Indicate failure

    logger.info(f"Attempting update Google Sheet ID: {target_sheet_id}, Worksheet: {target_sheet_name}")
    # Use imported function from gutils
    success = gutils.update_worksheet_from_df(gs_client, target_sheet_id, target_sheet_name, daily_summary)

    if success: 
        logger.info("Successfully updated the Daily Summary Report Google Sheet.")
        return True # Indicate success
    else: 
        logger.error("Failed to update the Daily Summary Report Google Sheet.")
        return False # Indicate failure