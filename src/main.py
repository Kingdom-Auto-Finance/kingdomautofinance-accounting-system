# src/main.py
import argparse
import logging
import os
import sys
# --- Corrected Imports - Ensure Flask is imported only if used ---
# from flask import Flask, request # Import Flask only if creating the 'app' object for HTTP trigger

# --- Path setup ---
# This setup helps Python find modules correctly when run using 'python -m src.main ...'
current_script_path = os.path.abspath(__file__)
src_directory = os.path.dirname(current_script_path)
project_root = os.path.dirname(src_directory)
# You might uncomment the below if running directly ('python src/main.py') causes issues,
# but using 'python -m ...' is generally preferred for packages.
# if project_root not in sys.path:
#      sys.path.insert(0, project_root)

# --- Import project modules using relative imports ---
try:
    from . import config # Assuming config.py is in the same directory (src)
    from .payment_processor import process_payments
    from .reporting import generate_period_report
    from .daily_summary_reporter import generate_and_update_daily_summary
except ImportError as e:
     # Provide a more helpful error message if imports fail
     print(f"Import Error: {e}. Failed to import modules from within the 'src' package.")
     print("Please ensure you are running this script as a module from the project's root directory using:")
     print("  python -m src.main [command]")
     print(f"Current sys.path: {sys.path}")
     sys.exit(1)


# --- Logging Setup ---
# Ensure log directory exists before setting up file handler
if not os.path.exists(config.LOG_DIR):
    try:
        os.makedirs(config.LOG_DIR)
    except OSError as e:
        print(f"Warning: Could not create log directory {config.LOG_DIR}: {e}")
        # Fallback to logging only to console if directory creation fails
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - [%(module)s.%(funcName)s:%(lineno)d] - %(message)s",
            handlers=[logging.StreamHandler(sys.stdout)]
        )
        print("Logging to file disabled due to directory error.")
else:
    # Setup logging to both file and console if directory exists
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - [%(module)s.%(funcName)s:%(lineno)d] - %(message)s",
        handlers=[
            logging.FileHandler(config.LOG_FILE), # Log to a file
            logging.StreamHandler(sys.stdout)      # Log to console (stdout for GCF)
        ]
    )
# Get a logger for this module
module_logger = logging.getLogger(__name__)


# --- Flask App & HTTP Endpoint (OPTIONAL - uncomment/define if deploying as HTTP GCF) ---
# If you are using Google Cloud Scheduler with an HTTP target for automation,
# you would define your Flask app and HTTP endpoint function here.
# If you are only using the CLI or OS-level scheduling, you don't need this Flask part.

# Example structure (uncomment and adapt if needed):
# app = Flask(__name__) # Initialize Flask app
#
# @app.route('/run-daily-summary', methods=['POST']) # Example route for daily summary
# def http_trigger_daily_summary():
#     module_logger.info("HTTP Trigger received for daily summary.")
#     # Add security checks if needed (e.g., check headers, tokens)
#     try:
#         success = generate_and_update_daily_summary()
#         if success:
#             return "Daily summary updated successfully.", 200
#         else:
#             return "Daily summary failed.", 500
#     except Exception as e:
#         module_logger.error(f"Error in HTTP triggered daily summary: {e}", exc_info=True)
#         return f"Internal Server Error: {e}", 500
#
# @app.route('/run-process-payments', methods=['POST']) # Example route for payment processing
# def http_trigger_process_payments():
#     module_logger.info("HTTP Trigger received for payment processing.")
#     try:
#         process_payments() # Doesn't return True/False, check logs for success
#         return "Payment processing triggered successfully.", 200
#     except Exception as e:
#         module_logger.error(f"Error in HTTP triggered payment processing: {e}", exc_info=True)
#         return f"Internal Server Error: {e}", 500
#
# # If using Flask, the Cloud Function Entry Point would be 'app'


# --- Command-Line Interface (CLI) Definition ---
def cli_main():
    """Parses command-line arguments and executes the corresponding function."""
    module_logger.info("Kingdom Auto Finance system starting via CLI.")
    parser = argparse.ArgumentParser(
        description="Kingdom Auto Finance Processing System",
        formatter_class=argparse.RawTextHelpFormatter # Allows better formatting in help
    )
    subparsers = parser.add_subparsers(
        dest="command",
        help="Available commands",
        required=True # Ensures a command must be provided
    )

    # --- Process payments command ---
    parser_process = subparsers.add_parser(
        "process",
        help="Process new payments from the Google Sheet Log."
    )
    parser_process.set_defaults(func=lambda args_ns: process_payments()) # Link command to function

    # --- Generate period report command ---
    parser_report = subparsers.add_parser(
        "report",
        help="Generate a financial report for a specific period."
    )
    parser_report.add_argument(
        "start_date",
        help="Report start date (YYYY-MM-DD)"
    )
    parser_report.add_argument(
        "end_date",
        help="Report end date (YYYY-MM-DD)"
    )
    parser_report.set_defaults(
        func=lambda args_ns: generate_period_report(args_ns.start_date, args_ns.end_date)
    )
    
    # --- Generate daily summary report command ---
    # Uses consistent 4-space indentation
    parser_daily = subparsers.add_parser(
        "daily_summary",
        help="Generate and update the daily financial summary report sheet."
    )
    parser_daily.set_defaults(
        func=lambda args_ns: generate_and_update_daily_summary()
    )
    
    # --- Parse arguments ---
    try:
        args = parser.parse_args()
    except SystemExit: 
        # Handle cases where --help is used or no command provided
        # parser.print_help() # argparse already does this
        sys.exit(0) # Exit cleanly after help

    # --- Execute the selected command's function ---
    if hasattr(args, 'func'):
        try:
            module_logger.info(f"Executing command: {args.command}")
            args.func(args) # Call the function linked by set_defaults
            module_logger.info(f"Command '{args.command}' executed successfully.")
        except Exception as e:
            module_logger.error(f"Error executing command '{args.command}': {e}", exc_info=True)
            sys.exit(1) # Exit with a non-zero code to indicate error
        finally: # Ensure this message logs even if errors occur within the function
             module_logger.info("Kingdom Auto Finance system CLI operation finished.")
    else:
        # This should not be reached if subparsers are required=True
        module_logger.error("No function associated with the parsed arguments.")
        parser.print_help()
        sys.exit(1)


# --- Main Execution Guard ---
if __name__ == "__main__":
    # This block runs ONLY when the script is executed directly
    # (e.g., 'python src/main.py process' or 'python -m src.main process')
    # It ensures the CLI logic is called.
    # If deploying as a Cloud Function with an 'app' entry point (using Flask),
    # this block will NOT run in the cloud environment. Gunicorn/Google runs the 'app' object directly.
    cli_main()