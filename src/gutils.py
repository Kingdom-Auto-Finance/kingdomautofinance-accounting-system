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
from . import config

logger = logging.getLogger(__name__)
drive_service_client = None

# --- get_drive_service --- (No changes)
def get_drive_service():
    global drive_service_client
    if drive_service_client is None:
        logger.debug("Initializing Google Drive service client...")
        try:
            credentials = get_service_account_credentials_from_secret_manager() 
            drive_service_client = build('drive', 'v3', credentials=credentials)
            logger.info("Google Drive API service client created successfully.")
        except Exception as e:
            logger.error(f"Failed to create Google Drive API service client: {e}", exc_info=True)
            drive_service_client = None 
            raise ConnectionError(f"Could not create Drive service client: {e}")
    return drive_service_client

# --- get_service_account_credentials_from_secret_manager --- (No changes)
def get_service_account_credentials_from_secret_manager():
    try:
        sm_client = secretmanager.SecretManagerServiceClient()
        response = sm_client.access_secret_version(request={"name": config.SERVICE_ACCOUNT_SECRET_RESOURCE_NAME})
        secret_payload_str = response.payload.data.decode("UTF-8")
        service_account_info = json.loads(secret_payload_str)
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive.file', 'https://www.googleapis.com/auth/drive.readonly']
        credentials = Credentials.from_service_account_info(service_account_info, scopes=scopes)
        logger.info("Successfully retrieved credentials from Secret Manager (including Drive scopes).")
        return credentials
    except Exception as e: logger.error(f"Failed to get credentials from Secret Manager: {e}", exc_info=True); raise

# --- get_gspread_client --- (No changes)
def get_gspread_client():
    try:
        credentials = get_service_account_credentials_from_secret_manager()
        gspread_client = gspread.authorize(credentials)
        logger.info("gspread client has been successfully authorized.")
        return gspread_client
    except Exception as e: logger.error(f"Failed to get authorized gspread client. Error: {e}", exc_info=True); raise ConnectionError(f"Could not authorize gspread client. Underlying error: {type(e).__name__} - {e}")

# --- find_sheet_id_by_loan_id_in_folder --- (No changes needed for quota, but ensure it uses get_drive_service)
def find_sheet_id_by_loan_id_in_folder(loan_id):
    target_filename = str(loan_id).strip()
    parent_folder_id = config.AMORTIZATION_SCHEDULES_FOLDER_ID
    if not parent_folder_id: logger.error("AMORTIZATION_SCHEDULES_FOLDER_ID not set."); return None
    logger.debug(f"Searching for Sheet '{target_filename}' in Drive Folder ID '{parent_folder_id}'")
    try:
        service = get_drive_service() # Use the potentially cached service client
        if not service: logger.error("Drive service client not available."); return None
        query = f"'{parent_folder_id}' in parents and name = '{target_filename}' and mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false"
        results = service.files().list(q=query, pageSize=5, fields="files(id, name)").execute()
        items = results.get('files', [])
        if not items: logger.warning(f"No Google Sheet named '{target_filename}' found..."); return None
        elif len(items) > 1: logger.warning(f"Found {len(items)} Sheets named '{target_filename}'... Returning first."); return items[0]['id']
        else: logger.info(f"Found Google Sheet for LoanID '{target_filename}'. File ID: {items[0]['id']}"); return items[0]['id']
    except HttpError as error: logger.error(f"Drive API error searching for '{target_filename}': {error}", exc_info=True); return None
    except Exception as e: logger.error(f"Unexpected error during Drive search for '{target_filename}': {e}", exc_info=True); return None


