# backend/routers/tracks.py
from __future__ import annotations
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.orm import Session

from ..deps import get_db
from ..models import Track
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
        "has_lyrics": bool(getattr(t, "has_lyrics", False)),
        "lyrics_local": getattr(t, "lyrics_local", None),
        "artist_valid": bool(getattr(t, "artist_valid", False)),
        "created_at": getattr(t, "created_at", None),
        "updated_at": getattr(t, "updated_at", None),
    }


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
        job_id = jobqueue.enqueue_job(session=db, job_type="download_track", payload=payload)
        return {"ok": True, "job_id": job_id}
    except Exception as e:
        logger.exception("download_track enqueue failed for %s", track_id)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{track_id}/ensure_lyrics", status_code=status.HTTP_202_ACCEPTED)
def ensure_lyrics(
    track_id: str,
    body: Dict[str, Any] = Body(default_factory=dict),
    current_user: User = Depends(require_member_or_admin),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Enqueue a job to fetch synchronized lyrics for the track.
    The job type used is 'ensure_track_lyrics' and payload should include:
      - artists: list[str] (optional)
      - title: str (optional)
      - album: str (optional)
      - duration: int seconds (optional)
      - dest_audio_path: str (optional)  (if you want to save LRC next to audio file)
    Returns { ok: True, job_id: <int> }.
    """
    if not track_id:
        raise HTTPException(status_code=400, detail="track_id required")
    try:
        payload: Dict[str, Any] = {"track_id": str(track_id), "user_id": current_user.id}
        for k in ("artists", "title", "album", "duration", "dest_audio_path"):
            if k in body:
                payload[k] = body.get(k)
        job_id = jobqueue.enqueue_job(session=db, job_type="ensure_track_lyrics", payload=payload)
        return {"ok": True, "job_id": job_id}
    except Exception as e:
        logger.exception("ensure_lyrics enqueue failed for %s", track_id)
        raise HTTPException(status_code=500, detail=str(e))


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
        t = tracks_svc.update_track_status(session=db, track_id=str(track_id), status="failed")
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