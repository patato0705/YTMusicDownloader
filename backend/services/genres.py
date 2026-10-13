# backend/services/genres.py
"""
Album and artist genres, from MusicBrainz then Deezer.

YouTube Music has no genre data, so it comes from two outside sources,
neither of which needs an API key:

- MusicBrainz: community-voted genres per release group (album) and per
  artist, specific ones ("french house", "conscious hip hop"). Many
  releases have none; artists far more often do. One request per second
  per IP at most, which the single worker-genres process keeps to
  (_MusicBrainz) -- nothing else ever calls it.
- Deezer: one coarse genre per album ("Dance", "Rap/Hip Hop", 26 in all),
  but on nearly every album.

Per album, the first of these that has anything wins:
  1. its MusicBrainz release group's genres
  2. the artist's MusicBrainz genres
  3. its Deezer album's genre
  4. the artist's most common Deezer genre
The two are never mixed: Deezer's "Rap/Hip Hop" next to MusicBrainz's
"Hip Hop" would be two genres to Jellyfin. At most MAX_GENRES, most votes
first. MusicBrainz names are title-cased to match Deezer's ("hip hop" ->
"Hip Hop"); Deezer's are kept as they are -- Jellyfin can split
"Rap/Hip Hop" itself.

One deliberate translation (_RENAMED): MusicBrainz's "hip hop" becomes
Deezer's "Rap/Hip Hop". MusicBrainz has no plain "rap" genre -- rap is
filed under hip hop (Eminem: "hip hop" 39 votes; "rap" only exists among
its free-form tags, which are too noisy to use) -- so without this no
album would ever be tagged Rap, and the same music would show up as
"Hip Hop" or "Rap/Hip Hop" depending on which source had it. In this
library, hip hop is rap nearly every time. Sub-genres ("Pop Rap",
"Conscious Hip Hop") are left as they are.

Both sources are searched by name, so a namesake is the main risk: an
artist is only accepted when its discography shares at least one album
title with ours. MusicBrainz is first asked by our YouTube Music channel,
which identifies the artist exactly when someone has linked it there.

lookup_artist() only talks to the sources; the fetch_genres task
(jobs/tasks.py) stores what it found and writes it to files. The DB
helpers at the bottom decide when an artist's genres are due.
"""
from __future__ import annotations
import logging
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

import requests
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import config
from ..jobs.jobqueue import enqueue_job, pending_jobs
from ..jobs.priorities import promote
from ..models import Album, Artist, ArtistSubscription
from ..settings import feature_enabled
from ..text_utils import fold
from ..time_utils import now_utc

logger = logging.getLogger("services.genres")

MAX_GENRES = 3
# Genres change slowly, but MusicBrainz keeps getting more of them
REFRESH_AFTER = timedelta(days=30)
_TIMEOUT = 20


class GenreSourceUnavailable(Exception):
    """A source failed in a way that may pass (network, 5xx, rate limit): retry later."""


# MusicBrainz asks every client to name itself and give a contact
_USER_AGENT = f"YTMusicDownloader/{config.APP_VERSION} ( https://github.com/patato0705/YTMusicDownloader )"


# ============================================================================
# SOURCES
# ============================================================================

class _MusicBrainz:
    BASE = "https://musicbrainz.org/ws/2"
    # 1 request/s on average per IP. Separately, busy times bring 503s for
    # everyone: a rate-limit bucket shared with other clients (its
    # X-RateLimit-Remaining swings by hundreds between two of our requests)
    # runs dry for a moment, and ~15% of requests bounce with Retry-After: 0.
    # Retrying soon is what works -- a long backoff only wastes the wait --
    # and giving up loses the artist's whole lookup, so be persistent.
    MIN_INTERVAL = 1.1
    RETRIES = 10

    def __init__(self) -> None:
        self._last = 0.0
        self._http = requests.Session()
        self._http.headers.update({"User-Agent": _USER_AGENT, "Accept": "application/json"})

    def get(self, path: str, **params: Any) -> Optional[Dict[str, Any]]:
        """GET a ws/2 resource as JSON; None when it doesn't exist (404)."""
        params["fmt"] = "json"
        error = ""
        retry_after = 0.0
        for attempt in range(self.RETRIES):
            wait = self._last + self.MIN_INTERVAL - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                response = self._http.get(f"{self.BASE}/{path}", params=params, timeout=_TIMEOUT)
            except requests.RequestException as e:
                error = str(e)
            else:
                if response.status_code == 404:
                    return None
                if response.ok:
                    return response.json()
                error = f"HTTP {response.status_code}"
                try:
                    retry_after = float(response.headers.get("Retry-After") or 0)
                except ValueError:
                    retry_after = 0.0
            if attempt < self.RETRIES - 1:
                # 1.5, 3, 4.5 ... 13.5 s: about a minute in all, unless told to wait longer
                time.sleep(max(retry_after, 1.5 * (attempt + 1)))
        raise GenreSourceUnavailable(f"MusicBrainz {path}: {error}")


