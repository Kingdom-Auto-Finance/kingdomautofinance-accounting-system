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
    
    if payments_log_df_original_state is None or payments_log_df_original_state.empty:
        logger.info("Payments log is empty or could not be read. No payments to process.")
        return

    original_payments_log_headers = payments_log_df_original_state.columns.tolist()
    payments_df_for_validation = payments_log_df_original_state.copy()
    payments_df_for_validation.columns = [str(col).strip().lower() for col in payments_df_for_validation.columns]

    LOAN_ID_COL_LOG = 'loanid'
    PAYMENT_DATE_COL_LOG = 'paymentdate'
    PAYMENT_AMOUNT_COL_LOG = 'paymentamount'
    PROCESSED_STATUS_COL_LOG = 'processedstatus'
    PROCESSED_TIMESTAMP_COL_LOG = 'processedtimestamp'

    original_status_col_name = next((h for h in original_payments_log_headers if str(h).strip().lower() == PROCESSED_STATUS_COL_LOG), PROCESSED_STATUS_COL_LOG)
    original_timestamp_col_name = next((h for h in original_payments_log_headers if str(h).strip().lower() == PROCESSED_TIMESTAMP_COL_LOG), PROCESSED_TIMESTAMP_COL_LOG)

    essential_log_cols = [LOAN_ID_COL_LOG, PAYMENT_DATE_COL_LOG, PAYMENT_AMOUNT_COL_LOG]
    for col_name in essential_log_cols:
        if col_name not in payments_df_for_validation.columns:
            logger.error(f"CRITICAL: Essential column '{col_name}' missing from Payments Log. Headers: {original_payments_log_headers}. Aborting.")
            return 
    
    if original_status_col_name not in payments_log_df_original_state.columns:
        payments_log_df_original_state[original_status_col_name] = ''
    if original_timestamp_col_name not in payments_log_df_original_state.columns:
        payments_log_df_original_state[original_timestamp_col_name] = pd.NaT


    valid_for_processing_indices = []
    rows_with_initial_errors = False # Flag to check if any errors occurred during validation

    for index, row_to_validate in payments_df_for_validation.iterrows():
        current_original_status = str(payments_log_df_original_state.loc[index, original_status_col_name]).strip().lower()
        if current_original_status.startswith('processed') or current_original_status.startswith('error'):
            continue 

        has_parsing_error_this_row = False
        
        # Validate LoanID
        loan_id_val = str(row_to_validate.get(LOAN_ID_COL_LOG, '')).strip().upper()
        if not loan_id_val or loan_id_val == "NAN": # Check for empty string or literal "NAN"
            logger.warning(f"Log row index {index}: LoanID is '{loan_id_val}'. Marking as error.")
            payments_log_df_original_state.loc[index, original_status_col_name] = "Error - Invalid/Missing LoanID in Log"
            has_parsing_error_this_row = True
        else:
            payments_df_for_validation.loc[index, LOAN_ID_COL_LOG] = loan_id_val

        # Validate PaymentDate (expect YYYY-MM-DD)
        raw_date_val = row_to_validate.get(PAYMENT_DATE_COL_LOG)
        parsed_date_val = pd.NaT # Default to NaT
        if not has_parsing_error_this_row:
            try:
                # Attempt to parse with specific format first, then general
                if pd.notna(raw_date_val) and str(raw_date_val).strip() != "": # Only parse if not already NA or empty
                    parsed_date_val = pd.to_datetime(raw_date_val, format='%Y-%m-%d', errors='raise')
                elif pd.isna(raw_date_val) or str(raw_date_val).strip() == "": # If it's blank or NaN, it's an error
                    raise ValueError("Date string is empty or missing")
            except (ValueError, TypeError): # Catch if specific format fails
                try: 
                    if pd.notna(raw_date_val) and str(raw_date_val).strip() != "":
                        parsed_date_val = pd.to_datetime(raw_date_val, errors='raise') # General parse as fallback
                        logger.warning(f"Log row index {index}, LoanID {loan_id_val}: PaymentDate '{raw_date_val}' not YYYY-MM-DD. Parsed generally. Correct source.")
                    else: # If still blank or NaN after first try
                        raise ValueError("Date string is empty or missing after fallback attempt")
                except (ValueError, TypeError): # Catch if general parse also fails or it was empty
                    logger.warning(f"Log row index {index}, LoanID {loan_id_val}: PaymentDate '{raw_date_val}' is invalid or missing. Marking as error.")
                    payments_log_df_original_state.loc[index, original_status_col_name] = "Error - Invalid PaymentDate in Log"
                    has_parsing_error_this_row = True
        payments_df_for_validation.loc[index, PAYMENT_DATE_COL_LOG] = parsed_date_val # Store parsed date (or NaT if error)

        # Validate PaymentAmount (expect positive number)
        raw_amount_val = row_to_validate.get(PAYMENT_AMOUNT_COL_LOG)
        parsed_amount_val = pd.NA 
        if not has_parsing_error_this_row:
            try:
                if pd.isna(raw_amount_val) or str(raw_amount_val).strip() == "":
                    raise ValueError("Payment amount is empty or missing")
                parsed_amount_val = float(raw_amount_val)
                if parsed_amount_val <= 0:
                    raise ValueError("Payment amount must be positive.")
            except (ValueError, TypeError):
                logger.warning(f"Log row index {index}, LoanID {loan_id_val}: PaymentAmount '{raw_amount_val}' invalid/missing/not positive. Marking as error.")
                payments_log_df_original_state.loc[index, original_status_col_name] = "Error - Invalid PaymentAmount in Log"
                has_parsing_error_this_row = True
        payments_df_for_validation.loc[index, PAYMENT_AMOUNT_COL_LOG] = parsed_amount_val


        if has_parsing_error_this_row:
            payments_log_df_original_state.loc[index, original_timestamp_col_name] = datetime.now()
            rows_with_initial_errors = True # Flag that at least one error occurred
        else:
            # Only add to valid_for_processing_indices if ALL critical fields are valid
            # Specifically, ensure parsed_date_val is NOT NaT
            if pd.notna(payments_df_for_validation.loc[index, LOAN_ID_COL_LOG]) and \
               payments_df_for_validation.loc[index, LOAN_ID_COL_LOG] != "NAN" and \
               pd.notna(payments_df_for_validation.loc[index, PAYMENT_DATE_COL_LOG]) and \
               pd.notna(payments_df_for_validation.loc[index, PAYMENT_AMOUNT_COL_LOG]):
                valid_for_processing_indices.append(index)
            else: # Should have been caught by has_parsing_error_this_row, but as a safeguard
                logger.warning(f"Log row index {index}, LoanID {loan_id_val}: Row marked invalid due to NaT/NaN in critical fields after parsing. Status: {payments_log_df_original_state.loc[index, original_status_col_name]}")
                if not str(payments_log_df_original_state.loc[index, original_status_col_name]).lower().startswith("error"):
                    payments_log_df_original_state.loc[index, original_status_col_name] = "Error - Invalid Parsed Data"
                    payments_log_df_original_state.loc[index, original_timestamp_col_name] = datetime.now()
                rows_with_initial_errors = True


    if not valid_for_processing_indices:
        logger.info("No valid pending payments found to process after initial validation.")
        if rows_with_initial_errors: # If errors were marked, write them back
            logger.info("Writing back payments log with parsing error statuses (no payments processed).")
            if not gutils.update_worksheet_from_df(gs_client, config.PAYMENTS_LOG_SHEET_ID, "Sheet1", payments_log_df_original_state):
                logger.error("CRITICAL: Failed to update Payments Log sheet with initial parsing error statuses.")
            else:
                logger.info("Payments Log sheet updated with parsing error statuses.")
        return
        
    pending_payments_to_process_df = payments_df_for_validation.loc[valid_for_processing_indices].sort_values(by=PAYMENT_DATE_COL_LOG, ascending=True).copy()
    logger.info(f"Found {len(pending_payments_to_process_df)} payments validated for processing attempt.")

    # --- 2. Process Each Valid Pending Payment ---
    for original_log_index, payment_to_process_row in pending_payments_to_process_df.iterrows():
        loan_id = payment_to_process_row[LOAN_ID_COL_LOG]
        actual_payment_date_dt = payment_to_process_row[PAYMENT_DATE_COL_LOG] # This should now always be a valid datetime
        actual_payment_amount_from_log = payment_to_process_row[PAYMENT_AMOUNT_COL_LOG]

        # The safeguard check for NaT date should ideally not be hit anymore due to improved validation above.
        # If it is hit, it means there's a flaw in the validation logic that allowed a NaT date through.
        if pd.isna(actual_payment_date_dt):
            logger.critical(f"INTERNAL LOGIC ERROR: PaymentDate for LoanID '{loan_id}' (log index {original_log_index}) is NaT despite validation. Skipping.")
            payments_log_df_original_state.loc[original_log_index, original_status_col_name] = "Error - Internal NaT Date at Process"
            payments_log_df_original_state.loc[original_log_index, original_timestamp_col_name] = datetime.now()
            continue
        if pd.isna(loan_id) or loan_id == '' or loan_id == "NAN":
             logger.critical(f"INTERNAL LOGIC ERROR: LoanID for payment (log index {original_log_index}) is '{loan_id}' despite validation. Skipping.")
             payments_log_df_original_state.loc[original_log_index, original_status_col_name] = "Error - Internal Invalid LoanID at Process"
             payments_log_df_original_state.loc[original_log_index, original_timestamp_col_name] = datetime.now()
             continue

        actual_payment_date_str = actual_payment_date_dt.strftime("%Y-%m-%d") # Error was here
        logger.info(f"Processing payment from log index {original_log_index}: LoanID={loan_id}, Date={actual_payment_date_str}, Amount={actual_payment_amount_from_log:.2f}")

        amortization_sheet_id = gutils.get_amortization_sheet_id(loan_id)
        if not amortization_sheet_id:
            logger.error(f"Amort. Sheet ID for LoanID '{loan_id}' not found. Log index {original_log_index}.")
            payments_log_df_original_state.loc[original_log_index, original_status_col_name] = "Error - No Amort. Sheet ID"
            payments_log_df_original_state.loc[original_log_index, original_timestamp_col_name] = datetime.now()
            continue

        try:
            # --- Start of Amortization Processing Block (Copied from previous, ensure local vars are defined) ---
            loan_terms_df_raw = gutils.get_sheet_as_df(gs_client, amortization_sheet_id, "LoanTerms")
            schedule_df_raw = gutils.get_sheet_as_df(gs_client, amortization_sheet_id, "Schedule")

            if loan_terms_df_raw is None or schedule_df_raw is None or loan_terms_df_raw.empty or schedule_df_raw.empty:
                logger.error(f"Could not read or empty LoanTerms/Schedule for {loan_id}. Log index {original_log_index}.")
                payments_log_df_original_state.loc[original_log_index, original_status_col_name] = "Error - Read/Empty Amort. Sheet"
                payments_log_df_original_state.loc[original_log_index, original_timestamp_col_name] = datetime.now()
                continue
            
            loan_terms_df = loan_terms_df_raw.copy()
            loan_terms_df.columns = [str(col).strip().lower() for col in loan_terms_df.columns]
            schedule_df = schedule_df_raw.copy()
            current_original_schedule_headers = schedule_df.columns.tolist() 
            schedule_df.columns = [str(col).strip().lower() for col in schedule_df.columns]

            DUE_DATE_COL_SCHED = 'duedate'; BEGIN_BAL_COL_SCHED = 'beginningbalance'; SCHED_PMT_COL_SCHED = 'scheduledpayment';
            ACTUAL_PMT_DATE_COL_SCHED = 'actualpaymentdate'; ACTUAL_PMT_AMT_COL_SCHED = 'actualpaymentamount';
            INTEREST_PAID_COL_SCHED = 'interestpaid'; PRINCIPAL_PAID_COL_SCHED = 'principalpaid';
            LATE_FEE_COL_SCHED = 'latefee'; CREDIT_APPLIED_COL_SCHED = 'creditapplied';
            ENDING_BAL_COL_SCHED = 'endingbalance'; STATUS_COL_SCHED = 'status'
            
            if 'parameter' not in loan_terms_df.columns or 'value' not in loan_terms_df.columns:
                payments_log_df_original_state.loc[original_log_index, original_status_col_name] = "Error - Bad LoanTerms Format"
                payments_log_df_original_state.loc[original_log_index, original_timestamp_col_name] = datetime.now()
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
                late_fee_percentage = float(loan_terms_s.get("latefeepercentage", str(config.DEFAULT_LATE_FEE_PERCENTAGE)))
                grace_period_days = int(loan_terms_s.get("graceperioddays", str(config.DEFAULT_GRACE_PERIOD_DAYS)))
            except (ValueError, TypeError) as ve:
                logger.error(f"Invalid LoanTerms value for {loan_id}: {ve}. Term 'annualinterestrate' was '{annual_interest_rate_str}'. Log index {original_log_index}.")
                payments_log_df_original_state.loc[original_log_index, original_status_col_name] = "Error - Invalid LoanTerms Value"
                payments_log_df_original_state.loc[original_log_index, original_timestamp_col_name] = datetime.now()
                continue
            
            target_row_idx = -1
            for i, sr_iter in schedule_df.iterrows():
                cs = str(sr_iter.get(STATUS_COL_SCHED, "Due")).strip().lower()
                apds = sr_iter.get(ACTUAL_PMT_DATE_COL_SCHED)
                if pd.isna(apds) or cs in ["due", "partially paid", ""]: target_row_idx = i; break
            
            if target_row_idx == -1:
                payments_log_df_original_state.loc[original_log_index, original_status_col_name] = "Error - No Due Payment Slot"
                payments_log_df_original_state.loc[original_log_index, original_timestamp_col_name] = datetime.now()
                continue

            due_date_dt_sched = schedule_df.loc[target_row_idx, DUE_DATE_COL_SCHED]
            if pd.isna(due_date_dt_sched):
                payments_log_df_original_state.loc[original_log_index, original_status_col_name] = "Error - Invalid Sched. DueDate"
                payments_log_df_original_state.loc[original_log_index, original_timestamp_col_name] = datetime.now()
                continue
            due_date_str_sched = due_date_dt_sched.strftime("%Y-%m-%d")
            
            beginning_balance_for_calc = schedule_df.loc[target_row_idx, BEGIN_BAL_COL_SCHED]
            if pd.isna(beginning_balance_for_calc):
                payments_log_df_original_state.loc[original_log_index, original_status_col_name] = "Error - Invalid Sched. BeginBal"
                payments_log_df_original_state.loc[original_log_index, original_timestamp_col_name] = datetime.now()
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
            schedule_df_to_write.columns = current_original_schedule_headers
            # --- End of Amortization Processing Block (Illustrative) ---

            if gutils.update_worksheet_from_df(gs_client, amortization_sheet_id, "Schedule", schedule_df_to_write):
                payments_log_df_original_state.loc[original_log_index, original_status_col_name] = "Processed"
                payments_log_df_original_state.loc[original_log_index, original_timestamp_col_name] = datetime.now()
                logger.info(f"Successfully processed payment for {loan_id} (log index {original_log_index}).")
            else:
                payments_log_df_original_state.loc[original_log_index, original_status_col_name] = "Error - Amort. Save Fail"
                payments_log_df_original_state.loc[original_log_index, original_timestamp_col_name] = datetime.now()

        except Exception as e: # Catch-all for this specific payment's processing
            logger.error(f"UNHANDLED EXCEPTION for LoanID {loan_id} (log index {original_log_index}): {e}", exc_info=True)
            payments_log_df_original_state.loc[original_log_index, original_status_col_name] = "Error - Unhandled Exception"
            payments_log_df_original_state.loc[original_log_index, original_timestamp_col_name] = datetime.now()
        
    # --- 4. Update Payments Log Sheet ---
    # At this point, payments_log_df_original_state contains the original key data,
    # and updated status/timestamp for all rows attempted (either success or specific error).
    if not gutils.update_worksheet_from_df(gs_client, config.PAYMENTS_LOG_SHEET_ID, "Sheet1", payments_log_df_original_state):
        logger.error("CRITICAL: Failed to update the Payments Log sheet with final processing statuses.")
    else:
        logger.info("Payments Log sheet updated with all final statuses.")

    logger.info("Payment processing run finished.")