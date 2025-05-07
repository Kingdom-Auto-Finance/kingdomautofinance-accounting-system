import argparse
import logging
import os
import sys
from flask import Flask, request

# --- Path setup for executing as a module or script ---
# This ensures that 'from . import config' works whether run as 'python -m src.main'
# or as part of a Cloud Function where 'src' is in the deployment package.
current_script_path = os.path.abspath(__file__)
src_directory = os.path.dirname(current_script_path) # .../KingdomAutoFinance/src
project_root = os.path.dirname(src_directory) # .../KingdomAutoFinance

# If 'src' is not already in sys.path (e.g. when running 'python src/main.py')
# and project_root is (for 'import src.config'), this might cause issues.
# The standard way for GCF is that the root of the deployment is in sys.path.
# If your deployment ZIP has 'src/' at the top level, then 'from src import config' might be needed.
# For 'python -m src.main', 'from . import config' is correct.
# Let's assume a structure where this file is part of the 'src' package.

try:
    from . import config # This expects 'src' to be treated as a package
    from .payment_processor import process_payments
    from .reporting import generate_period_report
except ImportError:
    # Fallback for scenarios where relative import fails (e.g. script run directly without -m)
    # This is less ideal but can help during local dev if not using `python -m src.main`
    if src_directory not in sys.path:
         sys.path.insert(0, src_directory)
    if project_root not in sys.path: # Add project root for 'import src.module'
         sys.path.insert(0, project_root)
    from src import config
    from src.payment_processor import process_payments
    from src.reporting import generate_period_report


# --- Logging Setup ---
# Ensure log directory exists (config.py already does this, but good to be sure)
if not os.path.exists(config.LOG_DIR):
    os.makedirs(config.LOG_DIR)

logging.basicConfig(
    level=logging.INFO, # Capture INFO, WARNING, ERROR, CRITICAL. Use logging.DEBUG for more detail.
    format="%(asctime)s - %(levelname)s - [%(module)s.%(funcName)s:%(lineno)d] - %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_FILE), # Log to a file
        logging.StreamHandler(sys.stdout)      # Log to console (stdout for GCF)
    ]
)
# Get a logger for this module
module_logger = logging.getLogger(__name__)

# --- CREATE FLASK APP ---
app = Flask(__name__)

# --- Google Cloud Function Entry Point (as an HTTP route) ---
@app.route('/', methods=['GET', 'POST']) # <--- DEFINE AN HTTP ROUTE
def automated_kaf_run_http(): # Renamed for clarity as an HTTP handler
    """
    HTTP endpoint for Google Cloud Function triggered by Cloud Scheduler or HTTP.
    """
    # For Pub/Sub triggers (if you switch later), you'd decode event['data']
    # For HTTP, you can inspect request object if needed (e.g., request.get_json(), request.args)
    # For a simple trigger like from Cloud Scheduler GET, no specific payload is usually needed.

    module_logger.info("Cloud Function HTTP Endpoint: automated_kaf_run_http triggered.")
    module_logger.info(f"Request method: {request.method}")
    # You can log headers or body if debugging:
    # module_logger.info(f"Request headers: {request.headers}")
    # if request.data:
    #    module_logger.info(f"Request data: {request.data.decode('utf-8')}")


    try:
        process_payments() # Call your main payment processing logic
        module_logger.info("Cloud Function: process_payments completed successfully.")
        return ("Payment processing completed successfully.", 200)
    except Exception as e:
        module_logger.error(f"Cloud Function: Error during process_payments: {e}", exc_info=True)
        return (f"Error during payment processing: {str(e)}", 500)

# --- Command-Line Interface (CLI) ---
def cli_main():
    module_logger.info("Kingdom Auto Finance system starting via CLI.")
    parser = argparse.ArgumentParser(description="Kingdom Auto Finance Processing System")
    subparsers = parser.add_subparsers(dest="command", help="Available commands", required=True)

    # Process payments command
    parser_process = subparsers.add_parser("process", help="Process new payments from Google Sheet Log")
    parser_process.set_defaults(func=lambda args_ns: process_payments()) # Pass args_ns if needed by func

    # Generate report command
    parser_report = subparsers.add_parser("report", help="Generate a financial report for a period")
    parser_report.add_argument("start_date", help="Report start date (YYYY-MM-DD)")
    parser_report.add_argument("end_date", help="Report end date (YYYY-MM-DD)")
    parser_report.set_defaults(func=lambda args_ns: generate_period_report(args_ns.start_date, args_ns.end_date))
    
    args = parser.parse_args()

    if hasattr(args, 'func'):
        try:
            module_logger.info(f"Executing command: {args.command}")
            args.func(args) # Call the function associated with the command
            module_logger.info(f"Command '{args.command}' executed successfully.")
        except Exception as e:
            module_logger.error(f"Error executing command '{args.command}': {e}", exc_info=True)
    else:
        # This case should not be reached if 'required=True' for subparsers
        parser.print_help()
    
    module_logger.info("Kingdom Auto Finance system CLI operation finished.")


if __name__ == "__main__":
    # This block is for CLI execution OR local Flask development server
    if len(sys.argv) > 1 and sys.argv[1] in ['process', 'report']:
        # If 'process' or 'report' is passed, assume CLI execution
        cli_main()
    else:
        # Otherwise, run the Flask development server locally if script is run directly
        # This is for local testing of the HTTP endpoint
        port = int(os.environ.get("PORT", 8080)) # Get PORT from environment or default
        module_logger.info(f"Starting Flask development server on port {port}...")
        app.run(debug=True, host='0.0.0.0', port=port)