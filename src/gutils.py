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
        # Create a client for interacting with Secret Manager
        sm_client = secretmanager.SecretManagerServiceClient()
        
        # Access the secret version using the resource name from config.py
        # config.SERVICE_ACCOUNT_SECRET_RESOURCE_NAME should be like:
        # "projects/YOUR_PROJECT_ID/secrets/YOUR_SECRET_NAME/versions/latest"
        response = sm_client.access_secret_version(request={"name": config.SERVICE_ACCOUNT_SECRET_RESOURCE_NAME})
        
        # Decode the secret payload (which is the JSON key content)
        secret_payload_str = response.payload.data.decode("UTF-8")
        
        # Parse the JSON string into a Python dictionary
        service_account_info = json.loads(secret_payload_str)

        # Define the scopes (permissions) our script needs for Google Sheets and Drive
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',  # Full access to spreadsheets
            'https://www.googleapis.com/auth/drive.file'     # To open spreadsheets by ID from Drive
        ]
        
        # Create credentials object from the service account info and defined scopes
        credentials = Credentials.from_service_account_info(service_account_info, scopes=scopes)
        
        logger.info("Successfully retrieved and created service account credentials from Secret Manager.")
        return credentials
    except Exception as e:
        logger.error(f"Failed to get or parse credentials from Secret Manager. Error: {e}", exc_info=True)
        # Re-raise the original exception so the calling function knows exactly what went wrong
        # This helps in debugging permission issues, secret not found, etc.
        raise


def get_gspread_client():
    """
    Authenticates with Google Sheets API using credentials obtained from Secret Manager
    and returns an authorized gspread client instance.
    This is the function that was causing the AttributeError.
    """
    try:
        # First, get the credentials object
        credentials = get_service_account_credentials_from_secret_manager()
        
        # Authorize gspread with these credentials
        gspread_client = gspread.authorize(credentials)
        
        logger.info("gspread client has been successfully authorized.")
        return gspread_client
    except Exception as e:
        # This will catch errors from get_service_account_credentials_from_secret_manager()
        # or from gspread.authorize() itself.
        logger.error(f"Failed to get authorized gspread client. Error: {e}", exc_info=True)
        # Raising a more specific error or letting the original propagate
        raise ConnectionError(f"Could not get authorized gspread client. Underlying error: {type(e).__name__} - {e}")


def get_sheet_as_df(gspread_client, sheet_id, sheet_name=None, max_retries=5, initial_delay=1):
    """
    Opens a Google Sheet by its ID, reads a specific worksheet (or the first one if no name given),
    and returns its content as a Pandas DataFrame.
    Includes exponential backoff retry logic for "Quota Exceeded" errors.
    Attempts basic type inference for common numeric and date column names.
    """
    if gspread_client is None:
        logger.error("gspread_client is None in get_sheet_as_df. Cannot proceed.")
        return pd.DataFrame() # Return empty DataFrame if client is not available

    retries = 0
    current_delay = initial_delay # Renamed 'delay' to 'current_delay' to avoid confusion with time module itself
    
    while retries < max_retries:
        try:
            spreadsheet = gspread_client.open_by_key(sheet_id)
            if sheet_name:
                worksheet = spreadsheet.worksheet(sheet_name)
            else:
                worksheet = spreadsheet.sheet1 # Default to the first sheet
            
            all_values = worksheet.get_all_values() # gspread returns list of lists (rows of cells)
            
            if not all_values:
                logger.warning(f"Sheet (ID: {sheet_id}, Name: '{sheet_name or 'first sheet'}') is empty or returned no data.")
                return pd.DataFrame() # Return an empty DataFrame
            
            headers = all_values[0]
            records = all_values[1:]

            # Create DataFrame
            df = pd.DataFrame(records, columns=headers)

            # Attempt to convert known numeric columns to numeric types, coercing errors to NaN
            for col in df.columns:
                col_lower = str(col).lower() # Work with lowercase column names for checks
                if any(num_keyword in col_lower for num_keyword in ['amount', 'balance', 'principal', 'interest', 'fee', 'rate', 'payment', 'number', '#', 'id', 'term', 'period', 'count', 'qty']):
                    # Replace empty strings with pd.NA (Pandas' missing value marker) before converting to numeric
                    df[col] = df[col].replace('', pd.NA) 
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # Attempt to convert columns that might contain dates
            for col in df.columns:
                col_lower = str(col).lower()
                if 'date' in col_lower or 'due' in col_lower or 'start' in col_lower or 'end' in col_lower or 'timestamp' in col_lower:
                    df[col] = df[col].replace('', pd.NaT) # Replace empty strings with NaT for dates
                    df[col] = pd.to_datetime(df[col], errors='coerce') # Coerce errors to NaT

            logger.debug(f"Successfully read and performed initial typing for sheet (ID: {sheet_id}, Name: '{sheet_name}'). Columns: {df.columns.tolist()}")
            return df # Success!

        except gspread.exceptions.APIError as e:
            # Check if the error has a 'response' attribute and a 'status_code'
            if hasattr(e, 'response') and hasattr(e.response, 'status_code') and e.response.status_code == 429: # Quota exceeded
                retries += 1
                if retries >= max_retries:
                    logger.error(f"Quota exceeded for sheet (ID: {sheet_id}, Name: '{sheet_name}'). Max retries ({max_retries}) reached. Error: {e}")
                    raise # Re-raise the error if max retries are exhausted
                
                wait_time = current_delay * (2 ** (retries - 1)) # Exponential backoff formula
                logger.warning(
                    f"Quota exceeded for sheet (ID: {sheet_id}, Name: '{sheet_name}'). "
                    f"Retrying in {wait_time:.2f} seconds... (Attempt {retries}/{max_retries})"
                )
                time.sleep(wait_time)
            else:
                # It's a different APIError (not quota related), so re-raise it immediately.
                logger.error(f"Non-quota APIError reading sheet (ID: {sheet_id}, Name: '{sheet_name}'): {e}", exc_info=True)
                raise
        except gspread.exceptions.WorksheetNotFound:
            logger.error(f"Worksheet '{sheet_name}' not found in spreadsheet (ID: {sheet_id}).")
            return pd.DataFrame() # Return empty DataFrame
        except Exception as e: # Catch any other unexpected errors
            logger.error(f"General error reading sheet (ID: {sheet_id}, Name: '{sheet_name}'): {e}", exc_info=True)
            return pd.DataFrame() # Return empty DataFrame

    # This part is reached if all retries for quota error fail
    logger.error(f"Failed to read sheet (ID: {sheet_id}, Name: '{sheet_name}') after {max_retries} retries due to persistent quota issues.")
    return pd.DataFrame() # Return empty DataFrame


