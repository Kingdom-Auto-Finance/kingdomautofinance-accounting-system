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

            # Replace empty strings with pd.NA to assist type conversion
            df.replace('', pd.NA, inplace=True)

            for col in df.columns:
                col_lower = str(col).lower()
                # Attempt numeric conversion
                if any(num_keyword in col_lower for num_keyword in ['amount', 'balance', 'principal', 'interest', 'fee', 'rate', 'payment', 'number', '#', 'id', 'term', 'period', 'count', 'qty', 'value']): # Added 'value' for LoanTerms
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                
                # Attempt datetime conversion (YYYY-MM-DD focus)
                if 'date' in col_lower or 'due' in col_lower or 'start' in col_lower or 'end' in col_lower or 'timestamp' in col_lower:
                    # Try specific format first for consistency, then general parsing
                    try:
                        # Coerce will turn unparseable to NaT
                        df[col] = pd.to_datetime(df[col], format='%Y-%m-%d', errors='coerce')
                    except TypeError: # If already datetime objects from a previous pd.to_datetime
                        df[col] = pd.to_datetime(df[col], errors='coerce') # General fallback coercion

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

# update_worksheet_from_df() - NO MAJOR CHANGES, previous version was good for writing.
# Key is 'USER_ENTERED' and preparing NaNs/NaTs to empty strings.
# The integrity of original payments_log data is handled in payment_processor.py *before* calling this.

def update_worksheet_from_df(gspread_client, sheet_id, sheet_name, df_to_write):
    """
    Updates a Google Sheet worksheet with data from a Pandas DataFrame.
    It clears the existing sheet content and then writes the new data, including headers.
    Uses 'USER_ENTERED' value input option for better type interpretation by Google Sheets.
    """
    if gspread_client is None: # Added check for client
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
                # Format YYYY-MM-DD for dates, YYYY-MM-DD HH:MM:SS for datetimes
                # Check if time component is midnight (00:00:00) to decide format
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
                df_prepared[col] = df_prepared[col].fillna('') # Convert other NAs to empty string
        
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

# get_amortization_sheet_id() - NO CHANGES