from __future__ import annotations
import logging
import os
import re
import signal
import threading
import time
import traceback
from typing import Optional, Sequence

from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..deps import wait_for_db
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

        # install signal handlers
        signal.signal(signal.SIGINT, self._handle_signal)
        try:
            signal.signal(signal.SIGTERM, self._handle_signal)
        except Exception:
            # some platforms may not allow SIGTERM (Windows) — ignore
            pass

    def _handle_signal(self, signum, frame) -> None:
        logger.info("Worker %s received signal %s — shutting down gracefully", self.worker_name, signum)
        self._stopped = True

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
            session = SessionLocal()
            try:
                reclaim_orphaned_jobs(session, self.worker_name)
            finally:
                session.close()
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
            # stop if max_jobs reached
            if self.max_jobs is not None and self._processed >= self.max_jobs:
                logger.info("Worker %s reached max_jobs=%s — exiting", self.worker_name, self.max_jobs)
                break

            session: Optional[Session] = None
            try:
                session = SessionLocal()
                types = self._reservable_types(session)
                job = reserve_job(session, self.worker_name, job_types=types) if types != [] else None
                if not job:
                    # no job available
                    session.close()
                    time.sleep(self.poll_interval)
                    continue

                logger.info("Worker %s reserved job id=%s type=%s attempts=%s",
                            self.worker_name, getattr(job, "id", None), getattr(job, "type", None), getattr(job, "attempts", None))

                # execute task
                self._set_current_job(getattr(job, "id", None))
                try:
                    result = run_job_task(session, job)
                    # result expected to be a dict with ok: bool
                    if isinstance(result, dict) and result.get("ok", False):
                        # mark done
                        try:
                            mark_job_done(session, getattr(job, "id"))
                            logger.info("Job id=%s marked done", getattr(job, "id"))
                        except Exception:
                            # if marking done fails, log and continue
                            logger.exception("Failed to mark job done id=%s", getattr(job, "id"))
                    else:
                        # mark failed — allow task to suggest retry_delay_seconds
                        err = None
                        retry_delay = None
                        if isinstance(result, dict):
                            err = result.get("error") or result.get("message")
                            retry_delay = result.get("retry_delay_seconds") or result.get("retry_after")
                        err_msg = str(err) if err is not None else "task returned ok=False"
                        try:
                            mark_job_failed(session, getattr(job, "id"), error_message=err_msg, retry_delay_seconds=retry_delay)
                            logger.warning("Job id=%s marked failed (retry_delay=%s) error=%s", getattr(job, "id"), retry_delay, err_msg)
                        except Exception:
                            logger.exception("Failed to mark job failed id=%s", getattr(job, "id"))
                except Exception as e:
                    # Unhandled exception while running task -> mark failed with no retry_delay by default
                    trace = traceback.format_exc()
                    logger.exception("Unhandled exception executing job id=%s: %s", getattr(job, "id", None), e)
                    try:
                        mark_job_failed(session, getattr(job, "id"), error_message=str(e))
                        logger.info("Marked job id=%s failed after exception", getattr(job, "id", None))
                    except Exception:
                        logger.exception("Failed to mark job failed after exception id=%s", getattr(job, "id", None))
                finally:
                    self._set_current_job(None)
                    # close session for this iteration (jobqueue functions commit)
                    try:
                        session.close()
                    except Exception:
                        pass

                self._processed += 1

            except Exception as outer_ex:
                # catch any unexpected errors in the loop
                logger.exception("Worker loop error: %s", outer_ex)
                # ensure session closed
                try:
                    if session:
                        session.close()
                except Exception:
                    pass
                time.sleep(self.idle_sleep)


def _env_get(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.environ.get(name)
    return v if v is not None else default


def main() -> None:
    worker_name = _env_get("WORKER_NAME") or f"worker-{os.getpid()}"
    configure_logging(process_name=worker_name)

    # Wait for database to be ready
    wait_for_db()

    poll_interval = float(_env_get("WORKER_POLL_INTERVAL") or 2.0)
    idle_sleep = float(_env_get("WORKER_IDLE_SLEEP_SEC") or 3.0)
    max_jobs_env = _env_get("WORKER_MAX_JOBS")
    max_jobs = int(max_jobs_env) if max_jobs_env is not None else None
    job_types_env = _env_get("WORKER_JOB_TYPES") or ""
    job_types = [t.strip() for t in job_types_env.split(",") if t.strip()] or None

    w = Worker(
        worker_name=worker_name,
        poll_interval=poll_interval,
        idle_sleep=idle_sleep,
        max_jobs=max_jobs,
        job_types=job_types,
    )
    w.run()


if __name__ == "__main__":
    main()