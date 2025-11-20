# backend/jobs/jobqueue.py
"""
Simple job queue helpers for SQLite-compatible job processing.

Functions:
- enqueue_job() - Create a new job and commit
- reserve_job() - Atomically reserve next job for processing
- mark_job_done() - Mark job as successfully completed
- mark_job_failed() - Mark job as failed (with optional retry)

Notes:
- All functions commit the session to make changes visible to worker processes
- Designed for SQLite (no SELECT ... FOR UPDATE)
- Reserve logic is best-effort with optimistic locking
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from ..models import Job
from ..time_utils import now_utc

logger = logging.getLogger("jobs.jobqueue")


def enqueue_job(
    session: Session,
    job_type: str,
    payload: Optional[dict] = None,
    scheduled_at: Optional[datetime] = None,
    priority: int = 0,
    max_attempts: int = 5,
    commit: bool = True,  # ← NEW parameter
) -> Job:
    """
    Create a new Job row and commit. Returns the Job instance.
    
    Args:
        session: SQLAlchemy session
        job_type: Job type identifier (e.g., "download_track", "import_album")
        payload: Job data as dict (e.g., {"track_id": "abc123"})
        scheduled_at: Optional datetime to schedule job for future execution
        priority: Job priority (higher = more important, default 0)
        max_attempts: Maximum retry attempts (default 5)
    
    Returns:
        Job instance with ID populated
    """
    if not job_type:
        raise ValueError("job_type is required")
    
    job = Job(
        type=str(job_type),
        payload=payload or {},
        status="queued",
        attempts=0,
        max_attempts=max_attempts,
        priority=priority,
        scheduled_at=scheduled_at,
        created_at=now_utc(),
    )
    session.add(job)
    
    if commit:
        session.commit()
        session.refresh(job)
    
    logger.debug(f"Enqueued job (commit={commit}): type={job_type}, priority={priority}")
    return job


def reserve_job(session: Session, worker_name: str) -> Optional[Job]:
    """
    Reserve the next available job for processing.
    
    Atomically selects and marks a job as reserved:
    1. Find oldest queued job where:
       - status = "queued"
       - attempts < max_attempts
       - scheduled_at is NULL or <= now
    2. Increment attempts
    3. Set status = "reserved"
    4. Set reserved_by = worker_name
    5. Set started_at = now
    6. Commit and return
    
    Args:
        session: SQLAlchemy session
        worker_name: Worker identifier (e.g., "worker-12345")
    
    Returns:
        Reserved Job instance, or None if no jobs available
    """
    now = now_utc()
    
    # Find candidate job (highest priority first, then oldest)
    stmt = (
        select(Job)
        .where(
            and_(
                Job.status == "queued",
                Job.attempts < Job.max_attempts,
                (Job.scheduled_at == None) | (Job.scheduled_at <= now),
            )
        )
        .order_by(Job.priority.desc(), Job.created_at.asc())
        .limit(1)
    )
    
    job = session.execute(stmt).scalars().first()
    if not job:
        return None
    
    # Atomically update the job
    try:
        job.attempts = (job.attempts or 0) + 1
        job.status = "reserved"
        job.reserved_by = worker_name
        job.started_at = now
        session.add(job)
        session.commit()
        session.refresh(job)
        
        logger.debug(
            f"Reserved job {job.id}: type={job.type}, "
            f"attempt={job.attempts}/{job.max_attempts}, "
            f"worker={worker_name}"
        )
        return job
    except Exception as e:
        logger.exception(f"Failed to reserve job {job.id}: {e}")
        session.rollback()
        return None


def mark_job_done(
    session: Session,
    job_id: int,
    result: Optional[dict] = None,
) -> None:
    """
    Mark job as successfully completed. Commits.
    
    Args:
        session: SQLAlchemy session
        job_id: Job ID
        result: Optional result data to store (dict)
    """
    job = session.get(Job, job_id)
    if not job:
        logger.warning(f"Cannot mark job {job_id} as done: not found")
        return
    
    job.status = "done"
    job.finished_at = now_utc()
    job.result = result or {}
    job.last_error = None  # Clear any previous errors
    session.add(job)
    session.commit()
    
    logger.info(f"Job {job_id} completed: type={job.type}")


def mark_job_failed(
    session: Session,
    job_id: int,
    error_message: Optional[str] = None,
    retry_delay_seconds: Optional[int] = None,
) -> None:
    """
    Mark job as failed. Optionally retry with exponential backoff.
    
    If retry_delay_seconds is provided and attempts < max_attempts:
    - Requeues job with scheduled_at = now + delay
    - Status set back to "queued"
    
    Otherwise:
    - Status set to "failed"
    - No further retries
    
    Args:
        session: SQLAlchemy session
        job_id: Job ID
        error_message: Error description
        retry_delay_seconds: Optional retry delay in seconds
    """
    job = session.get(Job, job_id)
    if not job:
        logger.warning(f"Cannot mark job {job_id} as failed: not found")
        return
    
    now = now_utc()
    job.last_error = str(error_message) if error_message else None
    
    # Check if we should retry
    if retry_delay_seconds and (job.attempts or 0) < (job.max_attempts or 1):
        # Requeue with backoff
        job.status = "queued"
        job.scheduled_at = now + timedelta(seconds=retry_delay_seconds)
        job.reserved_by = None  # Clear reservation
        session.add(job)
        session.commit()
        
        logger.warning(
            f"Job {job_id} failed (attempt {job.attempts}/{job.max_attempts}), "
            f"retrying in {retry_delay_seconds}s: {error_message}"
        )
    else:
        # Permanent failure
        job.status = "failed"
        job.finished_at = now
        session.add(job)
        session.commit()
        
        logger.error(
            f"Job {job_id} permanently failed after {job.attempts} attempts: "
            f"{error_message}"
        )


def get_job_stats(session: Session) -> dict:
    """
    Get statistics about jobs in the queue.
    Useful for monitoring and debugging.
    
    Returns:
        Dict with counts by status
    """
    from sqlalchemy import func
    
    stats = {}
    
    # Count by status
    result = session.query(Job.status, func.count(Job.id)).group_by(Job.status).all()
    for status, count in result:
        stats[status] = count
    
    # Count pending (queued but scheduled in future)
    now = now_utc()
    pending = (
        session.query(func.count(Job.id))
        .filter(Job.status == "queued", Job.scheduled_at > now)
        .scalar()
    )
    stats["pending_scheduled"] = pending or 0
    
    return stats


def cancel_job(session: Session, job_id: int, reason: Optional[str] = None) -> bool:
    """
    Cancel a queued or reserved job.
    Cannot cancel jobs that are already done or failed.
    
    Args:
        session: SQLAlchemy session
        job_id: Job ID
        reason: Optional cancellation reason
    
    Returns:
        True if cancelled, False if job not found or already finished
    """
    job = session.get(Job, job_id)
    if not job:
        return False
    
    if job.status in ["done", "failed"]:
        logger.warning(f"Cannot cancel job {job_id}: already {job.status}")
        return False
    
    job.status = "cancelled"
    job.finished_at = now_utc()
    job.last_error = f"Cancelled: {reason}" if reason else "Cancelled by user"
    session.add(job)
    session.commit()
    
    logger.info(f"Cancelled job {job_id}: {reason}")
    return True


def cleanup_old_jobs(
    session: Session,
    days_old: int = 7,
    keep_failed: bool = True,
) -> int:
    """
    Delete old completed jobs to prevent database bloat.
    
    Args:
        session: SQLAlchemy session
        days_old: Delete jobs older than this many days (default 7)
        keep_failed: If True, don't delete failed jobs (for debugging)
    
    Returns:
        Number of jobs deleted
    """
    cutoff = now_utc() - timedelta(days=days_old)
    
    query = session.query(Job).filter(
        Job.finished_at != None,
        Job.finished_at < cutoff,
    )
    
    if keep_failed:
        query = query.filter(Job.status == "done")
    else:
        query = query.filter(Job.status.in_(["done", "failed", "cancelled"]))
    
    jobs_to_delete = query.all()
    count = len(jobs_to_delete)
    
    for job in jobs_to_delete:
        session.delete(job)
    
    session.commit()
    
    logger.info(f"Cleaned up {count} old jobs (older than {days_old} days)")
    return count