# backend/scheduler.py
"""
Scheduler for periodic tasks, run as its own process (deploy/supervisord.conf).

Responsibilities:
1. Sync followed artists for new releases (`scheduler.artist_sync`), and
   queue the genre lookups that are due (services/genres.py) along with them
2. Re-sync followed charts (`scheduler.chart_sync`) and rescan followed
   playlists (`scheduler.playlist_sync`)
3. Retry/upgrade missing lyrics (`scheduler.lyrics_retry`)
4. Clean up old finished jobs, failed ones included (daily, keeping
   `scheduler.job_cleanup_days`), and expired refresh tokens (daily)
5. Requeue jobs abandoned by a dead worker, fix up "queued"/"downloading"
   tracks that lost their job, and drop stale download scratch dirs
   (every 5 minutes)
6. Delete thumbnail proxy cache files older than THUMBNAIL_CACHE_TTL (daily)

1, 2 and 3 follow schedules set in the admin panel (backend/schedules.py):
every N hours/days, or at a fixed time on chosen days of the week.
"""
from __future__ import annotations
import logging
import shutil
import signal
import threading
import time
from datetime import datetime, timedelta
from typing import Callable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config, schedules
from . import settings as settings_module
from .db import SessionLocal, wait_for_db
from .jobs.jobqueue import PENDING_STATUSES, cleanup_old_jobs, enqueue_job, pending_jobs, reclaim_orphaned_jobs
from .jobs.priorities import Origin
from .models import Job, Track
from .services import auth as auth_svc
from .services import charts as charts_svc
from .services import genres as genres_svc
from .services import playlists as playlists_svc
from .services import subscriptions as subs_svc
from .services import tracks as tracks_svc
from .time_utils import now_utc

logger = logging.getLogger("scheduler")

# Where each schedule's last fixed-time run is recorded (internal settings)
ARTIST_LAST_RUN = "scheduler.artist_sync_last_run"
CHART_LAST_RUN = "scheduler.chart_sync_last_run"
PLAYLIST_LAST_RUN = "scheduler.playlist_sync_last_run"
LYRICS_LAST_RUN = "scheduler.lyrics_retry_last_run"

# How often the loop wakes up. Every minute: a fixed-time run starts on
# time, and in interval mode -- a cutoff on each artist's last_synced_at --
# an artist is picked up within a minute of becoming due (polling exactly
# every N hours would find it synced a few seconds *after* the cutoff and
# skip it until 2N). Schedule changes made in the admin panel are read at
# every tick too.
TICK_SECONDS = 60
DAILY = 86400
STALE_SWEEP_SECONDS = 300

# How many artists one sweep queues for a genre lookup: at ~4 s each on
# worker-genres, a few minutes of lookups, and enough to refresh 1500
# artists a month with the default schedule
GENRE_SWEEP_LIMIT = 50


