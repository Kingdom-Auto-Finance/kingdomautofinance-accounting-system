# src/payment_processor.py
import pandas as pd
from datetime import datetime
import logging
from decimal import Decimal, InvalidOperation # Import Decimal and potential error
from . import config
from . import gutils
from .amortization_calculator import calculate_principal_and_status 
from collections import defaultdict

logger = logging.getLogger(__name__)

# Helper function to clean and convert currency strings to float
def safe_string_to_float(value_str, context=""):
    """Cleans string (removes $, commas) and converts to float, returns pd.NA on error."""
    if pd.isna(value_str) or str(value_str).strip() == "":
        logger.debug(f"Value is empty/NA for {context}. Returning pd.NA.")
        return pd.NA # Use Pandas NA for missing float
    try:
        # Remove common currency symbols and commas
        cleaned_str = str(value_str).replace('$', '').replace(',', '').strip()
        # Handle parentheses for negative numbers
        if cleaned_str.startswith('(') and cleaned_str.endswith(')'):
             cleaned_str = '-' + cleaned_str[1:-1]
        return float(cleaned_str)
    except (ValueError, TypeError):
        logger.warning(f"Could not convert '{value_str}' to float for {context}. Returning pd.NA.")
        return pd.NA # Use Pandas NA on conversion error


