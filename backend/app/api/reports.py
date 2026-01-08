"""
Reporting API endpoints.
"""
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from typing import Optional
from app.services.payment_service import generate_report

router = APIRouter()


class ReportRequest(BaseModel):
    start_date: str  # YYYY-MM-DD
    end_date: str  # YYYY-MM-DD


@router.post("/summary")
async def get_summary_report(request: ReportRequest):
    """
    Generate summary totals report.

    Returns CSV with:
    - Total principal paid
    - Total interest paid
    - Total late fees
    - Number of payments
    """
    try:
        csv_content = generate_report("summary", request.start_date, request.end_date)

        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=summary_report_{request.start_date}_{request.end_date}.csv"
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/day-breakdown")
async def get_day_breakdown_report(request: ReportRequest):
    """
    Generate day-by-day breakdown report.

    Returns CSV with daily totals for:
    - Payment date
    - Principal paid
    - Interest paid
    - Late fees
    - Payment count
    """
    try:
        csv_content = generate_report("day", request.start_date, request.end_date)

        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=day_breakdown_{request.start_date}_{request.end_date}.csv"
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/loan-breakdown")
async def get_loan_breakdown_report(request: ReportRequest):
    """
    Generate loan-by-loan breakdown report.

    Returns CSV with per-loan totals for:
    - Loan ID
    - Principal paid
    - Interest paid
    - Late fees
    - Payment count
    """
    try:
        csv_content = generate_report("loan", request.start_date, request.end_date)

        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=loan_breakdown_{request.start_date}_{request.end_date}.csv"
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/full-breakdown")
async def get_full_breakdown_report(request: ReportRequest):
    """
    Generate full detailed breakdown report.

    Returns CSV with:
    - Loan ID
    - Payment date
    - Principal paid
    - Interest paid
    - Late fees
    - Payment amount
    """
    try:
        csv_content = generate_report("full", request.start_date, request.end_date)

        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=full_breakdown_{request.start_date}_{request.end_date}.csv"
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
