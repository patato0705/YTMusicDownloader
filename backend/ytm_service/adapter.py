# backend/ytm_service/adapter.py
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional, Sequence, Iterable

from .client import call  # wrapper executing ytmusic methods (ex: call("get_artist", ...))
from . import normalizers as N
from backend.schemas import (
    AlbumSchema,
    TrackSchema,
    ArtistRefSchema,
    AlbumRefSchema,
    PlaylistSchema,
    SongSchema
)

logger = logging.getLogger("ytm_service.adapter")


def _safe_call(name: str, *args, **kwargs) -> Any:
    """
    Centralized call to client.call — Log and escalate exceptions.
    """
    try:
        return call(name, *args, **kwargs)
    except Exception as e:
        logger.exception("YTMusic client.call(%s) failed: %s", name, e)
        raise


def _ensure_track_payload(nt: Dict[str, Any]) -> Dict[str, Any]:
    """
    Guarantees that the returned dict by normalize_track_item has
    necessary fields at TrackSchema expected by TrackSchema.
    """
    if not isinstance(nt, dict):
        raise TypeError("normalize_track_item must return a dict")
    title = nt.get("title") or nt.get("name") or ""
    track_id = nt.get("id") or nt.get("videoId") or ""
    track_id = str(track_id)
    artists_raw = nt.get("artists") or []
    if not isinstance(artists_raw, Sequence):
        artists_raw = []
    artists_out: List[Dict[str, Optional[str]]] = []
    for a in artists_raw:
        if isinstance(a, dict):
            aid = a.get("id")
            aname = a.get("name") or a.get("title") or a.get("artist") or None
            artists_out.append({"id": str(aid) if aid is not None else None, "name": str(aname) if aname is not None else None})
        elif isinstance(a, str):
            artists_out.append({"id": None, "name": a})
        else:
            continue
    duration_seconds = nt.get("duration_seconds")
    try:
        duration_int = int(duration_seconds) if duration_seconds is not None else None
    except Exception:
        duration_int = None
    
    # Handle album as dict (from normalize_track_item)
    album_raw = nt.get("album") or {}
    album_id = None
    album_name = None
    if isinstance(album_raw, dict):
        album_id = album_raw.get("id") or None
        album_name = album_raw.get("name") or None
        if album_name:
            album_name = str(album_name)
    elif isinstance(album_raw, str):
        album_name = album_raw
    
    # Handle thumbnails - Add this section
    thumbnail_url = None
    track_thumbs = nt.get("thumbnails", [])
    if track_thumbs:
        thumbs_models = N._build_thumbnails(track_thumbs)
        thumbs_dicts = [t.model_dump() for t in thumbs_models]
        thumbnail_url = N.pick_best_thumbnail_url(thumbs_dicts) if thumbs_models else None
    
    track_number = nt.get("trackNumber") or nt.get("track_number") or nt.get("index") or None
    try:
        track_number_int = int(track_number) if track_number is not None else None
    except Exception:
        track_number_int = None
    return {
        "id": track_id,
        "title": str(title),
        "artists": artists_out,
        "duration": duration_int,
        "album_id": str(album_id) if album_id is not None else None,
        "album_name": album_name,
        "thumbnail": thumbnail_url,  # Add this line
        "track_number": track_number_int,
        "raw": nt,
    }

def _append_unique(out: List[Dict[str, Any]], item: Dict[str, Any], seen: set) -> bool:
    if not item:
        return False
    identifier = item.get("id") or (f"{item.get('resultType')}::{item.get('title') or ''}")
    if identifier in seen:
        return False
    seen.add(identifier)
    out.append(item)
    return True

