# src/gutils.py
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from google.cloud import secretmanager
import json
import logging
import time
from . import config

logger = logging.getLogger(__name__)

# get_service_account_credentials_from_secret_manager() - NO CHANGES
# get_gspread_client() - NO CHANGES

def get_sheet_as_df(gspread_client, sheet_id, sheet_name=None, max_retries=5, initial_delay=1, **kwargs):
    """
    Opens a Google Sheet by its ID, reads a specific worksheet,
    and returns its content as a Pandas DataFrame.
    kwargs can be passed to worksheet.get_all_records or get_all_values.
    By default, reads values as strings using get_all_values for consistent parsing later.
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
            
            # Get all values as strings. This provides raw data for consistent parsing.
            # gspread by default tries to infer types with get_all_records(), 
            # but get_all_values() with value_render_option='FORMATTED_VALUE' or 'UNFORMATTED_VALUE'
            # often gives more predictable string output. 'FORMATTED_VALUE' is often like what user sees.
            # Let's use default get_all_values() which is usually good for string representation.
            all_values = worksheet.get_all_values(**kwargs) 
            
            if not all_values:
                logger.warning(f"Sheet (ID: {sheet_id}, Name: '{sheet_name or 'first sheet'}') is empty.")
                return pd.DataFrame()
            
            headers = [str(h).strip() for h in all_values[0]] # Ensure headers are strings and stripped
            records = all_values[1:]
            df = pd.DataFrame(records, columns=headers)

            # Do NOT do aggressive type conversion here. Let the calling function handle it.
            # Just ensure all data from sheet is initially treated as object/string type from Pandas perspective.
            # Pandas will often infer 'object' dtype if mixed types or strings are present.
            # We will do explicit conversion in payment_processor.py.

            logger.debug(f"Successfully read sheet (ID: {sheet_id}, Name: '{sheet_name}') with {len(df)} rows. Headers: {headers}")
            return df

        except gspread.exceptions.APIError as e:
            # ... (quota handling as before) ...
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
    It clears the existing sheet content and then writes the new data, including headers.
    Uses 'USER_ENTERED' value input option for better type interpretation by Google Sheets.
    """
    if gspread_client is None:
        logger.error(f"gspread_client is None in update_worksheet_from_df for sheet (ID: {sheet_id}, Name: '{sheet_name}'). Cannot proceed.")
        return False
    if df_to_write is None: # Check if DataFrame itself is None
        logger.error(f"DataFrame to write to sheet (ID: {sheet_id}, Name: '{sheet_name}') is None. Aborting update.")
        return False
    # Also check if DataFrame is empty but has columns (only headers to write) or completely empty
    if df_to_write.empty and not df_to_write.columns.empty:
        logger.info(f"DataFrame for sheet (ID: {sheet_id}, Name: '{sheet_name}') has headers but no data rows. Writing only headers.")
        list_of_lists_for_gspread = [df_to_write.columns.tolist()]
    elif df_to_write.empty and df_to_write.columns.empty:
        logger.info(f"DataFrame for sheet (ID: {sheet_id}, Name: '{sheet_name}') is completely empty. Clearing sheet.")
        list_of_lists_for_gspread = [] # Will result in a clear sheet
    else: # DataFrame has data
        df_prepared = df_to_write.copy()
        for col in df_prepared.columns:
            # Handle datetimes (should be stored as datetime objects in DataFrame if parsed correctly)
            if pd.api.types.is_datetime64_any_dtype(df_prepared[col]):
                # gspread with USER_ENTERED often prefers datetime objects directly or well-formatted strings.
                # Let's provide datetime objects where possible, and string for NaT.
                # However, to be safe with bulk .update(), stringifying is more predictable.
                is_date_only = (df_prepared[col].dt.normalize() == df_prepared[col]).all() if df_prepared[col].notna().any() else True
                if is_date_only:
                    df_prepared[col] = df_prepared[col].apply(lambda x: x.strftime('%Y-%m-%d') if pd.notna(x) else '')
                else:
                    df_prepared[col] = df_prepared[col].apply(lambda x: x.strftime('%Y-%m-%d %H:%M:%S') if pd.notna(x) else '')
            elif pd.api.types.is_bool_dtype(df_prepared[col]):
                df_prepared[col] = df_prepared[col].apply(
                    lambda x: 'TRUE' if pd.notna(x) and x is True else ('FALSE' if pd.notna(x) and x is False else '')
                )
            else:
                # For other types, including numeric, convert NaN to empty string.
                # Numbers should be passed as numbers (int, float) for USER_ENTERED to work best.
                # fillna('') converts numbers to strings. This might be too aggressive.
                # Let's try to preserve numeric types and only fillna for object columns or convert all to string as a last resort.
                if df_prepared[col].dtype == 'object':
                    df_prepared[col] = df_prepared[col].fillna('')
                else: # For numeric, bool already handled.
                    # gspread typically handles Python None for missing numeric/bool, which Pandas NaNs become.
                    # Or convert all to string to be absolutely safe for .update() if issues persist.
                    df_prepared[col] = df_prepared[col].astype(str).replace({'nan': '', 'NaT': ''})


        list_of_lists_for_gspread = [df_prepared.columns.tolist()] + df_prepared.values.tolist()
    
    try:
        spreadsheet = gspread_client.open_by_key(sheet_id)
        worksheet = spreadsheet.worksheet(sheet_name)
        
        worksheet.clear() # Clear all existing data and formatting
        if list_of_lists_for_gspread: # Only update if there's something to write (headers or data)
            worksheet.update(list_of_lists_for_gspread, value_input_option='USER_ENTERED')
            logger.info(f"Successfully updated worksheet '{sheet_name}' in sheet (ID: {sheet_id}).")
        else:
            logger.info(f"Worksheet '{sheet_name}' in sheet (ID: {sheet_id}) was cleared as input DataFrame was empty.")
        return True
    except gspread.exceptions.WorksheetNotFound:
        logger.error(f"Worksheet '{sheet_name}' not found in spreadsheet (ID: {sheet_id}) for updating.")
        return False
    except Exception as e:
        logger.error(f"Error updating sheet (ID: {sheet_id}, Name: '{sheet_name}'): {e}", exc_info=True)
        return False

# get_amortization_sheet_id() - NO CHANGES