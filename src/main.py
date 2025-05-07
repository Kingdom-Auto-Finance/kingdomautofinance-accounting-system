# src/main.py
import argparse
import logging
import os
import sys
from datetime import datetime, timedelta # Import timedelta for recent days calc

# --- Imports ---
try:
    from . import config 
    from .payment_processor import process_payments
    from .reporting import generate_period_report
    from .daily_summary_reporter import generate_and_update_daily_summary 
    # Import the new fetcher function
    from .payment_fetcher import fetch_and_populate_payments 
except ImportError as e:
     print(f"Import Error: {e}. Check imports/paths/execution method ('python -m src.main ...').")
     sys.exit(1)

# --- Logging Setup ---
if not os.path.exists(config.LOG_DIR): os.makedirs(config.LOG_DIR, exist_ok=True) 
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s - %(levelname)s - [%(module)s.%(funcName)s:%(lineno)d] - %(message)s",
    handlers=[logging.FileHandler(config.LOG_FILE, encoding='utf-8'), logging.StreamHandler(sys.stdout)],
    # force=True # Consider if necessary
)
module_logger = logging.getLogger(__name__)

# --- Optional Flask App ---
# (Keep commented out unless needed)

# --- Command-Line Interface (CLI) Definition ---
def cli_main():
    module_logger.info("Kingdom Auto Finance system starting via CLI.")
    parser = argparse.ArgumentParser(
        description="Kingdom Auto Finance Processing System",
        formatter_class=argparse.RawTextHelpFormatter 
    )
    subparsers = parser.add_subparsers(
        dest="command", help="Available commands:", required=True 
    )

    # --- Process payments command ---
    parser_process = subparsers.add_parser("process", help="Process new payments from KAF Payments Log sheet.")
    parser_process.set_defaults(func=lambda args_ns: process_payments()) # Corrected lambda

    # --- Generate period report command ---
    parser_report = subparsers.add_parser("report", help="Generate a financial report for a specific period.")
    parser_report.add_argument("start_date", metavar='YYYY-MM-DD', type=str, help="Report start date (YYYY-MM-DD)")
    parser_report.add_argument("end_date", metavar='YYYY-MM-DD', type=str, help="Report end date (YYYY-MM-DD)")
    parser_report.set_defaults(func=lambda args_ns: generate_period_report(args_ns.start_date, args_ns.end_date))
    
    # --- Generate daily summary report command ---
    parser_daily = subparsers.add_parser("daily_summary", help="Update daily summary sheet incrementally (default). Use --full-rebuild for full history.")
    parser_daily.add_argument("--full-rebuild", action='store_true', help="Optional: Force a full rebuild of the entire daily summary history.")
    parser_daily.set_defaults(func=lambda args_ns: generate_and_update_daily_summary(full_rebuild=args_ns.full_rebuild))
    
    # --- Fetch payments command ---
    parser_fetch = subparsers.add_parser("fetch_payments", help="Fetch payments from source sheet and add to KAF Payments Log.")
    mode_group = parser_fetch.add_mutually_exclusive_group() # Ensure only one mode is selected
    mode_group.add_argument("--range", nargs=2, metavar=('START_YYYY-MM-DD', 'END_YYYY-MM-DD'), help="Fetch payments within a specific date range (inclusive).")
    mode_group.add_argument("--all", action='store_true', help="Fetch all payments not already in the log.")
    mode_group.add_argument("--recent", type=int, metavar='DAYS', help="Fetch payments from the last N days (e.g., --recent 7).")
    
    # Define the function to call, processing the args inside the lambda or helper
    def run_fetch(args_ns):
        """Helper function to parse fetch args and call the main fetch function."""
        start = None
        end = None
        fetch_all_flag = args_ns.all
        recent_days = args_ns.recent
        
        if args_ns.range:
            start = args_ns.range[0]
            end = args_ns.range[1]
            # Optional: Add date format validation for range here if desired
        
        # Default behavior if no mode flag is specified (e.g., run fetch for last 7 days)
        if not args_ns.range and not args_ns.all and not args_ns.recent:
             module_logger.info("No fetch mode specified for fetch_payments, defaulting to --recent 7 days.")
             recent_days = 7
             
        # Call the actual fetch function with parsed arguments
        fetch_and_populate_payments(
            start_date_str=start, 
            end_date_str=end, 
            fetch_all=fetch_all_flag, 
            fetch_recent_days=recent_days
        )

    parser_fetch.set_defaults(func=run_fetch) # Link fetch command to the wrapper function
    
    # --- Parse arguments ---
    try: args = parser.parse_args()
    except SystemExit: sys.exit(0) 
    except Exception as e: module_logger.error(f"Error parsing arguments: {e}"); parser.print_help(); sys.exit(1)

    # --- Execute the selected command's function ---
    if hasattr(args, 'func') and callable(args.func):
        try:
            module_logger.info(f"Executing command: {args.command}")
            args.func(args) # Call the function (could be direct or the lambda wrapper)
            module_logger.info(f"Command '{args.command}' executed successfully.")
        except Exception as e:
            module_logger.error(f"Error executing command '{args.command}': {e}", exc_info=True)
            sys.exit(1) 
        finally:
             module_logger.info("Kingdom Auto Finance system CLI operation finished.")
    else:
        module_logger.error(f"No function associated with command '{args.command}'.")
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    cli_main()