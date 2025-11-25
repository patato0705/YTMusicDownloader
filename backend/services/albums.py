# backend/services/albums.py
"""
Album entity CRUD operations and album-specific business logic.
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from pathlib import Path

import requests
from sqlalchemy.orm import Session

from ..ytm_service import adapter as ytm_adapter
from ..ytm_service import normalizers as N
from .. import config

if TYPE_CHECKING:
    from ..models import Album, Track

logger = logging.getLogger("services.albums")


# ============================================================================
# ALBUM CRUD
# ============================================================================

def upsert_album(
    session: Session,
    album_id: str,
    title: Optional[str],
    artist_id: Optional[str] = None,
    thumbnails: Optional[List[Any]] = None,
    image_local: Optional[str] = None,
    year: Optional[str] = None,
    album_type: Optional[str] = None,
    playlist_id: Optional[str] = None,
) -> Album:
    """
    Upsert an Album row. thumbnails is raw list (list[dict]).
    album_type: "Album", "Single", "EP", etc.
    Returns the Album instance (not committed).
    """
    from ..models import Album  # Import here to avoid circular dependency
    
    if not album_id:
        raise ValueError("album_id required")

    obj = session.get(Album, str(album_id))

    if obj is None:
        obj = Album(
            id=str(album_id),
            title=str(title) if title is not None else "",
            artist_id=str(artist_id) if artist_id is not None else None,
            thumbnails=thumbnails or None,
            image_local=str(image_local) if image_local else None,
            year=str(year) if year is not None else None,
            type=str(album_type) if album_type is not None else "Album",
            playlist_id=str(playlist_id) if playlist_id is not None else None,
        )
        session.add(obj)
        logger.debug(f"Created new album: {album_id}")
    else:
        changed = False
        if title is not None and obj.title != title:
            obj.title = title
            changed = True
        if artist_id is not None and obj.artist_id != artist_id:
            obj.artist_id = artist_id
            changed = True
        if thumbnails and obj.thumbnails != thumbnails:
            obj.thumbnails = thumbnails
            changed = True
        if image_local and obj.image_local != image_local:
            obj.image_local = image_local
            changed = True
        if year is not None and obj.year != year:
            obj.year = str(year)
            changed = True
        if album_type is not None and obj.type != album_type:
            obj.type = album_type
            changed = True
        if playlist_id is not None and obj.playlist_id != playlist_id:
            obj.playlist_id = playlist_id
            changed = True
        if changed:
            session.add(obj)
            logger.debug(f"Updated album: {album_id}")

    return obj


def get_album_from_db(
    session: Session,
    album_id: str,
    include_tracks: bool = True,
) -> Optional[Dict[str, Any]]:
    """
    Get a single album from DB by ID.
    
    Args:
        session: SQLAlchemy session
        album_id: Album ID
        include_tracks: If True, include full track list
    
    Returns:
        Dict with album data, or None if not found
    """
    from ..models import Album, Track
    
    try:
        album = session.get(Album, album_id)
        if not album:
            return None
        
        result = {
            "id": album.id,
            "title": album.title,
            "artist_id": album.artist_id,
            "year": album.year,
            "type": album.type or "Album",
            "thumbnails": album.thumbnails,
            "image_local": album.image_local,
            "playlist_id": album.playlist_id,
        }
        
        if include_tracks:
            tracks = (
                session.query(Track)
                .filter(Track.album_id == album_id)
                .order_by(Track.id.asc())
                .all()
            )
            result["tracks"] = [track.to_dict() for track in tracks]
        
        return result
    except Exception as e:
        logger.exception(f"get_album_from_db failed for {album_id}: {e}")
        return None


def list_albums_for_artist_from_db(
    session: Session,
    artist_id: str,
) -> List[Dict[str, Any]]:
    """
    Query DB for albums with artist_id. Returns a list of lightweight dicts.
    Includes type field to distinguish albums from singles/EPs.
    
    Returns:
        List of dicts with: id, title, thumbnail, image_local, year, type
    """
    from ..models import Album
    
    result: List[Dict[str, Any]] = []
    try:
        query = (
            session.query(Album)
            .filter(Album.artist_id == artist_id)
            .order_by(Album.year.desc().nullslast(), Album.title.asc())
        )
        
        for album in query.all():
            album_type = album.type or "Album"
            
            result.append({
                "id": album.id,
                "title": album.title,
                "thumbnails": album.thumbnails,
                "image_local": album.image_local,
                "year": album.year,
                "type": album_type,
            })
    except Exception as e:
        logger.exception(f"list_albums_for_artist_from_db failed for {artist_id}: {e}")
    
    return result


# ============================================================================
# ALBUM COVER MANAGEMENT
# ============================================================================

def ensure_album_cover(
    session: Session,
    album_obj: Album,
    thumbnails: Optional[List[Any]] = None,
    dest_dir: Optional[str] = None,
    final_cover_path: Optional[str] = None,
) -> Optional[str]:
    """
    Ensure the album has a local cover image. Downloads the best thumbnail if needed.
    
    Args:
        album_obj: Album model instance (should be attached to session)
        thumbnails: raw thumbnails (list[dict]) - optional, prefer these over album_obj.thumbnails
        dest_dir: override directory to save the cover. If None, uses COVERS_DIR from config
        final_cover_path: If provided from downloader, use this path directly
    
    Returns:
        Path to the saved cover (string) or None if failed
    """
    from ..models import Album
    
    if not album_obj:
        return None

    # If final path provided from downloader, use it directly
    if final_cover_path:
        p = Path(final_cover_path)
        if p.exists():
            album_obj.image_local = final_cover_path
            session.add(album_obj)
            logger.info(f"Updated album {album_obj.id} cover to {final_cover_path}")
            return final_cover_path

    # If album already has image_local and file exists -> return it
    cur_path = album_obj.image_local
    if cur_path:
        p = Path(str(cur_path))
        if p.exists():
            return str(p)

    # Pick thumbnails list to use
    thumbs_src = thumbnails or album_obj.thumbnails or []
    
    # Normalize and pick best thumbnail
    norm_thumbs = N.normalize_thumbnails(thumbs_src)
    best_url = N.pick_best_thumbnail_url(norm_thumbs) if norm_thumbs else None
    if not best_url:
        logger.warning(f"No thumbnail URL found for album {album_obj.id}")
        return None

    # Determine destination directory
    out_dir = Path(dest_dir) if dest_dir else (Path(str(config.COVERS_DIR)) if config.COVERS_DIR else None)
    if out_dir is None:
        logger.warning("No covers dest_dir configured; skipping cover save")
        return None
    out_dir.mkdir(parents=True, exist_ok=True)

    # Filename: album.id.jpg
    fname = f"{album_obj.id}.jpg"
    out_path = out_dir / fname

    # Download and save
    try:
        resp = requests.get(best_url, timeout=15)
        resp.raise_for_status()
        with open(out_path, "wb") as fh:
            fh.write(resp.content)
        
        # Update album_obj.image_local
        album_obj.image_local = str(out_path)
        session.add(album_obj)
        logger.info(f"Saved cover for album {album_obj.id}: {out_path}")
        
        return str(out_path)
    except Exception as e:
        logger.exception(f"Failed to download/save cover from {best_url} to {out_path}: {e}")
        return None


# ============================================================================
# FETCH & UPSERT ALBUM FROM YTMUSIC
# ============================================================================

def fetch_and_upsert_album(
    session: Session,
    browse_id: str,
    artist_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fetches an album via ytm_adapter.get_album(),
    upserts the album and its tracks to the database.
    
    IMPORTANT: Gets playlist data first to use audio IDs instead of video IDs.
    
    Args:
        session: SQLAlchemy session
        browse_id: YTMusic album browseId (e.g., "MPREb_sjcfEKGhGc6")
        artist_id: Optional artist ID to link the album to
    
    Returns:
        Dict with: {album_id, inserted_tracks, updated_tracks, cover_path}
    
    Note: Does NOT commit the session - caller controls transaction.
    """
    from ..models import Track
    
    if not browse_id:
        raise ValueError("browse_id required")

    # Fetch album data
    try:
        album_data = ytm_adapter.get_album(browse_id=browse_id)
    except Exception as e:
        logger.exception(f"ytm_adapter.get_album failed for browse_id={browse_id}")
        raise RuntimeError(f"Failed to fetch album from YTMusic: {e}")

    # Extract metadata
    album_id = album_data.get("id") or browse_id
    album_title = album_data.get("title") or "Unknown Album"
    thumbnails = album_data.get("thumbnails") or []
    year = album_data.get("year")
    album_type = album_data.get("type") or "Album"
    playlist_id = album_data.get("playlistId")
    tracks = album_data.get("tracks") or []
    
    # Extract artist from album data if not provided
    if not artist_id:
        artists = album_data.get("artists", [])
        if artists and isinstance(artists, list) and len(artists) > 0:
            first_artist = artists[0]
            if isinstance(first_artist, dict):
                artist_id = first_artist.get("id")

    logger.info(f"Fetched album {album_id}: {album_title} ({len(tracks)} tracks)")

    # Upsert album
    album_obj = upsert_album(
        session=session,
        album_id=str(album_id),
        title=album_title,
        artist_id=artist_id,
        thumbnails=thumbnails,
        year=year,
        album_type=album_type,
        playlist_id=playlist_id,
    )

    # Ensure cover
    cover_path = None
    try:
        dest_dir = str(config.COVERS_DIR) if config.COVERS_DIR else None
        cover_path = ensure_album_cover(
            session=session,
            album_obj=album_obj,
            thumbnails=thumbnails,
            dest_dir=dest_dir,
        )
    except Exception as e:
        logger.exception(f"ensure_album_cover failed for {album_id}: {e}")

    # Get playlist data for audio IDs
    playlist_tracks = []
    if playlist_id:
        try:
            playlist_data = ytm_adapter.get_playlist(playlist_id)
            playlist_tracks = playlist_data.get("tracks", [])
            logger.info(f"Fetched playlist {playlist_id}: {len(playlist_tracks)} tracks")
        except Exception as e:
            logger.warning(f"Failed to fetch playlist {playlist_id}: {e}")

    # Build audio ID map
    audio_id_map = {}
    if playlist_tracks:
        for idx, pl_track in enumerate(playlist_tracks):
            audio_id = pl_track.get("videoId") or pl_track.get("id")
            if audio_id:
                audio_id_map[idx] = {
                    "audio_id": audio_id,
                    "title": (pl_track.get("title") or "").lower().strip(),
                    "duration": pl_track.get("duration_seconds"),
                }
    
    # Upsert tracks
    from .tracks import upsert_track
    
    inserted = 0
    updated = 0
    replaced = 0
    
    for idx, track_data in enumerate(tracks):
        try:
            video_id = track_data.get("id") or track_data.get("videoId")
            if not video_id:
                continue

            title = track_data.get("title") or "Unknown Track"
            duration = track_data.get("duration_seconds") or track_data.get("duration")
            
            # Normalize artists
            artists_raw = track_data.get("artists", [])
            artists_for_db = []
            if isinstance(artists_raw, list):
                for a in artists_raw:
                    if isinstance(a, dict):
                        artists_for_db.append({
                            "id": a.get("id"),
                            "name": a.get("name"),
                        })
            
            track_number = track_data.get("track_number") or idx + 1
            
            # Use audio ID from playlist if available
            final_track_id = video_id
            if idx in audio_id_map:
                audio_info = audio_id_map[idx]
                audio_id = audio_info["audio_id"]
                
                if audio_id != video_id:
                    album_title_lower = title.lower().strip()
                    playlist_title_lower = audio_info["title"]
                    
                    title_match = (
                        album_title_lower == playlist_title_lower or
                        album_title_lower in playlist_title_lower or
                        playlist_title_lower in album_title_lower or
                        album_title_lower.split("(")[0].strip() == playlist_title_lower.split("(")[0].strip()
                    )
                    
                    if title_match:
                        logger.info(f"Using audio ID for '{title}': {video_id} → {audio_id}")
                        final_track_id = audio_id
                        replaced += 1

            # Check if track exists
            pre_existing = session.get(Track, str(final_track_id))
            
            # Preserve status if track has file
            if pre_existing and pre_existing.file_path:
                status = pre_existing.status or "done"
                file_path = pre_existing.file_path
            else:
                status = "new"
                file_path = None

            # Upsert track
            upsert_track(
                session=session,
                track_id=str(final_track_id),
                track_number=int(track_number),
                title=title,
                duration_seconds=int(duration) if duration is not None else None,
                artists_list=artists_for_db,
                album_id=str(album_id),
                status=status,
                file_path=file_path,
                artist_valid=True,
            )

            if pre_existing is None:
                inserted += 1
            else:
                updated += 1

        except Exception as e:
            logger.exception(f"Error processing track for album {album_id}: {e}")
            continue

    logger.info(
        f"Album {album_id} upserted: {inserted} new, {updated} updated, {replaced} IDs replaced"
    )

    session.flush()

    return {
        "album_id": str(album_id),
        "inserted_tracks": inserted,
        "updated_tracks": updated,
        "replaced_ids": replaced,
        "cover_path": cover_path,
    }


