import pandas as pd
from datetime import datetime
import logging
import time 
from . import config
from . import gutils

logger = logging.getLogger(__name__)

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
    report_data_list = [] # Changed name to avoid conflict

    # Iterate through configured amortization sheet IDs
    for loan_id, sheet_id in config.AMORTIZATION_SHEET_IDS.items():
        logger.debug(f"Processing report data for LoanID: {loan_id}, SheetID: {sheet_id}")
        
         # --- ADD DELAY ---
        try:
            # Wait for 1 second (you can adjust this)
            time.sleep(1) # <--- PAUSE FOR 1 SECOND 
            logger.debug(f"Waited 1 second before processing {loan_id}")
        except Exception as e_sleep: # Should not happen with time.sleep
            logger.warning(f"Error during time.sleep: {e_sleep}")
        
        schedule_df_raw = gutils.get_sheet_as_df(gs_client, sheet_id, "Schedule")

        if schedule_df_raw is None:
            logger.warning(f"Could not read schedule for {loan_id} (SheetID: {sheet_id}). Skipping.")
            continue
        if schedule_df_raw.empty:
            logger.debug(f"Schedule sheet is empty for {loan_id} (SheetID: {sheet_id}). Skipping.")
            continue

        schedule_df = schedule_df_raw.copy()
        schedule_df.columns = schedule_df.columns.str.strip().str.lower() # Standardize for processing

        # Data type conversions
        schedule_df["actualpaymentdate"] = pd.to_datetime(schedule_df.get("actualpaymentdate"), errors='coerce')
        schedule_df["actualpaymentamount"] = pd.to_numeric(schedule_df.get("actualpaymentamount"), errors='coerce')
        schedule_df["principalpaid"] = pd.to_numeric(schedule_df.get("principalpaid"), errors='coerce').fillna(0)
        schedule_df["interestpaid"] = pd.to_numeric(schedule_df.get("interestpaid"), errors='coerce').fillna(0)
        schedule_df["latefee"] = pd.to_numeric(schedule_df.get("latefee"), errors='coerce').fillna(0)
        # schedule_df["creditapplied"] = pd.to_numeric(schedule_df.get("creditapplied"), errors='coerce').fillna(0)


        period_payments = schedule_df[
            (schedule_df["actualpaymentdate"].notna()) &
            (schedule_df["actualpaymentdate"] >= start_date) &
            (schedule_df["actualpaymentdate"] <= end_date) &
            (schedule_df["actualpaymentamount"].notna()) &
            (schedule_df["actualpaymentamount"] > 0)
        ]

        if not period_payments.empty:
            loan_principal = period_payments["principalpaid"].sum()
            loan_interest = period_payments["interestpaid"].sum()
            loan_fees = period_payments["latefee"].sum()

            total_principal_collected += loan_principal
            total_interest_collected += loan_interest
            total_fees_collected += loan_fees
            
            for _, row in period_payments.iterrows():
                report_data_list.append({
                    "LoanID": loan_id,
                    "PaymentDate": row["actualpaymentdate"].strftime("%Y-%m-%d") if pd.notna(row["actualpaymentdate"]) else None,
                    "Principal": row["principalpaid"],
                    "Interest": row["interestpaid"],
                    "Fee": row["latefee"],
                })
        else:
            logger.debug(f"No payments found in the specified period for LoanID: {loan_id}")
    
    summary = (
        f"\n--- Periodic Financial Report (Google Sheets) ---\n"
        f"Period: {start_date_str} to {end_date_str}\n"
        f"--------------------------------------------------\n"
        f"Total Principal Collected: {total_principal_collected:.2f}\n"
        f"Total Interest Collected:  {total_interest_collected:.2f}\n"
        f"Total Fees Collected:      {total_fees_collected:.2f}\n"
        f"--------------------------------------------------"
    )
    logger.info(summary)
    
    if report_data_list:
        detailed_report_df = pd.DataFrame(report_data_list)
        logger.info("\nDetailed Breakdown:\n" + detailed_report_df.to_string(index=False))
    else:
        logger.info("No payment transactions found in the specified period for detailed breakdown.")

    return {
        "total_principal": total_principal_collected,
        "total_interest": total_interest_collected,
        "total_fees": total_fees_collected,
        "detailed_data": report_data_list
    }