def get_artist(channel_id: str) -> Dict[str, Any]:
    """
    Get artist info including embedded albums/singles (limited to 10 each).
    Returns structured data with albums and singles separated.
    """
    raw = None
    try:
        raw = _safe_call("get_artist", channelId=channel_id)
    except Exception:
        return {
            "id": str(channel_id),
            "name": None,
            "thumbnails": [],
            "thumbnail": None,
            "description": None,
            "albums": [],
            "singles": [],
        }
    if not isinstance(raw, dict):
        return {
            "id": str(channel_id),
            "name": None,
            "thumbnails": [],
            "thumbnail": None,
            "description": None,
            "albums": [],
            "singles": [],
        }
    
    # Extract basic artist info
    name = raw.get("name")
    description = raw.get("description") or ""
    thumbs_models = N._build_thumbnails(raw.get("thumbnails", []))
    thumbs_dicts = [t.model_dump() for t in thumbs_models]
    thumbnail = N.pick_best_thumbnail_url(thumbs_dicts) if thumbs_models else None
    
    # Get artist's albums - handle missing 'albums' key
    albums_data = []
    if raw.get("albums"):
        if raw["albums"].get("params") is not None:
            albums_browseId = str(raw["albums"].get("browseId"))
            albums_params = str(raw["albums"].get("params"))
            albums_data = get_artist_albums(browseId=albums_browseId, params=albums_params)
        else:
            raw_album_data = raw["albums"].get("results", [])
            for item in raw_album_data:
                if isinstance(item, dict):
                    albums_data.append(N._normalize_album_item(item))
    
    # Get artist's singles - handle missing 'singles' key
    singles_data = []
    if raw.get("singles"):
        if raw["singles"].get("params") is not None:
            singles_browseId = str(raw["singles"].get("browseId"))
            singles_params = str(raw["singles"].get("params"))
            singles_data = get_artist_albums(browseId=singles_browseId, params=singles_params)
        else:
            raw_singles_data = raw["singles"].get("results", [])
            for item in raw_singles_data:
                if isinstance(item, dict):
                    singles_data.append(N._normalize_album_item(item))
    
    return {
        "id": str(channel_id),
        "name": str(name) if name is not None else None,
        "thumbnails": thumbs_dicts,
        "thumbnail": thumbnail,
        "description": description,
        "albums": albums_data,
        "singles": singles_data,
    }


def get_artist_albums(browseId: str, params: str) -> List[Dict[str, Any]]:
    """
    Get full list of albums or singles for an artist.
    Use the params from get_artist() response to fetch complete list.
    """
    try:
        raw_list = _safe_call("get_artist_albums", channelId=browseId, params=params)
    except Exception:
        logger.exception("get_artist_albums failed for browseId=%s, params=%s", browseId,params)
        return []

    if not isinstance(raw_list, list):
        return []

    results = []
    for item in raw_list:
        if isinstance(item, dict):
            results.append(N._normalize_album_item(item))
    
    return results


