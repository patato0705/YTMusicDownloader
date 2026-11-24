# backend/downloader/embed.py
"""
Tags of downloaded files, in the two formats config.YDL_FORMAT downloads:
  - Opus (.opus, Ogg): Vorbis comments, free-form "KEY=value" text; the
    cover, being binary, as a base64 FLAC picture block in
    METADATA_BLOCK_PICTURE (what Jellyfin, ffmpeg and players read)
  - AAC (.m4a, MP4): iTunes-style atoms ("\xa9nam" for the title...)
Anything else is refused: nothing downloads it, and a tag written in the
wrong format would be lost or corrupt the file.
"""
from __future__ import annotations
import base64
import fcntl
import logging
from pathlib import Path
from typing import Callable, List, Optional, Union

from mutagen import File as MutagenFile
from mutagen.flac import Picture
from mutagen.mp4 import MP4, MP4Cover
from mutagen.oggopus import OggOpus

logger = logging.getLogger("downloader.embed")

AudioFile = Union[MP4, OggOpus]

# Text tags by field, in each format. Vorbis comment keys are case-insensitive
_KEYS = {
    "title": ("\xa9nam", "TITLE"),
    "album": ("\xa9alb", "ALBUM"),
    "artist": ("\xa9ART", "ARTIST"),
    "album_artist": ("aART", "ALBUMARTIST"),
    "year": ("\xa9day", "DATE"),
    "genres": ("\xa9gen", "GENRE"),
}

_COVER_TYPE_FRONT = 3  # ID3/FLAC picture type "Cover (front)"


def _open(path: Path) -> AudioFile:
    audio = MutagenFile(str(path))
    if isinstance(audio, (MP4, OggOpus)):
        return audio
    raise ValueError(f"not an Opus or M4A file: {path.name}")


def _set_text(audio: AudioFile, field: str, values: List[str]) -> None:
    """Replace a text tag (several values for genres); an empty list removes it."""
    key = _KEYS[field][0 if isinstance(audio, MP4) else 1]
    if values:
        audio[key] = list(values)
    elif audio.tags is not None and key in audio.tags:
        del audio[key]


def _set_track_number(audio: AudioFile, number: int) -> None:
    if isinstance(audio, MP4):
        audio["trkn"] = [(int(number), 0)]
    else:
        audio["TRACKNUMBER"] = [str(int(number))]


def _set_cover(audio: AudioFile, data: bytes, is_png: bool) -> None:
    mime = "image/png" if is_png else "image/jpeg"
    if isinstance(audio, MP4):
        fmt = MP4Cover.FORMAT_PNG if is_png else MP4Cover.FORMAT_JPEG
        audio["covr"] = [MP4Cover(data, imageformat=fmt)]
        return
    picture = Picture()
    picture.type = _COVER_TYPE_FRONT
    picture.mime = mime
    picture.desc = "cover"
    picture.data = data
    audio["METADATA_BLOCK_PICTURE"] = [base64.b64encode(picture.write()).decode("ascii")]


def _edit(file_path: Union[str, Path], what: str, edit: Callable[[AudioFile], None]) -> bool:
    """
    Change some tags of a file with `edit(audio)`, leaving every other tag
    alone. Returns whether it was written; errors are logged, not raised.

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
                audio = _open(path)
                edit(audio)
                audio.save()
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
        return True
    except Exception:
        logger.exception("Setting %s failed for %s", what, path)
        return False


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
        cover = cover_path.read_bytes() if cover_path else None
    except OSError:
        logger.exception("Reading cover %s failed", cover_path)
        cover = None
    is_png = bool(cover_path) and cover_path.suffix.lower() == ".png"

    def edit(audio: AudioFile) -> None:
        _set_text(audio, "title", [title])
        _set_text(audio, "album", [album])
        _set_text(audio, "artist", [artist])
        _set_text(audio, "album_artist", [artist])
        if track_number:
            _set_track_number(audio, track_number)
        if year:
            _set_text(audio, "year", [str(year)])
        if genres:
            _set_text(audio, "genres", genres)
        if cover:
            _set_cover(audio, cover, is_png)

    _edit(path, "metadata", edit)


def set_genres(file_path: str, genres: List[str]) -> bool:
    """Replace a library file's genre tag (an empty list removes it). Returns whether it was written."""
    return _edit(file_path, "genres", lambda audio: _set_text(audio, "genres", genres))


def set_tags(
    file_path: str,
    title: Optional[str] = None,
    track_number: Optional[int] = None,
    album: Optional[str] = None,
    year: Optional[str] = None,
) -> bool:
    """
    Replace the given tags of a library file (as embed_tags writes them),
    after YouTube Music changed them. Returns whether it was written.
    """
    def edit(audio: AudioFile) -> None:
        if title is not None:
            _set_text(audio, "title", [title])
        if album is not None:
            _set_text(audio, "album", [album])
        if track_number:
            _set_track_number(audio, track_number)
        if year:
            _set_text(audio, "year", [str(year)])

    return _edit(file_path, "tags", edit)


def set_cover(file_path: str, cover_path: Path) -> bool:
    """Replace a library file's embedded cover (as embed_tags writes it). Returns whether it was written."""
    try:
        cover = cover_path.read_bytes()
    except OSError:
        logger.exception("Reading cover %s failed", cover_path)
        return False
    is_png = cover_path.suffix.lower() == ".png"
    return _edit(file_path, "the cover", lambda audio: _set_cover(audio, cover, is_png))


def set_artist(file_path: str, artist: str) -> bool:
    """Replace a library file's artist and album artist tags (one name, as embed_tags writes them). Returns whether it was written."""
    def edit(audio: AudioFile) -> None:
        _set_text(audio, "artist", [artist])
        _set_text(audio, "album_artist", [artist])

    return _edit(file_path, "the artist", edit)
