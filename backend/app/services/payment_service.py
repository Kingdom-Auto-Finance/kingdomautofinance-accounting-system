"""
Payment processing service - wraps existing payment_processor.py
Preserves all business logic while making it accessible via API.
"""
import sys
import os
from pathlib import Path
from typing import Dict, Any

# Add parent src directory to path to import existing modules
project_root = Path(__file__).parent.parent.parent.parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

# Import existing payment processor (PRESERVED AS-IS)
import payment_processor
import payment_fetcher
import bootstrap
import reporting
from app.services.job_manager import job_manager


def process_payments_job(job_id: str) -> Dict[str, Any]:
    """
    Background job to process payments.
    Wraps the existing payment_processor.process_payments() function.

    Args:
        job_id: Job ID for progress tracking

    Returns:
        Dict with results
    """
    # Update progress
    job_manager.update_job_progress(job_id, 0, 100, "Starting payment processing...")

    try:
        # Call the existing payment processor (PRESERVED)
        success = payment_processor.process_payments()

        # Update progress
        job_manager.update_job_progress(job_id, 100, 100, "Payment processing completed")

        return {
            "success": success,
            "message": "Payment processing completed successfully" if success else "Payment processing completed with errors"
        }

    except Exception as e:
        raise Exception(f"Payment processing failed: {str(e)}")


def fetch_payments_job(job_id: str, mode: str = "all", days: int = None, start_date: str = None, end_date: str = None) -> Dict[str, Any]:
    """
    Background job to fetch payments from Google Sheets.
    Wraps the existing payment_fetcher functions.

    Args:
        job_id: Job ID for progress tracking
        mode: Fetch mode ('all', 'range', 'recent')
        days: Number of recent days (for 'recent' mode)
        start_date: Start date (for 'range' mode)
        end_date: End date (for 'range' mode)

    Returns:
        Dict with results
    """
    job_manager.update_job_progress(job_id, 0, 100, "Starting payment fetch...")

    try:
        if mode == "all":
            result = payment_fetcher.fetch_and_insert_all_payments()
        elif mode == "range" and start_date and end_date:
            result = payment_fetcher.fetch_and_insert_date_range(start_date, end_date)
        elif mode == "recent" and days:
            result = payment_fetcher.fetch_and_insert_recent(days)
        else:
            raise ValueError(f"Invalid fetch mode or missing parameters: {mode}")

        job_manager.update_job_progress(job_id, 100, 100, "Payment fetch completed")

        return {
            "success": result,
            "message": f"Fetched payments using mode: {mode}"
        }

    except Exception as e:
        raise Exception(f"Payment fetch failed: {str(e)}")


def import_amortization_job(job_id: str) -> Dict[str, Any]:
    """
    Background job to import amortization schedules from Google Drive.
    Wraps the existing bootstrap functions.

    Args:
        job_id: Job ID for progress tracking

    Returns:
        Dict with results
    """
    job_manager.update_job_progress(job_id, 0, 100, "Starting amortization import...")

    try:
        # Call the existing bootstrap function (PRESERVED)
        success = bootstrap.import_all_schedules_from_drive()

        job_manager.update_job_progress(job_id, 100, 100, "Amortization import completed")

        return {
            "success": success,
            "message": "Amortization schedules imported successfully" if success else "Import completed with errors"
        }

    except Exception as e:
        raise Exception(f"Amortization import failed: {str(e)}")


def generate_report(report_type: str, start_date: str = None, end_date: str = None) -> str:
    """
    Generate a report and return CSV content.
    Wraps the existing reporting functions.

    Args:
        report_type: Type of report ('summary', 'day', 'loan', 'full')
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)

    Returns:
        CSV content as string
    """
    try:
        if report_type == "summary":
            csv_path = reporting.generate_summary_totals_report(start_date, end_date)
        elif report_type == "day":
            csv_path = reporting.generate_day_breakdown_report(start_date, end_date)
        elif report_type == "loan":
            csv_path = reporting.generate_loan_breakdown_report(start_date, end_date)
        elif report_type == "full":
            csv_path = reporting.generate_full_breakdown_report(start_date, end_date)
        else:
            raise ValueError(f"Invalid report type: {report_type}")

        # Read the CSV file
        with open(csv_path, 'r') as f:
            csv_content = f.read()

        return csv_content

    except Exception as e:
        raise Exception(f"Report generation failed: {str(e)}")
