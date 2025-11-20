# backend/services/tracks.py
"""
Track entity CRUD operations and track-specific business logic.
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..models import Track

logger = logging.getLogger("services.tracks")


# ============================================================================
# TRACK CRUD
# ============================================================================

def upsert_track(
    session: Session,
    track_id: str,
    title: str,
    track_number: Optional[int],
    duration_seconds: Optional[int],
    artists_list: Optional[List[Dict[str, Optional[str]]]] = None,
    album_id: Optional[str] = None,
    status: str = "new",
    file_path: Optional[str] = None,
    artist_valid: bool = True,
    has_lyrics: bool = False,
    lyrics_local: Optional[str] = None,
) -> Track:
    """
    Upsert a Track row. `artists_list` is a list of dicts {id, name}.
    Returns the Track instance (not committed).
    """
    if not track_id:
        raise ValueError("track_id required")

    obj = session.get(Track, str(track_id))

    if obj is None:
        obj = Track(
            id=str(track_id),
            title=str(title) if title is not None else "",
            duration=int(duration_seconds) if duration_seconds is not None else None,
            artists=artists_list or None,
            album_id=str(album_id) if album_id is not None else None,
            track_number=int(track_number) if track_number is not None else None,
            has_lyrics=bool(has_lyrics),
            lyrics_local=str(lyrics_local) if lyrics_local else None,
            file_path=str(file_path) if file_path is not None else None,
            status=str(status),
            artist_valid=bool(artist_valid),
        )
        session.add(obj)
        logger.debug(f"Created new track: {track_id}")
    else:
        changed = False
        if title is not None and obj.title != title:
            obj.title = title
            changed = True
        if duration_seconds is not None and obj.duration != duration_seconds:
            obj.duration = int(duration_seconds)
            changed = True
        if artists_list is not None and obj.artists != artists_list:
            obj.artists = artists_list
            changed = True
        if album_id is not None and obj.album_id != album_id:
            obj.album_id = album_id
            changed = True
        if track_number is not None and obj.track_number != track_number:
            obj.track_number = track_number
            changed = True
        if file_path is not None and obj.file_path != file_path:
            obj.file_path = file_path
            changed = True
        if status is not None and obj.status != status:
            obj.status = status
            changed = True
        if obj.artist_valid != bool(artist_valid):
            obj.artist_valid = bool(artist_valid)
            changed = True
        if obj.has_lyrics != bool(has_lyrics):
            obj.has_lyrics = bool(has_lyrics)
            changed = True
        if lyrics_local is not None and obj.lyrics_local != lyrics_local:
            obj.lyrics_local = lyrics_local
            changed = True
        if changed:
            session.add(obj)
            logger.debug(f"Updated track: {track_id}")

    return obj


def get_track_from_db(session: Session, track_id: str) -> Optional[Track]:
    """Get track from database by ID."""
    return session.get(Track, track_id)


def list_tracks_for_album_from_db(
    session: Session,
    album_id: str,
) -> List[Dict[str, Any]]:
    """
    Query DB for tracks with album_id. Returns a list of track dicts.
    """
    result: List[Dict[str, Any]] = []
    try:
        query = (
            session.query(Track)
            .filter(Track.album_id == album_id)
            .order_by(Track.id.asc())  # TODO: Add track_number field and order by that
        )
        
        for track in query.all():
            result.append(track.to_dict())
    except Exception as e:
        logger.exception(f"list_tracks_for_album_from_db failed for {album_id}: {e}")
    
    return result


def update_track_status(
    session: Session,
    track_id: str,
    status: str,
    file_path: Optional[str] = None,
) -> bool:
    """
    Update track status and optionally file_path.
    
    Args:
        session: SQLAlchemy session
        track_id: Track ID
        status: New status ("new", "downloading", "done", "failed", etc.)
        file_path: Optional file path to set
    
    Returns:
        True if track was found and updated, False otherwise
    """
    try:
        track = session.get(Track, track_id)
        if not track:
            logger.warning(f"Track {track_id} not found for status update")
            return False
        
        track.status = status
        if file_path is not None:
            track.file_path = file_path
        
        session.add(track)
        logger.debug(f"Updated track {track_id} status to {status}")
        return True
    except Exception as e:
        logger.exception(f"Failed to update track status for {track_id}: {e}")
        return False


def get_tracks_by_status(
    session: Session,
    status: str,
    limit: Optional[int] = None,
) -> List[Track]:
    """
    Get tracks by status.
    
    Args:
        session: SQLAlchemy session
        status: Status to filter by ("new", "downloading", "done", "failed")
        limit: Optional limit on number of results
    
    Returns:
        List of Track instances
    """
    try:
        query = session.query(Track).filter(Track.status == status)
        
        if limit is not None:
            query = query.limit(limit)
        
        return list(query.all())
    except Exception as e:
        logger.exception(f"Failed to get tracks by status {status}: {e}")
        return []


def get_pending_download_tracks(
    session: Session,
    limit: Optional[int] = None,
) -> List[Track]:
    """
    Get tracks that need to be downloaded (status = "new" or "failed").
    
    Args:
        session: SQLAlchemy session
        limit: Optional limit on number of results
    
    Returns:
        List of Track instances
    """
    try:
        query = session.query(Track).filter(Track.status.in_(["new", "failed"]))
        
        if limit is not None:
            query = query.limit(limit)
        
        return list(query.all())
    except Exception as e:
        logger.exception(f"Failed to get pending download tracks: {e}")
        return []