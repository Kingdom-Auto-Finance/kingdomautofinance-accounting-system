# src/gutils.py
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials 
from google.cloud import secretmanager 
from googleapiclient.discovery import build 
from googleapiclient.errors import HttpError 
import json 
import logging 
import time 
from decimal import Decimal, InvalidOperation 
from datetime import datetime, date # Import base datetime types

# Import config relative to the src package
from . import config 

logger = logging.getLogger(__name__)

# Cache for initialized Google API clients to avoid re-authentication
drive_service_client = None 
gspread_authorized_client = None # Cache for gspread client

# --- Helper function to clean/convert currency strings to float ---
def safe_string_to_float(value_str, context=""):
    """Cleans string (removes $, commas) and converts to float, returns pd.NA on error."""
    if pd.isna(value_str) or str(value_str).strip() == "": 
        return pd.NA 
    try:
        cleaned_str = str(value_str).replace('$', '').replace(',', '').strip()
        # Handle parentheses for negative numbers
        if cleaned_str.startswith('(') and cleaned_str.endswith(')'):
             cleaned_str = '-' + cleaned_str[1:-1]
        return float(cleaned_str)
    except (ValueError, TypeError): 
        logger.warning(f"Could not convert '{value_str}' to float for {context}. Returning pd.NA.")
        return pd.NA 

# --- Helper function to clean/convert string to Decimal ---
def safe_string_to_decimal(value_str, context=""):
    """Cleans string (removes $, commas) and converts to Decimal, returns Decimal('NaN') on error."""
    if pd.isna(value_str) or str(value_str).strip() == "": 
        return Decimal('NaN')
    try:
        cleaned_str = str(value_str).replace('$', '').replace(',', '').strip()
        if cleaned_str.startswith('(') and cleaned_str.endswith(')'): 
             cleaned_str = '-' + cleaned_str[1:-1]
        return Decimal(cleaned_str)
    except (TypeError, InvalidOperation): 
        logger.warning(f"Could not convert '{value_str}' to Decimal for {context}. Returning NaN.")
        return Decimal('NaN')

# --- Helper Function to List Files in Drive Folder ---
def get_loan_ids_from_drive_folder(folder_id):
    """Lists Google Sheet files in Drive folder, returns their names (assumed LoanIDs)."""
    loan_ids = []
    drive_service = None # Local variable for this function call
    page_token = None
    try:
        drive_service = get_drive_service(); # Get potentially cached service
        if not drive_service: 
            logger.error("Cannot get Drive service client to list loan IDs.")
            return [] # Return empty list if service fails
        
        logger.info(f"Listing Google Sheets in Drive Folder ID: {folder_id}")
        # Use files().list() which returns a request object for pagination
        request = drive_service.files().list(
                q=f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.spreadsheet' and trashed=false",
                pageSize=1000, # Maximize items per page
                fields="nextPageToken, files(id, name)", # Only get needed fields
                pageToken=page_token
            )
        
        # Loop through pages of results
        while request is not None:
            results = request.execute()
            items = results.get('files', [])
            
            # Check if this page has items
            if items:
                 for item in items:
                     filename = item.get('name')
                     if filename: 
                         loan_ids.append(filename) 
                     else: 
                         logger.warning(f"Found file with ID {item.get('id')} but no name in folder {folder_id}.")
            elif not loan_ids: # No items on this page AND none found previously
                 if page_token is None: # If it was the very first page
                      logger.warning(f"No Google Sheet files found in the specified Drive folder: {folder_id}")
                      return [] # Folder is likely empty
                 else: # Empty page but not the first, means we're done
                      break

            # Get the request object for the next page, or None if no more pages
            request = drive_service.files().list_next(previous_request=request, previous_response=results)

        logger.info(f"Found {len(loan_ids)} potential LoanIDs (sheet names) in Drive folder.")
        return loan_ids
    except HttpError as error:
         logger.error(f"API error listing files in Drive folder {folder_id}: {error}", exc_info=True)
         return []
    except Exception as e: 
        logger.error(f"Failed to list files in Drive folder {folder_id}: {e}", exc_info=True)
        return []


# --- get_drive_service (Caches the client) ---
def get_drive_service():
    """Creates/returns Google Drive API service client, caching it globally."""
    global drive_service_client # Refer to the global variable
    if drive_service_client is None:
        logger.debug("Initializing Google Drive service client...")
        try:
            credentials = get_service_account_credentials_from_secret_manager() 
            drive_service_client = build('drive', 'v3', credentials=credentials, cache_discovery=False) 
            logger.info("Google Drive API service client created successfully.")
        except Exception as e:
            logger.error(f"Failed to create Google Drive API service client: {e}", exc_info=True)
            drive_service_client = None # Reset on failure
            raise ConnectionError(f"Could not create Drive service client: {e}")
    return drive_service_client

