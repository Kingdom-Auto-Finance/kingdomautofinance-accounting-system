# src/reporting.py
import pandas as pd
from datetime import datetime
import logging
from . import config # To get folder ID, etc.
from . import gutils # To get clients and read sheets

logger = logging.getLogger(__name__)

def get_loan_ids_from_drive_folder(folder_id):
    """
    Lists Google Sheet files in a specific Drive folder and returns their names
    (which are assumed to be the LoanIDs). Handles pagination for folders with many files.
    """
    loan_ids = []
    drive_service = None
    page_token = None
    
    try:
        drive_service = gutils.get_drive_service()
        if not drive_service:
            logger.error("Cannot get Drive service client to list loan IDs.")
            return [] # Return empty list if service fails

        logger.info(f"Listing Google Sheets in Drive Folder ID: {folder_id}")
        
        while True: # Loop to handle pagination if many files exist
            results = drive_service.files().list(
                q=f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.spreadsheet' and trashed=false",
                pageSize=100, # Get up to 100 items per request
                fields="nextPageToken, files(id, name)", # Get ID (for potential use) and name
                pageToken=page_token # Pass token for subsequent pages
            ).execute()
            
            items = results.get('files', [])
            
            if not items and not loan_ids: # Check if folder is completely empty on first fetch
                 logger.warning(f"No Google Sheet files found in the specified Drive folder: {folder_id}")
                 return []

            for item in items:
                filename = item.get('name')
                if filename:
                    # Assuming filename directly corresponds to LoanID
                    # Optional: Add validation here if filenames might not be valid LoanIDs
                    loan_ids.append(filename) 
                else:
                    logger.warning(f"Found file with ID {item.get('id')} but no name in folder {folder_id}.")

            page_token = results.get('nextPageToken', None)
            if page_token is None:
                break # Exit loop if there are no more pages

        logger.info(f"Found {len(loan_ids)} potential LoanIDs (sheet names) in Drive folder.")
        return loan_ids

    except Exception as e:
        logger.error(f"Failed to list files in Drive folder {folder_id}: {e}", exc_info=True)
        return [] # Return empty list on error


