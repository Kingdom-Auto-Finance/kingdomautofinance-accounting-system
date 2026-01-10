"""
Payment processing service - wraps existing payment_processor.py
Preserves all business logic while making it accessible via API.
"""
import sys
import os
import io
from pathlib import Path
from typing import Dict, Any
from contextlib import redirect_stdout

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
            result = payment_fetcher.fetch_and_populate_payments(fetch_all=True)
        elif mode == "range" and start_date and end_date:
            result = payment_fetcher.fetch_and_populate_payments(start_date_str=start_date, end_date_str=end_date)
        elif mode == "recent" and days:
            result = payment_fetcher.fetch_and_populate_payments(fetch_recent_days=days)
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
        bootstrap.bootstrap_tables()

        job_manager.update_job_progress(job_id, 100, 100, "Amortization import completed")

        return {
            "success": True,
            "message": "Amortization schedules imported successfully"
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
        # Capture stdout since reporting.py prints CSV directly
        csv_buffer = io.StringIO()

        with redirect_stdout(csv_buffer):
            if report_type == "summary":
                reporting.generate_period_report(start_date, end_date)
            elif report_type == "day":
                reporting.generate_day_breakdown(start_date, end_date, all_dates=False)
            elif report_type == "loan":
                reporting.generate_loan_breakdown(start_date, end_date, all_dates=False)
            elif report_type == "full":
                reporting.generate_full_breakdown(start_date, end_date, all_dates=False)
            else:
                raise ValueError(f"Invalid report type: {report_type}")

        csv_content = csv_buffer.getvalue()

        if not csv_content:
            raise ValueError(f"No data generated for report type: {report_type}")

        return csv_content

    except Exception as e:
        raise Exception(f"Report generation failed: {str(e)}")
