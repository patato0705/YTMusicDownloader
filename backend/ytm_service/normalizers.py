# backend/ytm_service/normalizers.py
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional, Sequence
from backend.schemas import Thumbnail as ThumbnailSchema

logger = logging.getLogger("ytm_service.normalizers")


def normalize_thumbnails(raw: Any) -> List[Dict[str, Optional[Any]]]:
    """
    Renvoie une liste de dicts {'url': str, 'width': Optional[int], 'height': Optional[int]}
    Accepts:
      - list of dicts like {'url':..., 'width':..., 'height':...}
      - list of dicts nested as {'thumbnail': {'thumbnails': [...]}} (we flatten)
      - list of strings (urls)
      - a single dict with 'thumbnails' key
    """
    out: List[Dict[str, Optional[Any]]] = []
    try:
        if raw is None:
            return out
        # if a dict with 'thumbnails' -> unwrap
        if isinstance(raw, dict) and "thumbnails" in raw:
            raw = raw.get("thumbnails") or []

        if isinstance(raw, list):
            for it in raw:
                if it is None:
                    continue
                # case: simple string url
                if isinstance(it, str):
                    out.append({"url": it, "width": None, "height": None})
                    continue
                # case: dict representing thumbnail or nested thumbnail
                if isinstance(it, dict):
                    # some items use 'url' key directly
                    url = it.get("url") or it.get("thumbnail") or None
                    # some nested forms: {'thumbnail': {'thumbnails': [...]}} -> skip here
                    if isinstance(url, dict):
                        # maybe nested thumbnail entry
                        url = url.get("url") or None
                    width = None
                    height = None
                    # attempt to parse width/height if present
                    w = it.get("width") or it.get("w")
                    h = it.get("height") or it.get("h")
                    try:
                        width = int(w) if w is not None else None
                    except Exception:
                        width = None
                    try:
                        height = int(h) if h is not None else None
                    except Exception:
                        height = None
                    if url and isinstance(url, str):
                        out.append({"url": url, "width": width, "height": height})
    except Exception:
        logger.exception("normalize_thumbnails failed for %r", raw)
    return out


def pick_best_thumbnail_url(ths: List[Dict[str, Optional[Any]]]) -> Optional[str]:
    """
    Tentative simple heuristics:
    - prefer the thumbnail with largest width
    - fallback to the last url available
    Accepts list of thumbnails as dicts (url,width,height).
    """
    if not ths:
        return None
    best = None
    best_w = -1
    for t in ths:
        try:
            url = t.get("url")
            w = t.get("width")
            if isinstance(w, int) and w > best_w and isinstance(url, str):
                best = url
                best_w = w
        except Exception:
            continue
    if best:
        return best
    # fallback: last url
    for t in reversed(ths):
        u = t.get("url")
        if isinstance(u, str):
            return u
    return None


def _build_thumbnails(thumbs_raw: Any) -> List[ThumbnailSchema]:
    """
    Normalise la liste de thumbs (via normalizers) et retourne une liste
    d'instances S.Thumbnail valides (filtre les entrées sans url).
    """
    out: List[ThumbnailSchema] = []
    th_list = normalize_thumbnails(thumbs_raw)
    if not isinstance(th_list, Sequence):
        return out

    for t in th_list:
        if not isinstance(t, dict):
            continue
        url = t.get("url")
        if not isinstance(url, str):
            continue

        def _to_int_or_none(v: Any) -> Optional[int]:
            if v is None:
                return None
            if isinstance(v, int):
                return v
            try:
                return int(v)
            except Exception:
                return None

        w = _to_int_or_none(t.get("width"))
        h = _to_int_or_none(t.get("height"))

        out.append(ThumbnailSchema(url=url, width=w, height=h))
    return out


def _extract_first_nested_artist(item: dict) -> dict | None:
    """
    Retourne le premier objet 'artist' imbriqué si présent (dict), sinon None.
    Gère différentes clés possibles ('artists', 'artist').
    """
    for key in ("artists", "artist"):
        val = item.get(key)
        if isinstance(val, list) and val:
            first = val[0]
            if isinstance(first, dict):
                return first
    return None

