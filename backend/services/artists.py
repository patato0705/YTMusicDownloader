# backend/services/artists.py
"""Artist rows: what YTMusic says about an artist, and its pictures."""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..downloader import cover as cover_mod
from ..models import Artist
from ..ytm_service import adapter as ytm_adapter
from ..ytm_service import normalizers as N
from . import folders
from . import recommendations as recommendations_svc

logger = logging.getLogger("services.artists")


def upsert_artist(
    session: Session,
    artist_id: str,
    name: Optional[str] = None,
    image_local: Optional[str] = None,
    banner_local: Optional[str] = None,
    description: Optional[str] = None,
) -> Artist:
    """
    Create or update an Artist row. Fields passed as None are left as they
    are on an existing row. Following is the subscriptions' business. Does
    not commit.
    """
    if not artist_id:
        raise ValueError("artist_id required")

    artist = session.get(Artist, artist_id)
    if artist is None:
        artist = Artist(id=artist_id, name=name or "")
        session.add(artist)
    elif name is not None:
        artist.name = name
    for field, value in (("image_local", image_local), ("banner_local", banner_local), ("description", description)):
        if value is not None:
            setattr(artist, field, value)
    return artist


# Square picture saved for the artist: about the height of YouTube Music's
# originals, so Google crops it rather than blowing it up
ARTIST_PICTURE_SIZE = 800


def ensure_artist_images(session: Session, artist: Artist, thumbnails: Optional[List[Any]]) -> Optional[str]:
    """
    Download the artist's pictures into its folder, from the thumbnails of its
    YouTube Music page (again at every sync, so a changed picture is mirrored):
      - folder.jpg: the picture cropped square, shown in the app (image_local)
        and used by Jellyfin as the artist's main image
      - backdrop.jpg: the page's wide banner (banner_local), Jellyfin's backdrop

    Both come from the same picture: Google crops the square from the
    original, which shows more than the banner (itself a crop of it).

    Returns the square picture's path, or None if it couldn't be saved.
    Does not commit.
    """
    banner_url = N.best_thumbnail(thumbnails)
    if not banner_url:
        logger.warning("No thumbnail URL found for artist %s", artist.id)
        return None
    picture_url = N.resize_thumbnail_url(banner_url, ARTIST_PICTURE_SIZE, crop=True)
    artist_folder = folders.artist_dir(session, artist)

    picture_path = artist_folder / "folder.jpg"
    picture_saved = cover_mod.download_image(picture_url, picture_path)
    if picture_saved:
        artist.image_local = str(picture_path)
    banner_path = artist_folder / "backdrop.jpg"
    if cover_mod.download_image(banner_url, banner_path):
        artist.banner_local = str(banner_path)

    logger.info("Saved pictures for artist %s in %s", artist.id, artist_folder)
    return str(picture_path) if picture_saved else None


def fetch_and_upsert_artist(session: Session, artist_id: str) -> Dict[str, Any]:
    """
    Fetch an artist from YTMusic and store its details and similar artists
    (for recommendations). Its albums are left to the caller, which gets
    them in the returned dict (adapter.get_artist's). Raises
    ytm_adapter.YTMusicUnavailable when it can't be read. Does not commit.
    """
    artist_data = ytm_adapter.get_artist(artist_id)
    upsert_artist(
        session,
        artist_id=artist_id,
        name=artist_data["name"],
        description=artist_data["description"],
    )
    recommendations_svc.store_related(session, artist_id, artist_data["related"])
    session.flush()
    logger.info("Fetched artist %s: %s", artist_id, artist_data["name"])
    return artist_data
