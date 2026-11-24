# backend/lyrics/base.py
"""
What a lyrics provider is given and gives back.

A provider is a module with NAME (shown in logs and errors) and
lookup(query: LyricsQuery) -> Lyrics, raising ProviderUnavailable when it
can't answer right now (down, rate-limiting), so that the caller retries
later instead of recording a misleading "not found". What to do with the
answer (synced or plain, retry when) is jobs.tasks.download_lyrics' call.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class LyricsQuery:
    video_id: str
    title: str
    artist: str  # the main artist's name
    album: str
    duration: int  # seconds, 0 when unknown


@dataclass(frozen=True)
class Lyrics:
    """
    found: the provider has a record of the song, with or without lyrics.
    instrumental: it says the song has no lyrics (never with synced/plain).
    source: which record answered, for the logs.
    """
    synced: Optional[str] = None  # LRC text, "[mm:ss.xx]line" per line
    plain: Optional[str] = None
    instrumental: bool = False
    found: bool = False
    source: str = ""


class ProviderUnavailable(Exception):
    """The provider answered with a rate limit or a server error, or didn't answer at all."""