# --- get_service_account_credentials_from_secret_manager --- 
def get_service_account_credentials_from_secret_manager():
    """Fetches credentials from Secret Manager including necessary Drive scopes."""
    try:
        sm_client = secretmanager.SecretManagerServiceClient()
        response = sm_client.access_secret_version(request={"name": config.SERVICE_ACCOUNT_SECRET_RESOURCE_NAME})
        secret_payload_str = response.payload.data.decode("UTF-8")
        service_account_info = json.loads(secret_payload_str)
        # Ensure all required scopes are listed
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets', 
            'https://www.googleapis.com/auth/drive.file', # Needed to open files by ID
            'https://www.googleapis.com/auth/drive.readonly' # Needed for listing/searching files
            ]
        credentials = Credentials.from_service_account_info(service_account_info, scopes=scopes)
        logger.debug("Successfully retrieved credentials from Secret Manager.")
        return credentials
    except Exception as e: 
        logger.error(f"Failed to get credentials from Secret Manager: {e}", exc_info=True)
        raise # Re-raise original error

# --- get_gspread_client (Caches the client) --- 
def get_gspread_client():
    """Authenticates and returns an authorized gspread client instance, caching it globally."""
    global gspread_authorized_client # Refer to global cache variable
    if gspread_authorized_client is None:
        logger.debug("Initializing gspread client...")
        try:
            credentials = get_service_account_credentials_from_secret_manager()
            gspread_authorized_client = gspread.authorize(credentials)
            logger.info("gspread client authorized successfully.")
        except Exception as e: 
            logger.error(f"Failed to get authorized gspread client: {e}", exc_info=True)
            gspread_authorized_client = None # Reset on error
            raise ConnectionError(f"Could not authorize gspread client...")
    return gspread_authorized_client

# --- find_sheet_id_by_loan_id_in_folder --- 
def find_sheet_id_by_loan_id_in_folder(loan_id):
    """Searches Drive folder for sheet named loan_id, returns sheet ID."""
    target_filename = str(loan_id).strip() # Use original case for filename search
    parent_folder_id = config.AMORTIZATION_SCHEDULES_FOLDER_ID
    if not parent_folder_id: logger.error("AMORTIZATION_SCHEDULES_FOLDER_ID not set."); return None
    
    logger.debug(f"Searching for Sheet file named exactly '{target_filename}' in Folder ID '{parent_folder_id}'")
    try:
        service = get_drive_service() 
        if not service: logger.error("Drive service not available for search."); return None
        
        # Note: Drive 'name =' query is often case-insensitive, but exact match is safer assumption
        query = f"'{parent_folder_id}' in parents and name = '{target_filename}' and mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false"
        
        results = service.files().list(
            q=query, 
            pageSize=5, # Should only find 1, limit results
            fields="files(id, name)" # Only need ID and name
            ).execute()
            
        items = results.get('files', [])
        if not items: 
            logger.warning(f"No Google Sheet named '{target_filename}' found in folder '{parent_folder_id}'.")
            return None
        elif len(items) > 1: 
            logger.warning(f"Found {len(items)} Sheets named '{target_filename}'... Returning first ID: {items[0]['id']}.")
            return items[0]['id']
        else: 
            found_id = items[0]['id']
            logger.info(f"Found Sheet for '{target_filename}'. File ID: {found_id}")
            return found_id
            
    except HttpError as error: logger.error(f"Drive API error searching for '{target_filename}': {error}", exc_info=True); return None
    except Exception as e: logger.error(f"Unexpected error during Drive search for '{target_filename}': {e}", exc_info=True); return None

