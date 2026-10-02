# backend/routers/library.py
"""
Library endpoints for browsing and managing downloaded/followed content.

Endpoints:
- GET /api/library/artists - List followed artists with stats
- GET /api/library/albums - List followed albums with download status
- GET /api/library/tracks - List downloaded tracks (with filters)
- GET /api/library/stats - Overall library statistics
- GET /api/library/albums/{album_id}/progress - Detailed album download progress
- DELETE /api/library/artists/{artist_id} - Delete artist from library (admin)
- DELETE /api/library/albums/{album_id} - Delete album from library (admin)
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, case

from ..deps import get_db
from ..models import Artist, Album, Track, ArtistSubscription
from ..services import subscriptions as subs_svc
from ..jobs.jobqueue import cancel_download_jobs
from .. import config
from ..downloader.cover import move_cover_if_exists

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
    limit: Optional[int] = Query(None, ge=1, description="Maximum number of artists to return"),
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
        # Per-artist counts are aggregated in one pass each and joined in,
        # rather than queried artist by artist.
        # Only count followed (download-mode) albums: light-mode artists keep
        # metadata-only album rows that aren't part of the library
        albums_counts = (
            db.query(
                Album.artist_id.label("artist_id"),
                func.count(Album.id).label("albums_count"),
            )
            .filter(Album.mode == "download")
            .group_by(Album.artist_id)
            .subquery()
        )
        tracks_counts = (
            db.query(
                Album.artist_id.label("artist_id"),
                func.count(Track.id).label("total"),
                func.sum(case((Track.status == "done", 1), else_=0)).label("downloaded"),
                func.sum(case((Track.status == "failed", 1), else_=0)).label("failed"),
            )
            .select_from(Track)
            .join(Album, Track.album_id == Album.id)
            .filter(Album.mode == "download")
            .group_by(Album.artist_id)
            .subquery()
        )

        # Get all artists with active subscriptions
        query = (
            db.query(
                Artist,
                ArtistSubscription,
                albums_counts.c.albums_count,
                tracks_counts.c.total,
                tracks_counts.c.downloaded,
                tracks_counts.c.failed,
            )
            .join(ArtistSubscription, ArtistSubscription.artist_id == Artist.id)
            .outerjoin(albums_counts, albums_counts.c.artist_id == Artist.id)
            .outerjoin(tracks_counts, tracks_counts.c.artist_id == Artist.id)
            .filter(ArtistSubscription.enabled == True)
        )

        # Apply sorting
        if sort_by == "name":
            query = query.order_by(Artist.name.asc() if order == "asc" else Artist.name.desc())
        elif sort_by == "followed_at":
            query = query.order_by(ArtistSubscription.created_at.desc() if order == "desc" else ArtistSubscription.created_at.asc())
        # albums_count sorting will be done in Python after fetching

        rows = query.all()
        
        result = []
        for artist, subscription, albums_count, total, downloaded, failed in rows:
            albums_count = int(albums_count or 0)
            tracks_total = int(total or 0)
            tracks_downloaded = int(downloaded or 0)
            tracks_failed = int(failed or 0)

            # Calculate download progress
            download_progress = 0.0
            if tracks_total > 0:
                download_progress = round((tracks_downloaded / tracks_total) * 100, 1)

            result.append({
                "id": artist.id,
                "name": artist.name,
                "thumbnail": artist.image_local,
                "mode": subscription.mode,
                "followed_at": subscription.created_at.isoformat() if subscription.created_at else None,
                "albums_count": albums_count,
                "tracks_total": tracks_total,
                "tracks_downloaded": tracks_downloaded,
                "tracks_failed": tracks_failed,
                "download_progress": download_progress,
                "last_synced_at": subscription.last_synced_at.isoformat() if subscription.last_synced_at else None,
            })
        
        # Sort by albums_count if requested
        if sort_by == "albums_count":
            result.sort(key=lambda x: x["albums_count"], reverse=(order == "desc"))
        
        total = len(result)
        if limit is not None:
            result = result[:limit]

        return {
            "artists": result,
            "total": total,
        }
    
    except Exception as e:
        logger.exception("list_followed_artists failed")
        raise HTTPException(status_code=500, detail=f"Failed to fetch artists: {e}")


@router.get("/albums", status_code=status.HTTP_200_OK)
def list_followed_albums(
    current_user: User = Depends(require_auth),
    artist_id: Optional[str] = Query(None, description="Filter by artist ID"),
    status_filter: Optional[str] = Query(None, pattern="^(completed|downloading|pending|failed)$", description="Filter by download status"),
    sort_by: str = Query("title", pattern="^(title|year|created_at|download_progress)$"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    limit: Optional[int] = Query(None, ge=1, description="Maximum number of albums to return"),
    offset: int = Query(0, ge=0, description="Number of albums to skip (after sorting)"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    List all followed albums with download status.

    Query params:
    - artist_id: Filter albums by artist (optional)
    - status: Filter by download status (completed, downloading, pending, failed)
    - sort_by: title, year, download_progress (default: title)
    - order: asc, desc (default: asc)
    - limit / offset: Page through the sorted list (optional)

    Returns list of albums with download stats.
    """
    try:
        # Track counts for every album in one grouped pass, joined in below,
        # rather than one query per album
        tracks_counts = (
            db.query(
                Track.album_id.label("album_id"),
                func.count(Track.id).label("total"),
                func.sum(case((Track.status == "done", 1), else_=0)).label("downloaded"),
                func.sum(case((Track.status == "failed", 1), else_=0)).label("failed"),
                func.sum(case((Track.lyrics != None, 1), else_=0)).label("with_lyrics"),  # noqa: E711
            )
            .group_by(Track.album_id)
            .subquery()
        )

        # Query albums directly (mode is now on the Album row)
        albums_query = (
            db.query(
                Album,
                Artist.id,
                Artist.name,
                tracks_counts.c.total,
                tracks_counts.c.downloaded,
                tracks_counts.c.failed,
                tracks_counts.c.with_lyrics,
            )
            .outerjoin(Artist, Artist.id == Album.artist_id)
            .outerjoin(tracks_counts, tracks_counts.c.album_id == Album.id)
        )

        if artist_id:
            albums_query = albums_query.filter(Album.artist_id == artist_id)

        albums_query = albums_query.filter(Album.mode == "download")

        rows = albums_query.all()

        if not rows:
            return {"albums": [], "total": 0}

        result = []
        for album, artist_db_id, artist_name, total, downloaded, failed, with_lyrics in rows:
            tracks_total = int(total or 0)
            tracks_downloaded = int(downloaded or 0)
            tracks_failed = int(failed or 0)
            tracks_with_lyrics = int(with_lyrics or 0)

            # Calculate download progress
            download_progress = 0.0
            if tracks_total > 0:
                download_progress = round((tracks_downloaded / tracks_total) * 100, 1)

            # Determine overall status
            download_status = album.download_status or "idle"

            # Apply status filter
            if status_filter and download_status != status_filter:
                continue

            result.append({
                "id": album.id,
                "title": album.title,
                "artist": {
                    "id": artist_db_id,
                    "name": artist_name,
                } if artist_db_id else None,
                "year": album.year,
                "type": album.type or "Album",
                "mode": album.mode,
                "thumbnail": album.image_local,
                "download_status": download_status,
                "tracks_total": tracks_total,
                "tracks_downloaded": tracks_downloaded,
                "tracks_failed": tracks_failed,
                "tracks_with_lyrics": tracks_with_lyrics,
                "download_progress": download_progress,
                "created_at": album.created_at.isoformat() if album.created_at else None,
            })
        
        # Sort results
        if sort_by == "title":
            result.sort(key=lambda x: (x["title"] or "").lower(), reverse=(order == "desc"))
        elif sort_by == "year":
            result.sort(key=lambda x: x["year"] or "", reverse=(order == "desc"))
        elif sort_by == "created_at":
            result.sort(key=lambda x: x["created_at"] or "", reverse=(order == "desc"))
        elif sort_by == "download_progress":
            result.sort(key=lambda x: x["download_progress"], reverse=(order == "desc"))
        
        total = len(result)
        end = offset + limit if limit is not None else None
        result = result[offset:end]

        return {
            "albums": result,
            "total": total,
        }
    
    except Exception as e:
        logger.exception("list_followed_albums failed")
        raise HTTPException(status_code=500, detail=f"Failed to fetch albums: {e}")