class _Deezer:
    BASE = "https://api.deezer.com"
    # Codes in the 200-with-{"error": ...} answers Deezer gives
    _NOT_FOUND = 800

    def __init__(self) -> None:
        self._http = requests.Session()
        # Genre names are translated to the server's location otherwise
        # ("Chanson française", "Films/Jeux vidéo")
        self._http.headers.update({"User-Agent": _USER_AGENT, "Accept-Language": "en"})
        self._genre_names: Optional[Dict[int, str]] = None

    def get(self, path: str, **params: Any) -> Optional[Dict[str, Any]]:
        """GET an API resource as JSON; None when it doesn't exist."""
        try:
            response = self._http.get(f"{self.BASE}/{path}", params=params, timeout=_TIMEOUT)
        except requests.RequestException as e:
            raise GenreSourceUnavailable(f"Deezer {path}: {e}")
        if not response.ok:
            raise GenreSourceUnavailable(f"Deezer {path}: HTTP {response.status_code}")
        data = response.json()
        error = data.get("error") if isinstance(data, dict) else None
        if error:
            if error.get("code") == self._NOT_FOUND:
                return None
            raise GenreSourceUnavailable(f"Deezer {path}: {error.get('message') or error}")
        return data

    def genre_names(self) -> Dict[int, str]:
        if self._genre_names is None:
            data = self.get("genre") or {}
            self._genre_names = {int(g["id"]): str(g["name"]) for g in data.get("data") or [] if "id" in g}
        return self._genre_names


# One per process: only worker-genres runs lookups, so the MusicBrainz
# spacing above holds for the whole app
_musicbrainz = _MusicBrainz()
_deezer = _Deezer()


# ============================================================================
# NAMES AND TITLES
# ============================================================================

# Spelled in capitals however MusicBrainz writes them
_ACRONYMS = {"edm", "idm", "ebm", "uk", "us", "dj", "mpb", "r&b", "rnb", "ost", "aor", "ccm", "nrg"}
# Lowercase inside a name ("Drum and Bass", "Rock and Roll")
_SMALL_WORDS = {"and", "of", "the", "n", "or"}

# MusicBrainz genres given Deezer's name for the same thing (see the module
# docstring for why), keyed by the title-cased MusicBrainz name
_RENAMED = {"Hip Hop": "Rap/Hip Hop"}

# Deezer categories that aren't genres: as tags they'd file every
# soundtrack under "Films" and "Games" in Jellyfin
_DEEZER_NOT_GENRES = {"All", "Films/Games", "Audiobooks", "Kids"}


def title_case(genre: str) -> str:
    """MusicBrainz's lowercase genre names, cased like Deezer's: "hip hop" -> "Hip Hop"."""
    words = []
    for i, word in enumerate(genre.strip().split()):
        parts = []
        for part in word.split("-"):
            lower = part.lower()
            if lower in _ACRONYMS:
                parts.append(part.upper())
            elif i > 0 and lower in _SMALL_WORDS:
                parts.append(lower)
            else:
                parts.append(part[:1].upper() + part[1:])
        words.append("-".join(parts))
    return " ".join(words)


_EDITION_WORDS = (
    "deluxe", "edition", "remaster", "remastered", "anniversary", "expanded",
    "bonus", "version", "explicit", "clean", "special", "collector", "reissue",
)
_BRACKETED = re.compile(r"\s*[(\[]([^)\]]*)[)\]]")
_DASH_EDITION = re.compile(r"\s+-\s+[^-]*\b(" + "|".join(_EDITION_WORDS) + r")\b.*$", re.IGNORECASE)


def _title_keys(title: Optional[str]) -> Tuple[str, str]:
    """
    (the title itself, the title without edition suffixes), both normalized:
    "Random Access Memories (10th Anniversary Edition)" matches
    "Random Access Memories" on the second.
    """
    full = fold(title)

    def drop_edition(match: re.Match) -> str:
        return "" if any(w in match.group(1).casefold() for w in _EDITION_WORDS) else match.group(0)

    base = _DASH_EDITION.sub("", _BRACKETED.sub(drop_edition, title or ""))
    return full, (fold(base) or full)


@dataclass
class _Release:
    """One album of the artist, as a source lists it."""
    title: str
    year: str
    genres: List[str]
    keys: Tuple[str, str] = field(init=False)

    def __post_init__(self) -> None:
        self.keys = _title_keys(self.title)


