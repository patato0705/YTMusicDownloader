# backend/services/normalizers.py
"""
Service-level normalizers for converting internal data formats.
These are different from ytm_service/normalizers which handle YTMusic API responses.

Purpose:
- ytm_service/normalizers: External API → Internal format
- services/normalizers: Internal format → DB/Business logic format
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("services.normalizers")


def normalize_artist_for_db(artist_data: dict) -> dict:
    """
    Convert API artist data to DB-ready format.
    
    Args:
        artist_data: Normalized artist data from adapter
        
    Returns:
        Dict ready for DB insertion with Artist model fields
    """
    return {
        "id": str(artist_data.get("id", "")),
        "name": artist_data.get("name"),
        "thumbnails": artist_data.get("thumbnails", []),
        "image_local": None,  # Will be set when cover is downloaded
        "followed": False,  # Default to not followed
    }


def normalize_album_for_db(album_data: dict, artist_id: Optional[str] = None) -> dict:
    """
    Convert API album data to DB-ready format.
    
    Args:
        album_data: Normalized album data from adapter
        artist_id: Optional artist ID to associate with album
        
    Returns:
        Dict ready for DB insertion with Album model fields
    """
    return {
        "id": album_data.get("id") or album_data.get("browseId", ""),
        "title": album_data.get("title"),
        "artist_id": artist_id or album_data.get("artist_id"),
        "thumbnails": album_data.get("thumbnails", []),
        "playlist_id": album_data.get("playlistId"),
        "year": album_data.get("year"),
        "type": album_data.get("type", "Album"),
        "image_local": None,  # Will be set when cover is downloaded
    }


def normalize_track_for_db(track_data: dict, album_id: Optional[str] = None) -> dict:
    """
    Convert API track data to DB-ready format.
    
    Args:
        track_data: Normalized track data from adapter
        album_id: Optional album ID to associate with track
        
    Returns:
        Dict ready for DB insertion with Track model fields
    """
    return {
        "id": track_data.get("id") or track_data.get("videoId", ""),
        "title": track_data.get("title"),
        "duration": track_data.get("duration_seconds") or track_data.get("duration"),
        "artists": track_data.get("artists", []),
        "album_id": album_id or track_data.get("album_id"),
        "track_number": track_data.get("track_number"),
        "has_lyrics": False,  # Default, will be updated when lyrics are fetched
        "lyrics_local": None,
        "file_path": None,
        "status": "new",
        "artist_valid": True,
    }


def normalize_search_results(raw_results: Dict[str, List[dict]]) -> Dict[str, List[dict]]:
    """
    Post-process search results for frontend consistency.
    Ensures all items have required fields with sensible defaults.
    
    Args:
        raw_results: Dict with keys "artists", "albums", "songs"
        
    Returns:
        Normalized results with consistent structure
    """
    normalized = {
        "artists": [],
        "albums": [],
        "songs": [],
    }
    
    # Normalize artists
    for artist in raw_results.get("artists", []):
        normalized["artists"].append({
            "resultType": "artist",
            "id": artist.get("id", ""),
            "name": artist.get("name", "Unknown Artist"),
            "thumbnail": artist.get("thumbnail"),
        })
    
    # Normalize albums
    for album in raw_results.get("albums", []):
        normalized["albums"].append({
            "resultType": "album",
            "id": album.get("id", ""),
            "title": album.get("title", "Untitled Album"),
            "artist": album.get("artist", "Unknown Artist"),
            "year": album.get("year"),
            "type": album.get("type", "Album"),
            "thumbnail": album.get("thumbnail"),
        })
    
    # Normalize songs
    for song in raw_results.get("songs", []):
        normalized["songs"].append({
            "resultType": "song",
            "id": song.get("id", ""),
            "title": song.get("title", "Untitled Track"),
            "artists": song.get("artists", []),
            "album": song.get("album", {}),
            "duration_seconds": song.get("duration_seconds"),
            "thumbnail": song.get("thumbnail"),
        })
    
    return normalized


def ensure_search_result_consistency(results: List[dict]) -> List[dict]:
    """
    Ensure search results have consistent structure (for old/flat search endpoint).
    Adds missing fields with defaults.
    
    Args:
        results: Flat list of search results
        
    Returns:
        List with consistent structure
    """
    normalized = []
    
    for item in results:
        result_type = (item.get("resultType") or item.get("type") or "").lower()
        
        # Ensure all items have core fields
        normalized_item = {
            **item,
            "resultType": result_type,
            "id": item.get("id", ""),
        }
        
        # Add type-specific defaults
        if result_type == "artist":
            normalized_item.setdefault("name", "Unknown Artist")
        elif result_type == "album":
            normalized_item.setdefault("title", "Untitled Album")
            normalized_item.setdefault("artist", "Unknown Artist")
        elif result_type in ("song", "track"):
            normalized_item.setdefault("title", "Untitled Track")
            normalized_item.setdefault("artists", [])
        
        normalized.append(normalized_item)
    
    return normalized