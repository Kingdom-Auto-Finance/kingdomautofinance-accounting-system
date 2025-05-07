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
from decimal import Decimal, InvalidOperation # Import Decimal here
from . import config 

logger = logging.getLogger(__name__)
drive_service_client = None # Cache for Drive API client

# --- Helper function to clean/convert currency strings to float ---
def safe_string_to_float(value_str, context=""):
    """Cleans string (removes $, commas) and converts to float, returns pd.NA on error."""
    if pd.isna(value_str) or str(value_str).strip() == "":
        return pd.NA 
    try:
        cleaned_str = str(value_str).replace('$', '').replace(',', '').strip()
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
        if cleaned_str.startswith('(') and cleaned_str.endswith(')'): cleaned_str = '-' + cleaned_str[1:-1]
        return Decimal(cleaned_str)
    except (TypeError, InvalidOperation): 
        logger.warning(f"Could not convert '{value_str}' to Decimal for {context}. Returning NaN.")
        return Decimal('NaN')

# --- Helper Function to List Files in Drive Folder ---
def get_loan_ids_from_drive_folder(folder_id):
    """Lists Google Sheet files in Drive folder, returns their names (assumed LoanIDs)."""
    loan_ids = []
    drive_service = None
    page_token = None
    try:
        drive_service = get_drive_service() # Use the function below to get/cache service
        if not drive_service: logger.error("Cannot get Drive service to list loan IDs."); return []
        
        logger.info(f"Listing Google Sheets in Drive Folder ID: {folder_id}")
        request = drive_service.files().list(
                q=f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.spreadsheet' and trashed=false",
                pageSize=1000, # Get more per page if possible, max 1000
                fields="nextPageToken, files(id, name)", 
                pageToken=page_token
            )
        while request is not None:
            results = request.execute()
            items = results.get('files', [])
            
            # Initial check modified slightly
            # if not items and page_token is None and not loan_ids: # More precise check for truly empty on first page
            if not items and not loan_ids: # Simpler check: if no items on a page AND we haven't found any yet
                 logger.warning(f"No Google Sheet files found in the specified Drive folder: {folder_id}")
                 # If it was the first page (page_token is None), return [], otherwise break (might be empty last page)
                 if page_token is None: return []
                 else: break 

            for item in items:
                filename = item.get('name')
                if filename: 
                    loan_ids.append(filename) 
                else: 
                    logger.warning(f"Found file with ID {item.get('id')} but no name in folder {folder_id}.")
            
            # Prepare request for the next page
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
    """Creates and returns a Google Drive API service client using credentials."""
    global drive_service_client
    if drive_service_client is None:
        logger.debug("Initializing Google Drive service client...")
        try:
            credentials = get_service_account_credentials_from_secret_manager() 
            drive_service_client = build('drive', 'v3', credentials=credentials, cache_discovery=False) # Disable discovery cache for potential dynamic envs
            logger.info("Google Drive API service client created successfully.")
        except Exception as e:
            logger.error(f"Failed to create Google Drive API service client: {e}", exc_info=True)
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
        # logger.info("Successfully retrieved credentials from Secret Manager.") # Reduce log noise
        return credentials
    except Exception as e: logger.error(f"Failed to get credentials from Secret Manager: {e}", exc_info=True); raise

# --- get_gspread_client --- 
def get_gspread_client():
    try:
        credentials = get_service_account_credentials_from_secret_manager()
        gspread_client = gspread.authorize(credentials)
        # logger.info("gspread client authorized successfully.") # Reduce log noise
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
        if not items: logger.warning(f"No Sheet named '{target_filename}' found in folder '{parent_folder_id}'."); return None
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
            # Read all as strings for consistency
            all_values = worksheet.get_all_values(value_render_option='FORMATTED_VALUE', **kwargs) # Use formatted value
            if not all_values: logger.warning(f"Sheet... empty."); return pd.DataFrame()
            headers = [str(h).strip() for h in all_values[0]]; records = all_values[1:]
            if not records: logger.warning(f"Sheet has headers but no data..."); return pd.DataFrame(columns=headers)
            df = pd.DataFrame(records, columns=headers); logger.debug(f"Successfully read sheet..."); return df
        except gspread.exceptions.APIError as e:
            if hasattr(e, 'response') and hasattr(e.response, 'status_code') and e.response.status_code == 429:
                retries += 1;
                if retries >= max_retries: logger.error(f"Quota exceeded... Max retries reached. Error: {e}"); raise
                wait_time = current_delay * (2 ** (retries - 1)); logger.warning(f"Quota exceeded reading... Retrying in {wait_time:.2f}s..."); time.sleep(wait_time)
            else: logger.error(f"Non-quota APIError reading sheet...: {e}", exc_info=True); raise
        except gspread.exceptions.WorksheetNotFound: logger.error(f"Worksheet '{sheet_name}' not found..."); return pd.DataFrame()
        except Exception as e: logger.error(f"General error reading sheet...: {e}", exc_info=True); return pd.DataFrame()
    logger.error(f"Failed read sheet... after {max_retries} retries."); return pd.DataFrame()


# --- update_worksheet_from_df --- 
def update_worksheet_from_df(gspread_client, sheet_id, sheet_name, df_to_write, max_retries=3, initial_delay=1.5):
    if gspread_client is None: logger.error(f"gspread_client is None..."); return False
    if df_to_write is None: logger.error(f"DataFrame to write is None..."); return False
    
    if df_to_write.empty and not df_to_write.columns.empty: list_of_lists_for_gspread = [df_to_write.columns.tolist()]
    elif df_to_write.empty and df_to_write.columns.empty: list_of_lists_for_gspread = []
    else:
        # Prepare data carefully for writing
        df_prepared = df_to_write.copy()
        # Convert columns to object type first to handle mixed types / prevent Pandas type inference issues before fillna
        for col in df_prepared.columns:
             df_prepared[col] = df_prepared[col].astype(object)
        
        # Fill NA values with empty string ONLY AFTER ensuring object type
        df_prepared.fillna('', inplace=True)
        
        # Convert back to list of lists, ensuring headers are present
        list_of_lists_for_gspread = [df_prepared.columns.tolist()] + df_prepared.values.tolist()
        
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
                if retries >= max_retries: logger.error(f"Write quota exceeded... Max retries reached. Error: {e}"); return False
                wait_time = current_delay * (2 ** (retries - 1)); logger.warning(f"Write quota exceeded... Retrying in {wait_time:.2f}s..."); time.sleep(wait_time)
            else: logger.error(f"Non-quota APIError updating sheet...: {e}", exc_info=True); return False
        except gspread.exceptions.WorksheetNotFound: logger.error(f"Worksheet '{sheet_name}' not found..."); return False
        except Exception as e: logger.error(f"General error updating sheet...: {e}", exc_info=True); return False
    logger.error(f"Failed to update sheet... after {max_retries} retries."); return False