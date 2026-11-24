# backend/lyrics/lrclib.py
"""
LRCLIB (lrclib.net): community-uploaded lyrics, synced and plain, looked up
by title, artist, album and duration. No account or API key needed.
"""
from __future__ import annotations
import logging
import random
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import requests

from .. import config
from ..text_utils import fold
from .base import Lyrics, LyricsQuery, ProviderUnavailable

logger = logging.getLogger("lyrics.lrclib")

NAME = "LRCLIB"

_LRCLIB_HEADERS = {"User-Agent": f"YTMusicDownloader v{config.APP_VERSION} (https://github.com/patato0705/YTMusicDownloader)"}

# YTMusic and LRCLIB (mostly Spotify-sourced) durations routinely disagree by
# a second; anything beyond this is treated as a different version/edit.
LRCLIB_DURATION_TOLERANCE = 2


# Newer LRCLIB records carry a "lyricsfile" (YAML) whose metadata can flag the
# track instrumental while the top-level "instrumental" field still says false.
_LYRICSFILE_INSTRUMENTAL_RE = re.compile(r"^\s*instrumental:\s*true\s*$", re.MULTILINE | re.IGNORECASE)


def _is_instrumental(record: Dict[str, Any]) -> bool:
    if record.get("instrumental"):
        return True
    lyricsfile = record.get("lyricsfile")
    return isinstance(lyricsfile, str) and bool(_LYRICSFILE_INSTRUMENTAL_RE.search(lyricsfile))


# LRCLIB allows an identified client about 90 requests/min per IP and asks
# for sequential requests with a pause between them (lrclib.net/docs, "Rate
# Limiting"). One worker process makes every LRCLIB call, one job at a time,
# so pacing here in the module covers them all: one request per 0.75 s is
# 80/min, under the limit with room for the user browsing lrclib.net.
_LRCLIB_MIN_INTERVAL = 0.75
# A 429/503 is retried after its Retry-After (plus up to 30% jitter, as the
# docs ask) this many times before the job gives up and is retried later.
_LRCLIB_THROTTLED_RETRIES = 3
# Retry-After beyond this is not slept through inside a job: the job fails
# and the cooldown still holds every later request back.
_LRCLIB_MAX_WAIT = 600
# monotonic() before which no request may start: pacing and Retry-After
_lrclib_next_request_at = 0.0


def _lrclib_wait_turn() -> None:
    delay = _lrclib_next_request_at - time.monotonic()
    if delay > 0:
        time.sleep(delay)


def _retry_after_seconds(response: requests.Response) -> float:
    try:
        return max(1.0, float(response.headers.get("Retry-After", "")))
    except ValueError:
        return 60.0  # missing, or an HTTP date: assume a minute


def _lrclib_get(endpoint: str, params: Dict[str, Any], timeout: int) -> Optional[Any]:
    """
    GET an LRCLIB endpoint, paced and honoring Retry-After. Returns the
    parsed JSON, None on 404, and raises ProviderUnavailable for anything
    still failing (429/5xx/network) so callers retry later instead of
    recording a misleading "not found".
    """
    global _lrclib_next_request_at
    url = f"https://lrclib.net/api/{endpoint}?{urlencode(params)}"
    for attempt in range(_LRCLIB_THROTTLED_RETRIES + 1):
        _lrclib_wait_turn()
        try:
            response = requests.get(url, timeout=timeout, headers=_LRCLIB_HEADERS)
        except requests.RequestException as e:
            _lrclib_next_request_at = time.monotonic() + _LRCLIB_MIN_INTERVAL
            raise ProviderUnavailable(str(e)) from e
        _lrclib_next_request_at = time.monotonic() + _LRCLIB_MIN_INTERVAL
        if response.status_code == 200:
            return response.json()
        if response.status_code == 404:
            return None
        if response.status_code not in (429, 503):
            raise ProviderUnavailable(f"HTTP {response.status_code}")

        wait = _retry_after_seconds(response)
        wait += random.uniform(0, wait * 0.3)
        _lrclib_next_request_at = max(_lrclib_next_request_at, time.monotonic() + wait)
        if attempt == _LRCLIB_THROTTLED_RETRIES or wait > _LRCLIB_MAX_WAIT:
            raise ProviderUnavailable(f"HTTP {response.status_code}, Retry-After {wait:.0f}s")
        logger.info("LRCLIB HTTP %s, waiting %.1fs as asked", response.status_code, wait)
    raise AssertionError("unreachable")


