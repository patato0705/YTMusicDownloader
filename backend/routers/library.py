# backend/routers/library.py
"""
Library endpoints for browsing downloaded/followed content.

Endpoints:
- GET /api/library/artists - List followed artists with stats
- GET /api/library/albums - List followed albums with download status
- GET /api/library/tracks - List downloaded tracks (with filters)
- GET /api/library/stats - Overall library statistics
- GET /api/library/albums/{album_id}/progress - Detailed album download progress
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, case

from ..deps import get_db
from ..models import Artist, Album, Track, AlbumSubscription, ArtistSubscription
from ..services import subscriptions as subs_svc

from backend.dependencies import require_auth, require_member_or_admin, require_admin
from backend.models import User

logger = logging.getLogger("routers.library")

router = APIRouter(prefix="/api/library", tags=["Library"])

def _safe_stats(stats_obj, fields):
    """Safely extract stats, returning 0 for missing fields."""
    if not stats_obj:
        return {field: 0 for field in fields}
    return {field: int(getattr(stats_obj, field, 0) or 0) for field in fields}

@router.get("/artists", status_code=status.HTTP_200_OK)
def list_followed_artists(
    current_user: User = Depends(require_auth),
    sort_by: str = Query("name", pattern="^(name|followed_at|albums_count)$"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    List all followed artists with statistics.
    
    Query params:
    - sort_by: name, followed_at, albums_count (default: name)
    - order: asc, desc (default: asc)
    
    Returns list of artists with download stats.
    """
    try:
        # Get all followed artists
        query = db.query(Artist).filter(Artist.followed == True)
        
        # Apply sorting
        if sort_by == "name":
            query = query.order_by(Artist.name.asc() if order == "asc" else Artist.name.desc())
        elif sort_by == "followed_at":
            query = query.order_by(Artist.created_at.desc() if order == "desc" else Artist.created_at.asc())
        # albums_count sorting will be done in Python after fetching
        
        artists = query.all()
        
        result = []
        for artist in artists:
            # Get albums count
            albums_count = db.query(func.count(Album.id)).filter(Album.artist_id == artist.id).scalar() or 0
            
            # Get tracks stats
            tracks_query = (
                db.query(
                    func.count(Track.id).label("total"),
                    func.sum(case((Track.status == "done", 1), else_=0)).label("downloaded"),
                    func.sum(case((Track.status == "failed", 1), else_=0)).label("failed"),
                )
                .join(Album, Track.album_id == Album.id)
                .filter(Album.artist_id == artist.id)
            )
            
            tracks_stats = tracks_query.first()
            stats = _safe_stats(tracks_stats, ['total', 'downloaded', 'failed'])
            tracks_total = stats['total']
            tracks_downloaded = stats['downloaded']
            tracks_failed = stats['failed']
            
            # Calculate download progress
            download_progress = 0.0
            if tracks_total > 0:
                download_progress = round((tracks_downloaded / tracks_total) * 100, 1)
            
            # Get subscription info
            subscription = subs_svc.get_artist_subscription(db, artist.id)
            
            result.append({
                "id": artist.id,
                "name": artist.name,
                "thumbnail": artist.image_local,
                "followed_at": artist.created_at.isoformat() if artist.created_at else None,
                "albums_count": albums_count,
                "tracks_total": tracks_total,
                "tracks_downloaded": tracks_downloaded,
                "tracks_failed": tracks_failed,
                "download_progress": download_progress,
                "last_synced_at": subscription.last_synced_at.isoformat() if subscription and subscription.last_synced_at else None,
            })
        
        # Sort by albums_count if requested
        if sort_by == "albums_count":
            result.sort(key=lambda x: x["albums_count"], reverse=(order == "desc"))
        
        return {
            "artists": result,
            "total": len(result),
        }
    
    except Exception as e:
        logger.exception("list_followed_artists failed")
        raise HTTPException(status_code=500, detail=f"Failed to fetch artists: {e}")


