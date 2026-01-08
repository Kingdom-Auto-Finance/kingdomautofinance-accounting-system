"""
Background job management system using Python threading.
Simple, lightweight alternative to Celery/Redis for single-server deployments.
"""
import threading
import traceback
import uuid
from datetime import datetime
from typing import Callable, Any, Optional, Dict
from app.db.supabase_client import supabase


class JobManager:
    """
    Manages background jobs using Python threading.
    Job status is tracked in Supabase 'jobs' table.
    """

    def __init__(self):
        self.active_threads: Dict[str, threading.Thread] = {}

    def create_job(self, job_type: str, user_id: Optional[str] = None) -> str:
        """
        Create a new job record in the database.

        Args:
            job_type: Type of job (e.g., 'process_payments', 'fetch_payments')
            user_id: Optional user ID who initiated the job

        Returns:
            job_id: UUID of the created job
        """
        job_data = {
            "job_type": job_type,
            "status": "queued",
            "progress": {"current": 0, "total": 0, "message": "Job queued"},
        }

        if user_id:
            job_data["user_id"] = user_id

        result = supabase.table("jobs").insert(job_data).execute()

        if not result.data:
            raise Exception("Failed to create job in database")

        job_id = result.data[0]["id"]
        return job_id

    def update_job_status(
        self,
        job_id: str,
        status: str,
        progress: Optional[Dict[str, Any]] = None,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ):
        """
        Update job status in the database.

        Args:
            job_id: Job UUID
            status: New status ('queued', 'running', 'completed', 'failed')
            progress: Optional progress data
            result: Optional result data (for completed jobs)
            error: Optional error message (for failed jobs)
        """
        update_data = {"status": status}

        if status == "running" and not supabase.table("jobs").select("started_at").eq("id", job_id).execute().data[0].get("started_at"):
            update_data["started_at"] = datetime.utcnow().isoformat()

        if status in ("completed", "failed"):
            update_data["completed_at"] = datetime.utcnow().isoformat()

        if progress:
            update_data["progress"] = progress

        if result:
            update_data["result"] = result

        if error:
            update_data["error"] = error

        supabase.table("jobs").update(update_data).eq("id", job_id).execute()

    def update_job_progress(self, job_id: str, current: int, total: int, message: str = ""):
        """
        Update job progress information.

        Args:
            job_id: Job UUID
            current: Current progress count
            total: Total items to process
            message: Optional progress message
        """
        progress = {
            "current": current,
            "total": total,
            "message": message,
            "percent": int((current / total * 100)) if total > 0 else 0,
        }

        self.update_job_status(job_id, "running", progress=progress)

    def run_job(
        self,
        job_id: str,
        target_func: Callable,
        *args,
        **kwargs
    ):
        """
        Execute a job function in a background thread.

        Args:
            job_id: Job UUID
            target_func: Function to execute
            *args: Positional arguments for target_func
            **kwargs: Keyword arguments for target_func
        """

        def wrapper():
            try:
                # Update status to running
                self.update_job_status(job_id, "running")

                # Execute the target function
                # The target function should call update_job_progress() as needed
                result = target_func(job_id, *args, **kwargs)

                # Mark as completed
                self.update_job_status(
                    job_id,
                    "completed",
                    result=result if isinstance(result, dict) else {"result": str(result)},
                )

            except Exception as e:
                # Mark as failed with error details
                error_msg = f"{str(e)}\n{traceback.format_exc()}"
                self.update_job_status(job_id, "failed", error=error_msg)

            finally:
                # Clean up thread reference
                if job_id in self.active_threads:
                    del self.active_threads[job_id]

        # Create and start thread
        thread = threading.Thread(target=wrapper, daemon=True)
        self.active_threads[job_id] = thread
        thread.start()

    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get current status of a job from database.

        Args:
            job_id: Job UUID

        Returns:
            Job data dictionary or None if not found
        """
        result = supabase.table("jobs").select("*").eq("id", job_id).execute()

        if result.data:
            return result.data[0]

        return None

    def start_job(
        self,
        job_type: str,
        target_func: Callable,
        user_id: Optional[str] = None,
        *args,
        **kwargs
    ) -> str:
        """
        Convenience method to create and start a job in one call.

        Args:
            job_type: Type of job
            target_func: Function to execute
            user_id: Optional user ID
            *args: Arguments for target_func
            **kwargs: Keyword arguments for target_func

        Returns:
            job_id: UUID of the created job
        """
        job_id = self.create_job(job_type, user_id)
        self.run_job(job_id, target_func, *args, **kwargs)
        return job_id


# Singleton instance
job_manager = JobManager()
