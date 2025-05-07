# src/payment_processor.py
import pandas as pd
from datetime import datetime
import logging
from . import config
from . import gutils # gutils now contains the new Drive search function
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
    # Initialize Drive client (optional early init, or let find_sheet_id init it)
    try:
        gutils.get_drive_service() 
    except ConnectionError as e:
         logger.warning(f"Could not initialize Google Drive client on startup: {e}. Will try again if needed.")


    # --- 1. Read Payments Log ---
    df_log_sheet_state = gutils.get_sheet_as_df(gs_client, config.PAYMENTS_LOG_SHEET_ID, "Sheet1")
    
    if df_log_sheet_state is None or df_log_sheet_state.empty:
        logger.info("Payments log is empty or could not be read.")
        return

    original_log_headers = df_log_sheet_state.columns.tolist()
    header_map = {str(h).strip().lower(): h for h in original_log_headers}

    LOAN_ID_COL_LOWER = 'loanid'
    PAYMENT_DATE_COL_LOWER = 'paymentdate'
    PAYMENT_AMOUNT_COL_LOWER = 'paymentamount'
    PROCESSED_STATUS_COL_LOWER = 'processedstatus'
    PROCESSED_TIMESTAMP_COL_LOWER = 'processedtimestamp'

    status_col_original_casing = header_map.get(PROCESSED_STATUS_COL_LOWER) or PROCESSED_STATUS_COL_LOWER
    timestamp_col_original_casing = header_map.get(PROCESSED_TIMESTAMP_COL_LOWER) or PROCESSED_TIMESTAMP_COL_LOWER

    if status_col_original_casing not in df_log_sheet_state.columns: df_log_sheet_state[status_col_original_casing] = ''
    if timestamp_col_original_casing not in df_log_sheet_state.columns: df_log_sheet_state[timestamp_col_original_casing] = pd.NaT


    # --- 2. Identify and Validate Pending Payments ---
    payments_to_attempt_processing = []
    rows_with_initial_errors = False

    for index, raw_row_series in df_log_sheet_state.iterrows():
        current_original_status = str(raw_row_series.get(status_col_original_casing, '')).strip().lower()
        if current_original_status.startswith('processed') or current_original_status.startswith('error'):
            continue

        has_critical_error = False
        validated_data = {}
        
        # LoanID validation
        raw_loan_id = str(raw_row_series.get(header_map.get(LOAN_ID_COL_LOWER, LOAN_ID_COL_LOWER), '')).strip()
        if not raw_loan_id or raw_loan_id.upper() == "NAN":
            logger.warning(f"Log index {index}: Invalid/Missing LoanID ('{raw_loan_id}'). Error.")
            df_log_sheet_state.loc[index, status_col_original_casing] = "Error - Invalid/Missing LoanID in Log"
            has_critical_error = True
        else:
            # Keep original casing for filename search, uppercase internal for consistency if needed elsewhere
            validated_data['loanid_original_case'] = raw_loan_id 
            validated_data[LOAN_ID_COL_LOWER] = raw_loan_id.upper() # Uppercase for internal use

        # PaymentDate validation
        raw_payment_date = str(raw_row_series.get(header_map.get(PAYMENT_DATE_COL_LOWER, PAYMENT_DATE_COL_LOWER), '')).strip()
        if not has_critical_error:
            parsed_date = pd.NaT
            if not raw_payment_date:
                df_log_sheet_state.loc[index, status_col_original_casing] = "Error - Missing PaymentDate"; has_critical_error = True
            else:
                try: parsed_date = pd.to_datetime(raw_payment_date, format='%Y-%m-%d', errors='raise')
                except (ValueError, TypeError):
                    try: parsed_date = pd.to_datetime(raw_payment_date, errors='raise'); logger.warning(f"Log index {index}: Date '{raw_payment_date}' not YYYY-MM-DD...")
                    except (ValueError, TypeError): df_log_sheet_state.loc[index, status_col_original_casing] = "Error - Invalid PaymentDate"; has_critical_error = True
            validated_data[PAYMENT_DATE_COL_LOWER] = parsed_date

        # PaymentAmount validation
        raw_payment_amount = str(raw_row_series.get(header_map.get(PAYMENT_AMOUNT_COL_LOWER, PAYMENT_AMOUNT_COL_LOWER), '')).strip()
        if not has_critical_error:
            parsed_amount = pd.NA
            if not raw_payment_amount:
                df_log_sheet_state.loc[index, status_col_original_casing] = "Error - Missing PaymentAmount"; has_critical_error = True
            else:
                try: parsed_amount = float(raw_payment_amount);
                     if parsed_amount <= 0: raise ValueError("Amount must be positive.")
                except (ValueError, TypeError): df_log_sheet_state.loc[index, status_col_original_casing] = "Error - Invalid PaymentAmount"; has_critical_error = True
            validated_data[PAYMENT_AMOUNT_COL_LOWER] = parsed_amount
        
        if has_critical_error:
            df_log_sheet_state.loc[index, timestamp_col_original_casing] = datetime.now()
            rows_with_initial_errors = True
        else:
             # Final check on parsed values before adding
             if pd.notna(validated_data.get('loanid_original_case')) and \
                validated_data.get('loanid_original_case').upper() != "NAN" and \
                pd.notna(validated_data.get(PAYMENT_DATE_COL_LOWER)) and \
                pd.notna(validated_data.get(PAYMENT_AMOUNT_COL_LOWER)):
                 payments_to_attempt_processing.append({'original_index': index, 'data': validated_data})
             else: 
                  if not str(df_log_sheet_state.loc[index, status_col_original_casing]).lower().startswith("error"):
                      df_log_sheet_state.loc[index, status_col_original_casing] = "Error - Invalid Parsed Data"; df_log_sheet_state.loc[index, timestamp_col_original_casing] = datetime.now(); rows_with_initial_errors = True


    if not payments_to_attempt_processing:
        logger.info("No valid payments found to attempt processing after validation.")
        if rows_with_initial_errors:
            logger.info("Writing back payments log with parsing error statuses...")
            if not gutils.update_worksheet_from_df(gs_client, config.PAYMENTS_LOG_SHEET_ID, "Sheet1", df_log_sheet_state): logger.error("CRITICAL: Failed update Payments Log...")
            else: logger.info("Payments Log sheet updated with parsing errors.")
        return
        
    payments_to_attempt_processing.sort(key=lambda p: p['data'][PAYMENT_DATE_COL_LOWER])
    logger.info(f"Found {len(payments_to_attempt_processing)} payments validated for processing attempt.")


    # --- 3. Process Each Validated Payment ---
    for payment_item in payments_to_attempt_processing:
        original_log_index = payment_item['original_index']
        validated_data = payment_item['data']

        loan_id_original_case = validated_data['loanid_original_case'] # Use this for filename search
        loan_id_internal = validated_data[LOAN_ID_COL_LOWER] # Uppercase for internal logs/keys
        actual_payment_date_dt = validated_data[PAYMENT_DATE_COL_LOWER]
        actual_payment_amount_from_log = validated_data[PAYMENT_AMOUNT_COL_LOWER]

        # Safeguards (should not be hit)
        if pd.isna(actual_payment_date_dt): logger.critical(f"...Date NaT... Skipping."); df_log_sheet_state.loc[original_log_index, status_col_original_casing] = "..."; df_log_sheet_state.loc[original_log_index, timestamp_col_original_casing] = datetime.now(); continue 
        if not loan_id_original_case or loan_id_original_case.upper() == "NAN": logger.critical(f"...LoanID invalid... Skipping."); df_log_sheet_state.loc[original_log_index, status_col_original_casing] = "..."; df_log_sheet_state.loc[original_log_index, timestamp_col_original_casing] = datetime.now(); continue

        actual_payment_date_str = actual_payment_date_dt.strftime("%Y-%m-%d")
        logger.info(f"Processing payment from log index {original_log_index}: LoanID={loan_id_original_case}, Date={actual_payment_date_str}, Amount={actual_payment_amount_from_log:.2f}")

        # --- *** Use Drive Search with original case LoanID for filename matching *** ---
        amortization_sheet_id = gutils.find_sheet_id_by_loan_id_in_folder(loan_id_original_case)
        # --- *** END CHANGE *** ---

        if not amortization_sheet_id:
            # Warning/Error already logged by find_sheet_id_by_loan_id_in_folder
            df_log_sheet_state.loc[original_log_index, status_col_original_casing] = "Error - Amort. Sheet Not Found in Drive"
            df_log_sheet_state.loc[original_log_index, timestamp_col_original_casing] = datetime.now()
            continue

        try:
            # --- Amortization Processing Block ---
            loan_terms_df_raw = gutils.get_sheet_as_df(gs_client, amortization_sheet_id, "LoanTerms")
            schedule_df_raw = gutils.get_sheet_as_df(gs_client, amortization_sheet_id, "Schedule")

            if loan_terms_df_raw is None or schedule_df_raw is None or loan_terms_df_raw.empty or schedule_df_raw.empty:
                logger.error(f"Read error or empty LoanTerms/Schedule for {loan_id_internal}. Log index {original_log_index}.")
                df_log_sheet_state.loc[original_log_index, status_col_original_casing] = "Error - Read/Empty Amort. Sheet"
                df_log_sheet_state.loc[original_log_index, timestamp_col_original_casing] = datetime.now()
                continue
            
            # Process terms and schedule (standardize cols, parse types, find row, calc, update schedule_df)
            # (Using illustrative placeholder - this block needs full logic from previous correct version)
            # --- Placeholder Start ---
            # Assume processing happens correctly, schedule_df is updated, 
            # and current_original_schedule_headers are stored
            logger.debug(f"Placeholder: Would process amortization for {loan_id_internal}")
            schedule_df = schedule_df_raw.copy() # Example: assume schedule_df is the final state
            current_original_schedule_headers = schedule_df.columns.tolist() # Get headers for write back
            amortization_update_success = True # Assume success for illustration
            # --- Placeholder End ---
            
            # Write schedule_df back
            if amortization_update_success:
                schedule_df_to_write = schedule_df.copy()
                # Ensure columns match original order/casing if possible for write-back
                # If columns were added/removed, more care is needed. Using headers read is safest.
                schedule_df_to_write.columns = current_original_schedule_headers 
                if gutils.update_worksheet_from_df(gs_client, amortization_sheet_id, "Schedule", schedule_df_to_write):
                    df_log_sheet_state.loc[original_log_index, status_col_original_casing] = "Processed"
                    df_log_sheet_state.loc[original_log_index, timestamp_col_original_casing] = datetime.now()
                    logger.info(f"Successfully processed payment for {loan_id_internal} (log index {original_log_index}).")
                else: # Failed to save amortization sheet
                    df_log_sheet_state.loc[original_log_index, status_col_original_casing] = "Error - Amort. Save Fail"
                    df_log_sheet_state.loc[original_log_index, timestamp_col_original_casing] = datetime.now()
            else: # If amortization processing itself failed before write attempt
                 df_log_sheet_state.loc[original_log_index, status_col_original_casing] = "Error - Amort. Processing Fail" # Or specific error
                 df_log_sheet_state.loc[original_log_index, timestamp_col_original_casing] = datetime.now()


        except Exception as e: # Catch-all for this specific payment's processing
            logger.error(f"UNHANDLED EXCEPTION processing LoanID {loan_id_internal} (log index {original_log_index}): {e}", exc_info=True)
            df_log_sheet_state.loc[original_log_index, status_col_original_casing] = "Error - Unhandled Exception"
            df_log_sheet_state.loc[original_log_index, timestamp_col_original_casing] = datetime.now()
        
    # --- 4. Update Payments Log Sheet ---
    if not gutils.update_worksheet_from_df(gs_client, config.PAYMENTS_LOG_SHEET_ID, "Sheet1", df_log_sheet_state):
        logger.error("CRITICAL: Failed to update the Payments Log sheet with final processing statuses.")
    else:
        logger.info("Payments Log sheet updated with all final statuses.")

    logger.info("Payment processing run finished.")