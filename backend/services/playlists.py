# backend/services/playlists.py
"""
YouTube Music playlists added to the library.

A playlist brings in what its songs belong to -- their albums ("albums"
mode) or their main artists, followed in full ("artists" mode) -- and is
either followed (rescanned on the `scheduler.playlist_sync` schedule, new
songs bringing in their albums or artists) or kept as added ("once": its
song list is never fetched again).

Either way it can be written out as an M3U file, MUSIC_DIR/Playlists/
<title>.m3u8, which Jellyfin turns into a playlist (and follows on each
library scan: additions, removals, order). It lists the playlist's songs
that are in the library, in playlist order, with paths relative to it, and
is rewritten after each scan and whenever one of its songs finishes
downloading. A song that leaves a followed playlist leaves the M3U; its
file stays, it belongs to its album.

A music video has no album: its song is looked for and, found, stands in
for it (fetch_playlist). An upload (UGC) isn't a song, and what it credits
is whoever uploaded it, a YouTube user and not an artist: it brings in
nothing, in either mode, and is counted as skipped like a video whose song
wasn't found.

The work a playlist starts (album downloads, artist follows) carries the
origin of the sync that found it: BULK for adding a playlist or switching
it to artists, like charts; AUTO for the scheduled rescans.
"""
from __future__ import annotations
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import or_, select, func
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from .. import config
from ..downloader.core import fit_name, safe_name
from ..jobs.jobqueue import enqueue_job, pending_jobs
from ..jobs.priorities import Origin, promote
from ..models import Album, Job, Playlist, PlaylistEntry, Track, VideoSong
from ..time_utils import ensure_timezone_aware, now_utc
from ..ytm_service import adapter as ytm_adapter
from ..ytm_service import normalizers as N
from . import subscriptions as subs_svc

logger = logging.getLogger("services.playlists")

MODES = ("albums", "artists")
M3U_DIR_NAME = "Playlists"
RETRY_DELAY_SECONDS = 120


class PlaylistAlreadyAdded(ValueError):
    """add_playlist() for a playlist already in the library."""


# The playlist IDs YouTube Music opens: user playlists (PL), album playlists
# (OLAK5uy_), its curated playlists and mixes (RDCLAK5uy_, RDTMAK5uy_...);
# and, with a signed-in client, the account's liked songs (LM, LL). Anything
# else (a word, a video, album or artist ID) isn't one, and is turned away
# before YouTube Music is asked.
_PLAYLIST_ID = re.compile(r"(?:PL|OLAK5uy_|RD)[A-Za-z0-9_-]{10,}|LM|LL")


def parse_playlist_id(raw: str) -> Optional[str]:
    """
    The playlist ID in `raw`, without the "VL" its YouTube Music page
    (browse/VL...) puts before it, so both forms are the same playlist; None
    when it isn't shaped like a YouTube playlist ID.
    """
    playlist_id = raw.strip()
    if playlist_id.startswith("VL"):
        playlist_id = playlist_id[2:]
    return playlist_id if _PLAYLIST_ID.fullmatch(playlist_id) else None


def m3u_dir() -> Path:
    return config.MUSIC_DIR / M3U_DIR_NAME


# ============================================================================
# ENTRIES
# ============================================================================

def fetch_playlist(session: Session, playlist_id: str) -> Dict[str, Any]:
    """
    adapter.get_playlist, with the songs already found for its music videos
    (a video has no album, its song does: see VideoSong): such a track gets
    its song's album and a "song": {id, title}. The music videos still to
    look up are in "videos_to_look_up", for look_up_songs: one search each
    is too slow for a request, so a job does it (queue_song_lookup, or the
    scan itself). Raises YTMusicUnavailable when the playlist can't be read.
    """
    data = ytm_adapter.get_playlist(playlist_id)
    tracks = [t for t in data.get("tracks") or [] if _needs_song(t)]
    known = _known_songs(session, {t["id"] for t in tracks})
    for t in tracks:
        row = known.get(t["id"])
        if row is not None and row.song_id:
            t["album"] = {"id": row.album_id, "name": row.album_title}
            t["song"] = {"id": row.song_id, "title": row.song_title}
    to_look_up = {t["id"]: _video(t) for t in tracks if t["id"] not in known}
    data["videos_to_look_up"] = list(to_look_up.values())
    return data


