# backend/services/exclusions.py
"""
Artists and albums kept out of the library (models.Exclusion): deleting
them, or unfollowing an artist, must stick. Every automatic path that
follows an artist or downloads an album asks here first:

| Path                          | excluded artist          | excluded album |
|-------------------------------|--------------------------|----------------|
| chart sync                    | not followed             |                |
| playlist scan, artists mode   | not followed             |                |
| playlist scan, albums mode    | its albums not           | not downloaded |
|                               | downloaded ("deleted")   |                |
| artist sync in full           |                          | stays metadata |
| backup import                 | not followed             | not downloaded |
| bulk buttons, playlist page   | skipped                  | skipped        |

Deleting an artist excludes it ("deleted") and each of its albums in the
library ("artist_deleted"): an album credits several artists, and only
its row says whose it is in the library. Albums the library didn't know
(released since) are kept out by their main artist (blocked_album_ids).

Following the artist or downloading the album by hand lifts it
(subscriptions.follow_artist / start_album_download, explicit=True), and
so does Restore in the library. Lifting an artist's lifts the exclusions
of the albums deleted with it, not those of albums deleted on their own.
"""
from __future__ import annotations
import logging
from typing import Any, Dict, Iterable, List, Optional, Set

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Album, Artist, Exclusion

logger = logging.getLogger("services.exclusions")

ARTIST = "artist"
ALBUM = "album"
DELETED = "deleted"
UNFOLLOWED = "unfollowed"
# An album deleted with its artist (not on its own)
ARTIST_DELETED = "artist_deleted"


def get(session: Session, kind: str, item_id: Optional[str]) -> Optional[Exclusion]:
    return session.get(Exclusion, (kind, item_id)) if item_id else None


def excluded_artist_ids(session: Session, reason: Optional[str] = None) -> Set[str]:
    """Excluded artists: all of them, or those excluded for `reason`."""
    stmt = select(Exclusion.item_id).where(Exclusion.kind == ARTIST)
    if reason:
        stmt = stmt.where(Exclusion.reason == reason)
    return set(session.scalars(stmt))


def blocked_album_ids(session: Session, albums: Dict[str, Optional[str]]) -> Set[str]:
    """
    Of these albums ({album id: its artist id, if known}), those nothing
    automatic may download: excluded themselves, or by a deleted artist.
    The album's own row says who its artist is when the library has one.
    """
    if not albums:
        return set()
    excluded = set(session.scalars(
        select(Exclusion.item_id).where(Exclusion.kind == ALBUM, Exclusion.item_id.in_(list(albums)))
    ))
    rows = dict(session.execute(select(Album.id, Album.artist_id).where(Album.id.in_(list(albums)))).all())
    deleted_artists = excluded_artist_ids(session, DELETED)
    return excluded | {
        album_id for album_id, artist_id in albums.items()
        if (rows.get(album_id) or artist_id) in deleted_artists
    }


def exclude_artist(session: Session, artist_id: str, name: Optional[str], reason: str) -> None:
    """
    Exclude an artist: "deleted" outranks "unfollowed" (deleting an artist
    that was unfollowed, never the other way). Does not commit.
    """
    exclusion = get(session, ARTIST, artist_id)
    if exclusion is None:
        session.add(Exclusion(kind=ARTIST, item_id=artist_id, reason=reason, name=(name or "")[:255]))
    elif reason == DELETED:
        exclusion.reason = DELETED
    logger.info("Excluded artist %s (%s)", artist_id, reason)


def exclude_album(session: Session, album: Album, reason: str = DELETED) -> None:
    """
    Exclude a deleted album, its title and artist kept to list it: on its
    own ("deleted", which outranks) or with its artist ("artist_deleted").
    Does not commit.
    """
    exclusion = get(session, ALBUM, album.id)
    if exclusion is not None:
        if reason == DELETED:
            exclusion.reason = DELETED
        return
    artist = session.get(Artist, album.artist_id) if album.artist_id else None
    session.add(Exclusion(
        kind=ALBUM, item_id=album.id, reason=reason, name=(album.title or "")[:255],
        artist_id=album.artist_id, artist_name=artist.name if artist else None,
    ))
    logger.info("Excluded album %s (%s)", album.id, reason)


