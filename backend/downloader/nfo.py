from __future__ import annotations
import logging
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

from ..config import MUSIC_DIR

logger = logging.getLogger("downloader.nfo")


def _safe_name(s: Optional[str]) -> str:
    if not s:
        return "Unknown"
    return "".join(c for c in s if c.isalnum() or c in " .-_()").strip() or "Unknown"


def _artist_dir(artist_name: Optional[str]) -> Path:
    return Path(str(MUSIC_DIR)) / _safe_name(artist_name)


def _album_dir(artist_name: Optional[str], album_title: Optional[str]) -> Path:
    return _artist_dir(artist_name) / _safe_name(album_title)


def _set_text(parent: ET.Element, tag: str, value: Optional[str]) -> None:
    if value is None or value == "":
        return
    el = ET.SubElement(parent, tag)
    el.text = str(value)


def _write_xml(root: ET.Element, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(root, space="  ")
    tree = ET.ElementTree(root)
    tree.write(str(dest), encoding="utf-8", xml_declaration=True)


def write_artist_nfo(artist) -> Optional[Path]:
    """Write {music_dir}/{artist}/artist.nfo. Returns the path or None on failure."""
    try:
        name = getattr(artist, "name", None)
        if not name:
            return None

        root = ET.Element("artist")
        _set_text(root, "name", name)
        _set_text(root, "biography", getattr(artist, "description", None))
        thumb = getattr(artist, "image_local", None)
        if thumb:
            _set_text(root, "thumb", str(thumb))

        dest = _artist_dir(name) / "artist.nfo"
        _write_xml(root, dest)
        logger.info("Wrote artist.nfo: %s", dest)
        return dest
    except Exception:
        logger.exception("Failed writing artist.nfo for %s", getattr(artist, "id", None))
        return None


def write_album_nfo(album, artist) -> Optional[Path]:
    """Write {music_dir}/{artist}/{album}/album.nfo. Returns the path or None on failure."""
    try:
        title = getattr(album, "title", None)
        artist_name = getattr(artist, "name", None) if artist else None
        if not title or not artist_name:
            return None

        root = ET.Element("album")
        _set_text(root, "title", title)
        _set_text(root, "artist", artist_name)
        _set_text(root, "year", getattr(album, "year", None))
        thumb = getattr(album, "image_local", None)
        if thumb:
            _set_text(root, "thumb", str(thumb))

        dest = _album_dir(artist_name, title) / "album.nfo"
        _write_xml(root, dest)
        logger.info("Wrote album.nfo: %s", dest)
        return dest
    except Exception:
        logger.exception("Failed writing album.nfo for %s", getattr(album, "id", None))
        return None
