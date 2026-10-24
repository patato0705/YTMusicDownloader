# backend/services/subscriptions.py
"""
What the library follows: artist subscriptions ("light": album metadata
only; "full": every release downloaded) and each album's mode
("metadata" or "download"), with the jobs that act on them.
"""
from __future__ import annotations
import logging
from typing import Collection, Optional
from datetime import datetime

from sqlalchemy import select, func, case
from sqlalchemy.orm import Session

from ..jobs.jobqueue import cancel_download_jobs, enqueue_job, pending_jobs
from ..jobs.priorities import Origin, promote
from ..models import Artist, Album, ArtistSubscription, Track
from ..time_utils import now_utc

logger = logging.getLogger("services.subscriptions")


# ============================================================================
# ARTIST SUBSCRIPTIONS
# ============================================================================

def get_artist_subscription(session: Session, artist_id: str) -> Optional[ArtistSubscription]:
    """Get artist subscription by artist ID."""
    stmt = select(ArtistSubscription).where(ArtistSubscription.artist_id == artist_id)
    return session.execute(stmt).scalars().first()


def subscribe_to_artist(session: Session, artist_id: str, mode: str = "full") -> ArtistSubscription:
    """Create the artist's subscription, or change its mode. Does not commit."""
    if mode not in ("light", "full"):
        raise ValueError(f"Invalid mode: {mode}. Must be 'light' or 'full'")

    subscription = get_artist_subscription(session, artist_id)
    if subscription is None:
        subscription = ArtistSubscription(artist_id=artist_id, mode=mode, enabled=True, created_at=now_utc())
        session.add(subscription)
        logger.info("Created artist subscription: %s (mode=%s)", artist_id, mode)
    elif subscription.mode != mode:
        logger.info("Updating artist subscription %s: %s -> %s", artist_id, subscription.mode, mode)
        subscription.mode = mode
    return subscription


def queue_artist_sync(
    session: Session,
    artist_id: str,
    user_id: Optional[int] = None,
    *,
    origin: Origin,
) -> bool:
    """
    Queue a sync_artist job, or move one already waiting up to `origin`'s
    class. One already running doesn't count: it may have read the
    subscription before the change that calls for this sync. Does not
    commit. Returns whether a job was queued.
    """
    waiting = pending_jobs(session, "sync_artist", statuses=("queued",), artist_id=artist_id)
    if waiting:
        promote(waiting[0], origin)
        return False
    enqueue_job(
        session, job_type="sync_artist", payload={"artist_id": artist_id},
        origin=origin, user_id=user_id, commit=False,
    )
    return True


def follow_artist(
    session: Session,
    artist_id: str,
    name: Optional[str],
    user_id: Optional[int] = None,
    *,
    origin: Origin,
) -> bool:
    """
    Follow an artist in full: its row (named `name` if it's new), a full
    subscription (a light one upgraded), and a sync job, which fetches the
    artist and brings in every release. No network here. Does not commit.
    Returns False when it was already followed in full.
    """
    subscription = get_artist_subscription(session, artist_id)
    if subscription is not None and subscription.mode == "full":
        return False
    if session.get(Artist, artist_id) is None:
        session.add(Artist(id=artist_id, name=name or ""))
    subscribe_to_artist(session, artist_id, mode="full")
    queue_artist_sync(session, artist_id, user_id=user_id, origin=origin)
    return True


def mark_artist_synced(
    session: Session,
    artist_id: str,
    error: Optional[str] = None,
) -> None:
    """Record a sync of the artist (and its error, if it failed). Does not commit."""
    subscription = get_artist_subscription(session, artist_id)
    if subscription:
        subscription.last_synced_at = now_utc()
        subscription.last_error = error


def get_monitored_artists_needing_sync(session: Session, cutoff: datetime) -> list[Artist]:
    """
    Artists followed in full (enabled subscription) not synced since
    `cutoff`, or ever. Used by the scheduler.
    """
    stmt = (
        select(Artist)
        .join(ArtistSubscription, ArtistSubscription.artist_id == Artist.id)
        .where(
            ArtistSubscription.enabled.is_(True),
            ArtistSubscription.mode == "full",
            ArtistSubscription.last_synced_at.is_(None) | (ArtistSubscription.last_synced_at < cutoff),
        )
    )
    return list(session.execute(stmt).scalars().all())


