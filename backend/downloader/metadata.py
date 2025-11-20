# backend/downloader/metadata.py
from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import LYRICS_DIR


def _safe_str(s: Optional[Any]) -> Optional[str]:
    if s is None:
        return None
    try:
        return str(s)
    except Exception:
        return None


def normalize_artists(artists: Optional[List[Dict[str, Optional[str]]]]) -> List[str]:
    """
    Convert a list of artist refs (dicts or strings) into a cleaned list of artist names.
    """
    out: List[str] = []
    if not artists:
        return out

    for a in artists:
        if not a:
            continue

        if isinstance(a, dict):
            # prefer name/title, fallback to id if present
            n = a.get("name") or a.get("title") or a.get("id") or None
        elif isinstance(a, str):
            n = a
        else:
            n = None

        if n is None:
            continue

        # ensure we operate on a str before calling strip()
        try:
            st = str(n).strip()
        except Exception:
            continue

        if st:
            out.append(st)

    return out


def _validate_file(path: Optional[str]) -> Optional[str]:
    """Return the string path if file exists & readable, else None."""
    if not path:
        return None
    try:
        p = Path(path)
        if p.is_file() and os.access(str(p), os.R_OK):
            return str(p)
    except Exception:
        pass
    return None


def build_metadata_tags(
    title: Optional[str],
    album: Optional[str],
    artists: Optional[List[Dict[str, Optional[str]]]] = None,
    album_artist: Optional[str] = None,
    lyrics_path: Optional[str] = None,
    cover_path: Optional[str] = None,
    track_number: Optional[int] = None,
    year: Optional[str] = None,
    dest_audio_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build a standardized metadata dict consumed by the embedder.
    If dest_audio_path is provided and lyrics_path is None, this function will *not*
    fetch lyrics by itself (lyrics fetching happens via downloader/lyrics.get_or_fetch)
    to avoid unnecessary network calls during metadata construction. However it will
    validate provided paths.

    Returned keys:
      - title, album, artists (list[str]), album_artist, lyrics_path, cover_path,
        track_number, year
    """
    artists_list = normalize_artists(artists or [])
    album_artist_safe = _safe_str(album_artist) if album_artist else (artists_list[0] if artists_list else None)

    tags: Dict[str, Any] = {
        "title": _safe_str(title),
        "album": _safe_str(album),
        "artists": artists_list,
        "album_artist": _safe_str(album_artist_safe),
        "lyrics_path": None,
        "cover_path": None,
        "track_number": int(track_number) if track_number is not None else None,
        "year": _safe_str(year) if year is not None else None,
    }

    # Validate explicit lyrics_path if given
    validated = _validate_file(lyrics_path)
    if validated:
        tags["lyrics_path"] = validated

    # Validate cover path if given
    validated_cover = _validate_file(cover_path)
    if validated_cover:
        tags["cover_path"] = validated_cover

    # If dest_audio_path provided and there's an existing same-name .lrc, prefer it.
    if dest_audio_path:
        try:
            p = Path(dest_audio_path)
            lrc_candidate = p.with_suffix(".lrc")
            if lrc_candidate.is_file() and os.access(str(lrc_candidate), os.R_OK):
                tags["lyrics_path"] = str(lrc_candidate)
        except Exception:
            pass

    return tags