# How long a music video whose song wasn't found waits to be looked up again
VIDEO_SONG_RETRY = timedelta(days=7)
# Searches at once: fewer than the client's YTM_MAX_CONC, so syncs, imports
# and pages still get through while a long playlist is looked up
LOOKUP_WORKERS = 2


def _needs_song(track: Dict[str, Any]) -> bool:
    """A video with no album that isn't an upload, credited to an artist: what find_song can look up."""
    main = next(iter(track.get("artists") or []), None) or {}
    return bool(track.get("id") and not (track.get("album") or {}).get("id")
                and not N.is_upload(track) and main.get("id"))


def _video(track: Dict[str, Any]) -> Dict[str, Any]:
    """A track to look up, as look_up_songs takes it."""
    main = track["artists"][0]
    return {"id": track["id"], "title": track.get("title") or "", "artist_id": main["id"], "artist_name": main.get("name")}


def _known_songs(session: Session, video_ids: Iterable[str]) -> Dict[str, VideoSong]:
    """The VideoSongs still good: a song found, or none found recently."""
    ids = set(video_ids)
    if not ids:
        return {}
    stale_before = now_utc() - VIDEO_SONG_RETRY
    return {
        r.video_id: r
        for r in session.scalars(select(VideoSong).where(VideoSong.video_id.in_(ids)))
        if r.song_id or ensure_timezone_aware(r.checked_at) > stale_before
    }


def look_up_songs(session: Session, videos: List[Dict[str, Any]]) -> int:
    """
    Look up the songs of music videos ({id, title, artist_id, artist_name})
    not known yet (adapter.find_song), LOOKUP_WORKERS at a time, and keep
    what was found, or that nothing was. Nothing is held in the DB while
    YouTube Music answers: the results are written in one short transaction
    at the end. Returns how many searches failed (those are looked up again
    next time). Commits.
    """
    known = _known_songs(session, (v["id"] for v in videos))
    session.commit()  # no transaction open through the searches
    todo = list({v["id"]: v for v in videos if v["id"] not in known}.values())
    if not todo:
        return 0

    def look_up(video: Dict[str, Any]) -> Tuple[str, Optional[Dict[str, Any]], bool]:
        try:
            return video["id"], ytm_adapter.find_song(video["title"], video["artist_id"], video["artist_name"]), True
        except ytm_adapter.YTMusicUnavailable:
            logger.warning("Couldn't look up the song of video %s", video["id"], exc_info=True)
            return video["id"], None, False

    with ThreadPoolExecutor(max_workers=LOOKUP_WORKERS) as pool:
        results = list(pool.map(look_up, todo))

    failed = 0
    for video_id, song, answered in results:
        if not answered:
            failed += 1
            continue
        album = (song or {}).get("album") or {}
        values = {
            "song_id": song["id"] if song else None,
            "song_title": song["title"][:1024] if song else None,
            "album_id": album.get("id"),
            "album_title": (album.get("name") or "")[:255] or None,
            "checked_at": now_utc(),
        }
        # Upsert: a scan and a page's lookup can find the same video at once
        session.execute(
            sqlite_insert(VideoSong).values(video_id=video_id, **values)
            .on_conflict_do_update(index_elements=[VideoSong.video_id], set_=values)
        )
    session.commit()
    logger.info("Looked up the songs of %s music videos (%s failed)", len(todo), failed)
    return failed


