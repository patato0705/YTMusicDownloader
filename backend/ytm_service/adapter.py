# backend/ytm_service/adapter.py
"""
The YouTube Music calls the app makes, returning plain dicts (schemas.ytmusic
shapes). Every one raises YTMusicUnavailable when YouTube Music can't be
read, so a caller never mistakes an outage for an empty answer.
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List

from .client import call
from . import normalizers as N
from ..schemas import AlbumSchema, PlaylistSchema, TrackSchema
from ..text_utils import fold

logger = logging.getLogger("ytm_service.adapter")


class YTMusicUnavailable(RuntimeError):
    """
    YouTube Music couldn't be read, after the client's own retries (it does
    send empty or unparseable pages at times). Raised where an empty answer
    would pass for real data -- an album with no tracks, an artist with no
    releases -- so the caller fails, and its job retries, instead.
    """


def _call(method: str, what: str, expected: type, *args: Any, **kwargs: Any) -> Any:
    """client.call, with any failure or unexpected answer as YTMusicUnavailable."""
    try:
        raw = call(method, *args, **kwargs)
    except Exception as e:
        raise YTMusicUnavailable(f"{method} failed for {what}: {e}") from e
    if not isinstance(raw, expected):
        raise YTMusicUnavailable(f"Unexpected {method} response for {what}: {type(raw).__name__}")
    return raw


def _trim_to_complete_sentence(text: str) -> str:
    """
    YTMusic truncates artist descriptions mid-sentence. Trim back to the last
    sentence boundary so we don't store/display a half-sentence tail.
    """
    if not text:
        return text
    text = text.rstrip()
    if text.endswith((".", "!", "?", "\"", "”", ")")):
        return text
    best = -1
    for marker in (". ", "! ", "? ", ".\n", "!\n", "?\n"):
        best = max(best, text.rfind(marker))
    if best > 0:
        return text[: best + 1].rstrip()
    return text


def get_artist(channel_id: str) -> Dict[str, Any]:
    """
    An artist's page: name, description, pictures, every album and single
    (the full lists, not the page's first 10), and its similar artists.
    """
    raw = _call("get_artist", channel_id, dict, channelId=channel_id)
    thumbnails = N.normalize_thumbnails(raw.get("thumbnails"))
    return {
        "id": str(channel_id),
        "name": str(raw["name"]) if raw.get("name") else None,
        # The page's wide banner (kept for backdrop.jpg)
        "thumbnails": thumbnails,
        # The artist is shown round, so the same picture cropped square
        "thumbnail": N.resize_thumbnail_url(N.pick_best_thumbnail_url(thumbnails), N.CARD_THUMBNAIL_SIZE, crop=True),
        "description": _trim_to_complete_sentence(raw.get("description") or ""),
        "albums": _artist_releases(raw.get("albums"), channel_id),
        "singles": _artist_releases(raw.get("singles"), channel_id),
        "related": _related_artists(raw, channel_id),
    }


def _artist_releases(section: Any, channel_id: str) -> List[Dict[str, Any]]:
    """
    An artist page's albums or singles. The page lists the first few; when
    there are more, its "params" fetch the full list.
    """
    if not section:
        return []
    if section.get("params") is not None:
        items = _call(
            "get_artist_albums", channel_id, list,
            channelId=str(section.get("browseId")), params=str(section.get("params")),
        )
    else:
        items = section.get("results") or []
    return [N.normalize_album_item(item) for item in items if isinstance(item, dict)]


def _related_artists(raw: Dict[str, Any], channel_id: str) -> List[Dict[str, Any]]:
    """The artist page's "Fans might also like", most similar first (YouTube Music shows 10)."""
    out: List[Dict[str, Any]] = []
    seen = {str(channel_id)}
    for item in (raw.get("related") or {}).get("results") or []:
        if not isinstance(item, dict):
            continue
        related_id = item.get("browseId")
        name = item.get("title")
        if not related_id or not name or related_id in seen:
            continue
        seen.add(related_id)
        out.append({
            "id": str(related_id),
            "name": str(name),
            "thumbnail": N.best_thumbnail(item.get("thumbnails")),
        })
    return out


def _tracks(raw_tracks: Any, what: str, number: bool = False) -> List[TrackSchema]:
    """Track items as TrackSchema, skipping (and logging) any that can't be read."""
    tracks = []
    for idx, raw in enumerate(raw_tracks if isinstance(raw_tracks, list) else [], 1):
        try:
            tracks.append(TrackSchema(**N.normalize_track(raw, idx if number else None)))
        except Exception:
            logger.warning("Skipping unreadable track %d of %s", idx, what, exc_info=True)
    return tracks


def get_album(browse_id: str) -> Dict[str, Any]:
    """
    Full album details with all tracks (AlbumSchema). Never answers with an
    empty album: saved, it would pass for one with no tracks.
    """
    raw = _call("get_album", browse_id, dict, browseId=browse_id)
    if not raw.get("title"):
        raise YTMusicUnavailable(f"Album {browse_id} came back without a title")

    thumbnails = N.normalize_thumbnails(raw.get("thumbnails"))
    duration_seconds = raw.get("duration_seconds")
    return AlbumSchema(
        id=str(browse_id),
        playlistId=raw.get("audioPlaylistId") or None,
        title=str(raw["title"]),
        type=str(raw.get("type") or "Album"),
        thumbnails=thumbnails,
        cover=N.pick_best_thumbnail_url(thumbnails),
        isExplicit=bool(raw.get("isExplicit")),
        description=raw.get("description"),
        year=str(raw["year"]) if raw.get("year") else None,
        artists=[N.normalize_artist_entry(a) for a in raw.get("artists") or [] if isinstance(a, dict)],
        trackCount=raw.get("trackCount"),
        duration=str(raw["duration"]) if raw.get("duration") is not None else None,
        duration_seconds=int(duration_seconds) if isinstance(duration_seconds, (int, float)) else None,
        tracks=_tracks(raw.get("tracks"), f"album {browse_id}", number=True),
    ).model_dump()


def get_playlist(playlist_id: str) -> Dict[str, Any]:
    """
    A playlist with all its tracks (ytmusicapi stops at 100 unless told
    otherwise). Raises YTMusicUnavailable for a private playlist too, which
    YouTube Music won't show signed out: an empty answer would pass for a
    playlist emptied of its songs.
    """
    raw = _call("get_playlist", playlist_id, dict, playlistId=playlist_id, limit=None)
    author = raw.get("author")
    return PlaylistSchema(
        id=str(playlist_id),
        title=str(raw["title"]) if raw.get("title") else None,
        description=raw.get("description") or None,
        author=author.get("name") if isinstance(author, dict) else None,
        thumbnail=N.best_thumbnail(raw.get("thumbnails")),
        tracks=_tracks(raw.get("tracks"), f"playlist {playlist_id}"),
    ).model_dump()


def get_charts(country: str) -> Dict[str, Any]:
    """A country's top artists chart: {"artists": [{id, name, thumbnail, rank, trend}]}."""
    raw = _call("get_charts", country, dict, country=country)
    return {
        "artists": [
            {
                "id": str(a.get("browseId") or ""),
                "name": a.get("title"),
                "thumbnail": N.best_thumbnail(a.get("thumbnails")),
                "rank": a.get("rank"),
                "trend": a.get("trend"),
            }
            for a in raw.get("artists") or []
            if isinstance(a, dict)
        ]
    }


def _search(q: str, filter: str, limit: int, allowed_types: set) -> List[Dict[str, Any]]:
    """
    One filtered search. Results of other types than asked are dropped; when
    that leaves fewer than `limit`, the search is asked once more for twice
    as many.
    """
    results: List[Dict[str, Any]] = []
    seen = set()
    client_limit = max(10, limit)
    for _ in range(2):
        for item in _call("search", q, list, q, filter=filter, limit=client_limit):
            norm = N.normalize_search_item(item, allowed_types)
            key = norm and (norm.get("id") or f"{norm['resultType']}::{norm.get('title') or ''}")
            if norm and key not in seen:
                seen.add(key)
                results.append(norm)
        if len(results) >= limit:
            break
        client_limit *= 2
    return results[:limit]


def _album_opens(browse_id: str) -> bool:
    """Whether YouTube Music serves the album's page (one try, no retries)."""
    try:
        call("get_album", browseId=browse_id, max_retries=1)
        return True
    except Exception:
        return False


def _live_albums(albums: List[Dict[str, Any]], artists: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Album search lists some albums twice: the real entry, and a stale one
    with neither an audio playlist nor a linked artist, whose page YouTube
    Music serves empty (opening it fails). The artist's page only lists real
    entries, so a stale entry takes the id of the artist's release of the
    same title, or is dropped when that release is already in the results.
    One with no such release is kept only if its page opens after all.
    """
    stale = []
    for album in albums:
        if not album.pop("playlist_id") and not album.get("artist_id"):
            stale.append(album)
    if not stale:
        return albums

    # Stale entries don't link their artist: it's found by name among the results
    artist_ids = {fold(a["name"]): a["id"] for a in artists if a.get("name") and a.get("id")}
    for album in albums:
        if album.get("artist_id"):
            artist_ids.setdefault(fold(album["artist"]), album["artist_id"])

    listed = {a["id"] for a in albums}
    releases: Dict[str, Dict[str, str]] = {}  # artist id -> folded title -> release id
    dropped = set()
    for album in stale:
        artist_id = artist_ids.get(fold(album["artist"]))
        if artist_id and artist_id not in releases:
            releases[artist_id] = {}
            try:
                artist = get_artist(artist_id)
            except YTMusicUnavailable:
                logger.warning("Couldn't read artist %s to replace stale search results", artist_id)
            else:
                for release in artist["albums"] + artist["singles"]:
                    releases[artist_id].setdefault(fold(release["title"]), release["id"])
        live = releases.get(artist_id or "", {}).get(fold(album["title"]))
        if live and live in listed:
            dropped.add(album["id"])
        elif live:
            listed.add(live)
            album["id"] = live
            album["artist_id"] = artist_id
        elif not _album_opens(album["id"]):
            dropped.add(album["id"])
    return [a for a in albums if a["id"] not in dropped]


def search_all(q: str, limit_per_type: int) -> Dict[str, List[Dict[str, Any]]]:
    """
    Artists, albums and songs matching q, from one filtered search each: more
    reliable than an unfiltered search, whose "top results" are scraped
    inconsistently and carry less metadata (no album on songs).
    """
    artists = _search(q, "artists", limit_per_type, {"artist"})
    return {
        "artists": artists,
        "albums": _live_albums(_search(q, "albums", limit_per_type, {"album"}), artists),
        "songs": _search(q, "songs", limit_per_type, {"song", "track"}),
    }