def _normalize_search_item(it: dict, include_raw: bool, allowed_set: Optional[set], default_exclude: set): # Used in search function
    """
    Retourne un dict normalisé ou None si filtré.
    """
    if not isinstance(it, dict):
        return None
    kind = (it.get("resultType") or it.get("type") or "").lower()
    if not kind:
        if it.get("videoId") or it.get("id"):
            kind = "song"

    if allowed_set is not None:
        if kind not in allowed_set:
            return None
    else:
        if kind in default_exclude:
            return None

    base: Dict[str, Any] = {"resultType": kind}
    if include_raw:
        base["raw"] = it

    if kind in ("song", "track"):
        base.update({
            "id": it.get("videoId") or it.get("id"),
            "title": it.get("title") or it.get("name"),
            "album": it.get("album") or [],
            "artists": [normalize_artist_entry(a) for a in (it.get("artists") or it.get("artist") or [])],
            "duration_seconds": it.get("duration_seconds") or it.get("duration"),
            "thumbnail": pick_best_thumbnail_url(it.get("thumbnails") or []),
        })
    elif kind == "artist":
        artists_list = it.get("artists") or []
        if not artists_list:
            base.update({
                "id": it.get("browseId") or it.get("id"),
                "name": it.get("title") or it.get("name") or it.get("artist"),
                "thumbnail": pick_best_thumbnail_url(it.get("thumbnails") or []),
            })
        else: # Top result
            nested = artists_list[0] if isinstance(artists_list, (list, tuple)) and len(artists_list) > 0 else {}
            base.update({
                "id": nested.get("browseId") or nested.get("id") or it.get("browseId") or it.get("id"),
                "name": nested.get("name") or it.get("title") or it.get("name") or it.get("artist"),
                "thumbnail": pick_best_thumbnail_url(it.get("thumbnails") or []),
            })
    elif kind == "album":
        base.update({
            "id": it.get("browseId") or it.get("id") or it.get("playlistId"),
            "title": it.get("title") or it.get("name"),
            "thumbnail": pick_best_thumbnail_url(it.get("thumbnails") or []),
            "artist": it.get("artists", [{}])[0].get("name") or "Unknown Artist",
            "year": it.get("year") or None,
        })
    else:
        if not include_raw:
            if it.get("browseId"):
                base["id"] = it.get("browseId")
            elif it.get("videoId"):
                base["id"] = it.get("videoId")
            if it.get("title"):
                base["title"] = it.get("title")
    return base

def _normalize_album_item(item: dict) -> Dict[str, Any]:
    """
    Normalize an album/single item from YTMusic response.
    Handles inconsistent formats from YTMusic API:
    """
    browse_id = item.get("browseId") or item.get("id") or ""
    playlist_id = item.get("audioPlaylistId") or item.get("playlistId") or ""
    title = item.get("title") or item.get("name") or None
    
    thumbs_models = _build_thumbnails(item.get("thumbnails", []))
    thumbs_dicts = [t.model_dump() for t in thumbs_models]
    thumbnail = pick_best_thumbnail_url(thumbs_dicts) if thumbs_models else None
    
    # Extract raw values
    raw_type = item.get("type")
    raw_year = item.get("year")
    
    item_type = None
    year = None
    
    # Valid type values
    valid_types = {"album", "single", "ep"}
    
    # STRATEGY: Check both fields and determine which format we have
    
    # Check if raw_type looks like a year (4 digits)
    type_is_year = (
        raw_type is not None 
        and str(raw_type).strip().isdigit() 
        and len(str(raw_type).strip()) == 4
    )
    
    # Check if raw_year looks like a type (valid type string)
    year_is_type = (
        raw_year is not None 
        and str(raw_year).strip().lower() in valid_types
    )
    
    # CASE 1: Buggy format - type/year are swapped
    if type_is_year and not year_is_type:
        # Year is in type field (albums from get_artist)
        year = str(raw_type).strip()
        item_type = "Album"  # Default for albums
    elif year_is_type and not type_is_year:
        # Type is in year field (singles from get_artist)
        item_type = str(raw_year).strip().capitalize()
        year = None
    # CASE 2: Both fields are swapped (rare but possible)
    elif type_is_year and year_is_type:
        year = str(raw_type).strip()
        item_type = str(raw_year).strip().capitalize()
    # CASE 3: Correct format (from get_artist_albums)
    else:
        # Check type field normally
        if raw_type is not None:
            type_str = str(raw_type).strip()
            if type_str.lower() in valid_types:
                item_type = type_str.capitalize()
            elif not type_str.isdigit():
                # Unknown type string, use it anyway
                item_type = type_str
        
        # Check year field normally
        if raw_year is not None:
            year_str = str(raw_year).strip()
            if year_str.isdigit() and len(year_str) == 4:
                year = year_str
    
    # Final defaults
    if item_type is None:
        item_type = "Album"
    
    return {
        "id": browse_id,
        "playlistId": playlist_id,
        "title": str(title),
        "thumbnails": thumbs_dicts,
        "thumbnail": thumbnail,
        "type": item_type,
        "year": year,
    }