def _search_matches(
    results: Any,
    track_name: str,
    artist_name: str,
    album_name: str,
    duration: int,
) -> List[Dict[str, Any]]:
    """
    The /api/search results that are this track, best first.

    /api/get returns a single record for the exact signature and happily
    returns a plain-only one even when a synced upload of the same song
    exists under "Foo - Single" or with a duration 1s off. So we look
    through the search results ourselves: same title, same (or containing)
    artist, duration within LRCLIB_DURATION_TOLERANCE. Ties go to an exact
    album match, then the closest duration, then the oldest (lowest id)
    upload.
    """
    if not isinstance(results, list):
        return []
    want_title = fold(track_name)
    want_artist = fold(artist_name)
    want_album = fold(album_name)

    ranked = []
    for c in results:
        if not isinstance(c, dict):
            continue
        if fold(c.get("trackName")) != want_title:
            continue
        cand_artist = fold(c.get("artistName"))
        if not (cand_artist == want_artist or want_artist in cand_artist or cand_artist in want_artist):
            continue
        try:
            delta = abs(float(c.get("duration") or 0) - float(duration))
        except (TypeError, ValueError):
            continue
        if duration and delta > LRCLIB_DURATION_TOLERANCE:
            continue
        album_rank = 0 if fold(c.get("albumName")) == want_album else 1
        ranked.append((album_rank, delta, int(c.get("id") or 0), c))

    ranked.sort(key=lambda r: r[:3])
    return [r[3] for r in ranked]


def lookup(query: LyricsQuery) -> Lyrics:
    """
    Find lyrics on LRCLIB for a track.

    Order: /api/get (exact signature) -> /api/search fallback (only when no
    synced lyrics yet). /api/get-cached is no longer documented and missed
    every time, so it is not asked. "instrumental" means a matching record
    is flagged instrumental (LRCLIB leaves both lyrics fields empty on
    those) and no lyrics turned up anywhere, so there is nothing to retry
    for. Raises ProviderUnavailable when LRCLIB is down/rate-limiting.
    """
    track_name, artist_name, album_name, duration = query.title, query.artist, query.album, query.duration
    params = {
        "track_name": track_name,
        "artist_name": artist_name,
        "album_name": album_name,
        "duration": duration,
    }
    synced = None
    plain = None
    instrumental = False
    found = False
    source = ""

    data = _lrclib_get("get", params, timeout=15)
    if data:
        found = True
        source = "get"
        synced = data.get("syncedLyrics")
        plain = data.get("plainLyrics")
        instrumental = _is_instrumental(data)

    # An exact record flagged instrumental is the answer; no search needed
    if not synced and not instrumental:
        results = _lrclib_get("search", {"track_name": track_name, "artist_name": artist_name}, timeout=15)
        matches = _search_matches(results, track_name, artist_name, album_name, duration)
        best = next((c for c in matches if c.get("syncedLyrics") and not _is_instrumental(c)), None)
        if best:
            found = True
            source = f"search#{best.get('id')}"
            synced = best.get("syncedLyrics")
            plain = best.get("plainLyrics") or plain
            logger.info(
                "LRCLIB search matched %s - %s: album=%r duration=%s (ours=%s)",
                artist_name, track_name, best.get("albumName"), best.get("duration"), duration,
            )
        elif not instrumental and not plain:
            # The exact record may be missing, or present but empty and
            # unflagged while other uploads of the same song are flagged
            flagged = next((c for c in matches if _is_instrumental(c)), None)
            if flagged:
                found = True
                source = f"search#{flagged.get('id')}"
                instrumental = True

    # Lyrics found anywhere win over an instrumental flag elsewhere
    instrumental = instrumental and not synced and not plain
    return Lyrics(synced=synced, plain=plain, instrumental=instrumental, found=found, source=source)
