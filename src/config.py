import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__)) # This will be src
PROJECT_ROOT = os.path.dirname(BASE_DIR) # This will be KingdomAutoFinance root

# --- Google Sheet Identifiers ---
PAYMENTS_LOG_SHEET_ID = "1WS70qASt5WXUrv_DuRxFG7MYoqbyMXBT08t-WW6zFbk" # Paste from Step 5.2

AMORTIZATION_SHEET_IDS = {
    "6647f2a4466cbb8aa4755a9e": "10MPnAV7wYWjsAvcsKZiHVPZuieqnghTqvd7sDm3PI9Y", # Paste from Step 5.3
    "66ec88773240569b72495dad": "1M5uILh-iO55qDIlcGlNE6ySrzPpXTBzgmQoCxy4wDrs",
    # Add all other loan IDs and their Google Sheet IDs
}

# --- Secret Manager ---
# Paste the full Secret Resource Name from Step 4.3
SERVICE_ACCOUNT_SECRET_RESOURCE_NAME = "projects/544331774603/secrets/kaf-service-account-key/versions/1"

# --- Local Paths (mainly for logs) ---
LOG_DIR = os.path.join(PROJECT_ROOT, "logs") # Correct path to logs at project root
LOG_FILE = os.path.join(LOG_DIR, "kaf_processing.log")

if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

DEFAULT_LATE_FEE_PERCENTAGE = 0.05
DEFAULT_GRACE_PERIOD_DAYS = 5