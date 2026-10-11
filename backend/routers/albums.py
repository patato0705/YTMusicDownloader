# backend/routers/albums.py
"""
Album endpoints.

Endpoints :
- GET /api/albums/{album_id} - Get album details
- POST /api/albums/{album_id}/download - Download album (queues its import, which queues the downloads)
- POST /api/albums/{album_id}/retry - Requeue tracks of a downloaded album that aren't on disk,
  or its import when it has no tracks yet
- DELETE /api/albums/{album_id}/download - Stop downloading album (revert to metadata)
"""
from __future__ import annotations
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..deps import get_db
from ..ytm_service.adapter import YTMusicUnavailable
from ..models import Album, Job, Track
from ..services import albums as albums_svc
from ..services import tracks as tracks_svc
from ..services import subscriptions as subs_svc
from ..jobs.priorities import Origin

from backend.dependencies import require_auth, require_member_or_admin, require_admin
from backend.models import User

logger = logging.getLogger("routers.albums")

router = APIRouter(prefix="/api/albums", tags=["Albums"])


def _ytmusic_unavailable() -> HTTPException:
    """YouTube Music couldn't be read: a code the frontend translates."""
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="ytmusic_unavailable")


def _import_waiting(db: Session, album_id: str) -> bool:
    """Whether an import_album job for this album is waiting or running."""
    return db.query(Job.id).filter(
        Job.type == "import_album",
        Job.status.in_(("queued", "reserved")),
        Job.payload["browse_id"].as_string() == album_id,
    ).first() is not None