def update_worksheet_from_df(gspread_client, sheet_id, sheet_name, df_to_write):
    """
    Updates a Google Sheet worksheet with data from a Pandas DataFrame.
    It clears the existing sheet content and then writes the new data, including headers.
    Uses 'USER_ENTERED' value input option for better type interpretation by Google Sheets.
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
        
        # Prepare DataFrame for writing to Google Sheets
        df_prepared = df_to_write.copy()

        # Convert all data to types that gspread handles well or Google Sheets can interpret with USER_ENTERED
        # Primarily, convert Pandas NA types (pd.NA, np.nan, pd.NaT) to empty strings or None.
        # Empty strings are often safer for gspread bulk updates.
        for col in df_prepared.columns:
            if pd.api.types.is_datetime64_any_dtype(df_prepared[col]):
                # Format datetime to ISO string; NaT becomes an empty string
                df_prepared[col] = df_prepared[col].dt.strftime('%Y-%m-%d %H:%M:%S').fillna('')
            elif pd.api.types.is_bool_dtype(df_prepared[col]):
                # Convert Python bools to string "TRUE" / "FALSE" or empty for NA
                # This ensures Sheets interprets them as booleans with USER_ENTERED
                df_prepared[col] = df_prepared[col].apply(
                    lambda x: 'TRUE' if pd.notna(x) and x is True else ('FALSE' if pd.notna(x) and x is False else '')
                )
            else:
                # For other types, fill NA/NaN with empty string.
                df_prepared[col] = df_prepared[col].fillna('')
        
        # The data to send to gspread needs to be a list of lists, with headers as the first list.
        list_of_lists_for_gspread = [df_prepared.columns.tolist()] + df_prepared.values.tolist()
        
        worksheet.clear() # Clear all existing data and formatting from the sheet
        
        # Update the sheet with the new data
        # 'USER_ENTERED' means Google Sheets will try to parse values as if a user typed them
        # e.g., "123" becomes a number, "2023-10-10" becomes a date.
        worksheet.update(list_of_lists_for_gspread, value_input_option='USER_ENTERED')
        
        logger.info(f"Successfully updated worksheet '{sheet_name}' in sheet (ID: {sheet_id}) with {len(df_to_write)} data rows (plus header).")
        return True
    except gspread.exceptions.WorksheetNotFound:
        logger.error(f"Worksheet '{sheet_name}' not found in spreadsheet (ID: {sheet_id}) for updating.")
        return False
    except Exception as e: # Catch any other unexpected errors during update
        logger.error(f"Error updating sheet (ID: {sheet_id}, Name: '{sheet_name}'): {e}", exc_info=True)
        return False


def get_amortization_sheet_id(loan_id):
    """
    Retrieves the Google Sheet ID for a given loan_id from the config.AMORTIZATION_SHEET_IDS dictionary.
    Ensures loan_id is treated as a string for consistent dictionary lookup.
    """
    # Standardize loan_id to string and perhaps a consistent case if not already done
    loan_id_str = str(loan_id).strip().upper() # Example: ensure it's uppercase like in config
    
    sheet_id = config.AMORTIZATION_SHEET_IDS.get(loan_id_str)
    if not sheet_id:
        logger.warning(f"No Google Sheet ID configured in config.py for LoanID: '{loan_id_str}'. Check AMORTIZATION_SHEET_IDS.")
    return sheet_id