# backend/scheduler.py
"""
Scheduler for periodic sync tasks.

Responsibilities:
1. Sync followed artists for new releases (every `scheduler.sync_interval_hours`)
2. Re-sync followed charts (every `scheduler.chart_sync_interval_days`)
3. Clean up old finished jobs, failed ones included (daily, keeping
   `scheduler.job_cleanup_days`)
4. Clean up expired refresh tokens (daily)
5. Retry/upgrade missing lyrics (every `scheduler.lyrics_retry_interval_hours`)
6. Requeue jobs abandoned by a dead worker, fix up "queued"/"downloading"
   tracks that lost their job, and drop stale download scratch dirs
   (every 5 minutes)
7. Delete thumbnail proxy cache files older than THUMBNAIL_CACHE_TTL (daily)

Note: Album subscriptions are handled on-demand (follow album → immediate import)
"""
from __future__ import annotations
import logging
import threading
import time
from typing import Optional

from sqlalchemy.orm import Session

from .db import SessionLocal
from .jobs.jobqueue import enqueue_job, cleanup_old_jobs, reclaim_orphaned_jobs
from .services import subscriptions as subs_svc, auth as auth_svc, charts as charts_svc
from .routers import features
from . import settings as settings_module

logger = logging.getLogger("scheduler")


