# src/main.py
import argparse
import logging
import os
import sys

# --- Path setup ---
current_script_path = os.path.abspath(__file__)
src_directory = os.path.dirname(current_script_path)
project_root = os.path.dirname(src_directory)
# Add project root to path if needed, for finding 'src' package
# if project_root not in sys.path:
#      sys.path.insert(0, project_root)

# --- Import project modules ---
try:
    # Assuming execution via 'python -m src.main ...'
    from . import config 
    from .payment_processor import process_payments
    from .reporting import generate_period_report
    from .daily_summary_reporter import generate_and_update_daily_summary # ** ADD THIS IMPORT **
except ImportError as e:
     print(f"Import Error: {e}. Ensure running with 'python -m src.main ...' from project root or check Python path.")
     sys.exit(1)


# --- Logging Setup ---
if not os.path.exists(config.LOG_DIR): os.makedirs(config.LOG_DIR) # Ensure log dir exists
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s - %(levelname)s - [%(module)s.%(funcName)s:%(lineno)d] - %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_FILE), 
        logging.StreamHandler(sys.stdout)      
    ]
)
module_logger = logging.getLogger(__name__)


# --- Flask App & HTTP Endpoint (if used for Cloud Function) ---
# from flask import Flask, request 
# app = Flask(__name__) 
# @app.route('/', methods=['GET', 'POST']) 
# def automated_kaf_run_http(): 
#    ... (function definition if deploying as HTTP GCF) ...


# --- Command-Line Interface (CLI) ---
def cli_main():
    module_logger.info("Kingdom Auto Finance system starting via CLI.")
    parser = argparse.ArgumentParser(description="Kingdom Auto Finance Processing System")
    subparsers = parser.add_subparsers(dest="command", help="Available commands", required=True)

    # Process payments command
    parser_process = subparsers.add_parser("process", help="Process new payments from Google Sheet Log")
    parser_process.set_defaults(func=lambda args_ns: process_payments()) 

    # Generate period report command
    parser_report = subparsers.add_parser("report", help="Generate a financial report for a period")
    parser_report.add_argument("start_date", help="Report start date (YYYY-MM-DD)")
    parser_report.add_argument("end_date", help="Report end date (YYYY-MM-DD)")
    parser_report.set_defaults(func=lambda args_ns: generate_period_report(args_ns.start_date, args_ns.end_date))
    
    # ** ADD THIS PARSER **
    # Generate daily summary report command
    parser_daily = subparsers.add_parser("daily_summary", help="Generate and update the daily summary report sheet.")
    parser_daily.set_defaults(func=lambda args_ns: generate_and_update_daily_summary())
    # ** END ADD **
    
    args = parser.parse_args()

    if hasattr(args, 'func'):
        try:
            module_logger.info(f"Executing command: {args.command}")
            args.func(args) # Call the function associated with the command
            module_logger.info(f"Command '{args.command}' executed successfully.")
        except Exception as e:
            module_logger.error(f"Error executing command '{args.command}': {e}", exc_info=True)
            sys.exit(1) # Exit with error code on exception
    
    module_logger.info("Kingdom Auto Finance system CLI operation finished.")


if __name__ == "__main__":
    # This block runs if the script is executed directly OR via 'python -m src.main ...'
    # It always executes the CLI part when __name__ is "__main__"
    cli_main()