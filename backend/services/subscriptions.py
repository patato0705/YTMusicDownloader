# backend/services/subscriptions.py

"""
Subscription service - manages artist and album subscriptions.
"""
from __future__ import annotations
import logging
from typing import Collection, Optional
from datetime import datetime

from sqlalchemy import select, func, case
from sqlalchemy.orm import Session

from ..models import Artist, Album, ArtistSubscription, Job, Track
from ..time_utils import now_utc, ensure_timezone_aware

logger = logging.getLogger("services.subscriptions")


# ============================================================================
# ARTIST SUBSCRIPTIONS
# ============================================================================

def get_artist_subscription(session: Session, artist_id: str) -> Optional[ArtistSubscription]:
    """Get artist subscription by artist ID."""
    stmt = select(ArtistSubscription).where(ArtistSubscription.artist_id == artist_id)
    return session.execute(stmt).scalars().first()


def subscribe_to_artist(
    session: Session,
    artist_id: str,
    mode: str = "full",
) -> ArtistSubscription:
    """
    Create or update artist subscription.
    
    Args:
        session: SQLAlchemy session
        artist_id: Artist ID
        mode: "light" (metadata only) or "full" (download everything)
    
    Returns:
        ArtistSubscription instance
    
    Raises:
        ValueError: If invalid mode
    """
    if mode not in ("light", "full"):
        raise ValueError(f"Invalid mode: {mode}. Must be 'light' or 'full'")
    
    # Check if already exists
    existing = get_artist_subscription(session, artist_id)
    
    if existing:
        # Update mode if different
        if existing.mode != mode:
            logger.info(f"Updating artist subscription {artist_id}: {existing.mode} → {mode}")
            existing.mode = mode
            session.add(existing)
        return existing
    
    # Create new subscription
    subscription = ArtistSubscription(
        artist_id=artist_id,
        mode=mode,
        enabled=True,
        created_at=now_utc(),
    )
    
    session.add(subscription)
    logger.info(f"Created artist subscription: {artist_id} (mode={mode})")
    
    return subscription


def unsubscribe_from_artist(session: Session, artist_id: str) -> bool:
    """
    Delete artist subscription.
    Does NOT delete files or database records - only stops syncing.
    
    Returns:
        True if deleted, False if not found
    """
    subscription = get_artist_subscription(session, artist_id)
    
    if not subscription:
        return False
    
    session.delete(subscription)
    logger.info(f"Deleted artist subscription: {artist_id}")
    
    return True


def update_artist_subscription_mode(
    session: Session,
    artist_id: str,
    mode: str,
) -> ArtistSubscription:
    """
    Update artist subscription mode.
    
    Args:
        mode: "light" or "full"
    
    Raises:
        ValueError: If subscription not found or invalid mode
    """
    if mode not in ("light", "full"):
        raise ValueError(f"Invalid mode: {mode}. Must be 'light' or 'full'")
    
    subscription = get_artist_subscription(session, artist_id)
    
    if not subscription:
        raise ValueError(f"No subscription found for artist {artist_id}")
    
    old_mode = subscription.mode
    subscription.mode = mode
    session.add(subscription)
    
    logger.info(f"Updated artist subscription {artist_id}: {old_mode} → {mode}")
    
    return subscription


def mark_artist_synced(
    session: Session,
    artist_id: str,
    error: Optional[str] = None,
) -> None:
    """Update artist subscription sync timestamp."""
    subscription = get_artist_subscription(session, artist_id)
    
    if subscription:
        subscription.last_synced_at = now_utc()
        subscription.last_error = error
        session.add(subscription)


# ============================================================================
# ALBUM MODE (formerly AlbumSubscription — now lives on the Album row)
# ============================================================================

def set_album_mode(session: Session, album_id: str, mode: str) -> Album:
    """
    Set the mode on an existing Album row.

    Args:
        mode: "metadata" or "download"

    Raises:
        ValueError: If album not found or invalid mode
    """
    if mode not in ("metadata", "download"):
        raise ValueError(f"Invalid mode: {mode}. Must be 'metadata' or 'download'")

    album = session.get(Album, album_id)
    if not album:
        raise ValueError(f"Album {album_id} not found")

    old_mode = album.mode
    if old_mode != mode:
        logger.info(f"Album {album_id} mode: {old_mode} → {mode}")
        album.mode = mode
        session.add(album)

    return album


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
    session.add(album)
    _stop_album_downloads(session, [album_id])
    logger.info(f"Cleared album download for {album_id}")
    return True


def upgrade_all_albums_to_download(
    session: Session,
    artist_id: str,
    user_id: Optional[int] = None,
) -> int:
    """
    Upgrade all albums for an artist from metadata to download mode, and
    queue an import_album for each so their tracks get (re)listed and
    downloaded. Used when upgrading artist from light to full mode.
    Does not commit.

    Download-mode albums that still have no tracks (an import that never
    landed) get one too, since the upgrade is when the user expects the
    whole discography to start downloading.

    Returns:
        Number of albums upgraded
    """
    stmt = select(Album).where(
        Album.artist_id == artist_id,
        Album.mode == "metadata",
    )
    albums = session.execute(stmt).scalars().all()

    for album in albums:
        album.mode = "download"
        session.add(album)

    count = len(albums)
    if count > 0:
        logger.info(f"Upgraded {count} albums to download mode for artist {artist_id}")

    queue_album_imports(
        session,
        {a.id for a in albums} | set(_trackless_download_album_ids(session, artist_id)),
        artist_id=artist_id,
        user_id=user_id,
    )
    return count