class Scheduler:
    """
    Simple threaded scheduler for periodic tasks.
    
    Tasks:
    - sync_monitored_artists: Check followed artists for new releases
    - sync_charts: Re-sync followed charts to follow new top-N entrants
    - cleanup_jobs: Remove old finished jobs (daily)
    """

    def __init__(
        self,
        sync_check_interval_seconds: Optional[int] = None,
        cleanup_interval_seconds: Optional[int] = None,
        token_cleanup_interval_seconds: Optional[int] = None,
        thread_name: str = "scheduler-thread",
        settings_refresh_interval: int = 300  # Refresh settings every 5 minutes
    ) -> None:
        # How often we *look* for artists that are due. The per-artist cadence is
        # `scheduler.sync_interval_hours`, applied as a cutoff on last_synced_at.
        # Looking more often than that keeps the real cadence close to the
        # setting: polling exactly every N hours would usually find the artist
        # synced a few seconds *after* the cutoff and skip it until 2N.
        self.sync_check_interval_seconds: int = sync_check_interval_seconds or 600  # 10 minutes
        self.sync_interval_hours: int = 6  # refreshed from DB
        # Same pattern for charts: `scheduler.chart_sync_interval_days` is a
        # cutoff on ChartSubscription.last_synced_at, checked on the artist cadence.
        self.chart_sync_interval_days: int = 7  # refreshed from DB
        # Fixed cadences (the settings only control retention / age):
        self.cleanup_interval_seconds: int = cleanup_interval_seconds or 86400  # 24 hours
        self.token_cleanup_interval_seconds: int = token_cleanup_interval_seconds or 86400  # 24 hours
        self.lyrics_retry_interval_seconds: int = 86400  # refreshed from DB
        self.stale_sweep_interval_seconds: int = 300
        self.thumbnail_cleanup_interval_seconds: int = 86400
        self.settings_refresh_interval: int = settings_refresh_interval

        self._thread_name = thread_name
        self._thread: Optional[threading.Thread] = None
        self._stopped = threading.Event()
        self._running_lock = threading.Lock()
        self._last_sync = 0.0
        self._last_cleanup = 0.0
        self._last_token_cleanup = 0.0
        self._last_lyrics_retry = 0.0
        self._last_stale_sweep = 0.0
        self._last_thumbnail_cleanup = 0.0
        self._last_settings_refresh = 0.0
        # Tracks the previous sweep found "queued" with no job (see
        # _requeue_orphaned_track_downloads)
        self._orphaned_track_ids: set[str] = set()
        
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
                "Scheduler started (sync_check_interval=%ss, cleanup_interval=%ss)",
                self.sync_check_interval_seconds,
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
            
            # Get sync interval from settings (in hours)
            sync_hours = settings_module.get_setting(
                session, 
                "scheduler.sync_interval_hours", 
                default=6
            )
            self.sync_interval_hours = max(1, int(sync_hours))

            chart_sync_days = settings_module.get_setting(
                session,
                "scheduler.chart_sync_interval_days",
                default=7
            )
            self.chart_sync_interval_days = max(1, int(chart_sync_days))

            # Get lyrics retry interval from settings (in hours, convert to seconds)
            lyrics_retry_hours = settings_module.get_setting(
                session,
                "scheduler.lyrics_retry_interval_hours",
                default=24
            )
            self.lyrics_retry_interval_seconds = max(1, int(lyrics_retry_hours)) * 3600

            logger.debug(
                f"Settings refreshed: sync_interval={self.sync_interval_hours}h, "
                f"chart_sync_interval={self.chart_sync_interval_days}d, "
                f"lyrics_retry_interval={self.lyrics_retry_interval_seconds}s"
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
                "Scheduler settings loaded (sync_interval=%sh, chart_sync_interval=%sd, lyrics_retry_interval=%ss)",
                self.sync_interval_hours,
                self.chart_sync_interval_days,
                self.lyrics_retry_interval_seconds
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
            
            # Check if any artist or chart sync is due
            if now - self._last_sync >= self.sync_check_interval_seconds:
                try:
                    self.sync_monitored_artists()
                except Exception:
                    logger.exception("Unexpected error in sync_monitored_artists")
                try:
                    self.sync_charts()
                except Exception:
                    logger.exception("Unexpected error in sync_charts")
                self._last_sync = now
            
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

            # Check if lyrics retry is due
            if now - self._last_lyrics_retry >= self.lyrics_retry_interval_seconds:
                try:
                    self.retry_missing_lyrics()
                    self._last_lyrics_retry = now
                except Exception:
                    logger.exception("Unexpected error in retry_missing_lyrics")

            if now - self._last_stale_sweep >= self.stale_sweep_interval_seconds:
                try:
                    self.sweep_stale_work()
                    self._last_stale_sweep = now
                except Exception:
                    logger.exception("Unexpected error in sweep_stale_work")

            if now - self._last_thumbnail_cleanup >= self.thumbnail_cleanup_interval_seconds:
                try:
                    self.cleanup_thumbnail_cache()
                    self._last_thumbnail_cleanup = now
                except Exception:
                    logger.exception("Unexpected error in cleanup_thumbnail_cache")

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
            try:
                artists = subs_svc.get_monitored_artists_needing_sync(
                    session=session,
                    sync_interval_hours=self.sync_interval_hours
                ) or []
            except Exception:
                logger.exception("Failed fetching monitored artists")
                return

            if not artists:
                logger.debug("No monitored artists need syncing")
                return

            # We look for due artists far more often than they are synced, so
            # skip any artist whose sync job is still waiting in the queue.
            from .models import Job
            from sqlalchemy import select, and_
            pending_payloads = session.execute(
                select(Job.payload).where(
                    and_(
                        Job.type == "sync_artist",
                        Job.status.in_(["queued", "reserved"]),
                    )
                )
            ).scalars().all()
            already_queued = {
                p.get("artist_id") for p in pending_payloads if isinstance(p, dict)
            }

            skipped = sum(1 for a in artists if str(getattr(a, "id", "")) in already_queued)
            if skipped == len(artists):
                logger.debug(f"{skipped} artist(s) due for sync already have a job queued")
                return
            logger.info(f"Found {len(artists)} monitored artist(s) needing sync ({skipped} already queued)")

            enqueued_count = 0
            for artist in artists:
                try:
                    artist_id = getattr(artist, "id", None)
                    if not artist_id:
                        continue
                    if str(artist_id) in already_queued:
                        logger.debug(f"Sync already queued for artist {artist_id}, skipping")
                        continue

                    # Enqueue sync_artist job
                    payload = {"artist_id": str(artist_id)}  # ← Fixed: was "channel_id"
                    
                    try:
                        job = enqueue_job(
                            session=session,
                            job_type="sync_artist",
                            payload=payload,
                            priority=25,  # Higher priority for syncs
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

    def sync_charts(self) -> None:
        """
        Enqueue sync_chart jobs for enabled charts not synced within
        chart_sync_interval_days. Skipped entirely while the charts feature is off.
        """
        session: Optional[Session] = None
        try:
            session = SessionLocal()

            if not features.charts_enabled(session):
                logger.debug("Charts feature disabled, skipping chart sync")
                return

            try:
                subscriptions = charts_svc.get_chart_subscriptions_needing_sync(
                    session=session,
                    sync_interval_hours=self.chart_sync_interval_days * 24,
                )
            except Exception:
                logger.exception("Failed fetching chart subscriptions needing sync")
                return

            if not subscriptions:
                logger.debug("No charts need syncing")
                return

            enqueued_count = 0
            for sub in subscriptions:
                try:
                    # enqueue_chart_sync reuses a job that is already waiting
                    if charts_svc.pending_sync_job(session, sub.country_code):
                        logger.debug(f"Sync already queued for chart {sub.country_code}, skipping")
                        continue
                    charts_svc.enqueue_chart_sync(session, sub.country_code)
                    session.commit()
                    enqueued_count += 1
                except Exception:
                    session.rollback()
                    logger.exception(f"Failed to enqueue sync job for chart {sub.country_code}")

            logger.info(f"Processed {len(subscriptions)} chart(s) due for sync (enqueued {enqueued_count} jobs)")

        finally:
            if session:
                try:
                    session.close()
                except Exception:
                    pass

    def cleanup_old_jobs(self) -> None:
        """
        Clean up old finished jobs (done, failed, cancelled) to prevent
        database bloat.
        """
        session: Optional[Session] = None
        try:
            session = SessionLocal()
            
            # Get cleanup days from settings
            days_old = settings_module.get_setting(
                session,
                "scheduler.job_cleanup_days",
                default=3
            )
            
            # Delete jobs older than specified days
            deleted = cleanup_old_jobs(
                session=session,
                days_old=int(days_old),
            )
            
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} old finished jobs")
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
        
    def sweep_stale_work(self) -> None:
        """
        Requeue jobs whose worker stopped heartbeating, and delete download
        scratch dirs nobody is writing to any more.

        Workers reclaim their own orphaned jobs when they start, but that
        needs the same worker name to come back: scale DOWNLOAD_WORKERS
        down and the retired worker's in-flight job would sit "reserved"
        forever. Its heartbeat goes stale within minutes, and this sweep
        catches that from a process that always runs.
        """
        session: Optional[Session] = None
        try:
            session = SessionLocal()
            # "scheduler" never reserves anything, so this only reclaims by
            # stale heartbeat, never by owner name.
            reclaimed = reclaim_orphaned_jobs(session, "scheduler")
            if reclaimed:
                logger.warning(f"Reclaimed {reclaimed} job(s) abandoned by a dead worker")
            self._requeue_orphaned_track_downloads(session)
        except Exception:
            logger.exception("Failed to reclaim stale jobs")
            if session:
                session.rollback()
        finally:
            if session:
                try:
                    session.close()
                except Exception:
                    pass

        # A worker killed mid-download leaves DOWNLOAD_DIR/<video_id>/ behind
        # until that job retries (which wipes it); if the job was cancelled
        # instead, nothing ever would. A live download touches its dir
        # constantly, so an hour without writes means abandoned.
        try:
            import shutil
            from . import config
            cutoff = time.time() - 3600
            removed = 0
            for d in config.DOWNLOAD_DIR.iterdir():
                if d.is_dir() and d.stat().st_mtime < cutoff:
                    shutil.rmtree(d, ignore_errors=True)
                    removed += 1
            if removed:
                logger.info(f"Removed {removed} stale download scratch dir(s)")
        except FileNotFoundError:
            pass
        except Exception:
            logger.exception("Failed to sweep download scratch dirs")

    def _requeue_orphaned_track_downloads(self, session: Session) -> None:
        """
        Fix up "queued" and "downloading" tracks whose job is gone.

        Everything that creates or drops a download job updates the track in
        the same transaction, so this should find nothing; it's the safety net
        for whatever slips through (a job deleted by hand, a crash between
        commits). A "queued" track gets a new job, or goes back to "available"
        if its album is no longer downloaded.

        A "downloading" track goes back to "available": its job was cancelled
        mid-download (cancel_download_jobs lets the worker finish) and the
        worker then died, so nothing will ever hand it back. If that worker is
        in fact still going, it lands the file as usual and the track ends up
        "done" anyway.

        A track is only acted on when two sweeps in a row find it orphaned:
        the jobs and tracks are read in two statements, not one snapshot, so a
        single sighting can just be a download queued between the two reads.
        """
        from .models import Track
        from .services import tracks as tracks_svc

        active = tracks_svc.active_download_track_ids(session)  # read first; see above
        candidates = session.query(Track).filter(Track.status.in_(("queued", "downloading"))).all()
        orphans = {t.id: t for t in candidates if t.id not in active}

        confirmed = [t for tid, t in orphans.items() if tid in self._orphaned_track_ids]
        self._orphaned_track_ids = set(orphans) - {t.id for t in confirmed}
        if not confirmed:
            return

        wanted = [
            t for t in confirmed
            if t.status == "queued" and t.album and t.album.mode == "download"
        ]
        released = [t for t in confirmed if t not in wanted]
        for track in released:
            track.status = "available"
            track.last_error = None
            session.add(track)
        requeued = tracks_svc.queue_track_downloads(session, wanted)

        # queue_track_downloads rolls up its own albums; the released ones
        # would otherwise keep showing "pending"/"downloading"
        released_albums = {t.album_id for t in released if t.album_id}
        if released_albums:
            session.flush()  # autoflush=False: the rollup has to see the new statuses
            for album_id in released_albums:
                subs_svc.check_and_update_album_download_status(session, album_id)

        session.commit()
        logger.warning(
            f"Found {len(confirmed)} queued/downloading track(s) with no download job: "
            f"requeued {requeued}, released {len(released)}"
        )

    def cleanup_thumbnail_cache(self) -> None:
        """
        Delete thumbnail proxy cache files (routers/media.py) older than
        THUMBNAIL_CACHE_TTL. The proxy already refuses to serve them, so
        running this daily only bounds how long dead files sit on disk.
        """
        from . import config
        cutoff = time.time() - config.THUMBNAIL_CACHE_TTL
        removed = 0
        try:
            for f in config.THUMBNAIL_CACHE_DIR.glob("*.jpg"):
                try:
                    if f.stat().st_mtime < cutoff:
                        f.unlink()
                        removed += 1
                except FileNotFoundError:
                    pass  # cleared from the admin endpoint meanwhile
        except FileNotFoundError:
            return
        if removed:
            logger.info(f"Removed {removed} expired thumbnail cache file(s)")
        else:
            logger.debug("No expired thumbnail cache files")

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

    def retry_missing_lyrics(self) -> None:
        """
        Find tracks that need lyrics recovery or plain-to-synced upgrade
        and enqueue deduplicated download_lyrics jobs.

        Two categories:
        1. Recovery: status="done", has audio, lyrics=None → normal download
        2. Upgrade: lyrics="plain" → attempt synced upgrade

        Each sweep takes a capped batch per category, least recently retried
        first (Track.lyrics_retried_at), so the whole library rotates through.
        """
        session: Optional[Session] = None
        try:
            session = SessionLocal()

            # Check if lyrics feature is enabled
            lyrics_enabled = settings_module.get_setting(
                session, "features.lyrics_enabled", True
            )
            if not lyrics_enabled:
                logger.debug("Lyrics feature disabled, skipping retry")
                return

            from .models import Track, Job
            from .time_utils import now_utc
            from sqlalchemy import select

            # Tracks with a lyrics job already waiting or running. The NULL
            # filter matters: one NULL in a NOT IN list matches nothing at all.
            pending_track_id = Job.payload["track_id"].as_string()
            pending = select(pending_track_id).where(
                Job.type == "download_lyrics",
                Job.status.in_(["queued", "reserved"]),
                pending_track_id != None,  # noqa: E711
            )

            def due_tracks(*conditions, limit: int) -> list[Track]:
                # Least recently retried first, never-retried before all:
                # tracks LRCLIB never has lyrics for would otherwise come back
                # in the same batch every sweep and starve all the others.
                return list(session.execute(
                    select(Track)
                    .where(*conditions, Track.id.notin_(pending))
                    .order_by(Track.lyrics_retried_at.asc().nulls_first(), Track.id)
                    .limit(limit)
                ).scalars().all())

            # === Category 1: Recovery (missing lyrics) ===
            recovery_tracks = due_tracks(
                Track.status == "done",
                Track.file_path != None,  # noqa: E711
                Track.lyrics == None,  # noqa: E711
                limit=50,
            )
            # === Category 2: Upgrade (plain → synced) ===
            upgrade_tracks = due_tracks(Track.lyrics == "plain", limit=25)

            now = now_utc()
            for track in recovery_tracks:
                enqueue_job(
                    session,
                    job_type="download_lyrics",
                    payload={"track_id": track.id},
                    priority=3,
                    max_attempts=3,
                    commit=False,
                )
                track.lyrics_retried_at = now
            for track in upgrade_tracks:
                enqueue_job(
                    session,
                    job_type="download_lyrics",
                    payload={"track_id": track.id, "mode": "upgrade"},
                    priority=2,
                    max_attempts=2,
                    commit=False,
                )
                track.lyrics_retried_at = now
            # Jobs and timestamps together, so a track is never marked as
            # retried without its job
            session.commit()

            recovery_count, upgrade_count = len(recovery_tracks), len(upgrade_tracks)
            if recovery_count or upgrade_count:
                logger.info(
                    f"Lyrics retry: enqueued {recovery_count} recovery + "
                    f"{upgrade_count} upgrade jobs"
                )
            else:
                logger.debug("Lyrics retry: no tracks need recovery or upgrade")

        except Exception:
            logger.exception("Failed in retry_missing_lyrics")
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
    from .logging_config import configure_logging
    configure_logging(process_name="scheduler")
    sched = Scheduler()
    try:
        sched.start()
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        sched.stop()