def generate_period_report(start_date_str, end_date_str):
    logger.info(f"Generating financial report for period: {start_date_str} to {end_date_str}")
    gs_client = None
    try:
        gs_client = gutils.get_gspread_client()
    except ConnectionError as e:
        logger.error(f"Failed to initialize Google Sheets client for reporting: {e}. Aborting.")
        return {"error": "Failed to connect to Google Sheets", "total_principal": 0, "total_interest": 0, "total_fees": 0, "detailed_data": []}

    try:
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
    except ValueError:
        logger.error("Invalid date format for report. Please use YYYY-MM-DD.")
        return {"error": "Invalid date format", "total_principal": 0, "total_interest": 0, "total_fees": 0, "detailed_data": []}

    total_principal_collected = 0.0
    total_interest_collected = 0.0
    total_fees_collected = 0.0
    report_data_list = []

    # --- Get List of LoanIDs by Listing Files in the Designated Drive Folder ---
    folder_id = config.AMORTIZATION_SCHEDULES_FOLDER_ID
    if not folder_id or folder_id == "YOUR_GOOGLE_DRIVE_FOLDER_ID_HERE":
         logger.error("AMORTIZATION_SCHEDULES_FOLDER_ID is not configured in config.py. Cannot generate report.")
         return {"error": "Amortization folder not configured", "total_principal": 0, "total_interest": 0, "total_fees": 0, "detailed_data": []}

    loan_ids_to_report = get_loan_ids_from_drive_folder(folder_id)

    if not loan_ids_to_report:
        logger.warning("No LoanIDs found from Drive folder to generate report.")
        # Return empty report structure
        summary = (f"\n--- Periodic Financial Report ---\nPeriod: {start_date_str} to {end_date_str}\nNo loans found in configured Drive folder.")
        logger.info(summary)
        return {"total_principal": 0, "total_interest": 0, "total_fees": 0, "detailed_data": []}


    # --- Iterate through LoanIDs found in the Drive folder ---
    for loan_id in loan_ids_to_report:
        # Find the corresponding Google Sheet ID using the Drive search function
        # (This is slightly redundant if get_loan_ids_from_drive_folder returned IDs,
        # but it confirms the file still exists and matches filename convention)
        # Alternatively, modify get_loan_ids_from_drive_folder to return a dict {name: id}
        
        # Let's keep using find_sheet_id_by_loan_id_in_folder for consistency with payment_processor
        sheet_id = gutils.find_sheet_id_by_loan_id_in_folder(loan_id) 
        
        if not sheet_id:
            # Warning already logged by find_sheet_id_by_loan_id_in_folder
            logger.warning(f"Skipping LoanID '{loan_id}' in report as its sheet wasn't found by ID search (might be temporary issue or name mismatch).")
            continue # Skip to the next loan ID

        logger.debug(f"Processing report data for LoanID: {loan_id}, SheetID: {sheet_id}")
        
        # Use get_sheet_as_df (which includes retries) to read the 'Schedule' worksheet
        schedule_df_raw = gutils.get_sheet_as_df(gs_client, sheet_id, "Schedule")

        if schedule_df_raw is None or schedule_df_raw.empty:
            logger.warning(f"Could not read or empty schedule for {loan_id} (SheetID: {sheet_id}). Skipping in report.")
            continue
        
        schedule_df = schedule_df_raw.copy()
        # Standardize columns for reliable access
        schedule_df.columns = [str(col).strip().lower() for col in schedule_df.columns]

        # Define expected lowercase column names for schedule data needed in report
        ACTUAL_PMT_DATE_COL = 'actualpaymentdate'
        ACTUAL_PMT_AMT_COL = 'actualpaymentamount'
        PRINCIPAL_PAID_COL = 'principalpaid'
        INTEREST_PAID_COL = 'interestpaid'
        LATE_FEE_COL = 'latefee'

        # Check if essential columns exist
        required_report_cols = [ACTUAL_PMT_DATE_COL, ACTUAL_PMT_AMT_COL, PRINCIPAL_PAID_COL, INTEREST_PAID_COL, LATE_FEE_COL]
        missing_cols = [col for col in required_report_cols if col not in schedule_df.columns]
        if missing_cols:
            logger.warning(f"Schedule for LoanID {loan_id} (SheetID: {sheet_id}) is missing required columns for reporting: {missing_cols}. Skipping this loan.")
            continue

        # Data type conversions and filtering
        schedule_df[ACTUAL_PMT_DATE_COL] = pd.to_datetime(schedule_df.get(ACTUAL_PMT_DATE_COL), errors='coerce')
        schedule_df[ACTUAL_PMT_AMT_COL] = pd.to_numeric(schedule_df.get(ACTUAL_PMT_AMT_COL), errors='coerce')
        schedule_df[PRINCIPAL_PAID_COL] = pd.to_numeric(schedule_df.get(PRINCIPAL_PAID_COL), errors='coerce').fillna(0)
        schedule_df[INTEREST_PAID_COL] = pd.to_numeric(schedule_df.get(INTEREST_PAID_COL), errors='coerce').fillna(0)
        schedule_df[LATE_FEE_COL] = pd.to_numeric(schedule_df.get(LATE_FEE_COL), errors='coerce').fillna(0)

        # Filter for payments within the specified date range
        period_payments = schedule_df[
            (schedule_df[ACTUAL_PMT_DATE_COL].notna()) &
            (schedule_df[ACTUAL_PMT_DATE_COL] >= start_date) &
            (schedule_df[ACTUAL_PMT_DATE_COL] <= end_date) &
            (schedule_df[ACTUAL_PMT_AMT_COL].notna()) &
            (schedule_df[ACTUAL_PMT_AMT_COL] > 0) # Ensure an actual payment amount exists and is positive
        ].copy() # Use .copy() to avoid SettingWithCopyWarning if modifying later

        if not period_payments.empty:
            loan_principal = period_payments[PRINCIPAL_PAID_COL].sum()
            loan_interest = period_payments[INTEREST_PAID_COL].sum()
            loan_fees = period_payments[LATE_FEE_COL].sum()

            total_principal_collected += loan_principal
            total_interest_collected += loan_interest
            total_fees_collected += loan_fees
            
            for _, row in period_payments.iterrows():
                report_data_list.append({
                    "LoanID": loan_id, # Use the original loan_id from the loop
                    "PaymentDate": row[ACTUAL_PMT_DATE_COL].strftime("%Y-%m-%d") if pd.notna(row[ACTUAL_PMT_DATE_COL]) else None,
                    "Principal": row[PRINCIPAL_PAID_COL],
                    "Interest": row[INTEREST_PAID_COL],
                    "Fee": row[LATE_FEE_COL],
                })
        else:
            logger.debug(f"No payments found in the specified period for LoanID: {loan_id}")
            
    # --- Reporting Summary ---
    summary = (
        f"\n--- Periodic Financial Report ---\n"
        f"Period: {start_date_str} to {end_date_str}\n"
        f"Based on {len(loan_ids_to_report)} loans found in Drive folder.\n"
        f"--------------------------------------------------\n"
        f"Total Principal Collected: {total_principal_collected:.2f}\n"
        f"Total Interest Collected:  {total_interest_collected:.2f}\n"
        f"Total Fees Collected:      {total_fees_collected:.2f}\n"
        f"--------------------------------------------------"
    )
    logger.info(summary)
    
    if report_data_list:
        detailed_report_df = pd.DataFrame(report_data_list)
        try: # Use try-except for to_string in case of very large dataframes
            logger.info("\nDetailed Breakdown:\n" + detailed_report_df.to_string(index=False))
        except Exception as e_log:
             logger.warning(f"Could not log full detailed breakdown: {e_log}")
             logger.info(f"Detailed breakdown contains {len(detailed_report_df)} rows.")
    else: 
        logger.info("No payment transactions found in the specified period across applicable loans for detailed breakdown.")

    return {
        "total_principal": total_principal_collected,
        "total_interest": total_interest_collected,
        "total_fees": total_fees_collected,
        "detailed_data": report_data_list # Return data for potential UI use
    }