def _trackless_download_album_ids(session: Session, artist_id: str) -> list[str]:
    """The artist's download-mode albums that have no Track rows yet."""
    return list(session.execute(
        select(Album.id).where(
            Album.artist_id == artist_id,
            Album.mode == "download",
            ~select(Track.id).where(Track.album_id == Album.id).exists(),
        )
    ).scalars().all())


def queue_trackless_album_imports(
    session: Session,
    artist_id: str,
    user_id: Optional[int] = None,
) -> int:
    """
    Queue an import_album for each of the artist's download-mode albums
    that still has no tracks: just created by a sync, or an earlier import
    that never landed (failed, or its worker died on the last attempt).
    Track-based recovery (album retry, the scheduler's orphan sweep) can't
    see those, and a sync only creates albums it hasn't seen before, so
    without this they would stay empty for good.

    Albums with an import already waiting or running are skipped (see
    queue_album_imports), which only sees committed jobs: commit any
    imports queued earlier in the transaction first. Does not commit.
    Returns the number queued.
    """
    return queue_album_imports(
        session,
        _trackless_download_album_ids(session, artist_id),
        artist_id=artist_id,
        user_id=user_id,
    )


def queue_album_imports(
    session: Session,
    album_ids: Collection[str],
    artist_id: Optional[str] = None,
    user_id: Optional[int] = None,
    priority: int = 20,
) -> int:
    """
    Queue an import_album job for each album that doesn't already have one
    waiting or running. Does not commit. Returns the number queued.
    """
    from ..jobs.jobqueue import enqueue_job

    pending = {
        str(p.get("browse_id"))
        for p in session.execute(
            select(Job.payload).where(
                Job.type == "import_album",
                Job.status.in_(("queued", "reserved")),
            )
        ).scalars()
        if isinstance(p, dict)
    }

    queued = 0
    for album_id in sorted(album_ids):
        if album_id in pending:
            continue
        enqueue_job(
            session,
            job_type="import_album",
            payload={"browse_id": album_id, "artist_id": artist_id},
            priority=priority,
            user_id=user_id,
            commit=False,
        )
        pending.add(album_id)
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
    stmt = select(Album).where(
        Album.artist_id == artist_id,
        Album.mode == "download",
    )
    albums = session.execute(stmt).scalars().all()

    for album in albums:
        album.mode = "metadata"
        album.download_status = None
        session.add(album)

    _stop_album_downloads(session, [a.id for a in albums])

    count = len(albums)
    if count > 0:
        logger.info(f"Downgraded {count} albums to metadata mode for artist {artist_id}")
    return count


def _stop_album_downloads(session: Session, album_ids: Collection[str]) -> None:
    """
    Cancel the download jobs of these albums' tracks and hand the tracks
    that were waiting (or had failed) back to "available". A download
    already running is left to finish. Does not commit.
    """
    if not album_ids:
        return
    from ..jobs.jobqueue import cancel_download_jobs

    tracks = session.execute(
        select(Track).where(Track.album_id.in_(list(album_ids)))
    ).scalars().all()
    cancel_download_jobs(session, [t.id for t in tracks], reason="album no longer followed")

    for track in tracks:
        if track.status in ("queued", "failed"):
            track.status = "available"
            track.last_error = None
            session.add(track)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def check_and_update_album_download_status(
    session: Session,
    album_id: str,
) -> str:
    """
    Check track statuses for an album and update Album.download_status.

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
        session.add(album)
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
        .first()
    )

    if not stats:
        album.download_status = "idle"
        session.add(album)
        return "idle"

    total = int(stats.total or 0)
    done = int(stats.done or 0)
    downloading = int(stats.downloading or 0)
    failed = int(stats.failed or 0)
    queued = int(stats.queued or 0)

    if total == 0:
        new_status = "idle"
    elif done == total:
        new_status = "completed"
    elif downloading > 0:
        new_status = "downloading"
    elif queued > 0:
        new_status = "pending"
    elif failed > 0:
        new_status = "failed"
    else:
        new_status = "idle"

    album.download_status = new_status
    session.add(album)

    return new_status


def get_artist_status(session: Session, artist_id: str) -> dict:
    """
    Get comprehensive artist subscription status.
    
    Returns:
        {
            "has_subscription": bool,
            "mode": None | "light" | "full",
            "is_fully_followed": bool,
        }
    """
    subscription = get_artist_subscription(session, artist_id)
    
    return {
        "has_subscription": subscription is not None,
        "mode": subscription.mode if subscription else None,
        "is_fully_followed": subscription is not None and subscription.mode == "full",
    }


def get_monitored_artists_needing_sync(
    session: Session,
    sync_interval_hours: int = 6,
) -> list[Artist]:
    """
    Return Artist rows that have an enabled subscription and haven't been
    synced within the last `sync_interval_hours` hours.

    Used by the scheduler to decide which artists to re-sync.
    """
    from datetime import timedelta

    cutoff = now_utc() - timedelta(hours=sync_interval_hours)

    stmt = (
        select(Artist)
        .join(ArtistSubscription, ArtistSubscription.artist_id == Artist.id)
        .where(
            ArtistSubscription.enabled == True,
            ArtistSubscription.mode == "full",
            (ArtistSubscription.last_synced_at == None) | (ArtistSubscription.last_synced_at < cutoff),
        )
    )

    return list(session.execute(stmt).scalars().all())