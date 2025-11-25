# backend/routers/albums.py
"""
Album endpoints:
- GET /api/albums/{album_id} - Get album details
- POST /api/albums/{album_id}/follow - Follow album (queue downloads)
- DELETE /api/albums/{album_id}/follow - Unfollow album
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
    Returns album data with tracks list and subscription status.
    """
    if not album_id:
        raise HTTPException(status_code=400, detail="album_id required")
    
    try:
        # Try DB first using service layer
        album = albums_svc.get_album_from_db(db, album_id, include_tracks=True)
        
        if album:
            # Check subscription status
            subscription = subs_svc.get_album_subscription(db, album_id)
            
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
                "followed": subscription is not None,
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
            "followed": False,
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


@router.post("/{album_id}/follow", status_code=status.HTTP_200_OK)
def follow_album(
    album_id: str,
    current_user: User = Depends(require_member_or_admin),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Follow an album:
    1. Fetch album from YTMusic if not in DB
    2. Create album subscription
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
                                thumbnails=None  # Could extract from album or fetch artist separately
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
        
        # Check if already followed
        existing_sub = subs_svc.get_album_subscription(db, album_id)
        if existing_sub:
            return {
                "source": "database",
                "followed": True,
                "message": "Album already followed",
                "album": {
                    "id": album["id"],
                    "title": album["title"],
                    "artist_id": album["artist_id"],
                },
                "tracks_queued": 0,
            }
        
        # Create album subscription
        subscription = subs_svc.subscribe_to_album(
            db,
            album_id=album_id,
            artist_id=album.get("artist_id"),
            mode="download"
        )
        logger.info(f"Created album subscription for {album_id} (user_id={current_user.id})")
        
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
                        priority=0,
                        user_id=current_user.id,
                        commit=False,  # Don't commit yet
                    )
                    queued_count += 1
                except Exception as e:
                    logger.exception(f"Failed to enqueue job for track {track_id}")

        # Commit everything once
        db.commit()
        
        logger.info(f"Album {album_id} followed by user {current_user.id}: {queued_count} tracks queued for download")
        
        return {
            "source": "database",
            "followed": True,
            "message": f"Album followed successfully. {queued_count} tracks queued for download.",
            "album": {
                "id": album["id"],
                "title": album["title"],
                "artist_id": album["artist_id"],
                "type": album["type"],
            },
            "tracks_total": len(tracks),
            "tracks_queued": queued_count,
        }
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"follow_album failed for {album_id}")
        raise HTTPException(status_code=500, detail=f"Failed to follow album: {e}")


@router.delete("/{album_id}/follow", status_code=status.HTTP_200_OK)
def unfollow_album(
    album_id: str,
    current_user: User = Depends(require_member_or_admin),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Unfollow an album:
    - Removes album subscription
    - Does NOT delete album or tracks from database
    - Does NOT cancel pending download jobs
    """
    if not album_id:
        raise HTTPException(status_code=400, detail="album_id required")
    
    try:
        # Check if album exists
        album = albums_svc.get_album_from_db(db, album_id, include_tracks=False)
        if not album:
            raise HTTPException(status_code=404, detail="Album not found")
        
        # Unsubscribe
        success = subs_svc.unsubscribe_from_album(db, album_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Album is not followed")
        
        db.commit()
        
        logger.info(f"Album {album_id} unfollowed")
        
        return {
            "message": "Album unfollowed successfully",
            "album": {
                "id": album["id"],
                "title": album["title"],
            },
            "followed": False,
        }
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"unfollow_album failed for {album_id}")
        raise HTTPException(status_code=500, detail=f"Failed to unfollow album: {e}")