@router.get("/tracks", status_code=status.HTTP_200_OK)
def list_tracks(
    current_user: User = Depends(require_auth),
    artist_id: Optional[str] = Query(None, description="Filter by artist ID"),
    album_id: Optional[str] = Query(None, description="Filter by album ID"),
    status_filter: Optional[str] = Query(None, pattern="^(available|queued|downloading|done|failed)$", description="Filter by track status"),
    lyrics: Optional[str] = Query(None, pattern="^(synced|plain|any)$", description="Filter by lyrics type (synced, plain, any)"),
    q: Optional[str] = Query(None, max_length=200, description="Case-insensitive substring match on track title"),
    limit: int = Query(100, ge=1, le=1000, description="Max results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    List tracks with optional filters.
    
    Query params:
    - artist_id: Filter by artist (optional)
    - album_id: Filter by album (optional)
    - status: Filter by status (available, queued, downloading, done, failed)
    - lyrics: Filter by lyrics type (synced, plain, any)
    - q: Case-insensitive substring match on the track title
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

        if lyrics is not None:
            if lyrics == "any":
                query = query.filter(Track.lyrics != None)  # noqa: E711
            else:
                query = query.filter(Track.lyrics == lyrics)

        q = (q or "").strip()
        if q:
            # Escape LIKE wildcards so a literal "%" or "_" in the query doesn't
            # match everything
            escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            query = query.filter(Track.title.ilike(f"%{escaped}%", escape="\\"))
        
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
                "lyrics": track.lyrics,
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
        # Artists stats (count active subscriptions)
        artists_total = db.query(func.count(ArtistSubscription.id)).filter(ArtistSubscription.enabled == True).scalar() or 0
        
        # Every count below is taken in a single pass over its table
        def count_where(condition):
            return func.sum(case((condition, 1), else_=0))

        # Albums stats (query Album table directly)
        # "total" counts every followed album, including ones only followed for
        # search/indexation (mode="metadata"). "downloaded" counts only albums
        # actually in the library (mode="download").
        albums = db.query(
            func.count(Album.id).label("total"),
            count_where(Album.mode == "download").label("downloaded"),
            count_where(Album.download_status == "completed").label("completed"),
            count_where(Album.download_status == "downloading").label("downloading"),
            count_where(Album.download_status == "pending").label("pending"),
            count_where(Album.download_status == "failed").label("failed"),
        ).one()

        # Tracks stats
        # Storage: sum of audio file sizes recorded at download time.
        # Lyrics/covers are not counted (~0.5% of the total).
        tracks = db.query(
            func.count(Track.id).label("total"),
            count_where(Track.status == "done").label("downloaded"),
            count_where(Track.status == "downloading").label("downloading"),
            count_where(Track.status == "queued").label("pending"),
            count_where(Track.status == "failed").label("failed"),
            count_where(Track.lyrics != None).label("with_lyrics"),  # noqa: E711
            count_where(Track.lyrics == "synced").label("with_synced_lyrics"),
            count_where(Track.lyrics == "plain").label("with_plain_lyrics"),
            func.sum(case((Track.status == "done", Track.file_size), else_=0)).label("storage_bytes"),
        ).one()

        album_fields = ["total", "downloaded", "completed", "downloading", "pending", "failed"]
        track_fields = [
            "total", "downloaded", "downloading", "pending", "failed",
            "with_lyrics", "with_synced_lyrics", "with_plain_lyrics",
        ]
        storage_bytes = int(tracks.storage_bytes or 0)

        return {
            "artists": {
                "total": int(artists_total),
            },
            "albums": _safe_stats(albums, album_fields),
            "tracks": _safe_stats(tracks, track_fields),
            "storage": {
                "bytes": storage_bytes,
                "gb": round(storage_bytes / 1024 ** 3, 2),
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
        
        # Get tracks
        tracks = db.query(Track).filter(Track.album_id == album_id).order_by(Track.id.asc()).all()
        
        tracks_data = []
        for track in tracks:
            tracks_data.append({
                "id": track.id,
                "title": track.title,
                "duration": track.duration,
                "status": track.status,
                "lyrics": track.lyrics,
                "file_path": track.file_path,
            })

        # Calculate stats
        total = len(tracks)
        downloaded = sum(1 for t in tracks if t.status == "done")
        downloading = sum(1 for t in tracks if t.status == "downloading")
        failed = sum(1 for t in tracks if t.status == "failed")
        pending = sum(1 for t in tracks if t.status == "queued")
        with_lyrics = sum(1 for t in tracks if t.lyrics is not None)
        
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
                "status": album.download_status or "idle",
                "mode": album.mode,
                "created_at": album.created_at.isoformat() if album.created_at else None,
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


# ============================================================================
# DELETE ENDPOINTS - Library content removal
# ============================================================================

def _delete_file_safe(path: Optional[str]) -> bool:
    """Delete a file if it exists. Returns True if deleted."""
    if not path:
        return False
    from pathlib import Path
    try:
        p = Path(path)
        if p.exists():
            p.unlink()
            return True
    except Exception as e:
        logger.warning(f"Failed to delete file {path}: {e}")
    return False


def _delete_dir_safe(path: str) -> bool:
    """Delete a directory if it exists and is empty. Returns True if deleted."""
    from pathlib import Path
    import shutil
    try:
        p = Path(path)
        if p.exists() and p.is_dir():
            shutil.rmtree(str(p))
            return True
    except Exception as e:
        logger.warning(f"Failed to delete directory {path}: {e}")
    return False


@router.delete("/artists/{artist_id}", status_code=status.HTTP_200_OK)
def delete_artist_from_library(
    artist_id: str,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Completely remove an artist from the library.

    Deletes everything:
    - All track files, lyrics files, album covers, artist banner
    - Artist folder on disk
    - All DB records: tracks, albums, artist
    - All subscriptions: artist subscription + all album subscriptions
      (including metadata-only subs that have no Album row in DB)

    Requires administrator role.
    """
    if not artist_id:
        raise HTTPException(status_code=400, detail="artist_id required")

    try:
        # Artist must exist either as a DB record or have subscriptions
        artist = db.get(Artist, artist_id)
        artist_sub = subs_svc.get_artist_subscription(db, artist_id)

        if not artist and not artist_sub:
            raise HTTPException(status_code=404, detail="Artist not found in library")

        artist_name = artist.name if artist else "Unknown"
        files_deleted = 0
        tracks_deleted = 0
        albums_deleted = 0

        # 1. Delete all albums that exist in DB for this artist
        if artist:
            albums = db.query(Album).filter(Album.artist_id == artist_id).all()
            for album in albums:
                tracks = db.query(Track).filter(Track.album_id == album.id).all()
                cancel_download_jobs(db, [t.id for t in tracks], reason="artist deleted")
                for track in tracks:
                    if _delete_file_safe(track.file_path):
                        files_deleted += 1
                    _delete_file_safe(track.lyrics_local)
                    db.delete(track)
                    tracks_deleted += 1

                _delete_file_safe(album.image_local)
                db.delete(album)
                albums_deleted += 1

        # 2. Delete artist banner
        if artist:
            _delete_file_safe(artist.image_local)

        # 3. Delete artist subscription
        if artist_sub:
            db.delete(artist_sub)

        # 4. Delete artist record
        if artist:
            db.delete(artist)

        # 5. Delete artist folder from disk
        from pathlib import Path
        from .. import config
        safe_name = "".join(c for c in (artist_name or "") if c.isalnum() or c in " .-_()").strip()
        if safe_name:
            artist_folder = Path(str(config.MUSIC_DIR)) / safe_name
            _delete_dir_safe(str(artist_folder))

        db.commit()

        logger.info(
            f"Deleted artist {artist_id} ({artist_name}) from library: "
            f"{albums_deleted} albums, {tracks_deleted} tracks, "
            f"{files_deleted} files"
        )

        return {
            "message": f"Artist '{artist_name}' completely removed from library.",
            "artist_id": artist_id,
            "albums_deleted": albums_deleted,
            "tracks_deleted": tracks_deleted,
            "files_deleted": files_deleted,
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"delete_artist_from_library failed for {artist_id}")
        raise HTTPException(status_code=500, detail=f"Failed to delete artist: {e}")


@router.delete("/albums/{album_id}", status_code=status.HTTP_200_OK)
def delete_album_from_library(
    album_id: str,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Delete an album's downloaded content from the library.

    What happens:
    - All track files, lyrics files, and album cover are deleted from disk
    - Album and Track DB rows are deleted
    - Album subscription is KEPT but downgraded to mode="metadata"
    - Artist subscription is downgraded to mode="light"
      (no more periodic sync; artist stays in library;
       re-following the artist will reimport and redownload this album)

    Requires administrator role.
    """
    if not album_id:
        raise HTTPException(status_code=400, detail="album_id required")

    try:
        album = db.get(Album, album_id)
        if not album:
            raise HTTPException(status_code=404, detail="Album not found in library")

        if album.mode == "metadata":
            raise HTTPException(
                status_code=400,
                detail="Cannot delete a metadata-only album. Only downloaded albums can be deleted."
            )

        album_title = album.title
        artist_id = album.artist_id
        files_deleted = 0
        tracks_deleted = 0

        # 1. Delete all track files and lyrics from disk
        tracks = db.query(Track).filter(Track.album_id == album.id).all()
        cancel_download_jobs(db, [t.id for t in tracks], reason="album deleted")
        for track in tracks:
            if _delete_file_safe(track.file_path):
                files_deleted += 1
            _delete_file_safe(track.lyrics_local)
            db.delete(track)
            tracks_deleted += 1

        # 2. Move album cover back to the covers directory (for metadata display)
        if album.image_local:
            cover_dest = config.COVERS_DIR / f"{album.id}.jpg"
            moved = move_cover_if_exists(album.image_local, cover_dest)
            album.image_local = str(moved) if moved else None
        else:
            album.image_local = None

        # 3. Downgrade album to metadata mode (keep the row)
        album.mode = "metadata"
        album.download_status = None
        db.add(album)

        artist_downgraded = False

        # 4. Downgrade artist subscription to light mode (stops periodic sync)
        if artist_id:
            artist_sub = subs_svc.get_artist_subscription(db, artist_id)
            if artist_sub and artist_sub.mode == "full":
                artist_sub.mode = "light"
                db.add(artist_sub)
                artist_downgraded = True
                logger.info(f"Downgraded artist {artist_id} to light mode after album deletion")

        db.commit()

        logger.info(
            f"Deleted album {album_id} ({album_title}) from library: "
            f"{tracks_deleted} tracks, {files_deleted} files"
        )

        return {
            "message": f"Album '{album_title}' deleted from library. Artist switched to light mode.",
            "album_id": album_id,
            "tracks_deleted": tracks_deleted,
            "files_deleted": files_deleted,
            "artist_downgraded": artist_downgraded,
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"delete_album_from_library failed for {album_id}")
        raise HTTPException(status_code=500, detail=f"Failed to delete album: {e}")
