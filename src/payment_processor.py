# src/payment_processor.py
import pandas as pd
from datetime import datetime
import logging
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
        return

    # --- 1. Read Payments Log ---
    payments_df_raw = gutils.get_sheet_as_df(gs_client, config.PAYMENTS_LOG_SHEET_ID, "Sheet1") # Let gutils handle basic typing
    if payments_df_raw is None: # gutils might return None on severe read error
        logger.error("Could not read Payments Log sheet (returned None). Aborting.")
        return
    if payments_df_raw.empty:
        logger.info("Payments log is empty. No payments to process.")
        return

    payments_df = payments_df_raw.copy() # Work on a copy

    # Standardize column names from Payments Log (case-insensitive, strip spaces)
    # Store original names to write back if needed, though gutils.update now takes df.columns
    original_payments_log_headers = payments_df.columns.tolist()
    payments_df.columns = [str(col).strip().lower() for col in payments_df.columns]

    # Define expected lowercase column names for clarity and checking
    # THESE MUST MATCH YOUR GOOGLE SHEET "KAF Payments Log" (after converting to lowercase)
    LOAN_ID_COL_LOG = 'loanid'
    PAYMENT_DATE_COL_LOG = 'paymentdate'
    PAYMENT_AMOUNT_COL_LOG = 'paymentamount' # Ensure this matches your sheet
    PROCESSED_STATUS_COL_LOG = 'processedstatus'
    PROCESSED_TIMESTAMP_COL_LOG = 'processedtimestamp'

    # Check for essential columns
    essential_log_cols = [LOAN_ID_COL_LOG, PAYMENT_DATE_COL_LOG, PAYMENT_AMOUNT_COL_LOG]
    for col_name in essential_log_cols:
        if col_name not in payments_df.columns:
            logger.error(f"CRITICAL: Column '{col_name}' (expected lowercase) missing from Payments Log sheet. Original headers found: {original_payments_log_headers}. Aborting.")
            return
    
    # Ensure status/timestamp columns exist, add if not (with lowercase names for processing)
    if PROCESSED_STATUS_COL_LOG not in payments_df.columns:
        payments_df[PROCESSED_STATUS_COL_LOG] = '' # Default to empty string for pending
    if PROCESSED_TIMESTAMP_COL_LOG not in payments_df.columns:
        payments_df[PROCESSED_TIMESTAMP_COL_LOG] = '' # pd.NaT might be better if column type is datetime

    # Explicit Data type conversions and cleaning for Payments Log data
    payments_df[PAYMENT_DATE_COL_LOG] = pd.to_datetime(payments_df[PAYMENT_DATE_COL_LOG], errors='coerce')
    payments_df[PAYMENT_AMOUNT_COL_LOG] = pd.to_numeric(payments_df[PAYMENT_AMOUNT_COL_LOG], errors='coerce')
    payments_df[LOAN_ID_COL_LOG] = payments_df[LOAN_ID_COL_LOG].astype(str).str.strip().str.upper() # Standardize LoanID to uppercase

    # Filter for pending payments (empty string or specific "Pending" text)
    payments_df[PROCESSED_STATUS_COL_LOG] = payments_df[PROCESSED_STATUS_COL_LOG].fillna('').astype(str).str.strip()
    pending_payments_df = payments_df[
        payments_df[PROCESSED_STATUS_COL_LOG].isin(['Pending', 'pending', '']) # Case-insensitive pending check
    ].sort_values(by=PAYMENT_DATE_COL_LOG, ascending=True).copy()

    if pending_payments_df.empty:
        logger.info("No pending payments found to process.")
        return
    logger.info(f"Found {len(pending_payments_df)} pending payments to process.")

    # --- 2. Process Each Payment ---
    for original_log_index, payment_row in pending_payments_df.iterrows():
        # Get values using the defined lowercase column names
        loan_id = payment_row[LOAN_ID_COL_LOG]
        actual_payment_date_dt = payment_row[PAYMENT_DATE_COL_LOG]
        actual_payment_amount_from_log = payment_row[PAYMENT_AMOUNT_COL_LOG] # This is the crucial part

        # Validate essential data from the payment row
        if pd.isna(loan_id) or loan_id == '':
            logger.warning(f"Skipping payment at log index {original_log_index} due to missing or blank LoanID.")
            payments_df.loc[original_log_index, PROCESSED_STATUS_COL_LOG] = "Error - Missing LoanID"
            payments_df.loc[original_log_index, PROCESSED_TIMESTAMP_COL_LOG] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            continue
        if pd.isna(actual_payment_date_dt):
            logger.warning(f"Skipping payment for LoanID {loan_id} (log index {original_log_index}) due to invalid PaymentDate.")
            payments_df.loc[original_log_index, PROCESSED_STATUS_COL_LOG] = "Error - Invalid Date"
            payments_df.loc[original_log_index, PROCESSED_TIMESTAMP_COL_LOG] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            continue
        if pd.isna(actual_payment_amount_from_log) or actual_payment_amount_from_log <= 0: # Payment must be positive
            logger.warning(f"Skipping payment for LoanID {loan_id} (log index {original_log_index}) due to invalid PaymentAmount: {actual_payment_amount_from_log}.")
            payments_df.loc[original_log_index, PROCESSED_STATUS_COL_LOG] = "Error - Invalid Amount"
            payments_df.loc[original_log_index, PROCESSED_TIMESTAMP_COL_LOG] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            continue
        
        actual_payment_date_str = actual_payment_date_dt.strftime("%Y-%m-%d")
        logger.info(f"Processing payment: LoanID={loan_id}, Date={actual_payment_date_str}, Amount={actual_payment_amount_from_log:.2f}")

        amortization_sheet_id = gutils.get_amortization_sheet_id(loan_id) # loan_id is already standardized (e.g., uppercase)
        if not amortization_sheet_id:
            logger.error(f"Amortization Google Sheet ID for LoanID '{loan_id}' not found/configured. Skipping payment.")
            payments_df.loc[original_log_index, PROCESSED_STATUS_COL_LOG] = "Error - No Amort. Sheet ID"
            payments_df.loc[original_log_index, PROCESSED_TIMESTAMP_COL_LOG] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            continue

        try:
            # Read loan terms and schedule
            loan_terms_df_raw = gutils.get_sheet_as_df(gs_client, amortization_sheet_id, "LoanTerms")
            schedule_df_raw = gutils.get_sheet_as_df(gs_client, amortization_sheet_id, "Schedule") # gutils now tries to type data

            if loan_terms_df_raw is None or schedule_df_raw is None : # Check for None explicitly
                logger.error(f"Could not read LoanTerms or Schedule for {loan_id} from sheet ID {amortization_sheet_id} (returned None).")
                payments_df.loc[original_log_index, PROCESSED_STATUS_COL_LOG] = "Error - Read Amort. Sheet"
                payments_df.loc[original_log_index, PROCESSED_TIMESTAMP_COL_LOG] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                continue
            if loan_terms_df_raw.empty or schedule_df_raw.empty:
                logger.error(f"LoanTerms or Schedule sheet is empty for {loan_id} (SheetID: {amortization_sheet_id}). Cannot process.")
                payments_df.loc[original_log_index, PROCESSED_STATUS_COL_LOG] = "Error - Empty Amort. Sheet"
                payments_df.loc[original_log_index, PROCESSED_TIMESTAMP_COL_LOG] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                continue
            
            # Standardize column names for processing
            loan_terms_df = loan_terms_df_raw.copy()
            loan_terms_df.columns = [str(col).strip().lower() for col in loan_terms_df.columns]
            
            schedule_df = schedule_df_raw.copy()
            original_schedule_headers = schedule_df.columns.tolist() # Keep original for writing back
            schedule_df.columns = [str(col).strip().lower() for col in schedule_df.columns]


            # Define expected lowercase column names for Amortization Schedule
            # THESE MUST MATCH YOUR GOOGLE SHEET "Amortization..." Schedule tab (after converting to lowercase)
            DUE_DATE_COL_SCHED = 'duedate'
            BEGIN_BAL_COL_SCHED = 'beginningbalance'
            SCHED_PMT_COL_SCHED = 'scheduledpayment'
            ACTUAL_PMT_DATE_COL_SCHED = 'actualpaymentdate'
            ACTUAL_PMT_AMT_COL_SCHED = 'actualpaymentamount' # THIS IS WHERE WE PUT THE PAYMENT
            INTEREST_PAID_COL_SCHED = 'interestpaid'
            PRINCIPAL_PAID_COL_SCHED = 'principalpaid'
            LATE_FEE_COL_SCHED = 'latefee'
            CREDIT_APPLIED_COL_SCHED = 'creditapplied'
            ENDING_BAL_COL_SCHED = 'endingbalance'
            STATUS_COL_SCHED = 'status'

            # Ensure 'parameter' and 'value' columns exist in loan_terms_df
            if 'parameter' not in loan_terms_df.columns or 'value' not in loan_terms_df.columns:
                logger.error(f"LoanTerms sheet for {loan_id} is missing 'Parameter' or 'Value' columns.")
                # ... (set error status in payments_df and continue) ...
                payments_df.loc[original_log_index, PROCESSED_STATUS_COL_LOG] = "Error - Bad LoanTerms Format"
                payments_df.loc[original_log_index, PROCESSED_TIMESTAMP_COL_LOG] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                continue

            loan_terms_s = loan_terms_df.set_index('parameter')['value'].astype(str).str.strip()

            # Explicit data type conversions for schedule_df after gutils' attempt
            # This provides more control and specific error handling if gutils typing was insufficient.
            schedule_df[DUE_DATE_COL_SCHED] = pd.to_datetime(schedule_df.get(DUE_DATE_COL_SCHED), errors='coerce')
            
            numeric_cols_schedule = [BEGIN_BAL_COL_SCHED, SCHED_PMT_COL_SCHED, ACTUAL_PMT_AMT_COL_SCHED,
                                     INTEREST_PAID_COL_SCHED, PRINCIPAL_PAID_COL_SCHED, LATE_FEE_COL_SCHED,
                                     CREDIT_APPLIED_COL_SCHED, ENDING_BAL_COL_SCHED]
            for col in numeric_cols_schedule:
                if col in schedule_df.columns:
                    schedule_df[col] = pd.to_numeric(schedule_df[col], errors='coerce') # .fillna(0.0) is risky if NaN means "not yet paid"
                else: # If a calculation column is missing, add it and fill with 0 or NaN as appropriate
                    schedule_df[col] = 0.0 if col != ACTUAL_PMT_AMT_COL_SCHED else pd.NA # Actual Pmt Amt is NA until paid

            if ACTUAL_PMT_DATE_COL_SCHED in schedule_df.columns:
                schedule_df[ACTUAL_PMT_DATE_COL_SCHED] = pd.to_datetime(schedule_df[ACTUAL_PMT_DATE_COL_SCHED], errors='coerce')
            else:
                schedule_df[ACTUAL_PMT_DATE_COL_SCHED] = pd.NaT # Not a Time, for missing dates

            if STATUS_COL_SCHED not in schedule_df.columns: # If status column is missing
                schedule_df[STATUS_COL_SCHED] = "Due"


            # Fetch necessary loan terms, with defaults or error handling
            try:
                annual_interest_rate = float(loan_terms_s.get("annualinterestrate", 0.0)) # Ensure key matches your LoanTerms sheet
                late_fee_percentage = float(loan_terms_s.get("latefeepercentage", config.DEFAULT_LATE_FEE_PERCENTAGE))
                grace_period_days = int(loan_terms_s.get("graceperioddays", config.DEFAULT_GRACE_PERIOD_DAYS))
            except ValueError as ve:
                logger.error(f"Invalid numeric value in LoanTerms for {loan_id}: {ve}. Loan terms found: {loan_terms_s.to_dict()}")
                payments_df.loc[original_log_index, PROCESSED_STATUS_COL_LOG] = "Error - Invalid LoanTerms Value"
                payments_df.loc[original_log_index, PROCESSED_TIMESTAMP_COL_LOG] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                continue

            # Find the target row for applying the payment
            target_row_idx = -1
            for i, schedule_row in schedule_df.iterrows():
                # A row is eligible if ActualPaymentDate is NaT (Not a Time) 
                # OR if its Status suggests it's still open (e.g. "Due", "Partially Paid", or empty)
                current_status = str(schedule_row.get(STATUS_COL_SCHED, "Due")).strip().lower()
                actual_payment_date_in_schedule = schedule_row.get(ACTUAL_PMT_DATE_COL_SCHED)

                if pd.isna(actual_payment_date_in_schedule) or current_status in ["due", "partially paid", ""]:
                    target_row_idx = i
                    break
            
            if target_row_idx == -1:
                logger.info(f"No eligible due payment slots found for {loan_id}. This payment might be an overpayment or error.")
                payments_df.loc[original_log_index, PROCESSED_STATUS_COL_LOG] = "Error - No Due Payment Slot"
                payments_df.loc[original_log_index, PROCESSED_TIMESTAMP_COL_LOG] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                continue

            # --- Crucial: Get data from the *identified target row* in the schedule ---
            due_date_dt_sched = schedule_df.loc[target_row_idx, DUE_DATE_COL_SCHED]
            if pd.isna(due_date_dt_sched):
                logger.error(f"CRITICAL: DueDate is missing or invalid for LoanID {loan_id} at schedule row index {target_row_idx}.")
                payments_df.loc[original_log_index, PROCESSED_STATUS_COL_LOG] = "Error - Invalid DueDate in Sched"
                # ... (set timestamp and continue) ...
                continue
            due_date_str_sched = due_date_dt_sched.strftime("%Y-%m-%d")
            
            # IMPORTANT: The beginning_balance for calculation MUST come from this target row
            beginning_balance_for_calc = pd.to_numeric(schedule_df.loc[target_row_idx, BEGIN_BAL_COL_SCHED], errors='coerce')
            if pd.isna(beginning_balance_for_calc):
                logger.error(f"CRITICAL: BeginningBalance is missing or invalid for LoanID {loan_id} at schedule row index {target_row_idx}.")
                payments_df.loc[original_log_index, PROCESSED_STATUS_COL_LOG] = "Error - Invalid BeginBal in Sched"
                # ... (set timestamp and continue) ...
                continue

            scheduled_payment_on_schedule = pd.to_numeric(schedule_df.loc[target_row_idx, SCHED_PMT_COL_SCHED], errors='coerce')
            if pd.isna(scheduled_payment_on_schedule): # Scheduled payment might be 0 for interest-only periods or final payment
                logger.warning(f"ScheduledPayment is missing or invalid for LoanID {loan_id} at schedule row {target_row_idx}. Assuming 0.0 if calculation needs it.")
                scheduled_payment_on_schedule = 0.0


            payment_calcs = calculate_payment_details(
                beginning_balance_for_calc, # Use the BB from the target row
                annual_interest_rate,
                30, # payment_frequency_days (approx monthly)
                scheduled_payment_on_schedule,
                actual_payment_amount_from_log, # Use the amount from the payment log
                due_date_str_sched, # Due date from the target row
                actual_payment_date_str, # Actual payment date from the payment log
                late_fee_percentage,
                grace_period_days
            )

            # Update the schedule DataFrame (target_row_idx) with calculated values AND the payment amount from log
            schedule_df.loc[target_row_idx, ACTUAL_PMT_DATE_COL_SCHED] = pd.to_datetime(actual_payment_date_str)
            schedule_df.loc[target_row_idx, ACTUAL_PMT_AMT_COL_SCHED] = actual_payment_amount_from_log # <<<< KEY FIX
            schedule_df.loc[target_row_idx, INTEREST_PAID_COL_SCHED] = payment_calcs["InterestPaid"]
            schedule_df.loc[target_row_idx, PRINCIPAL_PAID_COL_SCHED] = payment_calcs["PrincipalPaid"]
            schedule_df.loc[target_row_idx, LATE_FEE_COL_SCHED] = payment_calcs["LateFee"]
            schedule_df.loc[target_row_idx, CREDIT_APPLIED_COL_SCHED] = payment_calcs["CreditApplied"]
            schedule_df.loc[target_row_idx, ENDING_BAL_COL_SCHED] = payment_calcs["EndingBalance"]
            schedule_df.loc[target_row_idx, STATUS_COL_SCHED] = payment_calcs["Status"]

            # --- CRUCIAL: Update the BeginningBalance for the *next* scheduled row ---
            # This should only happen if the next row is not already paid/processed.
            next_row_idx = target_row_idx + 1
            if next_row_idx < len(schedule_df):
                # Check if the next row is already paid
                next_row_actual_payment_date = schedule_df.loc[next_row_idx, ACTUAL_PMT_DATE_COL_SCHED]
                next_row_status = str(schedule_df.loc[next_row_idx, STATUS_COL_SCHED]).strip().lower()
                
                is_next_row_paid_off = (pd.notna(next_row_actual_payment_date) and 
                                      (next_row_status.startswith("paid") or next_row_status == "paid off"))

                if not is_next_row_paid_off:
                    logger.info(f"Updating BeginningBalance for next period (row {next_row_idx}) for {loan_id} to: {payment_calcs['EndingBalance']:.2f}")
                    schedule_df.loc[next_row_idx, BEGIN_BAL_COL_SCHED] = payment_calcs["EndingBalance"]
                else:
                    logger.info(f"Next period (row {next_row_idx}) for {loan_id} is already paid/processed. Not updating its BeginningBalance.")
            
            # Prepare schedule_df for writing: assign original headers back
            # This assumes the order and number of columns in schedule_df (after processing)
            # matches original_schedule_headers. If columns were added/removed, this needs care.
            # For simplicity, if we only modified values, this should be fine.
            # If structure changed, rebuild df with original_schedule_headers and data from processed schedule_df.
            schedule_df_to_write = schedule_df.copy()
            try:
                schedule_df_to_write.columns = original_schedule_headers
            except ValueError as ve_cols:
                logger.error(f"Column mismatch when trying to write schedule for {loan_id}. Processed cols: {schedule_df.columns.tolist()}, Original headers: {original_schedule_headers}. Error: {ve_cols}")
                # Handle error - maybe skip writing this schedule or try to align columns.
                # For now, attempt to write with processed (lowercase) headers.
                # This might change headers in Google Sheet if they were originally mixed case.
                logger.warning(f"Attempting to write schedule for {loan_id} with processed (lowercase) headers.")


            if gutils.update_worksheet_from_df(gs_client, amortization_sheet_id, "Schedule", schedule_df_to_write):
                payments_df.loc[original_log_index, PROCESSED_STATUS_COL_LOG] = "Processed"
                payments_df.loc[original_log_index, PROCESSED_TIMESTAMP_COL_LOG] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                logger.info(f"Successfully processed payment for {loan_id} (log index {original_log_index}). Amortization Status: {payment_calcs['Status']}")
            else:
                # Error already logged by gutils.update_worksheet_from_df
                payments_df.loc[original_log_index, PROCESSED_STATUS_COL_LOG] = "Error - Amort. Save Fail"
                payments_df.loc[original_log_index, PROCESSED_TIMESTAMP_COL_LOG] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        except Exception as e:
            logger.error(f"UNHANDLED EXCEPTION processing payment for LoanID {loan_id} (log index {original_log_index}): {e}", exc_info=True)
            payments_df.loc[original_log_index, PROCESSED_STATUS_COL_LOG] = f"Error - Unhandled Exception"
            payments_df.loc[original_log_index, PROCESSED_TIMESTAMP_COL_LOG] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
    # --- 4. Update Payments Log Sheet with all statuses ---
    # Create a DataFrame for writing with the original headers to preserve casing in Google Sheet
    payments_df_to_write_log = pd.DataFrame(columns=original_payments_log_headers)
    for col_idx, original_header in enumerate(original_payments_log_headers):
        processed_col_name = str(original_header).strip().lower()
        if processed_col_name in payments_df.columns:
            payments_df_to_write_log[original_header] = payments_df[processed_col_name]
        else:
            # If a column was in original but not after processing (e.g. dropped), fill with empty
            payments_df_to_write_log[original_header] = [''] * len(payments_df)


    if not gutils.update_worksheet_from_df(gs_client, config.PAYMENTS_LOG_SHEET_ID, "Sheet1", payments_df_to_write_log):
        logger.error("CRITICAL: Failed to update the Payments Log sheet with processing statuses.")
    else:
        logger.info("Payments log sheet updated with all statuses.")

    logger.info("Payment processing run finished.")