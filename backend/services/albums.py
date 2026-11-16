# backend/services/albums.py
"""
Album rows: storing what YTMusic says about an album (its tracklist
included), its cover, and what follows an import.
"""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..downloader import cover as cover_mod, embed as embed_mod, nfo as nfo_mod
from ..jobs.jobqueue import cancel_download_jobs
from ..jobs.priorities import Origin
from ..models import Album, Artist, Track
from ..text_utils import fold
from ..time_utils import now_utc
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


# Covers are saved at the size of YouTube Music's album pages, whether their
# thumbnails come from one (an import) or from an artist page's cards (a sync)
ALBUM_COVER_SIZE = N.CARD_THUMBNAIL_SIZE


def ensure_album_cover(session: Session, album: Album, thumbnails: Optional[List[Any]]) -> bool:
    """
    Keep the album's cover on disk the picture YouTube Music shows, given
    its raw `thumbnails` (from the album's page or an artist page's card:
    the same picture, normalizers.image_id):
      - none on disk: saved as COVERS_DIR/<album id>.jpg (it moves into the
        album's folder as cover.jpg with its first track, downloader/core.py)
      - another picture than the one saved (Album.cover_id): it replaces
        the file where it is, folder or not
      - one saved before its picture was recorded: taken as the current one
    Returns whether a picture was saved: the album's files then embed it
    (embed_album_cover, once committed). Does not commit.
    """
    url = N.best_thumbnail(thumbnails)
    picture = N.image_id(url)
    on_disk = bool(album.image_local) and Path(album.image_local).exists()
    if on_disk and (not url or album.cover_id in (None, picture)):
        album.cover_id = album.cover_id or picture
        return False
    if not url:
        logger.warning("No thumbnail URL found for album %s", album.id)
        return False

    dest = Path(album.image_local) if on_disk else config.COVERS_DIR / f"{album.id}.jpg"
    if not cover_mod.download_image(N.resize_thumbnail_url(url, ALBUM_COVER_SIZE), dest, timeout=15):
        return False
    album.image_local = str(dest)
    album.cover_id = picture
    logger.info("%s cover of album %s: %s", "Replaced the" if on_disk else "Saved the", album.id, dest)
    return True


def embed_album_cover(session: Session, album_id: str) -> int:
    """Write the album's cover into the tags of its tracks on disk. Returns how many were written."""
    album = session.get(Album, album_id)
    if album is None or not album.image_local or not Path(album.image_local).is_file():
        return 0
    paths = session.scalars(
        select(Track.file_path).where(Track.album_id == album_id, Track.status == "done", Track.file_path.is_not(None))
    ).all()
    written = sum(embed_mod.set_cover(path, Path(album.image_local)) for path in paths)
    if written:
        logger.info("Embedded the new cover of album %s in %s files", album_id, written)
    return written


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

    Read again (an album refresh, subscriptions.queue_album_refreshes), the
    stored tracklist follows YouTube Music's: new tracks come in, changed
    ids are matched (_match_changed_ids), and tracks no longer listed get
    removed_at (their files stay).

    Returns {album_id, inserted_tracks, updated_tracks, removed_tracks,
    replaced_ids, retag, cover_changed}: retag lists (file path,
    {tag: value}) for the files on disk whose title, number, album title or
    year changed, for embed.set_tags once this is committed; cover_changed
    calls for embed_album_cover then.
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
    # Its tags as the files have them, if it's already stored: a change is
    # written to the files after the commit (fetch_and_upsert_album's "retag")
    known = session.get(Album, album_id)
    tagged_album = (known.title, known.year) if known else None
    album = upsert_album(
        session,
        album_id=album_id,
        title=album_data["title"],
        artist_id=artist_id,
        year=album_data["year"],
        album_type=album_data["type"],
        playlist_id=album_data["playlistId"],
    )
    album.last_synced_at = now_utc()
    album.last_error = None
    cover_changed = False
    try:
        cover_changed = ensure_album_cover(session, album, album_data["thumbnails"])
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

    # The tracklist as YouTube Music lists it now: (id, number, track data, title)
    listed: List[Tuple[str, int, Dict[str, Any], str]] = []
    replaced = 0
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
        listed.append((track_id, track_data.get("track_number") or idx + 1, track_data, title))

    stored = {t.id: t for t in session.query(Track).filter(Track.album_id == album_id).all()}
    unlisted = _match_changed_ids(session, listed, stored)

    # Stored tracks it no longer lists: kept (a file stays in the library)
    # but never downloaded again. An empty tracklist is YouTube Music
    # failing to list it, not every track gone.
    removed = 0
    if listed:
        now = now_utc()
        gone = [t for t in unlisted if t.removed_at is None]
        cancel_download_jobs(session, [t.id for t in gone if t.status == "queued"], reason="no longer on YouTube Music")
        for t in gone:
            t.removed_at = now
            if t.status in ("queued", "failed"):
                t.status = "available"
                t.last_error = None
            logger.info("Track %s (%s) of album %s is no longer on YouTube Music", t.id, t.title, album_id)
        removed = len(gone)

    inserted = updated = 0
    tag_changes: Dict[str, Dict[str, Any]] = {}
    for track_id, number, track_data, title in listed:
        # A known track keeps its status and file: a re-import mustn't reset
        # one that's queued or mid-download
        track = session.get(Track, track_id)
        is_new = track is None
        tagged = None if is_new else (track.title, track.track_number)
        track = upsert_track(
            session,
            track_id=track_id,
            track_number=number,
            title=title,
            duration_seconds=track_data.get("duration_seconds"),
            artists_list=[{"id": a.get("id"), "name": a.get("name")} for a in track_data.get("artists") or []],
            album_id=album_id,
            status="available" if is_new else None,
        )
        if track.removed_at is not None:
            logger.info("Track %s (%s) of album %s is back on YouTube Music", track_id, title, album_id)
            track.removed_at = None
        if is_new:
            inserted += 1
            continue
        updated += 1
        if tagged != (track.title, track.track_number):
            tag_changes[track_id] = {"title": track.title, "track_number": track.track_number}

    # The files' tags follow: the album's title and year on all of them,
    # a track's own title and number on its own
    if tagged_album is not None and tagged_album != (album.title, album.year):
        album_tags = {"album": album.title, "year": album.year}
        for track_id in stored:
            tag_changes[track_id] = {**album_tags, **tag_changes.get(track_id, {})}
    retag = [
        (t.file_path, tag_changes[t.id])
        for t in stored.values()
        if t.id in tag_changes and t.status == "done" and t.file_path
    ]

    session.flush()
    logger.info(
        "Album %s upserted: %s new, %s updated, %s no longer listed, %s IDs replaced",
        album_id, inserted, updated, removed, replaced,
    )
    return {
        "album_id": album_id,
        "inserted_tracks": inserted,
        "updated_tracks": updated,
        "removed_tracks": removed,
        "replaced_ids": replaced,
        "retag": retag,
        "cover_changed": cover_changed,
    }


def _match_changed_ids(
    session: Session,
    listed: List[Tuple[str, int, Dict[str, Any], str]],
    stored: Dict[str, Track],
) -> List[Track]:
    """
    YouTube Music sometimes gives a song of an album a new id: listed under
    an id the library doesn't know, while the stored track of the same
    title isn't listed any more. Such a pair is one track, not a removal
    and an addition:
      - on disk (or being downloaded): the stored track stays, under its
        id (`listed` is updated in place), its file being that song
      - otherwise: the stored track is deleted (its download cancelled) and
        the new id comes in as a new track, downloaded like any other

    Several stored tracks of the same title ("Interlude"): the one whose
    number is closest. Does not commit. Returns the stored tracks still not
    listed: those YouTube Music no longer has.
    """
    listed_ids = {track_id for track_id, *_ in listed}
    unlisted = [t for t in stored.values() if t.id not in listed_ids]
    for i, (track_id, number, track_data, title) in enumerate(listed):
        if not unlisted:
            break
        if track_id in stored or session.get(Track, track_id) is not None:
            continue
        same = [t for t in unlisted if fold(t.title) == fold(title)]
        if not same:
            continue
        old = min(same, key=lambda t: abs((t.track_number or 0) - number))
        unlisted.remove(old)
        if old.status in ("done", "downloading"):
            logger.info("Track %s of album %s is now listed as %s: kept under its id", old.id, old.album_id, track_id)
            listed[i] = (old.id, number, track_data, title)
        else:
            logger.info("Track %s of album %s is now listed as %s: replaced", old.id, old.album_id, track_id)
            cancel_download_jobs(session, [old.id], reason="YouTube Music changed the track's id")
            session.delete(old)
    return unlisted


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
