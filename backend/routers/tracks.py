# backend/routers/tracks.py
"""
Track endpoints.

Endpoints:
- GET /api/tracks/{track_id} - Return track info from DB
- GET /api/tracks/album/{album_id} - Return a lightweight list of tracks for the given album_id.
- POST /api/tracks/{track_id}/download - Enqueue a download job for the given track
- POST /api/tracks/{track_id}/ensure_lyrics - Fetch lyrics from LRCLIB now (queues/bumps a download_lyrics job).
- GET /api/tracks/{track_id}/lyrics - Return the track's .lrc file content.
- PUT /api/tracks/{track_id}/lyrics - Overwrite (or clear) the track's .lrc file.
- GET /api/tracks/{track_id}/mark_done - Mark a track as done and optionally provide file_path.
- DELETE /api/tracks/{track_id}/mark_failed - Mark a track as failed and optionally include an error message.
"""
from __future__ import annotations
import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.orm import Session

from ..config import MUSIC_DIR
from ..deps import get_db
from ..models import Job, Track
from ..time_utils import now_utc
from ..jobs import jobqueue
from ..services import tracks as tracks_svc

from backend.dependencies import require_auth, require_member_or_admin, require_admin
from backend.models import User

logger = logging.getLogger("routers.tracks")

router = APIRouter(prefix="/api/tracks", tags=["Tracks"])


# --- helpers --------------------------------------------------------------
def _track_to_dict(t: Track) -> Dict[str, Any]:
    """
    Minimal serializer for Track ORM instances.
    """
    return {
        "id": getattr(t, "id", None),
        "title": getattr(t, "title", None),
        "duration": getattr(t, "duration", None),
        "artists": getattr(t, "artists", None),
        "album_id": getattr(t, "album_id", None),
        "file_path": getattr(t, "file_path", None),
        "status": getattr(t, "status", None),
        "last_error": getattr(t, "last_error", None),
        "lyrics": getattr(t, "lyrics", None),
        "lyrics_local": getattr(t, "lyrics_local", None),
        "artist_valid": bool(getattr(t, "artist_valid", False)),
        "created_at": getattr(t, "created_at", None),
        "updated_at": getattr(t, "updated_at", None),
    }


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