def _match(title: str, year: Optional[str], releases: Sequence[_Release]) -> Optional[_Release]:
    """The source's release for one of our albums: same title, else same title
    without edition suffixes; the same year breaks ties."""
    keys = _title_keys(title)
    for level in (0, 1):
        hits = [r for r in releases if r.keys[level] == keys[level]]
        if hits:
            same_year = [r for r in hits if year and r.year == str(year)[:4]]
            return (same_year or hits)[0]
    return None


def _shares_an_album(our_titles: Sequence[str], releases: Sequence[_Release]) -> bool:
    """Whether a candidate artist is ours: at least one album title in common."""
    theirs = {r.keys[1] for r in releases}
    return any(_title_keys(t)[1] in theirs for t in our_titles)


# ============================================================================
# MUSICBRAINZ
# ============================================================================

def _mb_genres(raw: Optional[List[Dict[str, Any]]]) -> List[str]:
    voted = [g for g in raw or [] if g.get("name") and (g.get("count") or 0) > 0]
    voted.sort(key=lambda g: (-int(g.get("count") or 0), g["name"]))
    names = [title_case(g["name"]) for g in voted[:MAX_GENRES]]
    return [_RENAMED.get(name, name) for name in names]


def _mb_release_groups(mbid: str) -> List[_Release]:
    """The artist's whole discography with genres, 100 per request."""
    releases: List[_Release] = []
    offset = 0
    while offset < 500:  # a few prolific artists have thousands; their main albums come first
        data = _musicbrainz.get("release-group", artist=mbid, inc="genres", limit=100, offset=offset) or {}
        groups = data.get("release-groups") or []
        releases += [
            _Release(g.get("title") or "", (g.get("first-release-date") or "")[:4], _mb_genres(g.get("genres")))
            for g in groups
        ]
        offset += len(groups)
        if not groups or offset >= int(data.get("release-group-count") or 0):
            break
    return releases


