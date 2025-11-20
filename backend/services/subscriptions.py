# backend/services/subscriptions.py
from __future__ import annotations
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import select

from . import normalizers as N

from ..models import ArtistSubscription, AlbumSubscription, Artist, Album
from ..time_utils import now_utc

logger = logging.getLogger("services.subscriptions")


def subscribe_to_artist(
    session: Session,
    artist_id: str,
    mode: str = "full",
    sync_interval_hours: Optional[int] = 24,
) -> ArtistSubscription:
    """
    Create or update an artist subscription.
    mode: "full" = download all albums, "monitor" = track but don't download
    """
    # Check if subscription already exists
    stmt = select(ArtistSubscription).where(ArtistSubscription.artist_id == artist_id)
    existing = session.execute(stmt).scalar_one_or_none()
    
    if existing:
        # Update existing subscription
        existing.enabled = True
        existing.mode = mode
        existing.sync_interval_hours = sync_interval_hours
        session.add(existing)
        logger.info(f"Updated artist subscription for {artist_id}")
        return existing
    
    # Create new subscription
    subscription = ArtistSubscription(
        artist_id=artist_id,
        mode=mode,
        enabled=True,
        sync_interval_hours=sync_interval_hours,
        created_at=now_utc(),
    )
    session.add(subscription)
    logger.info(f"Created artist subscription for {artist_id}")
    return subscription


def unsubscribe_from_artist(session: Session, artist_id: str) -> bool:
    """
    Disable artist subscription (soft delete).
    Returns True if subscription was found and disabled.
    """
    stmt = select(ArtistSubscription).where(ArtistSubscription.artist_id == artist_id)
    subscription = session.execute(stmt).scalar_one_or_none()
    
    if not subscription:
        return False
    
    subscription.enabled = False
    session.add(subscription)
    logger.info(f"Disabled artist subscription for {artist_id}")
    return True


def subscribe_to_album(
    session: Session,
    album_id: str,
    artist_id: Optional[str] = None,
    mode: str = "download",
) -> AlbumSubscription:
    """
    Create or update an album subscription.
    mode: "download" = download all tracks, "monitor" = track but don't download
    """
    # Check if subscription already exists
    stmt = select(AlbumSubscription).where(AlbumSubscription.album_id == album_id)
    existing = session.execute(stmt).scalar_one_or_none()
    
    if existing:
        # Update existing subscription
        existing.mode = mode
        if artist_id:
            existing.artist_id = artist_id
        session.add(existing)
        logger.info(f"Updated album subscription for {album_id}")
        return existing
    
    # Create new subscription
    subscription = AlbumSubscription(
        album_id=album_id,
        artist_id=artist_id,
        mode=mode,
        created_at=now_utc(),
        download_status="pending",
    )
    session.add(subscription)
    logger.info(f"Created album subscription for {album_id}")
    return subscription


def unsubscribe_from_album(session: Session, album_id: str) -> bool:
    """
    Delete album subscription.
    Returns True if subscription was found and deleted.
    """
    stmt = select(AlbumSubscription).where(AlbumSubscription.album_id == album_id)
    subscription = session.execute(stmt).scalar_one_or_none()
    
    if not subscription:
        return False
    
    session.delete(subscription)
    logger.info(f"Deleted album subscription for {album_id}")
    return True


def get_artist_subscription(session: Session, artist_id: str) -> Optional[ArtistSubscription]:
    """Get artist subscription if it exists."""
    stmt = select(ArtistSubscription).where(ArtistSubscription.artist_id == artist_id)
    return session.execute(stmt).scalar_one_or_none()


def get_album_subscription(session: Session, album_id: str) -> Optional[AlbumSubscription]:
    """Get album subscription if it exists."""
    stmt = select(AlbumSubscription).where(AlbumSubscription.album_id == album_id)
    return session.execute(stmt).scalar_one_or_none()


def list_active_artist_subscriptions(session: Session) -> List[ArtistSubscription]:
    """Get all enabled artist subscriptions."""
    stmt = select(ArtistSubscription).where(ArtistSubscription.enabled == True)
    return list(session.execute(stmt).scalars().all())