def get_album(browse_id: str) -> Dict[str, Any]:
    """
    Get full album details with all tracks.
    
    Args:
        browse_id: Album browse ID (e.g., "MPREb_sjcfEKGhGc6")
        
    Returns:
        Dict representation of AlbumSchema with all album info and tracks
        
    Raises:
        ValueError: If browse_id is empty or response is invalid
        Exception: If API call fails
    """
    if not browse_id:
        raise ValueError("browse_id required")
    
    # Call YTMusic API
    try:
        raw = _safe_call("get_album", browseId=browse_id)
    except Exception:
        logger.exception("Failed to get album for browse_id=%s", browse_id)
        # Return minimal schema on error
        return AlbumSchema(
            id=str(browse_id),
            title="Unknown Album",
            tracks=[]
        ).model_dump()
    
    if not isinstance(raw, dict):
        logger.error("Invalid response type for album %s: %s", browse_id, type(raw))
        return AlbumSchema(
            id=str(browse_id),
            title="Unknown Album",
            tracks=[]
        ).model_dump()
    
    # Extract basic info with safe defaults
    title = raw.get("title") or "Unknown Album"
    album_type = raw.get("type") or "Album"
    is_explicit = bool(raw.get("isExplicit", False))
    description = raw.get("description")
    year = str(raw.get("year")) if raw.get("year") else None
    track_count = raw.get("trackCount")
    
    # Album duration (human readable string like "21 minutes")
    album_duration_raw = raw.get("duration")
    album_duration = str(album_duration_raw) if album_duration_raw is not None else None
    
    # Album duration in seconds (integer)
    album_duration_seconds = raw.get("duration_seconds")
    if album_duration_seconds is not None:
        try:
            album_duration_seconds = int(album_duration_seconds)
        except (ValueError, TypeError):
            album_duration_seconds = None
    
    playlist_id = raw.get("audioPlaylistId")
    
    # Build thumbnails
    thumbs_models = N._build_thumbnails(raw.get("thumbnails", []))
    thumbs_dicts = [t.model_dump() for t in thumbs_models]
    cover = N.pick_best_thumbnail_url(thumbs_dicts) if thumbs_models else None
    
    # Extract artists
    artists_raw = raw.get("artists", [])
    artists_models = []
    for a in artists_raw:
        if isinstance(a, dict):
            artists_models.append(
                ArtistRefSchema(
                    id=a.get("id"),
                    name=a.get("name")
                )
            )
    
    # Parse tracks
    tracks_raw = raw.get("tracks", [])
    tracks_models = []

    if isinstance(tracks_raw, list):
        for idx, track in enumerate(tracks_raw, 1):
            try:
                # Extract track duration (different variable name to avoid conflict!)
                track_duration_seconds = track.get("duration_seconds")
                
                # Normalize track using existing function
                nt_raw = N.normalize_track_item(track)
                nt = _ensure_track_payload(nt_raw)
                
                # Extract isExplicit
                track_is_explicit = track.get("isExplicit", False)
                
                # Get track number
                track_num = track.get("trackNumber") or nt.get("track_number") or idx
                
                # Create TrackSchema instance
                track_schema = TrackSchema(
                    id=nt.get("id") or "",
                    title=nt.get("title") or "",
                    artists=[
                        ArtistRefSchema(id=a.get("id"), name=a.get("name"))
                        for a in nt.get("artists", [])
                    ],
                    duration_seconds=int(track_duration_seconds) if track_duration_seconds is not None else 0,
                    track_number=int(track_num) if track_num is not None else idx,
                    isExplicit=bool(track_is_explicit),
                    raw=track
                )
                tracks_models.append(track_schema)
                
            except Exception:
                logger.debug(
                    "Skipping invalid track %d in album %s", 
                    idx, browse_id, 
                    exc_info=True
                )
                continue
    
    # Build AlbumSchema
    album_model = AlbumSchema(
        id=str(browse_id),
        playlistId=str(playlist_id) if playlist_id else None,
        title=str(title),
        type=str(album_type),
        thumbnails=thumbs_models,  # Pydantic models
        cover=cover,
        isExplicit=is_explicit,
        description=description,
        year=year,
        artists=artists_models,  # Pydantic models
        trackCount=track_count,
        duration=album_duration,  # String like "21 minutes"
        duration_seconds=album_duration_seconds,  # Integer
        tracks=tracks_models,  # Pydantic models
    )
    
    return album_model.model_dump()


