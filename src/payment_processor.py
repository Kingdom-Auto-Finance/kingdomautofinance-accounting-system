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
        logger.error(f"CRITICAL: Failed to initialize Google Sheets client: {e}. Aborting.")
        return

    # --- 1. Read Payments Log ---
    # df_log_sheet_state: This DataFrame will hold the state of the payments log.
    # We will ONLY modify its 'ProcessedStatus' and 'ProcessedTimestamp' columns.
    # All other columns (LoanID, PaymentDate, PaymentAmount) will remain untouched from their original read state.
    df_log_sheet_state = gutils.get_sheet_as_df(gs_client, config.PAYMENTS_LOG_SHEET_ID, "Sheet1")
    
    if df_log_sheet_state is None or df_log_sheet_state.empty:
        logger.info("Payments log is empty or could not be read. No payments to process.")
        return

    original_log_headers = df_log_sheet_state.columns.tolist()

    # Standardized lowercase column names for internal processing logic
    LOAN_ID_COL_LOWER = 'loanid'
    PAYMENT_DATE_COL_LOWER = 'paymentdate'
    PAYMENT_AMOUNT_COL_LOWER = 'paymentamount'
    PROCESSED_STATUS_COL_LOWER = 'processedstatus'
    PROCESSED_TIMESTAMP_COL_LOWER = 'processedtimestamp'

    # Map original headers to their lowercase versions for reliable access
    header_map = {str(h).strip().lower(): h for h in original_log_headers}

    # Get the actual (original casing) column names for status and timestamp
    # If these columns don't exist, we'll add them to df_log_sheet_state before writing back.
    status_col_original_casing = header_map.get(PROCESSED_STATUS_COL_LOWER)
    timestamp_col_original_casing = header_map.get(PROCESSED_TIMESTAMP_COL_LOWER)

    if not status_col_original_casing:
        status_col_original_casing = PROCESSED_STATUS_COL_LOWER # Default to lowercase if not found
        df_log_sheet_state[status_col_original_casing] = '' # Add the column
        logger.info(f"Added '{status_col_original_casing}' column to Payments Log DataFrame as it was missing.")
    if not timestamp_col_original_casing:
        timestamp_col_original_casing = PROCESSED_TIMESTAMP_COL_LOWER
        df_log_sheet_state[timestamp_col_original_casing] = pd.NaT # Add as datetime compatible
        logger.info(f"Added '{timestamp_col_original_casing}' column to Payments Log DataFrame as it was missing.")


    # --- 2. Identify and Validate Pending Payments ---
    payments_to_attempt_processing = [] # List of (index, validated_data_dict)

    for index, raw_row_series in df_log_sheet_state.iterrows():
        # Check current status using the original cased column name
        current_status_val = str(raw_row_series.get(status_col_original_casing, '')).strip().lower()
        if current_status_val.startswith('processed') or current_status_val.startswith('error'):
            continue # Skip if already handled in a previous run

        has_critical_error = False
        validated_data = {}

        # LoanID: Read raw, strip, uppercase. Handle "NAN" string as error.
        raw_loan_id = str(raw_row_series.get(header_map.get(LOAN_ID_COL_LOWER, LOAN_ID_COL_LOWER), '')).strip()
        if not raw_loan_id or raw_loan_id.upper() == "NAN":
            logger.warning(f"Log index {index}: LoanID is missing or 'NAN' ('{raw_loan_id}'). Marking as error.")
            df_log_sheet_state.loc[index, status_col_original_casing] = "Error - Invalid/Missing LoanID in Log"
            has_critical_error = True
        else:
            validated_data[LOAN_ID_COL_LOWER] = raw_loan_id.upper()

        # PaymentDate: Read raw, parse strictly to YYYY-MM-DD.
        raw_payment_date = str(raw_row_series.get(header_map.get(PAYMENT_DATE_COL_LOWER, PAYMENT_DATE_COL_LOWER), '')).strip()
        if not has_critical_error:
            parsed_date = pd.NaT
            if not raw_payment_date:
                logger.warning(f"Log index {index}, LoanID '{validated_data.get(LOAN_ID_COL_LOWER)}': PaymentDate is empty. Marking as error.")
                df_log_sheet_state.loc[index, status_col_original_casing] = "Error - Missing PaymentDate in Log"
                has_critical_error = True
            else:
                try:
                    # Try specific format, then general if that fails
                    parsed_date = pd.to_datetime(raw_payment_date, format='%Y-%m-%d', errors='raise')
                except (ValueError, TypeError):
                    try:
                        parsed_date = pd.to_datetime(raw_payment_date, errors='raise')
                        logger.warning(f"Log index {index}, LoanID '{validated_data.get(LOAN_ID_COL_LOWER)}': PaymentDate '{raw_payment_date}' not YYYY-MM-DD. Parsed generally. Correct source format.")
                    except (ValueError, TypeError):
                        logger.warning(f"Log index {index}, LoanID '{validated_data.get(LOAN_ID_COL_LOWER)}': PaymentDate '{raw_payment_date}' is invalid. Marking as error.")
                        df_log_sheet_state.loc[index, status_col_original_casing] = "Error - Invalid PaymentDate in Log"
                        has_critical_error = True
            validated_data[PAYMENT_DATE_COL_LOWER] = parsed_date


        # PaymentAmount: Read raw, convert to positive float.
        raw_payment_amount = str(raw_row_series.get(header_map.get(PAYMENT_AMOUNT_COL_LOWER, PAYMENT_AMOUNT_COL_LOWER), '')).strip()
        if not has_critical_error:
            parsed_amount = pd.NA
            if not raw_payment_amount:
                logger.warning(f"Log index {index}, LoanID '{validated_data.get(LOAN_ID_COL_LOWER)}': PaymentAmount is empty. Marking as error.")
                df_log_sheet_state.loc[index, status_col_original_casing] = "Error - Missing PaymentAmount in Log"
                has_critical_error = True
            else:
                try:
                    parsed_amount = float(raw_payment_amount)
                    if parsed_amount <= 0:
                        raise ValueError("Payment amount must be positive.")
                except (ValueError, TypeError):
                    logger.warning(f"Log index {index}, LoanID '{validated_data.get(LOAN_ID_COL_LOWER)}': PaymentAmount '{raw_payment_amount}' invalid/not positive. Marking as error.")
                    df_log_sheet_state.loc[index, status_col_original_casing] = "Error - Invalid PaymentAmount in Log"
                    has_critical_error = True
            validated_data[PAYMENT_AMOUNT_COL_LOWER] = parsed_amount
        
        if has_critical_error:
            df_log_sheet_state.loc[index, timestamp_col_original_casing] = datetime.now()
        else:
            # If all critical fields parsed correctly, add to list for processing
            payments_to_attempt_processing.append({'original_index': index, 'data': validated_data})

    if not payments_to_attempt_processing:
        logger.info("No valid payments found to attempt processing after validation.")
        # If any rows were marked with parsing errors on df_log_sheet_state, write them back.
        if (df_log_sheet_state[status_col_original_casing].astype(str).str.lower().str.startswith('error', na=False)).any():
            logger.info("Writing back payments log with parsing error statuses (no payments processed).")
            if not gutils.update_worksheet_from_df(gs_client, config.PAYMENTS_LOG_SHEET_ID, "Sheet1", df_log_sheet_state): # Write original state
                logger.error("CRITICAL: Failed to update Payments Log sheet with initial parsing error statuses.")
            else:
                logger.info("Payments Log sheet updated with parsing error statuses.")
        return
        
    # Sort payments to process by date
    payments_to_attempt_processing.sort(key=lambda p: p['data'][PAYMENT_DATE_COL_LOWER])
    logger.info(f"Found {len(payments_to_attempt_processing)} payments validated for processing attempt.")

    # --- 3. Process Each Validated Payment ---
    for payment_item in payments_to_attempt_processing:
        original_log_index = payment_item['original_index']
        validated_data = payment_item['data']

        loan_id = validated_data[LOAN_ID_COL_LOWER]
        actual_payment_date_dt = validated_data[PAYMENT_DATE_COL_LOWER]
        actual_payment_amount_from_log = validated_data[PAYMENT_AMOUNT_COL_LOWER]

        # Safeguards (should ideally not be hit if validation above is perfect)
        if pd.isna(actual_payment_date_dt):
            logger.critical(f"INTERNAL LOGIC ERROR: PaymentDate for LoanID '{loan_id}' (log index {original_log_index}) is NaT. Skipping.")
            df_log_sheet_state.loc[original_log_index, status_col_original_casing] = "Error - Internal NaT Date at Process"
            df_log_sheet_state.loc[original_log_index, timestamp_col_original_casing] = datetime.now()
            continue
        if pd.isna(loan_id) or loan_id == '' or loan_id == "NAN": # Should be caught by earlier validation
             logger.critical(f"INTERNAL LOGIC ERROR: LoanID for payment (log index {original_log_index}) is '{loan_id}'. Skipping.")
             df_log_sheet_state.loc[original_log_index, status_col_original_casing] = "Error - Internal Invalid LoanID at Process"
             df_log_sheet_state.loc[original_log_index, timestamp_col_original_casing] = datetime.now()
             continue

        actual_payment_date_str = actual_payment_date_dt.strftime("%Y-%m-%d")
        logger.info(f"Processing payment from log index {original_log_index}: LoanID={loan_id}, Date={actual_payment_date_str}, Amount={actual_payment_amount_from_log:.2f}")

        amortization_sheet_id = gutils.get_amortization_sheet_id(loan_id)
        if not amortization_sheet_id:
            logger.error(f"Amort. Sheet ID for LoanID '{loan_id}' not found. Log index {original_log_index}.")
            df_log_sheet_state.loc[original_log_index, status_col_original_casing] = "Error - No Amort. Sheet ID"
            df_log_sheet_state.loc[original_log_index, timestamp_col_original_casing] = datetime.now()
            continue

        try:
            # --- Start of Amortization Processing Block (logic from previous responses) ---
            loan_terms_df_raw = gutils.get_sheet_as_df(gs_client, amortization_sheet_id, "LoanTerms")
            schedule_df_raw = gutils.get_sheet_as_df(gs_client, amortization_sheet_id, "Schedule")

            if loan_terms_df_raw is None or schedule_df_raw is None or loan_terms_df_raw.empty or schedule_df_raw.empty:
                logger.error(f"Could not read or empty LoanTerms/Schedule for {loan_id}. Log index {original_log_index}.")
                df_log_sheet_state.loc[original_log_index, status_col_original_casing] = "Error - Read/Empty Amort. Sheet"
                df_log_sheet_state.loc[original_log_index, timestamp_col_original_casing] = datetime.now()
                continue
            
            loan_terms_df = loan_terms_df_raw.copy()
            loan_terms_df.columns = [str(col).strip().lower() for col in loan_terms_df.columns] # Lowercase for processing
            
            schedule_df = schedule_df_raw.copy()
            current_original_schedule_headers = schedule_df.columns.tolist() # Store for writing back
            schedule_df.columns = [str(col).strip().lower() for col in schedule_df.columns] # Lowercase for processing

            # Define expected lowercase column names for Amortization Schedule
            DUE_DATE_COL_SCHED = 'duedate'; BEGIN_BAL_COL_SCHED = 'beginningbalance'; SCHED_PMT_COL_SCHED = 'scheduledpayment';
            ACTUAL_PMT_DATE_COL_SCHED = 'actualpaymentdate'; ACTUAL_PMT_AMT_COL_SCHED = 'actualpaymentamount';
            INTEREST_PAID_COL_SCHED = 'interestpaid'; PRINCIPAL_PAID_COL_SCHED = 'principalpaid';
            LATE_FEE_COL_SCHED = 'latefee'; CREDIT_APPLIED_COL_SCHED = 'creditapplied';
            ENDING_BAL_COL_SCHED = 'endingbalance'; STATUS_COL_SCHED = 'status';
            
            if 'parameter' not in loan_terms_df.columns or 'value' not in loan_terms_df.columns:
                logger.error(f"LoanTerms for {loan_id} missing 'parameter' or 'value' columns. Log index {original_log_index}.")
                df_log_sheet_state.loc[original_log_index, status_col_original_casing] = "Error - Bad LoanTerms Format"
                df_log_sheet_state.loc[original_log_index, timestamp_col_original_casing] = datetime.now()
                continue
            loan_terms_s = loan_terms_df.set_index('parameter')['value'].astype(str).str.strip() # Values read as strings initially

            # Explicit type conversions for schedule_df (ensure columns exist before accessing)
            # Dates expect YYYY-MM-DD string from sheet for parsing
            schedule_df[DUE_DATE_COL_SCHED] = pd.to_datetime(schedule_df.get(DUE_DATE_COL_SCHED), format='%Y-%m-%d', errors='coerce')
            schedule_df[ACTUAL_PMT_DATE_COL_SCHED] = pd.to_datetime(schedule_df.get(ACTUAL_PMT_DATE_COL_SCHED), format='%Y-%m-%d', errors='coerce')
            
            numeric_cols_schedule = [BEGIN_BAL_COL_SCHED, SCHED_PMT_COL_SCHED, ACTUAL_PMT_AMT_COL_SCHED, 
                                     INTEREST_PAID_COL_SCHED, PRINCIPAL_PAID_COL_SCHED, LATE_FEE_COL_SCHED, 
                                     CREDIT_APPLIED_COL_SCHED, ENDING_BAL_COL_SCHED]
            for col in numeric_cols_schedule:
                schedule_df[col] = pd.to_numeric(schedule_df.get(col), errors='coerce') # Missing values become NaN
            
            if STATUS_COL_SCHED not in schedule_df.columns: schedule_df[STATUS_COL_SCHED] = "Due"


            # Fetch and validate loan terms (interest rate specifically)
            try:
                # Get values from series, then convert. Handle missing keys gracefully.
                annual_interest_rate_str = loan_terms_s.get("annualinterestrate", "0.0") # Ensure key matches sheet
                annual_interest_rate = float(annual_interest_rate_str)
                if annual_interest_rate < 0: raise ValueError("Annual interest rate cannot be negative.")

                late_fee_percentage_str = loan_terms_s.get("latefeepercentage", str(config.DEFAULT_LATE_FEE_PERCENTAGE))
                late_fee_percentage = float(late_fee_percentage_str)

                grace_period_days_str = loan_terms_s.get("graceperioddays", str(config.DEFAULT_GRACE_PERIOD_DAYS))
                grace_period_days = int(grace_period_days_str)

            except (ValueError, TypeError, KeyError) as ve: # Added KeyError
                logger.error(f"Invalid or missing required value in LoanTerms for {loan_id}: {ve}. Log index {original_log_index}.")
                df_log_sheet_state.loc[original_log_index, status_col_original_casing] = "Error - Invalid LoanTerms Value"
                df_log_sheet_state.loc[original_log_index, timestamp_col_original_casing] = datetime.now()
                continue
            
            # Find target row logic
            target_row_idx = -1
            for i, sr_iter in schedule_df.iterrows():
                cs = str(sr_iter.get(STATUS_COL_SCHED, "Due")).strip().lower()
                apds = sr_iter.get(ACTUAL_PMT_DATE_COL_SCHED) # This is already a datetime or NaT
                if pd.isna(apds) or cs in ["due", "partially paid", ""]:
                    target_row_idx = i
                    break
            
            if target_row_idx == -1: # No due slot
                df_log_sheet_state.loc[original_log_index, status_col_original_casing] = "Error - No Due Payment Slot"
                df_log_sheet_state.loc[original_log_index, timestamp_col_original_casing] = datetime.now()
                continue

            # Extract data from schedule's target row, with validation
            due_date_dt_sched = schedule_df.loc[target_row_idx, DUE_DATE_COL_SCHED] # Already datetime or NaT
            if pd.isna(due_date_dt_sched):
                df_log_sheet_state.loc[original_log_index, status_col_original_casing] = "Error - Invalid Sched. DueDate"
                df_log_sheet_state.loc[original_log_index, timestamp_col_original_casing] = datetime.now()
                continue
            due_date_str_sched = due_date_dt_sched.strftime("%Y-%m-%d")
            
            beginning_balance_for_calc = schedule_df.loc[target_row_idx, BEGIN_BAL_COL_SCHED] # Already float or NaN
            if pd.isna(beginning_balance_for_calc):
                df_log_sheet_state.loc[original_log_index, status_col_original_casing] = "Error - Invalid Sched. BeginBal"
                df_log_sheet_state.loc[original_log_index, timestamp_col_original_casing] = datetime.now()
                continue

            scheduled_payment_on_schedule = schedule_df.loc[target_row_idx, SCHED_PMT_COL_SCHED] # Already float or NaN
            if pd.isna(scheduled_payment_on_schedule): scheduled_payment_on_schedule = 0.0

            # Call calculation function
            payment_calcs = calculate_payment_details(
                beginning_balance_for_calc, annual_interest_rate, 30, 
                scheduled_payment_on_schedule, actual_payment_amount_from_log,
                due_date_str_sched, actual_payment_date_str, # actual_payment_date_str from log
                late_fee_percentage, grace_period_days
            )

            # Update the current row in schedule_df
            schedule_df.loc[target_row_idx, ACTUAL_PMT_DATE_COL_SCHED] = actual_payment_date_dt # Use datetime object from log
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
                # Check if next row is already paid using its ActualPaymentDate (which is datetime or NaT)
                is_next_row_paid_off = pd.notna(schedule_df.loc[next_row_idx, ACTUAL_PMT_DATE_COL_SCHED]) and \
                                     str(schedule_df.loc[next_row_idx, STATUS_COL_SCHED]).lower().startswith("paid")
                if not is_next_row_paid_off:
                    schedule_df.loc[next_row_idx, BEGIN_BAL_COL_SCHED] = payment_calcs["EndingBalance"]
            
            # Write schedule_df back using its original headers
            schedule_df_to_write = schedule_df.copy()
            schedule_df_to_write.columns = current_original_schedule_headers
            # --- End of Amortization Processing Block ---

            if gutils.update_worksheet_from_df(gs_client, amortization_sheet_id, "Schedule", schedule_df_to_write):
                df_log_sheet_state.loc[original_log_index, status_col_original_casing] = "Processed"
                df_log_sheet_state.loc[original_log_index, timestamp_col_original_casing] = datetime.now() # Store as datetime
                logger.info(f"Successfully processed payment for {loan_id} (log index {original_log_index}).")
            else: # Failed to save amortization sheet
                df_log_sheet_state.loc[original_log_index, status_col_original_casing] = "Error - Amort. Save Fail"
                df_log_sheet_state.loc[original_log_index, timestamp_col_original_casing] = datetime.now()

        except Exception as e: # Catch-all for this specific payment's processing
            logger.error(f"UNHANDLED EXCEPTION during processing of payment for LoanID {loan_id} (log index {original_log_index}): {e}", exc_info=True)
            df_log_sheet_state.loc[original_log_index, status_col_original_casing] = "Error - Unhandled Exception"
            df_log_sheet_state.loc[original_log_index, timestamp_col_original_casing] = datetime.now()
        
    # --- 4. Update Payments Log Sheet with ALL statuses ---
    # df_log_sheet_state now contains the original data for key fields,
    # and updated status/timestamp for all rows attempted. Its columns are already the original headers.
    if not gutils.update_worksheet_from_df(gs_client, config.PAYMENTS_LOG_SHEET_ID, "Sheet1", df_log_sheet_state):
        logger.error("CRITICAL: Failed to update the Payments Log sheet with final processing statuses.")
    else:
        logger.info("Payments Log sheet updated with all final statuses.")

    logger.info("Payment processing run finished.")