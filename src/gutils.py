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

from . import config 

logger = logging.getLogger(__name__)
drive_service_client = None 

# --- Helper function to clean/convert currency strings to float ---
def safe_string_to_float(value_str, context=""):
    """Cleans string (removes $, commas) and converts to float, returns pd.NA on error."""
    if pd.isna(value_str) or str(value_str).strip() == "": return pd.NA 
    try:
        cleaned_str = str(value_str).replace('$', '').replace(',', '').strip()
        if cleaned_str.startswith('(') and cleaned_str.endswith(')'): cleaned_str = '-' + cleaned_str[1:-1]
        return float(cleaned_str)
    except (ValueError, TypeError): logger.warning(f"Could not convert '{value_str}' to float for {context}. Returning pd.NA."); return pd.NA 

# --- Helper function to clean/convert string to Decimal ---
def safe_string_to_decimal(value_str, context=""):
    """Cleans string (removes $, commas) and converts to Decimal, returns Decimal('NaN') on error."""
    if pd.isna(value_str) or str(value_str).strip() == "": return Decimal('NaN')
    try:
        cleaned_str = str(value_str).replace('$', '').replace(',', '').strip()
        if cleaned_str.startswith('(') and cleaned_str.endswith(')'): cleaned_str = '-' + cleaned_str[1:-1]
        return Decimal(cleaned_str)
    except (TypeError, InvalidOperation): logger.warning(f"Could not convert '{value_str}' to Decimal for {context}. Returning NaN."); return Decimal('NaN')

