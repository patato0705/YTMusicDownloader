# backend/routers/albums.py
"""
Album endpoints.

Endpoints :
- GET /api/albums/{album_id} - Get album details
- POST /api/albums/{album_id}/download - Download album (queues the downloads of its tracks)
- POST /api/albums/{album_id}/retry - Requeue tracks of a downloaded album that aren't on disk,
  or its import when it has no tracks yet
"""
from __future__ import annotations
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db import get_session
from ..dependencies import require_auth, require_member_or_admin
from ..jobs.jobqueue import pending_jobs
from ..jobs.priorities import Origin
from ..models import Album, Track, User
from ..services import albums as albums_svc
from ..services import subscriptions as subs_svc
from ..services import tracks as tracks_svc
from ..ytm_service import adapter as ytm_adapter

logger = logging.getLogger("routers.albums")

router = APIRouter(prefix="/api/albums", tags=["Albums"])


def ytmusic_unavailable() -> HTTPException:
    """YouTube Music couldn't be read: a code the frontend translates."""
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="ytmusic_unavailable")


def _ytmusic_track(track: Dict[str, Any]) -> Dict[str, Any]:
    """A YTMusic track in the shape of the DB ones (Track.to_dict), with no download state."""
    return {
        "id": track["id"],
        "title": track["title"],
        "artists": track["artists"],
        "track_number": track["track_number"],
        "duration": track["duration_seconds"] or None,
    }


@router.get("/{album_id}", status_code=status.HTTP_200_OK)
def get_album(
    album_id: str,
    current_user: User = Depends(require_auth),
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """
    An album and its tracks: from the DB when its tracks are there,
    otherwise from YTMusic (merged with what the DB knows of it).

    "source" is "database" when the client should keep refreshing it with
    the job queue: always for a download-mode album, even one whose tracks
    still come from YTMusic because its import hasn't landed. "needs_import"
    marks a download-mode album without tracks and with no import waiting:
    Retry has to import it again.
    """
    album = albums_svc.get_album_from_db(session, album_id)
    db_tracks = album.pop("tracks") if album else []
    if db_tracks:
        return {"source": "database", "mode": album["mode"], "needs_import": False, "album": album, "tracks": db_tracks}

    try:
        album_data = ytm_adapter.get_album(browse_id=album_id)
    except ytm_adapter.YTMusicUnavailable:
        raise ytmusic_unavailable()

    artist = album_data["artists"][0] if album_data["artists"] else None
    tracks = [_ytmusic_track(t) for t in album_data["tracks"]]
    if album:
        downloading = album["mode"] == "download"
        return {
            "source": "database" if downloading else "ytmusic",
            "mode": album["mode"],
            "needs_import": downloading and not pending_jobs(session, "import_album", browse_id=album_id),
            "album": {**album, "artist": album["artist"] or artist},
            "tracks": tracks,
        }
    return {
        "source": "ytmusic",
        "mode": None,
        "needs_import": False,
        "album": {
            "id": album_data["id"],
            "title": album_data["title"],
            "artist": artist,
            "year": album_data["year"],
            "type": album_data["type"],
            "thumbnail": album_data["cover"],
            "genres": [],
        },
        "tracks": tracks,
    }


@router.post("/{album_id}/download", status_code=status.HTTP_200_OK)
def download_album(
    album_id: str,
    current_user: User = Depends(require_member_or_admin),
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """Download an album (see subscriptions.start_album_download)."""
    try:
        result = subs_svc.start_album_download(session, album_id, origin=Origin.USER, user_id=current_user.id)
    except ytm_adapter.YTMusicUnavailable:
        session.rollback()
        raise ytmusic_unavailable()
    if result["started"]:
        logger.info("Album %s set to download by user %s", album_id, current_user.id)
    return {
        "started": result["started"],
        "artist_subscription_created": result["artist_subscription_created"],
    }


@router.post("/{album_id}/retry", status_code=status.HTTP_200_OK)
def retry_album_download(
    album_id: str,
    current_user: User = Depends(require_member_or_admin),
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """
    Requeue every track of a download-mode album that isn't on disk and
    isn't already waiting: failed tracks, and any left "available" (e.g.
    after a cancelled job).

    An album with no tracks at all (its import failed for good) has nothing
    to requeue: its import is queued again instead.
    """
    album = session.get(Album, album_id)
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    if album.mode != "download":
        raise HTTPException(status_code=400, detail="Album is not in download mode")

    if session.query(Track.id).filter(Track.album_id == album_id).first() is None:
        subs_svc.queue_album_imports(
            session, [album_id], artist_id=album.artist_id, user_id=current_user.id, origin=Origin.USER
        )
        session.commit()
        logger.info("User %s retried album %s: no tracks, import queued", current_user.id, album_id)
        return {"album_id": album_id, "tracks_queued": 0, "import_queued": True}

    queued = tracks_svc.queue_album_downloads(session, album_id, user_id=current_user.id, origin=Origin.USER)
    session.commit()
    logger.info("User %s retried album %s: %s tracks queued", current_user.id, album_id, queued)
    return {"album_id": album_id, "tracks_queued": queued, "import_queued": False}
