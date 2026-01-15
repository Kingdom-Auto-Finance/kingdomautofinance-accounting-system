"""
Audit service for detecting payment discrepancies.

Compares payments_log amounts against schedule table totals
(principalpaid + interestpaid + latefee).
"""
import logging
from typing import Dict, List, Any
import calendar

from app.db.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

# Tolerance for floating point comparison (1 cent)
TOLERANCE = 0.01


def get_month_date_range(year: int, month: int) -> tuple[str, str]:
    """Get the start and end dates for a given month."""
    start_date = f"{year}-{month:02d}-01"
    last_day = calendar.monthrange(year, month)[1]
    end_date = f"{year}-{month:02d}-{last_day:02d}"
    return start_date, end_date


def fetch_payments_log_for_period(start_date: str, end_date: str) -> List[Dict]:
    """
    Fetch all payments from payments_log for the given date range.
    Returns list of dicts with: id, loan_id, payment_date, payment_amount
    """
    supabase = get_supabase_client()

    # Supabase has a 1000 row limit, so paginate
    all_payments = []
    offset = 0
    page_size = 1000

    while True:
        result = (
            supabase.table("payments_log")
            .select("id, loan_id, payment_date, payment_amount")
            .gte("payment_date", start_date)
            .lte("payment_date", end_date)
            .order("payment_date")
            .range(offset, offset + page_size - 1)
            .execute()
        )

        if not result.data:
            break

        all_payments.extend(result.data)

        if len(result.data) < page_size:
            break

        offset += page_size

    return all_payments


def fetch_schedule_totals_for_period(start_date: str, end_date: str) -> Dict[str, Dict[str, Dict]]:
    """
    Fetch allocation totals from payment_allocations ledger for all loans
    in the given date range.

    This uses the payment_allocations table which preserves the original
    payment_date, ensuring accurate cash-basis comparisons.

    Returns nested dict: {loan_id: {payment_date: {principal, interest, late_fee, total}}}
    """
    supabase = get_supabase_client()

    # Query payment_allocations table with pagination
    all_allocations = []
    page_size = 1000
    offset = 0

    while True:
        try:
            result = (
                supabase.table("payment_allocations")
                .select("loan_id, payment_date, principal_allocated, interest_allocated, late_fee_allocated")
                .gte("payment_date", start_date)
                .lte("payment_date", end_date)
                .range(offset, offset + page_size - 1)
                .execute()
            )

            if not result.data:
                break

            all_allocations.extend(result.data)

            if len(result.data) < page_size:
                break

            offset += page_size

        except Exception as e:
            logger.error(f"Failed to query payment_allocations: {e}")
            return {}

    # Group by loan_id and payment_date
    schedule_data: Dict[str, Dict[str, Dict]] = {}

    for alloc in all_allocations:
        loan_id = alloc["loan_id"]
        raw_date = alloc.get("payment_date")
        if not raw_date:
            continue

        # Extract date portion (handle both date and datetime formats)
        payment_date = str(raw_date)[:10]

        principal = float(alloc.get("principal_allocated") or 0)
        interest = float(alloc.get("interest_allocated") or 0)
        late_fee = float(alloc.get("late_fee_allocated") or 0)

        if loan_id not in schedule_data:
            schedule_data[loan_id] = {}

        if payment_date in schedule_data[loan_id]:
            schedule_data[loan_id][payment_date]["principal"] += principal
            schedule_data[loan_id][payment_date]["interest"] += interest
            schedule_data[loan_id][payment_date]["late_fee"] += late_fee
            schedule_data[loan_id][payment_date]["total"] += principal + interest + late_fee
        else:
            schedule_data[loan_id][payment_date] = {
                "principal": principal,
                "interest": interest,
                "late_fee": late_fee,
                "total": principal + interest + late_fee,
            }

    return schedule_data


def find_discrepancies(
    payments: List[Dict],
    schedule_data: Dict[str, Dict[str, Dict]]
) -> List[Dict]:
    """
    Compare payments_log entries against schedule totals.
    Returns list of discrepancies.
    """
    discrepancies = []

    for payment in payments:
        loan_id = payment["loan_id"]
        payment_date = payment["payment_date"]
        payment_amount = float(payment["payment_amount"])

        # Get schedule totals for this loan/date
        loan_schedules = schedule_data.get(loan_id, {})
        schedule_totals = loan_schedules.get(payment_date, {})

        schedule_total = schedule_totals.get("total", 0.0)
        difference = payment_amount - schedule_total

        # Check if discrepancy exceeds tolerance
        if abs(difference) > TOLERANCE:
            discrepancies.append({
                "loan_id": loan_id,
                "payment_log_id": payment["id"],
                "payment_date": payment_date,
                "payment_log_amount": round(payment_amount, 2),
                "schedule_principal": round(schedule_totals.get("principal", 0.0), 2),
                "schedule_interest": round(schedule_totals.get("interest", 0.0), 2),
                "schedule_late_fee": round(schedule_totals.get("late_fee", 0.0), 2),
                "schedule_total": round(schedule_total, 2),
                "difference": round(difference, 2),
            })

    return discrepancies


def fetch_monthly_discrepancies(year: int, month: int) -> Dict[str, Any]:
    """
    Get all discrepancy dates for a given month.

    Returns:
        {
            "year": 2026,
            "month": 1,
            "discrepancy_dates": ["2026-01-05", "2026-01-12"],
            "summary": {
                "total_discrepancies": 5,
                "total_affected_loans": 3
            }
        }
    """
    start_date, end_date = get_month_date_range(year, month)

    # Fetch data
    payments = fetch_payments_log_for_period(start_date, end_date)
    schedule_data = fetch_schedule_totals_for_period(start_date, end_date)

    # Find discrepancies
    discrepancies = find_discrepancies(payments, schedule_data)

    # Extract unique dates and loans
    discrepancy_dates = sorted(set(d["payment_date"] for d in discrepancies))
    affected_loans = set(d["loan_id"] for d in discrepancies)

    return {
        "year": year,
        "month": month,
        "discrepancy_dates": discrepancy_dates,
        "summary": {
            "total_discrepancies": len(discrepancies),
            "total_affected_loans": len(affected_loans),
        }
    }


def fetch_date_discrepancies(date_str: str) -> Dict[str, Any]:
    """
    Get detailed discrepancies for a specific date.

    Args:
        date_str: Date in YYYY-MM-DD format

    Returns:
        {
            "date": "2026-01-05",
            "discrepancies": [
                {
                    "loan_id": "12345",
                    "payment_log_id": "uuid",
                    "payment_log_amount": 500.00,
                    "schedule_principal": 300.00,
                    "schedule_interest": 150.00,
                    "schedule_late_fee": 25.00,
                    "schedule_total": 475.00,
                    "difference": 25.00
                }
            ]
        }
    """
    # Fetch data for just that day
    payments = fetch_payments_log_for_period(date_str, date_str)
    schedule_data = fetch_schedule_totals_for_period(date_str, date_str)

    # Find discrepancies
    discrepancies = find_discrepancies(payments, schedule_data)

    # Sort by absolute difference (largest first)
    discrepancies.sort(key=lambda d: abs(d["difference"]), reverse=True)

    return {
        "date": date_str,
        "discrepancies": discrepancies,
    }