def _lucene_phrase(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _mb_find_artist(
    channel_id: str, name: str, our_titles: Sequence[str], known_id: Optional[str]
) -> Tuple[Optional[str], List[_Release]]:
    """(MusicBrainz artist id, its discography), or (None, []) when not found."""
    if known_id:
        return known_id, _mb_release_groups(known_id)

    # Exact, when the artist's MusicBrainz page links our channel
    linked = _musicbrainz.get("url", resource=f"https://music.youtube.com/channel/{channel_id}", inc="artist-rels")
    for relation in (linked or {}).get("relations") or []:
        artist = relation.get("artist")
        if artist and artist.get("id"):
            return artist["id"], _mb_release_groups(artist["id"])

    found = _musicbrainz.get("artist", query=f"artist:{_lucene_phrase(name)}", limit=5) or {}
    candidates = [a for a in found.get("artists") or [] if (a.get("score") or 0) >= 90][:3]
    for candidate in candidates:
        releases = _mb_release_groups(candidate["id"])
        if _shares_an_album(our_titles, releases):
            return candidate["id"], releases
    return None, []


# ============================================================================
# DEEZER
# ============================================================================

def _dz_albums(deezer_id: str) -> List[_Release]:
    names = _deezer.genre_names()
    releases: List[_Release] = []
    index = 0
    while index < 300:
        data = _deezer.get(f"artist/{deezer_id}/albums", limit=100, index=index) or {}
        page = data.get("data") or []
        for album in page:
            name = names.get(int(album.get("genre_id") or -1))
            genres = [name] if name and name not in _DEEZER_NOT_GENRES else []
            releases.append(_Release(album.get("title") or "", (album.get("release_date") or "")[:4], genres))
        index += len(page)
        if not page or not data.get("next"):
            break
    return releases


def _dz_find_artist(
    name: str, our_titles: Sequence[str], known_id: Optional[str]
) -> Tuple[Optional[str], List[_Release]]:
    """(Deezer artist id, its albums), or (None, []) when not found."""
    if known_id:
        return known_id, _dz_albums(known_id)
    found = _deezer.get("search/artist", q=name, limit=5) or {}
    # Deezer's search is fuzzy: same name only, then the album check
    candidates = [a for a in found.get("data") or [] if fold(a.get("name")) == fold(name)][:3]
    for candidate in candidates:
        releases = _dz_albums(str(candidate["id"]))
        if _shares_an_album(our_titles, releases):
            return str(candidate["id"]), releases
    return None, []


# ============================================================================
# LOOKUP
# ============================================================================

@dataclass
class AlbumGenres:
    genres: List[str]
    source: Optional[str]  # e.g. "musicbrainz-album"; None when nothing was found


@dataclass
class ArtistGenres:
    genres: List[str]
    musicbrainz_id: Optional[str]
    deezer_id: Optional[str]
    albums: Dict[str, AlbumGenres]


def lookup_artist(
    channel_id: str,
    name: str,
    albums: Sequence[Tuple[str, str, Optional[str]]],
    musicbrainz_id: Optional[str] = None,
    deezer_id: Optional[str] = None,
) -> ArtistGenres:
    """
    Genres for an artist and each of its albums, given as (id, title, year).
    The ids are this artist on each source when an earlier lookup matched it.
    Raises GenreSourceUnavailable when a source can't be reached.
    """
    titles = [title for _, title, _ in albums]

    mb_id, mb_releases = _mb_find_artist(channel_id, name, titles, musicbrainz_id)
    mb_artist: List[str] = []
    if mb_id:
        mb_artist = _mb_genres(((_musicbrainz.get(f"artist/{mb_id}", inc="genres") or {}).get("genres")))

    picked: Dict[str, AlbumGenres] = {}
    for album_id, title, year in albums:
        release = _match(title, year, mb_releases)
        if release and release.genres:
            picked[album_id] = AlbumGenres(release.genres, "musicbrainz-album")
        elif mb_artist:
            picked[album_id] = AlbumGenres(mb_artist, "musicbrainz-artist")

    # Deezer only for what MusicBrainz had nothing at all for
    dz_id, dz_artist = deezer_id, []
    deezer_asked = len(picked) < len(albums)
    if deezer_asked:
        dz_id, dz_releases = _dz_find_artist(name, titles, deezer_id)
        counts = Counter(g for r in dz_releases for g in r.genres)
        dz_artist = [counts.most_common(1)[0][0]] if counts else []
        for album_id, title, year in albums:
            if album_id in picked:
                continue
            release = _match(title, year, dz_releases)
            if release and release.genres:
                picked[album_id] = AlbumGenres(release.genres, "deezer-album")
            elif dz_artist:
                picked[album_id] = AlbumGenres(dz_artist, "deezer-artist")

    for album_id, _, _ in albums:
        picked.setdefault(album_id, AlbumGenres([], None))

    logger.info(
        "Genres for %s: MusicBrainz %s, Deezer %s, %d/%d albums with genres",
        name, mb_id or "not found", (dz_id or "not found") if deezer_asked else "not needed",
        sum(1 for g in picked.values() if g.genres), len(albums),
    )
    return ArtistGenres(mb_artist or dz_artist, mb_id, dz_id, picked)


# ============================================================================
# WHEN (DB)
# ============================================================================

def _due_condition(cutoff):
    """SQL condition on Artist: never looked up, looked up too long ago, or
    an album that wasn't there at the last lookup."""
    unchecked_album = select(Album.id).where(Album.artist_id == Artist.id, Album.genres_checked_at.is_(None)).exists()
    return or_(Artist.genres_checked_at.is_(None), Artist.genres_checked_at < cutoff, unchecked_album)


def queue_lookup(session: Session, artist_id: str, *, origin, from_lookup: bool = False) -> bool:
    """
    Queue a fetch_genres for this artist if lookups are on and it's due (see
    _due_condition). One already waiting or running is enough: a waiting one
    is moved up to `origin`'s class instead. A running one may have read the
    artist's albums before a sync created the rest, so it calls this again
    when it's done (from_lookup, which ignores itself): the albums added
    meanwhile, if any, get a follow-up lookup. Does not commit. Returns
    whether a job was queued.
    """
    if not artist_id or not feature_enabled(session, "genres"):
        return False
    statuses = ("queued",) if from_lookup else ("queued", "reserved")
    waiting = pending_jobs(session, "fetch_genres", statuses=statuses, artist_id=artist_id)
    if waiting:
        promote(waiting[0], origin)
        return False
    due = session.execute(
        select(Artist.id).where(Artist.id == artist_id, _due_condition(now_utc() - REFRESH_AFTER))
    ).first()
    if not due:
        return False
    enqueue_job(session, job_type="fetch_genres", payload={"artist_id": artist_id}, origin=origin, commit=False)
    return True


def due_artist_ids(session: Session, limit: int) -> List[str]:
    """Subscribed artists whose genres are due, never-looked-up first."""
    return list(session.execute(
        select(Artist.id)
        .join(ArtistSubscription, ArtistSubscription.artist_id == Artist.id)
        .where(_due_condition(now_utc() - REFRESH_AFTER))
        .order_by(Artist.genres_checked_at.asc().nulls_first())
        .limit(limit)
    ).scalars().all())