# --- get_sheet_as_df (Using get_all_records) --- 
def get_sheet_as_df(gspread_client, sheet_id, sheet_name=None, max_retries=5, initial_delay=1, **kwargs):
    """
    Opens sheet, reads worksheet using get_all_records, returns Pandas DataFrame.
    Includes retries for quota errors. Relies on gspread type inference.
    """
    if gspread_client is None: logger.error("gspread_client is None..."); return pd.DataFrame()
    
    retries = 0; current_delay = initial_delay
    while retries < max_retries:
        try:
            spreadsheet = gspread_client.open_by_key(sheet_id)
            worksheet = spreadsheet.worksheet(sheet_name) if sheet_name else spreadsheet.sheet1
            
            logger.debug(f"Attempting read using get_all_records() for {sheet_id}/{sheet_name}")
            # kwargs can pass options like expected_headers, head, etc.
            records = worksheet.get_all_records(**kwargs) 
            
            if not records:
                headers = worksheet.row_values(1) 
                if not headers:
                    logger.warning(f"Sheet... '{sheet_name}' appears completely empty.")
                    return pd.DataFrame()
                else:
                     logger.warning(f"Sheet... '{sheet_name}' has headers but no data rows returned by get_all_records().")
                     df = pd.DataFrame(columns=[str(h).strip() for h in headers]) 
                     return df 
            
            df = pd.DataFrame.from_records(records) 
            df.columns = [str(h).strip() for h in df.columns] # Clean headers

            logger.debug(f"Successfully read sheet using get_all_records()... Columns: {df.columns.tolist()}")
            return df

        except gspread.exceptions.APIError as e:
            if hasattr(e, 'response') and hasattr(e.response, 'status_code') and e.response.status_code == 429:
                retries += 1;
                if retries >= max_retries: logger.error(f"Quota exceeded reading... Max retries. Error: {e}"); raise
                wait_time = current_delay * (2 ** (retries - 1)); logger.warning(f"Quota exceeded reading... Retrying in {wait_time:.2f}s..."); time.sleep(wait_time)
            else: logger.error(f"Non-quota APIError reading sheet...: {e}", exc_info=True); raise
        except gspread.exceptions.WorksheetNotFound: logger.error(f"Worksheet '{sheet_name}' not found..."); return pd.DataFrame()
        except Exception as e: logger.error(f"General error reading sheet...: {e}", exc_info=True); return pd.DataFrame()
        
    logger.error(f"Failed read sheet... after {max_retries} retries."); return pd.DataFrame()


# --- update_worksheet_from_df (Includes JSON serialization fix and retries) --- 
def update_worksheet_from_df(gspread_client, sheet_id, sheet_name, df_to_write, max_retries=3, initial_delay=1.5):
    """
    Updates sheet with DataFrame. Ensures data JSON serializable. Retries on quota errors.
    """
    if gspread_client is None: logger.error(f"gspread_client is None..."); return False
    if df_to_write is None: logger.error(f"DataFrame to write is None..."); return False
    
    # Prepare list of lists, ensuring JSON compatibility
    if df_to_write.empty:
        if not df_to_write.columns.empty: list_of_lists_for_gspread = [df_to_write.columns.tolist()]
        else: list_of_lists_for_gspread = []
    else:
        headers = df_to_write.columns.tolist()
        data_rows = []
        # Iterate through DataFrame rows efficiently
        for row_tuple in df_to_write.itertuples(index=False, name=None):
            processed_row = []
            for value in row_tuple:
                # --- Convert types to JSON safe primitives ---
                if pd.isna(value):
                    processed_row.append(None) # Use None for JSON null
                elif isinstance(value, (datetime, date, pd.Timestamp)):
                    try: # Format date/datetime as ISO string
                        if isinstance(value, date) and not isinstance(value, datetime): processed_row.append(value.strftime('%Y-%m-%d'))
                        elif isinstance(value, pd.Timestamp) and value.normalize() == value: processed_row.append(value.strftime('%Y-%m-%d'))
                        else: processed_row.append(value.isoformat()) 
                    except AttributeError: processed_row.append(None) 
                elif isinstance(value, (int, float)): 
                    processed_row.append(value) # Keep standard numbers
                elif isinstance(value, bool):
                    processed_row.append(value) # Keep standard booleans
                elif isinstance(value, Decimal):
                    processed_row.append(str(value)) # Convert Decimal to string
                else:
                    processed_row.append(str(value)) # Convert anything else to string
            data_rows.append(processed_row)
        list_of_lists_for_gspread = [headers] + data_rows
    
    # Retry logic for API calls
    retries = 0; current_delay = initial_delay
    while retries < max_retries:
        try:
            spreadsheet = gspread_client.open_by_key(sheet_id); worksheet = spreadsheet.worksheet(sheet_name)
            worksheet.clear(); 
            if list_of_lists_for_gspread: 
                worksheet.update(list_of_lists_for_gspread, value_input_option='USER_ENTERED')
                logger.info(f"Successfully updated worksheet '{sheet_name}'...")
            else: 
                logger.info(f"Worksheet '{sheet_name}' was cleared (empty input).")
            return True 
        except gspread.exceptions.APIError as e:
            if hasattr(e, 'response') and hasattr(e.response, 'status_code') and e.response.status_code == 429:
                retries += 1;
                if retries >= max_retries: logger.error(f"Write quota exceeded... Max retries. Error: {e}"); return False
                wait_time = current_delay * (2 ** (retries - 1)); logger.warning(f"Write quota exceeded... Retrying in {wait_time:.2f}s..."); time.sleep(wait_time)
            else: logger.error(f"Non-quota APIError updating sheet...: {e}", exc_info=True); return False
        except gspread.exceptions.WorksheetNotFound: logger.error(f"Worksheet '{sheet_name}' not found..."); return False
        except Exception as e: logger.error(f"General error updating sheet...: {e}", exc_info=True); return False
    logger.error(f"Failed to update sheet... after {max_retries} retries."); return False