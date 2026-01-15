"""
Audit API endpoints for payment discrepancy detection.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any
import logging

from app.services.audit_service import (
    fetch_monthly_discrepancies,
    fetch_date_discrepancies,
)

logger = logging.getLogger(__name__)
router = APIRouter()


class MonthlyDiscrepanciesRequest(BaseModel):
    year: int = Field(..., ge=2000, le=2100, description="Year (e.g., 2026)")
    month: int = Field(..., ge=1, le=12, description="Month (1-12)")


class DateDiscrepanciesRequest(BaseModel):
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="Date in YYYY-MM-DD format")


class DiscrepancySummary(BaseModel):
    total_discrepancies: int
    total_affected_loans: int


class MonthlyDiscrepanciesResponse(BaseModel):
    year: int
    month: int
    discrepancy_dates: List[str]
    summary: DiscrepancySummary


class DiscrepancyDetail(BaseModel):
    loan_id: str
    payment_log_id: str
    payment_date: str
    payment_log_amount: float
    schedule_principal: float
    schedule_interest: float
    schedule_late_fee: float
    schedule_total: float
    difference: float


class DateDiscrepanciesResponse(BaseModel):
    date: str
    discrepancies: List[DiscrepancyDetail]


@router.post("/monthly-discrepancies", response_model=MonthlyDiscrepanciesResponse)
async def get_monthly_discrepancies(request: MonthlyDiscrepanciesRequest):
    """
    Get dates with payment discrepancies for a given month.

    Returns a list of dates where the sum of (principalpaid + interestpaid + latefee)
    from schedule tables does not match payment_amount in payments_log.
    """
    try:
        result = fetch_monthly_discrepancies(request.year, request.month)
        return result
    except Exception as e:
        logger.error(f"Failed to fetch monthly discrepancies: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/date-discrepancies", response_model=DateDiscrepanciesResponse)
async def get_date_discrepancies(request: DateDiscrepanciesRequest):
    """
    Get detailed discrepancies for a specific date.

    Returns a list of all payments where the schedule totals don't match
    the payment_log amount, sorted by difference (largest first).
    """
    try:
        result = fetch_date_discrepancies(request.date)
        return result
    except Exception as e:
        logger.error(f"Failed to fetch date discrepancies: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
