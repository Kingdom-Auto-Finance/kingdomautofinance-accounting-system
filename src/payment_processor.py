# src/payment_processor.py
import pandas as pd
from datetime import datetime
import logging
from decimal import Decimal, InvalidOperation # Import Decimal and potential error
from . import config
from . import gutils
from .amortization_calculator import calculate_principal_and_status # Using pre-filled interest version
from collections import defaultdict

logger = logging.getLogger(__name__)

# Helper function to clean and convert currency strings to float
def safe_string_to_float(value_str, context=""):
    """Cleans string (removes $, commas) and converts to float, returns pd.NA on error."""
    if pd.isna(value_str) or str(value_str).strip() == "":
        return pd.NA 
    try:
        cleaned_str = str(value_str).replace('$', '').replace(',', '').strip()
        if cleaned_str.startswith('(') and cleaned_str.endswith(')'):
             cleaned_str = '-' + cleaned_str[1:-1]
        return float(cleaned_str)
    except (ValueError, TypeError):
        logger.warning(f"Could not convert '{value_str}' to float for {context}. Returning pd.NA.")
        return pd.NA 

# Helper function to clean and convert string to Decimal (use if needed, e.g., for precise fees)
def safe_string_to_decimal(value_str, context=""):
    if pd.isna(value_str) or str(value_str).strip() == "": return Decimal('NaN')
    try:
        cleaned_str = str(value_str).replace('$', '').replace(',', '').strip()
        if cleaned_str.startswith('(') and cleaned_str.endswith(')'): cleaned_str = '-' + cleaned_str[1:-1]
        return Decimal(cleaned_str)
    except (TypeError, InvalidOperation): logger.warning(f"Could not convert '{value_str}' to Decimal for {context}. Returning NaN."); return Decimal('NaN')