def get_playlist(playlist_id: str) -> Dict[str, Any]:
    try:
        raw = _safe_call("get_playlist", playlistId=playlist_id)
    except Exception:
        model = PlaylistSchema(id=str(playlist_id), title=None, thumbnails=[], tracks=[], raw=None)
        return model.model_dump()
    if not isinstance(raw, dict):
        model = PlaylistSchema(id=str(playlist_id), title=None, thumbnails=[], tracks=[], raw=raw)
        return model.model_dump()
    # Extract playlist title and thumbnails
    title = raw.get("title") or None
    thumbs_models = N._build_thumbnails(raw.get("thumbnails") or [])
    # Process tracks
    tracks_raw = raw.get("tracks") or []
    tracks_models_objects: List[TrackSchema] = []
    
    logger.debug("Processing %d tracks from playlist", len(tracks_raw))
    
    if isinstance(tracks_raw, list):
        for idx, t in enumerate(tracks_raw):
            try:
                # Normalize the track data
                nt_raw = N.normalize_track_item(t)
                nt = _ensure_track_payload(nt_raw)
                
                # Build album - TrackSchema expects Optional[AlbumRefSchema]
                album_id = nt.get("album_id")
                album_name = nt.get("album_name")
                album_obj = None
                if album_id or album_name:
                    album_obj = AlbumRefSchema(id=album_id, name=album_name)

                # Map the normalized data to the TrackSchema fields
                track_data = {
                    "id": nt.get("id") or "",
                    "title": nt.get("title") or "",
                    "artists": [
                        ArtistRefSchema(id=a.get("id"), name=a.get("name"))
                        for a in nt.get("artists", [])
                    ],
                    "album": album_obj,  # Pass single AlbumRefSchema or None
                    "cover": nt.get("thumbnail"),
                    "duration_seconds": nt.get("duration") or 0,
                    "track_number": nt.get("track_number") or None,
                    "isExplicit": t.get("isExplicit", False),
                    "raw": t
                }
                # Create the TrackSchema instance
                ts = TrackSchema(**track_data)
                tracks_models_objects.append(ts)
                logger.debug("Successfully processed track %d: %s", idx, nt.get("title"))
            except Exception as e:
                logger.error("Failed to process track %d: %s", idx, str(e), exc_info=True)
                continue
    
    logger.debug("Successfully processed %d out of %d tracks", len(tracks_models_objects), len(tracks_raw))
    
    # Create the final PlaylistSchema model with the processed data
    model = PlaylistSchema(
        id=str(playlist_id),
        title=str(title) if title is not None else None,
        thumbnails=thumbs_models,
        tracks=tracks_models_objects,
    )
    
    # Return the model's data as a dictionary
    return model.model_dump()


def get_charts(country: str = "US") -> Dict[str, Any]:
    try:
        raw = _safe_call("get_charts", country=country)
    except Exception:
        return {"artists": [], "songs": [], "raw": None}

    if not isinstance(raw, dict):
        return {"artists": [], "songs": [], "raw": raw}

    artists_in = raw.get("artists") or []
    artists_out: List[Dict[str, Any]] = []
    if isinstance(artists_in, Sequence):
        for a in artists_in:
            if not isinstance(a, dict):
                continue
            thumbs_models = N._build_thumbnails(a.get("thumbnails") or [])
            artists_out.append({
                "id": str(a.get("browseId") or a.get("channelId") or a.get("id") or ""),
                "name": a.get("title") or a.get("name"),
                "thumbnails": [t.model_dump() for t in thumbs_models],
                "raw": a,
            })

    songs_in = raw.get("tracks") or raw.get("songs") or []
    songs_out: List[Dict[str, Any]] = []
    if isinstance(songs_in, Sequence):
        for s in songs_in:
            try:
                nt_raw = N.normalize_track_item(s)
                nt = _ensure_track_payload(nt_raw)
                ts = TrackSchema(**nt)
                songs_out.append(ts.model_dump())
            except Exception:
                logger.debug("Skipping invalid chart song %r", s, exc_info=True)
                continue

    return {"artists": artists_out, "songs": songs_out, "raw": raw}


