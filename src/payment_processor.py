import pandas as pd
from datetime import datetime
import logging
# Use relative imports for modules within the same package (src)
from . import config
from . import gutils
from .amortization_calculator import calculate_payment_details

logger = logging.getLogger(__name__)

def process_payments():
    logger.info("Starting payment processing using Google Sheets...")
    gs_client = None
    try:
        gs_client = gutils.get_gspread_client()
    except ConnectionError as e:
        logger.error(f"Failed to initialize Google Sheets client: {e}. Aborting payment processing.")
        return # Critical error, cannot proceed

    # --- 1. Read Payments Log ---
    payments_df = gutils.get_sheet_as_df(gs_client, config.PAYMENTS_LOG_SHEET_ID, "Sheet1")
    if payments_df is None:
        logger.error("Could not read Payments Log sheet. Aborting.")
        return
    if payments_df.empty:
        logger.info("Payments log is empty. No payments to process.")
        return

    # Standardize column names (case-insensitivity, strip spaces)
    payments_df.columns = payments_df.columns.str.strip().str.lower()
    required_log_cols = ['loanid', 'paymentdate', 'paymentamount', 'processedstatus', 'processedtimestamp']
    for col_name in ['loanid', 'paymentdate', 'paymentamount']: # Core data columns
        if col_name not in payments_df.columns:
            logger.error(f"Critical column '{col_name}' missing from Payments Log sheet. Please add it. Aborting.")
            return
    
    # Ensure status/timestamp columns exist, add if not (though better if template has them)
    if 'processedstatus' not in payments_df.columns:
        payments_df['processedstatus'] = ''
    if 'processedtimestamp' not in payments_df.columns:
        payments_df['processedtimestamp'] = ''
        
    # Data type conversions and cleaning
    payments_df['paymentdate'] = pd.to_datetime(payments_df['paymentdate'], errors='coerce')
    payments_df['paymentamount'] = pd.to_numeric(payments_df['paymentamount'], errors='coerce')
    payments_df['loanid'] = payments_df['loanid'].astype(str).str.strip()

    # Filter for pending payments
    pending_payments_df = payments_df[
        payments_df['processedstatus'].fillna('').str.strip().isin(['Pending', ''])
    ].sort_values(by="paymentdate", ascending=True).copy()

    if pending_payments_df.empty:
        logger.info("No pending payments found to process.")
        return
    logger.info(f"Found {len(pending_payments_df)} pending payments to process.")

    # --- 2. Process Each Payment ---
    for original_log_index, payment_row in pending_payments_df.iterrows():
        loan_id = payment_row["loanid"]
        actual_payment_date_dt = payment_row["paymentdate"]
        actual_payment_amount = payment_row["paymentamount"]

        if pd.isna(loan_id) or loan_id == '':
            logger.warning(f"Skipping payment at log index {original_log_index} due to missing LoanID.")
            payments_df.loc[original_log_index, "processedstatus"] = "Error - Missing LoanID"
            payments_df.loc[original_log_index, "processedtimestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            continue
        if pd.isna(actual_payment_date_dt):
            logger.warning(f"Skipping payment for LoanID {loan_id} (log index {original_log_index}) due to invalid PaymentDate.")
            payments_df.loc[original_log_index, "processedstatus"] = "Error - Invalid Date"
            payments_df.loc[original_log_index, "processedtimestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            continue
        if pd.isna(actual_payment_amount) or actual_payment_amount <= 0:
            logger.warning(f"Skipping payment for LoanID {loan_id} (log index {original_log_index}) due to invalid PaymentAmount: {actual_payment_amount}.")
            payments_df.loc[original_log_index, "processedstatus"] = "Error - Invalid Amount"
            payments_df.loc[original_log_index, "processedtimestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            continue
        
        actual_payment_date_str = actual_payment_date_dt.strftime("%Y-%m-%d")
        logger.info(f"Processing payment: LoanID={loan_id}, Date={actual_payment_date_str}, Amount={actual_payment_amount:.2f}")

        amortization_sheet_id = gutils.get_amortization_sheet_id(loan_id)
        if not amortization_sheet_id:
            logger.error(f"Amortization Google Sheet ID for LoanID '{loan_id}' not found/configured. Skipping payment.")
            payments_df.loc[original_log_index, "processedstatus"] = "Error - No Amort. Sheet ID"
            payments_df.loc[original_log_index, "processedtimestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            continue

        try:
            loan_terms_df_raw = gutils.get_sheet_as_df(gs_client, amortization_sheet_id, "LoanTerms")
            schedule_df_raw = gutils.get_sheet_as_df(gs_client, amortization_sheet_id, "Schedule")

            if loan_terms_df_raw is None or schedule_df_raw is None:
                logger.error(f"Could not read LoanTerms or Schedule for {loan_id} from sheet ID {amortization_sheet_id}.")
                payments_df.loc[original_log_index, "processedstatus"] = "Error - Read Amort. Sheet"
                payments_df.loc[original_log_index, "processedtimestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                continue
            if loan_terms_df_raw.empty or schedule_df_raw.empty:
                logger.error(f"LoanTerms or Schedule sheet is empty for {loan_id} (SheetID: {amortization_sheet_id}). Cannot process.")
                payments_df.loc[original_log_index, "processedstatus"] = "Error - Empty Amort. Sheet"
                payments_df.loc[original_log_index, "processedtimestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                continue

            # Standardize column names and prepare DataFrames
            loan_terms_df_raw.columns = loan_terms_df_raw.columns.str.strip().str.lower()
            schedule_df_raw.columns = schedule_df_raw.columns.str.strip().str.lower()
            
            # Ensure 'parameter' and 'value' columns exist in loan_terms_df
            if 'parameter' not in loan_terms_df_raw.columns or 'value' not in loan_terms_df_raw.columns:
                logger.error(f"LoanTerms sheet for {loan_id} is missing 'Parameter' or 'Value' columns.")
                payments_df.loc[original_log_index, "processedstatus"] = "Error - Bad LoanTerms Format"
                payments_df.loc[original_log_index, "processedtimestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                continue

            loan_terms_s = loan_terms_df_raw.set_index('parameter')['value'].astype(str).str.strip()
            schedule_df = schedule_df_raw.copy() # Work on a copy

            # Data type conversions for schedule_df (critical after reading from Sheets)
            schedule_df['duedate'] = pd.to_datetime(schedule_df['duedate'], errors='coerce')
            numeric_cols = ['beginningbalance', 'scheduledpayment', 'actualpaymentamount', 
                            'interestpaid', 'principalpaid', 'latefee', 'creditapplied', 'endingbalance']
            for col in numeric_cols:
                if col in schedule_df.columns:
                    schedule_df[col] = pd.to_numeric(schedule_df[col], errors='coerce')#.fillna(0.0)
                else: # Add column if missing and fill with 0, except for actualpaymentamount initially
                    schedule_df[col] = 0.0 if col != 'actualpaymentamount' else pd.NA

            # For 'actualpaymentdate', it might be string or NaT. Convert to datetime, keep NaT as is.
            if 'actualpaymentdate' in schedule_df.columns:
                schedule_df['actualpaymentdate'] = pd.to_datetime(schedule_df['actualpaymentdate'], errors='coerce')
            else:
                schedule_df['actualpaymentdate'] = pd.NaT
            
            if 'status' not in schedule_df.columns:
                schedule_df['status'] = "Due" # Default status


            # Fetch necessary loan terms, with defaults or error handling
            try:
                annual_interest_rate = float(loan_terms_s.get("annualinterestrate", 0.0))
                late_fee_percentage = float(loan_terms_s.get("latefeepercentage", config.DEFAULT_LATE_FEE_PERCENTAGE))
                grace_period_days = int(loan_terms_s.get("graceperioddays", config.DEFAULT_GRACE_PERIOD_DAYS))
            except ValueError as ve:
                logger.error(f"Invalid numeric value in LoanTerms for {loan_id}: {ve}")
                payments_df.loc[original_log_index, "processedstatus"] = "Error - Invalid LoanTerms Value"
                payments_df.loc[original_log_index, "processedtimestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                continue


            # Find the next row to apply payment to
            target_row_idx = -1
            for i, row in schedule_df.iterrows():
                # A row is eligible if ActualPaymentDate is NaT (Not a Time) or Status is 'Due' or 'Partially Paid'
                is_paid_or_processed = pd.notna(row["actualpaymentdate"]) and str(row["status"]).lower().startswith("paid")
                if not is_paid_or_processed or str(row["status"]).lower() in ["due", "partially paid", ""]:
                    target_row_idx = i
                    break
            
            if target_row_idx == -1:
                logger.info(f"No due payment slots found for {loan_id}, or loan fully paid. This payment might be an overpayment or error.")
                payments_df.loc[original_log_index, "processedstatus"] = "Error - No Due Payment Slot"
                payments_df.loc[original_log_index, "processedtimestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                continue

            due_date_dt = schedule_df.loc[target_row_idx, "duedate"]
            if pd.isna(due_date_dt):
                logger.error(f"DueDate is missing or invalid for LoanID {loan_id} at schedule row {target_row_idx}.")
                payments_df.loc[original_log_index, "processedstatus"] = "Error - Invalid DueDate in Sched"
                payments_df.loc[original_log_index, "processedtimestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                continue
            due_date_str = due_date_dt.strftime("%Y-%m-%d")
            
            beginning_balance = float(schedule_df.loc[target_row_idx, "beginningbalance"])
            scheduled_payment_on_schedule = float(schedule_df.loc[target_row_idx, "scheduledpayment"])


            payment_calcs = calculate_payment_details(
                beginning_balance, annual_interest_rate, 30, scheduled_payment_on_schedule,
                actual_payment_amount, due_date_str, actual_payment_date_str,
                late_fee_percentage, grace_period_days
            )

            # Update the schedule DataFrame (make sure columns exist)
            schedule_df.loc[target_row_idx, "actualpaymentdate"] = pd.to_datetime(actual_payment_date_str)
            schedule_df.loc[target_row_idx, "actualpaymentamount"] = actual_payment_amount
            schedule_df.loc[target_row_idx, "interestpaid"] = payment_calcs["InterestPaid"]
            schedule_df.loc[target_row_idx, "principalpaid"] = payment_calcs["PrincipalPaid"]
            schedule_df.loc[target_row_idx, "latefee"] = payment_calcs["LateFee"]
            schedule_df.loc[target_row_idx, "creditapplied"] = payment_calcs["CreditApplied"]
            schedule_df.loc[target_row_idx, "endingbalance"] = payment_calcs["EndingBalance"]
            schedule_df.loc[target_row_idx, "status"] = payment_calcs["Status"]

            # Update the BeginningBalance for the *next* row, if it exists and isn't already paid
            if target_row_idx + 1 < len(schedule_df):
                next_row_status = str(schedule_df.loc[target_row_idx + 1, "status"]).lower()
                next_row_paid_date = schedule_df.loc[target_row_idx + 1, "actualpaymentdate"]
                if not (pd.notna(next_row_paid_date) and next_row_status.startswith("paid")):
                     schedule_df.loc[target_row_idx + 1, "beginningbalance"] = payment_calcs["EndingBalance"]
            
            # --- 3. Update Amortization Schedule Sheet ---
            # Ensure original column names for writing back (if they were different from lowercase)
            # For simplicity, we assume Google Sheets are fine with lowercase or we use consistent casing.
            # Convert datetime columns to string for gspread compatibility IF NEEDED.
            # schedule_df_to_write = schedule_df.copy()
            # schedule_df_to_write['duedate'] = schedule_df_to_write['duedate'].dt.strftime('%Y-%m-%d').replace('NaT', '')
            # schedule_df_to_write['actualpaymentdate'] = schedule_df_to_write['actualpaymentdate'].dt.strftime('%Y-%m-%d').replace('NaT', '')

            if gutils.update_worksheet_from_df(gs_client, amortization_sheet_id, "Schedule", schedule_df): # Pass original schedule_df
                payments_df.loc[original_log_index, "processedstatus"] = "Processed"
                payments_df.loc[original_log_index, "processedtimestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                logger.info(f"Successfully processed payment for {loan_id} (log index {original_log_index}). Amortization Status: {payment_calcs['Status']}")
            else:
                logger.error(f"Failed to update amortization sheet for {loan_id}. Payment status in log not marked as fully processed.")
                payments_df.loc[original_log_index, "processedstatus"] = "Error - Amort. Save Fail"
                payments_df.loc[original_log_index, "processedtimestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        except Exception as e:
            logger.error(f"UNHANDLED ERROR processing payment for LoanID {loan_id} (log index {original_log_index}): {e}", exc_info=True)
            payments_df.loc[original_log_index, "processedstatus"] = f"Error - Unhandled Exception"
            payments_df.loc[original_log_index, "processedtimestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # --- 4. Update Payments Log Sheet with all statuses ---
    # Ensure original column names for writing back to payments_df (if they were different from lowercase)
    # Here, we are updating the original payments_df which retained original casing if mixed.
    # If payments_df was fully lowercased, you'd need to map back or use consistent casing.
    # For this example, we assume the `payments_df.columns = payments_df.columns.str.strip().str.lower()`
    # was for processing, but the update to Sheets should use the original column names from the Sheet.
    # The `gutils.update_worksheet_from_df` currently writes the df.columns as headers.
    # It's simpler if Google Sheet column headers are consistently lowercase or match DataFrame.
    
    # Re-fetch the original headers from the sheet to ensure we write back with correct casing
    original_payments_log_sheet = gs_client.open_by_key(config.PAYMENTS_LOG_SHEET_ID).sheet1
    original_headers = original_payments_log_sheet.row_values(1)
    
    # Create a DataFrame with original headers and updated data
    payments_df_to_write = payments_df.copy()
    payments_df_to_write.columns = original_headers # Assume column order matches
    
    if not gutils.update_worksheet_from_df(gs_client, config.PAYMENTS_LOG_SHEET_ID, "Sheet1", payments_df_to_write):
        logger.error("CRITICAL: Failed to update the Payments Log sheet with processing statuses.")
    else:
        logger.info("Payments log sheet updated with all statuses.")

    logger.info("Payment processing run finished.")