# ============================================================================
# FETCH & UPSERT MULTIPLE ALBUMS FOR ARTIST
# ============================================================================

def fetch_and_upsert_albums_for_artist(
    session: Session,
    artist_id: str,
    albums: List[Dict[str, Any]],
    singles: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Given a list of album/single items (from ytm_adapter.get_artist response),
    fetches and upserts each album to the database.
    
    Args:
        session: SQLAlchemy session
        artist_id: Artist channel ID
        albums: List of album items (normalized dicts with id, title, etc.)
        singles: List of single items (normalized dicts with id, title, etc.)
    
    Returns:
        Dict with: {artist_id, albums_processed, tracks_inserted, tracks_updated, details: [...]}
    
    Note: Does NOT commit the session - caller controls transaction.
    """
    all_items = albums + singles
    processed = 0
    total_inserted = 0
    total_updated = 0
    details: List[Dict[str, Any]] = []

    for item in all_items:
        try:
            browse_id = item.get("id") or item.get("browseId")
            
            if not browse_id:
                continue

            logger.info(f"Processing album {browse_id} for artist {artist_id}")

            result = fetch_and_upsert_album(
                session=session,
                browse_id=browse_id,
                artist_id=artist_id,
            )
            
            processed += 1
            total_inserted += result.get("inserted_tracks", 0)
            total_updated += result.get("updated_tracks", 0)
            details.append(result)

        except Exception as e:
            logger.exception(f"Failed to process album for artist {artist_id}: {e}")
            continue

    session.flush()

    return {
        "artist_id": artist_id,
        "albums_processed": processed,
        "tracks_inserted": total_inserted,
        "tracks_updated": total_updated,
        "details": details,
    }