def exclude_deleted_artist(session: Session, artist: Artist) -> None:
    """Exclude an artist being deleted, and each of its albums in the library. Does not commit."""
    exclude_artist(session, artist.id, artist.name, DELETED)
    for album in session.scalars(select(Album).where(Album.artist_id == artist.id)):
        exclude_album(session, album, ARTIST_DELETED)


def lift(session: Session, kind: str, item_id: Optional[str]) -> bool:
    """Lift an exclusion, if there is one. Does not commit. Returns whether there was."""
    exclusion = get(session, kind, item_id)
    if exclusion is None:
        return False
    session.delete(exclusion)
    logger.info("Lifted the exclusion of %s %s", kind, item_id)
    return True


def lift_artist(session: Session, artist_id: str) -> bool:
    """
    Lift an artist's exclusion, and those of the albums deleted with it.
    Does not commit. Returns whether the artist was excluded.
    """
    for exclusion in session.scalars(select(Exclusion).where(
        Exclusion.kind == ALBUM, Exclusion.reason == ARTIST_DELETED, Exclusion.artist_id == artist_id,
    )):
        session.delete(exclusion)
    return lift(session, ARTIST, artist_id)


def list_all(session: Session) -> Dict[str, List[Dict[str, Any]]]:
    """
    Every exclusion, newest first, as the library lists them. Albums
    deleted with their artist are left out: the artist stands for them.
    """
    rows = session.scalars(
        select(Exclusion)
        .where(Exclusion.reason != ARTIST_DELETED)
        .order_by(Exclusion.created_at.desc())
    ).all()
    albums = {a.id: a for a in session.scalars(
        select(Album).where(Album.id.in_([r.item_id for r in rows if r.kind == ALBUM]))
    )}
    artists = {a.id: a for a in session.scalars(
        select(Artist).where(Artist.id.in_([r.item_id for r in rows if r.kind == ARTIST]))
    )}
    out: Dict[str, List[Dict[str, Any]]] = {"artists": [], "albums": []}
    for r in rows:
        if r.kind == ARTIST:
            artist = artists.get(r.item_id)
            out["artists"].append({
                "id": r.item_id,
                "name": artist.name if artist else r.name,
                "thumbnail": artist.image_local if artist else None,
                "reason": r.reason,
                "excluded_at": r.created_at.isoformat(),
            })
        else:
            album = albums.get(r.item_id)
            out["albums"].append({
                "id": r.item_id,
                "title": album.title if album else r.name,
                "artist": {"id": r.artist_id, "name": r.artist_name} if r.artist_id else None,
                "thumbnail": album.image_local if album else None,
                "year": album.year if album else None,
                "type": (album.type if album else None) or "Album",
                "reason": r.reason,
                "excluded_at": r.created_at.isoformat(),
            })
    return out


def export_rows(session: Session) -> List[Dict[str, Any]]:
    """Every exclusion, for a backup."""
    return [
        {
            "kind": r.kind, "id": r.item_id, "reason": r.reason, "name": r.name,
            "artist_id": r.artist_id, "artist_name": r.artist_name,
        }
        for r in session.scalars(select(Exclusion).order_by(Exclusion.kind, Exclusion.item_id))
    ]


def import_rows(session: Session, items: Iterable[Any]) -> int:
    """
    Restore a backup's exclusions (schemas.export.LibraryExclusion), keeping
    those already here ("deleted" outranks the others). Does not commit.
    Returns how many were added or changed.
    """
    changed = 0
    for item in items:
        existing = get(session, item.kind, item.id)
        if existing is None:
            session.add(Exclusion(
                kind=item.kind, item_id=item.id, reason=item.reason, name=item.name or "",
                artist_id=item.artist_id, artist_name=item.artist_name,
            ))
            changed += 1
        elif existing.reason != item.reason and item.reason == DELETED:
            existing.reason = DELETED
            changed += 1
    return changed
