# backend/jobs/worker.py
from __future__ import annotations
import logging
import os
import re
import select
import signal
import socket
import threading
from typing import Optional, Sequence

from sqlalchemy.orm import Session

from ..db import SessionLocal, wait_for_db
from .jobqueue import reserve_job, heartbeat_job, mark_job_done, mark_job_failed, reclaim_orphaned_jobs
from .tasks import run_job_task, ALL_JOB_TYPES
from . import gate
from ..logging_config import configure_logging

logger = logging.getLogger("jobs.worker")

# Must be well under jobqueue.STALE_HEARTBEAT_SECONDS, or a healthy worker's
# job gets reclaimed out from under it.
HEARTBEAT_INTERVAL_SECONDS = 30


class Worker:
    """
    Simple DB-backed worker process.

    Several of these run side by side (deploy/supervisord.conf), each scoped
    to a family of job types so that a long download never holds up
    metadata imports, and vice versa. Download workers are the only ones
    that talk to YouTube for media, so how many of them are *active* is
    what bounds the rate-limit exposure: that's decided per poll by
    jobs.gate (the download.max_concurrent setting and the rate-limit
    pause), not by how many processes supervisord started.

    Behaviour:
      - Reserve jobs using jobqueue.reserve_job(session, worker_name, job_types)
      - Heartbeat the reserved job from a background thread while it runs,
        so a job left "reserved" by a dead worker can be told apart from one
        another worker is busy with (jobqueue.reclaim_orphaned_jobs)
      - Dispatch to tasks.run_job_task(session, job)
      - Mark job done or failed using jobqueue helpers
      - Graceful shutdown on SIGINT / SIGTERM

    Configuration (via env):
      WORKER_NAME           : name used when reserving jobs (default "worker-<pid>").
                              Must be stable across restarts: it's how a
                              restarted worker finds the job its previous
                              incarnation died holding. A trailing "-<n>"
                              is the worker's index for the download gate
                              (worker-download-2 is the 3rd download slot);
                              no suffix means index 0, i.e. always active.
      WORKER_JOB_TYPES      : comma-separated job types this worker handles
                              (default: all types)
      WORKER_POLL_INTERVAL  : seconds to sleep when no job found (default 2)
      WORKER_IDLE_SLEEP_SEC : seconds to sleep after an unexpected error (default 3)
      WORKER_MAX_JOBS       : optional int, stop after processing this many jobs (default: unlimited)
    """

    def __init__(
        self,
        worker_name: Optional[str] = None,
        poll_interval: float = 2.0,
        idle_sleep: float = 3.0,
        max_jobs: Optional[int] = None,
        job_types: Optional[Sequence[str]] = None,
    ) -> None:
        self.worker_name = worker_name or f"worker-{os.getpid()}"
        self.poll_interval = float(poll_interval)
        self.idle_sleep = float(idle_sleep)
        self.max_jobs = int(max_jobs) if max_jobs is not None else None
        self.job_types = list(job_types) if job_types else None
        self._stopped = False
        self._processed = 0

        m = re.search(r"-(\d+)$", self.worker_name)
        self.worker_index = int(m.group(1)) if m else 0
        self._gate_reason: Optional[str] = None  # last logged gate state, to log changes once

        # Job currently being executed, heartbeated by _heartbeat_loop
        self._current_job_id: Optional[int] = None
        self._current_job_lock = threading.Lock()
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: Optional[threading.Thread] = None

        # Written to by _handle_signal to cut _sleep short. A socket pair
        # rather than os.pipe(): select() only takes sockets on Windows.
        self._wake_r, self._wake_w = socket.socketpair()
        self._wake_w.setblocking(False)

        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, signum, frame) -> None:
        logger.info("Worker %s received signal %s, shutting down gracefully", self.worker_name, signum)
        self._stopped = True
        try:
            self._wake_w.send(b"\0")
        except OSError:
            pass  # buffer full: a wake-up byte is already waiting

    # -- heartbeat -----------------------------------------------------------

    def _set_current_job(self, job_id: Optional[int]) -> None:
        with self._current_job_lock:
            self._current_job_id = job_id

    def _heartbeat_loop(self) -> None:
        """
        Runs in a daemon thread. The main thread is blocked inside yt-dlp /
        ytmusicapi for most of a job's life, so it can't heartbeat itself.
        Uses its own short-lived session each beat; never touches the main
        thread's session.
        """
        while not self._heartbeat_stop.wait(HEARTBEAT_INTERVAL_SECONDS):
            with self._current_job_lock:
                job_id = self._current_job_id
            if job_id is None:
                continue
            try:
                with SessionLocal() as session:
                    if not heartbeat_job(session, job_id, self.worker_name):
                        logger.warning(
                            "Job id=%s is no longer reserved by %s (cancelled or reclaimed); "
                            "its result will be ignored",
                            job_id, self.worker_name,
                        )
            except Exception:
                logger.exception("Heartbeat failed for job id=%s", job_id)

    def _start_heartbeat(self) -> None:
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, name=f"{self.worker_name}-heartbeat", daemon=True
        )
        self._heartbeat_thread.start()

    def _stop_heartbeat(self) -> None:
        self._heartbeat_stop.set()
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=5)

    # -- download gate -------------------------------------------------------

    def _reservable_types(self, session: Session) -> Optional[Sequence[str]]:
        """
        Job types to reserve on this poll: the worker's scope, minus
        download_track while the gate says this worker shouldn't download
        (paused after a rate limit, or above download.max_concurrent).
        None means "any type"; [] means "nothing right now".
        """
        scope = self.job_types if self.job_types is not None else list(ALL_JOB_TYPES)
        if gate.DOWNLOAD_JOB_TYPE not in scope:
            return self.job_types

        try:
            allowed, reason = gate.worker_may_download(session, self.worker_index)
        except Exception:
            logger.exception("Download gate check failed; assuming allowed")
            allowed, reason = True, ""

        if allowed:
            if self._gate_reason is not None:
                logger.info("Worker %s resuming downloads", self.worker_name)
                self._gate_reason = None
            return self.job_types

        if reason != self._gate_reason:
            logger.info("Worker %s not taking download jobs: %s", self.worker_name, reason)
            self._gate_reason = reason
        return [t for t in scope if t != gate.DOWNLOAD_JOB_TYPE]

    # -- main loop -----------------------------------------------------------

    def run(self) -> None:
        """
        Main loop. Never returns until stopped or max_jobs reached.
        """
        logger.info(
            "Starting worker %s (poll_interval=%s, job_types=%s)",
            self.worker_name, self.poll_interval, ",".join(self.job_types) if self.job_types else "all",
        )

        try:
            with SessionLocal() as session:
                reclaim_orphaned_jobs(session, self.worker_name)
        except Exception:
            logger.exception("Failed to reclaim orphaned jobs on startup")

        self._start_heartbeat()
        try:
            self._loop()
        finally:
            self._stop_heartbeat()

        logger.info("Worker %s stopping (processed=%s)", self.worker_name, self._processed)

    def _loop(self) -> None:
        while not self._stopped:
            if self.max_jobs is not None and self._processed >= self.max_jobs:
                logger.info("Worker %s reached max_jobs=%s, exiting", self.worker_name, self.max_jobs)
                break
            try:
                with SessionLocal() as session:
                    types = self._reservable_types(session)
                    job = reserve_job(session, self.worker_name, job_types=types) if types != [] else None
                    if job is None:
                        processed = False
                    else:
                        self._run(session, job)
                        processed = True
            except Exception:
                logger.exception("Worker loop error")
                self._sleep(self.idle_sleep)
                continue
            if processed:
                self._processed += 1
            else:
                self._sleep(self.poll_interval)

    def _sleep(self, seconds: float) -> None:
        """
        Sleep, but return as soon as a stop signal arrives. A plain
        time.sleep() resumes after the signal handler runs, so every idle
        worker would sit out its whole poll interval, eating into Docker's
        stop timeout. The handler writes to _wake_w instead, which ends the
        select() -- or makes it return at once if the signal came first.
        """
        if not self._stopped:
            select.select([self._wake_r], [], [], seconds)

    def _run(self, session: Session, job) -> None:
        """Run one reserved job and record its outcome."""
        # Read once: after a task fails mid-transaction the job's
        # attributes can't be loaded again until a rollback.
        job_id = job.id
        logger.info("Worker %s reserved job id=%s type=%s attempts=%s",
                    self.worker_name, job_id, job.type, job.attempts)
        self._set_current_job(job_id)
        try:
            # Never raises: task errors come back as {"ok": False, ...}
            result = run_job_task(session, job)
            _discard_failed_transaction(session)
            if result.get("ok"):
                mark_job_done(session, job_id)
            else:
                # The task may ask for a retry later and for the attempt not
                # to count (a rate limit says nothing about the job)
                mark_job_failed(
                    session,
                    job_id,
                    error_message=str(result.get("error") or "task returned ok=False"),
                    retry_delay_seconds=result.get("retry_delay_seconds"),
                    refund_attempt=bool(result.get("refund_attempt")),
                    worker_name=self.worker_name,
                )
        except Exception:
            # The bookkeeping itself failed: the job stays "reserved" and,
            # no longer heartbeated, is reclaimed by the stale-job sweep
            logger.exception("Failed to record the outcome of job id=%s", job_id)
        finally:
            self._set_current_job(None)


def _discard_failed_transaction(session: Session) -> None:
    """
    Roll back a transaction a task left failed (an error during flush that
    the task caught without rolling back). Until then every use of the
    session raises, so marking the job done/failed would fail and leave it
    "reserved" until the orphan sweep. A healthy session is left alone: the
    job bookkeeping commits whatever the task still has pending, as before.
    """
    if not session.is_active:
        try:
            session.rollback()
        except Exception:
            logger.exception("Rollback of a failed task transaction failed")


def main() -> None:
    worker_name = os.environ.get("WORKER_NAME") or f"worker-{os.getpid()}"
    configure_logging(process_name=worker_name)
    wait_for_db()

    max_jobs = os.environ.get("WORKER_MAX_JOBS")
    job_types = [t.strip() for t in os.environ.get("WORKER_JOB_TYPES", "").split(",") if t.strip()]
    Worker(
        worker_name=worker_name,
        poll_interval=float(os.environ.get("WORKER_POLL_INTERVAL") or 2.0),
        idle_sleep=float(os.environ.get("WORKER_IDLE_SLEEP_SEC") or 3.0),
        max_jobs=int(max_jobs) if max_jobs else None,
        job_types=job_types or None,
    ).run()


if __name__ == "__main__":
    main()
