# backend/routers/tracks.py
"""
Track endpoints.

Endpoints:
- GET /api/tracks/{track_id}/lyrics - Return the track's .lrc file content.
- PUT /api/tracks/{track_id}/lyrics - Overwrite (or clear) the track's .lrc file.
"""
from __future__ import annotations
import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..config import MUSIC_DIR
from ..db import get_session
from ..dependencies import require_auth, require_member_or_admin
from ..models import Track, User

logger = logging.getLogger("routers.tracks")

router = APIRouter(prefix="/api/tracks", tags=["Tracks"])


# A line starting with an LRC timestamp like [01:23.45] or [1:23]. One such
# line is enough to call the file "synced"; this mirrors what LRCLIB returns
# in syncedLyrics vs plainLyrics (see jobs.tasks.download_lyrics).
_LRC_TIMESTAMP_RE = re.compile(r"^\[\d{1,3}:\d{2}(?:[.:]\d{1,3})?\]", re.MULTILINE)

# Hard cap on what a user can push into a .lrc file; real lyrics are a few KB.
_LYRICS_MAX_CHARS = 200_000


def _classify_lyrics(content: str) -> str:
    return "synced" if _LRC_TIMESTAMP_RE.search(content) else "plain"


def _lyrics_path_for(t: Track) -> Optional[Path]:
    """
    Where this track's .lrc lives (or should live): next to the audio file,
    same basename -- the layout jobs.tasks.download_lyrics writes. Never
    derived from user input, and refused if it somehow escapes MUSIC_DIR.
    """
    if not t.file_path:
        return None
    try:
        path = Path(t.file_path).with_suffix(".lrc").resolve()
    except (OSError, RuntimeError):
        return None
    if not path.is_relative_to(MUSIC_DIR.resolve()):
        logger.warning("Refusing lyrics path outside MUSIC_DIR for track %s: %s", t.id, path)
        return None
    return path


# --- routes ---------------------------------------------------------------

@router.get("/{track_id}/lyrics", status_code=status.HTTP_200_OK)
def get_lyrics(
    track_id: str,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_session),
) -> Dict[str, Any]:
    """
    Return the raw content of the track's .lrc file.
    `content` is null when the track has no lyrics file on disk; `editable`
    tells the client whether a PUT could succeed (audio file present).
    """
    t = db.get(Track, track_id)
    if not t:
        raise HTTPException(status_code=404, detail="track not found")

    lrc_path = _lyrics_path_for(t)
    content: Optional[str] = None
    if lrc_path and lrc_path.is_file():
        try:
            content = lrc_path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            logger.exception("Failed to read lyrics for %s", track_id)
            raise HTTPException(status_code=500, detail=f"Failed to read lyrics: {e}")

    return {
        "ok": True,
        "track_id": t.id,
        "lyrics": t.lyrics,
        "lyrics_local": t.lyrics_local,
        "content": content,
        "editable": lrc_path is not None,
    }


@router.put("/{track_id}/lyrics", status_code=status.HTTP_200_OK)
def update_lyrics(
    track_id: str,
    body: Dict[str, Any] = Body(default_factory=dict),
    current_user: User = Depends(require_member_or_admin),
    db: Session = Depends(get_session),
) -> Dict[str, Any]:
    """
    Overwrite the track's .lrc file with body["content"] and re-classify it
    as synced/plain from its timestamps. Empty content deletes the file and
    resets the track to "no lyrics" (the scheduler's retry sweep will then
    try LRCLIB again). Only the .lrc is touched: lyrics are not re-embedded
    into the audio file, matching what download_lyrics does.
    """
    content = body.get("content")
    if content is None:
        content = ""
    if not isinstance(content, str):
        raise HTTPException(status_code=422, detail="content must be a string")
    if len(content) > _LYRICS_MAX_CHARS:
        raise HTTPException(status_code=413, detail="lyrics too large")

    t = db.get(Track, track_id)
    if not t:
        raise HTTPException(status_code=404, detail="track not found")
    lrc_path = _lyrics_path_for(t)
    if lrc_path is None:
        raise HTTPException(status_code=409, detail="track has no audio file yet")

    # Normalise line endings so pasted Windows/browser text yields a clean file.
    content = content.replace("\r\n", "\n").replace("\r", "\n").strip()

    try:
        if content:
            lrc_path.parent.mkdir(parents=True, exist_ok=True)
            lrc_path.write_text(content + "\n", encoding="utf-8")
            lrc_path.chmod(0o644)
            t.lyrics = _classify_lyrics(content)
            t.lyrics_local = str(lrc_path)
        else:
            if lrc_path.exists():
                lrc_path.unlink()
            t.lyrics = None
            t.lyrics_local = None
    except OSError as e:
        logger.exception("Failed to write lyrics for %s", track_id)
        raise HTTPException(status_code=500, detail=f"Failed to write lyrics: {e}")

    db.commit()

    logger.info("User %s set %s lyrics for track %s", current_user.id, t.lyrics or "no", track_id)
    return {
        "ok": True,
        "track": t.to_dict(),
        "content": content or None,
    }