# ============================================================================
# ALBUM MODE
# ============================================================================

def clear_album_download(session: Session, album_id: str) -> bool:
    """
    Downgrade an album back to metadata mode, cancel its pending downloads
    and clear download status. Does not commit.

    Returns:
        True if album existed, False otherwise
    """
    album = session.get(Album, album_id)
    if not album:
        return False

    album.mode = "metadata"
    album.download_status = None
    _stop_album_downloads(session, [album_id])
    logger.info("Cleared album download for %s", album_id)
    return True


def upgrade_all_albums_to_download(
    session: Session,
    artist_id: str,
    user_id: Optional[int] = None,
    *,
    origin: Origin,
) -> int:
    """
    Switch the artist's metadata albums to download mode and queue an
    import_album for each, so their tracks get (re)listed and downloaded;
    the download-mode albums that still have no tracks get one too (just
    created by a sync, or an earlier import that never landed: nothing
    else would ever import them). Does not commit. Returns the imports queued.
    """
    albums = session.execute(
        select(Album).where(Album.artist_id == artist_id, Album.mode == "metadata")
    ).scalars().all()
    for album in albums:
        album.mode = "download"
    if albums:
        logger.info("Upgraded %s albums to download mode for artist %s", len(albums), artist_id)
        session.flush()  # autoflush=False: the trackless query below must see them

    trackless = session.execute(
        select(Album.id).where(
            Album.artist_id == artist_id,
            Album.mode == "download",
            ~select(Track.id).where(Track.album_id == Album.id).exists(),
        )
    ).scalars().all()
    return queue_album_imports(
        session,
        {a.id for a in albums} | set(trackless),
        artist_id=artist_id,
        user_id=user_id,
        origin=origin,
    )


def queue_album_imports(
    session: Session,
    album_ids: Collection[str],
    artist_id: Optional[str] = None,
    user_id: Optional[int] = None,
    *,
    origin: Origin,
) -> int:
    """
    Queue an import_album job for each album that doesn't already have one
    waiting or running. A waiting one is moved up to `origin`'s class if
    that's higher (see jobs/priorities.py) rather than duplicated. Does not
    commit. Returns the number queued.
    """
    if not album_ids:
        return 0
    pending = {
        job.payload.get("browse_id"): job
        for job in pending_jobs(session, "import_album", browse_id=set(album_ids))
    }
    queued = 0
    for album_id in sorted(album_ids):
        if album_id in pending:
            promote(pending[album_id], origin)
            continue
        enqueue_job(
            session,
            job_type="import_album",
            payload={"browse_id": album_id, "artist_id": artist_id},
            origin=origin,
            user_id=user_id,
            commit=False,
        )
        queued += 1
    return queued


def downgrade_all_albums_to_metadata(session: Session, artist_id: str) -> int:
    """
    Downgrade all albums for an artist from download to metadata mode and
    cancel their pending downloads. Files already on disk stay.
    Used when downgrading artist from full to light mode. Does not commit.

    Returns:
        Number of albums downgraded
    """
    albums = session.execute(
        select(Album).where(Album.artist_id == artist_id, Album.mode == "download")
    ).scalars().all()
    for album in albums:
        album.mode = "metadata"
        album.download_status = None
    _stop_album_downloads(session, [a.id for a in albums])

    if albums:
        logger.info("Downgraded %s albums to metadata mode for artist %s", len(albums), artist_id)
    return len(albums)


def _stop_album_downloads(session: Session, album_ids: Collection[str]) -> None:
    """
    Cancel the download jobs of these albums' tracks and hand the tracks
    that were waiting (or had failed) back to "available". A download
    already running is left to finish. Does not commit.
    """
    if not album_ids:
        return
    tracks = session.execute(
        select(Track).where(Track.album_id.in_(list(album_ids)))
    ).scalars().all()
    cancel_download_jobs(session, [t.id for t in tracks], reason="album no longer followed")

    for track in tracks:
        if track.status in ("queued", "failed"):
            track.status = "available"
            track.last_error = None