@router.get("/albums", status_code=status.HTTP_200_OK)
def list_followed_albums(
    current_user: User = Depends(require_auth),
    artist_id: Optional[str] = Query(None, description="Filter by artist ID"),
    status_filter: Optional[str] = Query(None, pattern="^(completed|downloading|pending|failed)$", description="Filter by download status"),
    sort_by: str = Query("title", pattern="^(title|year|followed_at|download_progress)$"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    List all followed albums with download status.
    
    Query params:
    - artist_id: Filter albums by artist (optional)
    - status: Filter by download status (completed, downloading, pending, failed)
    - sort_by: title, year, download_progress (default: title)
    - order: asc, desc (default: asc)
    
    Returns list of albums with download stats.
    """
    try:
        # Get all album subscriptions
        subs_query = db.query(AlbumSubscription)
        
        if artist_id:
            subs_query = subs_query.filter(AlbumSubscription.artist_id == artist_id)
        
        subscriptions = subs_query.all()
        album_ids = [sub.album_id for sub in subscriptions]
        
        if not album_ids:
            return {"albums": [], "total": 0}
        
        # Get albums
        albums_query = db.query(Album).filter(Album.id.in_(album_ids))
        albums = albums_query.all()
        
        result = []
        for album in albums:
            # Get subscription for this album
            subscription = next((s for s in subscriptions if s.album_id == album.id), None)
            
            # Get artist info
            artist = None
            if album.artist_id:
                artist = db.get(Artist, album.artist_id)
            
            # Get tracks stats
            tracks_query = (
                db.query(
                    func.count(Track.id).label("total"),
                    func.sum(case((Track.status == "done", 1), else_=0)).label("downloaded"),
                    func.sum(case((Track.status == "failed", 1), else_=0)).label("failed"),
                    func.sum(case((Track.has_lyrics == True, 1), else_=0)).label("with_lyrics"),
                )
                .filter(Track.album_id == album.id)
            )
            
            tracks_stats = tracks_query.first()
            stats = _safe_stats(tracks_stats, ['total', 'downloaded', 'failed', 'with_lyrics'])
            tracks_total = stats['total']
            tracks_downloaded = stats['downloaded']
            tracks_failed = stats['failed']
            tracks_with_lyrics = stats['with_lyrics']
            
            # Calculate download progress
            download_progress = 0.0
            if tracks_total > 0:
                download_progress = round((tracks_downloaded / tracks_total) * 100, 1)
            
            # Determine overall status
            download_status = subscription.download_status if subscription else "idle"
            
            # Apply status filter
            if status_filter and download_status != status_filter:
                continue
            
            result.append({
                "id": album.id,
                "title": album.title,
                "artist": {
                    "id": artist.id if artist else None,
                    "name": artist.name if artist else None,
                } if artist else None,
                "year": album.year,
                "type": album.type or "Album",
                "thumbnail": album.image_local,
                "download_status": download_status,
                "tracks_total": tracks_total,
                "tracks_downloaded": tracks_downloaded,
                "tracks_failed": tracks_failed,
                "tracks_with_lyrics": tracks_with_lyrics,
                "download_progress": download_progress,
                "followed_at": subscription.created_at.isoformat() if subscription and subscription.created_at else None,
            })
        
        # Sort results
        if sort_by == "title":
            result.sort(key=lambda x: (x["title"] or "").lower(), reverse=(order == "desc"))
        elif sort_by == "year":
            result.sort(key=lambda x: x["year"] or "", reverse=(order == "desc"))
        elif sort_by == "followed_at":
            result.sort(key=lambda x: x["followed_at"] or "", reverse=(order == "desc"))
        elif sort_by == "download_progress":
            result.sort(key=lambda x: x["download_progress"], reverse=(order == "desc"))
        
        return {
            "albums": result,
            "total": len(result),
        }
    
    except Exception as e:
        logger.exception("list_followed_albums failed")
        raise HTTPException(status_code=500, detail=f"Failed to fetch albums: {e}")


@router.get("/tracks", status_code=status.HTTP_200_OK)
def list_tracks(
    current_user: User = Depends(require_auth),
    artist_id: Optional[str] = Query(None, description="Filter by artist ID"),
    album_id: Optional[str] = Query(None, description="Filter by album ID"),
    status_filter: Optional[str] = Query(None, pattern="^(done|failed|downloading|new)$", description="Filter by track status"),
    has_lyrics: Optional[bool] = Query(None, description="Filter by lyrics availability"),
    limit: int = Query(100, ge=1, le=1000, description="Max results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    List tracks with optional filters.
    
    Query params:
    - artist_id: Filter by artist (optional)
    - album_id: Filter by album (optional)
    - status: Filter by status (done, failed, downloading, new)
    - has_lyrics: Filter by lyrics availability (true/false)
    - limit: Max results (default 100, max 1000)
    - offset: Pagination offset (default 0)
    
    Returns list of tracks with metadata.
    """
    try:
        # Build query
        query = db.query(Track).join(Album, Track.album_id == Album.id)
        
        # Apply filters
        if album_id:
            query = query.filter(Track.album_id == album_id)
        elif artist_id:
            query = query.filter(Album.artist_id == artist_id)
        
        if status_filter:
            query = query.filter(Track.status == status_filter)
        
        if has_lyrics is not None:
            query = query.filter(Track.has_lyrics == has_lyrics)
        
        # Get total count
        total = query.count()
        
        # Apply pagination and ordering
        query = query.order_by(Album.title.asc(), Track.id.asc())
        query = query.limit(limit).offset(offset)
        
        tracks = query.all()
        
        result = []
        for track in tracks:
            # Get album and artist info
            album = db.get(Album, track.album_id) if track.album_id else None
            artist = None
            if album and album.artist_id:
                artist = db.get(Artist, album.artist_id)
            
            result.append({
                "id": track.id,
                "title": track.title,
                "artists": track.artists or [],
                "album": {
                    "id": album.id if album else None,
                    "title": album.title if album else None,
                    "thumbnail": album.image_local if album else None,
                } if album else None,
                "artist": {
                    "id": artist.id if artist else None,
                    "name": artist.name if artist else None,
                } if artist else None,
                "duration": track.duration,
                "status": track.status,
                "file_path": track.file_path,
                "has_lyrics": track.has_lyrics,
                "lyrics_path": track.lyrics_local,
                "created_at": track.created_at.isoformat() if track.created_at else None,
            })
        
        return {
            "tracks": result,
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    
    except Exception as e:
        logger.exception("list_tracks failed")
        raise HTTPException(status_code=500, detail=f"Failed to fetch tracks: {e}")


@router.get("/stats", status_code=status.HTTP_200_OK)
def get_library_stats(
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get overall library statistics.
    """
    try:
        # Artists stats
        artists_total = db.query(func.count(Artist.id)).filter(Artist.followed == True).scalar() or 0
        
        # Albums stats
        albums_total = db.query(func.count(AlbumSubscription.id)).scalar() or 0
        albums_completed = db.query(func.count(AlbumSubscription.id)).filter(
            AlbumSubscription.download_status == "completed"
        ).scalar() or 0
        albums_downloading = db.query(func.count(AlbumSubscription.id)).filter(
            AlbumSubscription.download_status == "downloading"
        ).scalar() or 0
        albums_pending = db.query(func.count(AlbumSubscription.id)).filter(
            AlbumSubscription.download_status == "pending"
        ).scalar() or 0
        albums_failed = db.query(func.count(AlbumSubscription.id)).filter(
            AlbumSubscription.download_status == "failed"
        ).scalar() or 0
        
        # Tracks stats
        tracks_total = db.query(func.count(Track.id)).scalar() or 0
        tracks_downloaded = db.query(func.count(Track.id)).filter(Track.status == "done").scalar() or 0
        tracks_downloading = db.query(func.count(Track.id)).filter(Track.status == "downloading").scalar() or 0
        tracks_failed = db.query(func.count(Track.id)).filter(Track.status == "failed").scalar() or 0
        tracks_pending = db.query(func.count(Track.id)).filter(Track.status == "new").scalar() or 0
        tracks_with_lyrics = db.query(func.count(Track.id)).filter(Track.has_lyrics == True).scalar() or 0
        
        # Calculate storage
        estimated_size_mb = int(tracks_downloaded) * 3
        estimated_size_gb = round(estimated_size_mb / 1024, 2)
        
        return {
            "artists": {
                "total": int(artists_total),
            },
            "albums": {
                "total": int(albums_total),
                "completed": int(albums_completed),
                "downloading": int(albums_downloading),
                "pending": int(albums_pending),
                "failed": int(albums_failed),
            },
            "tracks": {
                "total": int(tracks_total),
                "downloaded": int(tracks_downloaded),
                "downloading": int(tracks_downloading),
                "pending": int(tracks_pending),
                "failed": int(tracks_failed),
                "with_lyrics": int(tracks_with_lyrics),
            },
            "storage": {
                "estimated_mb": estimated_size_mb,
                "estimated_gb": estimated_size_gb,
            }
        }
    
    except Exception as e:
        logger.exception("get_library_stats failed")
        raise HTTPException(status_code=500, detail=f"Failed to fetch stats: {e}")


@router.get("/albums/{album_id}/progress", status_code=status.HTTP_200_OK)
def get_album_download_progress(
    album_id: str,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get detailed download progress for a specific album.
    
    Returns:
    - Album info
    - Track-by-track status
    - Overall progress
    """
    try:
        # Get album
        album = db.get(Album, album_id)
        if not album:
            raise HTTPException(status_code=404, detail="Album not found")
        
        # Get subscription
        subscription = subs_svc.get_album_subscription(db, album_id)
        
        # Get tracks
        tracks = db.query(Track).filter(Track.album_id == album_id).order_by(Track.id.asc()).all()
        
        tracks_data = []
        for track in tracks:
            tracks_data.append({
                "id": track.id,
                "title": track.title,
                "duration": track.duration,
                "status": track.status,
                "has_lyrics": track.has_lyrics,
                "file_path": track.file_path,
            })
        
        # Calculate stats
        total = len(tracks)
        downloaded = sum(1 for t in tracks if t.status == "done")
        downloading = sum(1 for t in tracks if t.status == "downloading")
        failed = sum(1 for t in tracks if t.status == "failed")
        pending = sum(1 for t in tracks if t.status == "new")
        with_lyrics = sum(1 for t in tracks if t.has_lyrics)
        
        progress = 0.0
        if total > 0:
            progress = round((downloaded / total) * 100, 1)
        
        return {
            "album": {
                "id": album.id,
                "title": album.title,
                "thumbnail": album.image_local,
            },
            "subscription": {
                "status": subscription.download_status if subscription else "idle",
                "followed_at": subscription.created_at.isoformat() if subscription and subscription.created_at else None,
            },
            "progress": {
                "percentage": progress,
                "tracks_total": total,
                "tracks_downloaded": downloaded,
                "tracks_downloading": downloading,
                "tracks_failed": failed,
                "tracks_pending": pending,
                "tracks_with_lyrics": with_lyrics,
            },
            "tracks": tracks_data,
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"get_album_download_progress failed for {album_id}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch album progress: {e}")