class Scheduler:
    def __init__(self) -> None:
        self._stopped = threading.Event()
        # time.time() of each periodic task's last run (0: not yet, so all
        # run on the first tick)
        self._last_run: dict[str, float] = {}
        # Tracks the previous sweep found "queued" with no job (see
        # _requeue_orphaned_track_downloads)
        self._orphaned_track_ids: set[str] = set()

    def stop(self, *_args) -> None:
        self._stopped.set()

    def run(self) -> None:
        """Run until stopped (SIGTERM/SIGINT)."""
        wait_for_db()
        logger.info("Scheduler started (TZ=%s)", schedules.timezone())
        while not self._stopped.is_set():
            self._safely("scheduler tick", self._tick, time.time())
            self._stopped.wait(TICK_SECONDS)
        logger.info("Scheduler stopped")

    def _tick(self, now: float) -> None:
        with SessionLocal() as session:
            artist_schedule = self._schedule(session, "scheduler.artist_sync")
            chart_schedule = self._schedule(session, "scheduler.chart_sync")
            playlist_schedule = self._schedule(session, "scheduler.playlist_sync")
            lyrics_schedule = self._schedule(session, "scheduler.lyrics_retry")

        self._safely("artist syncs", self._run_artist_syncs, artist_schedule, now)
        self._safely("chart syncs", self._run_scheduled, chart_schedule, CHART_LAST_RUN, "days", self.sync_charts)
        self._safely("playlist syncs", self._run_scheduled, playlist_schedule, PLAYLIST_LAST_RUN, "hours", self.sync_playlists)
        self._safely("lyrics retry", self._run_lyrics_retry, lyrics_schedule, now)
        self._every("cleanup_old_jobs", DAILY, now, self.cleanup_old_jobs)
        self._every("cleanup_expired_tokens", DAILY, now, self.cleanup_expired_tokens)
        self._every("sweep_stale_work", STALE_SWEEP_SECONDS, now, self.sweep_stale_work)
        self._every("cleanup_thumbnail_cache", DAILY, now, self.cleanup_thumbnail_cache)

    # -- plumbing --------------------------------------------------------------

    @staticmethod
    def _schedule(session: Session, key: str) -> schedules.Schedule:
        default = settings_module.get_default_value(key)
        return schedules.parse(settings_module.get_setting(session, key), default)

    @staticmethod
    def _safely(what: str, task: Callable, *args) -> None:
        try:
            task(*args)
        except Exception:
            logger.exception("Unexpected error in %s", what)

    def _every(self, name: str, interval: float, now: float, task: Callable[[], None]) -> None:
        """Run `task` when `interval` seconds have passed since its last run (a failed one included)."""
        if now - self._last_run.get(name, 0) < interval:
            return
        self._last_run[name] = now
        self._safely(name, task)

    @staticmethod
    def _fixed_run_due(schedule: schedules.Schedule, last_run_key: str) -> Optional[datetime]:
        """The fixed run of `schedule` to do now, given the last one done (stored under last_run_key)."""
        with SessionLocal() as session:
            raw = settings_module.get_setting(session, last_run_key)
        last_done = None
        if raw:
            try:
                last_done = datetime.fromisoformat(raw)
            except ValueError:
                logger.warning("Ignoring unparseable %s=%r", last_run_key, raw)
        return schedules.due_run(schedule, last_done, now_utc())

    @staticmethod
    def _mark_fixed_run(last_run_key: str) -> None:
        with SessionLocal() as session:
            settings_module.set_setting(session, last_run_key, now_utc().isoformat())

    def _run_scheduled(
        self,
        schedule: schedules.Schedule,
        last_run_key: str,
        unit: str,
        sync: Callable[[datetime], None],
    ) -> None:
        """
        Interval mode: sync whatever was last synced more than N hours (or
        days) ago, each on its own cadence. Fixed mode: at the run time,
        whatever wasn't synced since.
        """
        if schedule.fixed:
            run = self._fixed_run_due(schedule, last_run_key)
            if run is not None:
                logger.info("Fixed-time run of %s (%s)", last_run_key, schedule.time)
                sync(run)
                self._mark_fixed_run(last_run_key)
            return
        sync(now_utc() - timedelta(**{unit: schedule.every}))

    def _run_artist_syncs(self, schedule: schedules.Schedule, now: float) -> None:
        """Artist syncs, with the genre sweep going along so all network work keeps to the same schedule."""
        if schedule.fixed:
            def sync_with_genres(cutoff: datetime) -> None:
                self.sync_monitored_artists(cutoff)
                self.queue_due_genre_lookups()
            self._run_scheduled(schedule, ARTIST_LAST_RUN, "hours", sync_with_genres)
            return
        self._run_scheduled(schedule, ARTIST_LAST_RUN, "hours", self.sync_monitored_artists)
        self._every("queue_due_genre_lookups", schedule.every * 3600, now, self.queue_due_genre_lookups)

    def _run_lyrics_retry(self, schedule: schedules.Schedule, now: float) -> None:
        if schedule.fixed:
            if self._fixed_run_due(schedule, LYRICS_LAST_RUN):
                self.retry_missing_lyrics()
                self._mark_fixed_run(LYRICS_LAST_RUN)
            return
        self._every("retry_missing_lyrics", schedule.every * 3600, now, self.retry_missing_lyrics)

    # -- tasks -----------------------------------------------------------------

    def sync_monitored_artists(self, cutoff: datetime) -> None:
        """
        Queue a sync_artist job (AUTO) for every artist followed in full and
        last synced before `cutoff`. We look for due artists far more often
        than they are synced, so artists whose sync is still waiting or
        running are skipped.
        """
        with SessionLocal() as session:
            artists = subs_svc.get_monitored_artists_needing_sync(session, cutoff)
            if not artists:
                return
            busy = {job.payload.get("artist_id") for job in pending_jobs(session, "sync_artist")}
            due = [a for a in artists if a.id not in busy]
            for artist in due:
                enqueue_job(session, job_type="sync_artist", payload={"artist_id": artist.id},
                            origin=Origin.AUTO, commit=False)
            session.commit()
        if due:
            logger.info("Queued a sync of %s artist(s) (%s due, %s already queued)",
                        len(due), len(artists), len(artists) - len(due))

    def sync_charts(self, cutoff: datetime) -> None:
        """
        Queue a sync_chart job for every enabled chart last synced before
        `cutoff` (one already waiting is reused). Skipped entirely while the
        charts feature is off.
        """
        with SessionLocal() as session:
            if not settings_module.feature_enabled(session, "charts"):
                return
            queued = 0
            for subscription in charts_svc.get_chart_subscriptions_needing_sync(session, cutoff):
                _, created = charts_svc.enqueue_chart_sync(session, subscription.country_code)
                queued += created
            session.commit()
        if queued:
            logger.info("Queued a sync of %s chart(s)", queued)

    def sync_playlists(self, cutoff: datetime) -> None:
        """Queue a rescan (AUTO) of every followed playlist last scanned before `cutoff`."""
        with SessionLocal() as session:
            due = playlists_svc.followed_needing_sync(session, cutoff)
            for playlist in due:
                playlists_svc.queue_sync(session, playlist, origin=Origin.AUTO, fetch=True)
            session.commit()
        if due:
            logger.info("Queued a scan of %s followed playlist(s)", len(due))

    def queue_due_genre_lookups(self) -> None:
        """
        Queue a fetch_genres for subscribed artists whose genres are due
        (services/genres.py): the monthly refresh, and artists a sync never
        visits again -- light ones, whose albums were downloaded on their own
        -- after lookups were switched off and on again. Syncs and imports
        queue lookups for new albums themselves; this is the catch-all.
        """
        with SessionLocal() as session:
            if not settings_module.feature_enabled(session, "genres"):
                return
            queued = sum(
                genres_svc.queue_lookup(session, artist_id, origin=Origin.AUTO)
                for artist_id in genres_svc.due_artist_ids(session, GENRE_SWEEP_LIMIT)
            )
            session.commit()
        if queued:
            logger.info("Queued %s genre lookup(s)", queued)

    def retry_missing_lyrics(self) -> None:
        """
        Queue download_lyrics jobs for tracks that need lyrics recovery or a
        plain-to-synced upgrade:
        1. Recovery: on disk, with no lyrics -> normal download
        2. Upgrade: plain lyrics -> look for synced ones

        Each sweep takes a capped batch per category, least recently retried
        first (Track.lyrics_retried_at), so the whole library rotates through.
        """
        with SessionLocal() as session:
            if not settings_module.feature_enabled(session, "lyrics"):
                return

            # Tracks with a lyrics job already waiting or running. The NULL
            # filter matters: one NULL in a NOT IN list matches nothing at all.
            pending_track_id = Job.payload["track_id"].as_string()
            pending = select(pending_track_id).where(
                Job.type == "download_lyrics",
                Job.status.in_(PENDING_STATUSES),
                pending_track_id.is_not(None),
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

            recovery = due_tracks(Track.status == "done", Track.file_path.is_not(None), Track.lyrics.is_(None), limit=50)
            upgrade = due_tracks(Track.lyrics == "plain", limit=25)

            # Same priority for both: recoveries still run first, being queued
            # first (ties go to the oldest job)
            now = now_utc()
            for tracks, payload_extra, attempts in ((recovery, {}, 3), (upgrade, {"mode": "upgrade"}, 2)):
                for track in tracks:
                    enqueue_job(
                        session,
                        job_type="download_lyrics",
                        payload={"track_id": track.id, **payload_extra},
                        origin=Origin.AUTO,
                        max_attempts=attempts,
                        commit=False,
                    )
                    track.lyrics_retried_at = now
            # Jobs and timestamps together, so a track is never marked as
            # retried without its job
            session.commit()

        if recovery or upgrade:
            logger.info("Lyrics retry: queued %s recovery + %s upgrade jobs", len(recovery), len(upgrade))

    def cleanup_old_jobs(self) -> None:
        """Delete finished jobs (done, failed, cancelled) older than scheduler.job_cleanup_days."""
        with SessionLocal() as session:
            days = int(settings_module.get_setting(session, "scheduler.job_cleanup_days"))
            deleted = cleanup_old_jobs(session, days_old=days)
        if deleted:
            logger.info("Cleaned up %s old finished jobs (older than %s days)", deleted, days)

    def cleanup_expired_tokens(self) -> None:
        with SessionLocal() as session:
            deleted = auth_svc.cleanup_expired_tokens(session)
        if deleted:
            logger.info("Cleaned up %s expired refresh tokens", deleted)

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
        with SessionLocal() as session:
            # "scheduler" never reserves anything, so this only reclaims by
            # stale heartbeat, never by owner name.
            reclaim_orphaned_jobs(session, "scheduler")
            self._requeue_orphaned_track_downloads(session)

        # A worker killed mid-download leaves DOWNLOAD_DIR/<video_id>/ behind
        # until that job retries (which wipes it); if the job was cancelled
        # instead, nothing ever would. A live download touches its dir
        # constantly, so an hour without writes means abandoned.
        cutoff = time.time() - 3600
        removed = 0
        try:
            for d in config.DOWNLOAD_DIR.iterdir():
                if d.is_dir() and d.stat().st_mtime < cutoff:
                    shutil.rmtree(d, ignore_errors=True)
                    removed += 1
        except FileNotFoundError:
            pass
        if removed:
            logger.info("Removed %s stale download scratch dir(s)", removed)

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
        requeued = tracks_svc.queue_track_downloads(session, wanted, origin=Origin.AUTO)

        # queue_track_downloads rolls up its own albums; the released ones
        # would otherwise keep showing "pending"/"downloading"
        released_albums = {t.album_id for t in released if t.album_id}
        if released_albums:
            session.flush()  # autoflush=False: the rollup has to see the new statuses
            for album_id in released_albums:
                subs_svc.check_and_update_album_download_status(session, album_id)

        session.commit()
        logger.warning(
            "Found %s queued/downloading track(s) with no download job: requeued %s, released %s",
            len(confirmed), requeued, len(released),
        )

    def cleanup_thumbnail_cache(self) -> None:
        """
        Delete thumbnail proxy cache files (routers/media.py) older than
        THUMBNAIL_CACHE_TTL. The proxy already refuses to serve them, so
        running this daily only bounds how long dead files sit on disk.
        """
        cutoff = time.time() - config.THUMBNAIL_CACHE_TTL
        removed = 0
        for f in config.THUMBNAIL_CACHE_DIR.glob("*.jpg"):
            try:
                if f.stat().st_mtime < cutoff:
                    f.unlink()
                    removed += 1
            except FileNotFoundError:
                pass  # trimmed by the proxy meanwhile
        if removed:
            logger.info("Removed %s expired thumbnail cache file(s)", removed)


if __name__ == "__main__":
    from .logging_config import configure_logging

    configure_logging(process_name="scheduler")
    scheduler = Scheduler()
    signal.signal(signal.SIGTERM, scheduler.stop)
    signal.signal(signal.SIGINT, scheduler.stop)
    scheduler.run()