# --- Helper Function to List Files in Drive Folder ---
def get_loan_ids_from_drive_folder(folder_id):
    """Lists Google Sheet files in Drive folder, returns their names (assumed LoanIDs)."""
    loan_ids = []; drive_service = None; page_token = None
    try:
        drive_service = get_drive_service(); 
        if not drive_service: logger.error("Cannot get Drive service to list loan IDs."); return []
        logger.info(f"Listing Google Sheets in Drive Folder ID: {folder_id}")
        request = drive_service.files().list(q=f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.spreadsheet' and trashed=false", pageSize=1000, fields="nextPageToken, files(id, name)", pageToken=page_token)
        while request is not None:
            results = request.execute(); items = results.get('files', [])
            if not items and not loan_ids: 
                 if page_token is None: logger.warning(f"No sheets found in folder: {folder_id}"); return []
                 else: break 
            for item in items:
                filename = item.get('name')
                if filename: loan_ids.append(filename) 
                else: logger.warning(f"Found file with ID {item.get('id')} but no name.")
            request = drive_service.files().list_next(previous_request=request, previous_response=results)
        logger.info(f"Found {len(loan_ids)} potential LoanIDs in Drive folder.")
        return loan_ids
    except HttpError as error: logger.error(f"API error listing files in Drive folder {folder_id}: {error}", exc_info=True); return []
    except Exception as e: logger.error(f"Failed to list files in Drive folder {folder_id}: {e}", exc_info=True); return []

# --- get_drive_service ---
def get_drive_service():
    """Creates and returns a Google Drive API service client using credentials."""
    global drive_service_client
    if drive_service_client is None:
        logger.debug("Initializing Google Drive service client...")
        try:
            credentials = get_service_account_credentials_from_secret_manager() 
            drive_service_client = build('drive', 'v3', credentials=credentials, cache_discovery=False)
            logger.info("Google Drive API service client created successfully.")
        except Exception as e:
            logger.error(f"Failed to create Drive API service client: {e}", exc_info=True)
            drive_service_client = None 
            raise ConnectionError(f"Could not create Drive service client: {e}")
    return drive_service_client

# --- get_service_account_credentials_from_secret_manager --- 
def get_service_account_credentials_from_secret_manager():
    try:
        sm_client = secretmanager.SecretManagerServiceClient()
        response = sm_client.access_secret_version(request={"name": config.SERVICE_ACCOUNT_SECRET_RESOURCE_NAME})
        secret_payload_str = response.payload.data.decode("UTF-8")
        service_account_info = json.loads(secret_payload_str)
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive.file', 'https://www.googleapis.com/auth/drive.readonly']
        credentials = Credentials.from_service_account_info(service_account_info, scopes=scopes)
        return credentials
    except Exception as e: logger.error(f"Failed to get credentials from Secret Manager: {e}", exc_info=True); raise

# --- get_gspread_client --- 
def get_gspread_client():
    try:
        credentials = get_service_account_credentials_from_secret_manager()
        gspread_client = gspread.authorize(credentials)
        return gspread_client
    except Exception as e: logger.error(f"Failed to get authorized gspread client: {e}", exc_info=True); raise ConnectionError(f"Could not authorize gspread client...")

# --- find_sheet_id_by_loan_id_in_folder --- 
def find_sheet_id_by_loan_id_in_folder(loan_id):
    target_filename = str(loan_id).strip()
    parent_folder_id = config.AMORTIZATION_SCHEDULES_FOLDER_ID
    if not parent_folder_id: logger.error("AMORTIZATION_SCHEDULES_FOLDER_ID not set."); return None
    logger.debug(f"Searching for Sheet '{target_filename}' in Folder ID '{parent_folder_id}'")
    try:
        service = get_drive_service() 
        if not service: logger.error("Drive service not available."); return None
        query = f"'{parent_folder_id}' in parents and name = '{target_filename}' and mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false"
        results = service.files().list(q=query, pageSize=5, fields="files(id, name)").execute()
        items = results.get('files', [])
        if not items: logger.warning(f"No Sheet named '{target_filename}' found..."); return None
        elif len(items) > 1: logger.warning(f"Found {len(items)} Sheets named '{target_filename}'... Returning first."); return items[0]['id']
        else: logger.info(f"Found Sheet for '{target_filename}'. File ID: {items[0]['id']}"); return items[0]['id']
    except HttpError as error: logger.error(f"Drive API error searching for '{target_filename}': {error}", exc_info=True); return None
    except Exception as e: logger.error(f"Unexpected error during Drive search: {e}", exc_info=True); return None

# --- get_sheet_as_df --- 
def get_sheet_as_df(gspread_client, sheet_id, sheet_name=None, max_retries=5, initial_delay=1, **kwargs):
    if gspread_client is None: logger.error("gspread_client is None..."); return pd.DataFrame()
    retries = 0; current_delay = initial_delay
    while retries < max_retries:
        try:
            spreadsheet = gspread_client.open_by_key(sheet_id); worksheet = spreadsheet.worksheet(sheet_name) if sheet_name else spreadsheet.sheet1
            all_values = worksheet.get_all_values(value_render_option='FORMATTED_VALUE', **kwargs) 
            if not all_values: logger.warning(f"Sheet... empty."); return pd.DataFrame()
            headers = [str(h).strip() for h in all_values[0]]; records = all_values[1:]
            if not records: logger.warning(f"Sheet has headers but no data..."); return pd.DataFrame(columns=headers)
            df = pd.DataFrame(records, columns=headers); logger.debug(f"Successfully read sheet..."); return df
        except gspread.exceptions.APIError as e:
            if hasattr(e, 'response') and hasattr(e.response, 'status_code') and e.response.status_code == 429:
                retries += 1;
                if retries >= max_retries: logger.error(f"Quota exceeded reading... Max retries. Error: {e}"); raise
                wait_time = current_delay * (2 ** (retries - 1)); logger.warning(f"Quota exceeded reading... Retrying in {wait_time:.2f}s..."); time.sleep(wait_time)
            else: logger.error(f"Non-quota APIError reading sheet...: {e}", exc_info=True); raise
        except gspread.exceptions.WorksheetNotFound: logger.error(f"Worksheet '{sheet_name}' not found..."); return pd.DataFrame()
        except Exception as e: logger.error(f"General error reading sheet...: {e}", exc_info=True); return pd.DataFrame()
    logger.error(f"Failed read sheet... after {max_retries} retries."); return pd.DataFrame()


# --- update_worksheet_from_df (CORRECTED for JSON Serialization) --- 
def update_worksheet_from_df(gspread_client, sheet_id, sheet_name, df_to_write, max_retries=3, initial_delay=1.5):
    """
    Updates a Google Sheet worksheet with data from a Pandas DataFrame.
    Ensures all data is JSON serializable before sending.
    """
    if gspread_client is None: logger.error(f"gspread_client is None..."); return False
    if df_to_write is None: logger.error(f"DataFrame to write is None..."); return False
    
    # Prepare list of lists, ensuring JSON compatibility
    if df_to_write.empty:
        # Handle empty DataFrame (write only headers or clear)
        if not df_to_write.columns.empty:
             logger.info(f"Writing only headers to sheet (ID: {sheet_id}, Name: '{sheet_name}').")
             list_of_lists_for_gspread = [df_to_write.columns.tolist()]
        else:
             logger.info(f"Input DataFrame is empty, clearing sheet (ID: {sheet_id}, Name: '{sheet_name}').")
             list_of_lists_for_gspread = []
    else:
        # Convert DataFrame to list of lists, explicitly handling types
        # Headers first
        headers = df_to_write.columns.tolist()
        data_rows = []
        for index, row in df_to_write.iterrows():
            processed_row = []
            for col_name in headers: # Iterate based on header order
                value = row[col_name]
                # --- Convert types to JSON safe primitives ---
                if pd.isna(value):
                    processed_row.append(None) # Use None for JSON null
                elif isinstance(value, (datetime, date, pd.Timestamp)):
                    # Format dates/timestamps as ISO 8601 strings (common practice)
                    try:
                        # Check if it's date only (no time component or midnight)
                        if isinstance(value, date) and not isinstance(value, datetime):
                             processed_row.append(value.strftime('%Y-%m-%d'))
                        elif isinstance(value, pd.Timestamp) and value.normalize() == value:
                             processed_row.append(value.strftime('%Y-%m-%d'))
                        else: # Assume datetime
                             processed_row.append(value.isoformat()) 
                    except AttributeError: # Handle potential NaT cases missed earlier
                         processed_row.append(None) 
                elif isinstance(value, (int, float, bool)):
                    # Keep standard numeric/boolean types
                    processed_row.append(value)
                elif isinstance(value, Decimal):
                    # Convert Decimal to string for JSON (or float if precision loss is acceptable)
                    processed_row.append(str(value)) 
                else:
                    # Convert anything else to string
                    processed_row.append(str(value))
            data_rows.append(processed_row)
            
        list_of_lists_for_gspread = [headers] + data_rows
    
    # Retry logic for API calls
    retries = 0; current_delay = initial_delay
    while retries < max_retries:
        try:
            spreadsheet = gspread_client.open_by_key(sheet_id)
            worksheet = spreadsheet.worksheet(sheet_name)
            
            worksheet.clear() # Clear existing content first
            if list_of_lists_for_gspread: 
                # Update using the prepared list of lists
                worksheet.update(list_of_lists_for_gspread, value_input_option='USER_ENTERED')
                logger.info(f"Successfully updated worksheet '{sheet_name}' in sheet (ID: {sheet_id}).")
            else: 
                logger.info(f"Worksheet '{sheet_name}' was cleared (empty input).")
            return True # Success

        except gspread.exceptions.APIError as e:
            # Handle Quota errors with retry
            if hasattr(e, 'response') and hasattr(e.response, 'status_code') and e.response.status_code == 429:
                retries += 1;
                if retries >= max_retries: logger.error(f"Write quota exceeded... Max retries. Error: {e}"); return False
                wait_time = current_delay * (2 ** (retries - 1)); logger.warning(f"Write quota exceeded... Retrying in {wait_time:.2f}s..."); time.sleep(wait_time)
            else: logger.error(f"Non-quota APIError updating sheet...: {e}", exc_info=True); return False
        except gspread.exceptions.WorksheetNotFound: logger.error(f"Worksheet '{sheet_name}' not found..."); return False
        except Exception as e: logger.error(f"General error updating sheet...: {e}", exc_info=True); return False
        
    logger.error(f"Failed to update sheet... after {max_retries} retries."); return False


# --- find_sheet_id_by_loan_id_in_folder (Removed, use version defined above) ---
# --- get_amortization_sheet_id (Removed, use find_sheet_id... above) ---