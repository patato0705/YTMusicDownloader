# downloader/embed.py
from __future__ import annotations
import logging
import os
from pathlib import Path
from typing import Iterable, List, Optional, Union

logger = logging.getLogger("downloader.embed")
if not logging.getLogger().handlers:
    import sys, logging as _logging
    _logging.basicConfig(stream=sys.stderr, level=os.environ.get("LOG_LEVEL", "INFO"))

# try import mutagen helpers
try:
    from mutagen import File as MutagenFile  # type: ignore
    from mutagen.mp4 import MP4, MP4Cover  # type: ignore
    from mutagen.id3 import ID3, TIT2, TALB, TPE1, TPE2, TRCK, APIC, USLT  # type: ignore
    _HAS_MUTAGEN = True
except Exception:
    _HAS_MUTAGEN = False


def _read_bytes(p: Union[str, Path]) -> Optional[bytes]:
    try:
        return Path(str(p)).read_bytes()
    except Exception:
        return None


def _embed_mp4_tags(path: Path,
                    title: Optional[str],
                    album: Optional[str],
                    artists: Optional[Iterable[str]],
                    album_artist: Optional[str],
                    lyrics_path: Optional[Union[str, Path]],
                    cover_path: Optional[Union[str, Path]],
                    track_number: Optional[int],
                    year: Optional[str]) -> None:
    """
    Embed tags into M4A/MP4 file using mutagen.mp4.MP4.
    """
    try:
        mp4 = MP4(str(path))
        if title is not None:
            mp4["\xa9nam"] = [str(title)]
        if album is not None:
            mp4["\xa9alb"] = [str(album)]
        if artists:
            mp4["\xa9ART"] = [str(a) for a in artists]
        if album_artist:
            mp4["aART"] = [str(album_artist)]
        if track_number:
            try:
                mp4["trkn"] = [(int(track_number), 0)]
            except Exception:
                pass
        if year:
            try:
                mp4["\xa9day"] = [str(year)]
            except Exception:
                pass
        # lyrics
        if lyrics_path:
            lyrics_bytes = _read_bytes(lyrics_path)
            if lyrics_bytes:
                try:
                    # MP4 lyric tag key often ©lyr
                    mp4["©lyr"] = [lyrics_bytes.decode("utf-8", errors="ignore")]
                except Exception:
                    try:
                        mp4["\xa9lyr"] = [lyrics_bytes.decode("utf-8", errors="ignore")]
                    except Exception:
                        logger.debug("Could not set MP4 lyric tag, skipping")
        # cover
        if cover_path:
            cover_bytes = _read_bytes(cover_path)
            if cover_bytes:
                # choose format by extension
                fmt = None
                ext = str(cover_path).lower()
                if ext.endswith(".png"):
                    fmt = MP4Cover.FORMAT_PNG
                else:
                    fmt = MP4Cover.FORMAT_JPEG
                mp4["covr"] = [MP4Cover(cover_bytes, imageformat=fmt)]
        mp4.save()
    except Exception:
        logger.exception("MP4 embedding failed for %s", path)

def _embed_mp3_tags(path: Path,
                    title: Optional[str],
                    album: Optional[str],
                    artists: Optional[Iterable[str]],
                    album_artist: Optional[str],
                    lyrics_path: Optional[Union[str, Path]],
                    cover_path: Optional[Union[str, Path]],
                    track_number: Optional[int],
                    year: Optional[str]) -> None:
    """
    Embed tags into MP3 file using ID3 frames.
    """
    try:
        try:
            id3 = ID3(str(path))
        except Exception:
            id3 = ID3()
        if title is not None:
            id3.delall("TIT2")
            id3.add(TIT2(encoding=3, text=[str(title)]))
        if album is not None:
            id3.delall("TALB")
            id3.add(TALB(encoding=3, text=[str(album)]))
        if artists:
            id3.delall("TPE1")
            id3.add(TPE1(encoding=3, text=[", ".join(str(a) for a in artists)]))
        if album_artist:
            id3.delall("TPE2")
            id3.add(TPE2(encoding=3, text=[str(album_artist)]))
        if track_number:
            id3.delall("TRCK")
            id3.add(TRCK(encoding=3, text=[str(track_number)]))
        if year:
            id3.add(TALB(encoding=3, text=[str(year)]))  # not ideal but keep
        # lyrics
        if lyrics_path:
            lyrics_bytes = _read_bytes(lyrics_path)
            if lyrics_bytes:
                try:
                    txt = lyrics_bytes.decode("utf-8", errors="ignore")
                    id3.delall("USLT")
                    id3.add(USLT(encoding=3, lang="eng", desc="", text=txt))
                except Exception:
                    logger.debug("Could not add USLT lyrics")
        # cover
        if cover_path:
            cover_bytes = _read_bytes(cover_path)
            if cover_bytes:
                # try to detect mime
                mime = "image/jpeg"
                if str(cover_path).lower().endswith(".png"):
                    mime = "image/png"
                id3.delall("APIC")
                id3.add(APIC(encoding=3, mime=mime, type=3, desc="cover", data=cover_bytes))
        id3.save(str(path))
    except Exception:
        logger.exception("MP3 embedding failed for %s", path)


def embed_tags(file_path: str,
               title: Optional[str] = None,
               album: Optional[str] = None,
               artists: Optional[List[str]] = None,
               album_artist: Optional[str] = None,
               lyrics_path: Optional[Union[str, Path]] = None,
               cover_path: Optional[Union[str, Path]] = None,
               track_number: Optional[int] = None,
               year: Optional[str] = None) -> None:
    """
    Embeds metadata into an audio file. Supports MP4/M4A and MP3 via mutagen.
    If mutagen is not installed, logs and returns.
    """
    if not _HAS_MUTAGEN:
        logger.debug("mutagen not available, skipping embedding for %s", file_path)
        return

    p = Path(str(file_path))
    if not p.exists():
        logger.warning("embed_tags: file does not exist %s", file_path)
        return

    # normalize artists iterable
    artists_list = list(artists) if artists else []

    try:
        # autodetect container
        mf = MutagenFile(str(p))
        if isinstance(mf, MP4) or p.suffix.lower() in (".m4a", ".mp4", ".aac", ".m4b"):
            _embed_mp4_tags(p, title, album, artists_list, album_artist, lyrics_path, cover_path, track_number, year)
        else:
            # fallback to MP3 ID3 embedding where possible
            _embed_mp3_tags(p, title, album, artists_list, album_artist, lyrics_path, cover_path, track_number, year)
    except Exception:
        logger.exception("Embedding metadata failed for %s", file_path)