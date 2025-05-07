# src/payment_processor.py
import pandas as pd
from, although primary cleaning happens in processor)

---

**File 1: `src/payment_processor.py` datetime import datetime
import logging
from decimal import Decimal, InvalidOperation # Import Decimal and specific error
from . import config
from (Complete Code)**

We will modify the sections where strings read from the sheets are converted to numbers (`pd.to_ . import gutils
from .amortization_calculator import calculate_principal_and_status 
from collections importnumeric`) to first remove commas.

```python
# src/payment_processor.py
import pandas as pd
from defaultdict

logger = logging.getLogger(__name__)

# Helper function to safely clean and convert string to float, handling commas
def safe_string_to_float(value_str, context=""):
    if pd.isna(value_str) datetime import datetime
import logging
from decimal import Decimal, InvalidOperation # Import Decimal and potential error
from . import config
from . import gutils
from .amortization_calculator import calculate_principal_and_status 
from collections import or str(value_str).strip() == "":
        logger.debug(f"Value is empty/NA defaultdict

logger = logging.getLogger(__name__)

# Helper function to clean and convert currency strings
def parse_currency_ for {context}. Returning NaN.")
        return pd.NA # Return Pandas NA for missing numeric
    try:string(value_str):
    if pd.isna(value_str) or str(value_str).strip()
        # Remove commas, then convert to float
        cleaned_str = str(value_str).replace(',', ''). == "":
        return pd.NA # Return Pandas NA for missing/empty
    try:
        # Removestrip()
        # Handle potential parentheses for negative numbers if needed, e.g. (1,234.5 common currency symbols and commas, then convert to float
        cleaned_str = str(value_str).replace('$', '').6)
        if cleaned_str.startswith('(') and cleaned_str.endswith(')'):
             cleaned_replace(',', '').strip()
        return float(cleaned_str)
    except ValueError:
        # If conversionstr = '-' + cleaned_str[1:-1]
        return float(cleaned_str)
    except ( fails after cleaning, return NA
        return pd.NA

def process_payments():
    logger.info("Starting paymentValueError, TypeError):
        logger.warning(f"Could not convert '{value_str}' to float for { processing (using pre-filled interest)...")
    gs_client = None
    try: gs_client = gutils.get_gspread_client()
    except ConnectionError as e: logger.error(f"context}. Returning NaN.")
        return pd.NA # Return Pandas NA on conversion error

# Helper function to safely clean and convert string to Decimal
def safe_string_to_decimal(value_str, context=""):
    if pdCRITICAL: No GS client: {e}. Aborting."); return
    try: gutils.get_drive_service() 
    except ConnectionError as e: logger.warning(f"Could not init Drive client: {e}.").isna(value_str) or str(value_str).strip() == "":
        logger.debug(f"Value

    # --- 1. Read Payments Log ---
    # Read as strings first for consistent cleaning
    df is empty/NA for {context}. Returning Decimal('NaN').")
        return Decimal('NaN') # Decimal NA_log_sheet_state = gutils.get_sheet_as_df(gs_client, config. representation
    try:
        cleaned_str = str(value_str).replace(',', '').strip()
        PAYMENTS_LOG_SHEET_ID, "Sheet1") 
    
    if df_log_sheet_# Handle potential parentheses for negative numbers
        if cleaned_str.startswith('(') and cleaned_str.endswith(')'state is None or df_log_sheet_state.empty: logger.info("Payments log empty/unreadable."); return

    original_log_headers = df_log_sheet_state.columns.tolist()
    header_map):
             cleaned_str = '-' + cleaned_str[1:-1]
        # Create Decimal, quant = {str(h).strip().lower(): h for h in original_log_headers}

    LOANize later if needed in calculation
        return Decimal(cleaned_str)
    except (TypeError, InvalidOperation):_ID_COL_LOWER = 'loanid'; PAYMENT_DATE_COL_LOWER = 'paymentdate
        logger.warning(f"Could not convert '{value_str}' to Decimal for {context}. Returning Decimal('NaN').'; PAYMENT_AMOUNT_COL_LOWER = 'paymentamount';
    PROCESSED_STATUS_COL_")
        return Decimal('NaN')


def process_payments():
    logger.info("Starting payment processing (LOWER = 'processedstatus'; PROCESSED_TIMESTAMP_COL_LOWER = 'processedtimestamp';

    handling commas, using pre-filled interest)...")
    gs_client = None
    try: gs_client = gutils.get_gspread_client()
    except ConnectionError as e: logger.error(fstatus_col_original_casing = header_map.get(PROCESSED_STATUS_COL_LOWER, PROCESSED_STATUS_COL_LOWER)
    timestamp_col_original_casing = header_map.get(PROCESSED_TIMESTAMP_COL_LOWER, PROCESSED_TIMESTAMP_COL"CRITICAL: No GS client: {e}. Aborting."); return
    try: gutils.get__LOWER)

    if status_col_original_casing not in df_log_sheet_statedrive_service() 
    except ConnectionError as e: logger.warning(f"Could not init Drive client.columns: df_log_sheet_state[status_col_original_casing] = ''
    : {e}.")

    # --- 1. Read Payments Log ---
    # Read as strings initially using gif timestamp_col_original_casing not in df_log_sheet_state.columns: df_logutils
    df_log_sheet_state = gutils.get_sheet_as_df(gs_client,_sheet_state[timestamp_col_original_casing] = pd.NaT

    # ---  config.PAYMENTS_LOG_SHEET_ID, "Sheet1")
    if df_log_sheet2. Identify and Validate Pending Payments ---
    validated_payment_list = [] 
    rows_with_initial__state is None or df_log_sheet_state.empty: logger.info("Payments log empty/unerrors = False

    for index, raw_row_series in df_log_sheet_state.iterrows():readable."); return

    original_log_headers = df_log_sheet_state.columns.tolist()

        current_original_status = str(raw_row_series.get(status_col_original_casing,    header_map = {str(h).strip().lower(): h for h in original_log_headers}

    LOAN_ID_COL_LOWER = 'loanid'; PAYMENT_DATE_COL_LOWER '')).strip().lower()
        if current_original_status.startswith('processed') or current_original_ = 'paymentdate'; PAYMENT_AMOUNT_COL_LOWER = 'paymentamount';
    PROCESSED_status.startswith('error'): continue 

        has_critical_error = False; validated_data = {}; loanSTATUS_COL_LOWER = 'processedstatus'; PROCESSED_TIMESTAMP_COL_LOWER = 'processed_id_val = ''
        
        # --- Validate LoanID (as before) ---
        loan_id_header_original = header_map.get(LOAN_ID_COL_LOWER)
        timestamp';

    status_col_original_casing = header_map.get(PROCESSED_STATUSif not loan_id_header_original: df_log_sheet_state.loc[index, status__COL_LOWER, PROCESSED_STATUS_COL_LOWER)
    timestamp_col_original_casing = header_map.get(PROCESSED_TIMESTAMP_COL_LOWER, PROCESSEDcol_original_casing] = "Error - Missing LoanID Column"; has_critical_error = True
        else:
            try: 
                raw_loan_id = str(raw_row_series._TIMESTAMP_COL_LOWER)

    if status_col_original_casing not in df_logget(loan_id_header_original, '')).strip(); loan_id_val = raw_loan__sheet_state.columns: df_log_sheet_state[status_col_original_casing]id.upper()
                if not raw_loan_id or loan_id_val == "NAN": raise = ''
    if timestamp_col_original_casing not in df_log_sheet_state.columns: df_log_sheet_state[timestamp_col_original_casing] = pd.NaT


 ValueError("LoanID missing/NAN")
                validated_data['loanid_original_case'] = raw_loan_id; validated_data[LOAN_ID_COL_LOWER] = loan_id_val
                # --- 2. Identify and Validate Pending Payments ---
    payments_to_attempt_processing = [] except Exception as e: df_log_sheet_state.loc[index, status_col_original_c
    rows_with_initial_errors = False

    for index, raw_row_series in df_asing] = "Error - Invalid/Missing LoanID"; has_critical_error = True; logger.warning(log_sheet_state.iterrows():
        current_original_status = str(raw_row_series.f"Log idx {index}: LoanID validation error: {e}")

        # --- Validate PaymentDate (as before) ---get(status_col_original_casing, '')).strip().lower()
        if current_original_status.startswith('processed') or current_original_status.startswith('error'): continue 

        has_critical
        payment_date_header_original = header_map.get(PAYMENT_DATE_COL_L_error = False
        validated_data = {}
        loan_id_val = '' # Use for loggingOWER); parsed_date = pd.NaT
        if not has_critical_error:
            if not payment_date_header_original: df_log_sheet_state.loc[index, status_col_ context

        # --- Validate LoanID ---
        loan_id_header_original = header_map.get(original_casing] = "Error - Missing PaymentDate Column"; has_critical_error = True
            elseLOAN_ID_COL_LOWER)
        if not loan_id_header_original: df_log_sheet:
                raw_payment_date = str(raw_row_series.get(payment_date_header_state.loc[index, status_col_original_casing] = "Error - Missing LoanID Column_original, '')).strip()
                if not raw_payment_date: df_log_sheet_state"; has_critical_error = True
        else:
            try: 
                raw_loan_id.loc[index, status_col_original_casing] = "Error - Missing PaymentDate"; has_ = str(raw_row_series.get(loan_id_header_original, '')).strip()
                loan_critical_error = True
                else:
                    try: parsed_date = pd.to_datetime(rawid_val = raw_loan_id.upper() 
                if not raw_loan_id or loan_payment_date, format='%Y-%m-%d', errors='raise')
                    except (ValueError, TypeError_id_val == "NAN": raise ValueError("LoanID missing/NAN")
                validated_data['loanid):
                        try: parsed_date = pd.to_datetime(raw_payment_date, errors='raise_original_case'] = raw_loan_id; validated_data[LOAN_ID_COL_L'); logger.warning(f"Log index {index}: Date '{raw_payment_date}' not YYYY-OWER] = loan_id_val
            except Exception as e: df_log_sheet_state.locMM-DD...")
                        except (ValueError, TypeError): df_log_sheet_state.loc[index,[index, status_col_original_casing] = "Error - Invalid/Missing LoanID"; has_ status_col_original_casing] = "Error - Invalid PaymentDate"; has_critical_error = Truecritical_error = True; logger.warning(f"Log idx {index}: LoanID validation error: {e}")


            validated_data[PAYMENT_DATE_COL_LOWER] = parsed_date

        # ---        # --- Validate PaymentDate ---
        payment_date_header_original = header_map.get(PAY Validate PaymentAmount (Use helper function) ---
        payment_amount_header_original = header_map.get(PAYMENT_DATE_COL_LOWER); parsed_date = pd.NaT
        if not has_critical_error:
            if not payment_date_header_original: df_log_sheet_state.loc[MENT_AMOUNT_COL_LOWER); parsed_amount = pd.NA 
        if not has_critical_index, status_col_original_casing] = "Error - Missing PaymentDate Column"; has_critical_error =error:
            if not payment_amount_header_original:
                df_log_sheet_state.loc[index, status_col_original_casing] = "Error - Missing PaymentAmount Column"; has_critical_error True
            else:
                raw_payment_date = str(raw_row_series.get(payment = True
            else:
                 raw_payment_amount = raw_row_series.get(payment_amount_header_date_header_original, '')).strip()
                if not raw_payment_date: df_log_original) # Get raw value
                 parsed_amount = parse_currency_string(raw_payment_amount)_sheet_state.loc[index, status_col_original_casing] = "Error - Missing PaymentDate"; has_critical_error = True
                else:
                    try: parsed_date = pd.to # Clean and parse
                 if pd.isna(parsed_amount): # Check if helper returned NA
                     logger_datetime(raw_payment_date, format='%Y-%m-%d', errors='raise')
                    except.warning(f"Log index {index}, LoanID '{loan_id_val}': PaymentAmount '{raw_ (ValueError, TypeError):
                        try: parsed_date = pd.to_datetime(raw_payment_datepayment_amount}' invalid. Marking as error.")
                     df_log_sheet_state.loc[index, status_col, errors='raise'); logger.warning(f"Log index {index}: Date '{raw_payment_date}'_original_casing] = "Error - Invalid PaymentAmount in Log"
                     has_critical_error = not YYYY-MM-DD...")
                        except (ValueError, TypeError): df_log_sheet_state True
                 elif parsed_amount <= 0: # Check positivity after successful parse
                     logger.warning(f.loc[index, status_col_original_casing] = "Error - Invalid PaymentDate"; has_critical_error = True
            validated_data[PAYMENT_DATE_COL_LOWER] = parsed_"Log index {index}, LoanID '{loan_id_val}': PaymentAmount '{parsed_amount}' not positive. Marking as error.")
                     df_log_sheet_state.loc[index, status_col_date

        # --- Validate PaymentAmount (Using safe_string_to_float) ---
        payment_amount_headeroriginal_casing] = "Error - NonPositive PaymentAmount"
                     has_critical_error = True
                     parsed_original = header_map.get(PAYMENT_AMOUNT_COL_LOWER); parsed_amount = pd_amount = pd.NA # Treat as invalid if not positive
            validated_data[PAYMENT_AMOUNT_.NA 
        if not has_critical_error:
            if not payment_amount_header_original: df_log_sheet_state.loc[index, status_col_original_casing] = "Error -COL_LOWER] = parsed_amount # Store the float or pd.NA
        
        # --- Finalize row validation Missing PaymentAmount Column"; has_critical_error = True
            else:
                raw_payment_amount = raw ---
        if has_critical_error:
            df_log_sheet_state.loc[index, timestamp_row_series.get(payment_amount_header_original) # Get raw value
                # Use helper_col_original_casing] = datetime.now(); rows_with_initial_errors = True
        else:
             if pd.notna(validated_data.get('loanid_original_case')) and \ function to clean (remove commas) and convert to float
                parsed_amount = safe_string_to_float(raw_
                validated_data.get('loanid_original_case','').upper() != "NAN" and \payment_amount, context=f"Log index {index}, LoanID {loan_id_val}")
                

                pd.notna(validated_data.get(PAYMENT_DATE_COL_LOWER)) and \
                pd.notna(validated_data.get(PAYMENT_AMOUNT_COL_LOWER)):                if pd.isna(parsed_amount): # Check if helper returned NA (error)
                    df_log_sheet_state.loc[index, status_col_original_casing] = "Error - Invalid PaymentAmount in # Check if amount is not NA
                 validated_payment_list.append({'original_index': index, 'data': Log"
                    has_critical_error = True
                elif parsed_amount <= 0: # Check positivity after validated_data})
             else: 
                  if not str(df_log_sheet_state.loc[index, status_col_original_casing]).lower().startswith("error"):
                      df_log_ successful conversion
                    logger.warning(f"Log index {index}, LoanID '{loan_id_val}': PaymentAmount {parsed_amount} not positive. Marking as error.")
                    df_log_sheet_state.loc[indexsheet_state.loc[index, status_col_original_casing] = "Error - Invalid Parsed, status_col_original_casing] = "Error - NonPositive PaymentAmount"
                    has_critical_error = Data"; df_log_sheet_state.loc[index, timestamp_col_original_casing] = datetime.now(); rows_with_initial_errors = True

    # --- Handle case where no valid payments remain True
                    parsed_amount = pd.NA # Treat as invalid if not positive
            validated_data[PAY ---
    if not validated_payment_list:
        logger.info("No valid payments found to attempt processingMENT_AMOUNT_COL_LOWER] = parsed_amount
        
        # --- Finalize row validation ---
        if has_critical_error:
            df_log_sheet_state.loc[index, timestamp after validation.")
        if rows_with_initial_errors: 
            logger.info("Writing back payments log with parsing error statuses...")
            if not gutils.update_worksheet_from_df(gs__col_original_casing] = datetime.now(); rows_with_initial_errors = True
        elseclient, config.PAYMENTS_LOG_SHEET_ID, "Sheet1", df_log_sheet_state): logger.error("CRITICAL: Failed update Payments Log...")
            else: logger.info("Payments Log sheet updated with:
             # Check final parsed values before adding
             if pd.notna(validated_data.get('loanid_original_case')) and \
                validated_data.get('loanid_original_case','').upper() != "NAN" and \
                pd.notna(validated_data.get(PAYMENT_ parsing errors.")
        return
        
    # --- Group Validated Payments by LoanID and Sort ---
    validated_DATE_COL_LOWER)) and \
                pd.notna(validated_data.get(PAYMENTpayment_list.sort(key=lambda p: (p['data'][LOAN_ID_COL_L_AMOUNT_COL_LOWER)):
                 payments_to_attempt_processing.append({'original_index': index,OWER], p['data'][PAYMENT_DATE_COL_LOWER])) 
    grouped_payments = defaultdict 'data': validated_data})
             else: 
                  if not str(df_log_sheet_state.loc(list)
    for payment_item in validated_payment_list: grouped_payments[payment_item['data'][LOAN_ID_COL_LOWER]].append(payment_item) 
    logger.info(f"[index, status_col_original_casing]).lower().startswith("error"):
                      df_log_sheet_state.loc[index, status_col_original_casing] = "Error - Invalid ParsedProcessing {len(validated_payment_list)} validated payments across {len(grouped_payments)} unique LoanIDs.") Data"; df_log_sheet_state.loc[index, timestamp_col_original_casing] =

    # --- 3. Process Payments Loan by Loan ---
    for loan_id_internal, payment_ datetime.now(); rows_with_initial_errors = True


    if not payments_to_attempt_processing:
items_for_loan in grouped_payments.items():
        loan_id_original_case = payment_items_for_loan[0]['data']['loanid_original_case']
        logger.info(f        logger.info("No valid payments found to attempt processing after validation.")
        if rows_with_initial_"--- Processing {len(payment_items_for_loan)} payment(s) for LoanID: {loanerrors: 
            logger.info("Writing back payments log with parsing error statuses...")
            if not gutils.update_worksheet_from_df(gs_client, config.PAYMENTS_LOG_SHEET__id_original_case} ---")
        
        amortization_sheet_id = gutils.findID, "Sheet1", df_log_sheet_state): logger.error("CRITICAL: Failed update Payments_sheet_id_by_loan_id_in_folder(loan_id_original_case)
        if not amortization_sheet_id:
            logger.error(f"Amort. Sheet ID for '{ Log...")
            else: logger.info("Payments Log sheet updated with parsing errors.")
        return
        
    payments_to_attempt_processing.sort(key=lambda p: (p['data'][LOAN_IDloan_id_original_case}' not found. Marking payments as error.")
            for item in payment_items_for_loan: df_log_sheet_state.loc[item['original_index'], status_col_COL_LOWER], p['data'][PAYMENT_DATE_COL_LOWER])) 
    grouped_original_casing] = "Error - Amort. Sheet Not Found"; df_log_sheet_state_payments = defaultdict(list)
    for payment_item in validated_payment_list: grouped_payments[payment_item.loc[item['original_index'], timestamp_col_original_casing] = datetime.now()
['data'][LOAN_ID_COL_LOWER]].append(payment_item) 
    logger.info(            continue 

        schedule_df = None 
        loan_processing_failed_early = False
        f"Processing {len(validated_payment_list)} validated payments across {len(grouped_payments)} unique LoanIDs.")

current_original_schedule_headers = [] 

        try: # Read sheet data and terms ONCE per loan
    # --- 3. Process Payments Loan by Loan ---
    for loan_id_internal, payment_items            logger.debug(f"Reading amortization data for {loan_id_internal}")
            loan_terms__for_loan in grouped_payments.items():
        loan_id_original_case = payment_itemsdf_raw = gutils.get_sheet_as_df(gs_client, amortization_sheet_id_for_loan[0]['data']['loanid_original_case']
        logger.info(f", "LoanTerms")
            schedule_df_raw = gutils.get_sheet_as_df(--- Processing {len(payment_items_for_loan)} payment(s) for LoanID: {loan_id_original_case} ---")
        
        amortization_sheet_id = gutils.find_gs_client, amortization_sheet_id, "Schedule") # Reads as strings mostly
            if loan_terms_dfsheet_id_by_loan_id_in_folder(loan_id_original_case)
        _raw is None or schedule_df_raw is None or schedule_df_raw.empty: raise ValueError("LoanTermsif not amortization_sheet_id:
            logger.error(f"Amort. Sheet ID for '{loan_id_ or Schedule sheet empty/unreadable.")

            # Parse Loan Terms minimally
            grace_period_days = configoriginal_case}' not found. Marking payments as error.")
            for item in payment_items_for_loan.DEFAULT_GRACE_PERIOD_DAYS
            flat_late_fee = Decimal('25.00')
: df_log_sheet_state.loc[item['original_index'], status_col_original_casing] = "Error - Amort. Sheet Not Found"; df_log_sheet_state.loc[item            if not loan_terms_df_raw.empty:
                loan_terms_df = loan_terms_df_raw.copy(); loan_terms_df.columns = [str(col).strip().lower()['original_index'], timestamp_col_original_casing] = datetime.now()
            continue 

 for col in loan_terms_df.columns]
                if 'parameter' in loan_terms_df.        schedule_df = None 
        loan_processing_failed_early = False
        current_original_columns and 'value' in loan_terms_df.columns:
                    loan_terms_s = loan_terms_df.set_index('parameter')['value'].astype(str).str.strip()
                    try:schedule_headers = [] 
        grace_period_days = config.DEFAULT_GRACE_PERIOD_DAYS # Initialize with defaults
        flat_late_fee = Decimal('25.00')

        try: # grace_period_days = int(loan_terms_s.get("graceperioddays", config.DEFAULT_ Read sheet data and terms ONCE per loan
            logger.debug(f"Reading amortization data for {loan_id_GRACE_PERIOD_DAYS))
                    except (ValueError, TypeError): pass
                    try: flat_late_fee = Decimal(loan_terms_s.get("flatlatefee", '25.00')).quantinternal}")
            loan_terms_df_raw = gutils.get_sheet_as_df(gs_client, amortization_sheet_id, "LoanTerms")
            schedule_df_raw = gutils.ize(Decimal('0.01'))
                    except (ValueError, TypeError, InvalidOperation): pass
                else: logger.warning(f"LoanTerms sheet for {loan_id_internal} missing parameter/value columns.")

            #get_sheet_as_df(gs_client, amortization_sheet_id, "Schedule")
            if schedule Prepare schedule_df
            schedule_df = schedule_df_raw.copy()
            current_original_schedule_headers_df_raw is None or schedule_df_raw.empty: raise ValueError("Schedule sheet empty or unreadable.") = schedule_df.columns.tolist() 
            schedule_df.columns = [str(col).strip().lower

            # Parse Loan Terms minimally for grace period/fee
            if loan_terms_df_raw is not() for col in schedule_df.columns] 

            # Define expected internal lowercase column names
            DUE_ None and not loan_terms_df_raw.empty:
                loan_terms_df = loan_terms_df_DATE_COL_SCHED = 'duedate'; BEGIN_BAL_COL_SCHED = 'beginningbalance';raw.copy(); loan_terms_df.columns = [str(col).strip().lower() for col in SCHED_PMT_COL_SCHED = 'scheduledpayment'; # Sched Pmt might be needed for status loan_terms_df.columns]
                if 'parameter' in loan_terms_df.columns and 'value' in loan_terms_df.columns:
                    loan_terms_s = loan_terms_df logic
            ACTUAL_PMT_DATE_COL_SCHED = 'actualpaymentdate'; ACTUAL_PMT.set_index('parameter')['value'].astype(str).str.strip()
                    try: grace_period_AMT_COL_SCHED = 'actualpaymentamount';
            INTEREST_PAID_COL_SCHED = 'interestpaid'; PRINCIPAL_PAID_COL_SCHED = 'principalpaid';
            L_days = int(loan_terms_s.get("graceperioddays", config.DEFAULT_GRACE_ATE_FEE_COL_SCHED = 'latefee'; CREDIT_APPLIED_COL_SCHED =PERIOD_DAYS))
                    except (ValueError, TypeError): logger.warning(f"Using default grace days for {loan 'creditapplied'; 
            ENDING_BAL_COL_SCHED = 'endingbalance'; STATUS_COL_SCH_id_internal}. Invalid value in terms.")
                    try: flat_late_fee = safe_string_to_decimal(loan_terms_s.get("flatlatefee", '25.00'), context="ED = 'status';

            # Parse schedule columns strictly HERE, AFTER reading, using helper where needed
            schedule_df[DUE_DATE_COL_SCHED] = pd.to_datetime(schedule_df.FlatLateFee").quantize(Decimal('0.01'))
                    except (ValueError, TypeError, InvalidOperation): loggerget(DUE_DATE_COL_SCHED), format='%Y-%m-%d', errors='coerce')
            schedule.warning(f"Using default flat late fee for {loan_id_internal}. Invalid value in terms.")
_df[ACTUAL_PMT_DATE_COL_SCHED] = pd.to_datetime(schedule                else: logger.warning(f"LoanTerms sheet for {loan_id_internal} missing parameter/value columns.")_df.get(ACTUAL_PMT_DATE_COL_SCHED), format='%Y-%m-%

            # Prepare schedule_df
            schedule_df = schedule_df_raw.copy()
            current_original_schedule_headers = schedule_df.columns.tolist() 
            schedule_df.columns = [str(cold', errors='coerce')
            
            # Columns to parse as currency/float (handle commas, $)
            currency_cols_schedule = [BEGIN_BAL_COL_SCHED, SCHED_PMT_COL_SCHED, ACTUAL).strip().lower() for col in schedule_df.columns] 

            # Define expected columns
            DUE_PMT_AMT_COL_SCHED, 
                                      INTEREST_PAID_COL_SCHED, PRINC_DATE_COL_SCHED = 'duedate'; BEGIN_BAL_COL_SCHED = 'beginningbalance'; 
            ACTUAL_PMT_DATE_COL_SCHED = 'actualpaymentdate'; ACTUAL_IPAL_PAID_COL_SCHED, LATE_FEE_COL_SCHED, 
                               PMT_AMT_COL_SCHED = 'actualpaymentamount';
            INTEREST_PAID_COL       CREDIT_APPLIED_COL_SCHED, ENDING_BAL_COL_SCHED]
            _SCHED = 'interestpaid'; PRINCIPAL_PAID_COL_SCHED = 'principalpaid';
for col in currency_cols_schedule:
                if col in schedule_df.columns:
                    # Apply            LATE_FEE_COL_SCHED = 'latefee'; ENDING_BAL_COL_SCHED the helper function to clean and convert the column
                    schedule_df[col] = schedule_df[col].apply( = 'endingbalance'; STATUS_COL_SCHED = 'status';

            required_schedule_cols = [DUE_DATE_COL_SCHED, BEGIN_BAL_COL_SCHED, INTEREST_PAID_parse_currency_string) 
                    # Check if any NaNs resulted from parsing errors *after* applying
                    if schedule_df[col].isna().any():
                         logger.warning(f"Column '{col}' in schedule forCOL_SCHED, ACTUAL_PMT_DATE_COL_SCHED, ACTUAL_PMT_AMT_COL_SCHED, PRINCIPAL_PAID_COL_SCHED, LATE_FEE_COL_SCHED {loan_id_internal} contains values that could not be parsed as currency.")
                         # Depending on column importance, ENDING_BAL_COL_SCHED, STATUS_COL_SCHED]
            missing_cols = [col for col in required_schedule_cols if col not in schedule_df.columns]
            if missing, could raise ValueError here
                else: # Add column if missing, initialize with NA
                     schedule_df[col] =_cols: raise ValueError(f"Schedule sheet missing required columns: {missing_cols}")

            # Parse schedule types pd.NA 
                     schedule_df[col] = pd.to_numeric(schedule_df[col], errors, using safe_string_to_float for numerics
            schedule_df[DUE_DATE_COL_SCHED='coerce') # Ensure numeric type even if all NA

            if STATUS_COL_SCHED not in schedule_df.columns] = pd.to_datetime(schedule_df.get(DUE_DATE_COL_SCHED),: schedule_df[STATUS_COL_SCHED] = "Due"


        except Exception as loan_read_error format='%Y-%m-%d', errors='coerce')
            schedule_df[ACTUAL_PMT_DATE_COL_SCHED] = pd.to_datetime(schedule_df.get(ACTUAL_PM: # Catch errors reading/parsing sheet/terms
            logger.error(f"Error preparing amortization data for LoanT_DATE_COL_SCHED), format='%Y-%m-%d', errors='coerce')
            
ID {loan_id_internal}: {loan_read_error}", exc_info=True)
            loan_processing            numeric_schedule_cols = [BEGIN_BAL_COL_SCHED, INTEREST_PAID_COL__failed_early = True
            for item in payment_items_for_loan: 
                 df_log_sheet_state.loc[item['original_index'], status_col_original_casing] =SCHED, # Read these first
                                     ACTUAL_PMT_AMT_COL_SCHED, PRINCIPAL_PA f"Error - Amort. Read/Init Fail"; df_log_sheet_state.loc[item['ID_COL_SCHED, # To be updated
                                     LATE_FEE_COL_SCHED, ENDoriginal_index'], timestamp_col_original_casing] = datetime.now()
            continue # To next LoanID

ING_BAL_COL_SCHED]         # To be updated
            for col in numeric_schedule_cols        # --- Apply Payments to In-Memory Schedule ---
        loan_processing_succeeded_fully = True 
        if not loan_processing_failed_early and schedule_df is not None:
            for payment_:
                # Apply the safe converter to handle commas etc., then convert resulting object column back if needed
                 schedule_df[item in payment_items_for_loan:
                original_log_index = payment_item['original_col] = schedule_df[col].apply(lambda x: safe_string_to_float(x, contextindex']
                validated_data = payment_item['data']
                actual_payment_date_dt = validated_data[PAYMENT_DATE_COL_LOWER]
                actual_payment_amount_from_log = validated_data[PAYMENT_AMOUNT_COL_LOWER] # float
                actual_payment_=f"Schedule Col {col}"))
                 # Now coerce to numeric again, NAs remain NA
                 schedule_date_str = actual_payment_date_dt.strftime("%Y-%m-%d")

                logger.df[col] = pd.to_numeric(schedule_df[col], errors='coerce') 

            if STATUS_COL_SCHED not in schedule_df.columns: schedule_df[STATUS_COL_SCHED]debug(f"Applying pmt log idx {original_log_index} ({actual_payment_date_str}, Amt: {actual_payment_amount_from_log:.2f}) to {loan_id_internal}") = "Due"

        except Exception as loan_read_error:
            logger.error(f"Error preparing amortization data for LoanID {loan_id_internal}: {loan_read_error}", exc_info=True)

                try: # Inner try-except for applying one payment
                    target_row_idx = -1

            loan_processing_failed_early = True
            for item in payment_items_for_loan:                    for i, sr_iter in schedule_df.iterrows():
                        cs = str(sr_iter.get(STATUS_COL_SCHED, "Due")).strip().lower(); apds = sr_iter.get 
                 df_log_sheet_state.loc[item['original_index'], status_col_original_casing] = f"Error - Amort. Read/Init Fail"; df_log_sheet_state(ACTUAL_PMT_DATE_COL_SCHED)
                        if pd.isna(apds).loc[item['original_index'], timestamp_col_original_casing] = datetime.now()
 or cs in ["due", "partially paid", ""]: target_row_idx = i; break
                    if target_row_idx == -1: raise ValueError("No Due Payment Slot found")

                    # Extract data needed            continue # To next LoanID

        # --- Apply Payments to In-Memory Schedule ---
        loan_processing for calculation from target row
                    due_date_dt_sched = schedule_df.loc[target_row_succeeded_fully = True 
        if not loan_processing_failed_early and schedule_df is_idx, DUE_DATE_COL_SCHED]
                    beginning_balance_for_calc = schedule_ not None:
            for payment_item in payment_items_for_loan:
                original_log_df.loc[target_row_idx, BEGIN_BAL_COL_SCHED]
                    interest_paidindex = payment_item['original_index']
                validated_data = payment_item['data']
                _prefilled = schedule_df.loc[target_row_idx, INTEREST_PAID_COL_SCHactual_payment_date_dt = validated_data[PAYMENT_DATE_COL_LOWER]
                actual_payment_amount_from_log = validated_data[PAYMENT_AMOUNT_COL_LOWER]ED] # Read pre-filled interest
                    
                    # *** Validate extracted values needed for calculation ***
                    if pd. # float
                actual_payment_date_str = actual_payment_date_dt.strftime("%Y-%isna(due_date_dt_sched): raise ValueError("Invalid DueDate in target schedule row")
                    if pd.isna(beginning_balance_for_calc): raise ValueError("Invalid BeginBal in target schedule row") # THIS WASm-%d")

                logger.debug(f"Applying pmt log idx {original_log_index} ({ THE ERROR POINT
                    if pd.isna(interest_paid_prefilled): raise ValueError("Invalid/Missing PREactual_payment_date_str}, Amt: {actual_payment_amount_from_log:.2f}) to {loan_id_internal}")

                try: 
                    target_row_idx = -1
                    for i, sr_iter in schedule_df.iterrows():
                        cs = str(sr_iter.-FILLED InterestPaid in target schedule row")
                        
                    due_date_str_sched = due_date_dtget(STATUS_COL_SCHED, "Due")).strip().lower(); apds = sr_iter.get(_sched.strftime("%Y-%m-%d")

                    # Call calculation function (expects floats, strings, int, Decimal)
                    payment_calcs = calculate_principal_and_status(
                        beginning_balance_floatACTUAL_PMT_DATE_COL_SCHED)
                        if pd.isna(apds) or cs in ["=float(beginning_balance_for_calc), 
                        interest_paid_prefilled_float=floatdue", "partially paid", ""]: target_row_idx = i; break
                    if target_row(interest_paid_prefilled), 
                        actual_payment_amount_float=actual_payment_amount_idx == -1: raise ValueError("No Due Payment Slot found in schedule")

                    due_date_dt_from_log, 
                        due_date_str=due_date_str_sched, 
                        actual_sched = schedule_df.loc[target_row_idx, DUE_DATE_COL_SCHED]
                    beginning_balance_for_calc = schedule_df.loc[target_row_idx, BEGIN__payment_date_str=actual_payment_date_str,
                        grace_period_days=grace_period_days, 
                        late_fee_amount_flat=flat_late_fee # Pass Decimal feeBAL_COL_SCHED]
                    interest_paid_prefilled = schedule_df.loc[target_
                    )

                    if payment_calcs is None: raise ValueError("Calculation function returned None.")

                    # ---row_idx, INTEREST_PAID_COL_SCHED] 
                    
                    if pd.isna(due_date Update ONLY the specified columns in schedule_df ---
                    schedule_df.loc[target_row_idx,_dt_sched): raise ValueError("Invalid DueDate in target schedule row")
                    if pd.isna(beginning_ ACTUAL_PMT_DATE_COL_SCHED] = actual_payment_date_dt
                    schedule_balance_for_calc): raise ValueError("Invalid BeginBal in target schedule row") # This was the error source
                    if pddf.loc[target_row_idx, ACTUAL_PMT_AMT_COL_SCHED] = actual.isna(interest_paid_prefilled): raise ValueError("Invalid/Missing PRE-FILLED InterestPaid in target schedule row_payment_amount_from_log
                    schedule_df.loc[target_row_idx, PRINCIPAL_PAID_COL_SCHED] = float(payment_calcs["PrincipalPaid"])
                    schedule_")
                        
                    due_date_str_sched = due_date_dt_sched.strftime("%Y-%m-%d")

                    # Call calculation function (expects floats, strings, int)
                    payment_calcs = calculate_df.loc[target_row_idx, LATE_FEE_COL_SCHED] = float(payment_calcs["LateFee"])
                    schedule_df.loc[target_row_idx, STATUS_principal_and_status(
                        beginning_balance_float=float(beginning_balance_for_calc), 
                        interest_paid_prefilled_float=float(interest_paid_prefilled), 
                        COL_SCHED] = payment_calcs["Status"]
                    # ENDING_BAL_COL_SCHEDactual_payment_amount_float=actual_payment_amount_from_log, 
                        due_date_str= is also calculated and needs update
                    schedule_df.loc[target_row_idx, ENDING_BAL_COLdue_date_str_sched, 
                        actual_payment_date_str=actual_payment_date_SCHED] = float(payment_calcs["EndingBalance"])
                    # DO NOT update InterestPaid or BeginningBalance_str,
                        grace_period_days=grace_period_days, 
                        late_fee_amount_ for this row (target_row_idx)

                    # Update NEXT row's beginning balance 
                    next_flat=flat_late_fee 
                    )

                    if payment_calcs is None: raise ValueError("row_idx = target_row_idx + 1
                    if next_row_idx < len(scheduleCalculation function returned None.")

                    # Update specific columns in schedule_df (in memory)
                    schedule_df._df):
                        is_next_row_paid = pd.notna(schedule_df.loc[loc[target_row_idx, ACTUAL_PMT_DATE_COL_SCHED] = actual_paymentnext_row_idx, ACTUAL_PMT_DATE_COL_SCHED])
                        if not is_next_row_paid and BEGIN_BAL_COL_SCHED in schedule_df.columns:
                             schedule_df._date_dt 
                    schedule_df.loc[target_row_idx, ACTUAL_PMT_AMTloc[next_row_idx, BEGIN_BAL_COL_SCHED] = float(payment_calcs["EndingBalance_COL_SCHED] = actual_payment_amount_from_log 
                    schedule_df.loc[target_row_idx, PRINCIPAL_PAID_COL_SCHED] = float(payment_calcs"])
                    
                    df_log_sheet_state.loc[original_log_index, status_col_original_casing] = "Processed"
                    df_log_sheet_state.loc[original_["PrincipalPaid"]) 
                    schedule_df.loc[target_row_idx, LATE_FEE_COL_SCHED] = float(payment_calcs["LateFee"]) 
                    schedule_df.log_index, timestamp_col_original_casing] = datetime.now()
                    logger.debug(loc[target_row_idx, STATUS_COL_SCHED] = payment_calcs["Status"] f"Applied payment log index {original_log_index} ok.")

                except Exception as payment_error: 
                    schedule_df.loc[target_row_idx, ENDING_BAL_COL_SCHED] = float(
                    logger.error(f"Error applying payment log index {original_log_index} for LoanID {loan_id_internal}: {payment_error}", exc_info=True)
                    df_log_sheetpayment_calcs["EndingBalance"])
                    # InterestPaid and BeginningBalance of this row are NOT changed.

                    next_state.loc[original_log_index, status_col_original_casing] = f"Error_row_idx = target_row_idx + 1
                    if next_row_idx < len( - Payment Apply Fail ({type(payment_error).__name__})"
                    df_log_sheet_state.schedule_df):
                        is_next_row_paid = pd.notna(schedule_df.loc[next_row_idx, ACTUAL_PMT_DATE_COL_SCHED])
                        if not is_next_loc[original_log_index, timestamp_col_original_casing] = datetime.now()
                    loan_processing_succeeded_fully = False 
                    break # Exit inner loop for this loan

            # ---row_paid and BEGIN_BAL_COL_SCHED in schedule_df.columns:
                             schedule_df.loc[next_row_idx, BEGIN_BAL_COL_SCHED] = float(payment_cal After processing all payments for this loan ---
            if loan_processing_succeeded_fully:
                logger.info(f"Attempting final save for amortization schedule {loan_id_internal}...")
                schedule_dfcs["EndingBalance"]) 
                    
                    df_log_sheet_state.loc[original_log_index,_to_write = schedule_df.copy()
                try: schedule_df_to_write.columns status_col_original_casing] = "Processed"; df_log_sheet_state.loc[original_log_index, timestamp_col_original_casing] = datetime.now()
                    logger.debug = current_original_schedule_headers 
                except ValueError: logger.warning(f"Could not restore original headers for schedule(f"Applied payment log index {original_log_index} ok to in-memory schedule for {loan_ {loan_id_internal}...")
                
                if gutils.update_worksheet_from_df(id_internal}.")

                except Exception as payment_error: 
                    logger.error(f"Error applying payment loggs_client, amortization_sheet_id, "Schedule", schedule_df_to_write):
                    logger index {original_log_index} for LoanID {loan_id_internal}: {payment_error}", exc.info(f"Successfully saved updated amortization schedule for {loan_id_internal}.")
                else:
                    _info=True)
                    df_log_sheet_state.loc[original_log_index, statuslogger.error(f"Failed to save updated schedule for {loan_id_internal}. Reverting statuses.")
                    _col_original_casing] = f"Error - Payment Apply Fail ({type(payment_error).__name__})"for item in payment_items_for_loan: 
                        if str(df_log_sheet_state
                    df_log_sheet_state.loc[original_log_index, timestamp_col_original_.loc[item['original_index'], status_col_original_casing]).lower() == 'processed':casing] = datetime.now()
                    loan_processing_succeeded_fully = False 
                    break
                            df_log_sheet_state.loc[item['original_index'], status_col_original_ 

            # --- After processing all payments for this loan ---
            if loan_processing_succeeded_fullycasing] = "Error - Amort. Save Fail"
                            df_log_sheet_state.loc:
                logger.info(f"Attempting final save for amortization schedule {loan_id_internal}...")
                schedule[item['original_index'], timestamp_col_original_casing] = datetime.now() 
            _df_to_write = schedule_df.copy()
                try: schedule_df_to_writeelse:
                 logger.warning(f"Skipping final amortization save for {loan_id_internal} due.columns = current_original_schedule_headers 
                except ValueError: logger.warning(f"Could not restore to error during payment application.")
        # End of outer try block for a single loan's processing
        
    # original headers for schedule {loan_id_internal}...")
                
                if gutils.update_worksheet_ --- 4. Update Payments Log Sheet ---
    logger.info("Attempting final update of Payments Log sheet...")from_df(gs_client, amortization_sheet_id, "Schedule", schedule_df_to_write
    if not gutils.update_worksheet_from_df(gs_client, config.PAYMENTS):
                    logger.info(f"Successfully saved updated amortization schedule for {loan_id_internal}.")
                _LOG_SHEET_ID, "Sheet1", df_log_sheet_state):
        logger.else:
                    logger.error(f"Failed to save updated amortization schedule for {loan_id_internal}.error("CRITICAL: Failed to update the Payments Log sheet with final processing statuses.")
    else:
        logger Reverting statuses.")
                    for item in payment_items_for_loan: 
                        if str(df_log.info("Payments Log sheet updated with all final statuses.")

    logger.info("Payment processing run finished.")

_sheet_state.loc[item['original_index'], status_col_original_casing]).lower()```

