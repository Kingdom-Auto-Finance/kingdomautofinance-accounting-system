import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from google.cloud import secretmanager
import json
import logging
import time
from . import config # Assuming this runs from a context where 'src' is a package

logger = logging.getLogger(__name__)

def get_service_account_credentials_from_secret_manager():
    """Fetches service account credentials from Google Secret Manager."""
    try:
        client = secretmanager.SecretManagerServiceClient()
        response = client.access_secret_version(request={"name": config.SERVICE_ACCOUNT_SECRET_RESOURCE_NAME})
        secret_payload = response.payload.data.decode("UTF-8")
        service_account_info = json.loads(secret_payload)

        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive.file' # If creating new sheets or extensive drive interaction
        ]
        credentials = Credentials.from_service_account_info(service_account_info, scopes=scopes)
        logger.info("Successfully retrieved credentials from Secret Manager.")
        return credentials
    except Exception as e:
        logger.error(f"Failed to get credentials from Secret Manager: {e}", exc_info=True)
        raise ConnectionError(f"Could not retrieve service account credentials from Secret Manager: {e}")


def get_gspread_client():
    """Authenticates and returns a gspread client using credentials from Secret Manager."""
    try:
        credentials = get_service_account_credentials_from_secret_manager()
        client = gspread.authorize(credentials)
        logger.info("gspread client authorized successfully.")
        return client
    except Exception as e:
        logger.error(f"Failed to authorize gspread client: {e}", exc_info=True)
        raise ConnectionError(f"Could not authorize gspread client: {e}")


def get_sheet_as_df(gspread_client, sheet_id, sheet_name=None, max_retries=5, initial_delay=1):
    """
    Opens a Google Sheet by ID and returns a specific worksheet as a Pandas DataFrame.
    Includes exponential backoff for quota errors.
    """
    retries = 0
    delay = initial_delay
    while retries < max_retries:
        try:
            spreadsheet = gspread_client.open_by_key(sheet_id)
            if sheet_name:
                worksheet = spreadsheet.worksheet(sheet_name)
            else:
                worksheet = spreadsheet.sheet1
            
            data = worksheet.get_all_values()
            if not data:
                logger.warning(f"Sheet '{sheet_name or 'first sheet'}' in spreadsheet ID '{sheet_id}' is empty.")
                return pd.DataFrame()
            
            headers = data[0]
            records = data[1:]
            if not records:
                return pd.DataFrame(columns=headers)
            df = pd.DataFrame(records, columns=headers)
            return df # Success! Exit the loop and function.

        except gspread.exceptions.APIError as e:
            # Specifically check for "Quota exceeded" (status code 429)
            if e.response.status_code == 429: # type: ignore
                retries += 1
                if retries >= max_retries:
                    logger.error(f"Quota exceeded for sheet ID {sheet_id}, name '{sheet_name}'. Max retries reached. Error: {e}")
                    raise # Re-raise the error if max retries are exhausted
                
                wait_time = delay * (2 ** (retries -1)) # Exponential backoff
                logger.warning(
                    f"Quota exceeded for sheet ID {sheet_id}, name '{sheet_name}'. "
                    f"Retrying in {wait_time:.2f} seconds... (Attempt {retries}/{max_retries})"
                )
                time.sleep(wait_time)
            else:
                # It's a different APIError, not quota related, so re-raise it immediately.
                logger.error(f"Non-quota APIError reading sheet ID {sheet_id}, name '{sheet_name}': {e}", exc_info=True)
                raise
        except gspread.exceptions.WorksheetNotFound:
            logger.error(f"Worksheet '{sheet_name}' not found in spreadsheet ID '{sheet_id}'.")
            return None # Or raise
        except Exception as e:
            logger.error(f"General error reading sheet ID {sheet_id}, name '{sheet_name}': {e}", exc_info=True)
            return None # Or raise
    
    # Should not be reached if max_retries leads to a raise, but as a fallback:
    logger.error(f"Failed to read sheet ID {sheet_id}, name '{sheet_name}' after multiple retries.")
    return None

def update_worksheet_from_df(gspread_client, sheet_id, sheet_name, df):
    """Updates a Google Sheet worksheet with data from a Pandas DataFrame."""
    try:
        spreadsheet = gspread_client.open_by_key(sheet_id)
        worksheet = spreadsheet.worksheet(sheet_name)
        
        # Clear existing content; gspread > 5.8.0 handles NaT/NaN better
        worksheet.clear()
        
        # Convert all DataFrame values to strings to avoid gspread type issues, esp. with NaT, None
        # Also handle boolean values explicitly if necessary (gspread might treat them as 0/1)
        df_cleaned = df.astype(str).replace(['nan', 'NaT', '<NA>'], '') # Replace common Pandas NA representations

        update_values = [df_cleaned.columns.values.tolist()] + df_cleaned.values.tolist()
        worksheet.update(update_values, value_input_option='USER_ENTERED') # USER_ENTERED helps with date/number parsing by Sheets
        
        logger.info(f"Successfully updated worksheet '{sheet_name}' in sheet ID '{sheet_id}'.")
        return True
    except gspread.exceptions.WorksheetNotFound:
        logger.error(f"Worksheet '{sheet_name}' not found in spreadsheet ID '{sheet_id}' for updating.")
        return False
    except Exception as e:
        logger.error(f"Error updating sheet ID {sheet_id}, name '{sheet_name}': {e}", exc_info=True)
        return False

def get_amortization_sheet_id(loan_id):
    """Retrieves the Google Sheet ID for a given loan_id from config."""
    sheet_id = config.AMORTIZATION_SHEET_IDS.get(str(loan_id)) # Ensure loan_id is string for lookup
    if not sheet_id:
        logger.warning(f"No Google Sheet ID configured in config.py for LoanID: {loan_id}")
    return sheet_id