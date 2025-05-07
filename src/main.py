# src/main.py
import argparse
import logging
import os
import sys

# --- Path setup ---
current_script_path = os.path.abspath(__file__)
src_directory = os.path.dirname(current_script_path)
project_root = os.path.dirname(src_directory)
# if project_root not in sys.path: sys.path.insert(0, project_root) 

# --- Import project modules ---
try:
    from . import config 
    from .payment_processor import process_payments
    from .reporting import generate_period_report
    from .daily_summary_reporter import generate_and_update_daily_summary 
except ImportError as e:
     print(f"Import Error: {e}. Check imports/paths/execution method ('python -m src.main ...').")
     sys.exit(1)


# --- Logging Setup ---
if not os.path.exists(config.LOG_DIR):
    try:
        os.makedirs(config.LOG_DIR, exist_ok=True) 
        gitignore_path = os.path.join(config.LOG_DIR, ".gitignore")
        if not os.path.exists(gitignore_path):
            try:
                 with open(gitignore_path, "w") as f: f.write("*\n!.gitignore\n")
            except IOError: print(f"Warning: Could not create .gitignore in {config.LOG_DIR}")
    except OSError as e:
        print(f"Warning: Could not create log directory {config.LOG_DIR}: {e}")
        logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", handlers=[logging.StreamHandler(sys.stdout)])
        print("Logging to file disabled.")
else:
    logging.basicConfig(
        level=logging.INFO, 
        format="%(asctime)s - %(levelname)s - [%(module)s.%(funcName)s:%(lineno)d] - %(message)s",
        handlers=[
            logging.FileHandler(config.LOG_FILE, encoding='utf-8'), 
            logging.StreamHandler(sys.stdout)      
        ],
        # force=True # Consider if necessary
    )
module_logger = logging.getLogger(__name__)


# --- Optional Flask App ---
# (Keep commented out unless needed)


# --- Command-Line Interface (CLI) Definition ---
def cli_main():
    """Parses command-line arguments and executes the corresponding function."""
    module_logger.info("Kingdom Auto Finance system starting via CLI.")
    parser = argparse.ArgumentParser(
        description="Kingdom Auto Finance Processing System",
        formatter_class=argparse.RawTextHelpFormatter 
    )
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
    # *** Use lambda to call process_payments without arguments ***
    parser_process.set_defaults(func=lambda args_ns: process_payments()) 
    # *** End Change ***

    # --- Generate period report command ---
    parser_report = subparsers.add_parser(
        "report",
        help="Generate a financial report for a specific period."
    )
    parser_report.add_argument(
        "start_date",
        metavar='YYYY-MM-DD', 
        type=str, 
        help="Report start date (YYYY-MM-DD)"
    )
    parser_report.add_argument(
        "end_date",
        metavar='YYYY-MM-DD',
        type=str,
        help="Report end date (YYYY-MM-DD)"
    )
    parser_report.set_defaults(
        func=lambda args_ns: generate_period_report(args_ns.start_date, args_ns.end_date)
    )
    
    # --- Generate daily summary report command ---
    parser_daily = subparsers.add_parser(
        "daily_summary",
        help="Update daily summary sheet incrementally (default). Use --full-rebuild for full history."
    )
    parser_daily.add_argument(
        "--full-rebuild",
        action='store_true', 
        help="Optional: Force a full rebuild of the entire daily summary history."
    )
    parser_daily.set_defaults(
        func=lambda args_ns: generate_and_update_daily_summary(full_rebuild=args_ns.full_rebuild) 
    )
    
    # --- Parse arguments ---
    try: 
        args = parser.parse_args()
        module_logger.debug(f"Parsed arguments: {args}")
    except SystemExit: sys.exit(0) 
    except Exception as e: module_logger.error(f"Error parsing arguments: {e}"); parser.print_help(); sys.exit(1)

    # --- Execute the selected command's function ---
    if hasattr(args, 'func') and callable(args.func):
        try:
            module_logger.info(f"Executing command: {args.command}")
            args.func(args) # Call the function linked by set_defaults (lambda handles args)
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