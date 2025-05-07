# src/main.py
import argparse
import logging
import os
import sys

# --- Path setup ---
# Ensures correct relative imports when run as a module
current_script_path = os.path.abspath(__file__)
src_directory = os.path.dirname(current_script_path)
project_root = os.path.dirname(src_directory)
# Adding project root might be needed if imports use 'src.' prefix explicitly somewhere else
# if project_root not in sys.path:
#      sys.path.insert(0, project_root)

# --- Import project modules using relative imports ---
try:
    # Assuming execution via 'python -m src.main ...'
    from . import config # Imports config.py from src folder
    from .payment_processor import process_payments # Imports from src/payment_processor.py
    from .reporting import generate_period_report # Imports from src/reporting.py
    from .daily_summary_reporter import generate_and_update_daily_summary # Imports from src/daily_summary_reporter.py
except ImportError as e:
     # Provides guidance if imports fail
     print(f"Import Error: {e}. Failed to import modules from within the 'src' package.")
     print("Please ensure you are running this script as a module from the project's root directory using:")
     print("  python -m src.main [command]")
     print(f"Current sys.path: {sys.path}")
     sys.exit(1) # Exit if essential modules cannot be imported


# --- Logging Setup ---
# Ensures log directory exists and sets up logging handlers
if not os.path.exists(config.LOG_DIR):
    try:
        os.makedirs(config.LOG_DIR, exist_ok=True) # Use exist_ok=True
        # Optionally create .gitignore in logs directory
        gitignore_path = os.path.join(config.LOG_DIR, ".gitignore")
        if not os.path.exists(gitignore_path):
            try:
                 with open(gitignore_path, "w") as f: f.write("*\n!.gitignore\n")
            except IOError:
                 print(f"Warning: Could not create .gitignore in {config.LOG_DIR}")
    except OSError as e:
        print(f"Warning: Could not create log directory {config.LOG_DIR}: {e}")
        # Basic console logging as fallback
        logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", handlers=[logging.StreamHandler(sys.stdout)])
        print("Logging to file disabled.")
else:
    # Setup logging to both file and console
    logging.basicConfig(
        level=logging.INFO, 
        format="%(asctime)s - %(levelname)s - [%(module)s.%(funcName)s:%(lineno)d] - %(message)s",
        handlers=[
            logging.FileHandler(config.LOG_FILE, encoding='utf-8'), # Specify encoding
            logging.StreamHandler(sys.stdout)      
        ],
        # Force=True might be needed if logging is configured elsewhere first (e.g., GCF default)
        # force=True 
    )
# Get a logger specifically for this main module
module_logger = logging.getLogger(__name__)


# --- Optional Flask App & HTTP Endpoint ---
# Kept commented out as per previous instruction (only needed for HTTP GCF trigger)
# from flask import Flask, request 
# app = Flask(__name__) 
# @app.route('/run-daily-summary', methods=['POST']) 
# def http_trigger_daily_summary(): ...
# @app.route('/run-process-payments', methods=['POST']) 
# def http_trigger_process_payments(): ...
# # Cloud Function Entry Point would be 'app' if using Flask


# --- Command-Line Interface (CLI) Definition ---
def cli_main():
    """Parses command-line arguments and executes the corresponding function."""
    module_logger.info("Kingdom Auto Finance system starting via CLI.")
    parser = argparse.ArgumentParser(
        description="Kingdom Auto Finance Processing System",
        formatter_class=argparse.RawTextHelpFormatter 
    )
    # Make sure subparsers destination is set and required
    subparsers = parser.add_subparsers(
        dest="command",
        help="Available commands:",
        required=True 
    )

    # --- Process payments command ---
    parser_process = subparsers.add_parser(
        "process",
        help="Process new payments from the Google Sheet Log."
    )
    # Link the command 'process' to the process_payments function
    parser_process.set_defaults(func=process_payments) # No lambda needed if function takes no args

    # --- Generate period report command ---
    parser_report = subparsers.add_parser(
        "report",
        help="Generate a financial report for a specific period."
    )
    parser_report.add_argument(
        "start_date",
        metavar='YYYY-MM-DD', # Add metavar for clarity in help
        type=str, # Keep as string, validation happens in function
        help="Report start date (YYYY-MM-DD)"
    )
    parser_report.add_argument(
        "end_date",
        metavar='YYYY-MM-DD',
        type=str,
        help="Report end date (YYYY-MM-DD)"
    )
    # Link command 'report' to generate_period_report, passing the args object
    parser_report.set_defaults(
        func=lambda args_ns: generate_period_report(args_ns.start_date, args_ns.end_date)
    )
    
    # --- Generate daily summary report command ---
    # Consistent 4-space indentation verified
    parser_daily = subparsers.add_parser(
        "daily_summary",
        help="Generate/update daily summary sheet. Overwrites sheet. Use --since to limit history."
    )
    parser_daily.add_argument(
        "--since",
        metavar='YYYY-MM-DD',
        type=str,
        default=None, # Default processes all history
        help="Optional: Rebuild summary only for dates ON or AFTER this date."
    )
    # Link command 'daily_summary' to generate_and_update_daily_summary, passing args
    parser_daily.set_defaults(
        func=lambda args_ns: generate_and_update_daily_summary(since_date_str=args_ns.since) 
    )
    
    # --- Parse arguments ---
    try: 
        args = parser.parse_args()
        module_logger.debug(f"Parsed arguments: {args}")
    except SystemExit: 
        # Raised by argparse on --help or error, exit cleanly
        sys.exit(0) 
    except Exception as e:
        module_logger.error(f"Error parsing arguments: {e}")
        parser.print_help()
        sys.exit(1)

    # --- Execute the selected command's function ---
    # Check if the parsed args object has the 'func' attribute set by set_defaults
    if hasattr(args, 'func') and callable(args.func):
        try:
            module_logger.info(f"Executing command: {args.command}")
            # Call the function associated with the command, passing the full args namespace
            # This allows the target function to access specific args like args.start_date or args.since
            args.func(args) 
            module_logger.info(f"Command '{args.command}' executed successfully.")
        except Exception as e:
            # Catch errors during the execution of the command's function
            module_logger.error(f"Error executing command '{args.command}': {e}", exc_info=True)
            sys.exit(1) # Exit with error
        finally:
             # This will run even if an error occurs in the command function
             module_logger.info("Kingdom Auto Finance system CLI operation finished.")
    else:
        # Fallback if set_defaults wasn't called correctly (shouldn't happen with required=True)
        module_logger.error(f"No function associated with command '{args.command}'.")
        parser.print_help()
        sys.exit(1)


# --- Main Execution Guard ---
if __name__ == "__main__":
    # This ensures cli_main() is called when script is run directly or via 'python -m src.main'
    cli_main()