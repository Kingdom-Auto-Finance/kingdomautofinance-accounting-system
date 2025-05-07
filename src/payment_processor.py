# src/payment_processor.py
import pandas as pd
from datetime import datetime
import logging
from decimal import Decimal # Import Decimal for potential use if passing fees/terms
from . import config
from . import gutils
# Import the renamed calculation function
from .amortization_calculator import calculate_principal_and_status 
from collections import defaultdict

logger = logging.getLogger(__name__)

def process_payments():
    logger.info("Starting payment processing (using pre-filled interest)...")
    gs_client = None
    try: gs_client = gutils.get_gspread_client()
    except ConnectionError as e: logger.error(f"CRITICAL: No GS client: {e}. Aborting."); return
    try: gutils.get_drive_service() 
    except ConnectionError as e: logger.warning(f"Could not init Drive client: {e}.")

    # --- 1. Read Payments Log ---
    df_log_sheet_state = gutils.get_sheet_as_df(gs_client, config.PAYMENTS_LOG_SHEET_ID, "Sheet1")
    if df_log_sheet_state is None or df_log_sheet_state.empty: logger.info("Payments log empty/unreadable."); return

    original_log_headers = df_log_sheet_state.columns.tolist()
    header_map = {str(h).strip().lower(): h for h in original_log_headers}

    LOAN_ID_COL_LOWER = 'loanid'; PAYMENT_DATE_COL_LOWER = 'paymentdate'; PAYMENT_AMOUNT_COL_LOWER = 'paymentamount';
    PROCESSED_STATUS_COL_LOWER = 'processedstatus'; PROCESSED_TIMESTAMP_COL_LOWER = 'processedtimestamp';

    status_col_original_casing = header_map.get(PROCESSED_STATUS_COL_LOWER, PROCESSED_STATUS_COL_LOWER)
    timestamp_col_original_casing = header_map.get(PROCESSED_TIMESTAMP_COL_LOWER, PROCESSED_TIMESTAMP_COL_LOWER)

    if status_col_original_casing not in df_log_sheet_state.columns: df_log_sheet_state[status_col_original_casing] = ''
    if timestamp_col_original_casing not in df_log_sheet_state.columns: df_log_sheet_state[timestamp_col_original_casing] = pd.NaT


    # --- 2. Identify and Validate Pending Payments ---
    validated_payment_list = [] 
    rows_with_initial_errors = False

    for index, raw_row_series in df_log_sheet_state.iterrows():
        current_original_status = str(raw_row_series.get(status_col_original_casing, '')).strip().lower()
        if current_original_status.startswith('processed') or current_original_status.startswith('error'): continue 

        has_critical_error = False; validated_data = {}; loan_id_val = ''
        # Validate LoanID
        loan_id_header_original = header_map.get(LOAN_ID_COL_LOWER)
        if not loan_id_header_original: df_log_sheet_state.loc[index, status_col_original_casing] = "Error - Missing LoanID Column"; has_critical_error = True
        else:
            try: 
                raw_loan_id = str(raw_row_series.get(loan_id_header_original, '')).strip(); loan_id_val = raw_loan_id.upper()
                if not raw_loan_id or loan_id_val == "NAN": raise ValueError("LoanID missing/NAN")
                validated_data['loanid_original_case'] = raw_loan_id; validated_data[LOAN_ID_COL_LOWER] = loan_id_val
            except Exception as e: df_log_sheet_state.loc[index, status_col_original_casing] = "Error - Invalid/Missing LoanID"; has_critical_error = True; logger.warning(f"Log idx {index}: LoanID validation error: {e}")

        # Validate PaymentDate
        payment_date_header_original = header_map.get(PAYMENT_DATE_COL_LOWER); parsed_date = pd.NaT
        if not has_critical_error:
            if not payment_date_header_original: df_log_sheet_state.loc[index, status_col_original_casing] = "Error - Missing PaymentDate Column"; has_critical_error = True
            else:
                raw_payment_date = str(raw_row_series.get(payment_date_header_original, '')).strip()
                if not raw_payment_date: df_log_sheet_state.loc[index, status_col_original_casing] = "Error - Missing PaymentDate"; has_critical_error = True
                else:
                    try: parsed_date = pd.to_datetime(raw_payment_date, format='%Y-%m-%d', errors='raise')
                    except (ValueError, TypeError):
                        try: parsed_date = pd.to_datetime(raw_payment_date, errors='raise'); logger.warning(f"Log index {index}: Date '{raw_payment_date}' not YYYY-MM-DD...")
                        except (ValueError, TypeError): df_log_sheet_state.loc[index, status_col_original_casing] = "Error - Invalid PaymentDate"; has_critical_error = True
            validated_data[PAYMENT_DATE_COL_LOWER] = parsed_date

        # Validate PaymentAmount
        payment_amount_header_original = header_map.get(PAYMENT_AMOUNT_COL_LOWER); parsed_amount = pd.NA 
        if not has_critical_error:
            if not payment_amount_header_original: df_log_sheet_state.loc[index, status_col_original_casing] = "Error - Missing PaymentAmount Column"; has_critical_error = True
            else:
                 raw_payment_amount = str(raw_row_series.get(payment_amount_header_original, '')).strip()
                 if not raw_payment_amount: df_log_sheet_state.loc[index, status_col_original_casing] = "Error - Missing PaymentAmount"; has_critical_error = True
                 else:
                     try: 
                         parsed_amount = float(raw_payment_amount) 
                         if parsed_amount <= 0: raise ValueError("Payment amount must be positive.") 
                     except (ValueError, TypeError) as e: 
                         df_log_sheet_state.loc[index, status_col_original_casing] = "Error - Invalid PaymentAmount"; has_critical_error = True; parsed_amount = pd.NA; logger.warning(f"Log idx {index}...: PaymentAmount '{raw_payment_amount}' invalid... Error: {e}")
            validated_data[PAYMENT_AMOUNT_COL_LOWER] = parsed_amount
        
        if has_critical_error:
            df_log_sheet_state.loc[index, timestamp_col_original_casing] = datetime.now(); rows_with_initial_errors = True
        else:
             if pd.notna(validated_data.get('loanid_original_case')) and validated_data.get('loanid_original_case','').upper() != "NAN" and pd.notna(validated_data.get(PAYMENT_DATE_COL_LOWER)) and pd.notna(validated_data.get(PAYMENT_AMOUNT_COL_LOWER)):
                 validated_payment_list.append({'original_index': index, 'data': validated_data})
             else: 
                  if not str(df_log_sheet_state.loc[index, status_col_original_casing]).lower().startswith("error"):
                      df_log_sheet_state.loc[index, status_col_original_casing] = "Error - Invalid Parsed Data"; df_log_sheet_state.loc[index, timestamp_col_original_casing] = datetime.now(); rows_with_initial_errors = True

    if not validated_payment_list:
        logger.info("No valid payments found to attempt processing after validation.")
        if rows_with_initial_errors: 
            logger.info("Writing back payments log with parsing error statuses...")
            if not gutils.update_worksheet_from_df(gs_client, config.PAYMENTS_LOG_SHEET_ID, "Sheet1", df_log_sheet_state): logger.error("CRITICAL: Failed update Payments Log...")
            else: logger.info("Payments Log sheet updated with parsing errors.")
        return
        
    validated_payment_list.sort(key=lambda p: (p['data'][LOAN_ID_COL_LOWER], p['data'][PAYMENT_DATE_COL_LOWER])) 
    grouped_payments = defaultdict(list)
    for payment_item in validated_payment_list: grouped_payments[payment_item['data'][LOAN_ID_COL_LOWER]].append(payment_item) 
    logger.info(f"Processing {len(validated_payment_list)} validated payments across {len(grouped_payments)} unique LoanIDs.")

    # --- 3. Process Payments Loan by Loan ---
    for loan_id_internal, payment_items_for_loan in grouped_payments.items():
        loan_id_original_case = payment_items_for_loan[0]['data']['loanid_original_case']
        logger.info(f"--- Processing {len(payment_items_for_loan)} payment(s) for LoanID: {loan_id_original_case} ---")
        
        amortization_sheet_id = gutils.find_sheet_id_by_loan_id_in_folder(loan_id_original_case)
        if not amortization_sheet_id:
            logger.error(f"Amort. Sheet ID for '{loan_id_original_case}' not found. Marking payments as error.")
            for item in payment_items_for_loan: df_log_sheet_state.loc[item['original_index'], status_col_original_casing] = "Error - Amort. Sheet Not Found"; df_log_sheet_state.loc[item['original_index'], timestamp_col_original_casing] = datetime.now()
            continue 

        schedule_df = None 
        loan_processing_failed_early = False
        current_original_schedule_headers = [] 

        try: # Read sheet data and terms ONCE per loan
            logger.debug(f"Reading amortization data for {loan_id_internal}")
            # LoanTerms are no longer strictly needed for interest calc, but might be for grace period/fee? Read anyway.
            loan_terms_df_raw = gutils.get_sheet_as_df(gs_client, amortization_sheet_id, "LoanTerms")
            schedule_df_raw = gutils.get_sheet_as_df(gs_client, amortization_sheet_id, "Schedule")
            if loan_terms_df_raw is None or schedule_df_raw is None or schedule_df_raw.empty: # Allow empty LoanTerms if not used
                raise ValueError("Schedule sheet empty or unreadable.")

            # Parse Loan Terms minimally for grace period/fee if needed (provide defaults)
            grace_period_days = config.DEFAULT_GRACE_PERIOD_DAYS
            late_fee_amount = Decimal(str(config.DEFAULT_LATE_FEE_PERCENTAGE)) # Placeholder - using flat fee now
            flat_late_fee = Decimal('25.00') # Default flat fee
            
            if not loan_terms_df_raw.empty:
                loan_terms_df = loan_terms_df_raw.copy()
                loan_terms_df.columns = [str(col).strip().lower() for col in loan_terms_df.columns]
                if 'parameter' in loan_terms_df.columns and 'value' in loan_terms_df.columns:
                    loan_terms_s = loan_terms_df.set_index('parameter')['value'].astype(str).str.strip()
                    try: grace_period_days = int(loan_terms_s.get("graceperioddays", config.DEFAULT_GRACE_PERIOD_DAYS))
                    except (ValueError, TypeError): pass # Use default if invalid
                    try: flat_late_fee = Decimal(loan_terms_s.get("flatlatefee", '25.00')).quantize(Decimal('0.01')) # Example: Get flat fee if defined
                    except (ValueError, TypeError, decimal.InvalidOperation): pass # Use default if invalid
                else: logger.warning(f"LoanTerms sheet for {loan_id_internal} missing parameter/value columns.")


            # Prepare schedule_df
            schedule_df = schedule_df_raw.copy()
            current_original_schedule_headers = schedule_df.columns.tolist() 
            schedule_df.columns = [str(col).strip().lower() for col in schedule_df.columns] 

            # Define expected internal lowercase column names for schedule
            DUE_DATE_COL_SCHED = 'duedate'; BEGIN_BAL_COL_SCHED = 'beginningbalance'; SCHED_PMT_COL_SCHED = 'scheduledpayment';
            ACTUAL_PMT_DATE_COL_SCHED = 'actualpaymentdate'; ACTUAL_PMT_AMT_COL_SCHED = 'actualpaymentamount';
            INTEREST_PAID_COL_SCHED = 'interestpaid'; PRINCIPAL_PAID_COL_SCHED = 'principalpaid';
            LATE_FEE_COL_SCHED = 'latefee'; CREDIT_APPLIED_COL_SCHED = 'creditapplied'; # Although not used by calc
            ENDING_BAL_COL_SCHED = 'endingbalance'; STATUS_COL_SCHED = 'status';

            # Ensure required columns exist for reading/writing
            required_schedule_cols = [DUE_DATE_COL_SCHED, BEGIN_BAL_COL_SCHED, INTEREST_PAID_COL_SCHED, # Need prefilled InterestPaid
                                      ACTUAL_PMT_DATE_COL_SCHED, ACTUAL_PMT_AMT_COL_SCHED, 
                                      PRINCIPAL_PAID_COL_SCHED, LATE_FEE_COL_SCHED, 
                                      ENDING_BAL_COL_SCHED, STATUS_COL_SCHED]
            missing_cols = [col for col in required_schedule_cols if col not in schedule_df.columns]
            if missing_cols:
                raise ValueError(f"Schedule sheet missing required columns: {missing_cols}")

            # Parse schedule types strictly
            schedule_df[DUE_DATE_COL_SCHED] = pd.to_datetime(schedule_df.get(DUE_DATE_COL_SCHED), format='%Y-%m-%d', errors='coerce')
            schedule_df[ACTUAL_PMT_DATE_COL_SCHED] = pd.to_datetime(schedule_df.get(ACTUAL_PMT_DATE_COL_SCHED), format='%Y-%m-%d', errors='coerce')
            
            # Columns needed for calculation must be numeric
            numeric_calc_cols = [BEGIN_BAL_COL_SCHED, INTEREST_PAID_COL_SCHED] # ScheduledPayment no longer directly needed by calc
            for col in numeric_calc_cols: 
                schedule_df[col] = pd.to_numeric(schedule_df.get(col), errors='coerce')
                if schedule_df[col].isna().any(): # Check if coercion failed for any row needed later
                     logger.warning(f"Column '{col}' in schedule for {loan_id_internal} contains non-numeric values that became NaN.")
                     # This might cause errors later if NaN is used in calculation

            # Other columns to update (initialize type if converting later)
            numeric_update_cols = [ACTUAL_PMT_AMT_COL_SCHED, PRINCIPAL_PAID_COL_SCHED, LATE_FEE_COL_SCHED, ENDING_BAL_COL_SCHED]
            for col in numeric_update_cols: schedule_df[col] = pd.to_numeric(schedule_df.get(col), errors='coerce') 
            
            if STATUS_COL_SCHED not in schedule_df.columns: schedule_df[STATUS_COL_SCHED] = "Due"


        except Exception as loan_read_error: # Catch errors reading/parsing sheet/terms
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
                    if target_row_idx == -1: raise ValueError("No Due Payment Slot found in schedule")

                    # Extract data needed for calculation from target row
                    due_date_dt_sched = schedule_df.loc[target_row_idx, DUE_DATE_COL_SCHED]
                    beginning_balance_for_calc = schedule_df.loc[target_row_idx, BEGIN_BAL_COL_SCHED]
                    interest_paid_prefilled = schedule_df.loc[target_row_idx, INTEREST_PAID_COL_SCHED] # Read pre-filled interest
                    
                    # *** Validate extracted values from schedule ***
                    if pd.isna(due_date_dt_sched): raise ValueError("Invalid DueDate in target schedule row")
                    if pd.isna(beginning_balance_for_calc): raise ValueError("Invalid BeginBal in target schedule row")
                    if pd.isna(interest_paid_prefilled): raise ValueError("Invalid/Missing PRE-FILLED InterestPaid in target schedule row")
                        
                    due_date_str_sched = due_date_dt_sched.strftime("%Y-%m-%d")

                    # Call new calculation function (expects floats, strings, int)
                    payment_calcs = calculate_principal_and_status(
                        beginning_balance_float=float(beginning_balance_for_calc), 
                        interest_paid_prefilled_float=float(interest_paid_prefilled), # Pass pre-filled interest
                        actual_payment_amount_float=actual_payment_amount_from_log, 
                        due_date_str=due_date_str_sched, 
                        actual_payment_date_str=actual_payment_date_str,
                        grace_period_days=grace_period_days, 
                        late_fee_amount_flat=flat_late_fee # Pass Decimal fee
                    )

                    if payment_calcs is None: 
                        raise ValueError("Calculation function returned None (input error).")

                    # --- Update ONLY the specified columns in schedule_df ---
                    schedule_df.loc[target_row_idx, ACTUAL_PMT_DATE_COL_SCHED] = actual_payment_date_dt # Update Date
                    schedule_df.loc[target_row_idx, ACTUAL_PMT_AMT_COL_SCHED] = actual_payment_amount_from_log # Update Amount
                    schedule_df.loc[target_row_idx, PRINCIPAL_PAID_COL_SCHED] = float(payment_calcs["PrincipalPaid"]) # Update Principal Paid (as float)
                    schedule_df.loc[target_row_idx, LATE_FEE_COL_SCHED] = float(payment_calcs["LateFee"]) # Update Late Fee Charged (as float)
                    schedule_df.loc[target_row_idx, STATUS_COL_SCHED] = payment_calcs["Status"] # Update Status
                    # DO NOT update InterestPaid or BeginningBalance for this row (target_row_idx)

                    # Update EndingBalance (calculated, store as float)
                    schedule_df.loc[target_row_idx, ENDING_BAL_COL_SCHED] = float(payment_calcs["EndingBalance"])

                    # Update NEXT row's beginning balance (if applicable)
                    next_row_idx = target_row_idx + 1
                    if next_row_idx < len(schedule_df):
                        is_next_row_paid = pd.notna(schedule_df.loc[next_row_idx, ACTUAL_PMT_DATE_COL_SCHED]) # Simplified check
                        if not is_next_row_paid and BEGIN_BAL_COL_SCHED in schedule_df.columns:
                             schedule_df.loc[next_row_idx, BEGIN_BAL_COL_SCHED] = float(payment_calcs["EndingBalance"]) # Use calculated ending balance
                    
                    # Mark successful application in log state temporarily
                    df_log_sheet_state.loc[original_log_index, status_col_original_casing] = "Processed"
                    df_log_sheet_state.loc[original_log_index, timestamp_col_original_casing] = datetime.now()
                    logger.debug(f"Applied payment log index {original_log_index} ok to in-memory schedule for {loan_id_internal}.")

                except Exception as payment_error: 
                    logger.error(f"Error applying payment log index {original_log_index} for LoanID {loan_id_internal}: {payment_error}", exc_info=True)
                    df_log_sheet_state.loc[original_log_index, status_col_original_casing] = f"Error - Payment Apply Fail ({type(payment_error).__name__})"
                    df_log_sheet_state.loc[original_log_index, timestamp_col_original_casing] = datetime.now()
                    loan_processing_succeeded_fully = False 
                    break # Exit inner loop for this loan if one payment fails

            # --- After processing all payments for this loan ---
            if loan_processing_succeeded_fully:
                logger.info(f"Attempting final save for amortization schedule {loan_id_internal}...")
                schedule_df_to_write = schedule_df.copy()
                try: schedule_df_to_write.columns = current_original_schedule_headers # Restore original headers
                except ValueError: logger.warning(f"Could not restore original headers for schedule {loan_id_internal}...")
                
                if gutils.update_worksheet_from_df(gs_client, amortization_sheet_id, "Schedule", schedule_df_to_write):
                    logger.info(f"Successfully saved updated amortization schedule for {loan_id_internal}.")
                else:
                    logger.error(f"Failed to save updated amortization schedule for {loan_id_internal}. Reverting statuses.")
                    for item in payment_items_for_loan: # Revert only those processed in this batch for this loan
                        if str(df_log_sheet_state.loc[item['original_index'], status_col_original_casing]).lower() == 'processed':
                            df_log_sheet_state.loc[item['original_index'], status_col_original_casing] = "Error - Amort. Save Fail"
                            df_log_sheet_state.loc[item['original_index'], timestamp_col_original_casing] = datetime.now() 
            else:
                 logger.warning(f"Skipping final amortization save for {loan_id_internal} due to error during payment application.")
        # End of outer try block for a single loan's processing
        
    # --- 4. Update Payments Log Sheet (ONCE at the end) ---
    logger.info("Attempting final update of Payments Log sheet...")
    if not gutils.update_worksheet_from_df(gs_client, config.PAYMENTS_LOG_SHEET_ID, "Sheet1", df_log_sheet_state): # Use the original state df
        logger.error("CRITICAL: Failed to update the Payments Log sheet with final processing statuses.")
    else:
        logger.info("Payments Log sheet updated with all final statuses.")

    logger.info("Payment processing run finished.")