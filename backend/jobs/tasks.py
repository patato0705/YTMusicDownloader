# backend/jobs/tasks.py
"""
Job task handlers called by the worker.

Each task function:
- Takes (session: Session, **payload) as arguments
- Returns dict with {"ok": bool, "error": str (optional), ...}
- COMMITS at strategic points to avoid long-running transactions
- Updates database state (Track status, file paths, etc.)

Task types:
- download_track: Download a single track using yt-dlp
- download_lyrics: Download synced lyrics from LRCLIB
- import_album: Fetch and upsert album from YTMusic
- sync_artist: Check artist for new releases
"""
from __future__ import annotations
import logging
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError

from ..models import Job, Track, Album, Artist
from ..services import albums as albums_svc
from ..services import artists as artists_svc
from ..services import tracks as tracks_svc
from .. import downloader
from .. import config

logger = logging.getLogger("jobs.tasks")


# ============================================================================
# HELPER: DATABASE OPERATION WITH RETRY
# ============================================================================

def _db_operation_with_retry(operation, max_retries=3, delay=0.1):
    """
    Execute a database operation with automatic retry on lock errors.
    
    Args:
        operation: Callable that performs the database operation
        max_retries: Maximum number of retry attempts
        delay: Base delay between retries (exponential backoff)
    
    Returns:
        Result from the operation
    
    Raises:
        OperationalError: If operation fails after all retries
    """
    import time
    
    for attempt in range(max_retries):
        try:
            return operation()
        except OperationalError as e:
            if "database is locked" in str(e).lower():
                if attempt < max_retries - 1:
                    sleep_time = delay * (2 ** attempt)
                    logger.warning(f"Database locked, retry {attempt + 1}/{max_retries} after {sleep_time}s")
                    time.sleep(sleep_time)
                    continue
            raise


# ============================================================================
# TASK: DOWNLOAD TRACK
# ============================================================================

