# src/config.py
import os
import sys
from pathlib import Path

# Determine base directories reliably
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # Path to 'src' directory
PROJECT_ROOT = os.path.dirname(BASE_DIR)  # Path to 'KingdomAutoFinance' directory

# Try to import settings manager if available (when running via FastAPI backend)
try:
    backend_path = Path(__file__).parent.parent / "backend"
    if str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))
    from app.core.settings_manager import settings_manager
    USE_SETTINGS_MANAGER = True
except ImportError:
    USE_SETTINGS_MANAGER = False
    settings_manager = None

# --- Google Sheet Identifiers ---
# These are only needed if you continue using Google Sheets for data import/export.

# SOURCE_PAYMENTS_SHEET_ID: Now supports dynamic configuration via database
if USE_SETTINGS_MANAGER:
    try:
        SOURCE_PAYMENTS_SHEET_ID = settings_manager.get_setting(
            "SOURCE_PAYMENTS_SHEET_ID",
            os.getenv("SOURCE_PAYMENTS_SHEET_ID", "14aPTzhbjpRXXTjzLWbOtj5ZFiNhbWAGmgmXzkwkAvU8")
        )
    except Exception:
        # Fallback if settings manager fails
        SOURCE_PAYMENTS_SHEET_ID = os.getenv("SOURCE_PAYMENTS_SHEET_ID", "14aPTzhbjpRXXTjzLWbOtj5ZFiNhbWAGmgmXzkwkAvU8")
else:
    SOURCE_PAYMENTS_SHEET_ID = os.getenv("SOURCE_PAYMENTS_SHEET_ID", "14aPTzhbjpRXXTjzLWbOtj5ZFiNhbWAGmgmXzkwkAvU8")

PAYMENTS_LOG_SHEET_ID = os.getenv("PAYMENTS_LOG_SHEET_ID", "1WS70qASt5WXUrv_DuRxFG7MYoqbyMXBT08t-WW6zFbk")
DAILY_SUMMARY_REPORT_SHEET_ID = os.getenv("DAILY_SUMMARY_REPORT_SHEET_ID", "1ln9Bw9HkulHA_s1m8E2XnGbIs9K_-bkBikdjlo0tdLo")

# --- Google Drive Folder for Amortization Schedules ---
# AMORTIZATION_SCHEDULES_FOLDER_ID: Now supports dynamic configuration via database
if USE_SETTINGS_MANAGER:
    try:
        AMORTIZATION_SCHEDULES_FOLDER_ID = settings_manager.get_setting(
            "AMORTIZATION_SCHEDULES_FOLDER_ID",
            os.getenv("AMORTIZATION_SCHEDULES_FOLDER_ID", "1u5nAuQVIRosLsZgPPuPLmRriGRyQf60s")
        )
    except Exception:
        # Fallback if settings manager fails
        AMORTIZATION_SCHEDULES_FOLDER_ID = os.getenv("AMORTIZATION_SCHEDULES_FOLDER_ID", "1u5nAuQVIRosLsZgPPuPLmRriGRyQf60s")
else:
    AMORTIZATION_SCHEDULES_FOLDER_ID = os.getenv("AMORTIZATION_SCHEDULES_FOLDER_ID", "1u5nAuQVIRosLsZgPPuPLmRriGRyQf60s")

# --- Service Account Credentials (Google Sheets Only) ---
# Still needed ONLY if Google Sheets import/export is active
SERVICE_ACCOUNT_SECRET_RESOURCE_NAME = os.getenv("SERVICE_ACCOUNT_SECRET_RESOURCE_NAME", "")

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
        if not os.path.exists(LOG_DIR):
            print(f"Error creating log directory {LOG_DIR}: {e}") 
            raise 

# --- Default Financial Parameters ---
DEFAULT_LATE_FEE_PERCENTAGE = 0.05
DEFAULT_GRACE_PERIOD_DAYS = 3

from decimal import Decimal as D
DEFAULT_LATE_FEE = D("25.00")

# --- Supabase configuration (via environment variables only) ---
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://puwcyhbjchkfvvaccacg.supabase.co")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")  # Your secret (REQUIRED)
# No need for *_SECRET_RESOURCE_NAME or *_KEY_SECRET_NAME anymore!

# Table in Supabase that tracks all loan IDs
LOANS_TABLE = "loans"

# How many future installments may be covered before any excess goes to principal
MAX_FORWARD_INSTALLMENTS = 2
