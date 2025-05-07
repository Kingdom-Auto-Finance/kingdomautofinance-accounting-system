# src/gutils.py
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from google.cloud import secretmanager
import json
import logging
import time # We might keep this if exponential backoff isn't enough for all API calls
from . import config

logger = logging.getLogger(__name__)

# get_service_account_credentials_from_secret_manager() - NO CHANGES, ASSUMED CORRECT FROM PREVIOUS
# get_gspread_client() - NO CHANGES, ASSUMED CORRECT FROM PREVIOUS

def get_sheet_as_df(gspread_client, sheet_id, sheet_name=None, max_retries=5, initial_delay=1):
    """
    Opens a Google Sheet by ID and returns a specific worksheet as a Pandas DataFrame.
    Includes exponential backoff for quota errors.
    Ensures numeric columns are attempted to be converted to numeric.
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
            
            all_values = worksheet.get_all_values() # Get all values as strings initially
            if not all_values:
                logger.warning(f"Sheet '{sheet_name or 'first sheet'}' in spreadsheet ID '{sheet_id}' is empty or returned no data.")
                return pd.DataFrame()
            
            headers = all_values[0]
            records = all_values[1:]

            df = pd.DataFrame(records, columns=headers)

            # Attempt to convert known numeric columns to numeric types, coercing errors to NaN
            # This is a general attempt; specific converters might be needed in payment_processor.py
            for col in df.columns:
                # Try to infer if a column should be numeric based on its name (customize this list)
                if any(num_keyword in col.lower() for num_keyword in ['amount', 'balance', 'principal', 'interest', 'fee', 'rate', 'payment', 'number', '#', 'id']):
                    # Replace empty strings with NaN before converting to numeric so they don't become 0 if not intended
                    df[col] = df[col].replace('', pd.NA)
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # Attempt to convert date columns (customize this list)
            for col in df.columns:
                if 'date' in col.lower():
                    df[col] = df[col].replace('', pd.NaT) # Replace empty strings with NaT for dates
                    df[col] = pd.to_datetime(df[col], errors='coerce')

            logger.debug(f"Successfully read and typed sheet ID {sheet_id}, name '{sheet_name}'. Columns: {df.columns.tolist()}")
            return df

        except gspread.exceptions.APIError as e:
            if hasattr(e, 'response') and e.response.status_code == 429: # type: ignore
                retries += 1
                if retries >= max_retries:
                    logger.error(f"Quota exceeded for sheet ID {sheet_id}, name '{sheet_name}'. Max retries reached. Error: {e}")
                    raise
                wait_time = delay * (2 ** (retries - 1))
                logger.warning(
                    f"Quota exceeded for sheet ID {sheet_id}, name '{sheet_name}'. "
                    f"Retrying in {wait_time:.2f} seconds... (Attempt {retries}/{max_retries})"
                )
                time.sleep(wait_time)
            else:
                logger.error(f"Non-quota APIError reading sheet ID {sheet_id}, name '{sheet_name}': {e}", exc_info=True)
                raise
        except gspread.exceptions.WorksheetNotFound:
            logger.error(f"Worksheet '{sheet_name}' not found in spreadsheet ID '{sheet_id}'.")
            return pd.DataFrame() # Return empty DataFrame to prevent None downstream
        except Exception as e:
            logger.error(f"General error reading sheet ID {sheet_id}, name '{sheet_name}': {e}", exc_info=True)
            return pd.DataFrame() # Return empty DataFrame

    logger.error(f"Failed to read sheet ID {sheet_id}, name '{sheet_name}' after multiple retries.")
    return pd.DataFrame()


def update_worksheet_from_df(gspread_client, sheet_id, sheet_name, df_to_write):
    """
    Updates a Google Sheet worksheet with data from a Pandas DataFrame.
    Clears the sheet and writes all new data including headers.
    """
    if df_to_write is None:
        logger.error(f"DataFrame to write to sheet ID {sheet_id}, name '{sheet_name}' is None. Aborting update.")
        return False
    
    try:
        spreadsheet = gspread_client.open_by_key(sheet_id)
        worksheet = spreadsheet.worksheet(sheet_name)
        
        # Prepare DataFrame for writing:
        # Convert NaT to empty string for dates, other NAs to empty string
        # Ensure boolean True/False are written as such, not 1/0 by gspread if it converts to string first
        df_prepared = df_to_write.copy()
        for col in df_prepared.columns:
            if pd.api.types.is_datetime64_any_dtype(df_prepared[col]):
                # Format datetime to string that Google Sheets usually understands well
                # Keep NaT as empty string
                df_prepared[col] = df_prepared[col].dt.strftime('%Y-%m-%d %H:%M:%S').fillna('')
                # If only date is needed: df_prepared[col].dt.strftime('%Y-%m-%d').fillna('')
            elif pd.api.types.is_bool_dtype(df_prepared[col]):
                 # Explicitly convert boolean to TRUE/FALSE strings if gspread has issues
                 # df_prepared[col] = df_prepared[col].apply(lambda x: 'TRUE' if pd.notna(x) and x else ('FALSE' if pd.notna(x) and not x else ''))
                 pass # gspread usually handles Python bools fine with USER_ENTERED
            else:
                # For other types, fill NA with empty string.
                # Ensure numbers are not accidentally converted to strings with '.0' if they are integers
                # This is tricky; `value_input_option='USER_ENTERED'` helps Google Sheets interpret types.
                df_prepared[col] = df_prepared[col].fillna('')


        # Get all values as a list of lists, including headers
        # Ensure all values are basic Python types (str, int, float, bool) or None
        # gspread > 5.8.0 generally handles None and basic types well with USER_ENTERED
        list_of_lists = [df_prepared.columns.tolist()] + df_prepared.values.tolist()
        
        # Cleanse list_of_lists further: replace Pandas NA objects if any slipped through
        final_list_of_lists = []
        for row in list_of_lists:
            cleaned_row = []
            for cell_value in row:
                if pd.isna(cell_value):
                    cleaned_row.append('') # Or None, but '' is safer for gspread updates
                else:
                    cleaned_row.append(cell_value)
            final_list_of_lists.append(cleaned_row)

        worksheet.clear() # Clear all existing data and formatting
        worksheet.update(final_list_of_lists, value_input_option='USER_ENTERED')
        # USER_ENTERED asks Google Sheets to interpret the data (e.g., "123" as number, "2023-10-10" as date)
        
        logger.info(f"Successfully updated worksheet '{sheet_name}' in sheet ID '{sheet_id}' with {len(df_to_write)} rows.")
        return True
    except gspread.exceptions.WorksheetNotFound:
        logger.error(f"Worksheet '{sheet_name}' not found in spreadsheet ID '{sheet_id}' for updating.")
        return False
    except Exception as e:
        logger.error(f"Error updating sheet ID {sheet_id}, name '{sheet_name}': {e}", exc_info=True)
        return False

# get_amortization_sheet_id() - NO CHANGES, ASSUMED CORRECT