def process_payments():
    logger.info("Starting payment processing (handling commas, using pre-filled interest)...")
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
    df_log_sheet_state = gutils.get_sheet_as_df(gs_client, config.PAYMENTS_LOG_SHEET_ID, "Sheet1")
    
    if df_log_sheet_state is None or df_log_sheet_state.empty:
        logger.info("Payments log empty/unreadable.")
        return

    original_log_headers = df_log_sheet_state.columns.tolist()
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
        df_log_sheet_state[status_col_original_casing] = '' 
        original_log_headers.append(status_col_original_casing) 
        header_map[PROCESSED_STATUS_COL_LOWER] = status_col_original_casing 
        logger.info(f"Added missing '{status_col_original_casing}' column to Payments Log DataFrame.")
    if not timestamp_col_original_casing:
        timestamp_col_original_casing = PROCESSED_TIMESTAMP_COL_LOWER 
        df_log_sheet_state[timestamp_col_original_casing] = pd.NaT 
        original_log_headers.append(timestamp_col_original_casing)
        header_map[PROCESSED_TIMESTAMP_COL_LOWER] = timestamp_col_original_casing
        logger.info(f"Added missing '{timestamp_col_original_casing}' column to Payments Log DataFrame.")


    # --- 2. Identify and Validate Pending Payments ---
    validated_payment_list = [] 
    rows_with_initial_errors = False

    for index, raw_row_series in df_log_sheet_state.iterrows():
        # Check current status using the original cased column name from the sheet state
        current_original_status = str(raw_row_series.get(status_col_original_casing, '')).strip().lower()
        # Skip if already processed or errored in a previous run
        if current_original_status.startswith('processed') or current_original_status.startswith('error'):
            continue 

        has_critical_error = False
        validated_data = {}
        loan_id_val = '' # Initialize for logging context

        # --- Validate LoanID ---
        loan_id_header_original = header_map.get(LOAN_ID_COL_LOWER)
        if not loan_id_header_original:
             logger.warning(f"Log index {index}: Critical column '{LOAN_ID_COL_LOWER}' not found in log headers. Skipping row validation.")
             df_log_sheet_state.loc[index, status_col_original_casing] = "Error - Missing LoanID Column"
             has_critical_error = True
        else:
            try: 
                raw_loan_id = str(raw_row_series.get(loan_id_header_original, '')).strip()
                loan_id_val = raw_loan_id.upper() # Use this for checks now
                if not raw_loan_id or loan_id_val == "NAN": 
                    raise ValueError("LoanID is missing or 'NAN'")
                validated_data['loanid_original_case'] = raw_loan_id 
                validated_data[LOAN_ID_COL_LOWER] = loan_id_val
            except Exception as e: # Catch potential errors during string conversion/check
                logger.warning(f"Log index {index}: Error validating LoanID ('{raw_loan_id}'). Error: {e}. Marking as error.")
                df_log_sheet_state.loc[index, status_col_original_casing] = "Error - Invalid/Missing LoanID"
                has_critical_error = True

        # --- Validate PaymentDate ---
        payment_date_header_original = header_map.get(PAYMENT_DATE_COL_LOWER)
        parsed_date = pd.NaT
        if not has_critical_error: # Proceed only if LoanID was okay
            if not payment_date_header_original:
                logger.warning(f"Log index {index}, LoanID '{loan_id_val}': Critical column '{PAYMENT_DATE_COL_LOWER}' not found. Marking as error.")
                df_log_sheet_state.loc[index, status_col_original_casing] = "Error - Missing PaymentDate Column"
                has_critical_error = True
            else:
                raw_payment_date = str(raw_row_series.get(payment_date_header_original, '')).strip()
                if not raw_payment_date:
                    logger.warning(f"Log index {index}, LoanID '{loan_id_val}': PaymentDate is empty. Marking as error.")
                    df_log_sheet_state.loc[index, status_col_original_casing] = "Error - Missing PaymentDate"
                    has_critical_error = True
                else:
                    try:
                        # Attempt strict YYYY-MM-DD parsing first
                        parsed_date = pd.to_datetime(raw_payment_date, format='%Y-%m-%d', errors='raise')
                    except (ValueError, TypeError):
                        try: 
                            # Fallback to general parsing if strict format fails
                            parsed_date = pd.to_datetime(raw_payment_date, errors='raise')
                            logger.warning(f"Log index {index}, LoanID '{loan_id_val}': Date '{raw_payment_date}' not YYYY-MM-DD. Parsed generally. Please correct source.")
                        except (ValueError, TypeError):
                            # If both fail, mark as error
                            logger.warning(f"Log index {index}, LoanID '{loan_id_val}': Date '{raw_payment_date}' invalid. Marking as error.")
                            df_log_sheet_state.loc[index, status_col_original_casing] = "Error - Invalid PaymentDate"
                            has_critical_error = True
            validated_data[PAYMENT_DATE_COL_LOWER] = parsed_date # Store parsed date or NaT

        # --- Validate PaymentAmount (Using safe_string_to_float) ---
        payment_amount_header_original = header_map.get(PAYMENT_AMOUNT_COL_LOWER)
        parsed_amount = pd.NA # Use Pandas NA for missing float
        if not has_critical_error: # Proceed only if prior fields okay
            if not payment_amount_header_original:
                logger.warning(f"Log index {index}, LoanID '{loan_id_val}': Critical column '{PAYMENT_AMOUNT_COL_LOWER}' not found. Marking as error.")
                df_log_sheet_state.loc[index, status_col_original_casing] = "Error - Missing PaymentAmount Column"
                has_critical_error = True
            else:
                raw_payment_amount = raw_row_series.get(payment_amount_header_original) # Get raw value
                parsed_amount = safe_string_to_float(raw_payment_amount, context=f"Log index {index}, LoanID {loan_id_val}")
                
                if pd.isna(parsed_amount): # Check if helper returned NA (means empty or invalid format)
                    # Log warning already happened in helper function
                    df_log_sheet_state.loc[index, status_col_original_casing] = "Error - Invalid PaymentAmount Format"
                    has_critical_error = True
                elif parsed_amount <= 0: # Check positivity after successful parse
                    logger.warning(f"Log index {index}, LoanID '{loan_id_val}': PaymentAmount {parsed_amount} not positive. Marking as error.")
                    df_log_sheet_state.loc[index, status_col_original_casing] = "Error - NonPositive PaymentAmount"
                    has_critical_error = True
                    parsed_amount = pd.NA # Treat as invalid if not positive
            validated_data[PAYMENT_AMOUNT_COL_LOWER] = parsed_amount # Store the float or pd.NA
        
        # --- Finalize row validation ---
        if has_critical_error:
            # Set timestamp only if an error occurred in this validation pass
            if pd.isna(raw_row_series.get(timestamp_col_original_casing)): # Avoid overwriting previous error timestamps
                 df_log_sheet_state.loc[index, timestamp_col_original_casing] = datetime.now()
            rows_with_initial_errors = True
        else:
             # Add to list for processing only if all critical fields parsed correctly
             if pd.notna(validated_data.get('loanid_original_case')) and \
                validated_data.get('loanid_original_case','').upper() != "NAN" and \
                pd.notna(validated_data.get(PAYMENT_DATE_COL_LOWER)) and \
                pd.notna(validated_data.get(PAYMENT_AMOUNT_COL_LOWER)):
                 payments_to_attempt_processing.append({'original_index': index, 'data': validated_data})
             else: 
                  # Safeguard if error logic missed something
                  # Only update status if it wasn't already set to an error
                  if not str(df_log_sheet_state.loc[index, status_col_original_casing]).lower().startswith("error"):
                      logger.warning(f"Log index {index}, LoanID '{loan_id_val}': Row invalid due to NaT/NaN post-parsing.")
                      df_log_sheet_state.loc[index, status_col_original_casing] = "Error - Invalid Parsed Data"
                      df_log_sheet_state.loc[index, timestamp_col_original_casing] = datetime.now()
                  rows_with_initial_errors = True


    # --- Handle case where no valid payments remain ---
    if not payments_to_attempt_processing:
        logger.info("No valid payments found to attempt processing after validation.")
        if rows_with_initial_errors: # Write back if validation marked errors
            logger.info("Writing back payments log with parsing error statuses...")
            # Use the state df which contains original data + error statuses
            if not gutils.update_worksheet_from_df(gs_client, config.PAYMENTS_LOG_SHEET_ID, "Sheet1", df_log_sheet_state): 
                logger.error("CRITICAL: Failed update Payments Log with parsing errors.")
            else: 
                logger.info("Payments Log sheet updated with parsing errors.")
        return
        
    # --- Group Validated Payments by LoanID and Sort ---
    payments_to_attempt_processing.sort(key=lambda p: (p['data'][LOAN_ID_COL_LOWER], p['data'][PAYMENT_DATE_COL_LOWER])) 
    grouped_payments = defaultdict(list)
    for payment_item in payments_to_attempt_processing: grouped_payments[payment_item['data'][LOAN_ID_COL_LOWER]].append(payment_item) 
    logger.info(f"Processing {len(payments_to_attempt_processing)} validated payments across {len(grouped_payments)} unique LoanIDs.")

    # --- 3. Process Payments Loan by Loan ---
    for loan_id_internal, payment_items_for_loan in grouped_payments.items():
        loan_id_original_case = payment_items_for_loan[0]['data']['loanid_original_case']
        logger.info(f"--- Processing {len(payment_items_for_loan)} payment(s) for LoanID: {loan_id_original_case} ---")
        
        amortization_sheet_id = gutils.find_sheet_id_by_loan_id_in_folder(loan_id_original_case)
        if not amortization_sheet_id:
            logger.error(f"Amort. Sheet ID for '{loan_id_original_case}' not found. Marking payments as error.")
            for item in payment_items_for_loan: 
                df_log_sheet_state.loc[item['original_index'], status_col_original_casing] = "Error - Amort. Sheet Not Found"
                df_log_sheet_state.loc[item['original_index'], timestamp_col_original_casing] = datetime.now()
            continue 

        schedule_df = None 
        loan_processing_failed_early = False
        current_original_schedule_headers = [] 
        grace_period_days = config.DEFAULT_GRACE_PERIOD_DAYS # Initialize with defaults
        flat_late_fee = Decimal('25.00')

        try: # Read sheet data and terms ONCE per loan
            logger.debug(f"Reading amortization data for {loan_id_internal}")
            loan_terms_df_raw = gutils.get_sheet_as_df(gs_client, amortization_sheet_id, "LoanTerms")
            schedule_df_raw = gutils.get_sheet_as_df(gs_client, amortization_sheet_id, "Schedule")
            if schedule_df_raw is None or schedule_df_raw.empty: raise ValueError("Schedule sheet empty or unreadable.")

            # Parse Loan Terms minimally
            if loan_terms_df_raw is not None and not loan_terms_df_raw.empty:
                loan_terms_df = loan_terms_df_raw.copy(); loan_terms_df.columns = [str(col).strip().lower() for col in loan_terms_df.columns]
                if 'parameter' in loan_terms_df.columns and 'value' in loan_terms_df.columns:
                    loan_terms_s = loan_terms_df.set_index('parameter')['value'].astype(str).str.strip()
                    try: grace_period_days = int(loan_terms_s.get("graceperioddays", config.DEFAULT_GRACE_PERIOD_DAYS))
                    except (ValueError, TypeError): pass
                    try: flat_late_fee = safe_string_to_decimal(loan_terms_s.get("flatlatefee", '25.00'), context="FlatLateFee").quantize(Decimal('0.01'))
                    except (ValueError, TypeError, InvalidOperation): pass # Use default if error or NaN
                    if flat_late_fee.is_nan(): flat_late_fee = Decimal('25.00') # Ensure default if parse failed
                else: logger.warning(f"LoanTerms for {loan_id_internal} missing parameter/value columns.")
            else: logger.warning(f"LoanTerms sheet for {loan_id_internal} empty or unreadable. Using default grace/fee.")

            # Prepare schedule_df
            schedule_df = schedule_df_raw.copy()
            current_original_schedule_headers = schedule_df.columns.tolist() 
            schedule_df.columns = [str(col).strip().lower() for col in schedule_df.columns] 

            # Define expected columns
            DUE_DATE_COL_SCHED = 'duedate'; BEGIN_BAL_COL_SCHED = 'beginningbalance'; 
            ACTUAL_PMT_DATE_COL_SCHED = 'actualpaymentdate'; ACTUAL_PMT_AMT_COL_SCHED = 'actualpaymentamount';
            INTEREST_PAID_COL_SCHED = 'interestpaid'; PRINCIPAL_PAID_COL_SCHED = 'principalpaid';
            LATE_FEE_COL_SCHED = 'latefee'; ENDING_BAL_COL_SCHED = 'endingbalance'; STATUS_COL_SCHED = 'status';

            required_schedule_cols = [DUE_DATE_COL_SCHED, BEGIN_BAL_COL_SCHED, INTEREST_PAID_COL_SCHED, ACTUAL_PMT_DATE_COL_SCHED, ACTUAL_PMT_AMT_COL_SCHED, PRINCIPAL_PAID_COL_SCHED, LATE_FEE_COL_SCHED, ENDING_BAL_COL_SCHED, STATUS_COL_SCHED]
            missing_cols = [col for col in required_schedule_cols if col not in schedule_df.columns]
            if missing_cols: raise ValueError(f"Schedule sheet missing required columns: {missing_cols}")

            # Parse schedule columns strictly, using helper for numerics
            schedule_df[DUE_DATE_COL_SCHED] = pd.to_datetime(schedule_df.get(DUE_DATE_COL_SCHED), format='%Y-%m-%d', errors='coerce')
            schedule_df[ACTUAL_PMT_DATE_COL_SCHED] = pd.to_datetime(schedule_df.get(ACTUAL_PMT_DATE_COL_SCHED), format='%Y-%m-%d', errors='coerce')
            
            numeric_schedule_cols = [BEGIN_BAL_COL_SCHED, INTEREST_PAID_COL_SCHED, ACTUAL_PMT_AMT_COL_SCHED, PRINCIPAL_PAID_COL_SCHED, LATE_FEE_COL_SCHED, ENDING_BAL_COL_SCHED]
            for col in numeric_schedule_cols:
                 schedule_df[col] = schedule_df[col].apply(lambda x: safe_string_to_float(x, context=f"Schedule Col {col}"))
                 schedule_df[col] = pd.to_numeric(schedule_df[col], errors='coerce') 

            if STATUS_COL_SCHED not in schedule_df.columns: schedule_df[STATUS_COL_SCHED] = "Due"

        except Exception as loan_read_error:
            logger.error(f"Error preparing amortization data for LoanID {loan_id_internal}: {loan_read_error}", exc_info=True)
            loan_processing_failed_early = True
            for item in payment_items_for_loan: 
                 df_log_sheet_state.loc[item['original_index'], status_col_original_casing] = f"Error - Amort. Read/Init Fail"; df_log_sheet_state.loc[item['original_index'], timestamp_col_original_casing] = datetime.now()
            continue # To next LoanID

        # --- Apply Payments to In-Memory Schedule ---
        loan_processing_succeeded_fully = True 
        if not loan_processing_failed_early and schedule_df is not None:
            for payment_item in payment_items_for_loan:
                original_log_index = payment_item['original_index']
                validated_data = payment_item['data']
                actual_payment_date_dt = validated_data[PAYMENT_DATE_COL_LOWER]
                actual_payment_amount_from_log = validated_data[PAYMENT_AMOUNT_COL_LOWER] # float
                actual_payment_date_str = actual_payment_date_dt.strftime("%Y-%m-%d")

                logger.debug(f"Applying pmt log idx {original_log_index} ({actual_payment_date_str}, Amt: {actual_payment_amount_from_log:.2f}) to {loan_id_internal}")

                try: # Inner try-except for applying one payment
                    target_row_idx = -1
                    for i, sr_iter in schedule_df.iterrows():
                        cs = str(sr_iter.get(STATUS_COL_SCHED, "Due")).strip().lower(); apds = sr_iter.get(ACTUAL_PMT_DATE_COL_SCHED)
                        if pd.isna(apds) or cs in ["due", "partially paid", ""]: target_row_idx = i; break
                    if target_row_idx == -1: raise ValueError("No Due Payment Slot found")

                    # Extract data needed for calculation from target row
                    due_date_dt_sched = schedule_df.loc[target_row_idx, DUE_DATE_COL_SCHED]
                    beginning_balance_for_calc = schedule_df.loc[target_row_idx, BEGIN_BAL_COL_SCHED] # Should be float or NaN
                    interest_paid_prefilled = schedule_df.loc[target_row_idx, INTEREST_PAID_COL_SCHED] # Should be float or NaN
                    
                    # Validate extracted schedule values
                    if pd.isna(due_date_dt_sched): raise ValueError("Invalid DueDate in target schedule row")
                    if pd.isna(beginning_balance_for_calc): raise ValueError("Invalid BeginBal in target schedule row") 
                    if pd.isna(interest_paid_prefilled): raise ValueError("Invalid/Missing PRE-FILLED InterestPaid in target schedule row")
                        
                    due_date_str_sched = due_date_dt_sched.strftime("%Y-%m-%d")

                    # Call calculation function (expects floats, date strings, int, Decimal fee)
                    payment_calcs = calculate_principal_and_status(
                        beginning_balance_float=beginning_balance_for_calc, # Pass float
                        interest_paid_prefilled_float=interest_paid_prefilled, # Pass float
                        actual_payment_amount_float=actual_payment_amount_from_log, 
                        due_date_str=due_date_str_sched, 
                        actual_payment_date_str=actual_payment_date_str,
                        grace_period_days=grace_period_days, 
                        late_fee_amount_flat=flat_late_fee # Pass Decimal fee
                    )

                    if payment_calcs is None: raise ValueError("Calculation function returned None.")

                    # Update specific columns in schedule_df (target_row_idx)
                    schedule_df.loc[target_row_idx, ACTUAL_PMT_DATE_COL_SCHED] = actual_payment_date_dt
                    schedule_df.loc[target_row_idx, ACTUAL_PMT_AMT_COL_SCHED] = actual_payment_amount_from_log
                    schedule_df.loc[target_row_idx, PRINCIPAL_PAID_COL_SCHED] = float(payment_calcs["PrincipalPaid"])
                    schedule_df.loc[target_row_idx, LATE_FEE_COL_SCHED] = float(payment_calcs["LateFee"])
                    schedule_df.loc[target_row_idx, STATUS_COL_SCHED] = payment_calcs["Status"]
                    schedule_df.loc[target_row_idx, ENDING_BAL_COL_SCHED] = float(payment_calcs["EndingBalance"])
                    # InterestPaid and BeginningBalance of this row are NOT changed.

                    # Update NEXT row's beginning balance 
                    next_row_idx = target_row_idx + 1
                    if next_row_idx < len(schedule_df):
                        is_next_row_paid = pd.notna(schedule_df.loc[next_row_idx, ACTUAL_PMT_DATE_COL_SCHED])
                        if not is_next_row_paid and BEGIN_BAL_COL_SCHED in schedule_df.columns:
                             schedule_df.loc[next_row_idx, BEGIN_BAL_COL_SCHED] = float(payment_calcs["EndingBalance"]) 
                    
                    # Mark successful application in log state temporarily
                    df_log_sheet_state.loc[original_log_index, status_col_original_casing] = "Processed"
                    df_log_sheet_state.loc[original_log_index, timestamp_col_original_casing] = datetime.now()
                    logger.debug(f"Applied payment log index {original_log_index} ok.")

                except Exception as payment_error: 
                    logger.error(f"Error applying payment log index {original_log_index} for LoanID {loan_id_internal}: {payment_error}", exc_info=True)
                    df_log_sheet_state.loc[original_log_index, status_col_original_casing] = f"Error - Payment Apply Fail ({type(payment_error).__name__})"
                    df_log_sheet_state.loc[original_log_index, timestamp_col_original_casing] = datetime.now()
                    loan_processing_succeeded_fully = False 
                    break # Exit inner loop for this loan

            # --- After processing all payments for this loan ---
            if loan_processing_succeeded_fully:
                logger.info(f"Attempting final save for amortization schedule {loan_id_internal}...")
                schedule_df_to_write = schedule_df.copy()
                try: schedule_df_to_write.columns = current_original_schedule_headers 
                except ValueError: logger.warning(f"Could not restore original headers for schedule {loan_id_internal}...")
                
                if gutils.update_worksheet_from_df(gs_client, amortization_sheet_id, "Schedule", schedule_df_to_write):
                    logger.info(f"Successfully saved updated amortization schedule for {loan_id_internal}.")
                else:
                    logger.error(f"Failed to save updated schedule for {loan_id_internal}. Reverting statuses.")
                    for item in payment_items_for_loan: 
                        if str(df_log_sheet_state.loc[item['original_index'], status_col_original_casing]).lower() == 'processed':
                            df_log_sheet_state.loc[item['original_index'], status_col_original_casing] = "Error - Amort. Save Fail"
                            df_log_sheet_state.loc[item['original_index'], timestamp_col_original_casing] = datetime.now() 
            else:
                 logger.warning(f"Skipping final amortization save for {loan_id_internal} due to error during payment application.")
        # End of outer try block for a single loan's processing
        
    # --- 4. Update Payments Log Sheet ---
    logger.info("Attempting final update of Payments Log sheet...")
    if not gutils.update_worksheet_from_df(gs_client, config.PAYMENTS_LOG_SHEET_ID, "Sheet1", df_log_sheet_state): # Use the original state df
        logger.error("CRITICAL: Failed to update the Payments Log sheet with final processing statuses.")
    else:
        logger.info("Payments Log sheet updated with all final statuses.")

    logger.info("Payment processing run finished.")