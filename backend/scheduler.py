# backend/scheduler.py
"""
Scheduler for periodic sync tasks.

Responsibilities:
1. Sync followed artists for new releases (daily)
2. Clean up old completed jobs (weekly)

Note: Album subscriptions are handled on-demand (follow album → immediate import)
"""
from __future__ import annotations
import logging
import os
import threading
import time
from typing import Optional

from sqlalchemy.orm import Session

from .db import SessionLocal
from .jobs.jobqueue import enqueue_job, cleanup_old_jobs
from .services import subscriptions as subs_svc, auth as auth_svc

logger = logging.getLogger("scheduler")


class Scheduler:
    """
    Simple threaded scheduler for periodic tasks.
    
    Tasks:
    - sync_monitored_artists: Check followed artists for new releases (every 6 hours)
    - cleanup_jobs: Remove old completed jobs (daily)
    """

    def __init__(
        self,
        sync_interval_seconds: Optional[int] = None,
        cleanup_interval_seconds: Optional[int] = None,
        token_cleanup_interval_seconds: Optional[int] = None,  # NEW
        thread_name: str = "scheduler-thread"
    ) -> None:
        # Artist sync interval (default 6 hours)
        if sync_interval_seconds is None:
            try:
                sync_interval_seconds = int(os.environ.get("SCHED_SYNC_INTERVAL", "21600"))
            except Exception:
                sync_interval_seconds = 21600
        
        # Cleanup interval (default 24 hours)
        if cleanup_interval_seconds is None:
            try:
                cleanup_interval_seconds = int(os.environ.get("SCHED_CLEANUP_INTERVAL", "86400"))
            except Exception:
                cleanup_interval_seconds = 86400
        
        # Token cleanup interval (default 24 hours)
        if token_cleanup_interval_seconds is None:
            try:
                token_cleanup_interval_seconds = int(os.environ.get("SCHED_TOKEN_CLEANUP_INTERVAL", "86400"))
            except Exception:
                token_cleanup_interval_seconds = 86400
        
        self.sync_interval_seconds: int = int(sync_interval_seconds)
        self.cleanup_interval_seconds: int = int(cleanup_interval_seconds)
        self.token_cleanup_interval_seconds: int = int(token_cleanup_interval_seconds)
        self._thread_name = thread_name
        self._thread: Optional[threading.Thread] = None
        self._stopped = threading.Event()
        self._running_lock = threading.Lock()
        self._last_sync = 0.0
        self._last_cleanup = 0.0
        self._last_token_cleanup = 0.0

    def start(self) -> None:
        """Start the scheduler thread. Safe to call multiple times (idempotent)."""
        with self._running_lock:
            if self._thread is not None and self._thread.is_alive():
                logger.debug("Scheduler already running")
                return
            self._stopped.clear()
            self._thread = threading.Thread(target=self._run_loop, name=self._thread_name, daemon=True)
            self._thread.start()
            logger.info(
                "Scheduler started (sync_interval=%ss, cleanup_interval=%ss)",
                self.sync_interval_seconds,
                self.cleanup_interval_seconds
            )

    def stop(self, join_timeout: float = 5.0) -> None:
        """Signal the scheduler to stop and wait for thread to end."""
        self._stopped.set()
        th = self._thread
        if th is not None and th.is_alive():
            logger.info("Stopping scheduler...")
            th.join(timeout=join_timeout)
            if th.is_alive():
                logger.warning("Scheduler thread did not exit within timeout")
            else:
                logger.info("Scheduler stopped")
        else:
            logger.debug("Scheduler not running")
        self._thread = None

    def _run_loop(self) -> None:
        """Internal loop running until _stopped is set."""
        from .deps import wait_for_db
        try:
            wait_for_db()
        except Exception:
            logger.exception("Database failed to become ready, scheduler exiting")
            return
        
        try:
            time.sleep(0.1)
        except Exception:
            pass

        while not self._stopped.is_set():
            now = time.time()
            
            # Check if artist sync is due
            if now - self._last_sync >= self.sync_interval_seconds:
                try:
                    self.sync_monitored_artists()
                    self._last_sync = now
                except Exception:
                    logger.exception("Unexpected error in sync_monitored_artists")
            
            # Check if job cleanup is due
            if now - self._last_cleanup >= self.cleanup_interval_seconds:
                try:
                    self.cleanup_old_jobs()
                    self._last_cleanup = now
                except Exception:
                    logger.exception("Unexpected error in cleanup_old_jobs")
            
            # Check if token cleanup is due
            if now - self._last_token_cleanup >= self.token_cleanup_interval_seconds:
                try:
                    self.cleanup_expired_tokens()
                    self._last_token_cleanup = now
                except Exception:
                    logger.exception("Unexpected error in cleanup_expired_tokens")
            
            # Sleep for a short interval (check every minute)
            self._stopped.wait(timeout=60.0)

    def sync_monitored_artists(self) -> None:
        """
        Check for followed artists that need syncing and enqueue sync_artist jobs.
        Only syncs artists that haven't been synced in the last sync_interval_hours.
        """
        session: Optional[Session] = None
        try:
            session = SessionLocal()
            
            # Get artists that need syncing (followed=True and last_synced_at is old)
            sync_interval_hours = self.sync_interval_seconds // 3600
            try:
                artists = subs_svc.get_monitored_artists_needing_sync(
                    session=session,
                    sync_interval_hours=sync_interval_hours
                ) or []
            except Exception:
                logger.exception("Failed fetching monitored artists")
                return

            if not artists:
                logger.debug("No monitored artists need syncing")
                return

            logger.info(f"Found {len(artists)} monitored artist(s) needing sync")

            enqueued_count = 0
            for artist in artists:
                try:
                    artist_id = getattr(artist, "id", None)
                    if not artist_id:
                        continue

                    # Enqueue sync_artist job
                    payload = {"artist_id": str(artist_id)}  # ← Fixed: was "channel_id"
                    
                    try:
                        job = enqueue_job(
                            session=session,
                            job_type="sync_artist",
                            payload=payload,
                            priority=5,  # Higher priority for syncs
                        )
                        logger.info(f"Enqueued sync_artist job {job.id} for artist {artist_id}")
                        enqueued_count += 1
                    except Exception:
                        logger.exception(f"Failed to enqueue sync job for artist {artist_id}")
                        continue

                except Exception:
                    logger.exception(f"Error processing monitored artist {artist}")

            logger.info(f"Processed {len(artists)} monitored artists (enqueued {enqueued_count} jobs)")

        finally:
            if session:
                try:
                    session.close()
                except Exception:
                    pass

    def cleanup_old_jobs(self) -> None:
        """
        Clean up old completed jobs to prevent database bloat.
        Keeps failed jobs for debugging.
        """
        session: Optional[Session] = None
        try:
            session = SessionLocal()
            
            # Delete jobs older than 7 days
            deleted = cleanup_old_jobs(
                session=session,
                days_old=7,
                keep_failed=True,  # Keep failed jobs for debugging
            )
            
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} old completed jobs")
            else:
                logger.debug("No old jobs to clean up")
        
        except Exception:
            logger.exception("Failed to clean up old jobs")
        
        finally:
            if session:
                try:
                    session.close()
                except Exception:
                    pass
        
    def cleanup_expired_tokens(self) -> None:
        """
        Clean up expired refresh tokens.
        Runs daily to prevent database bloat.
        """
        session: Optional[Session] = None
        try:
            session = SessionLocal()
            
            deleted = auth_svc.cleanup_expired_tokens(session)
            
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} expired refresh tokens")
            else:
                logger.debug("No expired tokens to clean up")
        
        except Exception:
            logger.exception("Failed to clean up expired tokens")
        
        finally:
            if session:
                try:
                    session.close()
                except Exception:
                    pass


# Module-level default scheduler instance
_default_scheduler: Optional[Scheduler] = None


def get_default_scheduler() -> Scheduler:
    global _default_scheduler
    if _default_scheduler is None:
        _default_scheduler = Scheduler()
    return _default_scheduler


def start_default_scheduler() -> None:
    get_default_scheduler().start()


def stop_default_scheduler() -> None:
    global _default_scheduler
    if _default_scheduler is not None:
        _default_scheduler.stop()
        _default_scheduler = None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sched = Scheduler()
    try:
        sched.start()
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        sched.stop()