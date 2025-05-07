# src/gutils.py
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials # For creating credentials from service account info
from google.cloud import secretmanager # To fetch the secret from Secret Manager
import json # To parse the JSON string secret
import logging # For logging messages
import time # For delays, especially in retry logic
from . import config # To get configuration like SECRET_NAME and sheet IDs

# Get a logger for this module. Assumes logging is configured elsewhere (e.g., in main.py)
logger = logging.getLogger(__name__)

# --- Helper Function to get Credentials ---
def get_service_account_credentials_from_secret_manager():
    """
    Fetches the service account JSON key content from Google Secret Manager
    and creates a google.oauth2.service_account.Credentials object.
    """
    try:
        sm_client = secretmanager.SecretManagerServiceClient()
        response = sm_client.access_secret_version(request={"name": config.SERVICE_ACCOUNT_SECRET_RESOURCE_NAME})
        secret_payload_str = response.payload.data.decode("UTF-8")
        service_account_info = json.loads(secret_payload_str)
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive.file'
        ]
        credentials = Credentials.from_service_account_info(service_account_info, scopes=scopes)
        logger.info("Successfully retrieved and created service account credentials from Secret Manager.")
        return credentials
    except Exception as e:
        logger.error(f"Failed to get or parse credentials from Secret Manager. Error: {e}", exc_info=True)
        raise # Re-raise the original exception


# --- Main Function Called by Other Modules ---
def get_gspread_client():
    """
    Authenticates with Google Sheets API using credentials obtained from Secret Manager
    and returns an authorized gspread client instance.
    """
    try:
        credentials = get_service_account_credentials_from_secret_manager()
        gspread_client = gspread.authorize(credentials)
        logger.info("gspread client has been successfully authorized.")
        return gspread_client
    except Exception as e:
        logger.error(f"Failed to get authorized gspread client. Error: {e}", exc_info=True)
        raise ConnectionError(f"Could not get authorized gspread client. Underlying error: {type(e).__name__} - {e}")


# --- Function to Read Sheet Data ---
def get_sheet_as_df(gspread_client, sheet_id, sheet_name=None, max_retries=5, initial_delay=1, **kwargs):
    """
    Opens a Google Sheet by its ID, reads a specific worksheet,
    and returns its content as a Pandas DataFrame. Reads values as strings.
    """
    if gspread_client is None:
        logger.error("gspread_client is None in get_sheet_as_df. Cannot proceed.")
        return pd.DataFrame()

    retries = 0
    current_delay = initial_delay
    
    while retries < max_retries:
        try:
            spreadsheet = gspread_client.open_by_key(sheet_id)
            worksheet = spreadsheet.worksheet(sheet_name) if sheet_name else spreadsheet.sheet1
            
            all_values = worksheet.get_all_values(**kwargs) 
            
            if not all_values:
                logger.warning(f"Sheet (ID: {sheet_id}, Name: '{sheet_name or 'first sheet'}') is empty.")
                return pd.DataFrame()
            
            headers = [str(h).strip() for h in all_values[0]]
            records = all_values[1:]
            df = pd.DataFrame(records, columns=headers)

            logger.debug(f"Successfully read sheet (ID: {sheet_id}, Name: '{sheet_name}') with {len(df)} rows. Headers: {headers}")
            return df

        except gspread.exceptions.APIError as e:
            if hasattr(e, 'response') and hasattr(e.response, 'status_code') and e.response.status_code == 429:
                retries += 1
                if retries >= max_retries: logger.error(f"Quota exceeded... Max retries reached. Error: {e}"); raise
                wait_time = current_delay * (2 ** (retries - 1))
                logger.warning(f"Quota exceeded... Retrying in {wait_time:.2f}s...")
                time.sleep(wait_time)
            else: logger.error(f"Non-quota APIError reading sheet...: {e}", exc_info=True); raise
        except gspread.exceptions.WorksheetNotFound:
            logger.error(f"Worksheet '{sheet_name}' not found in spreadsheet (ID: {sheet_id}).")
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"General error reading sheet...: {e}", exc_info=True)
            return pd.DataFrame()

    logger.error(f"Failed to read sheet (ID: {sheet_id}, Name: '{sheet_name}') after {max_retries} retries.")
    return pd.DataFrame()


