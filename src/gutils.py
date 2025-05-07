# src/gutils.py
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials # For creating credentials from service account info
from google.cloud import secretmanager # To fetch the secret from Secret Manager
# --- ADD THIS for Drive API ---
from googleapiclient.discovery import build # To interact with Drive API
from googleapiclient.errors import HttpError # To handle Drive API errors
# --- END ADD ---
import json # To parse the JSON string secret
import logging # For logging messages
import time # For delays, especially in retry logic
from . import config # To get configuration like SECRET_NAME and sheet IDs

# Get a logger for this module. Assumes logging is configured elsewhere (e.g., in main.py)
logger = logging.getLogger(__name__)

# --- Global variable for Drive service client (to avoid rebuilding it constantly) ---
drive_service_client = None 

def get_drive_service():
    """Creates and returns a Google Drive API service client using credentials."""
    global drive_service_client
    if drive_service_client is None:
        logger.debug("Initializing Google Drive service client...")
        try:
            # Credentials should include Drive scopes
            credentials = get_service_account_credentials_from_secret_manager() 
            # Build the Drive service object using V3 of the API
            drive_service_client = build('drive', 'v3', credentials=credentials)
            logger.info("Google Drive API service client created successfully.")
        except Exception as e:
            logger.error(f"Failed to create Google Drive API service client: {e}", exc_info=True)
            drive_service_client = None # Ensure it remains None on failure
            raise ConnectionError(f"Could not create Drive service client: {e}")
    return drive_service_client


# --- Helper Function to get Credentials (includes Drive scopes) ---
def get_service_account_credentials_from_secret_manager():
    """
    Fetches the service account JSON key content from Google Secret Manager
    and creates a google.oauth2.service_account.Credentials object including necessary Drive scopes.
    """
    try:
        sm_client = secretmanager.SecretManagerServiceClient()
        response = sm_client.access_secret_version(request={"name": config.SERVICE_ACCOUNT_SECRET_RESOURCE_NAME})
        secret_payload_str = response.payload.data.decode("UTF-8")
        service_account_info = json.loads(secret_payload_str)
        
        # Define the scopes needed - ensure drive scopes are present
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',  # Full access to spreadsheets
            'https://www.googleapis.com/auth/drive.file',     # Needed to open spreadsheets by ID
            'https://www.googleapis.com/auth/drive.readonly' # Needed to search/list files in Drive
        ]
        
        credentials = Credentials.from_service_account_info(service_account_info, scopes=scopes)
        logger.info("Successfully retrieved credentials from Secret Manager (including Drive scopes).")
        return credentials
    except Exception as e:
        logger.error(f"Failed to get or parse credentials from Secret Manager. Error: {e}", exc_info=True)
        raise # Re-raise the original exception


# --- Main Function Called by Other Modules to get gspread client ---
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
        raise ConnectionError(f"Could not authorize gspread client. Underlying error: {type(e).__name__} - {e}")


