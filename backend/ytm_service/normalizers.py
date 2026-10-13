# backend/ytm_service/normalizers.py
"""Turn ytmusicapi's loosely shaped items into the dicts the adapter returns."""
from __future__ import annotations
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ytm_service.normalizers")


def _int_or_none(value: Any) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def normalize_thumbnails(raw: Any) -> List[Dict[str, Any]]:
    """
    Thumbnails as a list of {"url", "width", "height"}. Accepts a list of
    dicts or url strings, or a dict holding them under "thumbnails".
    """
    if isinstance(raw, dict):
        raw = raw.get("thumbnails") or []
    out: List[Dict[str, Any]] = []
    for it in raw if isinstance(raw, list) else []:
        if isinstance(it, str):
            out.append({"url": it, "width": None, "height": None})
        elif isinstance(it, dict):
            url = it.get("url") or it.get("thumbnail")
            if isinstance(url, dict):
                url = url.get("url")
            if isinstance(url, str) and url:
                out.append({"url": url, "width": _int_or_none(it.get("width")), "height": _int_or_none(it.get("height"))})
    return out


def pick_best_thumbnail_url(thumbnails: List[Dict[str, Any]]) -> Optional[str]:
    """The widest thumbnail's URL; the last one when none has a width."""
    if not thumbnails:
        return None
    with_width = [t for t in thumbnails if isinstance(t.get("width"), int)]
    if with_width:
        return max(with_width, key=lambda t: t["width"])["url"]
    return thumbnails[-1].get("url")


def best_thumbnail(raw: Any) -> Optional[str]:
    """pick_best_thumbnail_url of raw thumbnails in any shape normalize_thumbnails takes."""
    return pick_best_thumbnail_url(normalize_thumbnails(raw))


# Card artwork: what YouTube Music itself uses for its biggest cards
CARD_THUMBNAIL_SIZE = 544

_RESIZABLE_HOSTS = ("googleusercontent.com", "ggpht.com")
_SIZE_OPTION = re.compile(r"^[whs]\d+$")


def resize_thumbnail_url(url: Optional[str], size: int, crop: bool = False) -> Optional[str]:
    """
    Ask Google's image server for a size x size version of a thumbnail.

    Search results only list 60 and 120px versions of a picture that exists
    at any size: the size is the "=w120-h120-..." options at the end of the
    URL. Other options (quality, format) are kept, except "dc<hex>": a colour
    hint computed for the original picture, which Google refuses (HTTP 400)
    once the size changes. crop=True adds "p", which crops the original
    picture to a square instead of fitting it inside one; an artist's square
    crop shows more than its banner, which is a crop too.

    URLs from other hosts (i.ytimg.com video stills) are returned unchanged.
    """
    if not url or not any(host in url for host in _RESIZABLE_HOSTS):
        return url
    base, _, options = url.partition("=")
    kept = [
        o for o in options.split("-")
        if o and not _SIZE_OPTION.match(o) and o != "p" and not o.startswith("dc")
    ]
    wanted = [f"w{size}", f"h{size}"] + (["p"] if crop or "p" in options.split("-") else [])
    return f"{base}={'-'.join(wanted + kept)}"


def normalize_artist_entry(raw: Any) -> Dict[str, Optional[str]]:
    """
    An artist reference as {"id", "name"}, from a dict (browseId/id/channelId,
    name/title, or a nested navigationEndpoint) or a plain name.
    """
    if isinstance(raw, str):
        return {"id": None, "name": raw}
    if not isinstance(raw, dict):
        return {"id": None, "name": None}
    aid = raw.get("id") or raw.get("browseId") or raw.get("channelId")
    if not aid:
        endpoint = (raw.get("navigationEndpoint") or {}).get("browseEndpoint") or {}
        aid = endpoint.get("browseId") if isinstance(endpoint, dict) else None
    name = raw.get("name") or raw.get("title") or raw.get("artist")
    return {"id": str(aid) if aid else None, "name": str(name) if name else None}


