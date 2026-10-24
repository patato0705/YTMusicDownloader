# backend/services/folders.py
"""
Where an artist's and an album's files go: MUSIC_DIR/<artist folder>/<album folder>.

Each folder is named after the artist or the album the first time a file is
written there, and keeps that name (Artist.folder, Album.folder). A name that
changes afterwards never splits the files across two folders: YouTube Music's
album page and artist page can spell the same artist differently ("CG5" and
"Cg5"), and the artist's sync replaces one with the other.

A name another artist (or another album of the same artist) already has gets
a number, "Name (2)", so two namesakes never share a folder: deleting one
would delete the other's files with it. Media servers read the names from
the tags and .nfo files, so the number only shows on disk. Names are compared
ignoring case, as on a Windows or macOS share.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional, Set, Union

from sqlalchemy import select, update
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import set_committed_value

from .. import config
from ..downloader.core import safe_name
from ..models import Album, Artist
from .playlists import M3U_DIR_NAME

# The folder of albums without an artist
NO_ARTIST = safe_name(None)

# Longest file name most filesystems allow, in bytes
_MAX_NAME_BYTES = 255


def _fit(name: str, reserve: int = 0) -> str:
    """name cut to fit the filesystem's limit, leaving `reserve` bytes for a suffix."""
    return name.encode()[: _MAX_NAME_BYTES - reserve].decode(errors="ignore").rstrip()


def _free_name(name: str, taken: Set[str]) -> str:
    """name, or "name (2)", "name (3)"...: the first not taken, ignoring case."""
    taken = {t.casefold() for t in taken}
    candidate, n = name, 1
    while candidate.casefold() in taken:
        n += 1
        suffix = f" ({n})"
        candidate = _fit(name, len(suffix.encode())) + suffix
    return candidate


def _taken(session: Session, row: Union[Artist, Album]) -> Set[str]:
    """The folder names `row` can't have: those of its siblings, and for an artist the fixed ones."""
    if isinstance(row, Artist):
        siblings = select(Artist.folder).where(Artist.folder.is_not(None), Artist.id != row.id)
        reserved = {M3U_DIR_NAME, NO_ARTIST}
    else:
        same_artist = Album.artist_id == row.artist_id if row.artist_id else Album.artist_id.is_(None)
        siblings = select(Album.folder).where(Album.folder.is_not(None), Album.id != row.id, same_artist)
        reserved = set()
    return set(session.execute(siblings).scalars()) | reserved


def _claim(session: Session, row: Union[Artist, Album], name: Optional[str]) -> str:
    """
    row.folder, named after `name` when it has none yet. Takes SQLite's write
    lock first, so no other writer names a folder between the check and the
    update: two workers writing an album's first files at once agree on its
    folder, and two namesakes never get the same one.
    """
    if not row.folder:
        model = type(row)
        session.flush()  # a row just created must be in the DB for the updates to find it
        # A write that changes nothing, for the lock
        session.execute(update(model).where(model.id == row.id).values(folder=model.folder))
        folder = session.execute(select(model.folder).where(model.id == row.id)).scalar_one()
        if folder is None:
            folder = _free_name(_fit(safe_name(name)), _taken(session, row))
            session.execute(update(model).where(model.id == row.id).values(folder=folder))
        set_committed_value(row, "folder", folder)
    return row.folder


def artist_dir(session: Session, artist: Optional[Artist]) -> Path:
    """
    The artist's folder, named now if nothing of it was written yet. Naming
    it takes SQLite's write lock: the caller commits soon after. Does not commit.
    """
    if artist is None:
        return config.MUSIC_DIR / NO_ARTIST
    return config.MUSIC_DIR / _claim(session, artist, artist.name)


def album_dir(session: Session, album: Album) -> Path:
    """The album's folder, inside its artist's. Named like artist_dir. Does not commit."""
    return artist_dir(session, album.artist) / _claim(session, album, album.title)


def restore_folder(session: Session, row: Union[Artist, Album], folder: str) -> None:
    """
    Give a row without a folder the one a backup had for it, so copied files
    and new ones stay together (numbered if another row here has that name).
    Takes the write lock like artist_dir. Does not commit.
    """
    if not row.folder:
        _claim(session, row, folder)


def existing_artist_dir(artist: Artist) -> Optional[Path]:
    """The artist's folder, or None when nothing of it was ever written (no folder named)."""
    return config.MUSIC_DIR / artist.folder if artist.folder else None


def existing_album_dir(album: Album) -> Optional[Path]:
    """The album's folder, or None when nothing of it was ever written (no folder named)."""
    if not album.folder:
        return None
    if album.artist is None:
        return config.MUSIC_DIR / NO_ARTIST / album.folder
    artist_folder = existing_artist_dir(album.artist)
    return artist_folder / album.folder if artist_folder else None