def queue_song_lookup(session: Session, playlist_id: str, videos: List[Dict[str, Any]], *, origin: Origin) -> None:
    """
    Queue a find_video_songs job for a playlist's music videos, unless one
    is already waiting or running for it. Commits.
    """
    if pending_jobs(session, "find_video_songs", playlist_id=playlist_id):
        return
    enqueue_job(
        session, job_type="find_video_songs",
        payload={"playlist_id": playlist_id, "videos": videos},
        origin=origin, commit=True,
    )


def _stand_in_songs(session: Session, playlist_id: str) -> int:
    """
    Make the playlist's music videos their songs: the entries with a main
    artist and no album (uploads have no main artist), looked up first.
    A video found to be a song takes its id, title and album; its duration
    is the video's, so it's dropped (the M3U then takes the track's).
    Returns how many searches failed. Commits.
    """
    def videos_left() -> List[PlaylistEntry]:
        return session.scalars(
            select(PlaylistEntry).where(
                PlaylistEntry.playlist_id == playlist_id,
                PlaylistEntry.album_id.is_(None),
                PlaylistEntry.artist_id.is_not(None),
                PlaylistEntry.video_id.is_not(None),
            )
        ).all()

    videos = [
        {"id": e.video_id, "title": e.title, "artist_id": e.artist_id, "artist_name": e.artist_name}
        for e in videos_left()
    ]
    if not videos:
        return 0
    failed = look_up_songs(session, videos)
    rows = videos_left()
    known = _known_songs(session, (e.video_id for e in rows))
    for entry in rows:
        found = known.get(entry.video_id)
        if found is not None and found.song_id:
            entry.video_id = found.song_id
            entry.title = found.song_title or entry.title
            entry.album_id, entry.album_title = found.album_id, found.album_title
            entry.duration = None
    session.commit()
    return failed


