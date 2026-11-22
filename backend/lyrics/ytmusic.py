# backend/lyrics/ytmusic.py
"""
YouTube Music's own lyrics (licensed from LyricFind, Musixmatch...), found
by the track's video id, so always the lyrics of that very track. The last
resort after LRCLIB (see jobs.tasks._download_lyrics): two YouTube requests
per lookup, from the IP the downloads use. It never says a track is
instrumental: a song without lyrics there has no lyrics page at all.
"""
from __future__ import annotations
from typing import List, Tuple

from ..ytm_service import adapter as ytm_adapter
from .base import Lyrics, LyricsQuery, ProviderUnavailable

NAME = "YouTube Music"


def _lrc_timestamp(ms: int) -> str:
    """[mm:ss.xx], as LRCLIB writes them (minutes past 99 widen the field)."""
    centiseconds = max(0, ms) // 10
    minutes, centiseconds = divmod(centiseconds, 6000)
    seconds, centiseconds = divmod(centiseconds, 100)
    return f"[{minutes:02d}:{seconds:02d}.{centiseconds:02d}]"


def to_lrc(lines: List[Tuple[int, str]]) -> str:
    return "\n".join(f"{_lrc_timestamp(start)} {text}".rstrip() for start, text in lines)


def lookup(query: LyricsQuery) -> Lyrics:
    try:
        found = ytm_adapter.get_lyrics(query.video_id)
    except ytm_adapter.YTMusicUnavailable as e:
        raise ProviderUnavailable(str(e)) from e
    if not found:
        return Lyrics()
    source = found.get("source") or ""
    if found.get("lines"):
        return Lyrics(synced=to_lrc(found["lines"]), found=True, source=source)
    return Lyrics(plain=found.get("plain"), found=True, source=source)
