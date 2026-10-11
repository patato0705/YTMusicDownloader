# backend/services/artists.py

"""
Artist entity CRUD operations only.
Business logic for fetching artist data from YTMusic lives here.
"""
from __future__ import annotations
import logging
import shutil
from typing import Any, Dict, List, Optional
from pathlib import Path

import requests
from sqlalchemy.orm import Session

from ..models import Artist
from . import recommendations as recommendations_svc
from ..ytm_service import adapter as ytm_adapter
from ..ytm_service import normalizers as N
from .. import config
from ..downloader.core import safe_name

logger = logging.getLogger("services.artists")


# ============================================================================
# ARTIST CRUD
# ============================================================================

def upsert_artist(
    session: Session,
    artist_id: str,
    name: Optional[str] = None,
    image_local: Optional[str] = None,
    banner_local: Optional[str] = None,
    description: Optional[str] = None,
) -> Artist:
    """
    Upsert an Artist row.
    Returns the Artist instance (not committed).

    Note: Does NOT set followed status - use subscriptions for that.
    """
    if not artist_id:
        raise ValueError("artist_id required")

    obj = session.get(Artist, str(artist_id))

    if obj is None:
        obj = Artist(
            id=str(artist_id),
            name=str(name) if name is not None else "",
            image_local=str(image_local) if image_local else None,
            banner_local=str(banner_local) if banner_local else None,
            description=str(description) if description else None,
        )
        session.add(obj)
        logger.debug(f"Created new artist: {artist_id}")
    else:
        changed = False
        if name is not None and obj.name != name:
            obj.name = name
            changed = True
        if image_local is not None and obj.image_local != image_local:
            obj.image_local = image_local
            changed = True
        if banner_local is not None and obj.banner_local != banner_local:
            obj.banner_local = banner_local
            changed = True
        if description is not None and obj.description != description:
            obj.description = description
            changed = True
        if changed:
            session.add(obj)
            logger.debug(f"Updated artist: {artist_id}")

    return obj


def get_artist_from_db(session: Session, artist_id: str) -> Optional[Artist]:
    """Get artist from database by ID."""
    return session.get(Artist, artist_id)


# ============================================================================
# ARTIST IMAGES
# ============================================================================

# Square picture saved for the artist: about the height of YouTube Music's
# originals, so Google crops it rather than blowing it up
ARTIST_PICTURE_SIZE = 800


def _download_image(url: str, temp_path: Path, final_path: Path) -> bool:
    """Download url to final_path, through temp_path so a failed download never leaves half a file."""
    try:
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        temp_path.write_bytes(response.content)

        final_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(temp_path), str(final_path))
        try:
            final_path.chmod(0o644)
        except Exception as e:
            logger.debug(f"Failed to set permissions on {final_path}: {e}")
        return True
    except Exception as e:
        logger.error(f"Failed to download {url} to {final_path}: {e}")
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass
        return False


def ensure_artist_images(
    session: Session,
    artist_obj: Artist,
    thumbnails: Optional[List[Any]] = None,
) -> Optional[str]:
    """
    Download the artist's pictures into its folder, from the thumbnails of its
    YouTube Music page:
      - folder.jpg: the picture cropped square, shown in the app (image_local)
        and used by Jellyfin as the artist's main image
      - backdrop.jpg: the page's wide banner (banner_local), Jellyfin's backdrop

    Both come from the same picture: Google crops the square from the
    original, which shows more than the banner (itself a crop of it).

    Returns the square picture's path, or None if it couldn't be saved.
    """
    if not artist_obj:
        return None

    banner_url = N.pick_best_thumbnail_url(N.normalize_thumbnails(thumbnails or []))
    if not banner_url:
        logger.warning(f"No thumbnail URL found for artist {artist_obj.id}")
        return None
    picture_url = N.resize_thumbnail_url(banner_url, ARTIST_PICTURE_SIZE, crop=True)

    artist_folder = Path(str(config.MUSIC_DIR)) / safe_name(artist_obj.name or "Unknown Artist")
    covers_dir = Path(str(config.COVERS_DIR))

    picture_path = artist_folder / "folder.jpg"
    picture_saved = _download_image(picture_url, covers_dir / f"artist_{artist_obj.id}_folder.jpg", picture_path)
    if picture_saved:
        artist_obj.image_local = str(picture_path)

    banner_path = artist_folder / "backdrop.jpg"
    if _download_image(banner_url, covers_dir / f"artist_{artist_obj.id}_backdrop.jpg", banner_path):
        artist_obj.banner_local = str(banner_path)

    session.add(artist_obj)
    logger.info(f"Saved pictures for artist {artist_obj.id} in {artist_folder}")
    return str(picture_path) if picture_saved else None


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
    
    Also stores its similar artists, for recommendations.

    Note: This does NOT upsert albums/tracks - use albums.fetch_and_upsert_albums_for_artist() for that.
    Note: Does NOT set followed status - use subscriptions for that.
    Note: Does NOT commit the session - caller controls transaction.
    """
    # Raises ytm_adapter.YTMusicUnavailable when YouTube Music can't be read
    artist_data = ytm_adapter.get_artist(channel_id=artist_id)

    # Extract artist metadata
    name = artist_data.get("name")
    thumbnails = artist_data.get("thumbnails") or []
    description = artist_data.get("description")

    # Upsert artist (without albums/tracks)
    artist_obj = upsert_artist(
        session=session,
        artist_id=artist_id,
        name=name,
        description=description,
    )

    recommendations_svc.store_related(session, artist_id, artist_data.get("related") or [])

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