def entries_from_playlist(tracks: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    fetch_playlist's tracks as entry fields, in playlist order. A music
    video found to be a song is that song (its id, title and album: what
    the library has of it). An upload has no main artist: what it credits
    is whoever uploaded it.
    """
    out = []
    for t in tracks:
        song = t.get("song") or {}
        title = (song.get("title") or t.get("title") or "").strip()
        if not title:
            continue
        main = next(iter(t.get("artists") or []), None) or {}
        album = t.get("album") or {}
        out.append({
            "video_id": song.get("id") or t.get("id") or None,
            "title": title[:1024],
            "artist_id": None if N.is_upload(t) else (main.get("id") or None),
            "artist_name": (main.get("name") or None) and main["name"][:255],
            "album_id": album.get("id") or None,
            "album_title": (album.get("name") or None) and album["name"][:255],
            # A video's length isn't its song's: the M3U takes the track's
            "duration": None if song else (t.get("duration_seconds") or None),
        })
    return out


def _store_entries(session: Session, playlist: Playlist, entries: List[Dict[str, Any]]) -> None:
    """Replace a playlist's entries, updating rows in place (their key is the position)."""
    existing = {
        e.position: e
        for e in session.execute(
            select(PlaylistEntry).where(PlaylistEntry.playlist_id == playlist.id)
        ).scalars()
    }
    for position, fields in enumerate(entries):
        row = existing.pop(position, None)
        if row is None:
            row = PlaylistEntry(playlist_id=playlist.id, position=position)
            session.add(row)
        for key, value in fields.items():
            setattr(row, key, value)
    for row in existing.values():
        session.delete(row)


def _entry_dicts(session: Session, playlist_id: str) -> List[Dict[str, Any]]:
    """A playlist's entries as plain dicts, safe to use across commits."""
    rows = session.execute(
        select(PlaylistEntry)
        .where(PlaylistEntry.playlist_id == playlist_id)
        .order_by(PlaylistEntry.position)
    ).scalars().all()
    return [
        {
            "position": e.position, "video_id": e.video_id, "title": e.title,
            "artist_id": e.artist_id, "artist_name": e.artist_name,
            "album_id": e.album_id, "album_title": e.album_title, "duration": e.duration,
        }
        for e in rows
    ]


# ============================================================================
# FINDING THE SONGS IN THE LIBRARY
# ============================================================================

def _norm(title: Optional[str]) -> str:
    return " ".join((title or "").casefold().split())


def resolve_entries(session: Session, entries: List[Dict[str, Any]]) -> List[Tuple[Dict[str, Any], Track]]:
    """
    The entries whose song is downloaded, with its track, in playlist order.

    A playlist's video id is often not the id of the album track downloaded
    for the song (YouTube Music has several for one song), so a song is
    found by, in order: the same id; the same title in its album; the same
    title by the same main artist anywhere in the library (the song is on a
    release other than the playlist's, e.g. a single).
    """
    if not entries:
        return []
    video_ids = {e["video_id"] for e in entries if e["video_id"]}
    album_ids = {e["album_id"] for e in entries if e["album_id"]}
    # Exact titles for the query (SQLite's lower() only folds ASCII); the
    # comparisons below ignore case and spacing
    titles = {e["title"] for e in entries}

    candidates = session.execute(
        select(Track).where(
            Track.status == "done",
            Track.file_path.is_not(None),
            or_(
                Track.id.in_(video_ids),
                Track.album_id.in_(album_ids),
                Track.title.in_(titles),
            ),
        )
    ).scalars().all()

    by_id: Dict[str, Track] = {}
    by_album_title: Dict[Tuple[str, str], Track] = {}
    by_title_artist: Dict[Tuple[str, str], Track] = {}
    for t in candidates:
        if not Path(t.file_path).exists():
            continue
        by_id[t.id] = t
        key = _norm(t.title)
        if t.album_id:
            by_album_title.setdefault((t.album_id, key), t)
        for a in t.artists or []:
            ident = (a or {}).get("id") or _norm((a or {}).get("name"))
            if ident:
                by_title_artist.setdefault((key, ident), t)

    resolved = []
    for e in entries:
        key = _norm(e["title"])
        track = (
            (by_id.get(e["video_id"]) if e["video_id"] else None)
            or (by_album_title.get((e["album_id"], key)) if e["album_id"] else None)
            or by_title_artist.get((key, e["artist_id"] or _norm(e["artist_name"])))
        )
        if track is not None:
            resolved.append((e, track))
    return resolved


# ============================================================================
# M3U
# ============================================================================

# Bytes kept free in an M3U file name: " (999).m3u8", and the temp file's
# leading "." and ".<pid>.tmp"
_M3U_NAME_RESERVE = len(" (999).m3u8") + len("..4194304.tmp")


def _pick_m3u_name(session: Session, title: str) -> str:
    """A file name of its own in m3u_dir: not another playlist's, not a file already there."""
    # safe_name drops characters (/, [ ]...) but leaves their spaces: "A / B" -> "A  B".
    # No leading dot: a hidden file, which library scans skip ("...Ready For It").
    # Cut to leave room in the filesystem's limit for " (n).m3u8" and the
    # temp file's ".<name>.<pid>.tmp"
    base = " ".join(safe_name(title).split()).lstrip(". ") if title else ""
    base = fit_name(base, _M3U_NAME_RESERVE) or "Playlist"
    taken = set(session.execute(select(Playlist.m3u_name).where(Playlist.m3u_name.is_not(None))).scalars())
    n = 1
    while True:
        name = f"{base}.m3u8" if n == 1 else f"{base} ({n}).m3u8"
        if name not in taken and not (m3u_dir() / name).exists():
            return name
        n += 1


def _m3u_text(resolved: List[Tuple[Dict[str, Any], Track]]) -> str:
    folder = m3u_dir()
    lines = ["#EXTM3U"]
    for entry, track in resolved:
        duration = entry["duration"] or track.duration or -1
        label = f"{entry['artist_name']} - {entry['title']}" if entry["artist_name"] else entry["title"]
        lines.append(f"#EXTINF:{duration},{' '.join(label.split())}")
        lines.append(Path(os.path.relpath(track.file_path, folder)).as_posix())
    return "\n".join(lines) + "\n"


def refresh_m3u(session: Session, playlist: Playlist) -> None:
    """
    Recount the playlist's songs in the library and, if it has an M3U,
    rewrite it (only when its content changed). No commit.
    """
    resolved = resolve_entries(session, _entry_dicts(session, playlist.id))
    playlist.available_count = len(resolved)
    if not playlist.m3u:
        return
    if not playlist.m3u_name:
        playlist.m3u_name = _pick_m3u_name(session, playlist.title)
    path = m3u_dir() / playlist.m3u_name
    text = _m3u_text(resolved)
    try:
        if path.exists() and path.read_text(encoding="utf-8") == text:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        # Per process: several download workers can refresh one playlist at once
        tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)  # atomic: a library scan never reads half a file
        logger.info("Wrote %s (%s songs)", path, len(resolved))
    except OSError:
        logger.exception("Failed writing M3U for playlist %s", playlist.id)


