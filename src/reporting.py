# src/reporting.py
import pandas as pd
from datetime import datetime
import logging
from . import config 
# --- Import helpers from gutils ---
from . import gutils 
from .gutils import safe_string_to_float, get_loan_ids_from_drive_folder, find_sheet_id_by_loan_id_in_folder, get_sheet_as_df

logger = logging.getLogger(__name__)

# Helper functions are now imported from gutils, no local definitions needed

def generate_period_report(start_date_str, end_date_str):
    logger.info(f"Generating financial report for period: {start_date_str} to {end_date_str}")
    gs_client = None
    try: gs_client = gutils.get_gspread_client()
    except ConnectionError as e: logger.error(f"No GS client for reporting: {e}. Aborting."); return {"error": "Failed GS Client", "total_principal": 0, "total_interest": 0, "total_fees": 0, "detailed_data": []} 

    # --- Parse Report Dates ---
    try:
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
        logger.info(f"Report Date Range: {start_date} to {end_date}")
    except ValueError: logger.error("Invalid date format for report (use YYYY-MM-DD)."); return {"error": "Invalid date format", "total_principal": 0, "total_interest": 0, "total_fees": 0, "detailed_data": []}

    # --- Get Loan IDs ---
    folder_id = config.AMORTIZATION_SCHEDULES_FOLDER_ID
    if not folder_id or folder_id == "YOUR_GOOGLE_DRIVE_FOLDER_ID_HERE":
         logger.error("AMORTIZATION_SCHEDULES_FOLDER_ID not configured."); return {"error": "Folder not configured", "total_principal": 0, "total_interest": 0, "total_fees": 0, "detailed_data": []}

    # Use imported function from gutils
    loan_ids_to_report = get_loan_ids_from_drive_folder(folder_id) 
    if not loan_ids_to_report: logger.warning("No LoanIDs found from Drive folder."); return {"total_principal": 0, "total_interest": 0, "total_fees": 0, "detailed_data": []} 

    # --- Initialize Aggregators ---
    total_principal_collected = 0.0; total_interest_collected = 0.0; total_fees_collected = 0.0
    report_data_list = []

    # --- Iterate Through Loans ---
    for loan_id in loan_ids_to_report:
        # Use imported function from gutils
        sheet_id = find_sheet_id_by_loan_id_in_folder(loan_id) 
        if not sheet_id: logger.warning(f"Skipping LoanID '{loan_id}' (sheet not found)."); continue 

        logger.debug(f"Processing report data for LoanID: {loan_id}, SheetID: {sheet_id}")
        
        # Use imported function from gutils
        schedule_df_raw = get_sheet_as_df(gs_client, sheet_id, "Schedule") 
        if schedule_df_raw is None or schedule_df_raw.empty: logger.warning(f"Empty/unreadable schedule for {loan_id}."); continue
        
        schedule_df = schedule_df_raw.copy()
        original_schedule_headers = schedule_df.columns.tolist() 
        schedule_df.columns = [str(col).strip().lower() for col in schedule_df.columns]

        # Define expected columns
        ACTUAL_PMT_DATE_COL = 'actualpaymentdate'; ACTUAL_PMT_AMT_COL = 'actualpaymentamount';
        PRINCIPAL_PAID_COL = 'principalpaid'; INTEREST_PAID_COL = 'interestpaid'; LATE_FEE_COL = 'latefee'; 

        required_report_cols = [ACTUAL_PMT_DATE_COL, ACTUAL_PMT_AMT_COL, PRINCIPAL_PAID_COL, INTEREST_PAID_COL, LATE_FEE_COL]
        missing_cols = [col for col in required_report_cols if col not in schedule_df.columns]
        if missing_cols: logger.warning(f"Schedule for {loan_id} missing report columns: {missing_cols}. Skipping."); continue

        # --- Data Type Conversion and Cleaning ---
        schedule_df[ACTUAL_PMT_DATE_COL] = pd.to_datetime(schedule_df.get(ACTUAL_PMT_DATE_COL), errors='coerce').dt.date
        
        # Use imported safe_string_to_float from gutils
        schedule_df[PRINCIPAL_PAID_COL] = schedule_df[PRINCIPAL_PAID_COL].apply(lambda x: safe_string_to_float(x, context=f"Loan {loan_id} PrincipalPaid"))
        schedule_df[INTEREST_PAID_COL] = schedule_df[INTEREST_PAID_COL].apply(lambda x: safe_string_to_float(x, context=f"Loan {loan_id} InterestPaid"))
        schedule_df[LATE_FEE_COL] = schedule_df[LATE_FEE_COL].apply(lambda x: safe_string_to_float(x, context=f"Loan {loan_id} LateFee"))
        schedule_df[ACTUAL_PMT_AMT_COL] = schedule_df[ACTUAL_PMT_AMT_COL].apply(lambda x: safe_string_to_float(x, context=f"Loan {loan_id} ActualPaymentAmount"))
        
        # Coerce to numeric after cleaning, errors become NaN
        schedule_df[PRINCIPAL_PAID_COL] = pd.to_numeric(schedule_df[PRINCIPAL_PAID_COL], errors='coerce')
        schedule_df[INTEREST_PAID_COL] = pd.to_numeric(schedule_df[INTEREST_PAID_COL], errors='coerce')
        schedule_df[LATE_FEE_COL] = pd.to_numeric(schedule_df[LATE_FEE_COL], errors='coerce')
        schedule_df[ACTUAL_PMT_AMT_COL] = pd.to_numeric(schedule_df[ACTUAL_PMT_AMT_COL], errors='coerce')

        # --- Filtering ---
        period_payments = schedule_df[
            (schedule_df[ACTUAL_PMT_DATE_COL].notna()) & (schedule_df[ACTUAL_PMT_DATE_COL] >= start_date) & (schedule_df[ACTUAL_PMT_DATE_COL] <= end_date) &
            (schedule_df[ACTUAL_PMT_AMT_COL].notna()) & (schedule_df[ACTUAL_PMT_AMT_COL] > 0) 
        ].copy() 

        # --- Aggregation ---
        if not period_payments.empty:
            logger.debug(f"Found {len(period_payments)} payment entries in period for LoanID {loan_id}.")
            # Sum ignores NaN by default
            loan_principal = period_payments[PRINCIPAL_PAID_COL].sum()
            loan_interest = period_payments[INTEREST_PAID_COL].sum() 
            loan_fees = period_payments[LATE_FEE_COL].sum() 

            total_principal_collected += loan_principal; total_interest_collected += loan_interest; total_fees_collected += loan_fees
            
            # Append to detailed list, filling NaN with 0.0 for display/consistency
            for _, row in period_payments.iterrows():
                report_data_list.append({
                    "LoanID": loan_id, 
                    "PaymentDate": row[ACTUAL_PMT_DATE_COL].strftime("%Y-%m-%d") if pd.notna(row[ACTUAL_PMT_DATE_COL]) else None,
                    "Principal": row[PRINCIPAL_PAID_COL] if pd.notna(row[PRINCIPAL_PAID_COL]) else 0.0, 
                    "Interest": row[INTEREST_PAID_COL] if pd.notna(row[INTEREST_PAID_COL]) else 0.0, 
                    "Fee": row[LATE_FEE_COL] if pd.notna(row[LATE_FEE_COL]) else 0.0, 
                })
        else:
            logger.debug(f"No relevant payments found in period for LoanID: {loan_id}")
            
    # --- Reporting Summary ---
    summary = (
        f"\n--- Periodic Financial Report ---\n"
        f"Period: {start_date_str} to {end_date_str}\n"
        f"Based on {len(loan_ids_to_report)} loans found in Drive folder.\n"
        f"--------------------------------------------------\n"
        f"Total Principal Collected: {total_principal_collected:.2f}\n"
        f"Total Interest Collected:  {total_interest_collected:.2f}\n"
        f"Total Fees Collected:      {total_fees_collected:.2f}\n"
        f"--------------------------------------------------" )
    logger.info(summary)
    
    if report_data_list:
        detailed_report_df = pd.DataFrame(report_data_list)
        try: logger.info("\nDetailed Breakdown:\n" + detailed_report_df.to_string(index=False))
        except Exception as e_log: logger.warning(f"Could not log full detailed breakdown: {e_log}"); logger.info(f"Detailed breakdown contains {len(detailed_report_df)} rows.")
    else: logger.info("No payment transactions found in the specified period for detailed breakdown.")

    return {
        "total_principal": round(total_principal_collected, 2),
        "total_interest": round(total_interest_collected, 2),
        "total_fees": round(total_fees_collected, 2),
        "detailed_data": report_data_list 
    }