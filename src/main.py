import argparse
import logging
import os
import sys

# --- ADDED IMPORTS ---
import pandas as pd
from supabase import create_client, Client
import gutils
# --- END ADDED IMPORTS ---


# Suppress verbose logging from underlying clients
logging.getLogger("supabase").setLevel(logging.WARNING)
logging.getLogger("postgrest").setLevel(logging.WARNING)
logging.getLogger("_client").setLevel(logging.WARNING)
logging.getLogger("_client._send_single_request").setLevel(logging.WARNING)

# --- Imports ---
try:
    import config
    from payment_processor import process_payments
    from reporting import (
        generate_period_report,
        generate_day_breakdown,
        generate_loan_breakdown,
        generate_full_breakdown,
    )
    from daily_summary_reporter import generate_and_update_daily_summary
    from payment_fetcher import fetch_and_populate_payments
except ImportError as e:
    print(f"Import Error: {e}. Check imports/paths/execution method ('python -m src.main ...').")
    sys.exit(1)

# --- Logging Setup ---
if not os.path.exists(config.LOG_DIR):
    os.makedirs(config.LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(module)s.%(funcName)s:%(lineno)d] - %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
module_logger = logging.getLogger(__name__)


def run_fetch(args):
    """Parse fetch_payments args and invoke fetch_and_populate_payments."""
    start, end = None, None
    if args.range:
        start, end = args.range

    fetch_all_flag = args.all
    recent_days = args.recent

    if not args.range and not args.all and not args.recent:
        module_logger.info("No fetch mode specified, defaulting to --recent 7 days.")
        recent_days = 7

    fetch_and_populate_payments(
        start_date_str=start,
        end_date_str=end,
        fetch_all=fetch_all_flag,
        fetch_recent_days=recent_days,
    )


def run_report(args):
    """Dispatch report commands based on provided mode, dates, and flags."""
    # Gather provided positional tokens
    tokens = [t for t in (args.arg1, args.arg2, args.arg3) if t]

    if args.all_dates:
        # When --all is set, only a single optional mode token is allowed
        if len(tokens) == 0:
            mode = "summary"
            start = end = None
        elif len(tokens) == 1:
            mode = tokens[0]
            start = end = None
        else:
            module_logger.error("Too many arguments when using --all. Only report mode is allowed.")
            sys.exit(1)
    else:
        # Without --all, expect either [start, end] or [mode, start, end]
        if len(tokens) == 2:
            mode = "summary"
            start, end = tokens
        elif len(tokens) == 3:
            mode, start, end = tokens
        else:
            module_logger.error(
                "Invalid arguments. Without --all, provide either two dates or mode + two dates."
            )
            module_logger.info(
                "Examples:\n"
                "  report YYYY-MM-DD YYYY-MM-DD\n"
                "  report day-breakdown YYYY-MM-DD YYYY-MM-DD"
            )
            sys.exit(1)

    module_logger.info(
        f"Generating report '{mode}' " +
        ("for ALL data" if args.all_dates else f"from {start} to {end}")
    )

    # Dispatch to the correct reporting function
    if mode == "summary":
        generate_period_report(start, end)
    elif mode == "day-breakdown":
        generate_day_breakdown(start, end, all_dates=args.all_dates)
    elif mode == "loan-breakdown":
        generate_loan_breakdown(start, end, all_dates=args.all_dates)
    elif mode == "full-breakdown":
        generate_full_breakdown(start, end, all_dates=args.all_dates)
    else:
        module_logger.error(f"Unknown report mode '{mode}'")
        sys.exit(1)