def _delete_m3u(playlist: Playlist) -> None:
    if not playlist.m3u_name:
        return
    try:
        (m3u_dir() / playlist.m3u_name).unlink(missing_ok=True)
        logger.info("Deleted M3U %s", playlist.m3u_name)
    except OSError:
        logger.exception("Failed deleting M3U %s", playlist.m3u_name)
    playlist.m3u_name = None


def refresh_for_track(session: Session, track: Track) -> None:
    """After a track is downloaded: refresh the playlists it may be a song of. Commits."""
    matches = [PlaylistEntry.video_id == track.id]
    if track.album_id:
        matches.append(PlaylistEntry.album_id == track.album_id)
    if track.title:
        matches.append(PlaylistEntry.title == track.title)
    # Only the playlists it can be a song of (resolve_entries): its own id,
    # or its title. Every other track of an album a playlist lists matches
    # the query too, and a big playlist's refresh isn't cheap
    key = _norm(track.title)
    playlist_ids = {
        playlist_id
        for playlist_id, video_id, title in session.execute(
            select(PlaylistEntry.playlist_id, PlaylistEntry.video_id, PlaylistEntry.title).where(or_(*matches))
        )
        if video_id == track.id or _norm(title) == key
    }
    for playlist_id in playlist_ids:
        playlist = session.get(Playlist, playlist_id)
        if playlist:
            refresh_m3u(session, playlist)
    if playlist_ids:
        session.commit()


def refresh_all(session: Session) -> None:
    """After files were deleted: every playlist's count and M3U. Commits."""
    for playlist in session.execute(select(Playlist)).scalars().all():
        refresh_m3u(session, playlist)
    session.commit()


# ============================================================================
# WHAT A PLAYLIST BRINGS IN
# ============================================================================

def _download_albums(session: Session, entries: List[Dict[str, Any]], origin: Origin, user_id: Optional[int]) -> Tuple[int, int]:
    """Start the download of each entry's album not downloaded yet. Returns (started, failed)."""
    started = failed = 0
    seen = set()
    for e in entries:
        album_id = e["album_id"]
        if not album_id or album_id in seen:
            continue
        seen.add(album_id)
        album = session.get(Album, album_id)
        if album is not None and album.mode == "download":
            continue
        try:
            if subs_svc.start_album_download(session, album_id, origin=origin, user_id=user_id)["started"]:
                started += 1
        except Exception:
            # Mostly YouTube Music not answering: still not downloaded, so
            # the retry (or next scan) picks it up again
            logger.exception("Failed to start the download of album %s", album_id)
            session.rollback()
            failed += 1
    return started, failed


def _follow_artists(session: Session, entries: List[Dict[str, Any]], origin: Origin, user_id: Optional[int]) -> int:
    """
    Follow (full) each entry's main artist not followed yet, then sync it,
    which downloads every release -- like the Follow button. No network
    here: the sync fetches the artist. Returns how many were followed.
    """
    followed = 0
    seen = set()
    for e in entries:
        artist_id = e["artist_id"]
        if not artist_id or artist_id in seen:
            continue
        seen.add(artist_id)
        if subs_svc.follow_artist(session, artist_id, e["artist_name"], user_id=user_id, origin=origin):
            followed += 1
        session.commit()  # one short transaction per artist (single SQLite writer)
    return followed