def normalize_track(raw: Dict[str, Any], index: Optional[int] = None) -> Dict[str, Any]:
    """
    A track/song item as the fields of schemas.TrackSchema. `index` (1-based
    position in its album) stands in for a missing track number.
    """
    artists = raw.get("artists") or raw.get("artist") or []
    if not isinstance(artists, list):
        artists = [artists]
    album = raw.get("album")
    album_ref = None
    if isinstance(album, dict) and (album.get("id") or album.get("name")):
        album_ref = {"id": album.get("id"), "name": album.get("name")}
    elif isinstance(album, str):
        album_ref = {"id": None, "name": album}
    return {
        "id": str(raw.get("videoId") or raw.get("id") or ""),
        "title": str(raw.get("title") or raw.get("name") or ""),
        "artists": [normalize_artist_entry(a) for a in artists],
        "album": album_ref,
        "cover": best_thumbnail(raw.get("thumbnails")),
        "duration_seconds": _int_or_none(raw.get("duration_seconds")) or 0,
        "track_number": _int_or_none(raw.get("trackNumber")) or index,
        "isExplicit": bool(raw.get("isExplicit")),
    }


def _artist_card_thumbnail(it: dict) -> Optional[str]:
    """Search only lists 60 and 120px versions; artists are shown round, so square"""
    return resize_thumbnail_url(best_thumbnail(it.get("thumbnails")), CARD_THUMBNAIL_SIZE, crop=True)


def normalize_search_item(it: Any, allowed_types: set) -> Optional[Dict[str, Any]]:
    """A search result as the dict the frontend lists, or None if it isn't of an allowed type."""
    if not isinstance(it, dict):
        return None
    kind = (it.get("resultType") or it.get("type") or "").lower()
    if not kind and (it.get("videoId") or it.get("id")):
        kind = "song"
    if kind not in allowed_types:
        return None

    if kind in ("song", "track"):
        album = it.get("album")
        return {
            "resultType": kind,
            "id": it.get("videoId") or it.get("id"),
            "title": it.get("title") or it.get("name"),
            "album": album if isinstance(album, dict) else {},
            "artists": [normalize_artist_entry(a) for a in (it.get("artists") or it.get("artist") or [])],
            "duration_seconds": it.get("duration_seconds") or it.get("duration"),
            # Search only lists 60 and 120px versions
            "thumbnail": resize_thumbnail_url(best_thumbnail(it.get("thumbnails")), CARD_THUMBNAIL_SIZE),
        }
    if kind == "artist":
        # The top result nests the artist under "artists"
        nested = (it.get("artists") or [{}])[0]
        return {
            "resultType": kind,
            "id": nested.get("browseId") or nested.get("id") or it.get("browseId") or it.get("id"),
            "name": nested.get("name") or it.get("title") or it.get("name") or it.get("artist"),
            "thumbnail": _artist_card_thumbnail(it),
        }
    # album
    main_artist = normalize_artist_entry((it.get("artists") or [None])[0])
    return {
        "resultType": kind,
        "id": it.get("browseId") or it.get("id") or it.get("playlistId"),
        "title": it.get("title") or it.get("name"),
        "thumbnail": best_thumbnail(it.get("thumbnails")),
        "artist": main_artist["name"] or "Unknown Artist",
        "artist_id": main_artist["id"],
        "year": it.get("year") or None,
        "type": it.get("type") or "Album",
        # Its audio playlist; missing on stale entries (adapter._live_albums)
        "playlist_id": it.get("playlistId") or None,
    }


_RELEASE_TYPES = {"album", "single", "ep"}


def _is_year(value: Any) -> bool:
    text = str(value).strip() if value is not None else ""
    return len(text) == 4 and text.isdigit()


def normalize_album_item(item: dict) -> Dict[str, Any]:
    """
    An album/single item of an artist page. ytmusicapi swaps "type" and
    "year" in some lists (the year in "type" for albums from get_artist,
    the type in "year" for singles), so both are read from either field.
    """
    raw_type, raw_year = item.get("type"), item.get("year")
    values = [str(v).strip() for v in (raw_type, raw_year) if v is not None]
    year = next((v for v in values if _is_year(v)), None)
    item_type = next((v.capitalize() for v in values if v.lower() in _RELEASE_TYPES), None)
    if item_type is None and raw_type is not None and not str(raw_type).strip().isdigit():
        item_type = str(raw_type).strip()  # an unknown type string, kept as is

    thumbnails = normalize_thumbnails(item.get("thumbnails"))
    return {
        "id": item.get("browseId") or item.get("id") or "",
        "playlistId": item.get("audioPlaylistId") or item.get("playlistId") or "",
        "title": str(item.get("title") or item.get("name") or ""),
        "thumbnails": thumbnails,
        "thumbnail": pick_best_thumbnail_url(thumbnails),
        "type": item_type or "Album",
        "year": year,
    }
