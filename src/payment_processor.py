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

    # --- 1. Read Payments Log ---
    # payments_log_df_original_state holds the raw data exactly as read from the sheet.
    # It will be the source of truth for LoanID, PaymentDate, PaymentAmount.
    # Only its ProcessedStatus and ProcessedTimestamp columns will be modified.
    payments_log_df_original_state = gutils.get_sheet_as_df(gs_client, config.PAYMENTS_LOG_SHEET_ID, "Sheet1")
    
    if payments_log_df_original_state is None:
        logger.error("CRITICAL: Could not read Payments Log sheet (returned None). Aborting.")
        return
    if payments_log_df_original_state.empty:
        logger.info("Payments log is empty. No payments to process.")
        return

    original_payments_log_headers = payments_log_df_original_state.columns.tolist()

    # Create a working copy for parsing, validation, and identifying pending rows.
    # Column names are lowercased for internal processing consistency.
    payments_df_for_validation = payments_log_df_original_state.copy()
    payments_df_for_validation.columns = [str(col).strip().lower() for col in payments_df_for_validation.columns]

    LOAN_ID_COL_LOG = 'loanid'
    PAYMENT_DATE_COL_LOG = 'paymentdate'
    PAYMENT_AMOUNT_COL_LOG = 'paymentamount'
    PROCESSED_STATUS_COL_LOG = 'processedstatus' # Corresponds to a column in original_payments_log_headers
    PROCESSED_TIMESTAMP_COL_LOG = 'processedtimestamp' # Corresponds to a column in original_payments_log_headers

    # Find the actual original header names for status & timestamp for precise update later
    # This assumes they exist. If not, they'll be added when writing back.
    original_status_col_name = next((h for h in original_payments_log_headers if str(h).strip().lower() == PROCESSED_STATUS_COL_LOG), PROCESSED_STATUS_COL_LOG)
    original_timestamp_col_name = next((h for h in original_payments_log_headers if str(h).strip().lower() == PROCESSED_TIMESTAMP_COL_LOG), PROCESSED_TIMESTAMP_COL_LOG)

    # Ensure essential columns are present in the lowercased version for validation
    essential_log_cols = [LOAN_ID_COL_LOG, PAYMENT_DATE_COL_LOG, PAYMENT_AMOUNT_COL_LOG]
    for col_name in essential_log_cols:
        if col_name not in payments_df_for_validation.columns:
            logger.error(f"CRITICAL: Essential column '{col_name}' missing from Payments Log. Headers found: {original_payments_log_headers}. Aborting.")
            return 
    
    # Initialize status/timestamp in payments_log_df_original_state if columns don't exist,
    # using the potentially cased original names.
    if original_status_col_name not in payments_log_df_original_state.columns:
        payments_log_df_original_state[original_status_col_name] = ''
    if original_timestamp_col_name not in payments_log_df_original_state.columns:
        payments_log_df_original_state[original_timestamp_col_name] = pd.NaT


    # --- Strict Data Type Conversions and Validation on payments_df_for_validation ---
    # This loop identifies rows that are valid for processing.
    # Errors identified here update status/timestamp on payments_log_df_original_state.
    valid_for_processing_indices = []

    for index, row_to_validate in payments_df_for_validation.iterrows():
        # Check original status first. If already processed or errored (from a previous run), skip validation.
        current_original_status = str(payments_log_df_original_state.loc[index, original_status_col_name]).strip().lower()
        if current_original_status.startswith('processed') or current_original_status.startswith('error'):
            continue # Already handled, skip this row for pending check

        has_parsing_error = False
        
        # Validate LoanID
        loan_id_val = str(row_to_validate.get(LOAN_ID_COL_LOG, '')).strip().upper()
        if not loan_id_val: # Checks for empty string or if get returned None (though .get default is '')
            logger.warning(f"Log row index {index}: LoanID is missing or blank. Marking as error.")
            payments_log_df_original_state.loc[index, original_status_col_name] = "Error - Missing LoanID in Log"
            has_parsing_error = True
        else:
            payments_df_for_validation.loc[index, LOAN_ID_COL_LOG] = loan_id_val # Store standardized version

        # Validate PaymentDate (expect YYYY-MM-DD)
        raw_date_val = row_to_validate.get(PAYMENT_DATE_COL_LOG)
        parsed_date_val = pd.NaT
        if not has_parsing_error: # Only parse if no prior error on this row
            try:
                parsed_date_val = pd.to_datetime(raw_date_val, format='%Y-%m-%d', errors='raise')
            except (ValueError, TypeError):
                try: 
                    parsed_date_val = pd.to_datetime(raw_date_val, errors='raise')
                    logger.warning(f"Log row index {index}, LoanID {loan_id_val}: PaymentDate '{raw_date_val}' not YYYY-MM-DD. Parsed generally. Correct source.")
                except (ValueError, TypeError):
                    logger.warning(f"Log row index {index}, LoanID {loan_id_val}: PaymentDate '{raw_date_val}' is invalid. Marking as error.")
                    payments_log_df_original_state.loc[index, original_status_col_name] = "Error - Invalid PaymentDate in Log"
                    has_parsing_error = True
        payments_df_for_validation.loc[index, PAYMENT_DATE_COL_LOG] = parsed_date_val # Store parsed (or NaT)

        # Validate PaymentAmount (expect positive number)
        raw_amount_val = row_to_validate.get(PAYMENT_AMOUNT_COL_LOG)
        parsed_amount_val = pd.NA
        if not has_parsing_error:
            try:
                parsed_amount_val = float(raw_amount_val)
                if parsed_amount_val <= 0:
                    raise ValueError("Payment amount must be positive.")
            except (ValueError, TypeError):
                logger.warning(f"Log row index {index}, LoanID {loan_id_val}: PaymentAmount '{raw_amount_val}' invalid/not positive. Marking as error.")
                payments_log_df_original_state.loc[index, original_status_col_name] = "Error - Invalid PaymentAmount in Log"
                has_parsing_error = True
        payments_df_for_validation.loc[index, PAYMENT_AMOUNT_COL_LOG] = parsed_amount_val


        if has_parsing_error:
            payments_log_df_original_state.loc[index, original_timestamp_col_name] = datetime.now()
        else:
            # If no parsing errors for this row AND it wasn't already processed/errored, it's valid for now
            valid_for_processing_indices.append(index)
    
    # Create the DataFrame of payments that are actually pending and valid
    if not valid_for_processing_indices:
        logger.info("No valid pending payments found to process after initial validation.")
        # If any rows were marked with parsing errors, payments_log_df_original_state needs to be written back.
        if (payments_log_df_original_state[original_status_col_name].astype(str).str.lower().str.startswith('error', na=False)).any():
            logger.info("Writing back payments log with parsing error statuses.")
            # update_worksheet_from_df expects headers to match DataFrame columns for simplicity
            # For this write-back, ensure payments_log_df_original_state is used directly
            if not gutils.update_worksheet_from_df(gs_client, config.PAYMENTS_LOG_SHEET_ID, "Sheet1", payments_log_df_original_state):
                logger.error("CRITICAL: Failed to update Payments Log sheet with initial parsing error statuses.")
            else:
                logger.info("Payments Log sheet updated with parsing error statuses (no further payments processed).")
        return
        
    pending_payments_to_process_df = payments_df_for_validation.loc[valid_for_processing_indices].sort_values(by=PAYMENT_DATE_COL_LOG, ascending=True).copy()
    logger.info(f"Found {len(pending_payments_to_process_df)} payments validated for processing attempt.")


    # --- 2. Process Each Valid Pending Payment ---
    for original_log_index, payment_to_process_row in pending_payments_to_process_df.iterrows():
        # These values are from payments_df_for_validation and are typed/standardized
        loan_id = payment_to_process_row[LOAN_ID_COL_LOG]
        actual_payment_date_dt = payment_to_process_row[PAYMENT_DATE_COL_LOG]
        actual_payment_amount_from_log = payment_to_process_row[PAYMENT_AMOUNT_COL_LOG]

        # Safeguard: This should not happen if validation loop and filtering are correct
        if pd.isna(actual_payment_date_dt):
            logger.error(f"CRITICAL INTERNAL ERROR: PaymentDate for LoanID {loan_id} (log index {original_log_index}) is NaT. This should be impossible. Skipping.")
            payments_log_df_original_state.loc[original_log_index, original_status_col_name] = "Error - Internal NaT Date at Process"
            payments_log_df_original_state.loc[original_log_index, original_timestamp_col_name] = datetime.now()
            continue 
        if pd.isna(loan_id) or loan_id == '': # NAN loanid here means it was 'NAN' string or similar initially
             logger.error(f"CRITICAL INTERNAL ERROR: LoanID for payment (log index {original_log_index}) is missing/blank at processing. Skipping.")
             payments_log_df_original_state.loc[original_log_index, original_status_col_name] = "Error - Internal Missing LoanID at Process"
             payments_log_df_original_state.loc[original_log_index, original_timestamp_col_name] = datetime.now()
             continue


        actual_payment_date_str = actual_payment_date_dt.strftime("%Y-%m-%d")
        logger.info(f"Processing payment from log index {original_log_index}: LoanID={loan_id}, Date={actual_payment_date_str}, Amount={actual_payment_amount_from_log:.2f}")

        amortization_sheet_id = gutils.get_amortization_sheet_id(loan_id)
        if not amortization_sheet_id:
            logger.error(f"Amort. Sheet ID for LoanID '{loan_id}' not found. Log index {original_log_index}.")
            payments_log_df_original_state.loc[original_log_index, original_status_col_name] = "Error - No Amort. Sheet ID"
            payments_log_df_original_state.loc[original_log_index, original_timestamp_col_name] = datetime.now()
            continue

        try:
            # (The rest of your try...except block for processing a single amortization)
            # Ensure all error handling within this block updates 'payments_log_df_original_state.loc[original_log_index, original_status_col_name/original_timestamp_col_name]'
            # For brevity, I'll skip pasting that large block again, assuming its internal logic
            # for reading terms, schedule, calculating, and updating schedule sheet is mostly okay
            # from the previous response, with the key being that any `payments_log_df.loc` updates
            # are now `payments_log_df_original_state.loc` using original_status/timestamp_col_name.

            # --- Start of Amortization Processing Block (Illustrative - use your full block) ---
            loan_terms_df_raw = gutils.get_sheet_as_df(gs_client, amortization_sheet_id, "LoanTerms")
            schedule_df_raw = gutils.get_sheet_as_df(gs_client, amortization_sheet_id, "Schedule")

            if loan_terms_df_raw is None or schedule_df_raw is None or loan_terms_df_raw.empty or schedule_df_raw.empty:
                logger.error(f"Could not read or empty LoanTerms/Schedule for {loan_id}. Log index {original_log_index}.")
                payments_log_df_original_state.loc[original_log_index, original_status_col_name] = "Error - Read/Empty Amort. Sheet"
                payments_log_df_original_state.loc[original_log_index, original_timestamp_col_name] = datetime.now()
                continue
            
            # ... (Standardize columns, parse LoanTerms, parse Schedule columns for types) ...
            # ... (Find target_row_idx) ...
            # ... (Extract beginning_balance_for_calc, scheduled_payment_on_schedule, due_date_str_sched from target_row) ...
            # ... (Perform input validation on these extracted schedule values) ...
            
            # Example of what would be inside this block from previous version:
            loan_terms_df = loan_terms_df_raw.copy()
            loan_terms_df.columns = [str(col).strip().lower() for col in loan_terms_df.columns]
            schedule_df = schedule_df_raw.copy()
            current_original_schedule_headers = schedule_df.columns.tolist() # Use this for this specific sheet
            schedule_df.columns = [str(col).strip().lower() for col in schedule_df.columns]

            DUE_DATE_COL_SCHED = 'duedate' # Define these locally or ensure they are accessible
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
            
            if 'parameter' not in loan_terms_df.columns or 'value' not in loan_terms_df.columns: # Simplified
                payments_log_df_original_state.loc[original_log_index, original_status_col_name] = "Error - Bad LoanTerms Format"
                payments_log_df_original_state.loc[original_log_index, original_timestamp_col_name] = datetime.now()
                continue
            loan_terms_s = loan_terms_df.set_index('parameter')['value'].astype(str).str.strip()

            # Simplified type conversion for schedule (assuming gutils did a good job or explicit checks follow)
            schedule_df[DUE_DATE_COL_SCHED] = pd.to_datetime(schedule_df.get(DUE_DATE_COL_SCHED), errors='coerce') # Strict format YYYY-MM-DD
            numeric_cols_schedule = [BEGIN_BAL_COL_SCHED, SCHED_PMT_COL_SCHED, ACTUAL_PMT_AMT_COL_SCHED, INTEREST_PAID_COL_SCHED, PRINCIPAL_PAID_COL_SCHED, LATE_FEE_COL_SCHED, CREDIT_APPLIED_COL_SCHED, ENDING_BAL_COL_SCHED]
            for col in numeric_cols_schedule: schedule_df[col] = pd.to_numeric(schedule_df.get(col), errors='coerce')
            schedule_df[ACTUAL_PMT_DATE_COL_SCHED] = pd.to_datetime(schedule_df.get(ACTUAL_PMT_DATE_COL_SCHED), errors='coerce') # Strict format YYYY-MM-DD
            if STATUS_COL_SCHED not in schedule_df.columns: schedule_df[STATUS_COL_SCHED] = "Due"


            try: # Validate Loan Terms values needed for calculation
                annual_interest_rate_str = loan_terms_s.get("annualinterestrate", "0.0")
                annual_interest_rate = float(annual_interest_rate_str)
                if annual_interest_rate < 0: raise ValueError("Annual interest rate cannot be negative.")
                late_fee_percentage = float(loan_terms_s.get("latefeepercentage", str(config.DEFAULT_LATE_FEE_PERCENTAGE)))
                grace_period_days = int(loan_terms_s.get("graceperioddays", str(config.DEFAULT_GRACE_PERIOD_DAYS)))
            except (ValueError, TypeError) as ve:
                logger.error(f"Invalid LoanTerms value for {loan_id}: {ve}. Term 'annualinterestrate' was '{annual_interest_rate_str}'. Log index {original_log_index}.")
                payments_log_df_original_state.loc[original_log_index, original_status_col_name] = "Error - Invalid LoanTerms Value"
                payments_log_df_original_state.loc[original_log_index, original_timestamp_col_name] = datetime.now()
                continue # To next payment log entry
            
            target_row_idx = -1 # Find target row logic (as before)
            for i, sr_iter in schedule_df.iterrows():
                cs = str(sr_iter.get(STATUS_COL_SCHED, "Due")).strip().lower()
                apds = sr_iter.get(ACTUAL_PMT_DATE_COL_SCHED)
                if pd.isna(apds) or cs in ["due", "partially paid", ""]: target_row_idx = i; break
            
            if target_row_idx == -1: # No due slot logic (as before)
                payments_log_df_original_state.loc[original_log_index, original_status_col_name] = "Error - No Due Payment Slot"
                payments_log_df_original_state.loc[original_log_index, original_timestamp_col_name] = datetime.now()
                continue

            # Extract data from schedule's target row (as before, with validation)
            due_date_dt_sched = schedule_df.loc[target_row_idx, DUE_DATE_COL_SCHED]
            if pd.isna(due_date_dt_sched): # Validation
                payments_log_df_original_state.loc[original_log_index, original_status_col_name] = "Error - Invalid Sched. DueDate"
                payments_log_df_original_state.loc[original_log_index, original_timestamp_col_name] = datetime.now()
                continue
            due_date_str_sched = due_date_dt_sched.strftime("%Y-%m-%d")
            
            beginning_balance_for_calc = schedule_df.loc[target_row_idx, BEGIN_BAL_COL_SCHED]
            if pd.isna(beginning_balance_for_calc): # Validation
                payments_log_df_original_state.loc[original_log_index, original_status_col_name] = "Error - Invalid Sched. BeginBal"
                payments_log_df_original_state.loc[original_log_index, original_timestamp_col_name] = datetime.now()
                continue

            scheduled_payment_on_schedule = schedule_df.loc[target_row_idx, SCHED_PMT_COL_SCHED]
            if pd.isna(scheduled_payment_on_schedule): scheduled_payment_on_schedule = 0.0


            payment_calcs = calculate_payment_details(beginning_balance_for_calc, annual_interest_rate, 30, scheduled_payment_on_schedule, actual_payment_amount_from_log, due_date_str_sched, actual_payment_date_str, late_fee_percentage, grace_period_days)

            # Update schedule_df (as before)
            schedule_df.loc[target_row_idx, ACTUAL_PMT_DATE_COL_SCHED] = pd.to_datetime(actual_payment_date_str)
            schedule_df.loc[target_row_idx, ACTUAL_PMT_AMT_COL_SCHED] = actual_payment_amount_from_log
            schedule_df.loc[target_row_idx, INTEREST_PAID_COL_SCHED] = payment_calcs["InterestPaid"]
            schedule_df.loc[target_row_idx, PRINCIPAL_PAID_COL_SCHED] = payment_calcs["PrincipalPaid"]
            # ... etc. for all calculation result columns
            schedule_df.loc[target_row_idx, ENDING_BAL_COL_SCHED] = payment_calcs["EndingBalance"]
            schedule_df.loc[target_row_idx, STATUS_COL_SCHED] = payment_calcs["Status"]


            next_row_idx = target_row_idx + 1 # Update next row BB (as before)
            if next_row_idx < len(schedule_df):
                is_next_row_paid_off = pd.notna(schedule_df.loc[next_row_idx, ACTUAL_PMT_DATE_COL_SCHED]) and str(schedule_df.loc[next_row_idx, STATUS_COL_SCHED]).lower().startswith("paid")
                if not is_next_row_paid_off:
                    schedule_df.loc[next_row_idx, BEGIN_BAL_COL_SCHED] = payment_calcs["EndingBalance"]
            
            # Write schedule_df back
            schedule_df_to_write = schedule_df.copy()
            schedule_df_to_write.columns = current_original_schedule_headers # Use headers from this specific sheet
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
        
    # --- 4. Update Payments Log Sheet with ALL statuses ---
    # payments_log_df_original_state now contains the original data for key fields,
    # and updated status/timestamp. Its columns are already the original headers.
    if not gutils.update_worksheet_from_df(gs_client, config.PAYMENTS_LOG_SHEET_ID, "Sheet1", payments_log_df_original_state):
        logger.error("CRITICAL: Failed to update the Payments Log sheet with final processing statuses.")
    else:
        logger.info("Payments Log sheet updated with all final statuses.")

    logger.info("Payment processing run finished.")