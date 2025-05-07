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
        raise # Re-raise for debugging


def get_gspread_client(): # <<<< THIS IS THE FUNCTION PAYMENT_PROCESSOR.PY CALLS
    """
    Authenticates with Google Sheets API using credentials obtained from Secret Manager
    and returns an authorized gspread client instance.
    """
    try:
        # First, get the credentials object using the helper function
        credentials = get_service_account_credentials_from_secret_manager()
        
        # Authorize gspread with these credentials
        gspread_client = gspread.authorize(credentials)
        
        logger.info("gspread client has been successfully authorized.")
        return gspread_client
    except Exception as e:
        logger.error(f"Failed to get authorized gspread client. Error: {e}", exc_info=True)
        raise ConnectionError(f"Could not get authorized gspread client. Underlying error: {type(e).__name__} - {e}")


def get_sheet_as_df(gspread_client, sheet_id, sheet_name=None, max_retries=5, initial_delay=1):
    """
    Opens a Google Sheet by its ID, reads a specific worksheet,
    and returns its content as a Pandas DataFrame.
    Includes exponential backoff and basic type inference.
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
            
            all_values = worksheet.get_all_values()
            
            if not all_values:
                logger.warning(f"Sheet (ID: {sheet_id}, Name: '{sheet_name or 'first sheet'}') is empty.")
                return pd.DataFrame()
            
            headers = all_values[0]
            records = all_values[1:]
            df = pd.DataFrame(records, columns=headers)

            df.replace('', pd.NA, inplace=True)

            for col in df.columns:
                col_lower = str(col).lower()
                if any(num_keyword in col_lower for num_keyword in ['amount', 'balance', 'principal', 'interest', 'fee', 'rate', 'payment', 'number', '#', 'id', 'term', 'period', 'count', 'qty', 'value']):
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                
                if 'date' in col_lower or 'due' in col_lower or 'start' in col_lower or 'end' in col_lower or 'timestamp' in col_lower:
                    try:
                        df[col] = pd.to_datetime(df[col], format='%Y-%m-%d', errors='coerce')
                    except TypeError:
                        df[col] = pd.to_datetime(df[col], errors='coerce')

            logger.debug(f"Successfully read and typed sheet (ID: {sheet_id}, Name: '{sheet_name}').")
            return df

        except gspread.exceptions.APIError as e:
            if hasattr(e, 'response') and hasattr(e.response, 'status_code') and e.response.status_code == 429:
                retries += 1
                if retries >= max_retries:
                    logger.error(f"Quota exceeded for sheet (ID: {sheet_id}, Name: '{sheet_name}'). Max retries reached. Error: {e}")
                    raise
                wait_time = current_delay * (2 ** (retries - 1))
                logger.warning(f"Quota exceeded... Retrying in {wait_time:.2f}s...")
                time.sleep(wait_time)
            else:
                logger.error(f"Non-quota APIError reading sheet (ID: {sheet_id}, Name: '{sheet_name}'): {e}", exc_info=True)
                raise
        except gspread.exceptions.WorksheetNotFound:
            logger.error(f"Worksheet '{sheet_name}' not found in spreadsheet (ID: {sheet_id}).")
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"General error reading sheet (ID: {sheet_id}, Name: '{sheet_name}'): {e}", exc_info=True)
            return pd.DataFrame()

    logger.error(f"Failed to read sheet (ID: {sheet_id}, Name: '{sheet_name}') after {max_retries} retries.")
    return pd.DataFrame()


def update_worksheet_from_df(gspread_client, sheet_id, sheet_name, df_to_write):
    """
    Updates a Google Sheet worksheet with data from a Pandas DataFrame.
    """
    if gspread_client is None:
        logger.error(f"gspread_client is None in update_worksheet_from_df for sheet (ID: {sheet_id}, Name: '{sheet_name}'). Cannot proceed.")
        return False
    if df_to_write is None:
        logger.error(f"DataFrame to write to sheet (ID: {sheet_id}, Name: '{sheet_name}') is None. Aborting update.")
        return False
    
    try:
        spreadsheet = gspread_client.open_by_key(sheet_id)
        worksheet = spreadsheet.worksheet(sheet_name)
        
        df_prepared = df_to_write.copy()

        for col in df_prepared.columns:
            if pd.api.types.is_datetime64_any_dtype(df_prepared[col]):
                is_date_only = (df_prepared[col].dt.normalize() == df_prepared[col]).all() if df_prepared[col].notna().any() else True
                if is_date_only:
                    df_prepared[col] = df_prepared[col].dt.strftime('%Y-%m-%d').fillna('')
                else:
                    df_prepared[col] = df_prepared[col].dt.strftime('%Y-%m-%d %H:%M:%S').fillna('')
            elif pd.api.types.is_bool_dtype(df_prepared[col]):
                df_prepared[col] = df_prepared[col].apply(
                    lambda x: 'TRUE' if pd.notna(x) and x is True else ('FALSE' if pd.notna(x) and x is False else '')
                )
            else:
                df_prepared[col] = df_prepared[col].fillna('')
        
        list_of_lists_for_gspread = [df_prepared.columns.tolist()] + df_prepared.values.tolist()
        
        worksheet.clear()
        worksheet.update(list_of_lists_for_gspread, value_input_option='USER_ENTERED')
        
        logger.info(f"Successfully updated worksheet '{sheet_name}' in sheet (ID: {sheet_id}) with {len(df_to_write)} data rows.")
        return True
    except gspread.exceptions.WorksheetNotFound:
        logger.error(f"Worksheet '{sheet_name}' not found in spreadsheet (ID: {sheet_id}) for updating.")
        return False
    except Exception as e:
        logger.error(f"Error updating sheet (ID: {sheet_id}, Name: '{sheet_name}'): {e}", exc_info=True)
        return False


def get_amortization_sheet_id(loan_id):
    """
    Retrieves the Google Sheet ID for a given loan_id from the config.AMORTIZATION_SHEET_IDS dictionary.
    """
    loan_id_str = str(loan_id).strip().upper()
    sheet_id = config.AMORTIZATION_SHEET_IDS.get(loan_id_str)
    if not sheet_id:
        logger.warning(f"No Google Sheet ID configured in config.py for LoanID: '{loan_id_str}'. Check AMORTIZATION_SHEET_IDS.")
    return sheet_id