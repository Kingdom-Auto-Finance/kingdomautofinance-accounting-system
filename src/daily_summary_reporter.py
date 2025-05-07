# src/daily_summary_reporter.py
import pandas as pd
from datetime import datetime, date 
import logging
from . import config 
# --- Import helpers from gutils ---
from . import gutils 
# Import specific functions needed from gutils
from .gutils import safe_string_to_float, get_loan_ids_from_drive_folder, find_sheet_id_by_loan_id_in_folder, get_sheet_as_df 

logger = logging.getLogger(__name__)

# Helper functions are now imported from gutils, no local definitions needed


def generate_and_update_daily_summary():
    """
    Generates a daily summary of payments received, principal, and interest,
    and updates a specific Google Sheet. Imports helpers from gutils.
    """
    logger.info("Starting Daily Summary Report generation...")
    all_payments_data = [] 

    gs_client = None
    try: gs_client = gutils.get_gspread_client()
    except ConnectionError as e: logger.error(f"Failed GS client init: {e}. Aborting."); return False

    # --- 1. Get Loan IDs ---
    folder_id = config.AMORTIZATION_SCHEDULES_FOLDER_ID
    if not folder_id or folder_id == "YOUR_GOOGLE_DRIVE_FOLDER_ID_HERE":
         logger.error("AMORTIZATION_SCHEDULES_FOLDER_ID not configured."); return False
    
    # Use imported function from gutils
    loan_ids_to_process = get_loan_ids_from_drive_folder(folder_id) 
    if not loan_ids_to_process: logger.warning("No LoanIDs found for daily report."); return False

    # --- 2. Read Data from All Schedules ---
    logger.info(f"Reading schedule data for {len(loan_ids_to_process)} loans...")
    for loan_id in loan_ids_to_process:
        # Use imported function from gutils
        sheet_id = find_sheet_id_by_loan_id_in_folder(loan_id) 
        if not sheet_id: logger.warning(f"Skipping LoanID '{loan_id}' (sheet not found)."); continue 

        logger.debug(f"Reading schedule for LoanID: {loan_id}")
        # Use imported function from gutils
        schedule_df_raw = get_sheet_as_df(gs_client, sheet_id, "Schedule") 
        if schedule_df_raw is None or schedule_df_raw.empty: logger.warning(f"Empty/unreadable schedule for {loan_id}."); continue
        
        schedule_df = schedule_df_raw.copy()
        schedule_df.columns = [str(col).strip().lower() for col in schedule_df.columns]

        ACTUAL_PMT_DATE_COL = 'actualpaymentdate'; ACTUAL_PMT_AMT_COL = 'actualpaymentamount';
        PRINCIPAL_PAID_COL = 'principalpaid'; INTEREST_PAID_COL = 'interestpaid';

        required_cols = [ACTUAL_PMT_DATE_COL, ACTUAL_PMT_AMT_COL, PRINCIPAL_PAID_COL, INTEREST_PAID_COL]
        if not all(col in schedule_df.columns for col in required_cols):
            logger.warning(f"Schedule for {loan_id} missing required columns. Skipping."); continue

        schedule_df = schedule_df[required_cols].copy() 
        schedule_df[ACTUAL_PMT_DATE_COL] = pd.to_datetime(schedule_df[ACTUAL_PMT_DATE_COL], errors='coerce').dt.date
        schedule_df.dropna(subset=[ACTUAL_PMT_DATE_COL], inplace=True)

        # Use imported safe_string_to_float from gutils
        schedule_df[ACTUAL_PMT_AMT_COL] = schedule_df[ACTUAL_PMT_AMT_COL].apply(lambda x: safe_string_to_float(x))
        schedule_df[PRINCIPAL_PAID_COL] = schedule_df[PRINCIPAL_PAID_COL].apply(lambda x: safe_string_to_float(x))
        schedule_df[INTEREST_PAID_COL] = schedule_df[INTEREST_PAID_COL].apply(lambda x: safe_string_to_float(x))

        # Convert columns to numeric after cleaning attempt, coerce errors to NaN
        schedule_df[ACTUAL_PMT_AMT_COL] = pd.to_numeric(schedule_df[ACTUAL_PMT_AMT_COL], errors='coerce')
        schedule_df[PRINCIPAL_PAID_COL] = pd.to_numeric(schedule_df[PRINCIPAL_PAID_COL], errors='coerce')
        schedule_df[INTEREST_PAID_COL] = pd.to_numeric(schedule_df[INTEREST_PAID_COL], errors='coerce')
        
        # Filter out rows where numeric conversion failed or amount is zero/negative
        schedule_df = schedule_df[schedule_df[ACTUAL_PMT_AMT_COL].notna() & (schedule_df[ACTUAL_PMT_AMT_COL] > 0)]
        
        if not schedule_df.empty: all_payments_data.append(schedule_df)
        else: logger.debug(f"No valid payment rows found for {loan_id}")

    if not all_payments_data: logger.warning("No valid payment data found across all schedules."); return False

    # --- 3. Aggregate Data by Date ---
    logger.info("Aggregating payment data by date...")
    try:
        combined_df = pd.concat(all_payments_data, ignore_index=True)
        # Group by date (which is already date objects) and sum the required columns (which are float or NaN)
        # The sum() method in pandas skips NaN by default.
        daily_summary = combined_df.groupby(ACTUAL_PMT_DATE_COL).agg(
            PaymentsReceived=(ACTUAL_PMT_AMT_COL, 'sum'),
            PrincipalReceived=(PRINCIPAL_PAID_COL, 'sum'),
            InterestReceived=(INTEREST_PAID_COL, 'sum')
        ).reset_index() 

        daily_summary.rename(columns={ACTUAL_PMT_DATE_COL: 'Date'}, inplace=True)
        daily_summary['Date'] = pd.to_datetime(daily_summary['Date']).dt.strftime('%Y-%m-%d') # Convert date back to string for writing
        final_columns = ['Date', 'PaymentsReceived', 'PrincipalReceived', 'InterestReceived']
        # Reindex to ensure columns exist even if aggregation results in empty columns (unlikely with sum)
        daily_summary = daily_summary.reindex(columns=final_columns, fill_value=0.0)
        # Fill any remaining NaNs from sum (if all inputs were NaN) with 0.0
        daily_summary.fillna(0.0, inplace=True)
        
        daily_summary = daily_summary.sort_values(by='Date', ascending=True)
        logger.info(f"Generated daily summary with {len(daily_summary)} date entries.")
    except Exception as agg_error: logger.error(f"Error aggregating daily summary: {agg_error}", exc_info=True); return False

    # --- 4. Update Target Google Sheet ---
    target_sheet_id = config.DAILY_SUMMARY_REPORT_SHEET_ID
    target_sheet_name = "Sheet1" 
    if not target_sheet_id or target_sheet_id == "YOUR_DAILY_SUMMARY_REPORT_SHEET_ID_HERE": logger.error("Daily summary sheet ID not configured."); return False

    logger.info(f"Attempting update Google Sheet ID: {target_sheet_id}, Worksheet: {target_sheet_name}")
    # Use imported function from gutils
    success = gutils.update_worksheet_from_df(gs_client, target_sheet_id, target_sheet_name, daily_summary)

    if success: logger.info("Successfully updated Daily Summary Report Sheet."); return True
    else: logger.error("Failed to update Daily Summary Report Sheet."); return False