def process_payments():
    logger.info("Starting payment processing (handling commas, using pre-filled interest, batching)...")
    gs_client = None
    try: gs_client = gutils.get_gspread_client()
    except ConnectionError as e: logger.error(f"CRITICAL: No GS client: {e}. Aborting."); return
    try: gutils.get_drive_service() 
    except ConnectionError as e: logger.warning(f"Could not init Drive client: {e}.")

    # --- 1. Read Payments Log and Prepare ---
    df_log_sheet_state = gutils.get_sheet_as_df(gs_client, config.PAYMENTS_LOG_SHEET_ID, "Sheet1")
    if df_log_sheet_state is None or df_log_sheet_state.empty: logger.info("Payments log empty/unreadable."); return

    original_log_headers = df_log_sheet_state.columns.tolist()
    # Create a clean lowercase version of headers for internal use
    current_log_headers_lower = [str(h).strip().lower() for h in original_log_headers]
    
    # Define expected internal lowercase column names
    LOAN_ID_COL_LOWER = 'loanid'; PAYMENT_DATE_COL_LOWER = 'paymentdate'; PAYMENT_AMOUNT_COL_LOWER = 'paymentamount';
    PROCESSED_STATUS_COL_LOWER = 'processedstatus'; PROCESSED_TIMESTAMP_COL_LOWER = 'processedtimestamp';

    # Check if essential columns exist (using lowercase map)
    essential_cols_present = all(col in current_log_headers_lower for col in [LOAN_ID_COL_LOWER, PAYMENT_DATE_COL_LOWER, PAYMENT_AMOUNT_COL_LOWER])
    if not essential_cols_present:
        logger.error(f"CRITICAL: Payments Log sheet missing one or more essential columns (LoanID, PaymentDate, PaymentAmount - case insensitive check). Headers found: {original_log_headers}. Aborting.")
        return 

    # Find original casing for status/timestamp columns, add them if missing
    status_col_original_casing = next((h for h in original_log_headers if str(h).strip().lower() == PROCESSED_STATUS_COL_LOWER), PROCESSED_STATUS_COL_LOWER)
    timestamp_col_original_casing = next((h for h in original_log_headers if str(h).strip().lower() == PROCESSED_TIMESTAMP_COL_LOWER), PROCESSED_TIMESTAMP_COL_LOWER)

    if PROCESSED_STATUS_COL_LOWER not in current_log_headers_lower:
         df_log_sheet_state[status_col_original_casing] = '' # Add with the chosen (likely lowercase) name
         logger.info(f"Added missing '{status_col_original_casing}' column to Payments Log.")
    if PROCESSED_TIMESTAMP_COL_LOWER not in current_log_headers_lower:
         df_log_sheet_state[timestamp_col_original_casing] = pd.NaT
         logger.info(f"Added missing '{timestamp_col_original_casing}' column to Payments Log.")
         
    # Assign standardized lowercase headers to a working copy for easier processing
    df_log_working = df_log_sheet_state.copy()
    df_log_working.columns = current_log_headers_lower


    # --- 2. Identify and Validate Pending Payments ---
    payments_to_attempt = [] # List of dicts: {'original_index': idx, 'loan_id': str, 'payment_date': datetime, 'payment_amount': float, 'loan_id_orig': str}
    rows_with_initial_errors = False

    for index, row in df_log_working.iterrows():
        # Use original_index to update df_log_sheet_state directly
        original_index = index 

        current_original_status = str(df_log_sheet_state.loc[original_index, status_col_original_casing]).strip().lower()
        if current_original_status.startswith('processed') or current_original_status.startswith('error'):
            continue # Skip already handled rows

        has_error = False
        # --- Validate LoanID ---
        loan_id_str_orig = str(row.get(LOAN_ID_COL_LOWER, '')).strip()
        loan_id_str_upper = loan_id_str_orig.upper()
        if not loan_id_str_orig or loan_id_str_upper == 'NAN':
             df_log_sheet_state.loc[original_index, status_col_original_casing] = "Error - Invalid/Missing LoanID"
             has_error = True; logger.warning(f"Log idx {original_index}: Invalid LoanID '{loan_id_str_orig}'")
        
        # --- Validate PaymentDate ---
        payment_date_str = str(row.get(PAYMENT_DATE_COL_LOWER, '')).strip()
        payment_date_dt = pd.NaT
        if not has_error:
            if not payment_date_str:
                df_log_sheet_state.loc[original_index, status_col_original_casing] = "Error - Missing PaymentDate"
                has_error = True; logger.warning(f"Log idx {original_index}: Missing PaymentDate")
            else:
                try: payment_date_dt = pd.to_datetime(payment_date_str, format='%Y-%m-%d', errors='raise')
                except (ValueError, TypeError):
                    try: payment_date_dt = pd.to_datetime(payment_date_str, errors='raise'); logger.warning(f"Log idx {original_index}: Date '{payment_date_str}' not YYYY-MM-DD...")
                    except (ValueError, TypeError): df_log_sheet_state.loc[original_index, status_col_original_casing] = "Error - Invalid PaymentDate"; has_error = True; logger.warning(f"Log idx {original_index}: Invalid Date '{payment_date_str}'")
        
        # --- Validate PaymentAmount ---
        payment_amount_str = str(row.get(PAYMENT_AMOUNT_COL_LOWER, '')).strip()
        payment_amount_float = pd.NA
        if not has_error:
             if not payment_amount_str:
                 df_log_sheet_state.loc[original_index, status_col_original_casing] = "Error - Missing PaymentAmount"
                 has_error = True; logger.warning(f"Log idx {original_index}: Missing PaymentAmount")
             else:
                 payment_amount_float = safe_string_to_float(payment_amount_str, context=f"Log idx {original_index}")
                 if pd.isna(payment_amount_float):
                      df_log_sheet_state.loc[original_index, status_col_original_casing] = "Error - Invalid PaymentAmount Format"
                      has_error = True # Warning already logged by helper
                 elif payment_amount_float <= 0:
                      df_log_sheet_state.loc[original_index, status_col_original_casing] = "Error - NonPositive PaymentAmount"
                      has_error = True; logger.warning(f"Log idx {original_index}: Non-positive Amount {payment_amount_float}")
                      payment_amount_float = pd.NA # Treat as invalid
        
        # Final check for row
        if has_error:
             df_log_sheet_state.loc[original_index, timestamp_col_original_casing] = datetime.now()
             rows_with_initial_errors = True
        else:
             # Add validated data to list for processing
             payments_to_attempt.append({
                 'original_index': original_index, 
                 'loan_id': loan_id_str_upper, # Use standardized uppercase for grouping
                 'payment_date': payment_date_dt, 
                 'payment_amount': payment_amount_float,
                 'loan_id_orig': loan_id_str_orig # Keep original for Drive search
             })

    # --- Handle case where no valid payments remain ---
    if not payments_to_attempt:
        logger.info("No valid payments found to attempt processing after validation.")
        if rows_with_initial_errors: 
            logger.info("Writing back payments log with parsing error statuses...")
            if not gutils.update_worksheet_from_df(gs_client, config.PAYMENTS_LOG_SHEET_ID, "Sheet1", df_log_sheet_state): logger.error("CRITICAL: Failed update Payments Log...")
            else: logger.info("Payments Log sheet updated with parsing errors.")
        return
        
    # --- Group Validated Payments by LoanID and Sort ---
    payments_to_attempt.sort(key=lambda p: (p['loan_id'], p['payment_date'])) # Group by LoanID (upper), then sort by date
    grouped_payments = defaultdict(list)
    for payment_item in payments_to_attempt: grouped_payments[payment_item['loan_id']].append(payment_item) 
    logger.info(f"Processing {len(payments_to_attempt)} validated payments across {len(grouped_payments)} unique LoanIDs.")

    # --- 3. Process Payments Loan by Loan ---
    for loan_id_internal, payment_items_for_loan in grouped_payments.items():
        loan_id_original_case = payment_items_for_loan[0]['loan_id_orig'] # Get original casing from first item
        logger.info(f"--- Processing {len(payment_items_for_loan)} payment(s) for LoanID: {loan_id_original_case} ---")
        
        amortization_sheet_id = gutils.find_sheet_id_by_loan_id_in_folder(loan_id_original_case)
        if not amortization_sheet_id:
            logger.error(f"Amort. Sheet ID for '{loan_id_original_case}' not found. Marking payments as error.")
            for item in payment_items_for_loan: 
                df_log_sheet_state.loc[item['original_index'], status_col_original_casing] = "Error - Amort. Sheet Not Found"
                df_log_sheet_state.loc[item['original_index'], timestamp_col_original_casing] = datetime.now()
            continue 

        # Initialize vars for this loan's processing
        schedule_df = None 
        loan_processing_failed_early = False
        current_original_schedule_headers = [] 
        grace_period_days = config.DEFAULT_GRACE_PERIOD_DAYS
        flat_late_fee = Decimal('25.00')

        try: # Read sheet data and terms ONCE per loan
            logger.debug(f"Reading amortization data for {loan_id_internal}")
            loan_terms_df_raw = gutils.get_sheet_as_df(gs_client, amortization_sheet_id, "LoanTerms")
            schedule_df_raw = gutils.get_sheet_as_df(gs_client, amortization_sheet_id, "Schedule")
            if schedule_df_raw is None or schedule_df_raw.empty: raise ValueError("Schedule sheet empty or unreadable.")

            # Parse Loan Terms minimally if sheet exists
            if loan_terms_df_raw is not None and not loan_terms_df_raw.empty:
                loan_terms_df = loan_terms_df_raw.copy(); loan_terms_df.columns = [str(col).strip().lower() for col in loan_terms_df.columns]
                if 'parameter' in loan_terms_df.columns and 'value' in loan_terms_df.columns:
                    loan_terms_s = loan_terms_df.set_index('parameter')['value'].astype(str).str.strip()
                    try: grace_period_days = int(loan_terms_s.get("graceperioddays", config.DEFAULT_GRACE_PERIOD_DAYS))
                    except (ValueError, TypeError): pass
                    try: 
                        fee_str = loan_terms_s.get("flatlatefee", '25.00')
                        temp_fee = safe_string_to_decimal(fee_str, context="FlatLateFee")
                        if not temp_fee.is_nan(): flat_late_fee = temp_fee.quantize(Decimal('0.01'))
                    except Exception: pass # Use default if any error
                else: logger.warning(f"LoanTerms for {loan_id_internal} missing parameter/value columns.")
            else: logger.warning(f"LoanTerms sheet empty/unreadable for {loan_id_internal}.")

            # Prepare schedule_df
            schedule_df = schedule_df_raw.copy()
            current_original_schedule_headers = schedule_df.columns.tolist() 
            schedule_df.columns = [str(col).strip().lower() for col in schedule_df.columns] 

            # Define expected columns for schedule
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
                 # Coerce to numeric after cleaning attempt
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
                actual_payment_date_dt = payment_item['payment_date'] # Already datetime
                actual_payment_amount_from_log = payment_item['payment_amount'] # Already float
                actual_payment_date_str = actual_payment_date_dt.strftime("%Y-%m-%d")

                logger.debug(f"Applying pmt log idx {original_log_index} ({actual_payment_date_str}, Amt: {actual_payment_amount_from_log:.2f}) to {loan_id_internal}")

                try: 
                    target_row_idx = -1
                    for i, sr_iter in schedule_df.iterrows():
                        cs = str(sr_iter.get(STATUS_COL_SCHED, "Due")).strip().lower(); apds = sr_iter.get(ACTUAL_PMT_DATE_COL_SCHED)
                        if pd.isna(apds) or cs in ["due", "partially paid", ""]: target_row_idx = i; break
                    if target_row_idx == -1: raise ValueError("No Due Payment Slot found")

                    # Extract required values from target row
                    due_date_dt_sched = schedule_df.loc[target_row_idx, DUE_DATE_COL_SCHED]
                    beginning_balance_for_calc = schedule_df.loc[target_row_idx, BEGIN_BAL_COL_SCHED] 
                    interest_paid_prefilled = schedule_df.loc[target_row_idx, INTEREST_PAID_COL_SCHED] 
                    
                    # Validate extracted schedule values are not NA (parsing errors)
                    if pd.isna(due_date_dt_sched): raise ValueError("Invalid DueDate in target schedule row")
                    if pd.isna(beginning_balance_for_calc): raise ValueError("Invalid BeginBal in target schedule row") 
                    if pd.isna(interest_paid_prefilled): raise ValueError("Invalid/Missing PRE-FILLED InterestPaid in target schedule row")
                        
                    due_date_str_sched = due_date_dt_sched.strftime("%Y-%m-%d")

                    # Call calculation function (using pre-filled interest logic)
                    payment_calcs = calculate_principal_and_status(
                        beginning_balance_float=beginning_balance_for_calc, 
                        interest_paid_prefilled_float=interest_paid_prefilled, 
                        actual_payment_amount_float=actual_payment_amount_from_log, 
                        due_date_str=due_date_str_sched, 
                        actual_payment_date_str=actual_payment_date_str,
                        grace_period_days=grace_period_days, 
                        late_fee_amount_flat=flat_late_fee 
                    )

                    if payment_calcs is None: raise ValueError("Calculation function returned None.")

                    # Update specific columns in schedule_df (in memory)
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
                    # Update log state for this specific failed payment
                    df_log_sheet_state.loc[original_log_index, status_col_original_casing] = f"Error - Payment Apply Fail ({type(payment_error).__name__})"
                    df_log_sheet_state.loc[original_log_index, timestamp_col_original_casing] = datetime.now()
                    loan_processing_succeeded_fully = False # Mark loan as failed
                    break # Stop processing further payments for THIS loan if one fails

            # --- After processing all payments for this loan ---
            if loan_processing_succeeded_fully:
                logger.info(f"Attempting final save for amortization schedule {loan_id_internal}...")
                schedule_df_to_write = schedule_df.copy()
                try: schedule_df_to_write.columns = current_original_schedule_headers 
                except ValueError: logger.warning(f"Could not restore original headers for schedule {loan_id_internal}...")
                
                if gutils.update_worksheet_from_df(gs_client, amortization_sheet_id, "Schedule", schedule_df_to_write):
                    logger.info(f"Successfully saved updated amortization schedule for {loan_id_internal}.")
                    # Log statuses are already marked 'Processed' correctly.
                else:
                    logger.error(f"Failed to save updated schedule for {loan_id_internal}. Reverting statuses for this loan's payments.")
                    # Revert status ONLY for payments processed in this batch for this specific loan
                    for item in payment_items_for_loan: 
                        # Check if it was marked 'Processed' during this attempt
                        if str(df_log_sheet_state.loc[item['original_index'], status_col_original_casing]).lower() == 'processed':
                            df_log_sheet_state.loc[item['original_index'], status_col_original_casing] = "Error - Amort. Save Fail"
                            df_log_sheet_state.loc[item['original_index'], timestamp_col_original_casing] = datetime.now() 
            else:
                 logger.warning(f"Skipping final amortization save for {loan_id_internal} due to error during payment application.")
        # End of outer try block for processing a single loan's amortization sheet
        
    # --- 4. Update Payments Log Sheet ---
    logger.info("Attempting final update of Payments Log sheet...")
    if not gutils.update_worksheet_from_df(gs_client, config.PAYMENTS_LOG_SHEET_ID, "Sheet1", df_log_sheet_state): # Use the original state df
        logger.error("CRITICAL: Failed to update the Payments Log sheet with final processing statuses.")
    else:
        logger.info("Payments Log sheet updated with all final statuses.")

    logger.info("Payment processing run finished.")