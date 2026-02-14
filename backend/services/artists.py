# backend/services/artists.py
"""
Artist entity CRUD operations only.
Business logic for fetching artist data from YTMusic lives here.
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional
from pathlib import Path

import requests
from sqlalchemy.orm import Session

from ..models import Artist
from ..ytm_service import adapter as ytm_adapter
from ..ytm_service import normalizers as N
from .. import config

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
# ARTIST BANNER MANAGEMENT
# ============================================================================

def ensure_artist_banner(
    session: Session,
    artist_obj: Artist,
    thumbnails: Optional[List[Any]] = None,
) -> Optional[str]:
    """
    Ensure the artist has a local banner image. Downloads the best thumbnail if needed.
    
    Args:
        session: SQLAlchemy session
        artist_obj: Artist model instance (should be attached to session)
        thumbnails: raw thumbnails (list[dict]) - optional, prefer these over artist_obj.thumbnails
    
    Returns:
        Path to the saved banner (string) or None if failed
    """
    if not artist_obj:
        return None

    # Get artist name for folder path
    artist_name = artist_obj.name or "Unknown Artist"
    safe_artist_name = _safe_name(artist_name)
    
    # Artist folder: /data/{artist}/
    artist_folder = Path(str(config.MUSIC_DIR)) / safe_artist_name
    
    # Final banner path: /data/{artist}/backdrop.jpg
    final_banner_path = artist_folder / "backdrop.jpg"

    # Pick thumbnails list to use
    thumbs_src = thumbnails or artist_obj.thumbnails or []
    
    logger.debug(f"Artist {artist_obj.id} has {len(thumbs_src)} thumbnails")
    
    # Normalize and pick best thumbnail
    norm_thumbs = N.normalize_thumbnails(thumbs_src)
    logger.debug(f"Normalized to {len(norm_thumbs) if norm_thumbs else 0} thumbnails")
    
    best_url = N.pick_best_thumbnail_url(norm_thumbs) if norm_thumbs else None
    if not best_url:
        logger.warning(f"No thumbnail URL found for artist {artist_obj.id}")
        return None
    
    logger.info(f"Selected best thumbnail URL: {best_url[:100]}..." if len(best_url) > 100 else f"Selected best thumbnail URL: {best_url}")

    # Download to temp location first
    temp_banner_path = Path(str(config.COVERS_DIR)) / f"artist_{artist_obj.id}_backdrop.jpg"
    
    try:
        # Ensure temp directory exists
        Path(str(config.COVERS_DIR)).mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Downloading banner for artist {artist_obj.id} from {best_url}")
        response = requests.get(best_url, timeout=30)
        response.raise_for_status()
        
        # Save to temp location
        temp_banner_path.write_bytes(response.content)
        logger.debug(f"Downloaded banner to temp: {temp_banner_path}")
        
        # Create artist folder if it doesn't exist
        artist_folder.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Ensured artist folder exists: {artist_folder}")
        
        # Move to final location
        if final_banner_path.exists():
            # Backup old banner before replacing
            try:
                final_banner_path.unlink()
                logger.debug(f"Removed old banner: {final_banner_path}")
            except Exception as e:
                logger.warning(f"Failed to remove old banner: {e}")
        
        # Move temp file to final location
        import shutil
        shutil.move(str(temp_banner_path), str(final_banner_path))
        logger.info(f"Moved banner to: {final_banner_path}")
        
        # Set permissions
        try:
            final_banner_path.chmod(0o644)
        except Exception as e:
            logger.debug(f"Failed to set banner permissions: {e}")
        
        # Update database
        artist_obj.image_local = str(final_banner_path)
        session.add(artist_obj)
        
        return str(final_banner_path)
        
    except requests.RequestException as e:
        logger.error(f"Failed to download banner for artist {artist_obj.id}: {e}")
        # Clean up temp file if it exists
        if temp_banner_path.exists():
            try:
                temp_banner_path.unlink()
            except Exception:
                pass
        return None
    except Exception as e:
        logger.exception(f"Unexpected error ensuring banner for artist {artist_obj.id}: {e}")
        # Clean up temp file if it exists
        if temp_banner_path.exists():
            try:
                temp_banner_path.unlink()
            except Exception:
                pass
        return None


def _safe_name(s: Optional[str]) -> str:
    """
    Convert a string to a safe filename/directory name.
    Removes or replaces problematic characters.
    """
    if not s:
        return "Unknown"
    return "".join(c for c in s if c.isalnum() or c in " .-_()").strip() or "Unknown"


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