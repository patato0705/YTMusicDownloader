# backend/routers/artists.py

"""
Artist endpoints.

Endpoints :
- GET /api/artists/{artist_id} - Get artist details
- POST /api/artists/{artist_id}/follow - Follow artist (full mode)
- DELETE /api/artists/{artist_id}/follow - Unfollow artist
- PATCH /api/artists/{artist_id}/mode - Update subscription mode
"""
from __future__ import annotations
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..deps import get_db
from ..services import artists as artists_svc
from ..services import albums as albums_svc
from ..services import subscriptions as subs_svc
from ..jobs.jobqueue import enqueue_job
from backend.dependencies import require_auth, require_member_or_admin
from backend.models import User, Artist

logger = logging.getLogger("routers.artists")

router = APIRouter(prefix="/api/artists", tags=["Artists"])


@router.get("/{artist_id}", status_code=status.HTTP_200_OK)
def get_artist(
    artist_id: str,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get artist info with smart fetching logic.
    
    Priority:
    1. If artist has NO subscription → fetch from YTMusic (cloud data)
    2. If artist has subscription (light OR full) but mode="light" → fetch from YTMusic + DB status
    3. If artist has subscription mode="full" → use DB (full data)
    """
    if not artist_id:
        raise HTTPException(status_code=400, detail="artist_id required")

    try:
        # Get artist subscription status
        artist_sub = subs_svc.get_artist_subscription(db, artist_id)
        artist_obj = db.get(Artist, str(artist_id))
        
        # Case 1 & 2: No subscription OR light mode → fetch from YTMusic
        if not artist_sub or artist_sub.mode == "light":
            logger.info(f"Artist {artist_id} not fully followed, fetching from YTMusic")
            
            from ..ytm_service import adapter as ytm_adapter
            artist_data = ytm_adapter.get_artist(str(artist_id))
            
            if not artist_data:
                raise HTTPException(status_code=404, detail="Artist not found in YTMusic")
            
            # Get DB albums for status flags
            db_albums_map = {}
            if artist_obj:
                db_albums = albums_svc.list_albums_for_artist_from_db(session=db, artist_id=str(artist_id))
                for db_album in db_albums:
                    album_id = db_album.get("id")
                    if album_id:
                        album_sub = subs_svc.get_album_subscription(db, album_id)
                        db_albums_map[album_id] = {
                            "in_database": True,
                            "mode": album_sub.mode if album_sub else None,
                        }
            
            # Merge YTMusic albums with DB status
            ytmusic_albums = artist_data.get("albums", [])
            ytmusic_singles = artist_data.get("singles", [])
            all_ytmusic_albums = ytmusic_albums + ytmusic_singles
            
            albums_with_status = []
            for yt_album in all_ytmusic_albums:
                album_id = yt_album.get("id") or yt_album.get("browseId")
                db_status = db_albums_map.get(album_id, {
                    "in_database": False,
                    "mode": None,
                })
                
                albums_with_status.append({
                    **yt_album,
                    **db_status,
                })
            
            return {
                "ok": True,
                "source": "ytmusic",
                "subscription_mode": artist_sub.mode if artist_sub else None,
                "artist": {
                    "id": artist_data.get("id", artist_id),
                    "name": artist_data.get("name"),
                    "thumbnails": artist_data.get("thumbnails", []),
                    "image_local": artist_obj.image_local if artist_obj else None,
                },
                "albums": albums_with_status,
            }
        
        # Case 3: Full subscription → use DB (has complete data)
        if not artist_obj:
            raise HTTPException(status_code=404, detail="Artist not found in database")

        albums = albums_svc.list_albums_for_artist_from_db(session=db, artist_id=str(artist_id))

        # Add subscription mode to each album
        for album in albums:
            album_id = album.get("id")
            if album_id:
                album_sub = subs_svc.get_album_subscription(db, album_id)
                album["mode"] = album_sub.mode if album_sub else None
                album["in_database"] = True

        return {
            "ok": True,
            "source": "database",
            "subscription_mode": "full",
            "artist": {
                "id": artist_obj.id,
                "name": artist_obj.name,
                "thumbnails": artist_obj.thumbnails,
                "image_local": artist_obj.image_local,
            },
            "albums": albums,
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
    Follow an artist in FULL mode (downloads everything).
    
    If artist already has light subscription, upgrades to full.
    Queues sync_artist job to handle the heavy lifting.
    """
    if not artist_id:
        raise HTTPException(status_code=400, detail="artist_id required")
    
    try:
        logger.info(f"Following artist {artist_id} in full mode")
        
        # Check existing subscription
        existing_sub = subs_svc.get_artist_subscription(db, artist_id)
        old_mode = existing_sub.mode if existing_sub else None

        if old_mode == "full":
            return {
                "message": "Artist already fully followed",
                "artist_id": artist_id,
                "mode": "full",
            }

        # Fetch basic artist data
        artist_data = artists_svc.fetch_and_upsert_artist(db, artist_id)
        artist_name = artist_data.get("name", "Unknown Artist")

        # Create or upgrade subscription to full mode
        artist_subscription = subs_svc.subscribe_to_artist(
            db,
            artist_id=artist_id,
            mode="full",
        )

        # If upgrading from light to full, upgrade all album subscriptions
        # and queue import_album for albums that have no DB data yet
        imports_queued = 0
        if old_mode == "light":
            upgraded_count = subs_svc.upgrade_all_album_subscriptions_to_download(db, artist_id)
            logger.info(f"Upgraded {upgraded_count} albums to download mode for artist {artist_id}")

            # Queue import_album for upgraded albums that lack Album rows in DB
            from sqlalchemy import select
            from ..models import AlbumSubscription, Album
            upgraded_subs = (
                db.execute(
                    select(AlbumSubscription.album_id).where(
                        AlbumSubscription.artist_id == artist_id,
                        AlbumSubscription.mode == "download",
                        ~AlbumSubscription.album_id.in_(select(Album.id)),
                    )
                ).scalars().all()
            )
            for album_id in upgraded_subs:
                try:
                    enqueue_job(
                        db,
                        job_type="import_album",
                        payload={"browse_id": album_id, "artist_id": artist_id},
                        priority=20,
                        user_id=current_user.id,
                        commit=False,
                    )
                    imports_queued += 1
                except Exception as e:
                    logger.exception(f"Failed to queue import_album for {album_id}")

        db.commit()
        logger.info(f"Artist {artist_id} followed in full mode")

        # Queue sync_artist job (picks up any brand-new albums from API)
        try:
            job = enqueue_job(
                db,
                job_type="sync_artist",
                payload={"artist_id": artist_id},
                priority=30,
                user_id=current_user.id
            )
            logger.info(f"Queued sync_artist job {job.id} for artist {artist_id}")
        except Exception as e:
            logger.exception(f"Failed to queue sync_artist job for {artist_id}")

        return {
            "message": f"Artist followed successfully in full mode. Syncing in background.",
            "artist": {
                "id": artist_id,
                "name": artist_name,
            },
            "mode": "full",
            "status": "syncing",
            "imports_queued": imports_queued,
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
    Unfollow an artist (downgrade to light mode).

    - Downgrades artist subscription to light mode
    - Downgrades all album subscriptions to metadata mode
    - Does NOT delete files or database records
    """
    if not artist_id:
        raise HTTPException(status_code=400, detail="artist_id required")

    try:
        # Check if subscription exists
        subscription = subs_svc.get_artist_subscription(db, artist_id)
        if not subscription:
            raise HTTPException(status_code=404, detail="Artist is not followed")

        # Downgrade all album subscriptions to metadata mode
        downgraded_count = subs_svc.downgrade_all_album_subscriptions_to_metadata(db, artist_id)

        # Downgrade artist subscription to light mode
        subscription.mode = "light"

        db.commit()

        logger.info(f"Artist {artist_id} unfollowed: downgraded to light mode, {downgraded_count} albums downgraded to metadata mode")

        return {
            "message": "Artist unfollowed successfully. Downgraded to light mode.",
            "artist_id": artist_id,
            "albums_downgraded": downgraded_count,
        }
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"unfollow_artist failed for {artist_id}")
        raise HTTPException(status_code=500, detail=f"Failed to unfollow artist: {e}")


@router.patch("/{artist_id}/mode", status_code=status.HTTP_200_OK)
def update_artist_mode(
    artist_id: str,
    mode: str,  # "light" or "full"
    current_user: User = Depends(require_member_or_admin),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Update artist subscription mode.
    
    light → full: Upgrades all albums to download mode, queues sync
    full → light: Downgrades all albums to metadata mode
    """
    if mode not in ("light", "full"):
        raise HTTPException(status_code=400, detail="mode must be 'light' or 'full'")
    
    try:
        # Get current subscription
        subscription = subs_svc.get_artist_subscription(db, artist_id)
        if not subscription:
            raise HTTPException(status_code=404, detail="Artist not followed")
        
        old_mode = subscription.mode
        
        if old_mode == mode:
            return {
                "message": f"Artist already in {mode} mode",
                "artist_id": artist_id,
                "mode": mode,
            }
        
        # Update subscription mode
        subs_svc.update_artist_subscription_mode(db, artist_id, mode)
        
        # Update album subscriptions accordingly
        if mode == "full":
            # Upgrade: metadata → download
            upgraded_count = subs_svc.upgrade_all_album_subscriptions_to_download(db, artist_id)

            # Queue import_album for upgraded albums that lack Album rows in DB
            from sqlalchemy import select
            from ..models import AlbumSubscription, Album
            imports_queued = 0
            upgraded_subs = (
                db.execute(
                    select(AlbumSubscription.album_id).where(
                        AlbumSubscription.artist_id == artist_id,
                        AlbumSubscription.mode == "download",
                        ~AlbumSubscription.album_id.in_(select(Album.id)),
                    )
                ).scalars().all()
            )
            for album_id in upgraded_subs:
                try:
                    enqueue_job(
                        db,
                        job_type="import_album",
                        payload={"browse_id": album_id, "artist_id": artist_id},
                        priority=20,
                        user_id=current_user.id,
                        commit=False,
                    )
                    imports_queued += 1
                except Exception as e:
                    logger.exception(f"Failed to queue import_album for {album_id}")

            db.commit()

            # Queue sync job (picks up any brand-new albums from API)
            try:
                job = enqueue_job(
                    db,
                    job_type="sync_artist",
                    payload={"artist_id": artist_id},
                    priority=20,
                    user_id=current_user.id
                )
                logger.info(f"Queued sync_artist job {job.id} for upgraded artist {artist_id}")
            except Exception as e:
                logger.exception(f"Failed to queue sync_artist job")

            return {
                "message": f"Artist upgraded to full mode. {upgraded_count} albums will be downloaded.",
                "artist_id": artist_id,
                "mode": "full",
                "albums_upgraded": upgraded_count,
                "imports_queued": imports_queued,
            }
        else:
            # Downgrade: download → metadata
            downgraded_count = subs_svc.downgrade_all_album_subscriptions_to_metadata(db, artist_id)
            db.commit()
            
            return {
                "message": f"Artist downgraded to light mode. Files preserved, syncing stopped.",
                "artist_id": artist_id,
                "mode": "light",
                "albums_downgraded": downgraded_count,
            }
        
    except HTTPException:
        db.rollback()
        raise
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.exception(f"update_artist_mode failed for {artist_id}")
        raise HTTPException(status_code=500, detail=f"Failed to update mode: {e}")