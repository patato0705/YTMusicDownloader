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
    Follow an artist:
    1. Fetch artist data from YTMusic (includes albums/singles list)
    2. Fetch and upsert ALL albums/singles with their tracks
    3. Mark artist as followed
    4. Create artist subscription
    5. Create album subscriptions for all albums
    6. Queue download jobs for all tracks
    
    This can take 15-35 seconds depending on number of albums.
    Returns summary with counts.
    """
    if not artist_id:
        raise HTTPException(status_code=400, detail="artist_id required")
    
    try:
        logger.info(f"Following artist {artist_id}")
        
        # Step 1: Fetch artist data from YTMusic
        # This returns: {artist_id, name, description, thumbnails, albums: [...], singles: [...]}
        artist_data = artists_svc.fetch_and_upsert_artist(db, artist_id)
        
        artist_name = artist_data.get("name", "Unknown Artist")
        albums_list = artist_data.get("albums", [])
        singles_list = artist_data.get("singles", [])
        total_releases = len(albums_list) + len(singles_list)
        
        logger.info(f"Fetched artist {artist_name}: {len(albums_list)} albums, {len(singles_list)} singles")
        
        # Check if already followed
        artist_obj = artists_svc.get_artist_from_db(db, artist_id)
        if artist_obj and artist_obj.followed:
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
                    "tracks_queued": 0,
                }
        
        # Step 2: Fetch and upsert ALL albums/singles with their tracks
        # This is the slow part - fetches full data for each album
        logger.info(f"Fetching {total_releases} releases for artist {artist_id}...")
        
        albums_result = albums_svc.fetch_and_upsert_albums_for_artist(
            db,
            artist_id=artist_id,
            albums=albums_list,
            singles=singles_list,
        )
        
        albums_processed = albums_result["albums_processed"]
        tracks_inserted = albums_result["tracks_inserted"]
        tracks_updated = albums_result["tracks_updated"]
        total_tracks = tracks_inserted + tracks_updated
        
        logger.info(f"Processed {albums_processed} albums with {total_tracks} total tracks")
        
        # Step 3: Mark artist as followed
        if artist_obj:
            artist_obj.followed = True
            db.add(artist_obj)
        
        # Step 4: Create artist subscription
        artist_subscription = subs_svc.subscribe_to_artist(
            db,
            artist_id=artist_id,
            mode="full",
            sync_interval_hours=24,
        )
        logger.info(f"Created artist subscription for {artist_id}")
        
        # Step 5: Create album subscriptions for all albums
        album_sub_count = 0
        for album_detail in albums_result.get("details", []):
            album_id = album_detail.get("album_id")
            if not album_id:
                continue
            
            try:
                subs_svc.subscribe_to_album(
                    db,
                    album_id=album_id,
                    artist_id=artist_id,
                    mode="download"
                )
                album_sub_count += 1
            except Exception as e:
                logger.exception(f"Failed to create album subscription for {album_id}")
        
        logger.info(f"Created {album_sub_count} album subscriptions")
        
        # Step 6: Queue download jobs for all tracks
        queued_count = 0
        jobs_to_create = []  # ← Collect all jobs first

        for album_detail in albums_result.get("details", []):
            album_id = album_detail.get("album_id")
            if not album_id:
                continue
            
            # Get tracks for this album
            tracks = tracks_svc.list_tracks_for_album_from_db(db, album_id)
            
            for track in tracks:
                track_id = track.get("id")
                if not track_id:
                    continue
                
                # Only queue if track needs downloading
                if track.get("status") in ["new", "failed"]:
                    jobs_to_create.append({
                        "track_id": track_id,
                        "album_id": album_id,
                        "artist_id": artist_id,
                        "user_id": current_user.id
                    })

        # Now create all jobs in batch WITHOUT committing each one
        for payload in jobs_to_create:
            try:
                enqueue_job(
                    db,
                    job_type="download_track",
                    payload=payload,
                    priority=0,
                    commit=False,  # ← DON'T commit yet
                )
                queued_count += 1
            except Exception as e:
                logger.exception(f"Failed to enqueue job for track {payload.get('track_id')}")

        # Commit everything once at the end
        db.commit()
        
        logger.info(f"Artist {artist_id} followed: {queued_count} tracks queued for download")
        
        return {
            "source": "ytmusic",
            "followed": True,
            "message": f"Artist followed successfully. {queued_count} tracks queued for download.",
            "artist": {
                "id": artist_id,
                "name": artist_name,
            },
            "albums_processed": albums_processed,
            "tracks_total": total_tracks,
            "tracks_queued": queued_count,
            "estimated_download_time": f"~{queued_count * 10} seconds",  # Rough estimate: 10 sec per track
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