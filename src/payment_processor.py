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
        logger.error(f"CRITICAL: Failed to initialize Google Sheets client: {e}. Aborting payment processing.")
        return

    payments_log_df_original_state = gutils.get_sheet_as_df(gs_client, config.PAYMENTS_LOG_SHEET_ID, "Sheet1")
    
    if payments_log_df_original_state is None:
        logger.error("CRITICAL: Could not read Payments Log sheet (returned None). Aborting.")
        return
    if payments_log_df_original_state.empty:
        logger.info("Payments log is empty. No payments to process.")
        return

    original_payments_log_headers = payments_log_df_original_state.columns.tolist()
    payments_df_processing = payments_log_df_original_state.copy()
    payments_df_processing.columns = [str(col).strip().lower() for col in payments_df_processing.columns]

    LOAN_ID_COL_LOG = 'loanid'
    PAYMENT_DATE_COL_LOG = 'paymentdate'
    PAYMENT_AMOUNT_COL_LOG = 'paymentamount'
    PROCESSED_STATUS_COL_LOG = 'processedstatus'
    PROCESSED_TIMESTAMP_COL_LOG = 'processedtimestamp'

    essential_log_cols = [LOAN_ID_COL_LOG, PAYMENT_DATE_COL_LOG, PAYMENT_AMOUNT_COL_LOG]
    for col_name in essential_log_cols:
        if col_name not in payments_df_processing.columns:
            logger.error(f"CRITICAL: Essential column '{col_name}' missing from Payments Log. Headers: {original_payments_log_headers}. Aborting.")
            return 
    
    if PROCESSED_STATUS_COL_LOG not in payments_df_processing.columns:
        payments_df_processing[PROCESSED_STATUS_COL_LOG] = ''
    if PROCESSED_TIMESTAMP_COL_LOG not in payments_df_processing.columns:
        payments_df_processing[PROCESSED_TIMESTAMP_COL_LOG] = pd.NaT

    # --- Strict Data Type Conversions and Validation for Payments Log Data ---
    # We iterate through the processing DataFrame to validate and type data.
    # Errors found here will update the 'payments_log_df_original_state' for final write-back.
    # We also mark rows in 'payments_df_processing' if they have parsing errors to exclude them later.
    
    # Add a temporary column to payments_df_processing to mark rows with parsing errors
    PARSING_ERROR_FLAG_COL = '_parsing_error'
    payments_df_processing[PARSING_ERROR_FLAG_COL] = False

    for index, row in payments_df_processing.iterrows():
        current_status_original = str(payments_log_df_original_state.loc[index, PROCESSED_STATUS_COL_LOG]).strip().lower()
        # Only validate rows that are not already marked as 'processed' or 'error' in the original log
        if current_status_original.startswith('processed') or current_status_original.startswith('error'):
            # If it's already processed or errored from a *previous* run, mark it so it's not re-processed
            # and also ensure it doesn't get flagged as a *new* parsing error.
            payments_df_processing.loc[index, PARSING_ERROR_FLAG_COL] = True # Effectively excludes it from pending
            continue

        parsing_error_this_row = False
        # LoanID
        loan_id_val = str(row.get(LOAN_ID_COL_LOG, '')).strip().upper()
        if not loan_id_val:
            logger.warning(f"Log row {index}: LoanID is missing. Marking as error.")
            payments_log_df_original_state.loc[index, PROCESSED_STATUS_COL_LOG] = "Error - Missing LoanID in Log"
            parsing_error_this_row = True
        else:
            payments_df_processing.loc[index, LOAN_ID_COL_LOG] = loan_id_val

        # PaymentDate (expect YYYY-MM-DD)
        raw_date_val = row.get(PAYMENT_DATE_COL_LOG)
        parsed_date_val = pd.NaT
        try:
            parsed_date_val = pd.to_datetime(raw_date_val, format='%Y-%m-%d', errors='raise')
        except (ValueError, TypeError):
            try: 
                parsed_date_val = pd.to_datetime(raw_date_val, errors='raise') # General parse
                logger.warning(f"Log row {index}, LoanID {loan_id_val if loan_id_val else 'N/A'}: PaymentDate '{raw_date_val}' not in YYYY-MM-DD. Parsed generally. Correct source format.")
            except (ValueError, TypeError):
                logger.warning(f"Log row {index}, LoanID {loan_id_val if loan_id_val else 'N/A'}: PaymentDate '{raw_date_val}' is invalid. Marking as error.")
                payments_log_df_original_state.loc[index, PROCESSED_STATUS_COL_LOG] = "Error - Invalid PaymentDate in Log"
                parsing_error_this_row = True
        payments_df_processing.loc[index, PAYMENT_DATE_COL_LOG] = parsed_date_val # Store NaT if parsing failed

        # PaymentAmount (expect positive number)
        raw_amount_val = row.get(PAYMENT_AMOUNT_COL_LOG)
        parsed_amount_val = pd.NA # Use pd.NA for numeric missing initially
        try:
            parsed_amount_val = float(raw_amount_val)
            if parsed_amount_val <= 0:
                raise ValueError("Payment amount must be positive.")
        except (ValueError, TypeError):
            logger.warning(f"Log row {index}, LoanID {loan_id_val if loan_id_val else 'N/A'}: PaymentAmount '{raw_amount_val}' is invalid or not positive. Marking as error.")
            payments_log_df_original_state.loc[index, PROCESSED_STATUS_COL_LOG] = "Error - Invalid PaymentAmount in Log"
            parsing_error_this_row = True
        payments_df_processing.loc[index, PAYMENT_AMOUNT_COL_LOG] = parsed_amount_val


        if parsing_error_this_row:
            payments_log_df_original_state.loc[index, PROCESSED_TIMESTAMP_COL_LOG] = datetime.now()
            payments_df_processing.loc[index, PARSING_ERROR_FLAG_COL] = True


    # Filter for pending payments:
    # - Not already marked with a parsing error in this run.
    # - Original status (from sheet) is not 'processed' or 'error' (case-insensitive start).
    
    # Ensure processedstatus in processing_df is up-to-date for filtering logic
    payments_df_processing[PROCESSED_STATUS_COL_LOG] = payments_df_processing[PROCESSED_STATUS_COL_LOG].fillna('').astype(str).str.strip().str.lower()

    pending_mask = \
        (payments_df_processing[PARSING_ERROR_FLAG_COL] == False) & \
        (~payments_df_processing[PROCESSED_STATUS_COL_LOG].str.startswith('error', na=False)) & \
        (~payments_df_processing[PROCESSED_STATUS_COL_LOG].str.startswith('processed', na=False)) & \
        (payments_df_processing[PROCESSED_STATUS_COL_LOG].isin(['pending', '']))


    pending_payments_to_process_df = payments_df_processing[pending_mask].sort_values(by=PAYMENT_DATE_COL_LOG, ascending=True).copy()
    pending_payments_to_process_df.drop(columns=[PARSING_ERROR_FLAG_COL], inplace=True, errors='ignore')


    if pending_payments_to_process_df.empty:
        logger.info("No valid pending payments found to process after initial validation pass.")
        # Write back payments_log_df_original_state if any parsing errors were logged onto it
        # This is to ensure errors from the validation loop are saved.
        if (payments_log_df_original_state[PROCESSED_STATUS_COL_LOG].str.lower().str.startswith('error',na=False)).any():
            final_payments_log_to_write = pd.DataFrame(columns=original_payments_log_headers) # Prepare with original headers
            for original_header in original_payments_log_headers:
                # Map original header to its potential lowercase version used internally if necessary,
                # or directly use original_header if payments_log_df_original_state still uses them.
                if original_header in payments_log_df_original_state.columns:
                    final_payments_log_to_write[original_header] = payments_log_df_original_state[original_header]
                else: # Fallback if column name was somehow lost (should not happen with copy)
                     logger.warning(f"Header '{original_header}' missing in final log state, filling empty.")
                     final_payments_log_to_write[original_header] = [''] * len(payments_log_df_original_state)

            if not gutils.update_worksheet_from_df(gs_client, config.PAYMENTS_LOG_SHEET_ID, "Sheet1", final_payments_log_to_write):
                logger.error("CRITICAL: Failed to update Payments Log sheet with initial parsing error statuses after finding no pending payments.")
            else:
                logger.info("Payments Log sheet updated with initial parsing error statuses (no further payments processed).")
        return
        
    logger.info(f"Found {len(pending_payments_to_process_df)} payments to attempt processing.")

    # --- 2. Process Each Valid Pending Payment ---
    for original_log_index, payment_row_data_to_process in pending_payments_to_process_df.iterrows():
        loan_id = payment_row_data_to_process[LOAN_ID_COL_LOG]
        actual_payment_date_dt = payment_row_data_to_process[PAYMENT_DATE_COL_LOG]
        actual_payment_amount_from_log = payment_row_data_to_process[PAYMENT_AMOUNT_COL_LOG]

        # ---- ADDED SAFEGUARD for NaT just before strftime ----
        if pd.isna(actual_payment_date_dt):
            logger.error(f"CRITICAL INTERNAL ERROR: PaymentDate for LoanID {loan_id} (log index {original_log_index}) is NaT at processing stage. This should have been caught earlier. Skipping.")
            payments_log_df_original_state.loc[original_log_index, PROCESSED_STATUS_COL_LOG] = "Error - Internal NaT Date"
            payments_log_df_original_state.loc[original_log_index, PROCESSED_TIMESTAMP_COL_LOG] = datetime.now()
            continue 
        # ---- END SAFEGUARD ----

        actual_payment_date_str = actual_payment_date_dt.strftime("%Y-%m-%d") # Error was here
        logger.info(f"Processing payment from log index {original_log_index}: LoanID={loan_id}, Date={actual_payment_date_str}, Amount={actual_payment_amount_from_log:.2f}")

        # ... (rest of the processing logic for amortization sheets from previous correct version) ...
        # Ensure all error handling within this try-except block updates 'payments_log_df_original_state.loc[original_log_index, ...]'
        amortization_sheet_id = gutils.get_amortization_sheet_id(loan_id)
        if not amortization_sheet_id:
            logger.error(f"Amortization Google Sheet ID for LoanID '{loan_id}' not found. Log index {original_log_index}.")
            payments_log_df_original_state.loc[original_log_index, PROCESSED_STATUS_COL_LOG] = "Error - No Amort. Sheet ID"
            payments_log_df_original_state.loc[original_log_index, PROCESSED_TIMESTAMP_COL_LOG] = datetime.now()
            continue

        try:
            loan_terms_df_raw = gutils.get_sheet_as_df(gs_client, amortization_sheet_id, "LoanTerms")
            schedule_df_raw = gutils.get_sheet_as_df(gs_client, amortization_sheet_id, "Schedule")

            if loan_terms_df_raw is None or schedule_df_raw is None or loan_terms_df_raw.empty or schedule_df_raw.empty:
                logger.error(f"Could not read or empty LoanTerms/Schedule for {loan_id} (SheetID: {amortization_sheet_id}). Log index {original_log_index}.")
                payments_log_df_original_state.loc[original_log_index, PROCESSED_STATUS_COL_LOG] = "Error - Read/Empty Amort. Sheet"
                payments_log_df_original_state.loc[original_log_index, PROCESSED_TIMESTAMP_COL_LOG] = datetime.now()
                continue

            loan_terms_df = loan_terms_df_raw.copy()
            loan_terms_df.columns = [str(col).strip().lower() for col in loan_terms_df.columns]
            schedule_df = schedule_df_raw.copy()
            original_schedule_headers = schedule_df.columns.tolist()
            schedule_df.columns = [str(col).strip().lower() for col in schedule_df.columns]

            DUE_DATE_COL_SCHED = 'duedate'
            BEGIN_BAL_COL_SCHED = 'beginningbalance'
            SCHED_PMT_COL_SCHED = 'scheduledpayment'
            ACTUAL_PMT_DATE_COL_SCHED = 'actualpaymentdate'
            ACTUAL_PMT_AMT_COL_SCHED = 'actualpaymentamount'
            INTEREST_PAID_COL_SCHED = 'interestpaid'
            PRINCIPAL_PAID_COL_SCHED = 'principalpaid'
            LATE_FEE_COL_SCHED = 'latefee'
            CREDIT_APPLIED_COL_SCHED = 'creditapplied'
            ENDING_BAL_COL_SCHED = 'endingbalance'
            STATUS_COL_SCHED = 'status'
            
            if 'parameter' not in loan_terms_df.columns or 'value' not in loan_terms_df.columns:
                logger.error(f"LoanTerms sheet for {loan_id} is missing 'parameter' or 'value' columns. Log index {original_log_index}.")
                payments_log_df_original_state.loc[original_log_index, PROCESSED_STATUS_COL_LOG] = "Error - Bad LoanTerms Format"
                payments_log_df_original_state.loc[original_log_index, PROCESSED_TIMESTAMP_COL_LOG] = datetime.now()
                continue
            loan_terms_s = loan_terms_df.set_index('parameter')['value'].astype(str).str.strip()

            schedule_df[DUE_DATE_COL_SCHED] = pd.to_datetime(schedule_df.get(DUE_DATE_COL_SCHED), format='%Y-%m-%d', errors='coerce')
            numeric_cols_schedule = [BEGIN_BAL_COL_SCHED, SCHED_PMT_COL_SCHED, ACTUAL_PMT_AMT_COL_SCHED, INTEREST_PAID_COL_SCHED, PRINCIPAL_PAID_COL_SCHED, LATE_FEE_COL_SCHED, CREDIT_APPLIED_COL_SCHED, ENDING_BAL_COL_SCHED]
            for col in numeric_cols_schedule: schedule_df[col] = pd.to_numeric(schedule_df.get(col), errors='coerce')
            schedule_df[ACTUAL_PMT_DATE_COL_SCHED] = pd.to_datetime(schedule_df.get(ACTUAL_PMT_DATE_COL_SCHED), format='%Y-%m-%d', errors='coerce')
            if STATUS_COL_SCHED not in schedule_df.columns: schedule_df[STATUS_COL_SCHED] = "Due"

            try:
                annual_interest_rate_str = loan_terms_s.get("annualinterestrate", "0.0")
                annual_interest_rate = float(annual_interest_rate_str)
                if annual_interest_rate < 0: raise ValueError("Annual interest rate cannot be negative.")
                late_fee_percentage_str = loan_terms_s.get("latefeepercentage", str(config.DEFAULT_LATE_FEE_PERCENTAGE))
                late_fee_percentage = float(late_fee_percentage_str)
                grace_period_days_str = loan_terms_s.get("graceperioddays", str(config.DEFAULT_GRACE_PERIOD_DAYS))
                grace_period_days = int(grace_period_days_str)
            except (ValueError, TypeError) as ve:
                logger.error(f"Invalid LoanTerms value for {loan_id}: {ve}. Key 'annualinterestrate' was '{annual_interest_rate_str}'. Log index {original_log_index}.")
                payments_log_df_original_state.loc[original_log_index, PROCESSED_STATUS_COL_LOG] = "Error - Invalid LoanTerms Value"
                payments_log_df_original_state.loc[original_log_index, PROCESSED_TIMESTAMP_COL_LOG] = datetime.now()
                continue
            
            target_row_idx = -1
            for i, schedule_row_iter in schedule_df.iterrows():
                current_status = str(schedule_row_iter.get(STATUS_COL_SCHED, "Due")).strip().lower()
                actual_payment_date_in_schedule = schedule_row_iter.get(ACTUAL_PMT_DATE_COL_SCHED)
                if pd.isna(actual_payment_date_in_schedule) or current_status in ["due", "partially paid", ""]:
                    target_row_idx = i
                    break
            
            if target_row_idx == -1:
                logger.warning(f"No eligible due payment slots found for {loan_id}. Log index {original_log_index}.")
                payments_log_df_original_state.loc[original_log_index, PROCESSED_STATUS_COL_LOG] = "Error - No Due Payment Slot"
                payments_log_df_original_state.loc[original_log_index, PROCESSED_TIMESTAMP_COL_LOG] = datetime.now()
                continue

            due_date_dt_sched = schedule_df.loc[target_row_idx, DUE_DATE_COL_SCHED]
            if pd.isna(due_date_dt_sched):
                logger.error(f"DueDate invalid in Amort. Sched. for {loan_id}, row {target_row_idx}. Log index {original_log_index}.")
                payments_log_df_original_state.loc[original_log_index, PROCESSED_STATUS_COL_LOG] = "Error - Invalid Sched. DueDate"
                payments_log_df_original_state.loc[original_log_index, PROCESSED_TIMESTAMP_COL_LOG] = datetime.now()
                continue
            due_date_str_sched = due_date_dt_sched.strftime("%Y-%m-%d")
            
            beginning_balance_for_calc = schedule_df.loc[target_row_idx, BEGIN_BAL_COL_SCHED]
            if pd.isna(beginning_balance_for_calc):
                logger.error(f"BeginBal invalid in Amort. Sched. for {loan_id}, row {target_row_idx}. Log index {original_log_index}.")
                payments_log_df_original_state.loc[original_log_index, PROCESSED_STATUS_COL_LOG] = "Error - Invalid Sched. BeginBal"
                payments_log_df_original_state.loc[original_log_index, PROCESSED_TIMESTAMP_COL_LOG] = datetime.now()
                continue

            scheduled_payment_on_schedule = schedule_df.loc[target_row_idx, SCHED_PMT_COL_SCHED]
            if pd.isna(scheduled_payment_on_schedule): scheduled_payment_on_schedule = 0.0

            payment_calcs = calculate_payment_details(beginning_balance_for_calc, annual_interest_rate, 30, scheduled_payment_on_schedule, actual_payment_amount_from_log, due_date_str_sched, actual_payment_date_str, late_fee_percentage, grace_period_days)

            schedule_df.loc[target_row_idx, ACTUAL_PMT_DATE_COL_SCHED] = pd.to_datetime(actual_payment_date_str)
            schedule_df.loc[target_row_idx, ACTUAL_PMT_AMT_COL_SCHED] = actual_payment_amount_from_log
            schedule_df.loc[target_row_idx, INTEREST_PAID_COL_SCHED] = payment_calcs["InterestPaid"]
            schedule_df.loc[target_row_idx, PRINCIPAL_PAID_COL_SCHED] = payment_calcs["PrincipalPaid"]
            schedule_df.loc[target_row_idx, LATE_FEE_COL_SCHED] = payment_calcs["LateFee"]
            schedule_df.loc[target_row_idx, CREDIT_APPLIED_COL_SCHED] = payment_calcs["CreditApplied"]
            schedule_df.loc[target_row_idx, ENDING_BAL_COL_SCHED] = payment_calcs["EndingBalance"]
            schedule_df.loc[target_row_idx, STATUS_COL_SCHED] = payment_calcs["Status"]

            next_row_idx = target_row_idx + 1
            if next_row_idx < len(schedule_df):
                is_next_row_paid_off = pd.notna(schedule_df.loc[next_row_idx, ACTUAL_PMT_DATE_COL_SCHED]) and str(schedule_df.loc[next_row_idx, STATUS_COL_SCHED]).lower().startswith("paid")
                if not is_next_row_paid_off:
                    schedule_df.loc[next_row_idx, BEGIN_BAL_COL_SCHED] = payment_calcs["EndingBalance"]

            schedule_df_to_write = schedule_df.copy()
            schedule_df_to_write.columns = original_schedule_headers
            if gutils.update_worksheet_from_df(gs_client, amortization_sheet_id, "Schedule", schedule_df_to_write):
                payments_log_df_original_state.loc[original_log_index, PROCESSED_STATUS_COL_LOG] = "Processed"
                payments_log_df_original_state.loc[original_log_index, PROCESSED_TIMESTAMP_COL_LOG] = datetime.now()
                logger.info(f"Successfully processed payment for {loan_id} (log index {original_log_index}).")
            else:
                payments_log_df_original_state.loc[original_log_index, PROCESSED_STATUS_COL_LOG] = "Error - Amort. Save Fail"
                payments_log_df_original_state.loc[original_log_index, PROCESSED_TIMESTAMP_COL_LOG] = datetime.now()

        except Exception as e:
            logger.error(f"UNHANDLED EXCEPTION for LoanID {loan_id} (log index {original_log_index}): {e}", exc_info=True)
            payments_log_df_original_state.loc[original_log_index, PROCESSED_STATUS_COL_LOG] = "Error - Unhandled Exception"
            payments_log_df_original_state.loc[original_log_index, PROCESSED_TIMESTAMP_COL_LOG] = datetime.now()
        
    # --- 4. Update Payments Log Sheet with ALL statuses from payments_log_df_original_state ---
    final_payments_log_to_write = pd.DataFrame(columns=original_payments_log_headers)
    for original_header in original_payments_log_headers:
        if original_header in payments_log_df_original_state.columns:
            final_payments_log_to_write[original_header] = payments_log_df_original_state[original_header]
        else:
            logger.warning(f"Header '{original_header}' from sheet not in final log state. Filling empty.")
            final_payments_log_to_write[original_header] = [''] * len(payments_log_df_original_state)

    if not gutils.update_worksheet_from_df(gs_client, config.PAYMENTS_LOG_SHEET_ID, "Sheet1", final_payments_log_to_write):
        logger.error("CRITICAL: Failed to update Payments Log sheet with final processing statuses.")
    else:
        logger.info("Payments Log sheet updated with all final statuses.")

    logger.info("Payment processing run finished.")