@router.get("/{track_id}", status_code=status.HTTP_200_OK)
def get_track(
    track_id: str,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Return track info from DB (light representation).
    """
    if not track_id:
        raise HTTPException(status_code=400, detail="track_id required")
    try:
        t = tracks_svc.get_track_from_db(db, str(track_id))
        if not t:
            raise HTTPException(status_code=404, detail="track not found")
        return {"ok": True, "track": _track_to_dict(t)}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("get_track failed for %s", track_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/album/{album_id}", status_code=status.HTTP_200_OK)
def list_tracks_for_album(
    album_id: str,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Return a lightweight list of tracks for the given album_id.
    Uses services.tracks.list_tracks_for_album which returns a list of dicts.
    """
    if not album_id:
        raise HTTPException(status_code=400, detail="album_id required")
    try:
        tracks = tracks_svc.list_tracks_for_album_from_db(session=db, album_id=str(album_id))
        return {"ok": True, "tracks": tracks}
    except Exception as e:
        logger.exception("list_tracks_for_album failed for %s", album_id)
        raise HTTPException(status_code=500, detail=str(e))


class DownloadRequestModel(dict):
    """
    Simple inline model shape documentation for request body of download endpoint.
    Keys typically:
      - cover_path (optional string)
      - track_title, artist_name, album_name, year, track_number (optional metadata)
    """

@router.post("/{track_id}/download", status_code=status.HTTP_202_ACCEPTED)
def download_track(
    track_id: str,
    body: Dict[str, Any] = Body(default_factory=dict),
    current_user: User = Depends(require_member_or_admin),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Enqueue a download job for the given track (video id).
    The job type used is 'download_track' and payload includes video_id plus optional metadata from body.
    Returns { ok: True, job_id: <int> } on success.
    """
    if not track_id:
        raise HTTPException(status_code=400, detail="track_id required")
    try:
        payload: Dict[str, Any] = {"video_id": str(track_id), "user_id": current_user.id}
        # merge allowed optional metadata from body
        for k in ("artist_name", "album_name", "track_title", "track_number", "year", "cover_path"):
            if k in body:
                payload[k] = body.get(k)
        job = jobqueue.enqueue_job(session=db, job_type="download_track", payload=payload)
        return {"ok": True, "job_id": job.id}
    except Exception as e:
        logger.exception("download_track enqueue failed for %s", track_id)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{track_id}/ensure_lyrics", status_code=status.HTTP_202_ACCEPTED)
def ensure_lyrics(
    track_id: str,
    current_user: User = Depends(require_member_or_admin),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Fetch lyrics from LRCLIB for the track now (a download_lyrics job, same
    as the one queued after each download and by the scheduler's retry
    sweep). If one is already queued -- typically waiting out a 24h retry
    delay -- it's pulled forward to run immediately instead of duplicated.
    Returns { ok: True, job_id: <int>, queued: bool } (queued=False when an
    existing job was bumped).
    """
    if not track_id:
        raise HTTPException(status_code=400, detail="track_id required")
    t = tracks_svc.get_track_from_db(db, str(track_id))
    if not t:
        raise HTTPException(status_code=404, detail="track not found")
    if not t.file_path:
        raise HTTPException(status_code=409, detail="track has no audio file yet")
    try:
        pending = (
            db.query(Job)
            .filter(Job.type == "download_lyrics", Job.status.in_(["queued", "reserved"]))
            .all()
        )
        for job in pending:
            if isinstance(job.payload, dict) and job.payload.get("track_id") == str(track_id):
                if job.status == "queued":
                    job.scheduled_at = now_utc()
                    db.commit()
                return {"ok": True, "job_id": job.id, "queued": False}
        job = jobqueue.enqueue_job(
            session=db,
            job_type="download_lyrics",
            payload={"track_id": str(track_id), "mode": "normal"},
            user_id=current_user.id,
        )
        return {"ok": True, "job_id": job.id, "queued": True}
    except Exception as e:
        logger.exception("ensure_lyrics enqueue failed for %s", track_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{track_id}/lyrics", status_code=status.HTTP_200_OK)
def get_lyrics(
    track_id: str,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Return the raw content of the track's .lrc file.
    `content` is null when the track has no lyrics file on disk; `editable`
    tells the client whether a PUT could succeed (audio file present).
    """
    if not track_id:
        raise HTTPException(status_code=400, detail="track_id required")
    t = tracks_svc.get_track_from_db(db, str(track_id))
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
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Overwrite the track's .lrc file with body["content"] and re-classify it
    as synced/plain from its timestamps. Empty content deletes the file and
    resets the track to "no lyrics" (the scheduler's retry sweep will then
    try LRCLIB again). Only the .lrc is touched: lyrics are not re-embedded
    into the audio file, matching what download_lyrics does.
    """
    if not track_id:
        raise HTTPException(status_code=400, detail="track_id required")
    content = body.get("content")
    if content is None:
        content = ""
    if not isinstance(content, str):
        raise HTTPException(status_code=422, detail="content must be a string")
    if len(content) > _LYRICS_MAX_CHARS:
        raise HTTPException(status_code=413, detail="lyrics too large")

    t = tracks_svc.get_track_from_db(db, str(track_id))
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

    try:
        db.add(t)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("DB commit failed updating lyrics for %s", track_id)
        raise HTTPException(status_code=500, detail="DB commit failed")

    logger.info("User %s set %s lyrics for track %s", current_user.id, t.lyrics or "no", track_id)
    return {
        "ok": True,
        "track": _track_to_dict(t),
        "content": content or None,
    }


@router.post("/{track_id}/mark_done", status_code=status.HTTP_200_OK)
def mark_done(
    track_id: str,
    body: Optional[Dict[str, Any]] = Body(default_factory=dict),
    current_user: User = Depends(require_member_or_admin),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Mark a track as done and optionally provide file_path.
    Uses services.tracks.mark_track_done and commits the DB.
    """
    if not track_id:
        raise HTTPException(status_code=400, detail="track_id required")
    try:
        file_path = body.get("file_path") if isinstance(body, dict) else None
        t = tracks_svc.update_track_status(session=db, track_id=str(track_id), file_path=file_path, status="done")
        if t is None:
            raise HTTPException(status_code=404, detail="track not found")
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("DB commit failed marking track done %s", track_id)
            raise HTTPException(status_code=500, detail="DB commit failed")
        return {"ok": True, "track": _track_to_dict(t)}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("mark_done failed for %s", track_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{track_id}/mark_failed", status_code=status.HTTP_200_OK)
def mark_failed(
    track_id: str,
    body: Optional[Dict[str, Any]] = Body(default_factory=dict),
    current_user: User = Depends(require_member_or_admin),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Mark a track as failed and optionally include an error message.
    Uses services.tracks.mark_track_failed and commits.
    """
    if not track_id:
        raise HTTPException(status_code=400, detail="track_id required")
    try:
        err_msg = body.get("error") if isinstance(body, dict) else None
        t = tracks_svc.update_track_status(session=db, track_id=str(track_id), status="failed", error=err_msg)
        if t is None:
            raise HTTPException(status_code=404, detail="track not found")
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("DB commit failed marking track failed %s", track_id)
            raise HTTPException(status_code=500, detail="DB commit failed")
        return {"ok": True, "track": _track_to_dict(t)}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("mark_failed failed for %s", track_id)
        raise HTTPException(status_code=500, detail=str(e))