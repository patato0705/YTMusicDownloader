# backend/routers/jobs.py
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..db import get_session
from ..dependencies import require_auth, require_admin
from ..models import Job, User
from ..jobs import jobqueue
from ..schemas.jobs import (
    EnqueueRequest,
    EnqueueResponse,
    JobOut,
    CancelRequest,
    RequeueRequest,
)
from ..time_utils import now_utc
from .. import config

logger = logging.getLogger("routers.jobs")
router = APIRouter(prefix="/api/jobs", tags=["Jobs"])


# ============================================================================
# HELPERS
# ============================================================================

def _job_to_dict(job: Job) -> Dict[str, Any]:
    """Convert Job ORM to dict"""
    return {
        "id": job.id,
        "type": job.type,
        "status": job.status,
        "attempts": job.attempts,
        "max_attempts": job.max_attempts,
        "priority": job.priority,
        "scheduled_at": job.scheduled_at,
        "reserved_by": job.reserved_by,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "created_at": job.created_at,
        "last_error": job.last_error,
        "result": job.result,
        "payload": job.payload,
        "user_id": getattr(job, "user_id", None),  # May be None if not yet migrated
    }


def _user_can_access_job(user: User, job: Job) -> bool:
    """Check if user can access this job"""
    # Admins can access all jobs
    if user.role == config.ROLE_ADMINISTRATOR:
        return True
    
    # Users can only access their own jobs
    job_user_id = getattr(job, "user_id", None)
    return job_user_id == user.id


# ============================================================================
# ROUTES
# ============================================================================

@router.post("/enqueue", response_model=EnqueueResponse, status_code=status.HTTP_201_CREATED)
def enqueue_job_endpoint(
    req: EnqueueRequest,
    current_user: User = Depends(require_auth),
    session: Session = Depends(get_session),
) -> EnqueueResponse:
    """
    Enqueue a new job.
    
    Permissions: All authenticated users
    The job will be associated with the current user.
    """
    if not req.type or not req.type.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job type is required"
        )
    
    try:
        # Add user_id to payload
        payload = req.payload or {}
        payload["user_id"] = current_user.id
        
        job = jobqueue.enqueue_job(
            session=session,
            job_type=req.type.strip(),
            payload=payload,
            scheduled_at=req.scheduled_at,
            priority=req.priority if req.priority is not None else 0,
            max_attempts=req.max_attempts if req.max_attempts is not None else 5,
        )
        
        logger.info(f"User {current_user.username} enqueued job {job.id} (type={req.type})")
        
        return EnqueueResponse(
            ok=True,
            job_id=job.id,
            message="Job enqueued successfully"
        )
    
    except Exception as e:
        logger.exception(f"Failed to enqueue job {req.type}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("", response_model=List[JobOut])
def list_jobs(
    job_status: Optional[str] = Query(
        None,
        alias="status",
        description="Filter by status (queued, reserved, done, failed)"
    ),
    limit: int = Query(100, ge=1, le=1000, description="Max results"),
    current_user: User = Depends(require_auth),
    session: Session = Depends(get_session),
) -> List[JobOut]:
    """
    List jobs.
    
    Permissions:
    - Admins see all jobs
    - Users see only their own jobs
    
    Results ordered by created_at desc (newest first).
    """
    try:
        query = session.query(Job)
        
        # Filter by user (non-admins see only their jobs)
        if current_user.role != config.ROLE_ADMINISTRATOR:
            query = query.filter(Job.user_id == current_user.id)
        
        # Filter by status if provided
        if job_status:
            query = query.filter(Job.status == job_status)
        
        # Order and limit
        query = query.order_by(Job.created_at.desc()).limit(limit)
        
        jobs = query.all()
        return [JobOut(**_job_to_dict(job)) for job in jobs]
    
    except Exception as e:
        logger.exception("list_jobs failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/{job_id}", response_model=JobOut)
def get_job(
    job_id: int,
    current_user: User = Depends(require_auth),
    session: Session = Depends(get_session),
) -> JobOut:
    """
    Get a single job by ID.
    
    Permissions:
    - Admins can view any job
    - Users can only view their own jobs
    """
    try:
        job = session.get(Job, job_id)
        
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found"
            )
        
        # Check permission
        if not _user_can_access_job(current_user, job):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to view this job"
            )
        
        return JobOut(**_job_to_dict(job))
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"get_job failed for id={job_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/{job_id}/cancel")
def cancel_job(
    job_id: int,
    body: CancelRequest,
    current_user: User = Depends(require_auth),
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """
    Cancel a job.
    
    Permissions:
    - Admins can cancel any job
    - Users can only cancel their own jobs
    - Cannot cancel jobs that are already done/failed
    """
    try:
        job = session.get(Job, job_id)
        
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found"
            )
        
        # Check permission
        if not _user_can_access_job(current_user, job):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to cancel this job"
            )
        
        # Check if job can be cancelled
        if job.status in ["done", "failed"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot cancel job with status '{job.status}'"
            )
        
        # Cancel the job
        message = body.message or "Cancelled by user"
        jobqueue.mark_job_failed(
            session,
            job_id,
            error_message=message,
            retry_delay_seconds=None  # No retry
        )
        
        logger.info(f"User {current_user.username} cancelled job {job_id}")
        
        return {
            "ok": True,
            "job_id": job_id,
            "status": "failed",
            "message": message
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"cancel_job failed for id={job_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/{job_id}/requeue")
def requeue_job(
    job_id: int,
    body: RequeueRequest,
    current_user: User = Depends(require_admin),  # Admin only
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """
    Requeue a failed job.
    
    Permissions: Administrators only
    
    Puts a job back in the queue, optionally with a delay.
    """
    try:
        job = session.get(Job, job_id)
        
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found"
            )
        
        # Calculate scheduled_at if delay provided
        scheduled_at = None
        if body.delay_seconds is not None:
            scheduled_at = now_utc() + timedelta(seconds=body.delay_seconds)
        
        # Update job
        job.status = "queued"
        job.scheduled_at = scheduled_at
        job.last_error = None
        job.attempts = 0  # Reset attempts
        session.add(job)
        session.commit()
        session.refresh(job)
        
        logger.info(f"Admin {current_user.username} requeued job {job_id}")
        
        return {
            "ok": True,
            "job_id": job_id,
            "status": "queued",
            "scheduled_at": scheduled_at.isoformat() if scheduled_at else None
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"requeue_job failed for id={job_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/stats/summary")
def get_job_stats(
    current_user: User = Depends(require_auth),
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """
    Get job statistics.
    
    Permissions:
    - Admins see global stats
    - Users see only their own stats
    """
    try:
        from sqlalchemy import func
        
        query = session.query(Job.status, func.count(Job.id))
        
        # Filter by user for non-admins
        if current_user.role != config.ROLE_ADMINISTRATOR:
            query = query.filter(Job.user_id == current_user.id)
        
        # Execute query and build dict
        results = query.group_by(Job.status).all()
        stats: Dict[str, int] = {status: count for status, count in results}
        
        return {
            "ok": True,
            "stats": stats,
            "total": sum(stats.values()),
        }
    
    except Exception as e:
        logger.exception("get_job_stats failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )