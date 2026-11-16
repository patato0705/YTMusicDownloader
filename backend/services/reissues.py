# backend/services/reissues.py
"""
Albums YouTube Music reissues under a new id, or stops serving.

An artist page lists the artist's releases (Album.on_artist_page records
whether it did at its last sync). Not every album is on it, so one missing
says nothing alone; one that was listed and no longer is:
  - was replaced, when a release newly listed has the same tracks (most
    of the old ones on the new one, and most of the new ones on the old):
    the library album moves to the new id (adopt), files, folder and
    settings kept, and its next import brings the tracklist up to date
    (albums.fetch_and_upsert_album: same-title tracks keep their files,
    new ones are downloaded, missing ones marked removed). A new title
    ("... (Deluxe Edition)") is no obstacle: it's what YouTube Music serves
    in the old one's place.
  - was removed, when nothing replaces it and its page no longer opens:
    marked removed (Album.removed_at), files kept, nothing more downloaded.
  - is otherwise just no longer listed: its page still opens.
Two releases YouTube Music both lists stay two albums.

The artist syncs (follow_listing) and the albums downloaded by hand or by
a playlist scan before their artist's sync saw the new id (replaced_by)
both go through here.
"""
from __future__ import annotations
import logging
from typing import Any, Dict, Iterable, List, Optional, Set

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from ..jobs.jobqueue import cancel_download_jobs
from ..models import Album, Exclusion, PlaylistEntry, Track, VideoSong
from ..text_utils import fold
from ..time_utils import now_utc
from ..ytm_service import adapter as ytm_adapter

logger = logging.getLogger("services.reissues")

# Share of the old album's tracks found on the new one, and of the new
# one's found on the old one: a deluxe edition passes (12 of 12, 12 of 18),
# a single dropped while an album with its song came out doesn't (1 of 15)
OLD_SHARE = 0.8
NEW_SHARE = 0.5


def _titles(tracks: Iterable[Any]) -> Set[str]:
    return {fold(t.get("title") if isinstance(t, dict) else t) for t in tracks} - {""}


def _library_titles(session: Session, album_id: str) -> Set[str]:
    """The album's tracks still listed, by title."""
    return _titles(session.scalars(
        select(Track.title).where(Track.album_id == album_id, Track.removed_at.is_(None))
    ))


def _shared(old: Set[str], new: Set[str]) -> int:
    """How many tracks the two have in common, 0 unless enough to be one album."""
    if not old or not new:
        return 0
    common = len(old & new)
    return common if common / len(old) >= OLD_SHARE and common / len(new) >= NEW_SHARE else 0


def _match(old: Album, old_titles: Optional[Set[str]], new_title: Optional[str], new_titles: Set[str]) -> int:
    """
    How strongly a release matches an album (0: not the same). With no
    tracklist to compare (not downloaded, and its page gone: a deleted,
    excluded album, say), the same title has to do, so its exclusion
    follows it to the new id.
    """
    if old_titles:
        return _shared(old_titles, new_titles)
    return 1 if fold(old.title) and fold(old.title) == fold(new_title) else 0


def _page_titles(album_id: str) -> Optional[Set[str]]:
    """The album page's tracks, by title; None when it no longer opens."""
    try:
        return _titles(ytm_adapter.get_album(browse_id=album_id)["tracks"])
    except ytm_adapter.YTMusicUnavailable:
        return None


def adopt(session: Session, old: Album, new_id: str, release: Dict[str, Any]) -> Album:
    """
    Move a library album to the id YouTube Music now serves it under: a new
    row with its title, type and year from `release` (the new one's card or
    page), everything else carried over, and everything that pointed at the
    old id (tracks, playlist songs, its exclusion) pointing at the new one.
    The old row goes. Its next import (last_synced_at cleared) brings its
    tracklist and cover up to date. Does not commit.
    """
    old_id, folder = old.id, old.folder
    new = Album(
        id=new_id,
        title=release.get("title") or old.title,
        type=release.get("type") or old.type,
        artist_id=old.artist_id,
        year=str(release["year"]) if release.get("year") else old.year,
        image_local=old.image_local,
        cover_id=old.cover_id,
        genres=old.genres,
        genres_checked_at=old.genres_checked_at,
        mode=old.mode,
        download_status=old.download_status,
        on_artist_page=True,
        created_at=old.created_at,
    )
    session.add(new)
    session.flush()
    for model, column in ((Track, Track.album_id), (PlaylistEntry, PlaylistEntry.album_id), (VideoSong, VideoSong.album_id)):
        session.execute(update(model).where(column == old_id).values(album_id=new_id))
    session.execute(
        update(Exclusion).where(Exclusion.kind == "album", Exclusion.item_id == old_id).values(item_id=new_id)
    )
    # Not through the ORM: its cascade would take the tracks the old row
    # still holds in the session along with it
    session.expunge(old)
    session.execute(delete(Album).where(Album.id == old_id))
    new.folder = folder
    session.flush()
    logger.info("Album %s (%s) is now %s (%s) on YouTube Music: moved", old_id, old.title, new_id, new.title)
    return new


def mark_removed(session: Session, album: Album) -> None:
    """
    YouTube Music no longer serves the album: marked, its waiting downloads
    cancelled (they would fail). Its files stay. Does not commit.
    """
    if album.removed_at is None:
        album.removed_at = now_utc()
        logger.info("Album %s (%s) is no longer on YouTube Music", album.id, album.title)
    tracks = session.scalars(select(Track).where(Track.album_id == album.id, Track.status == "queued")).all()
    cancel_download_jobs(session, [t.id for t in tracks], reason="album no longer on YouTube Music")
    for track in tracks:
        track.status = "available"
        track.last_error = None


def follow_listing(session: Session, artist_id: str, releases: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    At an artist sync, with its page's releases (albums.list_artist_releases):
    record which of its albums the page lists, and settle those it no longer
    lists (see the top of this file). Releases taken over by an album
    moved to them are no longer new to the caller. Does not commit.
    Returns {"replaced", "removed"}.
    """
    listed = {r["id"] for r in releases}
    albums = session.scalars(select(Album).where(Album.artist_id == artist_id)).all()
    if not listed and any(a.on_artist_page for a in albums):
        # A page without releases is YouTube Music failing to list them
        logger.warning("Artist %s's page lists no releases: its albums' listing left as it was", artist_id)
        return {"replaced": 0, "removed": 0}

    dropped = [a for a in albums if a.on_artist_page and a.id not in listed]
    for album in albums:
        if album.id in listed:
            album.on_artist_page = True
    if not dropped:
        return {"replaced": 0, "removed": 0}

    arrivals = [r for r in releases if session.get(Album, r["id"]) is None]
    arrival_titles = {r["id"]: _page_titles(r["id"]) for r in arrivals}
    old_pages: Dict[str, Optional[Set[str]]] = {}
    replaced = removed = 0
    for old in dropped:
        old_titles = _library_titles(session, old.id)
        if not old_titles:
            # Not downloaded: its tracks are on its page, if it still opens
            old_pages[old.id] = old_titles = _page_titles(old.id)
        best, best_shared = None, 0
        for release in arrivals:
            new_titles = arrival_titles.get(release["id"])
            if new_titles is None:
                continue
            shared = _match(old, old_titles, release.get("title"), new_titles)
            if shared > best_shared:
                best, best_shared = release, shared
        if best is not None:
            adopt(session, old, best["id"], best)
            arrivals.remove(best)
            replaced += 1
            continue

        old.on_artist_page = False
        page = old_pages[old.id] if old.id in old_pages else _page_titles(old.id)
        if page is None:
            mark_removed(session, old)
            removed += 1
        else:
            logger.info("Album %s (%s) is no longer on its artist's page, but still on YouTube Music", old.id, old.title)
    return {"replaced": replaced, "removed": removed}


def replaced_by(session: Session, album_data: Dict[str, Any]) -> Optional[Album]:
    """
    For an album about to be downloaded that the library doesn't have (by
    hand, or a playlist scan) with adapter.get_album's data: the library
    album it replaces, if any. Only an album of the same artist with enough
    of the same tracks (or the same title, with none to compare: _match)
    is a candidate; the artist's page then decides: the
    old one no longer listed and the new one listed. Two releases it both
    lists are two albums. One artist page read, only for a candidate.
    """
    artist_id = next((a.get("id") for a in album_data.get("artists") or [] if a.get("id")), None)
    new_titles = _titles(album_data.get("tracks") or [])
    if not artist_id or not new_titles:
        return None
    best, best_shared = None, 0
    for album in session.scalars(select(Album).where(
        Album.artist_id == artist_id, Album.on_artist_page.is_(True), Album.id != album_data["id"],
    )):
        shared = _match(album, _library_titles(session, album.id), album_data.get("title"), new_titles)
        if shared > best_shared:
            best, best_shared = album, shared
    if best is None:
        return None
    try:
        artist = ytm_adapter.get_artist(artist_id)
    except ytm_adapter.YTMusicUnavailable:
        logger.warning("Couldn't read artist %s to tell whether album %s replaces %s", artist_id, album_data["id"], best.id)
        return None
    listed = {r["id"] for r in artist["albums"] + artist["singles"] if r.get("id")}
    if best.id in listed or album_data["id"] not in listed:
        return None
    return best