# --- get_sheet_as_df --- (Retry logic already present, no changes needed)
def get_sheet_as_df(gspread_client, sheet_id, sheet_name=None, max_retries=5, initial_delay=1, **kwargs):
    if gspread_client is None: logger.error("gspread_client is None..."); return pd.DataFrame()
    retries = 0; current_delay = initial_delay
    while retries < max_retries:
        try:
            spreadsheet = gspread_client.open_by_key(sheet_id)
            worksheet = spreadsheet.worksheet(sheet_name) if sheet_name else spreadsheet.sheet1
            all_values = worksheet.get_all_values(**kwargs) 
            if not all_values: logger.warning(f"Sheet... empty."); return pd.DataFrame()
            headers = [str(h).strip() for h in all_values[0]]; records = all_values[1:]
            if not records: logger.warning(f"Sheet has headers but no data..."); return pd.DataFrame(columns=headers)
            df = pd.DataFrame(records, columns=headers); logger.debug(f"Successfully read sheet..."); return df
        except gspread.exceptions.APIError as e:
            if hasattr(e, 'response') and hasattr(e.response, 'status_code') and e.response.status_code == 429:
                retries += 1;
                if retries >= max_retries: logger.error(f"Quota exceeded reading... Max retries reached. Error: {e}"); raise
                wait_time = current_delay * (2 ** (retries - 1)); logger.warning(f"Quota exceeded reading... Retrying in {wait_time:.2f}s..."); time.sleep(wait_time)
            else: logger.error(f"Non-quota APIError reading sheet...: {e}", exc_info=True); raise
        except gspread.exceptions.WorksheetNotFound: logger.error(f"Worksheet '{sheet_name}' not found..."); return pd.DataFrame()
        except Exception as e: logger.error(f"General error reading sheet...: {e}", exc_info=True); return pd.DataFrame()
    logger.error(f"Failed read sheet... after {max_retries} retries."); return pd.DataFrame()


# --- update_worksheet_from_df (Add optional retry logic for writes) ---
def update_worksheet_from_df(gspread_client, sheet_id, sheet_name, df_to_write, max_retries=3, initial_delay=1.5): # Increased initial delay slightly for writes
    """
    Updates a Google Sheet worksheet with data from a Pandas DataFrame.
    Includes optional exponential backoff for write quota errors.
    """
    if gspread_client is None: logger.error(f"gspread_client is None..."); return False
    if df_to_write is None: logger.error(f"DataFrame to write is None..."); return False
    
    # Prepare list of lists for gspread update (logic from previous version)
    if df_to_write.empty and not df_to_write.columns.empty: list_of_lists_for_gspread = [df_to_write.columns.tolist()]
    elif df_to_write.empty and df_to_write.columns.empty: list_of_lists_for_gspread = []
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
                 df_prepared[col] = df_prepared[col].astype(str).replace({'nan': '', '<NA>': '', 'NaT': ''}) # Ensure safe strings
        list_of_lists_for_gspread = [df_prepared.columns.tolist()] + df_prepared.values.tolist()

    retries = 0
    current_delay = initial_delay
    while retries < max_retries:
        try:
            spreadsheet = gspread_client.open_by_key(sheet_id)
            worksheet = spreadsheet.worksheet(sheet_name)
            
            worksheet.clear() 
            if list_of_lists_for_gspread: 
                worksheet.update(list_of_lists_for_gspread, value_input_option='USER_ENTERED')
                logger.info(f"Successfully updated worksheet '{sheet_name}' in sheet (ID: {sheet_id}).")
            else:
                logger.info(f"Worksheet '{sheet_name}' cleared (empty input).")
            return True # Success! Exit loop.

        except gspread.exceptions.APIError as e:
            # Check for write quota errors (often 429, but could be others like 403 if concurrent writes are too fast)
            if hasattr(e, 'response') and hasattr(e.response, 'status_code') and e.response.status_code == 429:
                retries += 1
                if retries >= max_retries: 
                    logger.error(f"Write quota exceeded for sheet (ID: {sheet_id}, Name: '{sheet_name}'). Max retries reached. Error: {e}")
                    return False # Indicate failure after retries
                wait_time = current_delay * (2 ** (retries - 1))
                logger.warning(f"Write quota exceeded for sheet (ID: {sheet_id}, Name: '{sheet_name}'). Retrying in {wait_time:.2f}s... (Attempt {retries}/{max_retries})")
                time.sleep(wait_time)
            else: # Different API error during write
                logger.error(f"Non-quota APIError updating sheet (ID: {sheet_id}, Name: '{sheet_name}'): {e}", exc_info=True)
                return False # Indicate failure
        except gspread.exceptions.WorksheetNotFound: 
            logger.error(f"Worksheet '{sheet_name}' not found for update..."); return False
        except Exception as e: 
            logger.error(f"General error updating sheet...: {e}", exc_info=True); return False
            
    # If loop finishes due to retries failing
    logger.error(f"Failed to update sheet (ID: {sheet_id}, Name: '{sheet_name}') after {max_retries} retries due to persistent quota issues.")
    return False