def normalize_artist_entry(raw: Any) -> Dict[str, Optional[str]]:
    """
    Normalize an artist entry which can be:
      - dict with 'browseId'/'id' and 'name'/'title'
      - string name
      - dict with nested browseEndpoint
    Returns { 'id': Optional[str], 'name': Optional[str] }
    """
    if raw is None:
        return {"id": None, "name": None}
    try:
        if isinstance(raw, str):
            return {"id": None, "name": raw}
        if isinstance(raw, dict):
            # look for several possible keys
            aid = raw.get("id") or raw.get("browseId") or raw.get("channelId") or None
            name = raw.get("name") or raw.get("title") or None
            # sometimes it's nested inside navigationEndpoint -> browseEndpoint
            if not aid:
                nav = raw.get("navigationEndpoint") or {}
                if isinstance(nav, dict):
                    be = nav.get("browseEndpoint") or {}
                    if isinstance(be, dict):
                        aid = be.get("browseId") or aid
            return {"id": str(aid) if aid is not None else None, "name": str(name) if name is not None else None}
    except Exception:
        logger.exception("normalize_artist_entry failed for %r", raw)
    return {"id": None, "name": None}


def normalize_track_item(raw: Any) -> Dict[str, Optional[Any]]:
    """
    Convertit un item de piste (issu de playlist/album/watch) en dict standardisé
    attendu par TrackSchema:
      {
        "id": Optional[str],
        "title": Optional[str],
        "artists": [ { "id": Optional[str], "name": Optional[str] }, ... ],
        "duration_seconds": Optional[int],
        "track_number": Optional[int],
        "raw": raw
      }
    """
    out: Dict[str, Optional[Any]] = {
        "id": None,
        "title": None,
        "artists": [],
        "duration_seconds": None,
        "track_number": None,
        "raw": raw,
    }
    try:
        if raw is None:
            return out
        # if raw is a dict: attempt to find common fields
        if isinstance(raw, dict):
            vid = raw.get("videoId") or raw.get("id") or raw.get("video_id") or None
            out["id"] = str(vid) if vid is not None else None
            title = raw.get("title") or raw.get("name") or None
            out["title"] = str(title) if title is not None else None

            # artists: may be list of dicts or a string
            artists_src = raw.get("artists") or raw.get("artist") or raw.get("artistsList") or []
            artists_list = []
            if isinstance(artists_src, list):
                for a in artists_src:
                    artists_list.append(normalize_artist_entry(a))
            elif isinstance(artists_src, dict):
                # sometimes a single dict
                artists_list.append(normalize_artist_entry(artists_src))
            elif isinstance(artists_src, str):
                artists_list.append({"id": None, "name": artists_src})
            out["artists"] = artists_list

            # duration
            dur = raw.get("duration_seconds") or None
            try:
                out["duration_seconds"] = int(dur) if dur is not None else None
            except Exception:
                out["duration_seconds"] = None

            # track number / index
            tn = raw.get("trackNumber") or None
            try:
                out["track_number"] = int(tn) if tn is not None else None
            except Exception:
                out["track_number"] = None

            return out

        # if raw is a string, use as title
        if isinstance(raw, str):
            out["title"] = raw
            return out

    except Exception:
        logger.exception("normalize_track_item failed for %r", raw)
    return out