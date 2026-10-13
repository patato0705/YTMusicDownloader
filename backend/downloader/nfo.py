# backend/downloader/nfo.py
"""artist.nfo and album.nfo files, the metadata Jellyfin reads next to the music."""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

from ..config import MUSIC_DIR
from .core import album_dir, safe_name

logger = logging.getLogger("downloader.nfo")


def _artist_dir(artist_name: Optional[str]) -> Path:
    return MUSIC_DIR / safe_name(artist_name)


def _set_text(parent: ET.Element, tag: str, value: Optional[str]) -> None:
    if value is None or value == "":
        return
    el = ET.SubElement(parent, tag)
    el.text = str(value)


def _set_genres(parent: ET.Element, genres) -> None:
    # One element per genre: how Jellyfin reads several
    for genre in genres or []:
        _set_text(parent, "genre", genre)


def artist_dir_exists(artist_name: Optional[str]) -> bool:
    return bool(artist_name) and _artist_dir(artist_name).is_dir()


def album_dir_exists(artist_name: Optional[str], album_title: Optional[str]) -> bool:
    return bool(artist_name and album_title) and album_dir(artist_name, album_title).is_dir()


def _write_xml(root: ET.Element, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(root, space="  ")
    tree = ET.ElementTree(root)
    tree.write(str(dest), encoding="utf-8", xml_declaration=True)


def write_artist_nfo(artist) -> Optional[Path]:
    """Write {music_dir}/{artist}/artist.nfo. Returns the path or None on failure."""
    try:
        name = artist.name
        if not name:
            return None

        root = ET.Element("artist")
        _set_text(root, "name", name)
        _set_text(root, "biography", artist.description)
        _set_genres(root, artist.genres)
        _set_text(root, "thumb", artist.image_local)
        if artist.banner_local:
            _set_text(ET.SubElement(root, "fanart"), "thumb", artist.banner_local)

        dest = _artist_dir(name) / "artist.nfo"
        _write_xml(root, dest)
        logger.info("Wrote artist.nfo: %s", dest)
        return dest
    except Exception:
        logger.exception("Failed writing artist.nfo for %s", artist.id)
        return None


def write_album_nfo(album, artist) -> Optional[Path]:
    """Write {music_dir}/{artist}/{album}/album.nfo. Returns the path or None on failure."""
    try:
        title = album.title
        artist_name = artist.name if artist else None
        if not title or not artist_name:
            return None

        root = ET.Element("album")
        _set_text(root, "title", title)
        _set_text(root, "artist", artist_name)
        _set_text(root, "year", album.year)
        _set_genres(root, album.genres)
        _set_text(root, "thumb", album.image_local)

        dest = album_dir(artist_name, title) / "album.nfo"
        _write_xml(root, dest)
        logger.info("Wrote album.nfo: %s", dest)
        return dest
    except Exception:
        logger.exception("Failed writing album.nfo for %s", album.id)
        return None
