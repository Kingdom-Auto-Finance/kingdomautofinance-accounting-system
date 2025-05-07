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

    # --- 1. Read Payments Log (DataFrame named 'payments_log_df_original_state') ---
    # This DataFrame represents the exact state of the Google Sheet when read.
    # We will only modify 'processedstatus' and 'processedtimestamp' on this for error cases,
    # or mark as 'Processed' if everything for a row succeeds.
    payments_log_df_original_state = gutils.get_sheet_as_df(gs_client, config.PAYMENTS_LOG_SHEET_ID, "Sheet1")
    
    if payments_log_df_original_state is None:
        logger.error("CRITICAL: Could not read Payments Log sheet (returned None). Aborting.")
        return
    if payments_log_df_original_state.empty:
        logger.info("Payments log is empty. No payments to process.")
        return

    # Store original headers to write back with correct casing.
    # It's crucial that the order of columns in the DataFrame matches the sheet when writing back.
    # gutils.update_worksheet_from_df now uses df.columns, so we prepare the final DF with original headers.
    original_payments_log_headers = payments_log_df_original_state.columns.tolist()

    # Create a working copy for processing (standardize column names here)
    payments_df_processing = payments_log_df_original_state.copy()
    payments_df_processing.columns = [str(col).strip().lower() for col in payments_df_processing.columns]

    # Define expected lowercase column names for clarity and robust checking
    LOAN_ID_COL_LOG = 'loanid'
    PAYMENT_DATE_COL_LOG = 'paymentdate'
    PAYMENT_AMOUNT_COL_LOG = 'paymentamount'
    PROCESSED_STATUS_COL_LOG = 'processedstatus'
    PROCESSED_TIMESTAMP_COL_LOG = 'processedtimestamp'

    essential_log_cols = [LOAN_ID_COL_LOG, PAYMENT_DATE_COL_LOG, PAYMENT_AMOUNT_COL_LOG]
    for col_name in essential_log_cols:
        if col_name not in payments_df_processing.columns:
            logger.error(f"CRITICAL: Essential column '{col_name}' (expected lowercase) missing from Payments Log sheet. Headers found: {original_payments_log_headers}. Aborting.")
            # Update the original state DataFrame with a general error if possible
            # This is tricky as we don't know which row this applies to yet.
            # Best to ensure sheets have correct columns.
            return 
    
    # Ensure status/timestamp columns exist in processing DataFrame for consistent logic
    if PROCESSED_STATUS_COL_LOG not in payments_df_processing.columns:
        payments_df_processing[PROCESSED_STATUS_COL_LOG] = ''
    if PROCESSED_TIMESTAMP_COL_LOG not in payments_df_processing.columns:
        # If adding, ensure it's compatible with later strftime, or handle NaT
        payments_df_processing[PROCESSED_TIMESTAMP_COL_LOG] = pd.NaT # Use NaT for datetime column

    # --- Strict Data Type Conversions and Validation for Payments Log Data ---
    error_in_log_parsing = False
    for index, row in payments_df_processing.iterrows():
        # LoanID
        loan_id_val = str(row.get(LOAN_ID_COL_LOG, '')).strip().upper()
        if not loan_id_val:
            logger.warning(f"Log row {index}: LoanID is missing or blank. Marking as error.")
            payments_log_df_original_state.loc[index, PROCESSED_STATUS_COL_LOG] = "Error - Missing LoanID in Log"
            payments_log_df_original_state.loc[index, PROCESSED_TIMESTAMP_COL_LOG] = datetime.now()
            error_in_log_parsing = True
            continue # Skip to next row in log for parsing
        payments_df_processing.loc[index, LOAN_ID_COL_LOG] = loan_id_val

        # PaymentDate (expect YYYY-MM-DD)
        try:
            # Try to parse with specific format, then general if that fails
            date_val = pd.to_datetime(row.get(PAYMENT_DATE_COL_LOG), format='%Y-%m-%d', errors='raise')
            payments_df_processing.loc[index, PAYMENT_DATE_COL_LOG] = date_val
        except (ValueError, TypeError):
            try: # General parsing as a fallback
                date_val = pd.to_datetime(row.get(PAYMENT_DATE_COL_LOG), errors='raise')
                payments_df_processing.loc[index, PAYMENT_DATE_COL_LOG] = date_val
                logger.warning(f"Log row {index}, LoanID {loan_id_val}: PaymentDate '{row.get(PAYMENT_DATE_COL_LOG)}' not in YYYY-MM-DD. Parsed generally. Please correct source format.")
            except (ValueError, TypeError):
                logger.warning(f"Log row {index}, LoanID {loan_id_val}: PaymentDate '{row.get(PAYMENT_DATE_COL_LOG)}' is invalid. Marking as error.")
                payments_log_df_original_state.loc[index, PROCESSED_STATUS_COL_LOG] = "Error - Invalid PaymentDate in Log"
                payments_log_df_original_state.loc[index, PROCESSED_TIMESTAMP_COL_LOG] = datetime.now()
                error_in_log_parsing = True
                continue
        
        # PaymentAmount (expect positive number)
        try:
            amount_val = float(row.get(PAYMENT_AMOUNT_COL_LOG))
            if amount_val <= 0:
                raise ValueError("Payment amount must be positive.")
            payments_df_processing.loc[index, PAYMENT_AMOUNT_COL_LOG] = amount_val
        except (ValueError, TypeError):
            logger.warning(f"Log row {index}, LoanID {loan_id_val}: PaymentAmount '{row.get(PAYMENT_AMOUNT_COL_LOG)}' is invalid or not positive. Marking as error.")
            payments_log_df_original_state.loc[index, PROCESSED_STATUS_COL_LOG] = "Error - Invalid PaymentAmount in Log"
            payments_log_df_original_state.loc[index, PROCESSED_TIMESTAMP_COL_LOG] = datetime.now()
            error_in_log_parsing = True
            continue

    if error_in_log_parsing:
        logger.warning("Errors found while parsing the payments log. Some rows will be marked as error and not processed.")
        # At this point, payments_log_df_original_state has error statuses for unparseable rows.
        # We will write it back at the end.


    # Filter for pending payments (those not yet marked with an error or 'Processed')
    payments_df_processing[PROCESSED_STATUS_COL_LOG] = payments_df_processing[PROCESSED_STATUS_COL_LOG].fillna('').astype(str).str.strip()
    # Consider a row pending if its corresponding entry in payments_log_df_original_state is not yet errored or processed.
    pending_mask = ~payments_log_df_original_state[PROCESSED_STATUS_COL_LOG].fillna('').str.lower().str.startswith('error') & \
                   ~payments_log_df_original_state[PROCESSED_STATUS_COL_LOG].fillna('').str.lower().str.startswith('processed')
    
    pending_payments_to_process_df = payments_df_processing[pending_mask].sort_values(by=PAYMENT_DATE_COL_LOG, ascending=True).copy()


    if pending_payments_to_process_df.empty:
        logger.info("No valid pending payments found to process after initial validation.")
        # Still need to write back payments_log_df_original_state if parsing errors occurred.
        if error_in_log_parsing:
             # Construct DataFrame for writing with original headers
            payments_log_to_write = pd.DataFrame(columns=original_payments_log_headers)
            for col_original in original_payments_log_headers:
                col_lower = str(col_original).strip().lower()
                if col_lower in payments_log_df_original_state.columns: # Use original state which has only status/ts potentially changed
                    payments_log_to_write[col_original] = payments_log_df_original_state[col_lower]
                else: # Should map to original columns of payments_log_df_original_state
                    payments_log_to_write[col_original] = payments_log_df_original_state[col_original]


            if not gutils.update_worksheet_from_df(gs_client, config.PAYMENTS_LOG_SHEET_ID, "Sheet1", payments_log_to_write):
                logger.error("CRITICAL: Failed to update Payments Log sheet with initial parsing error statuses.")
            else:
                logger.info("Payments Log sheet updated with initial parsing error statuses.")
        return
        
    logger.info(f"Found {len(pending_payments_to_process_df)} valid payments to process.")

    # --- 2. Process Each Valid Pending Payment ---
    # All modifications due to processing errors will now be made on payments_log_df_original_state
    for original_log_index, payment_row_data_to_process in pending_payments_to_process_df.iterrows():
        loan_id = payment_row_data_to_process[LOAN_ID_COL_LOG] # Already validated and typed
        actual_payment_date_dt = payment_row_data_to_process[PAYMENT_DATE_COL_LOG] # Already datetime
        actual_payment_amount_from_log = payment_row_data_to_process[PAYMENT_AMOUNT_COL_LOG] # Already float

        actual_payment_date_str = actual_payment_date_dt.strftime("%Y-%m-%d")
        logger.info(f"Processing payment from log index {original_log_index}: LoanID={loan_id}, Date={actual_payment_date_str}, Amount={actual_payment_amount_from_log:.2f}")

        amortization_sheet_id = gutils.get_amortization_sheet_id(loan_id)
        if not amortization_sheet_id:
            logger.error(f"Amortization Google Sheet ID for LoanID '{loan_id}' not found. Log index {original_log_index}.")
            payments_log_df_original_state.loc[original_log_index, PROCESSED_STATUS_COL_LOG] = "Error - No Amort. Sheet ID"
            payments_log_df_original_state.loc[original_log_index, PROCESSED_TIMESTAMP_COL_LOG] = datetime.now()
            continue # Move to next payment in the log

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

            # Define expected lowercase column names for Amortization Schedule
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
            
            # Validate LoanTerms format
            if 'parameter' not in loan_terms_df.columns or 'value' not in loan_terms_df.columns:
                logger.error(f"LoanTerms sheet for {loan_id} is missing 'parameter' or 'value' columns. Log index {original_log_index}.")
                payments_log_df_original_state.loc[original_log_index, PROCESSED_STATUS_COL_LOG] = "Error - Bad LoanTerms Format"
                payments_log_df_original_state.loc[original_log_index, PROCESSED_TIMESTAMP_COL_LOG] = datetime.now()
                continue
            loan_terms_s = loan_terms_df.set_index('parameter')['value'].astype(str).str.strip()

            # Strict type conversions for schedule_df
            schedule_df[DUE_DATE_COL_SCHED] = pd.to_datetime(schedule_df.get(DUE_DATE_COL_SCHED), format='%Y-%m-%d', errors='coerce')
            
            numeric_cols_schedule = [BEGIN_BAL_COL_SCHED, SCHED_PMT_COL_SCHED, ACTUAL_PMT_AMT_COL_SCHED,
                                     INTEREST_PAID_COL_SCHED, PRINCIPAL_PAID_COL_SCHED, LATE_FEE_COL_SCHED,
                                     CREDIT_APPLIED_COL_SCHED, ENDING_BAL_COL_SCHED]
            for col in numeric_cols_schedule:
                schedule_df[col] = pd.to_numeric(schedule_df.get(col), errors='coerce') # .fillna(0.0) or handle NaNs explicitly

            schedule_df[ACTUAL_PMT_DATE_COL_SCHED] = pd.to_datetime(schedule_df.get(ACTUAL_PMT_DATE_COL_SCHED), format='%Y-%m-%d', errors='coerce')
            if STATUS_COL_SCHED not in schedule_df.columns: schedule_df[STATUS_COL_SCHED] = "Due"


            # Fetch and validate loan terms (interest rate specifically)
            try:
                annual_interest_rate_str = loan_terms_s.get("annualinterestrate", "0.0") # key must match LoanTerms sheet
                annual_interest_rate = float(annual_interest_rate_str)
                if annual_interest_rate < 0: raise ValueError("Annual interest rate cannot be negative.")

                late_fee_percentage_str = loan_terms_s.get("latefeepercentage", str(config.DEFAULT_LATE_FEE_PERCENTAGE))
                late_fee_percentage = float(late_fee_percentage_str)

                grace_period_days_str = loan_terms_s.get("graceperioddays", str(config.DEFAULT_GRACE_PERIOD_DAYS))
                grace_period_days = int(grace_period_days_str)

            except (ValueError, TypeError) as ve:
                logger.error(f"Invalid or missing numeric value in LoanTerms for {loan_id}: {ve}. Key: 'annualinterestrate' value was '{annual_interest_rate_str}'. Log index {original_log_index}.")
                payments_log_df_original_state.loc[original_log_index, PROCESSED_STATUS_COL_LOG] = "Error - Invalid LoanTerms Value"
                payments_log_df_original_state.loc[original_log_index, PROCESSED_TIMESTAMP_COL_LOG] = datetime.now()
                continue
            
            # Find target row for payment
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

            # Extract data from the identified target row for calculation
            due_date_dt_sched = schedule_df.loc[target_row_idx, DUE_DATE_COL_SCHED]
            if pd.isna(due_date_dt_sched):
                logger.error(f"DueDate is invalid in Amort. Schedule for {loan_id}, row {target_row_idx}. Log index {original_log_index}.")
                payments_log_df_original_state.loc[original_log_index, PROCESSED_STATUS_COL_LOG] = "Error - Invalid Sched. DueDate"
                payments_log_df_original_state.loc[original_log_index, PROCESSED_TIMESTAMP_COL_LOG] = datetime.now()
                continue
            due_date_str_sched = due_date_dt_sched.strftime("%Y-%m-%d")
            
            beginning_balance_for_calc = schedule_df.loc[target_row_idx, BEGIN_BAL_COL_SCHED]
            if pd.isna(beginning_balance_for_calc):
                logger.error(f"BeginningBalance is invalid in Amort. Schedule for {loan_id}, row {target_row_idx}. Log index {original_log_index}.")
                payments_log_df_original_state.loc[original_log_index, PROCESSED_STATUS_COL_LOG] = "Error - Invalid Sched. BeginBal"
                payments_log_df_original_state.loc[original_log_index, PROCESSED_TIMESTAMP_COL_LOG] = datetime.now()
                continue

            scheduled_payment_on_schedule = schedule_df.loc[target_row_idx, SCHED_PMT_COL_SCHED]
            if pd.isna(scheduled_payment_on_schedule): scheduled_payment_on_schedule = 0.0

            # Call calculation function
            payment_calcs = calculate_payment_details(
                beginning_balance_for_calc, annual_interest_rate, 30, 
                scheduled_payment_on_schedule, actual_payment_amount_from_log,
                due_date_str_sched, actual_payment_date_str,
                late_fee_percentage, grace_period_days
            )

            # Update the current row in schedule_df
            schedule_df.loc[target_row_idx, ACTUAL_PMT_DATE_COL_SCHED] = pd.to_datetime(actual_payment_date_str) # Store as datetime
            schedule_df.loc[target_row_idx, ACTUAL_PMT_AMT_COL_SCHED] = actual_payment_amount_from_log
            schedule_df.loc[target_row_idx, INTEREST_PAID_COL_SCHED] = payment_calcs["InterestPaid"]
            schedule_df.loc[target_row_idx, PRINCIPAL_PAID_COL_SCHED] = payment_calcs["PrincipalPaid"]
            schedule_df.loc[target_row_idx, LATE_FEE_COL_SCHED] = payment_calcs["LateFee"]
            schedule_df.loc[target_row_idx, CREDIT_APPLIED_COL_SCHED] = payment_calcs["CreditApplied"]
            schedule_df.loc[target_row_idx, ENDING_BAL_COL_SCHED] = payment_calcs["EndingBalance"]
            schedule_df.loc[target_row_idx, STATUS_COL_SCHED] = payment_calcs["Status"]

            # Update BeginningBalance for the next row if applicable
            next_row_idx = target_row_idx + 1
            if next_row_idx < len(schedule_df):
                is_next_row_paid_off = pd.notna(schedule_df.loc[next_row_idx, ACTUAL_PMT_DATE_COL_SCHED]) and \
                                     str(schedule_df.loc[next_row_idx, STATUS_COL_SCHED]).lower().startswith("paid")
                if not is_next_row_paid_off:
                    schedule_df.loc[next_row_idx, BEGIN_BAL_COL_SCHED] = payment_calcs["EndingBalance"]

            # Write updated schedule back to Google Sheet
            schedule_df_to_write = schedule_df.copy()
            schedule_df_to_write.columns = original_schedule_headers # Restore original headers for writing
            if gutils.update_worksheet_from_df(gs_client, amortization_sheet_id, "Schedule", schedule_df_to_write):
                # Mark as processed in the *original state* DataFrame that will be written back
                payments_log_df_original_state.loc[original_log_index, PROCESSED_STATUS_COL_LOG] = "Processed"
                payments_log_df_original_state.loc[original_log_index, PROCESSED_TIMESTAMP_COL_LOG] = datetime.now() # Store as datetime, gutils will format
                logger.info(f"Successfully processed payment for {loan_id} (log index {original_log_index}).")
            else:
                payments_log_df_original_state.loc[original_log_index, PROCESSED_STATUS_COL_LOG] = "Error - Amort. Save Fail"
                payments_log_df_original_state.loc[original_log_index, PROCESSED_TIMESTAMP_COL_LOG] = datetime.now()

        except Exception as e: # Catch-all for any other error during this payment's processing
            logger.error(f"UNHANDLED EXCEPTION during processing of payment for LoanID {loan_id} (log index {original_log_index}): {e}", exc_info=True)
            payments_log_df_original_state.loc[original_log_index, PROCESSED_STATUS_COL_LOG] = "Error - Unhandled Exception"
            payments_log_df_original_state.loc[original_log_index, PROCESSED_TIMESTAMP_COL_LOG] = datetime.now()
        
    # --- 4. Update Payments Log Sheet with ALL statuses from payments_log_df_original_state ---
    # This DataFrame now contains the original LoanID, PaymentDate, PaymentAmount for ALL rows,
    # and updated ProcessedStatus/Timestamp for rows that were attempted.
    
    # Prepare the final DataFrame for writing using original headers
    final_payments_log_to_write = pd.DataFrame(columns=original_payments_log_headers)
    for original_header in original_payments_log_headers:
        # Map original header to its potential lowercase version used internally if necessary,
        # or directly use original_header if payments_log_df_original_state still uses them.
        # Since payments_log_df_original_state was a direct copy, it has original headers.
        if original_header in payments_log_df_original_state.columns:
            final_payments_log_to_write[original_header] = payments_log_df_original_state[original_header]
        else:
            # This case should ideally not happen if original_payments_log_headers came from payments_log_df_original_state
            logger.warning(f"Original header '{original_header}' not found in payments_log_df_original_state. Filling with empty for log write-back.")
            final_payments_log_to_write[original_header] = [''] * len(payments_log_df_original_state)


    if not gutils.update_worksheet_from_df(gs_client, config.PAYMENTS_LOG_SHEET_ID, "Sheet1", final_payments_log_to_write):
        logger.error("CRITICAL: Failed to update the Payments Log sheet with final processing statuses.")
    else:
        logger.info("Payments Log sheet updated with all final statuses.")

    logger.info("Payment processing run finished.")