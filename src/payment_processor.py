# src/payment_processor.py
import pandas as pd
from datetime import datetime
import logging
from . import config  # Assuming config.py is in the same directory (src) or package structure is correct
from . import gutils  # Assuming gutils.py is in the same directory
from .amortization_calculator import calculate_payment_details # Assuming amortization_calculator.py is in the same directory

logger = logging.getLogger(__name__)

def process_payments():
    logger.info("Starting payment processing using Google Sheets...")
    gs_client = None
    try:
        gs_client = gutils.get_gspread_client()
    except ConnectionError as e:
        logger.error(f"CRITICAL: Failed to initialize Google Sheets client: {e}. Aborting.")
        return
    # Optionally initialize Drive client early
    try:
        gutils.get_drive_service() 
    except ConnectionError as e:
         logger.warning(f"Could not initialize Drive client on startup: {e}.")

    # --- 1. Read Payments Log ---
    # df_log_sheet_state holds the raw data exactly as read from the sheet.
    # We will ONLY modify its 'ProcessedStatus' and 'ProcessedTimestamp' columns.
    df_log_sheet_state = gutils.get_sheet_as_df(gs_client, config.PAYMENTS_LOG_SHEET_ID, "Sheet1")
    
    if df_log_sheet_state is None or df_log_sheet_state.empty:
        logger.info("Payments log is empty or could not be read. No payments to process.")
        return

    original_log_headers = df_log_sheet_state.columns.tolist()
    # Create a mapping from lowercase header to original header for reliable access
    header_map = {str(h).strip().lower(): h for h in original_log_headers}

    # Define standardized lowercase column names expected internally
    LOAN_ID_COL_LOWER = 'loanid'
    PAYMENT_DATE_COL_LOWER = 'paymentdate'
    PAYMENT_AMOUNT_COL_LOWER = 'paymentamount'
    PROCESSED_STATUS_COL_LOWER = 'processedstatus'
    PROCESSED_TIMESTAMP_COL_LOWER = 'processedtimestamp'

    # Find the actual (original casing) column names for status and timestamp in the sheet
    status_col_original_casing = header_map.get(PROCESSED_STATUS_COL_LOWER)
    timestamp_col_original_casing = header_map.get(PROCESSED_TIMESTAMP_COL_LOWER)

    # Add status/timestamp columns to the DataFrame if they don't exist in the sheet
    if not status_col_original_casing:
        status_col_original_casing = PROCESSED_STATUS_COL_LOWER # Use lowercase if adding
        df_log_sheet_state[status_col_original_casing] = '' # Add the column, default empty
        original_log_headers.append(status_col_original_casing) # Add to header list for write-back
        header_map[PROCESSED_STATUS_COL_LOWER] = status_col_original_casing # Update map
        logger.info(f"Added missing '{status_col_original_casing}' column to Payments Log DataFrame.")
    if not timestamp_col_original_casing:
        timestamp_col_original_casing = PROCESSED_TIMESTAMP_COL_LOWER # Use lowercase if adding
        df_log_sheet_state[timestamp_col_original_casing] = pd.NaT # Add as datetime compatible
        original_log_headers.append(timestamp_col_original_casing)
        header_map[PROCESSED_TIMESTAMP_COL_LOWER] = timestamp_col_original_casing
        logger.info(f"Added missing '{timestamp_col_original_casing}' column to Payments Log DataFrame.")

    # --- 2. Identify and Validate Pending Payments ---
    payments_to_attempt_processing = [] # List of {'original_index': index, 'data': validated_data_dict}
    rows_with_initial_errors = False # Flag to check if any errors occurred during validation

    for index, raw_row_series in df_log_sheet_state.iterrows():
        # Check current status using the original cased column name from the sheet state
        current_original_status = str(raw_row_series.get(status_col_original_casing, '')).strip().lower()
        # Skip if already processed or errored in a previous run
        if current_original_status.startswith('processed') or current_original_status.startswith('error'):
            continue 

        has_critical_error = False
        validated_data = {}
        loan_id_val = '' # Initialize for logging

        # --- Validate LoanID ---
        # Use header_map to find the original column name corresponding to lowercase 'loanid'
        loan_id_header_original = header_map.get(LOAN_ID_COL_LOWER)
        if not loan_id_header_original: # Check if 'loanid' (case-insensitive) exists in headers
             logger.warning(f"Log index {index}: Critical column '{LOAN_ID_COL_LOWER}' not found in log headers. Skipping row validation.")
             df_log_sheet_state.loc[index, status_col_original_casing] = "Error - Missing LoanID Column"
             has_critical_error = True
        else:
            try: 
                raw_loan_id = str(raw_row_series.get(loan_id_header_original, '')).strip()
                loan_id_val = raw_loan_id.upper() # Standardize for internal checks
                if not raw_loan_id or loan_id_val == "NAN": 
                    raise ValueError("LoanID is missing or 'NAN'")
                validated_data['loanid_original_case'] = raw_loan_id # Keep original case for filename search
                validated_data[LOAN_ID_COL_LOWER] = loan_id_val # Store standardized uppercase version
            except Exception as e: 
                logger.warning(f"Log index {index}: Error validating LoanID ('{raw_loan_id}'). Error: {e}. Marking as error.")
                df_log_sheet_state.loc[index, status_col_original_casing] = "Error - Invalid/Missing LoanID in Log"
                has_critical_error = True

        # --- Validate PaymentDate ---
        payment_date_header_original = header_map.get(PAYMENT_DATE_COL_LOWER)
        raw_payment_date = ''
        parsed_date = pd.NaT
        if not has_critical_error:
            if not payment_date_header_original:
                logger.warning(f"Log index {index}, LoanID '{loan_id_val}': Critical column '{PAYMENT_DATE_COL_LOWER}' not found. Marking as error.")
                df_log_sheet_state.loc[index, status_col_original_casing] = "Error - Missing PaymentDate Column"
                has_critical_error = True
            else:
                raw_payment_date = str(raw_row_series.get(payment_date_header_original, '')).strip()
                if not raw_payment_date:
                    logger.warning(f"Log index {index}, LoanID '{loan_id_val}': PaymentDate is empty. Marking as error.")
                    df_log_sheet_state.loc[index, status_col_original_casing] = "Error - Missing PaymentDate in Log"
                    has_critical_error = True
                else:
                    try:
                        parsed_date = pd.to_datetime(raw_payment_date, format='%Y-%m-%d', errors='raise')
                    except (ValueError, TypeError):
                        try: 
                            parsed_date = pd.to_datetime(raw_payment_date, errors='raise')
                            logger.warning(f"Log index {index}, LoanID '{loan_id_val}': Date '{raw_payment_date}' not YYYY-MM-DD...")
                        except (ValueError, TypeError):
                            logger.warning(f"Log index {index}, LoanID '{loan_id_val}': Date '{raw_payment_date}' invalid. Marking as error.")
                            df_log_sheet_state.loc[index, status_col_original_casing] = "Error - Invalid PaymentDate in Log"
                            has_critical_error = True
            validated_data[PAYMENT_DATE_COL_LOWER] = parsed_date

        # --- Validate PaymentAmount ---
        payment_amount_header_original = header_map.get(PAYMENT_AMOUNT_COL_LOWER)
        raw_payment_amount = ''
        parsed_amount = pd.NA 
        if not has_critical_error:
            if not payment_amount_header_original:
                logger.warning(f"Log index {index}, LoanID '{loan_id_val}': Critical column '{PAYMENT_AMOUNT_COL_LOWER}' not found. Marking as error.")
                df_log_sheet_state.loc[index, status_col_original_casing] = "Error - Missing PaymentAmount Column"
                has_critical_error = True
            else:
                raw_payment_amount = str(raw_row_series.get(payment_amount_header_original, '')).strip()
                if not raw_payment_amount:
                    logger.warning(f"Log index {index}, LoanID '{loan_id_val}': PaymentAmount is empty. Marking as error.")
                    df_log_sheet_state.loc[index, status_col_original_casing] = "Error - Missing PaymentAmount in Log"
                    has_critical_error = True
                else:
                    try: 
                        parsed_amount = float(raw_payment_amount) 
                        if parsed_amount <= 0:
                            raise ValueError("Payment amount must be positive.") 
                    except (ValueError, TypeError) as e: 
                        logger.warning(f"Log index {index}, LoanID '{loan_id_val}': PaymentAmount '{raw_payment_amount}' invalid/not positive. Error: {e}. Marking as error.")
                        df_log_sheet_state.loc[index, status_col_original_casing] = "Error - Invalid PaymentAmount in Log"
                        has_critical_error = True
                        parsed_amount = pd.NA # Ensure NA on error
            validated_data[PAYMENT_AMOUNT_COL_LOWER] = parsed_amount
        
        # --- Finalize row validation ---
        if has_critical_error:
            # Ensure timestamp is set if an error occurred in this validation pass
            df_log_sheet_state.loc[index, timestamp_col_original_casing] = datetime.now()
            rows_with_initial_errors = True
        else:
             # Add to list for processing only if all critical fields parsed correctly
             if pd.notna(validated_data.get('loanid_original_case')) and \
                validated_data.get('loanid_original_case').upper() != "NAN" and \
                pd.notna(validated_data.get(PAYMENT_DATE_COL_LOWER)) and \
                pd.notna(validated_data.get(PAYMENT_AMOUNT_COL_LOWER)):
                 payments_to_attempt_processing.append({'original_index': index, 'data': validated_data})
             else: 
                  # This block is a safeguard if has_critical_error logic somehow failed
                  # Only update status if it wasn't already set to an error
                  if not str(df_log_sheet_state.loc[index, status_col_original_casing]).lower().startswith("error"):
                      logger.warning(f"Log index {index}, LoanID '{loan_id_val}': Row invalid due to NaT/NaN post-parsing.")
                      df_log_sheet_state.loc[index, status_col_original_casing] = "Error - Invalid Parsed Data"
                      df_log_sheet_state.loc[index, timestamp_col_original_casing] = datetime.now()
                  rows_with_initial_errors = True


    if not payments_to_attempt_processing:
        logger.info("No valid payments found to attempt processing after validation.")
        if rows_with_initial_errors: # Write back if validation marked errors
            logger.info("Writing back payments log with parsing error statuses...")
            if not gutils.update_worksheet_from_df(gs_client, config.PAYMENTS_LOG_SHEET_ID, "Sheet1", df_log_sheet_state): # Use original state df
                logger.error("CRITICAL: Failed to update Payments Log sheet with initial parsing error statuses.")
            else:
                logger.info("Payments Log sheet updated with parsing error statuses.")
        return
        
    # Sort the valid payments by date before processing
    payments_to_attempt_processing.sort(key=lambda p: p['data'][PAYMENT_DATE_COL_LOWER])
    logger.info(f"Found {len(payments_to_attempt_processing)} payments validated for processing attempt.")


    # --- 3. Process Each Validated Payment ---
    for payment_item in payments_to_attempt_processing:
        original_log_index = payment_item['original_index']
        validated_data = payment_item['data']

        loan_id_original_case = validated_data['loanid_original_case'] # Use this for filename search
        loan_id_internal = validated_data[LOAN_ID_COL_LOWER] # Uppercase for internal use/logs
        actual_payment_date_dt = validated_data[PAYMENT_DATE_COL_LOWER] # Already validated datetime
        actual_payment_amount_from_log = validated_data[PAYMENT_AMOUNT_COL_LOWER] # Already validated float

        # Safeguards (these checks indicate a flaw in the validation logic if hit)
        if pd.isna(actual_payment_date_dt): logger.critical(f"INTERNAL LOGIC ERROR: PaymentDate for '{loan_id_internal}' (idx {original_log_index}) is NaT. Skipping."); df_log_sheet_state.loc[original_log_index, status_col_original_casing] = "Error - Internal NaT Date"; df_log_sheet_state.loc[original_log_index, timestamp_col_original_casing] = datetime.now(); continue 
        if not loan_id_original_case or loan_id_original_case.upper() == "NAN": logger.critical(f"INTERNAL LOGIC ERROR: LoanID '{loan_id_original_case}' (idx {original_log_index}) invalid. Skipping."); df_log_sheet_state.loc[original_log_index, status_col_original_casing] = "Error - Internal Invalid LoanID"; df_log_sheet_state.loc[original_log_index, timestamp_col_original_casing] = datetime.now(); continue

        # Format date string now that we know it's valid
        actual_payment_date_str = actual_payment_date_dt.strftime("%Y-%m-%d")
        logger.info(f"Processing payment from log index {original_log_index}: LoanID={loan_id_original_case}, Date={actual_payment_date_str}, Amount={actual_payment_amount_from_log:.2f}")

        # Find Amortization Sheet using Drive search
        amortization_sheet_id = gutils.find_sheet_id_by_loan_id_in_folder(loan_id_original_case)

        if not amortization_sheet_id:
            # Warning/Error already logged by find_sheet_id_by_loan_id_in_folder
            df_log_sheet_state.loc[original_log_index, status_col_original_casing] = "Error - Amort. Sheet Not Found in Drive"
            df_log_sheet_state.loc[original_log_index, timestamp_col_original_casing] = datetime.now()
            continue # Skip to next payment

        # --- Start of Amortization Processing Block ---
        try:
            # Read terms and schedule sheets
            loan_terms_df_raw = gutils.get_sheet_as_df(gs_client, amortization_sheet_id, "LoanTerms")
            schedule_df_raw = gutils.get_sheet_as_df(gs_client, amortization_sheet_id, "Schedule")

            # Validate sheets were read and are not empty
            if loan_terms_df_raw is None or schedule_df_raw is None or loan_terms_df_raw.empty or schedule_df_raw.empty:
                logger.error(f"Read error or empty LoanTerms/Schedule for {loan_id_internal}. Log index {original_log_index}.")
                df_log_sheet_state.loc[original_log_index, status_col_original_casing] = "Error - Read/Empty Amort. Sheet"
                df_log_sheet_state.loc[original_log_index, timestamp_col_original_casing] = datetime.now()
                continue
            
            # Prepare DataFrames for processing (lowercase columns, etc.)
            loan_terms_df = loan_terms_df_raw.copy()
            loan_terms_df.columns = [str(col).strip().lower() for col in loan_terms_df.columns]
            schedule_df = schedule_df_raw.copy()
            current_original_schedule_headers = schedule_df.columns.tolist() 
            schedule_df.columns = [str(col).strip().lower() for col in schedule_df.columns]

            # Define expected internal lowercase column names for schedule
            DUE_DATE_COL_SCHED = 'duedate'; BEGIN_BAL_COL_SCHED = 'beginningbalance'; SCHED_PMT_COL_SCHED = 'scheduledpayment';
            ACTUAL_PMT_DATE_COL_SCHED = 'actualpaymentdate'; ACTUAL_PMT_AMT_COL_SCHED = 'actualpaymentamount';
            INTEREST_PAID_COL_SCHED = 'interestpaid'; PRINCIPAL_PAID_COL_SCHED = 'principalpaid';
            LATE_FEE_COL_SCHED = 'latefee'; CREDIT_APPLIED_COL_SCHED = 'creditapplied';
            ENDING_BAL_COL_SCHED = 'endingbalance'; STATUS_COL_SCHED = 'status';
            
            # Validate LoanTerms format and parse required values
            if 'parameter' not in loan_terms_df.columns or 'value' not in loan_terms_df.columns:
                 logger.error(f"LoanTerms for {loan_id_internal} missing 'parameter' or 'value' columns. Log index {original_log_index}.")
                 df_log_sheet_state.loc[original_log_index, status_col_original_casing] = "Error - Bad LoanTerms Format"; df_log_sheet_state.loc[original_log_index, timestamp_col_original_casing] = datetime.now(); continue
            loan_terms_s = loan_terms_df.set_index('parameter')['value'].astype(str).str.strip()

            try: # Validate terms needed for calculation
                annual_interest_rate = float(loan_terms_s.get("annualinterestrate", "Error")) # Use Error string to force exception if key missing
                if annual_interest_rate < 0: raise ValueError("Negative rate")
                late_fee_percentage = float(loan_terms_s.get("latefeepercentage", str(config.DEFAULT_LATE_FEE_PERCENTAGE)))
                grace_period_days = int(loan_terms_s.get("graceperioddays", str(config.DEFAULT_GRACE_PERIOD_DAYS)))
            except (ValueError, TypeError, KeyError) as ve:
                logger.error(f"Invalid/missing required value in LoanTerms for {loan_id_internal}: {ve}. Log index {original_log_index}.")
                df_log_sheet_state.loc[original_log_index, status_col_original_casing] = "Error - Invalid/Missing LoanTerm"; df_log_sheet_state.loc[original_log_index, timestamp_col_original_casing] = datetime.now(); continue

            # Parse Schedule columns strictly
            schedule_df[DUE_DATE_COL_SCHED] = pd.to_datetime(schedule_df.get(DUE_DATE_COL_SCHED), format='%Y-%m-%d', errors='coerce')
            schedule_df[ACTUAL_PMT_DATE_COL_SCHED] = pd.to_datetime(schedule_df.get(ACTUAL_PMT_DATE_COL_SCHED), format='%Y-%m-%d', errors='coerce')
            numeric_cols_schedule = [BEGIN_BAL_COL_SCHED, SCHED_PMT_COL_SCHED, ACTUAL_PMT_AMT_COL_SCHED, INTEREST_PAID_COL_SCHED, PRINCIPAL_PAID_COL_SCHED, LATE_FEE_COL_SCHED, CREDIT_APPLIED_COL_SCHED, ENDING_BAL_COL_SCHED]
            for col in numeric_cols_schedule: schedule_df[col] = pd.to_numeric(schedule_df.get(col), errors='coerce') # Missing become NaN
            if STATUS_COL_SCHED not in schedule_df.columns: schedule_df[STATUS_COL_SCHED] = "Due" # Add if missing

            # Find target row logic
            target_row_idx = -1
            for i, sr_iter in schedule_df.iterrows():
                cs = str(sr_iter.get(STATUS_COL_SCHED, "Due")).strip().lower()
                apds = sr_iter.get(ACTUAL_PMT_DATE_COL_SCHED) # Already datetime or NaT
                if pd.isna(apds) or cs in ["due", "partially paid", ""]: target_row_idx = i; break
            
            if target_row_idx == -1:
                df_log_sheet_state.loc[original_log_index, status_col_original_casing] = "Error - No Due Payment Slot"; df_log_sheet_state.loc[original_log_index, timestamp_col_original_casing] = datetime.now(); continue

            # Extract and validate data from schedule's target row
            due_date_dt_sched = schedule_df.loc[target_row_idx, DUE_DATE_COL_SCHED]
            beginning_balance_for_calc = schedule_df.loc[target_row_idx, BEGIN_BAL_COL_SCHED]
            scheduled_payment_on_schedule = schedule_df.loc[target_row_idx, SCHED_PMT_COL_SCHED]

            if pd.isna(due_date_dt_sched): df_log_sheet_state.loc[original_log_index, status_col_original_casing] = "Error - Invalid Sched. DueDate"; df_log_sheet_state.loc[original_log_index, timestamp_col_original_casing] = datetime.now(); continue
            if pd.isna(beginning_balance_for_calc): df_log_sheet_state.loc[original_log_index, status_col_original_casing] = "Error - Invalid Sched. BeginBal"; df_log_sheet_state.loc[original_log_index, timestamp_col_original_casing] = datetime.now(); continue
            if pd.isna(scheduled_payment_on_schedule): scheduled_payment_on_schedule = 0.0 # Allow 0 scheduled payment

            due_date_str_sched = due_date_dt_sched.strftime("%Y-%m-%d")

            # Call calculation function
            payment_calcs = calculate_payment_details(
                beginning_balance_for_calc, annual_interest_rate, 30, 
                scheduled_payment_on_schedule, actual_payment_amount_from_log,
                due_date_str_sched, actual_payment_date_str,
                late_fee_percentage, grace_period_days
            )

            # Update the target row in schedule_df
            schedule_df.loc[target_row_idx, ACTUAL_PMT_DATE_COL_SCHED] = actual_payment_date_dt # Use the datetime object
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
                    # Ensure BEGIN_BAL_COL_SCHED exists before assigning
                    if BEGIN_BAL_COL_SCHED in schedule_df.columns:
                         schedule_df.loc[next_row_idx, BEGIN_BAL_COL_SCHED] = payment_calcs["EndingBalance"]
                    else:
                         logger.warning(f"Column '{BEGIN_BAL_COL_SCHED}' missing in schedule for {loan_id_internal}, cannot update next row BB.")
            
            # Prepare schedule_df for writing back (restore original headers)
            schedule_df_to_write = schedule_df.copy()
            try:
                schedule_df_to_write.columns = current_original_schedule_headers 
            except ValueError:
                logger.warning(f"Could not restore original headers for schedule {loan_id_internal}. Writing with processed headers.")
            
            amortization_update_success = gutils.update_worksheet_from_df(gs_client, amortization_sheet_id, "Schedule", schedule_df_to_write)
            # --- End of Amortization Processing Block ---

            if amortization_update_success:
                df_log_sheet_state.loc[original_log_index, status_col_original_casing] = "Processed"
                df_log_sheet_state.loc[original_log_index, timestamp_col_original_casing] = datetime.now()
                logger.info(f"Successfully processed payment for {loan_id_internal} (log index {original_log_index}).")
            else: # Failed to save amortization sheet
                df_log_sheet_state.loc[original_log_index, status_col_original_casing] = "Error - Amort. Save Fail"
                df_log_sheet_state.loc[original_log_index, timestamp_col_original_casing] = datetime.now()

        except Exception as e: # Catch-all for this specific payment's processing
            logger.error(f"UNHANDLED EXCEPTION processing LoanID {loan_id_internal} (log index {original_log_index}): {e}", exc_info=True)
            df_log_sheet_state.loc[original_log_index, status_col_original_casing] = "Error - Unhandled Exception"
            df_log_sheet_state.loc[original_log_index, timestamp_col_original_casing] = datetime.now()
        
    # --- 4. Update Payments Log Sheet ---
    # df_log_sheet_state contains original key data + updated status/timestamp
    # Its columns should already match the original headers from the sheet
    if not gutils.update_worksheet_from_df(gs_client, config.PAYMENTS_LOG_SHEET_ID, "Sheet1", df_log_sheet_state):
        logger.error("CRITICAL: Failed to update the Payments Log sheet with final processing statuses.")
    else:
        logger.info("Payments Log sheet updated with all final statuses.")

    logger.info("Payment processing run finished.")