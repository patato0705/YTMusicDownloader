# backend/services/artists.py
"""
Artist entity CRUD operations only.
Business logic for fetching artist data from YTMusic lives here.
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..models import Artist
from ..ytm_service import adapter as ytm_adapter
from ..ytm_service import normalizers as N

logger = logging.getLogger("services.artists")


# ============================================================================
# ARTIST CRUD
# ============================================================================

def upsert_artist(
    session: Session,
    artist_id: str,
    name: Optional[str] = None,
    thumbnails: Optional[List[Any]] = None,
    image_local: Optional[str] = None,
) -> Artist:
    """
    Upsert an Artist row. `thumbnails` is expected to be the raw thumbnails list.
    Returns the Artist instance (not committed).
    """
    if not artist_id:
        raise ValueError("artist_id required")

    obj = session.get(Artist, str(artist_id))
    thumbs = thumbnails or []

    if obj is None:
        obj = Artist(
            id=str(artist_id),
            name=str(name) if name is not None else "",
            thumbnails=thumbs or None,
            image_local=str(image_local) if image_local else None,
            followed=False,
        )
        session.add(obj)
        logger.debug(f"Created new artist: {artist_id}")
    else:
        changed = False
        if name is not None and obj.name != name:
            obj.name = name
            changed = True
        if thumbs and obj.thumbnails != thumbs:
            obj.thumbnails = thumbs
            changed = True
        if image_local is not None and obj.image_local != image_local:
            obj.image_local = image_local
            changed = True
        if changed:
            session.add(obj)
            logger.debug(f"Updated artist: {artist_id}")

    return obj


def get_artist_from_db(session: Session, artist_id: str) -> Optional[Artist]:
    """Get artist from database by ID."""
    return session.get(Artist, artist_id)


# ============================================================================
# FETCH ARTIST FROM YTMUSIC
# ============================================================================

def fetch_and_upsert_artist(
    session: Session,
    artist_id: str,
) -> Dict[str, Any]:
    """
    Fetch artist data from YTMusic and upsert to database.
    Returns the artist data with albums and singles.
    
    Note: This does NOT upsert albums/tracks - use albums.fetch_and_upsert_albums_for_artist() for that.
    Note: Does NOT commit the session - caller controls transaction.
    """
    try:
        artist_data = ytm_adapter.get_artist(channel_id=artist_id)
    except Exception as e:
        logger.exception(f"Failed to fetch artist {artist_id} from YTMusic")
        raise RuntimeError(f"Failed to fetch artist from YTMusic: {e}")

    # Extract artist metadata
    name = artist_data.get("name")
    thumbnails = artist_data.get("thumbnails") or []
    description = artist_data.get("description")
    
    # Upsert artist (without albums/tracks)
    artist_obj = upsert_artist(
        session=session,
        artist_id=artist_id,
        name=name,
        thumbnails=thumbnails,
    )
    
    session.flush()
    
    logger.info(f"Fetched artist {artist_id}: {name}")
    
    return {
        "artist_id": artist_id,
        "name": name,
        "description": description,
        "thumbnails": thumbnails,
        "albums": artist_data.get("albums", []),
        "singles": artist_data.get("singles", []),
    }