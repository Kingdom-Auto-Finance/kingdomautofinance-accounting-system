"""
Job status API endpoints.
"""
from fastapi import APIRouter, HTTPException
from app.services.job_manager import job_manager

router = APIRouter()


@router.get("/{job_id}")
async def get_job_status(job_id: str):
    """
    Get status of a background job.

    Returns:
    - id: Job UUID
    - job_type: Type of job
    - status: Current status ('queued', 'running', 'completed', 'failed')
    - progress: Progress information (current, total, message, percent)
    - result: Result data (for completed jobs)
    - error: Error message (for failed jobs)
    - created_at: When job was created
    - started_at: When job started running
    - completed_at: When job finished
    """
    try:
        job = job_manager.get_job_status(job_id)

        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

        return job

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/")
async def list_jobs(limit: int = 50, status: str = None):
    """
    List recent jobs with optional status filter.

    Query parameters:
    - limit: Max number of jobs to return (default: 50)
    - status: Filter by status ('queued', 'running', 'completed', 'failed')
    """
    from app.db.supabase_client import supabase

    try:
        query = supabase.table("jobs").select("*")

        if status:
            query = query.eq("status", status)

        query = query.order("created_at", desc=True).limit(limit)

        result = query.execute()

        return {
            "data": result.data,
            "count": len(result.data)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