# --- Function to Write DataFrame to Sheet ---
def update_worksheet_from_df(gspread_client, sheet_id, sheet_name, df_to_write):
    """
    Updates a Google Sheet worksheet with data from a Pandas DataFrame. Clears sheet first.
    """
    if gspread_client is None: logger.error(f"gspread_client is None in update_worksheet_from_df..."); return False
    if df_to_write is None: logger.error(f"DataFrame to write is None..."); return False
    
    if df_to_write.empty and not df_to_write.columns.empty:
        list_of_lists_for_gspread = [df_to_write.columns.tolist()]
    elif df_to_write.empty and df_to_write.columns.empty:
        list_of_lists_for_gspread = []
    else:
        df_prepared = df_to_write.copy()
        for col in df_prepared.columns:
             if pd.api.types.is_datetime64_any_dtype(df_prepared[col]):
                 is_date_only = (df_prepared[col].dt.normalize() == df_prepared[col]).all() if df_prepared[col].notna().any() else True
                 fmt = '%Y-%m-%d' if is_date_only else '%Y-%m-%d %H:%M:%S'
                 df_prepared[col] = df_prepared[col].apply(lambda x: x.strftime(fmt) if pd.notna(x) else '')
             elif pd.api.types.is_bool_dtype(df_prepared[col]):
                 df_prepared[col] = df_prepared[col].apply(lambda x: 'TRUE' if pd.notna(x) and x is True else ('FALSE' if pd.notna(x) and x is False else ''))
             else:
                 df_prepared[col] = df_prepared[col].astype(str).replace({'nan': '', '<NA>': '', 'NaT': ''})

        list_of_lists_for_gspread = [df_prepared.columns.tolist()] + df_prepared.values.tolist()
    
    try:
        spreadsheet = gspread_client.open_by_key(sheet_id)
        worksheet = spreadsheet.worksheet(sheet_name)
        
        worksheet.clear() 
        if list_of_lists_for_gspread:
            worksheet.update(list_of_lists_for_gspread, value_input_option='USER_ENTERED')
            logger.info(f"Successfully updated worksheet '{sheet_name}' in sheet (ID: {sheet_id}).")
        else:
            logger.info(f"Worksheet '{sheet_name}' in sheet (ID: {sheet_id}) was cleared (empty input).")
        return True
    except gspread.exceptions.WorksheetNotFound: logger.error(f"Worksheet '{sheet_name}' not found..."); return False
    except Exception as e: logger.error(f"Error updating sheet...: {e}", exc_info=True); return False

# --- Function to Get Amortization Sheet ID (CASE-INSENSITIVE KEY LOOKUP) ---
def get_amortization_sheet_id(loan_id):
    """
    Retrieves the Google Sheet ID for a given loan_id from the 
    config.AMORTIZATION_SHEET_IDS dictionary using a case-insensitive lookup.
    """
    # Standardize the input loan_id for comparison (uppercase, stripped)
    loan_id_upper = str(loan_id).strip().upper()
    
    # Iterate through the dictionary keys in config.py
    for key_in_config, sheet_id_value in config.AMORTIZATION_SHEET_IDS.items():
        # Compare the uppercased input ID with the uppercased key from the dictionary
        if str(key_in_config).strip().upper() == loan_id_upper:
            # Found a match (ignoring case)
            logger.debug(f"Found Sheet ID '{sheet_id_value}' for LoanID '{loan_id}' using key '{key_in_config}'.")
            return sheet_id_value # Return the corresponding sheet ID

    # If the loop finishes without finding a match
    logger.warning(f"No Google Sheet ID configured in config.py for LoanID: '{loan_id}' (checked case-insensitively as '{loan_id_upper}').")
    return None # Return None if no match is found