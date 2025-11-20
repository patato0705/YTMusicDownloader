from __future__ import annotations
import logging
import os
import signal
import time
import traceback
from typing import Optional

from sqlalchemy.orm import Session

from ..db import SessionLocal
from .jobqueue import reserve_job, mark_job_done, mark_job_failed
from .tasks import run_job_task
from ..logging_config import configure_logging
from ..time_utils import now_utc

logger = logging.getLogger("jobs.worker")


class Worker:
    """
    Simple DB-backed worker process.

    Behaviour:
      - Reserve jobs using jobqueue.reserve_job(session, worker_name)
      - Dispatch to tasks.run_job_task(session, job)
      - Mark job done or failed using jobqueue helpers
      - Graceful shutdown on SIGINT / SIGTERM

    Configuration (via env):
      WORKER_NAME           : name used when reserving jobs (default "worker-<pid>")
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
    ) -> None:
        self.worker_name = worker_name or f"worker-{os.getpid()}"
        self.poll_interval = float(poll_interval)
        self.idle_sleep = float(idle_sleep)
        self.max_jobs = int(max_jobs) if max_jobs is not None else None
        self._stopped = False
        self._processed = 0

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

    def run(self) -> None:
        """
        Main loop. Never returns until stopped or max_jobs reached.
        """
        logger.info("Starting worker %s (poll_interval=%s)", self.worker_name, self.poll_interval)

        while not self._stopped:
            # stop if max_jobs reached
            if self.max_jobs is not None and self._processed >= self.max_jobs:
                logger.info("Worker %s reached max_jobs=%s — exiting", self.worker_name, self.max_jobs)
                break

            session: Optional[Session] = None
            try:
                session = SessionLocal()
                job = reserve_job(session, self.worker_name)
                if not job:
                    # no job available
                    session.close()
                    time.sleep(self.poll_interval)
                    continue

                logger.info("Worker %s reserved job id=%s type=%s attempts=%s",
                            self.worker_name, getattr(job, "id", None), getattr(job, "type", None), getattr(job, "attempts", None))

                # execute task
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

        logger.info("Worker %s stopping (processed=%s)", self.worker_name, self._processed)


def _env_get(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.environ.get(name)
    return v if v is not None else default


def main() -> None:
    configure_logging()  # basic logging; caller can configure differently before import if needed
    worker_name = _env_get("WORKER_NAME") or f"worker-{os.getpid()}"
    poll_interval = float(_env_get("WORKER_POLL_INTERVAL") or 2.0)
    idle_sleep = float(_env_get("WORKER_IDLE_SLEEP_SEC") or 3.0)
    max_jobs_env = _env_get("WORKER_MAX_JOBS")
    max_jobs = int(max_jobs_env) if max_jobs_env is not None else None

    w = Worker(worker_name=worker_name, poll_interval=poll_interval, idle_sleep=idle_sleep, max_jobs=max_jobs)
    w.run()


if __name__ == "__main__":
    main()