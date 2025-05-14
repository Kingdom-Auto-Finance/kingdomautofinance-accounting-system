# src/config.py
import os

# Determine base directories reliably
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # Path to 'src' directory
PROJECT_ROOT = os.path.dirname(BASE_DIR)  # Path to 'KingdomAutoFinance' directory

# --- Google Sheet Identifiers ---
# Replace with your actual Payments Log Sheet ID
# --- Google Sheet Identifiers ---
SOURCE_PAYMENTS_SHEET_ID = "14aPTzhbjpRXXTjzLWbOtj5ZFiNhbWAGmgmXzkwkAvU8" # Added Source Sheet ID
PAYMENTS_LOG_SHEET_ID = "1WS70qASt5WXUrv_DuRxFG7MYoqbyMXBT08t-WW6zFbk" 
DAILY_SUMMARY_REPORT_SHEET_ID = "1ln9Bw9HkulHA_s1m8E2XnGbIs9K_-bkBikdjlo0tdLo" 

# --- Google Drive Folder for Amortization Schedules ---
# ** ACTION: Replace with the actual ID of the Google Drive folder **
# Find this ID in the folder's URL in Google Drive
# e.g., https://drive.google.com/drive/folders/THIS_IS_THE_FOLDER_ID
AMORTIZATION_SCHEDULES_FOLDER_ID = "1u5nAuQVIRosLsZgPPuPLmRriGRyQf60s"

# --- Secret Manager ---
# Replace with your actual Secret Resource Name from Google Cloud Secret Manager
SERVICE_ACCOUNT_SECRET_RESOURCE_NAME = "projects/544331774603/secrets/kaf-service-account-key/versions/2"

# --- Local Paths (mainly for logs) ---
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
LOG_FILE = os.path.join(LOG_DIR, "kaf_processing.log")

# Ensure log directory exists when config is loaded
if not os.path.exists(LOG_DIR):
    try:
        os.makedirs(LOG_DIR)
        # Optionally add a .gitignore file inside logs to ignore log files
        gitignore_path = os.path.join(LOG_DIR, ".gitignore")
        if not os.path.exists(gitignore_path):
            with open(gitignore_path, "w") as f:
                f.write("*\n")
                f.write("!.gitignore\n")
    except OSError as e:
        # Handle potential race condition if another process creates it
        if not os.path.exists(LOG_DIR):
            # Re-raise exception if it's not due to directory already existing
            # Use print here as logging might not be configured yet when config is imported
            print(f"Error creating log directory {LOG_DIR}: {e}") 
            raise 

# --- Default Financial Parameters ---
DEFAULT_LATE_FEE_PERCENTAGE = 0.05
DEFAULT_GRACE_PERIOD_DAYS = 5