def start_album_download(
    session: Session,
    album_id: str,
    *,
    origin: Origin,
    user_id: Optional[int] = None,
) -> dict:
    """
    Download an album: set it to download mode, write its album.nfo and
    queue a download for every track not on disk.

    An album not in the DB yet is fetched here (raises
    ytm_adapter.YTMusicUnavailable when it can't be), so it shows up with
    its real title, artist and tracks right away, and its downloads are
    queued straight from that fetch. One already in the DB gets an
    import_album instead, which fetches the current tracklist first: the
    same path as the albums of a followed artist. Its artist gets a light
    subscription if it has none (album metadata and pictures, no
    downloads), synced right after.

    Commits. Returns {"album": Album, "started": bool,
    "artist_subscription_created": bool}; started is False for an album
    already in download mode.
    """
    from . import albums as albums_svc

    album = session.get(Album, album_id)
    fetched = album is None
    if fetched:
        logger.info("Album %s not in DB, fetching from YTMusic", album_id)
        albums_svc.fetch_and_upsert_album(session, browse_id=album_id)
        session.flush()  # autoflush=False: get can't see the new row before this
        album = session.get(Album, album_id)
    elif album.mode == "download":
        return {"album": album, "started": False, "artist_subscription_created": False}

    album.mode = "download"
    artist_sub_created = False
    if album.artist_id and not get_artist_subscription(session, album.artist_id):
        subscribe_to_artist(session, artist_id=album.artist_id, mode="light")
        # The light subscription's sync fetches the artist's album list and pictures
        queue_artist_sync(session, album.artist_id, user_id=user_id, origin=origin)
        artist_sub_created = True
        logger.info("Auto-created light artist subscription for %s", album.artist_id)

    if fetched:
        session.commit()
        albums_svc.complete_import(session, album_id, origin=origin)
    else:
        session.flush()  # autoflush=False: the rollup and the import check see the mode change
        check_and_update_album_download_status(session, album_id)
        queue_album_imports(session, [album_id], artist_id=album.artist_id, user_id=user_id, origin=origin)
        session.commit()

    logger.info("Album %s set to download", album_id)
    return {"album": album, "started": True, "artist_subscription_created": artist_sub_created}


def check_and_update_album_download_status(session: Session, album_id: str) -> str:
    """
    Recompute Album.download_status from its tracks' statuses. Does not commit.

    Status logic, first match wins:
    - "completed": all tracks are "done"
    - "downloading": at least one track is "downloading"
    - "pending": at least one track is "queued"
    - "failed": at least one track is "failed" (and nothing left to try)
    - "idle": no tracks, or the rest are "available" (nothing planned)

    Returns:
        The new download_status string
    """
    album = session.get(Album, album_id)
    if not album:
        return "idle"

    # Only albums being downloaded have a download status. A metadata album
    # can still see a track finish (a download that was already running when
    # it was unfollowed), which mustn't bring the status back.
    if album.mode != "download":
        album.download_status = None
        return "idle"

    stats = (
        session.query(
            func.count(Track.id).label("total"),
            func.sum(case((Track.status == "done", 1), else_=0)).label("done"),
            func.sum(case((Track.status == "downloading", 1), else_=0)).label("downloading"),
            func.sum(case((Track.status == "failed", 1), else_=0)).label("failed"),
            func.sum(case((Track.status == "queued", 1), else_=0)).label("queued"),
        )
        .filter(Track.album_id == album_id)
        .one()
    )

    if not stats.total:
        new_status = "idle"
    elif stats.done == stats.total:
        new_status = "completed"
    elif stats.downloading:
        new_status = "downloading"
    elif stats.queued:
        new_status = "pending"
    elif stats.failed:
        new_status = "failed"
    else:
        new_status = "idle"

    album.download_status = new_status
    return new_status