---

**File 3: `src/amortization_calculator.py` (Complete Code - No changes == 'processed':
                            df_log_sheet_state.loc[item['original_index'], status_ needed from previous version)**

(The version provided in the response before this one, implementing the pre-filled interest logiccol_original_casing] = "Error - Amort. Save Fail"
                            df_log_sheet_state.loc[item['original_index'], timestamp_col_original_casing] = datetime.now(), is correct and doesn't need changes for this specific comma issue, as the cleaning happens in `payment_processor.py 
            else:
                 logger.warning(f"Skipping final amortization save for {loan_id_` before calling the calculator.)

```python
# src/amortization_calculator.py
from datetime import datetimeinternal} due to error during payment application.")
        # End of outer try block for a single loan's processing
        
, timedelta
import logging
import decimal # Use decimal for precise currency calculations

D = decimal.Decimal
decimal.    # --- 4. Update Payments Log Sheet (ONCE at the end) ---
    logger.info("Attempting finalgetcontext().rounding = decimal.ROUND_HALF_UP # Standard rounding

logger = logging.getLogger(__name__)

 update of Payments Log sheet...")
    if not gutils.update_worksheet_from_df(gs_def calculate_principal_and_status(
    # Inputs expected as standard Python types initially
    beginning_balance_float,client, config.PAYMENTS_LOG_SHEET_ID, "Sheet1", df_log_sheet_
    interest_paid_prefilled_float, # The interest amount already in the schedule cell
    actual_payment_amountstate): # Use the original state df
        logger.error("CRITICAL: Failed to update the Payments Log sheet with_float,
    due_date_str, # Expected YYYY-MM-DD
    actual_ final processing statuses.")
    else:
        logger.info("Payments Log sheet updated with all final statuses.")

payment_date_str, # Expected YYYY-MM-DD
    grace_period_days=3    logger.info("Payment processing run finished.")