# backend/services/albums.py
"""
Album rows: storing what YTMusic says about an album (its tracklist
included), its cover, and what follows an import.
"""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..downloader import cover as cover_mod, nfo as nfo_mod
from ..jobs.priorities import Origin
from ..models import Album, Artist, Track
from ..ytm_service import adapter as ytm_adapter
from ..ytm_service import normalizers as N
from . import folders

logger = logging.getLogger("services.albums")


class ArtistDeleted(Exception):
    """The artist an album was being imported for is no longer in the library."""


def upsert_album(
    session: Session,
    album_id: str,
    title: Optional[str],
    artist_id: Optional[str] = None,
    image_local: Optional[str] = None,
    year: Optional[str] = None,
    album_type: Optional[str] = None,
    playlist_id: Optional[str] = None,
) -> Album:
    """
    Create or update an Album row. Fields passed as None are left as they
    are on an existing row. album_type: "Album", "Single", "EP"... Does not commit.
    """
    if not album_id:
        raise ValueError("album_id required")

    album = session.get(Album, album_id)
    if album is None:
        album = Album(id=album_id, title=title or "", type=album_type or "Album")
        session.add(album)
    elif title is not None:
        album.title = title
    for field, value in (
        ("artist_id", artist_id),
        ("image_local", image_local),
        ("year", str(year) if year is not None else None),
        ("type", album_type),
        ("playlist_id", playlist_id),
    ):
        if value is not None:
            setattr(album, field, value)
    return album


def get_album_from_db(session: Session, album_id: str) -> Optional[Dict[str, Any]]:
    """An album as the album endpoint returns it, with its tracks in order; None if not in the DB."""
    album = session.get(Album, album_id)
    if not album:
        return None
    tracks = (
        session.query(Track)
        .filter(Track.album_id == album_id)
        .order_by(Track.track_number.asc().nulls_last(), Track.id.asc())
        .all()
    )
    return {
        "id": album.id,
        "title": album.title,
        "artist": {"id": album.artist.id, "name": album.artist.name} if album.artist else None,
        "year": album.year,
        "type": album.type or "Album",
        "thumbnail": album.image_local,
        "genres": album.genres or [],
        "mode": album.mode,
        "tracks": [t.to_dict() for t in tracks],
    }


def list_albums_for_artist_from_db(session: Session, artist_id: str) -> List[Dict[str, Any]]:
    """The artist's albums in the DB, newest first, as the artist endpoint lists them."""
    albums = (
        session.query(Album)
        .filter(Album.artist_id == artist_id)
        .order_by(Album.year.desc().nullslast(), Album.title.asc())
        .all()
    )
    return [
        {
            "id": album.id,
            "title": album.title,
            "thumbnail": album.image_local,
            "year": album.year,
            "type": album.type or "Album",
            "mode": album.mode,
            "download_status": album.download_status,
        }
        for album in albums
    ]


def ensure_album_cover(session: Session, album: Album, thumbnails: Optional[List[Any]]) -> Optional[str]:
    """
    Make sure the album has a cover on disk: the one it has, or the best of
    `thumbnails` (raw, from the API) saved as COVERS_DIR/<album id>.jpg.
    Returns its path, or None when there's none. Does not commit.
    """
    if album.image_local and Path(album.image_local).exists():
        return album.image_local

    url = N.best_thumbnail(thumbnails)
    if not url:
        logger.warning("No thumbnail URL found for album %s", album.id)
        return None
    dest = config.COVERS_DIR / f"{album.id}.jpg"
    if not cover_mod.download_image(url, dest, timeout=15):
        return None
    album.image_local = str(dest)
    logger.info("Saved cover for album %s: %s", album.id, dest)
    return str(dest)