# --- NEW FUNCTION: Find Sheet ID by Name in Folder using Drive API ---
def find_sheet_id_by_loan_id_in_folder(loan_id):
    """
    Searches a specific Google Drive folder (defined in config) for a Google Sheet file
    whose name exactly matches the provided loan_id (case-sensitive recommended).
    Returns the Google Sheet file ID if found, otherwise None.
    """
    target_filename = str(loan_id).strip() # Filename should exactly match the LoanID
    parent_folder_id = config.AMORTIZATION_SCHEDULES_FOLDER_ID
    
    if not parent_folder_id:
        logger.error("AMORTIZATION_SCHEDULES_FOLDER_ID is not set in config.py. Cannot search Drive.")
        return None

    logger.debug(f"Searching for Sheet named '{target_filename}' in Drive Folder ID '{parent_folder_id}'")

    try:
        service = get_drive_service() # Get initialized Drive API client
        if not service:
             logger.error("Drive service client is not available for searching.")
             return None

        # Construct the search query using 'q' parameter for Drive API v3
        # - Search within the specific parent folder
        # - Match the exact filename (case-sensitive depends on Drive implementation, often case-insensitive but safer to assume sensitive)
        # - Ensure it's a Google Sheet (mimeType)
        # - Ensure it's not in the trash
        query = (
            f"'{parent_folder_id}' in parents "
            f"and name = '{target_filename}' "
            f"and mimeType = 'application/vnd.google-apps.spreadsheet' "
            f"and trashed = false"
        )

        # Execute the search using files().list
        results = service.files().list(
            q=query,
            pageSize=5, # Limit results (should ideally only be 1)
            fields="files(id, name)" # Specify only the fields needed (ID and name)
        ).execute()
        
        items = results.get('files', [])

        if not items:
            logger.warning(f"No Google Sheet named '{target_filename}' found in folder '{parent_folder_id}'.")
            return None
        elif len(items) > 1:
            # This indicates a potential issue with duplicate filenames
            logger.warning(f"Found {len(items)} Google Sheets named '{target_filename}' in folder '{parent_folder_id}'. Returning the first one found (ID: {items[0]['id']}). Please ensure LoanID filenames are unique.")
            return items[0]['id'] # Return the ID of the first match found
        else:
            # Exactly one item found
            found_id = items[0]['id']
            logger.info(f"Found Google Sheet for LoanID '{target_filename}'. File ID: {found_id}")
            return found_id

    except HttpError as error:
        # Specifically catch HTTP errors from the API call
        logger.error(f"A Google Drive API error occurred searching for '{target_filename}': {error}", exc_info=True)
        return None
    except Exception as e:
        # Catch any other unexpected errors during the process
        logger.error(f"An unexpected error occurred during Google Drive search for '{target_filename}': {e}", exc_info=True)
        return None


