# backend/routers/artists.py
from __future__ import annotations
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..deps import get_db
from ..services import artists as artists_svc
from ..services import albums as albums_svc
from ..services import tracks as tracks_svc
from ..services import subscriptions as subs_svc
from ..jobs.jobqueue import enqueue_job
from backend.dependencies import require_auth, require_member_or_admin, require_admin
from backend.models import User

from ..models import Artist, AlbumSubscription

logger = logging.getLogger("routers.artists")

router = APIRouter(prefix="/api/artists", tags=["Artists"])


@router.get("/{artist_id}", status_code=status.HTTP_200_OK)
def get_artist(
    artist_id: str,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get artist info - tries DB first, then fetches from YTMusic if not found.
    Returns full artist data including albums list.
    """
    if not artist_id:
        raise HTTPException(status_code=400, detail="artist_id required")

    try:
        # Try to get from DB first
        artist_obj = db.get(Artist, str(artist_id))
        
        if artist_obj:
            # Artist exists in DB - get albums from DB
            from ..services import albums as albums_svc
            
            albums = albums_svc.list_albums_for_artist_from_db(session=db, artist_id=str(artist_id))
            
            return {
                "ok": True,
                "source": "database",
                "followed": getattr(artist_obj, "followed", False),
                "artist": {
                    "id": artist_obj.id,
                    "name": artist_obj.name,
                    "thumbnails": artist_obj.thumbnails,
                    "image_local": artist_obj.image_local,
                },
                "albums": albums,
            }
        
        # Not in DB - fetch from YTMusic adapter
        logger.info(f"Artist {artist_id} not in DB, fetching from YTMusic")
        from ..ytm_service import adapter as ytm_adapter
        
        artist_data = ytm_adapter.get_artist(str(artist_id))
        if not artist_data:
            raise HTTPException(status_code=404, detail="Artist not found in YTMusic")
        
        return {
            "ok": True,
            "source": "ytmusic",
            "followed": False,
            "artist": {
                "id": artist_data.get("id", artist_id),
                "name": artist_data.get("name"),
                "thumbnail": artist_data.get("thumbnail", []),
                "image_local": None,
            },
            "albums": artist_data.get("albums"),
            "singles": artist_data.get("singles"),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("get_artist failed for %s", artist_id)
        raise HTTPException(status_code=500, detail=f"Failed retrieving artist: {e}")


@router.post("/{artist_id}/follow", status_code=status.HTTP_200_OK)
def follow_artist(
    artist_id: str,
    current_user: User = Depends(require_member_or_admin),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Follow an artist - FAST version:
    1. Fetch artist data from YTMusic (just metadata + album list)
    2. Mark artist as followed and create subscriptions
    3. Queue an import_artist job to handle the heavy lifting
    4. Return immediately with artist info
    
    The actual album/track fetching happens asynchronously via worker.
    Response time: ~2-3 seconds instead of 15-35 seconds.
    """
    if not artist_id:
        raise HTTPException(status_code=400, detail="artist_id required")
    
    try:
        logger.info(f"Following artist {artist_id}")
        
        # Step 1: Fetch basic artist data from YTMusic (fast - just metadata)
        artist_data = artists_svc.fetch_and_upsert_artist(db, artist_id)
        
        artist_name = artist_data.get("name", "Unknown Artist")
        albums_list = artist_data.get("albums", [])
        singles_list = artist_data.get("singles", [])
        total_releases = len(albums_list) + len(singles_list)
        
        logger.info(f"Fetched artist {artist_name}: {len(albums_list)} albums, {len(singles_list)} singles")
        
        # Step 2: Get artist object and check if already followed
        artist_obj = db.get(Artist, artist_id)
        if not artist_obj:
            raise HTTPException(status_code=404, detail="Artist not found after fetch")
        
        if artist_obj.followed:
            existing_sub = subs_svc.get_artist_subscription(db, artist_id)
            if existing_sub:
                return {
                    "source": "database",
                    "followed": True,
                    "message": "Artist already followed",
                    "artist": {
                        "id": artist_id,
                        "name": artist_name,
                    },
                    "albums_count": total_releases,
                }
        
        # Step 3: Mark artist as followed and create artist subscription
        artist_obj.followed = True
        db.add(artist_obj)
        
        artist_subscription = subs_svc.subscribe_to_artist(
            db,
            artist_id=artist_id,
            mode="full",
            sync_interval_hours=24,
        )
        
        # Commit artist follow status and subscription
        db.commit()
        logger.info(f"Marked artist {artist_id} as followed")
        
        # Step 4: Queue a sync_artist job to import all albums/tracks asynchronously
        try:
            job = enqueue_job(
                db,
                job_type="sync_artist",
                payload={
                    "artist_id": artist_id,
                },
                priority=5,  # Higher priority for new follows
                user_id=current_user.id,
                commit=True,
            )
            logger.info(f"Queued sync_artist job {job.id} for artist {artist_id}")
        except Exception as e:
            logger.exception(f"Failed to queue sync_artist job for {artist_id}")
            # Don't fail the request if job queueing fails
        
        # Return immediately - user doesn't have to wait
        return {
            "source": "ytmusic",
            "followed": True,
            "message": f"Artist followed successfully. Importing {total_releases} releases in the background.",
            "artist": {
                "id": artist_id,
                "name": artist_name,
            },
            "albums_count": total_releases,
            "status": "importing",
            "note": "Albums and tracks are being imported in the background. Check back in a few minutes.",
        }
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"follow_artist failed for {artist_id}")
        raise HTTPException(status_code=500, detail=f"Failed to follow artist: {e}")


@router.delete("/{artist_id}/follow", status_code=status.HTTP_200_OK)
def unfollow_artist(
    artist_id: str,
    current_user: User = Depends(require_member_or_admin),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Unfollow an artist:
    - Marks artist as not followed
    - Disables artist subscription
    - Removes all album subscriptions for this artist
    - Does NOT delete artist, albums, or tracks from database
    - Does NOT cancel pending download jobs
    """
    if not artist_id:
        raise HTTPException(status_code=400, detail="artist_id required")
    
    try:
        # Check if artist exists
        artist_obj = artists_svc.get_artist_from_db(db, artist_id)
        if not artist_obj:
            raise HTTPException(status_code=404, detail="Artist not found")
        
        # Mark artist as not followed
        if artist_obj.followed:
            artist_obj.followed = False
            db.add(artist_obj)
        
        # Unsubscribe from artist
        success = subs_svc.unsubscribe_from_artist(db, artist_id)

        if not success:
            raise HTTPException(status_code=404, detail="Artist is not followed")
        
        # Remove all album subscriptions for this artist
        from ..models import AlbumSubscription
        album_subs = (
            db.query(AlbumSubscription)
            .filter(AlbumSubscription.artist_id == artist_id)
            .all()
        )
        
        removed_album_subs = 0
        for sub in album_subs:
            try:
                db.delete(sub)
                removed_album_subs += 1
            except Exception as e:
                logger.exception(f"Failed to remove album subscription {sub.id}")
        
        db.commit()
        
        logger.info(f"Artist {artist_id} unfollowed: removed {removed_album_subs} album subscriptions")
        
        return {
            "message": "Artist unfollowed successfully",
            "artist": {
                "id": artist_id,
                "name": artist_obj.name,
            },
            "followed": False,
            "album_subscriptions_removed": removed_album_subs,
        }
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"unfollow_artist failed for {artist_id}")
        raise HTTPException(status_code=500, detail=f"Failed to unfollow artist: {e}")