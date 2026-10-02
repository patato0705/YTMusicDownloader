# backend/jobs/jobqueue.py
"""
Simple job queue helpers for SQLite-compatible job processing.

Functions:
- enqueue_job() - Create a new job and commit
- reserve_job() - Atomically reserve next job for processing
- heartbeat_job() - Record that the worker holding a job is still alive
- mark_job_done() - Mark job as successfully completed
- mark_job_failed() - Mark job as failed (with optional retry)
- reclaim_orphaned_jobs() - Requeue jobs left "reserved" by a dead worker
- cancel_job() - Cancel a queued or reserved job
- cancel_download_jobs() - Cancel the download jobs of a set of tracks
- set_download_track_status() - Mirror a download job's state onto its track
- cleanup_old_jobs() - Delete old finished jobs

Notes:
- All functions commit the session to make changes visible to worker processes
- Several worker processes poll this queue concurrently (see
  deploy/supervisord.conf), so reserve_job() must be safe against two
  workers picking the same row. It is: the claim is a conditional UPDATE
  (... WHERE status = 'queued' AND attempts = <seen>) and only the worker
  whose UPDATE hit a row wins. No SELECT ... FOR UPDATE needed, so this
  works on SQLite as-is.
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta
from typing import Collection, Optional, Sequence

from sqlalchemy import select, update, and_, or_
from sqlalchemy.orm import Session

from ..models import Job, Track
from ..time_utils import now_utc

logger = logging.getLogger("jobs.jobqueue")

# How many lost reservation races to retry before giving up this poll.
RESERVE_MAX_RACES = 5

# A reserved job whose heartbeat is older than this is treated as abandoned.
# Workers heartbeat every HEARTBEAT_INTERVAL_SECONDS (jobs/worker.py), so this
# tolerates a few missed beats before pulling a job out from under a worker
# that's merely slow.
STALE_HEARTBEAT_SECONDS = 300


def enqueue_job(
    session: Session,
    job_type: str,
    payload: Optional[dict] = None,
    scheduled_at: Optional[datetime] = None,
    priority: int = 0,
    max_attempts: int = 5,
    user_id: Optional[int] = None,  # NEW parameter
    commit: bool = True,
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
        user_id: Optional user ID who initiated the job (for tracking)
        commit: Whether to commit immediately (default True)
    
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
        user_id=user_id,  # NEW: Store user_id on Job model
    )
    session.add(job)
    
    if commit:
        session.commit()
        session.refresh(job)
    
    logger.debug(f"Enqueued job (commit={commit}): type={job_type}, priority={priority}, user_id={user_id}")
    return job


def reserve_job(
    session: Session,
    worker_name: str,
    job_types: Optional[Sequence[str]] = None,
) -> Optional[Job]:
    """
    Reserve the next available job for processing.

    Picks the highest-priority, oldest job that is queued, under its attempt
    limit and not scheduled for later, then claims it with a conditional
    UPDATE so that concurrent workers can't both take it. If the claim loses
    the race (0 rows updated) the next candidate is tried, up to a few times.

    Args:
        session: SQLAlchemy session
        worker_name: Worker identifier (e.g., "worker-download-0")
        job_types: If given, only jobs of these types are considered. This is
            how a worker gets scoped to a task family (downloads vs metadata)
            -- see WORKER_JOB_TYPES in jobs/worker.py.

    Returns:
        Reserved Job instance, or None if no jobs available
    """
    now = now_utc()

    conditions = [
        Job.status == "queued",
        Job.attempts < Job.max_attempts,
        (Job.scheduled_at == None) | (Job.scheduled_at <= now),
    ]
    if job_types:
        conditions.append(Job.type.in_(list(job_types)))

    # A lost race means another worker took the row between our SELECT and
    # our UPDATE; there's usually a next candidate right behind it.
    for _ in range(RESERVE_MAX_RACES):
        stmt = (
            select(Job.id, Job.attempts)
            .where(and_(*conditions))
            .order_by(Job.priority.desc(), Job.created_at.asc())
            .limit(1)
        )
        row = session.execute(stmt).first()
        if not row:
            return None
        job_id, seen_attempts = row

        try:
            claimed = session.execute(
                update(Job)
                .where(
                    Job.id == job_id,
                    Job.status == "queued",
                    Job.attempts == seen_attempts,
                )
                .values(
                    status="reserved",
                    attempts=(seen_attempts or 0) + 1,
                    reserved_by=worker_name,
                    started_at=now,
                    heartbeat_at=now,
                )
            ).rowcount
            session.commit()
        except Exception as e:
            logger.exception(f"Failed to reserve job {job_id}: {e}")
            session.rollback()
            return None

        if claimed != 1:
            logger.debug(f"Lost race for job {job_id} to another worker, retrying")
            continue

        job = session.get(Job, job_id)
        if job is None:  # cancelled/deleted under us; vanishingly rare
            continue
        session.refresh(job)
        logger.debug(
            f"Reserved job {job.id}: type={job.type}, "
            f"attempt={job.attempts}/{job.max_attempts}, "
            f"worker={worker_name}"
        )
        return job

    return None


def heartbeat_job(session: Session, job_id: int, worker_name: str) -> bool:
    """
    Refresh heartbeat_at on a job this worker is still running. Commits.

    Returns False if the job is no longer reserved by this worker (it was
    cancelled, or reclaimed because this heartbeat arrived too late) --
    the worker can't do much about that mid-task, but it gets logged.
    """
    updated = session.execute(
        update(Job)
        .where(Job.id == job_id, Job.status == "reserved", Job.reserved_by == worker_name)
        .values(heartbeat_at=now_utc())
    ).rowcount
    session.commit()
    return updated == 1


def reclaim_orphaned_jobs(
    session: Session,
    worker_name: str,
    stale_after_seconds: int = STALE_HEARTBEAT_SECONDS,
) -> int:
    """
    Requeue "reserved" jobs whose worker is gone.

    Two cases, both requeued (or failed, if the dead worker's attempt was
    the job's last):
      - jobs reserved under *this* worker's name: this process is the only
        one that should hold them, and it just started, so a previous
        incarnation died mid-job (container restart, crash, update);
      - jobs whose heartbeat is older than stale_after_seconds, whoever
        holds them: that worker stopped heartbeating (see Worker in
        jobs/worker.py), so it's dead or wedged.

    Jobs currently held by *other* live workers are left alone -- with
    several worker processes running, "reserved" no longer means orphaned.

    Args:
        session: SQLAlchemy session
        worker_name: This worker's identifier
        stale_after_seconds: Heartbeat age beyond which a job counts as
            abandoned. Must comfortably exceed the worker's heartbeat
            interval.

    Returns:
        Number of jobs reclaimed
    """
    now = now_utc()
    cutoff = now - timedelta(seconds=stale_after_seconds)
    stmt = select(Job).where(
        Job.status == "reserved",
        or_(
            Job.reserved_by == worker_name,
            Job.heartbeat_at < cutoff,
            # Reserved before heartbeats existed / never heartbeated at all
            and_(Job.heartbeat_at == None, Job.started_at < cutoff),
        ),
    )
    orphaned = session.execute(stmt).scalars().all()

    if not orphaned:
        return 0

    failed = 0
    for job in orphaned:
        previous = job.reserved_by
        reason = (
            f"Reclaimed by {worker_name}: orphaned by {previous or 'unknown worker'}, "
            f"which never finished it"
        )
        job.reserved_by = None
        job.heartbeat_at = None

        # reserve_job already counted the dead worker's attempt. Requeueing a
        # job that used its last one would leave it "queued" but never
        # reservable: a zombie that blocks every "already queued?" check.
        if (job.attempts or 0) >= (job.max_attempts or 1):
            job.status = "failed"
            job.finished_at = now
            job.last_error = f"{reason} (out of attempts)"
            session.add(job)
            set_download_track_status(session, job, "failed", error=job.last_error)
            failed += 1
            continue

        job.status = "queued"
        job.started_at = None
        job.last_error = reason
        session.add(job)

        # The dead worker had already flipped its track to "downloading";
        # without this it would sit there looking in-progress until the
        # retry, which may be a while.
        set_download_track_status(session, job, "queued")

    session.commit()

    logger.warning(
        f"Reclaimed {len(orphaned)} orphaned job(s) left 'reserved' by a dead worker: "
        f"requeued {len(orphaned) - failed}, failed {failed} out of attempts"
    )
    return len(orphaned)


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
    refund_attempt: bool = False,
    worker_name: Optional[str] = None,
) -> None:
    """
    Mark job as failed. Optionally retry with exponential backoff.
    
    If retry_delay_seconds is provided and attempts < max_attempts:
    - Requeues job with scheduled_at = now + delay
    - Status set back to "queued"
    
    Otherwise:
    - Status set to "failed"
    - No further retries

    A download_track job's track follows: "queued" when retried, "failed"
    once out of attempts.
    
    Args:
        session: SQLAlchemy session
        job_id: Job ID
        error_message: Error description
        retry_delay_seconds: Optional retry delay in seconds
        refund_attempt: The failure wasn't the job's fault (YouTube rate
            limit): don't count this attempt against max_attempts
        worker_name: The worker reporting the failure. When given, the
            outcome is ignored unless that worker still holds the job.
    """
    job = session.get(Job, job_id)
    if not job:
        logger.warning(f"Cannot mark job {job_id} as failed: not found")
        return

    # Cancelled or reclaimed while this attempt ran: its outcome no longer
    # decides anything, and requeueing here would undo a cancellation.
    if job.status != "reserved" or (worker_name and job.reserved_by != worker_name):
        logger.info(
            f"Ignoring failure of job {job_id} reported by {worker_name or 'caller'}: "
            f"job is now {job.status} (held by {job.reserved_by or 'nobody'})"
        )
        if job.status == "cancelled":
            set_download_track_status(session, job, "available", only_from=("queued", "downloading"))
            session.commit()
        return
    
    now = now_utc()
    job.last_error = str(error_message) if error_message else None

    if refund_attempt and job.attempts:
        job.attempts -= 1
    
    # Check if we should retry
    if retry_delay_seconds and (job.attempts or 0) < (job.max_attempts or 1):
        # Requeue with backoff
        job.status = "queued"
        job.priority = job.priority - job.attempts
        job.scheduled_at = now + timedelta(seconds=retry_delay_seconds)
        job.reserved_by = None  # Clear reservation
        job.heartbeat_at = None
        session.add(job)
        set_download_track_status(session, job, "queued")
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
        set_download_track_status(session, job, "failed", error=error_message)
        session.commit()
        
        logger.error(
            f"Job {job_id} permanently failed after {job.attempts} attempts: "
            f"{error_message}"
        )


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
    # A download already running is left to finish: its worker then lands
    # the file, or hands the track back via mark_job_failed's cancelled path.
    set_download_track_status(session, job, "available", only_from=("queued",))
    session.commit()
    
    logger.info(f"Cancelled job {job_id}: {reason}")
    return True


def cancel_download_jobs(session: Session, track_ids: Collection[str], reason: str) -> int:
    """
    Cancel every queued or running download_track job for these tracks.
    Does not commit, and leaves the tracks' status to the caller.

    A worker already downloading one of them carries on; when it finishes
    the file lands as usual, and a failure is discarded (see mark_job_failed).

    Returns the number of jobs cancelled.
    """
    wanted = {str(t) for t in track_ids}
    if not wanted:
        return 0

    jobs = session.execute(
        select(Job).where(Job.type == "download_track", Job.status.in_(("queued", "reserved")))
    ).scalars().all()

    now = now_utc()
    cancelled = 0
    for job in jobs:
        payload = job.payload if isinstance(job.payload, dict) else {}
        if str(payload.get("track_id")) not in wanted:
            continue
        job.status = "cancelled"
        job.finished_at = now
        job.last_error = f"Cancelled: {reason}"
        session.add(job)
        cancelled += 1

    if cancelled:
        logger.info(f"Cancelled {cancelled} download job(s): {reason}")
    return cancelled


def set_download_track_status(
    session: Session,
    job: Job,
    status: str,
    only_from: Optional[Collection[str]] = None,
    error: Optional[str] = None,
) -> None:
    """
    Mirror a download_track job's state onto its track and roll the album
    up. No-op for other job types and for tracks already on disk. Does not
    commit: call it in the transaction that changes the job.

    Args:
        only_from: Only change tracks currently in one of these statuses
        error: Recorded on the track when failing it, if the download
            didn't already leave a more specific one
    """
    if job.type != "download_track":
        return
    track_id = job.payload.get("track_id") if isinstance(job.payload, dict) else None
    track = session.get(Track, str(track_id)) if track_id else None
    if not track or track.status == "done":
        return
    if only_from is not None and track.status not in only_from:
        return

    track.status = status
    if status == "failed" and error and not track.last_error:
        from ..services.tracks import truncate_error
        track.last_error = truncate_error(error)
    elif status == "available":
        track.last_error = None
    session.add(track)

    if track.album_id:
        from ..services import subscriptions as subs_svc
        session.flush()  # autoflush=False: the rollup has to see the new status
        subs_svc.check_and_update_album_download_status(session, track.album_id)


def cleanup_old_jobs(
    session: Session,
    days_old: int = 7,
) -> int:
    """
    Delete old finished jobs (done, failed, cancelled) to prevent database bloat.

    Args:
        session: SQLAlchemy session
        days_old: Delete jobs finished more than this many days ago (default 7)

    Returns:
        Number of jobs deleted
    """
    cutoff = now_utc() - timedelta(days=days_old)

    query = session.query(Job).filter(
        Job.finished_at != None,
        Job.finished_at < cutoff,
        Job.status.in_(["done", "failed", "cancelled"]),
    )

    jobs_to_delete = query.all()
    count = len(jobs_to_delete)
    
    for job in jobs_to_delete:
        session.delete(job)
    
    session.commit()
    
    logger.info(f"Cleaned up {count} old jobs (older than {days_old} days)")
    return count