# backend/services/artists.py
"""Artist rows: what YTMusic says about an artist, and its pictures."""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..downloader import cover as cover_mod
from ..models import Artist, UserChannel
from ..ytm_service import adapter as ytm_adapter
from ..ytm_service import normalizers as N
from . import folders
from . import recommendations as recommendations_svc
from . import subscriptions as subs_svc

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


def ensure_artist_images(
    session: Session, artist: Artist, thumbnails: Optional[List[Any]], picture: Optional[str]
) -> Optional[str]:
    """
    Download the artist's pictures into its folder, from its YouTube Music
    page (again at every sync, so a changed picture is mirrored):
      - folder.jpg: `picture` cropped square, shown in the app (image_local)
        and used by Jellyfin as the artist's main image
      - backdrop.jpg: the page's wide banner (`thumbnails`, banner_local),
        Jellyfin's backdrop

    For an artist both come from the same picture: Google crops the square
    from the original, which shows more than the banner (itself a crop of
    it). A YouTube user's channel has a picture of its own.

    Returns the square picture's path, or None if it couldn't be saved.
    Does not commit.
    """
    banner_url = N.best_thumbnail(thumbnails)
    if not banner_url and not picture:
        logger.warning("No thumbnail URL found for artist %s", artist.id)
        return None
    artist_folder = folders.artist_dir(session, artist)

    picture_path = artist_folder / "folder.jpg"
    picture_saved = bool(picture) and cover_mod.download_image(
        N.resize_thumbnail_url(picture, ARTIST_PICTURE_SIZE, crop=True), picture_path
    )
    if picture_saved:
        artist.image_local = str(picture_path)
    banner_path = artist_folder / "backdrop.jpg"
    if banner_url and cover_mod.download_image(banner_url, banner_path):
        artist.banner_local = str(banner_path)

    logger.info("Saved pictures for artist %s in %s", artist.id, artist_folder)
    return str(picture_path) if picture_saved else None


def fetch_and_upsert_artist(session: Session, artist_id: str) -> Dict[str, Any]:
    """
    Fetch an artist from YTMusic and store its details and similar artists
    (for recommendations). Its albums are left to the caller, which gets
    them in the returned dict (adapter.get_artist's). A YouTube user's
    channel ("channel" true) isn't an artist: nothing is stored, see
    drop_channel. Raises ytm_adapter.YTMusicUnavailable when it can't be
    read. Does not commit.
    """
    artist_data = ytm_adapter.get_artist(artist_id)
    if artist_data["channel"]:
        return artist_data
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


def drop_channel(session: Session, artist_id: str) -> None:
    """
    Take a YouTube user's channel (adapter.get_artist's "channel") back out
    of the library, where a follow put it before its page was read: its
    subscription, and its row unless it has albums (a channel has none).
    Everyone's like of it goes with the row. It's noted as a channel, so
    nothing follows it again. Does not commit.
    """
    note_channel(session, artist_id, True)
    subscription = subs_svc.get_artist_subscription(session, artist_id)
    if subscription is not None:
        session.delete(subscription)
    artist = session.get(Artist, artist_id)
    if artist is not None and not artist.albums:
        session.delete(artist)


def note_channel(session: Session, artist_id: str, channel: bool) -> None:
    """
    Record what an artist page just turned out to be: a YouTube user's
    channel (UserChannel, never followed), or an artist (no longer one,
    if it was). Does not commit.
    """
    known = session.get(UserChannel, artist_id)
    if channel and known is None:
        session.add(UserChannel(id=artist_id))
    elif not channel and known is not None:
        session.delete(known)
