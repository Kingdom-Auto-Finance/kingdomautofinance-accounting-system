# src/daily_summary_reporter.py
import pandas as pd
from datetime import datetime, date 
import logging
from decimal import Decimal # Keep Decimal import if used by helpers 

# Import project modules using relative paths
from . import config 
from . import gutils 
# Import specific functions needed from gutils 
# Ensure these exist in the latest gutils.py
from .gutils import safe_string_to_float, get_loan_ids_from_drive_folder, find_sheet_id_by_loan_id_in_folder, get_sheet_as_df 

logger = logging.getLogger(__name__)

# Helper functions safe_string_to_float and get_loan_ids_from_drive_folder are imported

def generate_and_update_daily_summary(since_date_str=None): # Argument added
    """
    Generates/updates daily summary sheet. Handles --since flag for filtering.
    """
    filter_start_date = None # Initialize filter date
    if since_date_str:
        logger.info(f"Starting Daily Summary Report generation SINCE {since_date_str}...")
        try:
            filter_start_date = datetime.strptime(since_date_str, "%Y-%m-%d").date()
            logger.info(f"Filtering summary to include dates on or after: {filter_start_date}")
        except ValueError:
            logger.error(f"Invalid format for --since date: '{since_date_str}'. Expected YYYY-MM-DD. Aborting.")
            return False # Indicate failure due to bad argument
    else:
        logger.info("Starting Daily Summary Report generation for ALL DATES...")

    all_payments_data = [] # List to hold DataFrames

    # --- Initialize Google Sheets Client ---
    gs_client = None
    try: gs_client = gutils.get_gspread_client()
    except ConnectionError as e: logger.error(f"Failed GS client init: {e}. Aborting."); return False

    # --- 1. Get Loan IDs ---
    folder_id = config.AMORTIZATION_SCHEDULES_FOLDER_ID
    if not folder_id or folder_id == "YOUR_GOOGLE_DRIVE_FOLDER_ID_HERE":
         logger.error("AMORTIZATION_SCHEDULES_FOLDER_ID not configured."); return False
    
    loan_ids_to_process = get_loan_ids_from_drive_folder(folder_id) 
    if not loan_ids_to_process: logger.warning("No LoanIDs found for daily report."); return False

    # --- 2. Read Data from All Schedules ---
    logger.info(f"Reading schedule data for {len(loan_ids_to_process)} loans...")
    for loan_id in loan_ids_to_process:
        sheet_id = find_sheet_id_by_loan_id_in_folder(loan_id) 
        if not sheet_id: logger.warning(f"Skipping LoanID '{loan_id}' (sheet not found)."); continue 

        logger.debug(f"Reading schedule for LoanID: {loan_id}")
        schedule_df_raw = get_sheet_as_df(gs_client, sheet_id, "Schedule") 
        if schedule_df_raw is None or schedule_df_raw.empty: logger.warning(f"Empty/unreadable schedule for {loan_id}."); continue
        
        schedule_df = schedule_df_raw.copy()
        schedule_df.columns = [str(col).strip().lower() for col in schedule_df.columns]

        # Define expected columns
        ACTUAL_PMT_DATE_COL = 'actualpaymentdate'; ACTUAL_PMT_AMT_COL = 'actualpaymentamount';
        PRINCIPAL_PAID_COL = 'principalpaid'; INTEREST_PAID_COL = 'interestpaid';
        LATE_FEE_COL_SCHED = 'latefee'; CREDIT_APPLIED_COL_SCHED = 'creditapplied';

        required_cols = [ACTUAL_PMT_DATE_COL, ACTUAL_PMT_AMT_COL, PRINCIPAL_PAID_COL, INTEREST_PAID_COL, LATE_FEE_COL_SCHED, CREDIT_APPLIED_COL_SCHED]
        present_cols = [] # Track columns actually present or added
        
        # Check for essential columns first
        essential_cols = [ACTUAL_PMT_DATE_COL, ACTUAL_PMT_AMT_COL, PRINCIPAL_PAID_COL, INTEREST_PAID_COL]
        missing_essential = [col for col in essential_cols if col not in schedule_df.columns]
        if missing_essential:
             logger.warning(f"Schedule for {loan_id} missing ESSENTIAL cols: {missing_essential}. Skipping.")
             continue

        # Add optional columns if missing, filling with 0
        if LATE_FEE_COL_SCHED not in schedule_df.columns: 
             logger.warning(f"Schedule {loan_id} missing '{LATE_FEE_COL_SCHED}'. Adding column with 0.")
             schedule_df[LATE_FEE_COL_SCHED] = 0.0
        if CREDIT_APPLIED_COL_SCHED not in schedule_df.columns:
             logger.warning(f"Schedule {loan_id} missing '{CREDIT_APPLIED_COL_SCHED}'. Adding column with 0.")
             schedule_df[CREDIT_APPLIED_COL_SCHED] = 0.0
             
        # Select only the required columns now guaranteed to exist
        schedule_df = schedule_df[required_cols].copy() 
        
        # --- Data Type Conversion and Cleaning ---
        schedule_df[ACTUAL_PMT_DATE_COL] = pd.to_datetime(schedule_df[ACTUAL_PMT_DATE_COL], errors='coerce').dt.date
        schedule_df.dropna(subset=[ACTUAL_PMT_DATE_COL], inplace=True) # Drop rows where date is invalid AFTER parsing

        numeric_cols_to_parse = [ACTUAL_PMT_AMT_COL, PRINCIPAL_PAID_COL, INTEREST_PAID_COL, LATE_FEE_COL_SCHED, CREDIT_APPLIED_COL_SCHED]
        for col in numeric_cols_to_parse:
            schedule_df[col] = schedule_df[col].apply(lambda x: safe_string_to_float(x, context=f"Daily Report Col {col} for {loan_id}"))
            schedule_df[col] = pd.to_numeric(schedule_df[col], errors='coerce') 

        # Filter out rows without positive payment AFTER cleaning
        schedule_df = schedule_df[schedule_df[ACTUAL_PMT_AMT_COL].notna() & (schedule_df[ACTUAL_PMT_AMT_COL] > 0)]
        
        if not schedule_df.empty: all_payments_data.append(schedule_df)
        else: logger.debug(f"No valid payment rows found for {loan_id} after cleaning/filtering.")

    if not all_payments_data: logger.warning("No valid payment data found across all loan schedules."); return False

    # --- 3. Aggregate Data by Date ---
    logger.info("Aggregating payment data by date...")
    try:
        combined_df = pd.concat(all_payments_data, ignore_index=True)
        
        daily_summary_all = combined_df.groupby(ACTUAL_PMT_DATE_COL).agg(
            PaymentsReceived=(ACTUAL_PMT_AMT_COL, 'sum'),
            PrincipalReceived=(PRINCIPAL_PAID_COL, 'sum'),
            InterestReceived=(INTEREST_PAID_COL, 'sum'),
            LateFeesReceived=(LATE_FEE_COL_SCHED, 'sum'), 
            CreditAdded=(CREDIT_APPLIED_COL_SCHED, 'sum') 
        ).fillna(0.0).reset_index() # Fill NaN sums with 0.0

        daily_summary_all.rename(columns={ACTUAL_PMT_DATE_COL: 'Date'}, inplace=True)
        
        # Convert Date column back to date objects for filtering comparison
        daily_summary_all['Date_Obj'] = pd.to_datetime(daily_summary_all['Date']).dt.date

        # --- FILTERING BASED ON --since ---
        if filter_start_date:
            # Keep rows where the date object is >= filter_start_date
            daily_summary_to_write = daily_summary_all[daily_summary_all['Date_Obj'] >= filter_start_date].copy()
            logger.info(f"Filtered daily summary to {len(daily_summary_to_write)} entries on or after {filter_start_date}.")
        else:
            daily_summary_to_write = daily_summary_all.copy()
            logger.info(f"Generated daily summary with {len(daily_summary_to_write)} total date entries.")
        
        # Drop the temporary Date_Obj column before writing
        if 'Date_Obj' in daily_summary_to_write.columns: # Check if it exists before dropping
            daily_summary_to_write.drop(columns=['Date_Obj'], inplace=True)

        # Format Date string and ensure column order
        daily_summary_to_write['Date'] = pd.to_datetime(daily_summary_to_write['Date']).dt.strftime('%Y-%m-%d') 
        final_columns = ['Date', 'PaymentsReceived', 'PrincipalReceived', 'InterestReceived', 'LateFeesReceived', 'CreditAdded']
        # Reindex to ensure all target columns exist and are in order
        daily_summary_to_write = daily_summary_to_write.reindex(columns=final_columns, fill_value=0.0) 
        
        # Convert summary values to float with 2 decimal places for cleaner output (optional)
        for col in ['PaymentsReceived', 'PrincipalReceived', 'InterestReceived', 'LateFeesReceived', 'CreditAdded']:
            daily_summary_to_write[col] = daily_summary_to_write[col].round(2)

        daily_summary_to_write = daily_summary_to_write.sort_values(by='Date', ascending=True)
        
    except Exception as agg_error: logger.error(f"Error aggregating/filtering daily summary: {agg_error}", exc_info=True); return False

    # --- 4. Update Target Google Sheet ---
    if daily_summary_to_write.empty:
        logger.info(f"No daily summary data found for the specified period (since {since_date_str}). No update performed.")
        # Decide if clearing the sheet is desired if empty after filtering. 
        # Current gutils.update clears sheet if df is empty. Maybe add a check here?
        # If filter_start_date was used AND result is empty, likely don't want to clear sheet.
        if filter_start_date:
             logger.info("Since filter resulted in no data, skipping sheet update to avoid clearing history.")
             return True # Consider this a success state for the filtered run
        # If no filter was used and it's empty, proceed to clear/update (gutils handles empty df)

    target_sheet_id = config.DAILY_SUMMARY_REPORT_SHEET_ID
    target_sheet_name = "Sheet1" # Default sheet name
    if not target_sheet_id or target_sheet_id == "YOUR_DAILY_SUMMARY_REPORT_SHEET_ID_HERE": logger.error("Daily summary sheet ID not configured."); return False

    logger.info(f"Attempting to OVERWRITE Google Sheet ID: {target_sheet_id}, Worksheet: {target_sheet_name} with {len(daily_summary_to_write)} rows.")
    success = gutils.update_worksheet_from_df(gs_client, target_sheet_id, target_sheet_name, daily_summary_to_write)

    if success: logger.info("Successfully updated Daily Summary Report Sheet."); return True
    else: logger.error("Failed to update Daily Summary Report Sheet."); return False