@router.get("/{album_id}", status_code=status.HTTP_200_OK)
def get_album(
    album_id: str,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get album details - tries DB first, then fetches from YTMusic if not found.
    Returns album data with tracks list and mode.
    """
    if not album_id:
        raise HTTPException(status_code=400, detail="album_id required")

    try:
        # Try DB first using service layer
        album = albums_svc.get_album_from_db(db, album_id, include_tracks=True)

        if album and album.get("tracks"):
            # Album in DB with tracks - return from DB
            artist = None
            if album.get("artist_id"):
                from ..services import artists as artists_svc
                artist_obj = artists_svc.get_artist_from_db(db, album["artist_id"])
                if artist_obj:
                    artist = {
                        "id": artist_obj.id,
                        "name": artist_obj.name
                    }

            return {
                "source": "database",
                "mode": album.get("mode", "metadata"),
                "needs_import": False,
                "album": {
                    "id": album["id"],
                    "title": album["title"],
                    "artist": artist,
                    "year": album["year"],
                    "type": album["type"],
                    "image_local": album["image_local"],
                    "playlist_id": album["playlist_id"],
                    "genres": album["genres"],
                },
                "tracks": album.get("tracks", []),
            }

        # Not in DB or metadata-mode with no tracks - fetch from YTMusic
        # Keep track of whether album exists in DB (metadata mode, no tracks)
        db_mode = album.get("mode") if album else None

        logger.info(f"Album {album_id} fetching tracks from YTMusic (db_mode={db_mode})")
        from ..ytm_service import adapter as ytm_adapter

        album_data = ytm_adapter.get_album(browse_id=album_id)

        if not album_data or not album_data.get("id"):
            raise HTTPException(status_code=404, detail="Album not found in YTMusic")

        # Extract artist info from artists list
        artist = None
        artists = album_data.get("artists", [])
        if artists and isinstance(artists, list) and len(artists) > 0:
            first_artist = artists[0]
            if isinstance(first_artist, dict):
                artist = {
                    "id": first_artist.get("id"),
                    "name": first_artist.get("name")
                }

        # Use DB info when the album exists in library, otherwise pure YTMusic.
        # The tracks come from YTMusic either way, so they carry no download
        # state; "database" only tells the client to keep refreshing, which
        # is worth it for a download-mode album whose import hasn't landed.
        if album:
            return {
                "source": "database" if db_mode == "download" else "ytmusic",
                "mode": db_mode,
                # A download-mode album whose import failed for good: the
                # tracks shown are YTMusic's, none are in the DB to retry, so
                # Retry has to import it again
                "needs_import": db_mode == "download" and not _import_waiting(db, album_id),
                "album": {
                    "id": album["id"],
                    "title": album["title"],
                    "artist": artist,
                    "year": album["year"],
                    "type": album["type"],
                    "image_local": album["image_local"],
                    "playlist_id": album["playlist_id"],
                    "genres": album["genres"],
                },
                "tracks": album_data.get("tracks", []),
            }

        return {
            "source": "ytmusic",
            "mode": None,
            "needs_import": False,
            "album": {
                "id": album_data.get("id", album_id),
                "title": album_data.get("title"),
                "artist": artist,
                "year": album_data.get("year"),
                "type": album_data.get("type", "Album"),
                "thumbnail": album_data.get("cover"),
                "playlist_id": album_data.get("playlistId"),
                "genres": [],
            },
            "tracks": album_data.get("tracks", []),
        }

    except HTTPException:
        raise
    except YTMusicUnavailable:
        raise _ytmusic_unavailable()
    except Exception as e:
        logger.exception(f"get_album failed for {album_id}")
        raise HTTPException(status_code=500, detail=f"Failed retrieving album: {e}")


@router.post("/{album_id}/download", status_code=status.HTTP_200_OK)
def download_album(
    album_id: str,
    current_user: User = Depends(require_member_or_admin),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Download an album (see subscriptions.start_album_download)."""
    if not album_id:
        raise HTTPException(status_code=400, detail="album_id required")

    try:
        result = subs_svc.start_album_download(
            db, album_id, origin=Origin.USER, user_id=current_user.id
        )
        album_obj = result["album"]
        album_info = {
            "id": album_obj.id,
            "title": album_obj.title,
            "artist_id": album_obj.artist_id,
            "type": album_obj.type,
        }
        if not result["started"]:
            return {
                "source": "database",
                "mode": "download",
                "message": "Album already in download mode",
                "album": album_info,
                "artist_subscription_created": False,
            }
        logger.info(f"Album {album_id} set to download by user {current_user.id}")
        return {
            "source": "database",
            "mode": "download",
            "message": "Album download started",
            "album": album_info,
            "artist_subscription_created": result["artist_subscription_created"],
        }

    except HTTPException:
        db.rollback()
        raise
    except YTMusicUnavailable:
        db.rollback()
        raise _ytmusic_unavailable()
    except Exception as e:
        db.rollback()
        logger.exception(f"download_album failed for {album_id}")
        raise HTTPException(status_code=500, detail=f"Failed to download album: {e}")


@router.post("/{album_id}/retry", status_code=status.HTTP_200_OK)
def retry_album_download(
    album_id: str,
    current_user: User = Depends(require_member_or_admin),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Requeue every track of a download-mode album that isn't on disk and
    isn't already waiting: failed tracks, and any left "available" (e.g.
    after a cancelled job).

    An album with no tracks at all (its import failed for good) has nothing
    to requeue: its import is queued again instead.
    """
    album_obj = db.get(Album, album_id)
    if not album_obj:
        raise HTTPException(status_code=404, detail="Album not found")
    if album_obj.mode != "download":
        raise HTTPException(status_code=400, detail="Album is not in download mode")

    try:
        if db.query(Track.id).filter(Track.album_id == album_id).first() is None:
            subs_svc.queue_album_imports(
                db, [album_id], artist_id=album_obj.artist_id, user_id=current_user.id, origin=Origin.USER
            )
            db.commit()
            logger.info(f"User {current_user.id} retried album {album_id}: no tracks, import queued")
            return {"album_id": album_id, "tracks_queued": 0, "import_queued": True}

        queued = tracks_svc.queue_album_downloads(
            db, album_id, user_id=current_user.id, origin=Origin.USER
        )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.exception(f"retry_album_download failed for {album_id}")
        raise HTTPException(status_code=500, detail=f"Failed to retry album: {e}")

    logger.info(f"User {current_user.id} retried album {album_id}: {queued} tracks queued")
    return {"album_id": album_id, "tracks_queued": queued, "import_queued": False}


@router.delete("/{album_id}/download", status_code=status.HTTP_200_OK)
def cancel_album_download(
    album_id: str,
    current_user: User = Depends(require_member_or_admin),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Revert album to metadata mode:
    - Sets album mode back to "metadata"
    - Clears download status
    - Does NOT delete album, tracks, or files from database/disk
    """
    if not album_id:
        raise HTTPException(status_code=400, detail="album_id required")

    try:
        # Check if album exists
        album = albums_svc.get_album_from_db(db, album_id, include_tracks=False)
        if not album:
            raise HTTPException(status_code=404, detail="Album not found")

        album_obj = db.get(Album, album_id)
        if not album_obj or album_obj.mode != "download":
            raise HTTPException(status_code=404, detail="Album is not in download mode")

        # Revert to metadata mode
        subs_svc.clear_album_download(db, album_id)

        db.commit()

        logger.info(f"Album {album_id} reverted to metadata mode")

        return {
            "message": "Album reverted to metadata mode",
            "album": {
                "id": album["id"],
                "title": album["title"],
            },
            "mode": "metadata",
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"cancel_album_download failed for {album_id}")
        raise HTTPException(status_code=500, detail=f"Failed to cancel album download: {e}")