def list_artist_releases(artist_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The albums then the singles of artists.fetch_and_upsert_artist's result, as {id, title, type, year, thumbnails}."""
    return [
        {
            "id": item["id"],
            "title": item.get("title") or "",
            "type": item.get("type") or default_type,
            "year": item.get("year"),
            "thumbnails": item.get("thumbnails") or [],
        }
        for key, default_type in (("albums", "Album"), ("singles", "Single"))
        for item in artist_data.get(key) or []
        if item.get("id")
    ]


def fetch_and_upsert_album(
    session: Session,
    browse_id: str,
    artist_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fetch an album from YTMusic and store it with its tracks (and its cover,
    if it has none yet). Raises ytm_adapter.YTMusicUnavailable when it can't
    be read, ArtistDeleted when `artist_id` was deleted from the library
    while it was being fetched. Does not commit.

    The album's audio playlist is fetched too: its video ids are the audio
    versions of the tracks, which the album page itself sometimes lists as
    music videos.

    Returns {album_id, inserted_tracks, updated_tracks, replaced_ids}.
    """
    from .artists import upsert_artist
    from .tracks import upsert_track

    album_data = ytm_adapter.get_album(browse_id=browse_id)
    album_id = album_data["id"]
    tracks = album_data["tracks"]

    # Deleted from the library meanwhile (its albums with it): storing the
    # album now would bring the artist back. Read from the DB, not the
    # session's identity map, which may still hold it.
    if artist_id and session.execute(select(Artist.id).where(Artist.id == artist_id)).first() is None:
        raise ArtistDeleted(artist_id)
    # The artist from the album itself when not given, with its row: an album
    # pointing at an artist the DB doesn't know shows up with no artist
    # anywhere in the library. The album page only names a new artist: the
    # artist page can spell it differently ("CG5" / "Cg5") and its name wins.
    if not artist_id and album_data["artists"]:
        first = album_data["artists"][0]
        artist_id = first.get("id")
        if artist_id and session.get(Artist, artist_id) is None:
            upsert_artist(session, artist_id=artist_id, name=first.get("name"))

    logger.info("Fetched album %s: %s (%s tracks)", album_id, album_data["title"], len(tracks))
    album = upsert_album(
        session,
        album_id=album_id,
        title=album_data["title"],
        artist_id=artist_id,
        year=album_data["year"],
        album_type=album_data["type"],
        playlist_id=album_data["playlistId"],
    )
    try:
        ensure_album_cover(session, album, album_data["thumbnails"])
    except Exception:
        logger.exception("ensure_album_cover failed for %s", album_id)

    # Audio ids from the album's playlist, by position
    audio_ids: Dict[int, Dict[str, Any]] = {}
    if album_data["playlistId"]:
        try:
            playlist_tracks = ytm_adapter.get_playlist(album_data["playlistId"])["tracks"]
            for idx, pl_track in enumerate(playlist_tracks):
                if pl_track.get("id"):
                    audio_ids[idx] = {"id": pl_track["id"], "title": (pl_track.get("title") or "").lower().strip()}
        except Exception as e:
            logger.warning("Failed to fetch playlist %s: %s", album_data["playlistId"], e)

    inserted = updated = replaced = 0
    for idx, track_data in enumerate(tracks):
        video_id = track_data.get("id")
        if not video_id:
            continue
        title = track_data.get("title") or "Unknown Track"

        # The playlist's audio id when its title matches the album's track
        track_id = video_id
        audio = audio_ids.get(idx)
        if audio and audio["id"] != video_id:
            album_title = title.lower().strip()
            playlist_title = audio["title"]
            if (
                album_title == playlist_title
                or album_title in playlist_title
                or playlist_title in album_title
                or album_title.split("(")[0].strip() == playlist_title.split("(")[0].strip()
            ):
                logger.info("Using audio ID for '%s': %s -> %s", title, video_id, audio["id"])
                track_id = audio["id"]
                replaced += 1

        # A known track keeps its status and file: a re-import mustn't reset
        # one that's queued or mid-download
        is_new = session.get(Track, track_id) is None
        upsert_track(
            session,
            track_id=track_id,
            track_number=track_data.get("track_number") or idx + 1,
            title=title,
            duration_seconds=track_data.get("duration_seconds"),
            artists_list=[{"id": a.get("id"), "name": a.get("name")} for a in track_data.get("artists") or []],
            album_id=album_id,
            status="available" if is_new else None,
        )
        if is_new:
            inserted += 1
        else:
            updated += 1

    session.flush()
    logger.info("Album %s upserted: %s new, %s updated, %s IDs replaced", album_id, inserted, updated, replaced)
    return {
        "album_id": album_id,
        "inserted_tracks": inserted,
        "updated_tracks": updated,
        "replaced_ids": replaced,
    }


def complete_import(session: Session, album_id: str, *, origin: Origin) -> int:
    """
    What follows storing an album's tracklist: its album.nfo, the download
    of every track not on disk (download-mode albums), and a genre lookup
    for its artist if one is due. Commits. Returns the downloads queued.
    """
    from . import genres as genres_svc
    from . import tracks as tracks_svc

    album = session.get(Album, album_id)
    nfo_mod.write_album_nfo(album, album.artist, folders.album_dir(session, album))
    queued = 0
    if album.mode == "download":
        queued = tracks_svc.queue_album_downloads(session, album_id, origin=origin)
    if album.artist_id:
        genres_svc.queue_lookup(session, album.artist_id, origin=origin)
    session.commit()
    return queued