# --- ADDED: NEW COMMAND FUNCTIONALITY ---
def run_integrity_check(args):
    """Checks for row count discrepancies between Google Sheets and Supabase tables."""
    module_logger.info("Starting integrity check for amortization schedules...")
    
    supabase_url = config.SUPABASE_URL
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("supabase_service_role_key")
    supabase: Client = create_client(supabase_url, supabase_key)
    
    gs_client = gutils.get_gspread_client()

    all_loan_ids = gutils.get_loan_ids_from_drive_folder(config.AMORTIZATION_SCHEDULES_FOLDER_ID)
    report_data = []

    for loan_id in all_loan_ids:
        table_name = f"schedule_{loan_id}"
        
        # Get count from Supabase
        db_count = "N/A"
        try:
            res = supabase.from_(table_name).select('paymentnumber', count='exact').execute()
            db_count = res.count
        except Exception as e:
            module_logger.error(f"Error fetching DB count for {loan_id} ({table_name}): {e}")
            
        # Get count from Google Sheets
        sheet_count = "N/A"
        try:
            sheet_id = gutils.find_sheet_id_by_loan_id_in_folder(loan_id)
            if sheet_id:
                sheet = gs_client.open_by_key(sheet_id)
                worksheet = sheet.worksheet("Schedule")
                # Get the number of rows with values
                sheet_count = len(worksheet.get_all_values()) - 1 # Subtract 1 for the header
        except Exception as e:
            module_logger.error(f"Error fetching Sheet count for {loan_id}: {e}")

        status = "N/A"
        if isinstance(db_count, int) and isinstance(sheet_count, int):
            status = "Match" if db_count == sheet_count else "Mismatch"
        
        report_data.append({
            "loan_id": loan_id,
            "supabase_table": table_name,
            "sheet_rows": sheet_count,
            "db_rows": db_count,
            "status": status,
        })
    
    df = pd.DataFrame(report_data)
    
    # This prints the CSV to stdout for the UI to capture
    print(df.to_csv(index=False))
    module_logger.info("Integrity check complete.")
# --- END ADDED CODE ---


def cli_main():
    module_logger.info("Kingdom Auto Finance system starting via CLI.")
    parser = argparse.ArgumentParser(
        description="Kingdom Auto Finance Processing System",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands:", required=True)

    # --- process command ---
    p_process = subparsers.add_parser(
        "process", help="Process new payments into amortization schedules."
    )
    p_process.set_defaults(func=lambda ns: process_payments())

    # --- report command ---
    p_report = subparsers.add_parser(
        "report",
        help="Generate summary or breakdown reports over a date range or all data."
    )
    p_report.add_argument(
        "--all",
        action="store_true",
        dest="all_dates",
        help="Ignore dates and include all available data",
    )
    p_report.add_argument(
        "arg1",
        nargs="?",
        help="Report mode (day-breakdown, loan-breakdown, full-breakdown) or start date",
    )
    p_report.add_argument(
        "arg2",
        nargs="?",
        help="Start date if mode given, otherwise end date",
    )
    p_report.add_argument(
        "arg3",
        nargs="?",
        help="End date if mode given",
    )
    p_report.set_defaults(func=run_report)

    # --- daily_summary command ---
    p_daily = subparsers.add_parser(
        "daily_summary",
        help="Update daily summary sheet incrementally or full rebuild."
    )
    p_daily.add_argument(
        "--full-rebuild",
        action="store_true",
        help="Force a full rebuild of the entire daily summary history.",
    )
    p_daily.set_defaults(
        func=lambda ns: generate_and_update_daily_summary(full_rebuild=ns.full_rebuild)
    )

    # --- fetch_payments command ---
    p_fetch = subparsers.add_parser(
        "fetch_payments",
        help="Fetch payments from source and append to KAF Payments Log."
    )
    fg = p_fetch.add_mutually_exclusive_group()
    fg.add_argument(
        "--range", nargs=2, metavar=("START_YYYY-MM-DD", "END_YYYY-MM-DD"),
        help="Fetch payments within specific date range."
    )
    fg.add_argument(
        "--all",
        action="store_true",
        help="Fetch all payments not already logged."
    )
    fg.add_argument(
        "--recent",
        type=int,
        metavar="DAYS",
        help="Fetch payments from the last N days."
    )
    p_fetch.set_defaults(func=run_fetch)

    # --- ADDED: check_integrity command ---
    p_integrity = subparsers.add_parser(
        "check_integrity",
        help="Compares amortization schedule row counts between Google Sheets and Supabase.",
    )
    p_integrity.set_defaults(func=run_integrity_check)
    # --- END ADDED CODE ---


    # --- Parse and dispatch ---
    try:
        args = parser.parse_args()
    except SystemExit:
        sys.exit(0)
    except Exception as e:
        module_logger.error(f"Error parsing arguments: {e}")
        parser.print_help()
        sys.exit(1)

    if hasattr(args, 'func') and callable(args.func):
        try:
            module_logger.info(f"Executing command: {args.command}")
            args.func(args)
            module_logger.info(f"Command '{args.command}' executed successfully.")
        except RuntimeError as e:
            # User-friendly error without full traceback
            print(e)
            sys.exit(1)
        except Exception as e:
            module_logger.error(
                f"Error executing command '{args.command}': {e}",
                exc_info=True
            )
            sys.exit(1)
        finally:
            module_logger.info("Kingdom Auto Finance CLI operation finished.")
    else:
        module_logger.error(f"No function bound to command '{args.command}'.")
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    cli_main()