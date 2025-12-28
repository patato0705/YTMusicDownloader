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
import threading
import time
from typing import Optional

from sqlalchemy.orm import Session

from .db import SessionLocal
from .jobs.jobqueue import enqueue_job, cleanup_old_jobs
from .services import subscriptions as subs_svc, auth as auth_svc
from . import settings as settings_module

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
        token_cleanup_interval_seconds: Optional[int] = None,
        thread_name: str = "scheduler-thread",
        settings_refresh_interval: int = 300  # Refresh settings every 5 minutes
    ) -> None:
        # Store initial intervals (will be refreshed from DB once it's ready)
        self.sync_interval_seconds: int = sync_interval_seconds or 21600  # 6 hours default
        self.cleanup_interval_seconds: int = cleanup_interval_seconds or 86400  # 24 hours default
        self.token_cleanup_interval_seconds: int = token_cleanup_interval_seconds or 86400  # 24 hours default
        self.settings_refresh_interval: int = settings_refresh_interval
        
        self._thread_name = thread_name
        self._thread: Optional[threading.Thread] = None
        self._stopped = threading.Event()
        self._running_lock = threading.Lock()
        self._last_sync = 0.0
        self._last_cleanup = 0.0
        self._last_token_cleanup = 0.0
        self._last_settings_refresh = 0.0
        
        # Don't load settings here - database might not be ready yet
        # Settings will be loaded in _run_loop after wait_for_db()

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

    def _refresh_settings_from_db(self) -> None:
        """
        Load scheduler settings from database.
        Called periodically to allow runtime configuration changes.
        """
        session: Optional[Session] = None
        try:
            session = SessionLocal()
            
            # Get sync interval from settings (in hours, convert to seconds)
            sync_hours = settings_module.get_setting(
                session, 
                "scheduler.sync_interval_hours", 
                default=6
            )
            self.sync_interval_seconds = int(sync_hours) * 3600
            
            # Get cleanup interval from settings (in days, convert to seconds)
            cleanup_days = settings_module.get_setting(
                session,
                "scheduler.job_cleanup_days",
                default=3
            )
            self.cleanup_interval_seconds = int(cleanup_days) * 86400
            
            # Get token cleanup interval from settings (in days, convert to seconds)
            token_cleanup_days = settings_module.get_setting(
                session,
                "scheduler.token_cleanup_days",
                default=1
            )
            self.token_cleanup_interval_seconds = int(token_cleanup_days) * 86400
            
            logger.debug(
                f"Settings refreshed: sync_interval={self.sync_interval_seconds}s, "
                f"cleanup_interval={self.cleanup_interval_seconds}s, "
                f"token_cleanup_interval={self.token_cleanup_interval_seconds}s"
            )
            
        except Exception as e:
            # Check if this is a "table doesn't exist" error
            error_msg = str(e).lower()
            if "no such table" in error_msg or "doesn't exist" in error_msg:
                logger.debug("Settings table not yet created, using default values")
            else:
                logger.warning(f"Failed to refresh settings from database: {e}")
                logger.debug("Using current/default values")
        finally:
            if session:
                try:
                    session.close()
                except Exception:
                    pass

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
        
        # Load settings from database now that it's ready
        try:
            self._refresh_settings_from_db()
            self._last_settings_refresh = time.time()
            logger.info(
                "Scheduler settings loaded (sync_interval=%ss, cleanup_interval=%ss, token_cleanup_interval=%ss)",
                self.sync_interval_seconds,
                self.cleanup_interval_seconds,
                self.token_cleanup_interval_seconds
            )
        except Exception:
            logger.exception("Failed to load initial settings from database, using defaults")
        
        try:
            time.sleep(0.1)
        except Exception:
            pass

        while not self._stopped.is_set():
            now = time.time()
            
            # Check if settings refresh is due
            if now - self._last_settings_refresh >= self.settings_refresh_interval:
                try:
                    self._refresh_settings_from_db()
                    self._last_settings_refresh = now
                except Exception:
                    logger.exception("Unexpected error in _refresh_settings_from_db")
            
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
            
            # Get sync interval from settings (in hours)
            sync_interval_hours = settings_module.get_setting(
                session,
                "scheduler.sync_interval_hours",
                default=6
            )
            
            # Get artists that need syncing (followed=True and last_synced_at is old)
            try:
                artists = subs_svc.get_monitored_artists_needing_sync(
                    session=session,
                    sync_interval_hours=int(sync_interval_hours)
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
            
            # Get cleanup days from settings
            days_old = settings_module.get_setting(
                session,
                "scheduler.job_cleanup_days",
                default=7
            )
            
            # Delete jobs older than specified days
            deleted = cleanup_old_jobs(
                session=session,
                days_old=int(days_old),
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