# ============================================================================
# SYNC (the sync_playlist job)
# ============================================================================

def run_sync(session: Session, playlist_id: str, *, fetch: bool, origin: Origin) -> Dict[str, Any]:
    """
    Scan a playlist: fetch its songs again (followed playlists, when `fetch`),
    bring in what they belong to, refresh its M3U. Bringing in is
    idempotent -- what's already downloaded or followed is skipped -- so
    every scan goes over every song. Returns the job result.
    """
    playlist = session.get(Playlist, playlist_id)
    if playlist is None:
        return {"ok": True, "skipped": True, "reason": "playlist removed"}

    if fetch and playlist.followed:
        try:
            data = fetch_playlist(session, playlist_id)
        except ytm_adapter.YTMusicUnavailable as e:
            # Recorded as a sync, like artists: a playlist that stays
            # unreadable is retried by the job, then waits for its next turn
            playlist.last_error = str(e)[:1000]
            playlist.last_synced_at = now_utc()
            session.commit()
            return {"ok": False, "error": str(e), "retry_delay_seconds": RETRY_DELAY_SECONDS}
        playlist.title = (data.get("title") or playlist.title)[:255]
        playlist.author = data.get("author")
        playlist.thumbnail = data.get("thumbnail")
        _store_entries(session, playlist, entries_from_playlist(data.get("tracks") or []))
        session.commit()

    # Music videos not looked up yet (new ones, or added with the playlist):
    # their songs, and so their albums, before anything is brought in
    songs_failed = _stand_in_songs(session, playlist_id)
    # Read again from the DB, not the session's copy (kept across commits):
    # removed, switched off or renamed by a request meanwhile
    playlist = session.get(Playlist, playlist_id, populate_existing=True)
    if playlist is None:  # removed meanwhile
        return {"ok": True, "skipped": True, "reason": "playlist removed"}

    entries = _entry_dicts(session, playlist_id)
    user_id = playlist.created_by
    albums_started = albums_failed = artists_followed = 0
    if playlist.mode == "artists":
        artists_followed = _follow_artists(session, entries, origin, user_id)
    else:
        albums_started, albums_failed = _download_albums(session, entries, origin, user_id)

    # Again: the brought-in part can take minutes, and a download may have
    # named its M3U meanwhile (refresh_for_track)
    playlist = session.get(Playlist, playlist_id, populate_existing=True)
    if playlist is None:  # removed meanwhile
        return {"ok": True, "skipped": True, "reason": "playlist removed"}
    refresh_m3u(session, playlist)
    playlist.last_synced_at = now_utc()
    problems = [
        f"{albums_failed} album(s) couldn't be read from YouTube Music" if albums_failed else None,
        f"the songs of {songs_failed} music video(s) couldn't be looked up" if songs_failed else None,
    ]
    playlist.last_error = "; ".join(p for p in problems if p) or None
    session.commit()

    result = {
        "ok": not (albums_failed or songs_failed),
        "entries": len(entries),
        "albums_started": albums_started,
        "artists_followed": artists_followed,
        "available": playlist.available_count,
    }
    if albums_failed or songs_failed:
        # What's done is skipped next time: the retry only does the rest
        result.update(error=playlist.last_error, retry_delay_seconds=RETRY_DELAY_SECONDS)
    logger.info("Synced playlist %s (%s): %s", playlist_id, playlist.mode, result)
    return result


def pending_syncs(session: Session, playlist_id: Optional[str] = None) -> List[Job]:
    """The sync_playlist jobs waiting or running: of one playlist, or of all of them."""
    if playlist_id is None:
        return pending_jobs(session, "sync_playlist")
    return pending_jobs(session, "sync_playlist", playlist_id=playlist_id)


def _syncing_ids(session: Session) -> set:
    """Playlists with a scan waiting or running."""
    return {job.payload.get("playlist_id") for job in pending_syncs(session)}


