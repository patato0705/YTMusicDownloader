# backend/downloader/embed.py
"""Tags of downloaded files: M4A/MP4 via mutagen.mp4, anything else as MP3 (ID3)."""
from __future__ import annotations
import fcntl
import logging
from pathlib import Path
from typing import Any, Callable, List, Optional

from mutagen import File as MutagenFile
from mutagen.id3 import ID3, ID3NoHeaderError, TIT2, TALB, TPE1, TPE2, TRCK, TDRC, TCON, APIC
from mutagen.mp4 import MP4, MP4Cover

logger = logging.getLogger("downloader.embed")

_MP4_SUFFIXES = (".m4a", ".mp4", ".aac", ".m4b")


def _open(path: Path):
    """The file's tags: an MP4 object, or ID3 (empty when the file has none yet)."""
    mf = MutagenFile(str(path))
    if isinstance(mf, MP4) or path.suffix.lower() in _MP4_SUFFIXES:
        return mf if isinstance(mf, MP4) else MP4(str(path))
    try:
        return ID3(str(path))
    except ID3NoHeaderError:
        return ID3()


def embed_tags(
    path: Path,
    title: str,
    album: str,
    artist: str,
    cover_path: Optional[Path] = None,
    track_number: Optional[int] = None,
    year: Optional[str] = None,
    genres: Optional[List[str]] = None,
) -> None:
    """Write a downloaded track's tags (artist doubles as album artist). Errors are logged, not raised."""
    try:
        tags = _open(path)
        cover = cover_path.read_bytes() if cover_path else None
        is_png = bool(cover_path) and cover_path.suffix.lower() == ".png"
        if isinstance(tags, MP4):
            tags["\xa9nam"] = [title]
            tags["\xa9alb"] = [album]
            tags["\xa9ART"] = [artist]
            tags["aART"] = [artist]
            if track_number:
                tags["trkn"] = [(int(track_number), 0)]
            if year:
                tags["\xa9day"] = [str(year)]
            if genres:
                tags["\xa9gen"] = list(genres)
            if cover:
                fmt = MP4Cover.FORMAT_PNG if is_png else MP4Cover.FORMAT_JPEG
                tags["covr"] = [MP4Cover(cover, imageformat=fmt)]
            tags.save()
        else:
            for frame in (TIT2(encoding=3, text=[title]), TALB(encoding=3, text=[album]),
                          TPE1(encoding=3, text=[artist]), TPE2(encoding=3, text=[artist])):
                tags.setall(frame.FrameID, [frame])
            if track_number:
                tags.setall("TRCK", [TRCK(encoding=3, text=[str(track_number)])])
            if year:
                tags.setall("TDRC", [TDRC(encoding=3, text=[str(year)])])
            if genres:
                tags.setall("TCON", [TCON(encoding=3, text=list(genres))])
            if cover:
                mime = "image/png" if is_png else "image/jpeg"
                tags.setall("APIC", [APIC(encoding=3, mime=mime, type=3, desc="cover", data=cover)])
            tags.save(str(path))
    except Exception:
        logger.exception("Embedding metadata failed for %s", path)


def _edit(file_path: str, what: str, edit: Callable[[Any], None]) -> bool:
    """
    Change some tags of a file already in the library with `edit(tags)`,
    leaving every other tag alone. Returns whether it was written.

    Holds an exclusive lock on the file meanwhile: a download finishing
    (jobs.tasks.download_track catches up on genres and on an artist renamed
    mid-download), the genre lookup and an artist's rename can all get here
    for the same file, from different processes.
    """
    path = Path(file_path)
    if not path.is_file():
        return False
    try:
        with open(path, "rb") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                tags = _open(path)
                edit(tags)
                if isinstance(tags, MP4):
                    tags.save()
                else:
                    tags.save(str(path))
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
        return True
    except Exception:
        logger.exception("Setting %s failed for %s", what, path)
        return False


def set_genres(file_path: str, genres: List[str]) -> bool:
    """Replace a library file's genre tag (an empty list removes it). Returns whether it was written."""
    def edit(tags) -> None:
        if isinstance(tags, MP4):
            if genres:
                tags["\xa9gen"] = list(genres)
            else:
                tags.pop("\xa9gen", None)
        else:
            tags.delall("TCON")
            if genres:
                tags.add(TCON(encoding=3, text=list(genres)))

    return _edit(file_path, "genres", edit)


def set_artist(file_path: str, artist: str) -> bool:
    """Replace a library file's artist and album artist tags (one name, as embed_tags writes them). Returns whether it was written."""
    def edit(tags) -> None:
        if isinstance(tags, MP4):
            tags["\xa9ART"] = [artist]
            tags["aART"] = [artist]
        else:
            tags.setall("TPE1", [TPE1(encoding=3, text=[artist])])
            tags.setall("TPE2", [TPE2(encoding=3, text=[artist])])

    return _edit(file_path, "the artist", edit)