# --- Function to Read Sheet Data ---
def get_sheet_as_df(gspread_client, sheet_id, sheet_name=None, max_retries=5, initial_delay=1, **kwargs):
    """
    Opens a Google Sheet by its ID, reads a specific worksheet,
    and returns its content as a Pandas DataFrame. Reads values as strings.
    Includes exponential backoff retry logic for quota errors.
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
            
            # Get all values as strings for consistent parsing later.
            all_values = worksheet.get_all_values(**kwargs) 
            
            if not all_values:
                logger.warning(f"Sheet (ID: {sheet_id}, Name: '{sheet_name or 'first sheet'}') is empty.")
                return pd.DataFrame()
            
            headers = [str(h).strip() for h in all_values[0]]
            records = all_values[1:]
            # Handle case where there are only headers and no records
            if not records:
                 logger.warning(f"Sheet (ID: {sheet_id}, Name: '{sheet_name}') has headers but no data rows.")
                 return pd.DataFrame(columns=headers) # Return DataFrame with headers but no rows

            df = pd.DataFrame(records, columns=headers)

            logger.debug(f"Successfully read sheet (ID: {sheet_id}, Name: '{sheet_name}') with {len(df)} rows. Headers: {headers}")
            return df

        except gspread.exceptions.APIError as e:
            # Handle quota errors with exponential backoff
            if hasattr(e, 'response') and hasattr(e.response, 'status_code') and e.response.status_code == 429:
                retries += 1
                if retries >= max_retries: 
                    logger.error(f"Quota exceeded for sheet (ID: {sheet_id}, Name: '{sheet_name}'). Max retries ({max_retries}) reached. Error: {e}")
                    raise # Re-raise the final quota error
                wait_time = current_delay * (2 ** (retries - 1))
                logger.warning(f"Quota exceeded reading sheet (ID: {sheet_id}, Name: '{sheet_name}'). Retrying in {wait_time:.2f}s... (Attempt {retries}/{max_retries})")
                time.sleep(wait_time)
            else: 
                # Handle other API errors
                logger.error(f"Non-quota APIError reading sheet (ID: {sheet_id}, Name: '{sheet_name}'): {e}", exc_info=True)
                raise # Re-raise other API errors
        except gspread.exceptions.WorksheetNotFound:
            logger.error(f"Worksheet '{sheet_name}' not found in spreadsheet (ID: {sheet_id}).")
            return pd.DataFrame() # Return empty DataFrame if sheet/tab not found
        except Exception as e:
            logger.error(f"General error reading sheet (ID: {sheet_id}, Name: '{sheet_name}'): {e}", exc_info=True)
            return pd.DataFrame() # Return empty DataFrame on other errors

    # This part is reached only if all retries failed due to quota
    logger.error(f"Failed to read sheet (ID: {sheet_id}, Name: '{sheet_name}') after {max_retries} retries due to persistent quota issues.")
    return pd.DataFrame()


# --- Function to Write DataFrame to Sheet ---
def update_worksheet_from_df(gspread_client, sheet_id, sheet_name, df_to_write):
    """
    Updates a Google Sheet worksheet with data from a Pandas DataFrame.
    Clears the existing sheet content and then writes the new data, including headers.
    Uses 'USER_ENTERED' value input option for better type interpretation by Google Sheets.
    """
    if gspread_client is None: logger.error(f"gspread_client is None in update_worksheet_from_df for sheet ID {sheet_id}."); return False
    if df_to_write is None: logger.error(f"DataFrame to write to sheet ID {sheet_id} is None."); return False
    
    # Prepare list of lists for gspread update
    if df_to_write.empty and not df_to_write.columns.empty:
        logger.info(f"Writing only headers to sheet (ID: {sheet_id}, Name: '{sheet_name}').")
        list_of_lists_for_gspread = [df_to_write.columns.tolist()]
    elif df_to_write.empty and df_to_write.columns.empty:
        logger.info(f"Input DataFrame is empty, clearing sheet (ID: {sheet_id}, Name: '{sheet_name}').")
        list_of_lists_for_gspread = []
    else:
        # Prepare data: Convert NaNs/NaTs and specific types to strings for reliable update
        df_prepared = df_to_write.copy()
        for col in df_prepared.columns:
             if pd.api.types.is_datetime64_any_dtype(df_prepared[col]):
                 is_date_only = (df_prepared[col].dt.normalize() == df_prepared[col]).all() if df_prepared[col].notna().any() else True
                 fmt = '%Y-%m-%d' if is_date_only else '%Y-%m-%d %H:%M:%S'
                 df_prepared[col] = df_prepared[col].apply(lambda x: x.strftime(fmt) if pd.notna(x) else '')
             elif pd.api.types.is_bool_dtype(df_prepared[col]):
                 df_prepared[col] = df_prepared[col].apply(lambda x: 'TRUE' if pd.notna(x) and x is True else ('FALSE' if pd.notna(x) and x is False else ''))
             else:
                 # Convert remaining NAs to empty string after handling specific types
                 # This ensures numbers passed to Sheets are numbers if possible, NAs are blank
                 df_prepared[col] = df_prepared[col].fillna('') # Prefer fillna('') over astype(str) for non-object cols

        # Convert prepared DataFrame to list of lists
        list_of_lists_for_gspread = [df_prepared.columns.tolist()] + df_prepared.astype(object).where(pd.notna(df_prepared), '').values.tolist()


    
    try:
        spreadsheet = gspread_client.open_by_key(sheet_id)
        worksheet = spreadsheet.worksheet(sheet_name)
        
        worksheet.clear() 
        if list_of_lists_for_gspread: # Only update if there's something to write
            worksheet.update(list_of_lists_for_gspread, value_input_option='USER_ENTERED')
            logger.info(f"Successfully updated worksheet '{sheet_name}' in sheet (ID: {sheet_id}).")
        else:
            logger.info(f"Worksheet '{sheet_name}' in sheet (ID: {sheet_id}) was cleared (empty input).")
        return True
    except gspread.exceptions.WorksheetNotFound: 
        logger.error(f"Worksheet '{sheet_name}' not found in spreadsheet (ID: {sheet_id}) for updating.")
        return False
    except Exception as e: 
        logger.error(f"Error updating sheet (ID: {sheet_id}, Name: '{sheet_name}'): {e}", exc_info=True)
        return False

# --- REMOVED OLD DICTIONARY-BASED LOOKUP FUNCTION ---
# def get_amortization_sheet_id(loan_id): ... (old function removed)