def queue_sync(session: Session, playlist: Playlist, *, origin: Origin, fetch: bool = True) -> None:
    """
    Queue a sync_playlist job, or reuse (and promote) the one already
    waiting. One already running doesn't count: what changed since it
    started (a mode switch) needs a scan of its own. No commit.
    """
    waiting = [j for j in pending_syncs(session, playlist.id) if j.status == "queued"]
    if waiting:
        job = waiting[0]
        promote(job, origin)
        if fetch and not (job.payload or {}).get("fetch"):
            job.payload = {**job.payload, "fetch": True}
        return
    enqueue_job(
        session, job_type="sync_playlist",
        payload={"playlist_id": playlist.id, "fetch": fetch},
        origin=origin, user_id=playlist.created_by, commit=False,
    )


# ============================================================================
# ADD / CHANGE / REMOVE
# ============================================================================

def add_playlist(
    session: Session,
    playlist_id: str,
    *,
    mode: str,
    followed: bool,
    m3u: bool,
    user_id: Optional[int],
) -> Playlist:
    """
    Add a playlist: its songs are read now (raises YTMusicUnavailable when
    they can't be), its M3U written with what's already in the library, and
    a BULK sync queued to bring in the rest. Commits.
    """
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    if not followed and not m3u:
        raise ValueError("a playlist added once needs an M3U file (or use the one-time buttons)")
    if session.get(Playlist, playlist_id) is not None:
        raise PlaylistAlreadyAdded(playlist_id)

    data = fetch_playlist(session, playlist_id)
    playlist = Playlist(
        id=playlist_id,
        title=(data.get("title") or playlist_id)[:255],
        author=data.get("author"),
        thumbnail=data.get("thumbnail"),
        mode=mode, followed=followed, m3u=m3u,
        created_by=user_id,
    )
    session.add(playlist)
    session.flush()
    _store_entries(session, playlist, entries_from_playlist(data.get("tracks") or []))
    session.flush()
    refresh_m3u(session, playlist)
    queue_sync(session, playlist, origin=Origin.BULK, fetch=False)
    session.commit()
    logger.info("Added playlist %s (%s, followed=%s, m3u=%s)", playlist_id, mode, followed, m3u)
    return playlist


def update_playlist(
    session: Session,
    playlist: Playlist,
    *,
    mode: Optional[str] = None,
    followed: Optional[bool] = None,
    m3u: Optional[bool] = None,
) -> Playlist:
    """
    Change a playlist's options. Commits.

    - albums -> artists: the whole playlist is rescanned and every main
      artist followed (BULK).
    - artists -> albums: the artists followed stay followed; from now on
      songs bring in their albums.
    - Followed again: rescanned now (BULK). Unfollowed: no more scans, the
      M3U stays as last written (still filled in as downloads land).
    - M3U on: written now. Off: the file is deleted.
    """
    new_mode = playlist.mode if mode is None else mode
    new_followed = playlist.followed if followed is None else followed
    new_m3u = playlist.m3u if m3u is None else m3u
    if new_mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    if not new_followed and not new_m3u:
        raise ValueError("a playlist that's neither followed nor written as an M3U does nothing: remove it instead")

    rescan = (new_mode == "artists" and playlist.mode != "artists") or (new_followed and not playlist.followed)
    playlist.mode, playlist.followed = new_mode, new_followed
    if new_m3u != playlist.m3u:
        playlist.m3u = new_m3u
        if not new_m3u:
            _delete_m3u(playlist)
        refresh_m3u(session, playlist)
    if rescan:
        queue_sync(session, playlist, origin=Origin.BULK, fetch=True)
    session.commit()
    return playlist


def remove_playlist(session: Session, playlist: Playlist) -> None:
    """Remove a playlist and its M3U. The music stays. Commits."""
    _delete_m3u(playlist)
    session.delete(playlist)
    session.commit()


