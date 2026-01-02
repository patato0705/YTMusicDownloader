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
from pathlib import Path

from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError

from ..models import Job, Track, Album, Artist
from ..services import albums as albums_svc
from ..services import artists as artists_svc
from ..services import tracks as tracks_svc
from .. import downloader

from ..config import YDL_COOKIEFILE

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
# HELPER: YTCOOKIES MANAGEMENT FOR RATE LIMITING
# ============================================================================

def _is_youtube_rate_limit_error(error_msg: str) -> bool:
    """
    Check if the error is YouTube's rate limit error.
    """
    if not error_msg:
        return False
    
    error_lower = str(error_msg).lower()
    return (
        "rate-limited by youtube" in error_lower or
        "current session has been rate-limited" in error_lower or
        ("this content isn't available" in error_lower and "try again later" in error_lower)
    )


def _reset_youtube_cookies() -> bool:
    """
    Delete the YouTube cookies file to reset the rate limit session.
    
    Returns:
        True if cookies were deleted, False otherwise
    """
    try:
        if YDL_COOKIEFILE.exists():
            YDL_COOKIEFILE.unlink()
            logger.info(f"Deleted YouTube cookies at {YDL_COOKIEFILE} to reset rate limit")
            return True
        else:
            logger.warning(f"YouTube cookies file not found at {YDL_COOKIEFILE}")
            return False
    except Exception as e:
        logger.exception(f"Failed to delete YouTube cookies: {e}")
        return False
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
    5. If rate-limited, delete cookies and retry
    6. Update Track table with file_path and status, COMMIT
    7. Update Album cover if new cover path returned, COMMIT
    
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
        # Get track info and update status
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
        
        # Perform download with retry on rate limit
        max_download_attempts = 2  # Try once, if rate-limited reset cookies and try once more
        last_error = None
        result = None
        
        for attempt in range(max_download_attempts):
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
                    skip_metadata=True,
                )
                
                # Success! Break out of retry loop
                break
                
            except Exception as download_error:
                last_error = download_error
                error_msg = str(download_error)
                
                # Check if this is a YouTube rate limit error
                if _is_youtube_rate_limit_error(error_msg):
                    logger.warning(
                        f"YouTube rate limit detected on attempt {attempt + 1}/{max_download_attempts} "
                        f"for track {track_id}"
                    )
                    
                    # If this is not the last attempt, reset cookies and retry
                    if attempt < max_download_attempts - 1:
                        cookies_deleted = _reset_youtube_cookies()
                        
                        if cookies_deleted:
                            logger.info(f"Retrying download for track {track_id} after cookie reset")
                            import time
                            time.sleep(2)  # Brief pause before retry
                            continue
                        else:
                            logger.error("Failed to reset cookies, not retrying")
                            # Fall through to raise below
                    
                    # Last attempt or cookie deletion failed
                    logger.error(
                        f"YouTube rate limit persists for track {track_id}"
                    )
                
                # Re-raise the error (either not a rate limit, or exhausted retries)
                raise
        
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
        
        # Update track with success
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
        
        # Update album cover
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

        # Update album download status
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
        
        # Queue lyrics download job
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
        
        # Update track status to failed
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
        
        # Check if this is a rate limit error for retry logic
        error_msg = str(e)
        if _is_youtube_rate_limit_error(error_msg):
            return {
                "ok": False,
                "error": f"Download failed: {error_msg}",
                "retry_delay_seconds": 600,  # Retry in 10 minutes if still rate-limited
            }
        else:
            return {
                "ok": False,
                "error": f"Download failed: {error_msg}",
                "retry_delay_seconds": 300,  # Standard retry delay
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
    Fetch and import an album from YTMusic, then queue download jobs.
    
    Flow:
    1. Fetch album data from YTMusic (includes full track list)
    2. Upsert album and tracks to database
    3. Queue download_track jobs for all new tracks
    4. Return summary
    
    Args:
        session: SQLAlchemy session
        browse_id: Album browse ID from YTMusic
        artist_id: Optional artist ID to link album to
    
    Returns:
        {"ok": bool, "album_id": str, "tracks_inserted": int, "downloads_queued": int}
    """
    if not browse_id:
        return {"ok": False, "error": "browse_id required"}
    
    try:
        logger.info(f"Importing album {browse_id}")
        
        # ===== NO TRANSACTION: Fetch from YTMusic API =====
        # This is an external API call, no database locks needed
        
        # ===== TRANSACTION 1: Upsert album and tracks =====
        result = albums_svc.fetch_and_upsert_album(
            session=session,
            browse_id=browse_id,
            artist_id=artist_id,
        )
        
        def commit_album():
            session.commit()
        
        _db_operation_with_retry(commit_album)
        
        album_id = result["album_id"]
        
        logger.info(
            f"Imported album {album_id}: "
            f"{result['inserted_tracks']} new tracks, "
            f"{result['updated_tracks']} updated tracks"
        )
        
        # ===== TRANSACTION 2: Queue download jobs for new tracks =====
        try:
            from .jobqueue import enqueue_job
            
            # Get tracks for this album
            tracks = tracks_svc.list_tracks_for_album_from_db(session, album_id)
            
            queued = 0
            for track in tracks:
                if track.get("status") in ["new", "failed"]:
                    try:
                        enqueue_job(
                            session,
                            job_type="download_track",
                            payload={
                                "track_id": track["id"],
                                "album_id": album_id,
                                "artist_id": artist_id,
                            },
                            priority=0,  # Low priority - background downloads
                            commit=True,  # Each job commits separately
                        )
                        queued += 1
                    except Exception as e:
                        logger.exception(f"Failed to queue download for track {track['id']}")
            
            logger.info(f"Queued {queued} download jobs for album {album_id}")
        
        except Exception as e:
            logger.warning(f"Failed to queue download jobs for album {album_id}: {e}")
            queued = 0
        
        return {
            "ok": True,
            "album_id": album_id,
            "tracks_inserted": result["inserted_tracks"],
            "tracks_updated": result["updated_tracks"],
            "downloads_queued": queued,
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
    Check an artist for new releases and queue import jobs.
    
    NEW BEHAVIOR:
    Instead of importing all albums synchronously, this now:
    1. Fetches artist data from YTMusic (just metadata + album list)
    2. Checks and updates artist banner if thumbnails changed
    3. Compares with existing albums in DB
    4. Creates album subscriptions for new albums
    5. Queues separate import_album jobs for each new album
    6. Returns quickly (3-5 seconds instead of 2+ minutes)
    
    Flow:
    1. Fetch artist data from YTMusic
    2. Check if thumbnails changed and update banner if needed
    3. Compare albums with DB
    4. Create album subscriptions for new albums
    5. Queue import_album job for each new album
    6. Update last_synced_at timestamp
    
    Args:
        session: SQLAlchemy session
        artist_id: Artist channel ID
    
    Returns:
        {"ok": bool, "new_albums": int, "jobs_queued": int, "banner_updated": bool}
    """
    if not artist_id:
        return {"ok": False, "error": "artist_id required"}
    
    try:
        logger.info(f"Syncing artist {artist_id}")
        
        # ===== TRANSACTION 1: Fetch and upsert artist =====
        artist_data = artists_svc.fetch_and_upsert_artist(session, artist_id)
        
        # Check if banner needs updating
        banner_updated = False
        try:
            artist_obj = session.get(Artist, artist_id)
            if artist_obj:
                # Get thumbnails from API response
                new_thumbnails = artist_data.get("thumbnails") or []
                
                # Normalize both thumbnail lists for comparison
                from ..ytm_service import normalizers as N
                new_thumbs_normalized = N.normalize_thumbnails(new_thumbnails)
                old_thumbs_normalized = N.normalize_thumbnails(artist_obj.thumbnails or [])
                
                # Check if thumbnails changed OR if banner doesn't exist
                thumbnails_changed = new_thumbs_normalized != old_thumbs_normalized
                banner_missing = not artist_obj.image_local or not Path(str(artist_obj.image_local)).exists()
                
                if thumbnails_changed or banner_missing:
                    if thumbnails_changed:
                        logger.info(f"Thumbnails changed for artist {artist_id}, updating banner")
                    if banner_missing:
                        logger.info(f"Banner missing for artist {artist_id}, downloading banner")
                    
                    # Update thumbnails in database if they changed
                    if thumbnails_changed:
                        artist_obj.thumbnails = new_thumbnails
                        session.add(artist_obj)
                    
                    # Download and update banner
                    banner_path = artists_svc.ensure_artist_banner(
                        session=session,
                        artist_obj=artist_obj,
                        thumbnails=new_thumbnails,
                    )
                    
                    if banner_path:
                        logger.info(f"Updated banner for artist {artist_id}: {banner_path}")
                        banner_updated = True
                    else:
                        logger.error(f"Failed to update banner for artist {artist_id}")
                        # Fail the task if banner download fails
                        return {
                            "ok": False,
                            "error": "Failed to download artist banner",
                            "retry_delay_seconds": 300,  # Retry in 5 minutes
                        }
                else:
                    logger.debug(f"Thumbnails unchanged and banner exists for artist {artist_id}, skipping banner update")
        except Exception as e:
            logger.exception(f"Failed to check/update banner for artist {artist_id}")
            # Fail the task if banner check fails
            return {
                "ok": False,
                "error": f"Failed to check/update artist banner: {e}",
                "retry_delay_seconds": 300,  # Retry in 5 minutes
            }
        
        def commit_artist():
            session.commit()
        
        _db_operation_with_retry(commit_artist)
        
        # ===== TRANSACTION 2: Get current albums from DB =====
        existing_albums = albums_svc.list_albums_for_artist_from_db(session, artist_id)
        existing_album_ids = {a["id"] for a in existing_albums}
        
        # Find new albums (no database operation)
        ytm_albums = artist_data.get("albums", []) + artist_data.get("singles", [])
        new_albums = [a for a in ytm_albums if a.get("id") not in existing_album_ids]
        
        if not new_albums:
            logger.info(f"No new albums found for artist {artist_id}")
            
            # ===== TRANSACTION 3: Update sync timestamp =====
            from ..services import subscriptions as subs_svc
            subs_svc.mark_artist_synced(session, artist_id)
            
            def commit_sync():
                session.commit()
            
            _db_operation_with_retry(commit_sync)
            
            return {
                "ok": True,
                "new_albums": 0,
                "jobs_queued": 0,
                "banner_updated": banner_updated,
            }
        
        logger.info(f"Found {len(new_albums)} new albums for artist {artist_id}")
        
        # ===== TRANSACTION 3: Create album subscriptions for new albums =====
        from ..services import subscriptions as subs_svc
        subscriptions_created = 0
        
        for album_item in new_albums:
            album_id = album_item.get("id") or album_item.get("browseId")
            if not album_id:
                continue
            
            try:
                subs_svc.subscribe_to_album(
                    session,
                    album_id=album_id,
                    artist_id=artist_id,
                    mode="download"
                )
                subscriptions_created += 1
            except Exception as e:
                logger.exception(f"Failed to create album subscription for {album_id}")
        
        def commit_subscriptions():
            session.commit()
        
        _db_operation_with_retry(commit_subscriptions)
        
        logger.info(f"Created {subscriptions_created} album subscriptions for artist {artist_id}")
        
        # ===== TRANSACTION 4: Queue import_album jobs =====
        from .jobqueue import enqueue_job
        jobs_queued = 0
        
        for album_item in new_albums:
            browse_id = album_item.get("id") or album_item.get("browseId")
            if not browse_id:
                continue
            
            try:
                enqueue_job(
                    session,
                    job_type="import_album",
                    payload={
                        "browse_id": browse_id,
                        "artist_id": artist_id,
                    },
                    priority=3,  # Medium priority (higher than downloads, lower than sync_artist)
                    commit=True,  # Each job commits separately
                )
                jobs_queued += 1
                logger.debug(f"Queued import_album job for {browse_id}")
            except Exception as e:
                logger.exception(f"Failed to queue import_album job for {browse_id}")
        
        logger.info(f"Queued {jobs_queued} import_album jobs for artist {artist_id}")
        
        # ===== TRANSACTION 5: Update sync timestamp =====
        subs_svc.mark_artist_synced(session, artist_id)
        
        def commit_final_sync():
            session.commit()
        
        _db_operation_with_retry(commit_final_sync)
        
        logger.info(
            f"Synced artist {artist_id}: {len(new_albums)} new albums, "
            f"{subscriptions_created} subscriptions created, {jobs_queued} import jobs queued, "
            f"banner {'updated' if banner_updated else 'unchanged'}"
        )
        
        return {
            "ok": True,
            "new_albums": len(new_albums),
            "subscriptions_created": subscriptions_created,
            "jobs_queued": jobs_queued,
            "banner_updated": banner_updated,
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