def search(q: str, filter: Optional[str] = None, limit: int = 10,
           include_raw: bool = True,
           allowed_types: Optional[Iterable[str]] = None,
           max_fetch: int = 200,
           fetch_multiplier: int = 2,
           max_attempts: int = 2) -> List[Dict[str, Any]]:
    try:
        q = str(q or "").strip()
        if not q:
            return []

        try:
            lim = int(limit or 0)
        except Exception:
            lim = 10

        allowed_set: Optional[set] = None
        if allowed_types is not None:
            try:
                allowed_set = {str(x).lower().strip() for x in allowed_types if x is not None}
            except Exception:
                allowed_set = None

        default_exclude = {"podcast", "episode", "playlist", "video"}

        results: List[Dict[str, Any]] = []
        seen = set()

        # initial client_limit: at least requested limit, give some headroom but don't exceed max_fetch
        client_limit = min(max(10, lim), int(max_fetch))

        attempt = 0
        while attempt < int(max_attempts):
            attempt += 1
            try:
                raw = _safe_call("search", q, filter=filter, limit=client_limit)
            except Exception:
                raw = []

            if not isinstance(raw, Sequence):
                raw = []

            for it in raw:
                norm = N._normalize_search_item(it, include_raw=include_raw, allowed_set=allowed_set, default_exclude=default_exclude)
                if norm is None:
                    continue
                _append_unique(results, norm, seen)
                if lim and len(results) >= lim:
                    break

            if lim and len(results) >= lim:
                break

            # if we've already reached max_fetch on client side, stop
            if client_limit >= int(max_fetch):
                break

            # increase client_limit for next attempt (bounded)
            client_limit = min(int(max_fetch), max(client_limit * fetch_multiplier, lim * fetch_multiplier))
            # continue loop to fetch more

        if lim and len(results) > lim:
            results = results[:lim]

        return results

    except Exception:
        logger.exception("ytm_service.adapter.search unexpected error")
        return []


def search_artists(q: str, limit: int = 10, include_raw: bool = False, **kwargs) -> List[Dict[str, Any]]:
    """
    Search for artists only using YTMusic filter - more reliable than unfiltered search.
    Returns normalized artist results.
    """
    return search(
        q=q,
        filter="artists",
        limit=limit,
        include_raw=include_raw,
        allowed_types=["artist"],
        **kwargs
    )


def search_albums(q: str, limit: int = 10, include_raw: bool = False, **kwargs) -> List[Dict[str, Any]]:
    """
    Search for albums only using YTMusic filter - more reliable than unfiltered search.
    Returns normalized album results with more complete metadata.
    """
    return search(
        q=q,
        filter="albums",
        limit=limit,
        include_raw=include_raw,
        allowed_types=["album"],
        **kwargs
    )


def search_songs(q: str, limit: int = 10, include_raw: bool = False, **kwargs) -> List[Dict[str, Any]]:
    """
    Search for songs only using YTMusic filter - more reliable than unfiltered search.
    Returns normalized song results with album info.
    """
    return search(
        q=q,
        filter="songs",
        limit=limit,
        include_raw=include_raw,
        allowed_types=["song", "track"],
        **kwargs
    )


def search_all_filtered(
    q: str,
    limit_per_type: int = 10,
    include_raw: bool = False,
    **kwargs
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Search all types using individual filtered searches for maximum reliability.
    
    This is preferred over unfiltered search because:
    - Avoids inconsistent "top results" scraping
    - Returns more complete metadata (e.g., album info on songs)
    - More reliable result types and structure
    
    Args:
        q: Search query
        limit_per_type: Max results per type (artists, albums, songs)
        include_raw: Whether to include raw YTMusic response
        **kwargs: Additional arguments passed to individual search functions
    
    Returns:
        Dict with keys: "artists", "albums", "songs"
        Each containing a list of normalized results
    """
    try:
        return {
            "artists": search_artists(q, limit=limit_per_type, include_raw=include_raw, **kwargs),
            "albums": search_albums(q, limit=limit_per_type, include_raw=include_raw, **kwargs),
            "songs": search_songs(q, limit=limit_per_type, include_raw=include_raw, **kwargs),
        }
    except Exception:
        logger.exception("search_all_filtered failed for q=%r", q)
        return {"artists": [], "albums": [], "songs": []}