# ============================================================================
# DELETIONS
# ============================================================================

def playlists_bringing_back(
    session: Session,
    *,
    album_ids: Iterable[str] = (),
    artist_ids: Iterable[str] = (),
) -> List[Playlist]:
    """
    The followed playlists whose next scan would bring back what's being
    deleted from the library: in albums mode, one listing a song of these
    albums; in artists mode, one listing a song by these artists.
    """
    album_ids = {a for a in album_ids if a}
    artist_ids = {a for a in artist_ids if a}
    if not album_ids and not artist_ids:
        return []
    matches = []
    if album_ids:
        matches.append((Playlist.mode == "albums") & PlaylistEntry.album_id.in_(album_ids))
    if artist_ids:
        matches.append((Playlist.mode == "artists") & PlaylistEntry.artist_id.in_(artist_ids))
    return list(session.execute(
        select(Playlist)
        .join(PlaylistEntry, PlaylistEntry.playlist_id == Playlist.id)
        .where(Playlist.followed.is_(True), or_(*matches))
        .distinct()
        .order_by(func.lower(Playlist.title))
    ).scalars())


def unfollow_for_deletion(session: Session, playlists: Iterable[Playlist]) -> List[str]:
    """
    Unfollow playlists that would bring a deleted album or artist back: they
    become one-time playlists (their M3U stays). Returns their titles. No commit.
    """
    titles = []
    for playlist in playlists:
        playlist.followed = False
        titles.append(playlist.title)
        logger.info("Unfollowed playlist %s: it would bring back what was deleted", playlist.id)
    return titles


# ============================================================================
# LISTING
# ============================================================================

def summary(session: Session, playlist: Playlist, syncing: Optional[set] = None) -> Dict[str, Any]:
    """The playlist as the API lists it. `syncing`: _syncing_ids(), when summarizing several."""
    entries = session.execute(
        select(PlaylistEntry.album_id, PlaylistEntry.artist_id).where(PlaylistEntry.playlist_id == playlist.id)
    ).all()
    # Songs that bring nothing in for this mode: in albums mode no album
    # (uploads, music videos whose song wasn't found), in artists mode no
    # main artist (uploads: see entries_from_playlist); a music video with no
    # album still brings its artist in (_follow_artists)
    skipped = sum(
        1 for album_id, artist_id in entries
        if not (artist_id if playlist.mode == "artists" else album_id)
    )
    syncing = playlist.id in (syncing if syncing is not None else _syncing_ids(session))
    return {
        "id": playlist.id,
        "title": playlist.title,
        "author": playlist.author,
        "thumbnail": playlist.thumbnail,
        "mode": playlist.mode,
        "followed": playlist.followed,
        "m3u": playlist.m3u,
        "m3u_file": f"{M3U_DIR_NAME}/{playlist.m3u_name}" if playlist.m3u and playlist.m3u_name else None,
        "songs": len(entries),
        "skipped": skipped,
        "available": playlist.available_count,
        "syncing": syncing,
        "last_synced_at": playlist.last_synced_at.isoformat() if playlist.last_synced_at else None,
        "last_error": playlist.last_error,
        "created_at": playlist.created_at.isoformat() if playlist.created_at else None,
    }


def list_playlists(session: Session) -> List[Dict[str, Any]]:
    rows = session.execute(select(Playlist).order_by(func.lower(Playlist.title))).scalars().all()
    syncing = _syncing_ids(session)
    return [summary(session, p, syncing) for p in rows]


def followed_needing_sync(session: Session, cutoff: datetime) -> List[Playlist]:
    """
    Followed playlists not scanned since `cutoff` (or never), and with no
    scan already waiting or running: the scheduler looks every minute.
    """
    due = session.execute(
        select(Playlist).where(
            Playlist.followed.is_(True),
            or_(Playlist.last_synced_at.is_(None), Playlist.last_synced_at < cutoff),
        )
    ).scalars().all()
    syncing = _syncing_ids(session)
    return [p for p in due if p.id not in syncing]
