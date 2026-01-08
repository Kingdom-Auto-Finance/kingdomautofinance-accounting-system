"""
Payment API endpoints.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.services.payment_service import process_payments_job, fetch_payments_job
from app.services.job_manager import job_manager

router = APIRouter()


class FetchPaymentsRequest(BaseModel):
    mode: str = "all"  # 'all', 'range', 'recent'
    days: Optional[int] = None  # for 'recent' mode
    start_date: Optional[str] = None  # for 'range' mode (YYYY-MM-DD)
    end_date: Optional[str] = None  # for 'range' mode (YYYY-MM-DD)


@router.post("/fetch")
async def fetch_payments(request: FetchPaymentsRequest):
    """
    Fetch payments from Google Sheets.
    Starts a background job and returns job_id for status tracking.

    Modes:
    - 'all': Fetch all payments
    - 'range': Fetch payments within date range (requires start_date and end_date)
    - 'recent': Fetch recent N days (requires days)
    """
    try:
        job_id = job_manager.start_job(
            job_type="fetch_payments",
            target_func=fetch_payments_job,
            mode=request.mode,
            days=request.days,
            start_date=request.start_date,
            end_date=request.end_date
        )

        return {
            "job_id": job_id,
            "message": "Payment fetch started",
            "status_url": f"/api/v1/jobs/{job_id}"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/process")
async def process_payments():
    """
    Process unprocessed payments from payments_log.
    Starts a background job and returns job_id for status tracking.

    This allocates payments to amortization schedules, calculating:
    - Principal and interest allocation
    - Late fees
    - Payment status (PAID/PARTIAL)
    - Balance updates
    """
    try:
        job_id = job_manager.start_job(
            job_type="process_payments",
            target_func=process_payments_job
        )

        return {
            "job_id": job_id,
            "message": "Payment processing started",
            "status_url": f"/api/v1/jobs/{job_id}"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/log")
async def get_payment_log(
    limit: int = 100,
    offset: int = 0,
    loan_id: Optional[str] = None,
    processed: Optional[bool] = None
):
    """
    Get payment log entries with optional filtering.

    Query parameters:
    - limit: Max number of records to return (default: 100)
    - offset: Number of records to skip (default: 0)
    - loan_id: Filter by loan ID (optional)
    - processed: Filter by processed status (optional)
    """
    from app.db.supabase_client import supabase

    try:
        query = supabase.table("payments_log").select("*")

        if loan_id:
            query = query.eq("loan_id", loan_id)

        if processed is not None:
            query = query.eq("processed", processed)

        query = query.order("payment_date", desc=True).limit(limit).offset(offset)

        result = query.execute()

        return {
            "data": result.data,
            "count": len(result.data)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
