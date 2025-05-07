# src/daily_summary_reporter.py
import pandas as pd
from datetime import datetime, date, timedelta 
import logging
from decimal import Decimal 
# --- Import project modules ---
from . import config 
from . import gutils 
# Import specific functions needed from gutils 
from .gutils import safe_string_to_float, get_loan_ids_from_drive_folder, find_sheet_id_by_loan_id_in_folder, get_sheet_as_df 

logger = logging.getLogger(__name__)

# Helper functions are imported from gutils, no local definitions needed here

def generate_and_update_daily_summary(full_rebuild=False): # Argument added, default is False
    """
    Generates/updates daily summary sheet. 
    Default (full_rebuild=False): Reads existing report, calculates new data, merges, overwrites.
    If full_rebuild=True: Calculates all history and overwrites.
    """
    run_mode = "Full Rebuild" if full_rebuild else "Incremental Update"
    logger.info(f"Starting Daily Summary Report generation ({run_mode})...")
        
    all_payments_data = [] # List to hold DataFrames from each schedule

    # --- Initialize Google Sheets Client ---
    gs_client = None
    try: gs_client = gutils.get_gspread_client()
    except ConnectionError as e: logger.error(f"Failed GS client init: {e}. Aborting."); return False

    target_sheet_id = config.DAILY_SUMMARY_REPORT_SHEET_ID
    target_sheet_name = "Sheet1" # Default sheet name
    if not target_sheet_id or target_sheet_id == "YOUR_DAILY_SUMMARY_REPORT_SHEET_ID_HERE": 
        logger.error("Daily summary sheet ID not configured."); return False

    last_report_date = None
    df_existing_report = pd.DataFrame() # Initialize empty

    # --- Try to Read Existing Report (only if NOT doing full rebuild) ---
    if not full_rebuild:
        logger.info(f"Attempting incremental update. Reading existing summary from Sheet ID: {target_sheet_id}")
        df_existing_report_raw = gutils.get_sheet_as_df(gs_client, target_sheet_id, target_sheet_name)
        
        if df_existing_report_raw is not None and not df_existing_report_raw.empty:
            # Check if the essential 'Date' column exists
            if 'Date' in df_existing_report_raw.columns:
                df_existing_report = df_existing_report_raw.copy()
                # Attempt to parse date, drop invalid rows
                df_existing_report['Date'] = pd.to_datetime(df_existing_report['Date'], errors='coerce').dt.date
                df_existing_report.dropna(subset=['Date'], inplace=True) 
                
                if not df_existing_report.empty:
                    last_report_date = df_existing_report['Date'].max()
                    logger.info(f"Last date found in existing report: {last_report_date}")
                else:
                     logger.warning("Existing report contained no valid dates after parsing. Will perform full rebuild.")
                     full_rebuild = True # Force rebuild if dates are bad
            else:
                logger.warning("Existing report sheet is missing 'Date' column. Will perform full rebuild.")
                full_rebuild = True # Force rebuild if structure is wrong
        else:
            logger.info("Existing daily summary report is empty or unreadable. Performing full rebuild.")
            full_rebuild = True # Force rebuild if sheet empty/unreadable

    # Determine the date from which new calculations are needed for merging
    start_date_for_new_data = last_report_date + timedelta(days=1) if last_report_date and not full_rebuild else None
    if start_date_for_new_data: logger.info(f"Will merge new summary data starting from: {start_date_for_new_data}")


    # --- 1. Get Loan IDs (Required for both modes) ---
    folder_id = config.AMORTIZATION_SCHEDULES_FOLDER_ID
    if not folder_id or folder_id == "YOUR_GOOGLE_DRIVE_FOLDER_ID_HERE": logger.error("Amortization folder ID not configured."); return False
    loan_ids_to_process = get_loan_ids_from_drive_folder(folder_id) 
    if not loan_ids_to_process: logger.warning("No LoanIDs found."); return False # Nothing to process

    # --- 2. Read Data from All Schedules (Required for both modes) ---
    logger.info(f"Reading schedule data for {len(loan_ids_to_process)} loans...")
    for loan_id in loan_ids_to_process:
        sheet_id = find_sheet_id_by_loan_id_in_folder(loan_id) 
        if not sheet_id: logger.warning(f"Skipping LoanID '{loan_id}' (sheet not found)."); continue 
        schedule_df_raw = get_sheet_as_df(gs_client, sheet_id, "Schedule") 
        if schedule_df_raw is None or schedule_df_raw.empty: logger.warning(f"Empty/unreadable schedule for {loan_id}."); continue
        
        schedule_df = schedule_df_raw.copy()
        schedule_df.columns = [str(col).strip().lower() for col in schedule_df.columns]

        ACTUAL_PMT_DATE_COL = 'actualpaymentdate'; ACTUAL_PMT_AMT_COL = 'actualpaymentamount';
        PRINCIPAL_PAID_COL = 'principalpaid'; INTEREST_PAID_COL = 'interestpaid';
        LATE_FEE_COL_SCHED = 'latefee'; CREDIT_APPLIED_COL_SCHED = 'creditapplied';
        required_cols = [ACTUAL_PMT_DATE_COL, ACTUAL_PMT_AMT_COL, PRINCIPAL_PAID_COL, INTEREST_PAID_COL, LATE_FEE_COL_SCHED, CREDIT_APPLIED_COL_SCHED]
        
        missing_essential = [c for c in required_cols[:4] if c not in schedule_df.columns]
        if missing_essential: logger.warning(f"Schedule {loan_id} missing ESSENTIAL cols: {missing_essential}. Skipping."); continue
        
        if LATE_FEE_COL_SCHED not in schedule_df.columns: schedule_df[LATE_FEE_COL_SCHED] = 0.0
        if CREDIT_APPLIED_COL_SCHED not in schedule_df.columns: schedule_df[CREDIT_APPLIED_COL_SCHED] = 0.0
             
        schedule_df = schedule_df[required_cols].copy() 
        schedule_df[ACTUAL_PMT_DATE_COL] = pd.to_datetime(schedule_df[ACTUAL_PMT_DATE_COL], errors='coerce').dt.date
        schedule_df.dropna(subset=[ACTUAL_PMT_DATE_COL], inplace=True) 

        numeric_cols_to_parse = [ACTUAL_PMT_AMT_COL, PRINCIPAL_PAID_COL, INTEREST_PAID_COL, LATE_FEE_COL_SCHED, CREDIT_APPLIED_COL_SCHED]
        for col in numeric_cols_to_parse:
            schedule_df[col] = schedule_df[col].apply(lambda x: safe_string_to_float(x, context=f"Daily Report Col {col} for {loan_id}"))
            schedule_df[col] = pd.to_numeric(schedule_df[col], errors='coerce') 

        schedule_df = schedule_df[schedule_df[ACTUAL_PMT_AMT_COL].notna() & (schedule_df[ACTUAL_PMT_AMT_COL] > 0)]
        
        if not schedule_df.empty: all_payments_data.append(schedule_df)
        else: logger.debug(f"No valid payment rows found for {loan_id}")

    if not all_payments_data: logger.warning("No valid payment data found across all loan schedules."); return False # Return False as nothing was processed

    # --- 3. Aggregate ALL Data by Date ---
    logger.info("Aggregating all payment data by date...")
    daily_summary_all_calculated = pd.DataFrame() # Initialize empty
    try:
        combined_df = pd.concat(all_payments_data, ignore_index=True)
        daily_summary_all_calculated = combined_df.groupby(ACTUAL_PMT_DATE_COL).agg(
            PaymentsReceived=(ACTUAL_PMT_AMT_COL, 'sum'),
            PrincipalReceived=(PRINCIPAL_PAID_COL, 'sum'),
            InterestReceived=(INTEREST_PAID_COL, 'sum'),
            LateFeesReceived=(LATE_FEE_COL_SCHED, 'sum'), 
            CreditAdded=(CREDIT_APPLIED_COL_SCHED, 'sum') 
        ).fillna(0.0).reset_index() 
        daily_summary_all_calculated.rename(columns={ACTUAL_PMT_DATE_COL: 'Date'}, inplace=True)
        # Convert 'Date' to date objects for comparison/merging
        daily_summary_all_calculated['Date'] = pd.to_datetime(daily_summary_all_calculated['Date']).dt.date 
        logger.info(f"Calculated full daily summary with {len(daily_summary_all_calculated)} date entries.")
        
    except Exception as agg_error: 
        logger.error(f"Error aggregating daily summary: {agg_error}", exc_info=True)
        return False # Indicate failure

    # --- 4. Determine Final Data to Write (Merge or Full) ---
    if full_rebuild:
        logger.info("Full rebuild requested. Using all calculated data.")
        final_summary_to_write = daily_summary_all_calculated
    else:
        # Incremental: Combine existing valid report data with new calculated data
        logger.info("Incremental update. Merging existing data with new calculations.")
        if last_report_date is None or df_existing_report.empty:
            logger.warning("Performing full rebuild because existing report was empty or invalid.")
            final_summary_to_write = daily_summary_all_calculated
        else:
            # Ensure existing report numeric columns are float and NAs are 0.0
            report_numeric_cols = ['PaymentsReceived', 'PrincipalReceived', 'InterestReceived', 'LateFeesReceived', 'CreditAdded']
            for col in report_numeric_cols:
                 if col in df_existing_report.columns:
                      # Apply safe converter to handle any non-numeric strings in existing report too
                      df_existing_report[col] = df_existing_report[col].apply(lambda x: safe_string_to_float(x, context=f"Existing Report Col {col}"))
                      df_existing_report[col] = pd.to_numeric(df_existing_report[col], errors='coerce').fillna(0.0)
                 else: 
                     df_existing_report[col] = 0.0
            
            # Get only NEW data from the full calculation (dates > last_report_date)
            df_new_data = daily_summary_all_calculated[daily_summary_all_calculated['Date'] > last_report_date].copy()
            logger.info(f"Found {len(df_new_data)} new/updated date entries to include.")
            
            # Keep only OLD data from existing report (dates <= last_report_date)
            # Use the already parsed 'Date' column (which contains date objects)
            df_old_data_to_keep = df_existing_report[df_existing_report['Date'] <= last_report_date].copy()
            logger.info(f"Keeping {len(df_old_data_to_keep)} old date entries from existing report.")

            # Combine old kept data and new data
            if not df_new_data.empty:
                final_summary_to_write = pd.concat([df_old_data_to_keep, df_new_data], ignore_index=True)
            else:
                # If no new data, just use the old data (no need to rewrite unless forced)
                logger.info("No new daily summary data found since last report date.")
                final_summary_to_write = df_old_data_to_keep # Keep old data
                # Optionally, could return True here to avoid unnecessary write if df_old == df_existing
                if df_old_data_to_keep.equals(df_existing_report.loc[df_existing_report['Date'] <= last_report_date, df_old_data_to_keep.columns]):
                    logger.info("Existing data matches calculated old data. No sheet update needed.")
                    return True # Indicate success without writing

            logger.info(f"Combined summary has {len(final_summary_to_write)} total entries.")

    # --- 5. Format and Write Final Data ---
    try:
        # Check if empty before proceeding (e.g., if full_rebuild and no data ever)
        if final_summary_to_write.empty:
            logger.info("Final summary to write is empty. Clearing sheet.")
            # Prepare empty df with headers for gutils update function
            final_columns_order = ['Date', 'PaymentsReceived', 'PrincipalReceived', 'InterestReceived', 'LateFeesReceived', 'CreditAdded']
            final_summary_to_write = pd.DataFrame(columns=final_columns_order)
        else:
            # Format Date string and ensure column order
            final_summary_to_write['Date'] = pd.to_datetime(final_summary_to_write['Date']).dt.strftime('%Y-%m-%d') 
            final_columns_order = ['Date', 'PaymentsReceived', 'PrincipalReceived', 'InterestReceived', 'LateFeesReceived', 'CreditAdded']
            final_summary_to_write = final_summary_to_write.reindex(columns=final_columns_order, fill_value=0.0) 
            
            # Round numeric columns
            for col in ['PaymentsReceived', 'PrincipalReceived', 'InterestReceived', 'LateFeesReceived', 'CreditAdded']:
                # Ensure column is numeric before rounding
                final_summary_to_write[col] = pd.to_numeric(final_summary_to_write[col], errors='coerce').fillna(0.0).round(2)

            final_summary_to_write = final_summary_to_write.sort_values(by='Date', ascending=True)

    except Exception as format_error:
         logger.error(f"Error formatting final summary data: {format_error}", exc_info=True)
         return False

    logger.info(f"Attempting to OVERWRITE Google Sheet ID: {target_sheet_id}, Worksheet: {target_sheet_name} with {len(final_summary_to_write)} rows.")
    success = gutils.update_worksheet_from_df(gs_client, target_sheet_id, target_sheet_name, final_summary_to_write)

    if success: logger.info("Successfully updated the Daily Summary Report Google Sheet."); return True
    else: logger.error("Failed to update the Daily Summary Report Google Sheet."); return False