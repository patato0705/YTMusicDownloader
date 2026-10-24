# backend/services/folders.py
"""
Where an artist's and an album's files go: MUSIC_DIR/<artist folder>/<album folder>.

Each folder is named after the artist or the album the first time a file is
written there, and keeps that name (Artist.folder, Album.folder). A name that
changes afterwards never splits the files across two folders: YouTube Music's
album page and artist page can spell the same artist differently ("CG5" and
"Cg5"), and the artist's sync replaces one with the other.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional, Union

from sqlalchemy import select, update
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import set_committed_value

from .. import config
from ..downloader.core import safe_name
from ..models import Album, Artist


def _claim(session: Session, row: Union[Artist, Album], name: Optional[str]) -> str:
    """
    row.folder, set from `name` when it has none yet. Only the first writer
    sets it, so two workers writing an album's first files at once agree.
    """
    if not row.folder:
        model = type(row)
        session.flush()  # a row just created must be in the DB for the update to find it
        session.execute(
            update(model).where(model.id == row.id, model.folder.is_(None)).values(folder=safe_name(name))
        )
        folder = session.execute(select(model.folder).where(model.id == row.id)).scalar_one()
        set_committed_value(row, "folder", folder)
    return row.folder


def artist_dir(session: Session, artist: Optional[Artist]) -> Path:
    """
    The artist's folder, named now if nothing of it was written yet. Naming
    it takes SQLite's write lock: the caller commits soon after. Does not commit.
    """
    if artist is None:
        return config.MUSIC_DIR / safe_name(None)
    return config.MUSIC_DIR / _claim(session, artist, artist.name)


def album_dir(session: Session, album: Album) -> Path:
    """The album's folder, inside its artist's. Named like artist_dir. Does not commit."""
    return artist_dir(session, album.artist) / _claim(session, album, album.title)


def existing_artist_dir(artist: Artist) -> Optional[Path]:
    """The artist's folder, or None when nothing of it was ever written (no folder named)."""
    return config.MUSIC_DIR / artist.folder if artist.folder else None


def existing_album_dir(album: Album) -> Optional[Path]:
    """The album's folder, or None when nothing of it was ever written (no folder named)."""
    if not album.folder:
        return None
    if album.artist is None:
        return config.MUSIC_DIR / safe_name(None) / album.folder
    artist_folder = existing_artist_dir(album.artist)
    return artist_folder / album.folder if artist_folder else None