def download_track(
    session: Session,
    track_id: str,
    album_id: Optional[str] = None,
    artist_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Download a track by video ID using yt-dlp.
    
    Flow:
    1. Get track info from DB
    2. Get album/artist info for metadata
    3. Update status to "downloading" and COMMIT
    4. Call downloader.core.download_track_by_videoid() (no transaction held)
    5. Update Track table with file_path and status, COMMIT
    6. Update Album cover if new cover path returned, COMMIT
    
    Args:
        session: SQLAlchemy session
        track_id: Track video ID (from Track.id)
        album_id: Optional album ID for metadata
        artist_id: Optional artist ID for metadata
    
    Returns:
        {"ok": bool, "file_path": str, "error": str}
    """
    if not track_id:
        return {"ok": False, "error": "track_id required"}
    
    try:
        # ===== TRANSACTION 1: Get track info and update status =====
        track = session.get(Track, str(track_id))
        if not track:
            return {"ok": False, "error": f"Track {track_id} not found in database"}
        
        # Get album info for metadata
        album = None
        if track.album_id:
            album = session.get(Album, track.album_id)
        elif album_id:
            album = session.get(Album, album_id)
        
        # Get artist info for metadata
        artist = None
        if album and album.artist_id:
            artist = session.get(Artist, album.artist_id)
        elif artist_id:
            artist = session.get(Artist, artist_id)
        
        # Extract metadata (before we detach objects)
        artist_name = artist.name if artist else None
        album_name = album.title if album else None
        track_title = track.title
        track_number = track.track_number
        year = int(album.year) if album and album.year else None
        cover_path = album.image_local if album else None
        album_id_final = album.id if album else None
        track_album_id = track.album_id
        
        # Update status to "downloading"
        track.status = "downloading"
        session.add(track)
        
        def commit_status():
            session.commit()
        
        _db_operation_with_retry(commit_status)
        
        logger.info(f"Downloading track {track_id}: {track_title}")
        
        # ===== NO TRANSACTION: Perform actual download =====
        # This can take 10-60 seconds, no database locks held
        try:
            dl_func = getattr(downloader.core, "download_track_by_videoid", None)
            if dl_func is None:
                raise AttributeError("downloader.core.download_track_by_videoid not found")
            
            result = dl_func(
                video_id=track_id,
                artist_name=artist_name,
                album_name=album_name,
                track_title=track_title,
                track_number=track_number,
                year=year,
                cover_path_override=cover_path,
            )
            
            # Handle tuple return (file_path, cover_path)
            file_path = None
            new_cover_path = None
            
            if isinstance(result, tuple) and len(result) == 2:
                file_path, new_cover_path = result
            elif isinstance(result, str):
                file_path = result
            elif isinstance(result, dict):
                file_path = result.get("file_path")
            else:
                raise ValueError(f"Downloader returned unexpected type: {type(result)}")
            
            if not file_path:
                raise ValueError("Downloader did not return a valid file_path")
            
            # ===== TRANSACTION 2: Update track with success =====
            track = session.get(Track, str(track_id))  # Re-fetch after commit
            if not track:
                raise RuntimeError(f"Track {track_id} disappeared after commit")
            track.status = "done"
            track.file_path = str(file_path)
            session.add(track)
            
            def commit_track_update():
                session.commit()
            
            _db_operation_with_retry(commit_track_update)
            
            logger.info(f"Successfully downloaded track {track_id} to {file_path}")
            
            # ===== TRANSACTION 3: Update album cover (separate transaction) =====
            if new_cover_path and album_id_final:
                try:
                    album = session.get(Album, album_id_final)  # Re-fetch
                    if album:
                        from ..services.albums import ensure_album_cover
                        ensure_album_cover(
                            session=session,
                            album_obj=album,
                            final_cover_path=new_cover_path
                        )
                        
                        def commit_cover():
                            session.commit()
                        
                        _db_operation_with_retry(commit_cover)
                        logger.info(f"Updated album {album_id_final} cover to {new_cover_path}")
                except Exception as e:
                    session.rollback()
                    logger.warning(f"Failed to update album cover: {e}")

            # ===== TRANSACTION 4: Update album download status =====
            if track_album_id:
                try:
                    from ..services import subscriptions as subs_svc
                    new_status = subs_svc.check_and_update_album_download_status(
                        session,
                        track_album_id
                    )
                    
                    def commit_album_status():
                        session.commit()
                    
                    _db_operation_with_retry(commit_album_status)
                    logger.debug(f"Album {track_album_id} download status updated to: {new_status}")
                except Exception as e:
                    session.rollback()
                    logger.warning(f"Failed to update album download status: {e}")
            
            # ===== TRANSACTION 5: Queue lyrics download job =====
            try:
                from .jobqueue import enqueue_job
                enqueue_job(
                    session,
                    job_type="download_lyrics",
                    payload={"track_id": track_id},
                    priority=0,
                    commit=True,  # enqueue_job handles its own commit
                )
                logger.debug(f"Queued lyrics download for track {track_id}")
            except Exception as e:
                logger.warning(f"Failed to queue lyrics job for track {track_id}: {e}")
            
            return {
                "ok": True,
                "file_path": str(file_path),
                "track_id": track_id,
                "cover_path": new_cover_path,
            }
            
        except Exception as e:
            logger.exception(f"Download failed for track {track_id}")
            
            # ===== TRANSACTION: Update track status to failed =====
            try:
                track = session.get(Track, str(track_id))  # Re-fetch
                if not track:
                    logger.error(f"Track {track_id} not found when marking failed")
                else:
                    track.status = "failed"
                    session.add(track)
                    
                    def commit_failed_status():
                        session.commit()
                    
                    _db_operation_with_retry(commit_failed_status)
            except Exception as commit_error:
                logger.exception(f"Failed to update track status to failed: {commit_error}")
                session.rollback()
            
            return {
                "ok": False,
                "error": f"Download failed: {str(e)}",
                "retry_delay_seconds": 300,
            }
    
    except Exception as e:
        logger.exception(f"download_track failed for {track_id}")
        try:
            session.rollback()
        except Exception:
            pass
        return {
            "ok": False,
            "error": str(e),
            "retry_delay_seconds": 60,
        }


# ============================================================================
# TASK: DOWNLOAD LYRICS
# ============================================================================

def download_lyrics(
    session: Session,
    track_id: str,
) -> Dict[str, Any]:
    """
    Download synced lyrics for a track using LRCLIB API.
    
    Flow:
    1. Get track info from DB
    2. Query LRCLIB API (cached first, then full)
    3. Save .lrc file next to audio file
    4. Update Track.has_lyrics and Track.lyrics_local
    
    Only succeeds if syncedLyrics are available (plainLyrics only = retry later)
    
    Args:
        session: SQLAlchemy session
        track_id: Track video ID
    
    Returns:
        {"ok": bool, "lyrics_path": str, "error": str}
    """
    if not track_id:
        return {"ok": False, "error": "track_id required"}
    
    try:
        import requests
        from pathlib import Path
        from urllib.parse import urlencode
        
        # ===== TRANSACTION 1: Get track info =====
        track = session.get(Track, str(track_id))
        if not track:
            return {"ok": False, "error": f"Track {track_id} not found in database"}
        
        # Check if track has audio file
        if not track.file_path:
            return {"ok": False, "error": "Track has no audio file yet"}
        
        audio_path = Path(track.file_path)
        if not audio_path.exists():
            return {"ok": False, "error": f"Audio file not found: {track.file_path}"}
        
        # Get metadata for LRCLIB query
        track_name = track.title or ""
        
        # Get artist name
        artist_name = ""
        if track.artists and len(track.artists) > 0:
            artist_name = track.artists[0].get("name", "")
        
        # Get album name
        album_name = ""
        album = None
        if track.album_id:
            album = session.get(Album, track.album_id)
            if album:
                album_name = album.title or ""
        
        # Get duration
        duration = track.duration or 0
        
        if not track_name or not artist_name:
            return {"ok": False, "error": "Missing track name or artist name"}
        
        logger.info(f"Fetching lyrics for: {artist_name} - {track_name}")
        
        # ===== NO TRANSACTION: Fetch lyrics from API =====
        # Build query parameters
        params = {
            "track_name": track_name,
            "artist_name": artist_name,
            "album_name": album_name,
            "duration": duration,
        }
        
        # Try cached endpoint first
        synced_lyrics = None
        try:
            cached_url = f"https://lrclib.net/api/get-cached?{urlencode(params)}"
            logger.debug(f"Trying cached LRCLIB: {cached_url}")
            
            response = requests.get(cached_url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                synced_lyrics = data.get("syncedLyrics")
                if synced_lyrics:
                    logger.info(f"Found synced lyrics in cache for track {track_id}")
        except Exception as e:
            logger.debug(f"Cached LRCLIB failed: {e}")
        
        # If not in cache, try full endpoint
        if not synced_lyrics:
            try:
                full_url = f"https://lrclib.net/api/get?{urlencode(params)}"
                logger.debug(f"Trying full LRCLIB: {full_url}")
                
                response = requests.get(full_url, timeout=15)
                if response.status_code == 200:
                    data = response.json()
                    synced_lyrics = data.get("syncedLyrics")
                    if synced_lyrics:
                        logger.info(f"Found synced lyrics for track {track_id}")
                elif response.status_code == 404:
                    logger.info(f"No lyrics found for track {track_id}")
                    return {
                        "ok": False,
                        "error": "Lyrics not found",
                        "retry_delay_seconds": 86400,  # Retry in 24 hours
                    }
            except Exception as e:
                logger.exception(f"Full LRCLIB request failed: {e}")
                return {
                    "ok": False,
                    "error": f"LRCLIB request failed: {str(e)}",
                    "retry_delay_seconds": 3600,  # Retry in 1 hour
                }
        
        # Check if we got synced lyrics
        if not synced_lyrics:
            # API returned data but only plainLyrics
            logger.info(f"Only plain lyrics available for track {track_id}, will retry later")
            return {
                "ok": False,
                "error": "Only plain lyrics available (synced lyrics required)",
                "retry_delay_seconds": 86400,  # Retry in 24 hours
            }
        
        # Save .lrc file next to audio file
        lrc_path = audio_path.with_suffix(".lrc")
        try:
            with open(lrc_path, "w", encoding="utf-8") as f:
                f.write(synced_lyrics)
            logger.info(f"Saved lyrics to {lrc_path}")
        except Exception as e:
            logger.exception(f"Failed to save lyrics file: {e}")
            return {
                "ok": False,
                "error": f"Failed to save lyrics: {str(e)}",
                "retry_delay_seconds": 300,  # Retry in 5 minutes
            }
        
        # ===== TRANSACTION 2: Update track with lyrics info =====
        track = session.get(Track, str(track_id))  # Re-fetch to be safe
        if not track:
            raise RuntimeError(f"Track {track_id} disappeared after lyrics fetch")
        track.has_lyrics = True
        track.lyrics_local = str(lrc_path)
        session.add(track)
        
        def commit_lyrics():
            session.commit()
        
        _db_operation_with_retry(commit_lyrics)
        
        logger.info(f"Successfully downloaded lyrics for track {track_id}")
        
        return {
            "ok": True,
            "lyrics_path": str(lrc_path),
            "track_id": track_id,
        }
    
    except Exception as e:
        logger.exception(f"download_lyrics failed for {track_id}")
        try:
            session.rollback()
        except Exception:
            pass
        return {
            "ok": False,
            "error": str(e),
            "retry_delay_seconds": 3600,  # Retry in 1 hour for unexpected errors
        }


# ============================================================================
# TASK: IMPORT ALBUM
# ============================================================================

def import_album(
    session: Session,
    browse_id: str,
    artist_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fetch and import an album from YTMusic.
    
    Flow:
    1. Call albums_svc.fetch_and_upsert_album()
    2. Return summary
    
    Args:
        session: SQLAlchemy session
        browse_id: Album browse ID from YTMusic
        artist_id: Optional artist ID to link album to
    
    Returns:
        {"ok": bool, "album_id": str, "tracks_inserted": int}
    """
    if not browse_id:
        return {"ok": False, "error": "browse_id required"}
    
    try:
        logger.info(f"Importing album {browse_id}")
        
        # ===== TRANSACTION: Fetch and upsert album =====
        result = albums_svc.fetch_and_upsert_album(
            session=session,
            browse_id=browse_id,
            artist_id=artist_id,
        )
        
        def commit_album():
            session.commit()
        
        _db_operation_with_retry(commit_album)
        
        logger.info(
            f"Imported album {result['album_id']}: "
            f"{result['inserted_tracks']} new tracks, "
            f"{result['updated_tracks']} updated tracks"
        )
        
        return {
            "ok": True,
            "album_id": result["album_id"],
            "tracks_inserted": result["inserted_tracks"],
            "tracks_updated": result["updated_tracks"],
        }
    
    except Exception as e:
        logger.exception(f"import_album failed for {browse_id}")
        try:
            session.rollback()
        except Exception:
            pass
        return {
            "ok": False,
            "error": str(e),
            "retry_delay_seconds": 120,  # Retry in 2 minutes
        }


# ============================================================================
# TASK: SYNC ARTIST
# ============================================================================

def sync_artist(
    session: Session,
    artist_id: str,
) -> Dict[str, Any]:
    """
    Check an artist for new releases and import them.
    
    Flow:
    1. Fetch artist data from YTMusic
    2. Compare albums with DB
    3. Import new albums
    4. Update last_synced_at timestamp
    
    Args:
        session: SQLAlchemy session
        artist_id: Artist channel ID
    
    Returns:
        {"ok": bool, "new_albums": int, "new_tracks": int}
    """
    if not artist_id:
        return {"ok": False, "error": "artist_id required"}
    
    try:
        logger.info(f"Syncing artist {artist_id}")
        
        # ===== TRANSACTION 1: Fetch and upsert artist =====
        artist_data = artists_svc.fetch_and_upsert_artist(session, artist_id)
        
        def commit_artist():
            session.commit()
        
        _db_operation_with_retry(commit_artist)
        
        # ===== TRANSACTION 2: Get current albums from DB =====
        existing_albums = albums_svc.list_albums_for_artist_from_db(session, artist_id)
        existing_album_ids = {a["id"] for a in existing_albums}
        
        # Find new albums
        ytm_albums = artist_data.get("albums", []) + artist_data.get("singles", [])
        new_albums = [a for a in ytm_albums if a.get("id") not in existing_album_ids]
        
        if not new_albums:
            logger.info(f"No new albums found for artist {artist_id}")
            
            # Update sync timestamp
            from ..services import subscriptions as subs_svc
            subs_svc.mark_artist_synced(session, artist_id)
            
            def commit_sync():
                session.commit()
            
            _db_operation_with_retry(commit_sync)
            
            return {
                "ok": True,
                "new_albums": 0,
                "new_tracks": 0,
            }
        
        # ===== TRANSACTION 3: Import new albums =====
        logger.info(f"Found {len(new_albums)} new albums for artist {artist_id}")
        
        result = albums_svc.fetch_and_upsert_albums_for_artist(
            session=session,
            artist_id=artist_id,
            albums=[a for a in new_albums if a.get("type", "").lower() == "album"],
            singles=[a for a in new_albums if a.get("type", "").lower() in ("single", "ep")],
        )
        
        def commit_new_albums():
            session.commit()
        
        _db_operation_with_retry(commit_new_albums)
        
        # ===== TRANSACTION 4: Create album subscriptions =====
        from ..services import subscriptions as subs_svc
        for album_detail in result.get("details", []):
            album_id_to_sub = album_detail.get("album_id")
            if album_id_to_sub:
                try:
                    subs_svc.subscribe_to_album(session, album_id=album_id_to_sub, artist_id=artist_id)
                    
                    def commit_subscription():
                        session.commit()
                    
                    _db_operation_with_retry(commit_subscription)
                except Exception as e:
                    logger.exception(f"Failed to subscribe to new album {album_id_to_sub}")
                    session.rollback()
        
        # ===== TRANSACTION 5: Queue download jobs =====
        from .jobqueue import enqueue_job
        queued = 0
        for album_detail in result.get("details", []):
            album_id_for_tracks = album_detail.get("album_id")
            tracks = tracks_svc.list_tracks_for_album_from_db(session, album_id_for_tracks)
            
            for track in tracks:
                if track.get("status") in ["new", "failed"]:
                    try:
                        enqueue_job(
                            session,
                            job_type="download_track",
                            payload={
                                "track_id": track["id"],
                                "album_id": album_id_for_tracks,
                                "artist_id": artist_id,
                            },
                            priority=0,
                            commit=True,  # Each job commits separately
                        )
                        queued += 1
                    except Exception as e:
                        logger.exception(f"Failed to queue download for track {track['id']}")
        
        # ===== TRANSACTION 6: Update sync timestamp =====
        subs_svc.mark_artist_synced(session, artist_id)
        
        def commit_final_sync():
            session.commit()
        
        _db_operation_with_retry(commit_final_sync)
        
        logger.info(
            f"Synced artist {artist_id}: {result['albums_processed']} new albums, "
            f"{result['tracks_inserted']} new tracks, {queued} downloads queued"
        )
        
        return {
            "ok": True,
            "new_albums": result["albums_processed"],
            "new_tracks": result["tracks_inserted"],
            "downloads_queued": queued,
        }
    
    except Exception as e:
        logger.exception(f"sync_artist failed for {artist_id}")
        
        # Update sync timestamp with error
        try:
            from ..services import subscriptions as subs_svc
            subs_svc.mark_artist_synced(session, artist_id, error=str(e))
            
            def commit_sync_error():
                session.commit()
            
            _db_operation_with_retry(commit_sync_error)
        except Exception:
            session.rollback()
        
        return {
            "ok": False,
            "error": str(e),
            "retry_delay_seconds": 600,  # Retry in 10 minutes
        }


# ============================================================================
# TASK DISPATCHER
# ============================================================================

_TASK_MAP = {
    "download_track": download_track,
    "download_lyrics": download_lyrics,
    "import_album": import_album,
    "sync_artist": sync_artist,
}


def run_job_task(session: Session, job: Job) -> Dict[str, Any]:
    """
    Dispatch job to appropriate task handler.
    Called by the worker for each reserved job.
    
    Args:
        session: SQLAlchemy session
        job: Reserved Job instance
    
    Returns:
        Task result dict with {"ok": bool, "error": str (optional), ...}
    """
    try:
        # Parse payload
        payload = job.payload or {}
        if isinstance(payload, str):
            try:
                import json
                payload = json.loads(payload)
            except Exception:
                payload = {}
        
        # Get task handler
        job_type = (job.type or "").strip()
        handler = _TASK_MAP.get(job_type)
        
        if handler is None:
            logger.error(f"Unknown job type: {job_type}")
            return {"ok": False, "error": f"Unknown job type: {job_type}"}
        
        # Execute task (task handles its own commits)
        logger.debug(f"Executing task {job_type} with payload: {payload}")
        result = handler(session, **payload)
        
        return result or {"ok": True}
    
    except TypeError as e:
        # Wrong arguments passed to handler
        logger.exception(f"Task handler signature mismatch for job {job.id}")
        return {
            "ok": False,
            "error": f"Invalid task arguments: {str(e)}",
        }
    
    except Exception as e:
        logger.exception(f"Unexpected error in run_job_task for job {job.id}")
        try:
            session.rollback()
        except Exception:
            pass
        return {
            "ok": False,
            "error": f"Unexpected error: {str(e)}",
        }