def list_pending_album_downloads(session: Session) -> List[AlbumSubscription]:
    """Get all album subscriptions that need downloading."""
    stmt = select(AlbumSubscription).where(
        AlbumSubscription.download_status.in_(["pending", "failed"])
    )
    return list(session.execute(stmt).scalars().all())


def get_due_album_subscriptions(session: Session) -> List[AlbumSubscription]:
    """
    Get album subscriptions that are due for sync/download.
    Returns subscriptions with download_status in ('pending', 'failed').
    This is called by the scheduler.
    """
    return list_pending_album_downloads(session)


def get_monitored_artists_needing_sync(
    session: Session,
    sync_interval_hours: int = 24
) -> List[Artist]:
    """
    Get artists that are followed and need syncing.
    An artist needs syncing if:
    - artist.followed = True
    - Either: artist_subscription doesn't exist, OR last_synced_at is older than sync_interval_hours
    """
    from sqlalchemy import select, or_
    from datetime import timedelta
    from ..models import Artist
    
    # Calculate cutoff time
    cutoff = now_utc() - timedelta(hours=sync_interval_hours)
    
    # Get all followed artists
    stmt = select(Artist).where(Artist.followed == True)
    followed_artists = list(session.execute(stmt).scalars().all())
    
    due_artists = []
    for artist in followed_artists:
        # Check if subscription exists and when it was last synced
        sub = get_artist_subscription(session, artist.id)
        
        if not sub:
            # No subscription but followed - needs sync
            due_artists.append(artist)
        elif not sub.last_synced_at or sub.last_synced_at < cutoff:
            # Subscription exists but hasn't been synced recently
            due_artists.append(artist)
    
    return due_artists


def mark_artist_synced(
    session: Session,
    artist_id: str,
    error: Optional[str] = None
) -> None:
    """Update last_synced_at timestamp for artist subscription."""
    subscription = get_artist_subscription(session, artist_id)
    if subscription:
        subscription.last_synced_at = now_utc()
        if error:
            subscription.last_error = error
        else:
            subscription.last_error = None
        session.add(subscription)


def mark_album_download_status(
    session: Session,
    album_id: str,
    status: str,
    error: Optional[str] = None
) -> None:
    """Update download status for album subscription."""
    subscription = get_album_subscription(session, album_id)
    if subscription:
        subscription.download_status = status
        subscription.last_synced_at = now_utc()
        if error:
            subscription.last_error = error
        else:
            subscription.last_error = None
        session.add(subscription)

def check_and_update_album_download_status(
    session: Session,
    album_id: str,
) -> str:
    """
    Check all tracks for an album and update AlbumSubscription.download_status.
    
    Returns the new status:
    - "idle": No subscription found
    - "pending": Some tracks not downloaded
    - "downloading": Some tracks actively downloading
    - "completed": All tracks done
    - "failed": All tracks failed
    """
    from ..models import Track
    
    # Get subscription
    subscription = get_album_subscription(session, album_id)
    if not subscription:
        return "idle"
    
    # Get all tracks for album
    tracks = session.query(Track).filter(Track.album_id == album_id).all()
    
    if not tracks:
        # No tracks yet
        subscription.download_status = "pending"
        session.add(subscription)
        return "pending"
    
    # Count track statuses
    status_counts = {}
    for track in tracks:
        status = track.status or "new"
        status_counts[status] = status_counts.get(status, 0) + 1
    
    total = len(tracks)
    done_count = status_counts.get("done", 0)
    downloading_count = status_counts.get("downloading", 0)
    failed_count = status_counts.get("failed", 0)
    new_count = status_counts.get("new", 0)
    
    # Determine overall status
    if done_count == total:
        new_status = "completed"
    elif done_count > 0 and (new_count + failed_count) == 0:
        new_status = "completed"  # Some might be in other states but main ones are done
    elif downloading_count > 0:
        new_status = "downloading"
    elif failed_count == total:
        new_status = "failed"
    elif failed_count > 0 or new_count > 0:
        new_status = "pending"
    else:
        new_status = "completed"
    
    # Update subscription
    subscription.download_status = new_status
    subscription.last_synced_at = now_utc()
    session.add(subscription)
    
    logger.debug(
        f"Album {album_id} download status: {new_status} "
        f"(done={done_count}/{total}, downloading={downloading_count}, failed={failed_count})"
    )
    
    return new_status