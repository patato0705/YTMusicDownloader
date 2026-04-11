# backend/routers/albums.py
"""
Album endpoints.

Endpoints :
- GET /api/albums/{album_id} - Get album details
- POST /api/albums/{album_id}/download - Download album (queue track downloads)
- DELETE /api/albums/{album_id}/download - Stop downloading album (revert to metadata)
"""
from __future__ import annotations
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..deps import get_db
from ..models import Album
from ..services import albums as albums_svc
from ..services import tracks as tracks_svc
from ..services import subscriptions as subs_svc
from ..jobs.jobqueue import enqueue_job

from backend.dependencies import require_auth, require_member_or_admin, require_admin
from backend.models import User

logger = logging.getLogger("routers.albums")

router = APIRouter(prefix="/api/albums", tags=["Albums"])


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

        if album:
            # Get artist info from DB
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
                "album": {
                    "id": album["id"],
                    "title": album["title"],
                    "artist": artist,
                    "year": album["year"],
                    "type": album["type"],
                    "thumbnails": album["thumbnails"],
                    "image_local": album["image_local"],
                    "playlist_id": album["playlist_id"],
                },
                "tracks": album.get("tracks", []),
            }

        # Not in DB - fetch from YTMusic
        logger.info(f"Album {album_id} not in DB, fetching from YTMusic")
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

        return {
            "source": "ytmusic",
            "mode": None,
            "album": {
                "id": album_data.get("id", album_id),
                "title": album_data.get("title"),
                "artist": artist,
                "year": album_data.get("year"),
                "type": album_data.get("type", "Album"),
                "thumbnail": album_data.get("cover"),
                "playlist_id": album_data.get("playlistId"),
            },
            "tracks": album_data.get("tracks", []),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"get_album failed for {album_id}")
        raise HTTPException(status_code=500, detail=f"Failed retrieving album: {e}")


@router.post("/{album_id}/download", status_code=status.HTTP_200_OK)
def download_album(
    album_id: str,
    current_user: User = Depends(require_member_or_admin),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Download an album:
    1. Fetch album from YTMusic if not in DB
    2. Set album mode to "download"
    3. Queue download jobs for all tracks

    Returns album data and count of queued jobs.
    """
    if not album_id:
        raise HTTPException(status_code=400, detail="album_id required")

    try:
        # Check if album exists in DB
        album = albums_svc.get_album_from_db(db, album_id, include_tracks=True)

        if not album:
            # Not in DB - fetch and upsert from YTMusic
            logger.info(f"Album {album_id} not in DB, fetching from YTMusic")

            # First, get album data to extract artist info
            from ..ytm_service import adapter as ytm_adapter
            album_raw = ytm_adapter.get_album(browse_id=album_id)

            # Upsert artist first if present
            artist_id = None
            artists = album_raw.get("artists", [])
            if artists and isinstance(artists, list) and len(artists) > 0:
                first_artist = artists[0]
                if isinstance(first_artist, dict):
                    artist_id = first_artist.get("id")
                    artist_name = first_artist.get("name")

                    if artist_id:
                        from ..services import artists as artists_svc
                        try:
                            artists_svc.upsert_artist(
                                db,
                                artist_id=artist_id,
                                name=artist_name,
                                thumbnails=None
                            )
                            logger.info(f"Upserted artist {artist_id}: {artist_name}")
                        except Exception as e:
                            logger.exception(f"Failed to upsert artist {artist_id}")

            # Now fetch and upsert album with artist_id
            result = albums_svc.fetch_and_upsert_album(db, browse_id=album_id, artist_id=artist_id)

            # Get the album data
            album = albums_svc.get_album_from_db(db, album_id, include_tracks=True)

            if not album:
                raise HTTPException(status_code=500, detail="Failed to fetch album from YTMusic")

            logger.info(f"Fetched and upserted album {album_id}: {result['inserted_tracks']} tracks")

        # Check if already in download mode
        album_obj = db.get(Album, album_id)
        if album_obj and album_obj.mode == "download":
            return {
                "source": "database",
                "mode": "download",
                "message": "Album already in download mode",
                "album": {
                    "id": album["id"],
                    "title": album["title"],
                    "artist_id": album["artist_id"],
                },
                "tracks_queued": 0,
            }

        # Set album mode to download
        album_obj.mode = "download"
        db.add(album_obj)

        album_artist_id = album.get("artist_id")
        logger.info(f"Set album {album_id} to download mode")

        # Auto-create light artist subscription if artist doesn't have one yet
        artist_sub_created = False
        if album_artist_id:
            existing_artist_sub = subs_svc.get_artist_subscription(db, album_artist_id)
            if not existing_artist_sub:
                from ..services import artists as artists_svc
                # Ensure artist record exists in DB
                artists_svc.upsert_artist(
                    db,
                    artist_id=album_artist_id,
                    name=album.get("artist_name") or None,
                )
                subs_svc.subscribe_to_artist(db, artist_id=album_artist_id, mode="light")
                artist_sub_created = True
                logger.info(f"Auto-created light artist subscription for {album_artist_id}")

        # Queue download jobs for all tracks
        tracks = album.get("tracks", [])
        queued_count = 0

        for track in tracks:
            track_id = track.get("id")
            if not track_id:
                continue

            # Only queue if track is not already downloaded
            if track.get("status") in ["new", "failed"]:
                try:
                    enqueue_job(
                        db,
                        job_type="download_track",
                        payload={
                            "track_id": track_id,
                            "album_id": album_id,
                        },
                        priority=10,
                        user_id=current_user.id,
                        commit=False,
                    )
                    queued_count += 1
                except Exception as e:
                    logger.exception(f"Failed to enqueue job for track {track_id}")

        # Commit mode change + download jobs
        db.commit()

        # Queue sync_artist job for light subscription (fetches all albums metadata + banner)
        if artist_sub_created and album_artist_id:
            try:
                enqueue_job(
                    db,
                    job_type="sync_artist",
                    payload={"artist_id": album_artist_id},
                    priority=15,
                    user_id=current_user.id,
                )
                logger.info(f"Queued sync_artist job for light subscription of {album_artist_id}")
            except Exception as e:
                logger.exception(f"Failed to queue sync_artist job for {album_artist_id}")

        logger.info(f"Album {album_id} set to download by user {current_user.id}: {queued_count} tracks queued")

        return {
            "source": "database",
            "mode": "download",
            "message": f"Album download started. {queued_count} tracks queued.",
            "album": {
                "id": album["id"],
                "title": album["title"],
                "artist_id": album_artist_id,
                "type": album["type"],
            },
            "tracks_total": len(tracks),
            "tracks_queued": queued_count,
            "artist_subscription_created": artist_sub_created,
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"download_album failed for {album_id}")
        raise HTTPException(status_code=500, detail=f"Failed to download album: {e}")


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
