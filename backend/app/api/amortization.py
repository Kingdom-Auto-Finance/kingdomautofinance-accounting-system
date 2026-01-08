"""
Amortization schedule API endpoints.
"""
from fastapi import APIRouter, HTTPException
from typing import Optional
from app.services.payment_service import import_amortization_job
from app.services.job_manager import job_manager
from app.db.supabase_client import supabase

router = APIRouter()


@router.post("/import")
async def import_schedules():
    """
    Import amortization schedules from Google Drive.
    Starts a background job and returns job_id for status tracking.

    This scans the Google Drive folder for loan spreadsheets and:
    - Creates schedule_{loan_id} tables
    - Imports amortization data
    - Skips tables that already have data
    """
    try:
        job_id = job_manager.start_job(
            job_type="import_amortization",
            target_func=import_amortization_job
        )

        return {
            "job_id": job_id,
            "message": "Amortization import started",
            "status_url": f"/api/v1/jobs/{job_id}"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/loans")
async def get_loans():
    """
    Get list of all loans.
    """
    try:
        result = supabase.table("loans").select("*").execute()

        return {
            "data": result.data,
            "count": len(result.data)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/schedule/{loan_id}")
async def get_loan_schedule(loan_id: str, limit: int = 1000):
    """
    Get amortization schedule for a specific loan.

    Args:
        loan_id: Loan identifier
        limit: Max number of rows to return (default: 1000)
    """
    try:
        table_name = f"schedule_{loan_id}"

        result = (
            supabase.table(table_name)
            .select("*")
            .order("paymentnumber")
            .limit(limit)
            .execute()
        )

        return {
            "loan_id": loan_id,
            "data": result.data,
            "count": len(result.data)
        }

    except Exception as e:
        if "does not exist" in str(e) or "42P01" in str(e):
            raise HTTPException(status_code=404, detail=f"Schedule not found for loan {loan_id}")
        raise HTTPException(status_code=500, detail=str(e))
