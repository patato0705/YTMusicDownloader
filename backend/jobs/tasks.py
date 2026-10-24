# backend/jobs/tasks.py
"""
Job task handlers called by the worker.

Each task function:
- Takes (session: Session, **payload) as arguments
- Returns dict with {"ok": bool, "error": str (optional), ...}, plus
  "retry_delay_seconds" when a failure is worth another attempt later
- Commits in short transactions, never held across a network call: SQLite
  has a single writer, shared with every other worker

Task types:
- download_track: Download a single track using yt-dlp
- download_lyrics: Download synced lyrics from LRCLIB
- import_album: Fetch an album's tracklist from YTMusic, then queue its downloads
- sync_artist: Check artist for new releases
- sync_chart: Follow a chart's top artists
- sync_playlist: Scan a playlist added to the library
- fetch_genres: Look up an artist's and its albums' genres (MusicBrainz, Deezer)
"""
from __future__ import annotations
import contextlib
import fcntl
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlencode

import requests
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import config, settings as settings_module
from ..config import YDL_COOKIEFILE, YDL_USER_COOKIEFILE
from ..downloader import embed as embed_mod, nfo as nfo_mod
from ..downloader.core import download_track_by_videoid
from ..models import Job, Track, Album, Artist
from ..services import albums as albums_svc
from ..services import artists as artists_svc
from ..services import charts as charts_svc
from ..services import folders as folders_svc
from ..services import genres as genres_svc
from ..services import playlists as playlists_svc
from ..services import subscriptions as subs_svc
from ..services import tracks as tracks_svc
from ..text_utils import fold
from ..time_utils import now_utc
from ..ytm_service.adapter import YTMusicUnavailable
from . import gate
from .jobqueue import enqueue_job
from .priorities import Origin

logger = logging.getLogger("jobs.tasks")


# ============================================================================
# YOUTUBE COOKIES AND ERRORS
# ============================================================================

def _youtube_cookiefile() -> Path:
    """
    The yt-dlp cookie jar this worker process uses.

    yt-dlp both reads the jar and writes it back on exit, and these cookies
    are an anonymous session yt-dlp creates by itself (nobody logs in). So
    each download worker gets its own file, named after WORKER_NAME
    (deploy/supervisord.conf): with a shared file, worker A resetting its
    rate-limited session would race worker B rewriting the stale one back
    a moment later. A process without WORKER_NAME (dev shell) keeps the
    plain config.YDL_COOKIEFILE.
    """
    worker = os.environ.get("WORKER_NAME", "").strip()
    if not worker:
        return YDL_COOKIEFILE
    safe = "".join(c for c in worker if c.isalnum() or c in "-_") or "worker"
    return YDL_COOKIEFILE.with_name(f"{YDL_COOKIEFILE.stem}-{safe}{YDL_COOKIEFILE.suffix}")


# Substrings (lower-cased, straight apostrophes) of the yt-dlp errors that
# mean "YouTube is throttling this IP/session", as opposed to a problem with
# the one video. Keep this list current: when YouTube changes the wording,
# the symptom is dozens of identical failures in a row with no "Paused all
# downloads" line between them.
_YOUTUBE_THROTTLE_MARKERS = (
    "rate-limited by youtube",
    "current session has been rate-limited",
    "sign in to confirm you're not a bot",   # IP-level bot check, the usual one since 2024
    "confirm you're not a bot",
    "http error 429",
    "too many requests",
    # "unable to download video data: HTTP Error 403: Forbidden": the
    # googlevideo CDN refusing this IP/session outright, which is what too
    # many concurrent downloads get before (or instead of) the bot check.
    # A stale yt-dlp signature gives the same 403 -- also global, not
    # per-video, so pausing is right either way.
    "http error 403",
)

# yt-dlp errors that mean "this video needs a signed-in, age-verified
# account" -- the one case the user's own cookie jar is used for.
_YOUTUBE_AGE_GATE_MARKERS = (
    "sign in to confirm your age",
    "age-restricted",
    "age restricted",
    "inappropriate for some users",
)


def _error_text(error: Any) -> str:
    # yt-dlp quotes YouTube's message verbatim, curly apostrophe included
    return str(error or "").lower().replace("’", "'")


def _is_youtube_rate_limit_error(error: Any) -> bool:
    """
    Whether a yt-dlp error means YouTube is throttling us (rate limit or
    bot check) rather than something wrong with this particular video.
    """
    text = _error_text(error)
    if any(marker in text for marker in _YOUTUBE_THROTTLE_MARKERS):
        return True
    return "this content isn't available" in text and "try again later" in text


def _is_youtube_age_gate_error(error: Any) -> bool:
    text = _error_text(error)
    return any(marker in text for marker in _YOUTUBE_AGE_GATE_MARKERS)


def _user_cookiefile_available() -> bool:
    try:
        return YDL_USER_COOKIEFILE.is_file() and YDL_USER_COOKIEFILE.stat().st_size > 0
    except OSError:
        return False


@contextlib.contextmanager
def _user_cookie_lock():
    """
    Serialise use of the account cookie jar across worker processes.

    yt-dlp writes the jar back on exit (Google rotates session cookies, so
    that write-back is what keeps an uploaded jar valid over time), and two
    workers doing so at once would corrupt it. Age-gated tracks are rare,
    so waiting on the lock costs nothing in practice.
    """
    with open(YDL_USER_COOKIEFILE.with_suffix(".lock"), "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _reset_youtube_cookies() -> bool:
    """
    Delete this worker's YouTube cookies file to reset the rate-limited
    session; yt-dlp starts a fresh anonymous one and writes a new file on
    the next download. Returns whether there was one to delete.
    """
    cookiefile = _youtube_cookiefile()
    try:
        cookiefile.unlink()
    except FileNotFoundError:
        logger.warning("YouTube cookies file not found at %s", cookiefile)
        return False
    except OSError:
        logger.exception("Failed to delete YouTube cookies at %s", cookiefile)
        return False
    logger.info("Deleted YouTube cookies at %s to reset rate limit", cookiefile)
    return True


# ============================================================================
# TASK: DOWNLOAD TRACK
# ============================================================================

def _download_with_fallbacks(track_id: str, **metadata: Any) -> Tuple[str, Optional[str]]:
    """
    downloader.core.download_track_by_videoid with two fallbacks, each tried
    at most once:
      - YouTube throttles us -> reset this worker's anonymous cookie jar
        (fresh session) and retry;
      - the video is age-gated -> retry with the account cookies the admin
        uploaded, if any. That jar is used for nothing else: not for
        ordinary downloads, and NOT to get past a rate limit, so the
        account only ever sees a handful of requests.
    """
    cookiefile = _youtube_cookiefile()
    cookies_reset = False
    user_jar_tried = False

    while True:
        lock = _user_cookie_lock() if cookiefile == YDL_USER_COOKIEFILE else contextlib.nullcontext()
        try:
            with lock:
                return download_track_by_videoid(video_id=track_id, cookiefile=cookiefile, **metadata)
        except Exception as error:
            if _is_youtube_age_gate_error(error):
                if not user_jar_tried and _user_cookiefile_available():
                    user_jar_tried = True
                    cookiefile = YDL_USER_COOKIEFILE
                    logger.info("Track %s is age-restricted; retrying with the account cookies", track_id)
                    continue
                if not user_jar_tried:
                    logger.warning(
                        "Track %s is age-restricted and no account cookies are uploaded "
                        "(admin panel > Settings > Downloads)", track_id,
                    )
                raise

            if _is_youtube_rate_limit_error(error) and cookiefile != YDL_USER_COOKIEFILE:
                logger.warning("YouTube rate limit detected for track %s", track_id)
                if not cookies_reset and _reset_youtube_cookies():
                    cookies_reset = True
                    logger.info("Retrying download for track %s after cookie reset", track_id)
                    time.sleep(2)
                    continue
                logger.error("YouTube rate limit persists for track %s", track_id)
            raise


def download_track(session: Session, track_id: str, *, origin: str) -> Dict[str, Any]:
    """
    Download a track with yt-dlp into its album's folder, tagged
    (see _download_track). Any error, not only the download's own, ends as
    a failed attempt with a retry later rather than a job failed for good.
    """
    try:
        return _download_track(session, track_id, origin=origin)
    except Exception as error:
        return _download_failed(session, track_id, error)


def _download_track(session: Session, track_id: str, *, origin: str) -> Dict[str, Any]:
    """
    Download a track with yt-dlp into its album's folder, tagged.

    Flow:
    1. Skip a track already on disk (an admin requeue, a duplicate job)
    2. Mark it "downloading" and roll that up to its album, naming the
       album's folder if none of its files was written yet
       (services/folders.py), COMMIT
    3. Download, outside any transaction (see _download_with_fallbacks)
    4. Mark it "done" with its file, COMMIT; the first track of an album
       also moves the cover into the album folder
    5. Catch up on genres found meanwhile, refresh the playlists listing
       it, queue its lyrics

    A failure keeps the reason on the track; the worker's next step
    (jobqueue.mark_job_failed) settles its status: "queued" for a retry,
    "failed" once out of attempts.
    """
    track = session.get(Track, track_id)
    if not track:
        return {"ok": False, "error": f"Track {track_id} not found in database"}

    if track.status == "done" and track.file_path and Path(track.file_path).exists():
        logger.info("Track %s is already on disk, skipping download", track_id)
        return {"ok": True, "file_path": track.file_path, "skipped": True}

    album = track.album
    artist = album.artist if album else None
    album_id = album.id if album else None
    genres = list(album.genres or []) if album else []
    # The album's first file names its folder, committed below with the status
    dest_dir = folders_svc.album_dir(session, album) if album else config.MUSIC_DIR / "Unknown" / "Unknown Album"
    metadata = {
        "dest_dir": dest_dir,
        "artist_name": artist.name if artist else None,
        "album_name": album.title if album else None,
        "track_title": track.title,
        "track_number": track.track_number,
        "year": album.year if album else None,
        "cover_path": album.image_local if album else None,
        "genres": genres,
    }

    track.status = "downloading"
    track.last_error = None
    if album_id:
        # Rolled up now, not just when the track finishes: otherwise an album
        # in progress reports "pending". Flushed first: the session is
        # autoflush=False, so the rollup would still count it as "queued".
        session.flush()
        subs_svc.check_and_update_album_download_status(session, album_id)
    session.commit()

    logger.info("Downloading track %s: %s", track_id, track.title)
    file_path, moved_cover = _download_with_fallbacks(track_id, **metadata)

    # Read again from the DB (the session keeps objects across commits): the
    # album may have been deleted from the library during the download
    session.expire_all()
    track = session.get(Track, track_id)
    if track is None:
        logger.info("Track %s was removed during its download, deleting %s", track_id, file_path)
        Path(file_path).unlink(missing_ok=True)
        return {"ok": True, "skipped": "track removed during the download"}
    track.status = "done"
    track.last_error = None
    track.file_path = file_path
    try:
        track.file_size = Path(file_path).stat().st_size
    except OSError:
        logger.warning("Could not stat downloaded file for track %s: %s", track_id, file_path)
        track.file_size = None
    album = session.get(Album, album_id) if album_id else None
    if album:
        if moved_cover:
            album.image_local = moved_cover
        session.flush()
        subs_svc.check_and_update_album_download_status(session, album_id)
    session.commit()
    logger.info("Downloaded track %s to %s", track_id, file_path)

    if album and moved_cover:
        # album.nfo was written while the cover was still in COVERS_DIR
        nfo_mod.write_album_nfo(album, album.artist, dest_dir)

    # Genres found while this track was downloading: the genre lookup only
    # re-tags tracks that were already done, so this one catches up. Read
    # from the DB, not the session (expire_on_commit=False).
    if album_id:
        try:
            current = session.execute(select(Album.genres).where(Album.id == album_id)).scalar() or []
            if list(current) != genres:
                embed_mod.set_genres(file_path, list(current))
        except Exception:
            logger.exception("Failed to re-tag genres of track %s", track_id)

    # Playlists listing this song: their M3U gains it
    try:
        playlists_svc.refresh_for_track(session, track)
    except Exception:
        logger.exception("Failed to refresh playlists for track %s", track_id)
        session.rollback()

    # A success means YouTube is talking to us again: reset the pause
    # escalation so the next throttle starts from the base duration.
    try:
        gate.note_download_succeeded(session)
    except Exception:
        logger.debug("Failed to reset pause streak", exc_info=True)
        session.rollback()

    if settings_module.feature_enabled(session, "lyrics"):
        try:
            enqueue_job(session, job_type="download_lyrics", payload={"track_id": track_id}, origin=Origin(origin))
        except Exception:
            logger.exception("Failed to queue lyrics job for track %s", track_id)
            session.rollback()

    return {"ok": True, "file_path": file_path}


def _download_failed(session: Session, track_id: str, error: Exception) -> Dict[str, Any]:
    """The task result for a failed download, with the reason recorded on the track."""
    session.rollback()
    throttled = _is_youtube_rate_limit_error(error)
    if throttled:
        logger.warning("Download of track %s hit YouTube's rate limit; requeued", track_id)
    else:
        logger.error("Download failed for track %s", track_id, exc_info=error)

    track = session.get(Track, track_id)
    if track:
        track.last_error = tracks_svc.truncate_error(error)
        session.commit()

    if _is_youtube_age_gate_error(error):
        # Nothing will change until someone uploads account cookies (or the
        # uploaded ones are from an account that isn't age-verified), so
        # don't burn attempts every five minutes.
        hint = (
            "age-restricted even with the uploaded account cookies (is that account age-verified?)"
            if _user_cookiefile_available()
            else "age-restricted; upload cookies from a signed-in YouTube account in the admin panel"
        )
        return {"ok": False, "error": f"Download failed: {hint} -- {error}", "retry_delay_seconds": 86400}

    if throttled:
        # Still limited after a fresh session: it's the IP, not the cookies.
        # Stop every download worker for a while rather than letting the
        # others keep hammering (jobs.gate).
        try:
            gate.pause_downloads(session, reason=f"track {track_id}: {tracks_svc.truncate_error(error)}")
        except Exception:
            logger.exception("Failed to pause downloads after rate limit")
            session.rollback()
        return {
            "ok": False,
            "error": f"Download failed: {error}",
            "retry_delay_seconds": 600,
            # A rate limit says nothing about the track: a long block
            # mustn't burn through its attempts and fail it for good.
            "refund_attempt": True,
        }

    return {"ok": False, "error": f"Download failed: {error}", "retry_delay_seconds": 300}


# ============================================================================
# TASK: DOWNLOAD LYRICS
# ============================================================================

_LRCLIB_HEADERS = {"User-Agent": f"YTMusicDownloader v{config.APP_VERSION} (https://github.com/patato0705/YTMusicDownloader)"}

# YTMusic and LRCLIB (mostly Spotify-sourced) durations routinely disagree by
# a second; anything beyond this is treated as a different version/edit.
LRCLIB_DURATION_TOLERANCE = 2


class LrclibUnavailable(Exception):
    """LRCLIB answered with a rate-limit/5xx or didn't answer at all."""


def _lrclib_get(endpoint: str, params: Dict[str, Any], timeout: int) -> Optional[Any]:
    """
    GET an LRCLIB endpoint. Returns the parsed JSON, None on 404, and raises
    LrclibUnavailable for anything transient (429/5xx/network) so callers
    retry soon instead of recording a misleading "not found".
    """
    try:
        response = requests.get(
            f"https://lrclib.net/api/{endpoint}?{urlencode(params)}", timeout=timeout, headers=_LRCLIB_HEADERS
        )
    except requests.RequestException as e:
        raise LrclibUnavailable(str(e)) from e
    if response.status_code == 200:
        return response.json()
    if response.status_code == 404:
        return None
    raise LrclibUnavailable(f"HTTP {response.status_code}")


def _pick_search_candidate(
    results: Any,
    track_name: str,
    artist_name: str,
    album_name: str,
    duration: int,
) -> Optional[Dict[str, Any]]:
    """
    Choose the best synced record from /api/search results.

    /api/get returns a single record for the exact signature and happily
    returns a plain-only one even when a synced upload of the same song
    exists under "Foo - Single" or with a duration 1s off. So we look
    through the search results ourselves: same title, same (or containing)
    artist, duration within LRCLIB_DURATION_TOLERANCE, not instrumental.
    Ties go to an exact album match, then the closest duration, then the
    oldest (lowest id) upload.
    """
    if not isinstance(results, list):
        return None
    want_title = fold(track_name)
    want_artist = fold(artist_name)
    want_album = fold(album_name)

    ranked = []
    for c in results:
        if not isinstance(c, dict) or not c.get("syncedLyrics") or c.get("instrumental"):
            continue
        if fold(c.get("trackName")) != want_title:
            continue
        cand_artist = fold(c.get("artistName"))
        if not (cand_artist == want_artist or want_artist in cand_artist or cand_artist in want_artist):
            continue
        try:
            delta = abs(float(c.get("duration") or 0) - float(duration))
        except (TypeError, ValueError):
            continue
        if duration and delta > LRCLIB_DURATION_TOLERANCE:
            continue
        album_rank = 0 if fold(c.get("albumName")) == want_album else 1
        ranked.append((album_rank, delta, int(c.get("id") or 0), c))

    if not ranked:
        return None
    ranked.sort(key=lambda r: r[:3])
    return ranked[0][3]


def _lrclib_lookup(
    track_name: str,
    artist_name: str,
    album_name: str,
    duration: int,
) -> Dict[str, Any]:
    """
    Find lyrics on LRCLIB for a track.

    Order: /api/get-cached (cheap) -> /api/get -> /api/search fallback (only
    when no synced lyrics yet). Returns {"synced": str|None, "plain":
    str|None, "found": bool, "source": str}. Raises LrclibUnavailable when
    LRCLIB is down/rate-limiting.
    """
    params = {
        "track_name": track_name,
        "artist_name": artist_name,
        "album_name": album_name,
        "duration": duration,
    }
    synced = None
    plain = None
    found = False
    source = ""

    # get-cached is best-effort; a hiccup there just means we ask /api/get
    try:
        data = _lrclib_get("get-cached", params, timeout=10)
    except LrclibUnavailable as e:
        logger.debug("LRCLIB get-cached unavailable: %s", e)
        data = None
    if data:
        found = True
        source = "get-cached"
        synced = data.get("syncedLyrics")
        plain = data.get("plainLyrics")

    if not synced:
        data = _lrclib_get("get", params, timeout=15)
        if data:
            found = True
            source = "get"
            synced = data.get("syncedLyrics")
            plain = data.get("plainLyrics") or plain

    if not synced:
        results = _lrclib_get("search", {"track_name": track_name, "artist_name": artist_name}, timeout=15)
        best = _pick_search_candidate(results, track_name, artist_name, album_name, duration)
        if best:
            found = True
            source = f"search#{best.get('id')}"
            synced = best.get("syncedLyrics")
            plain = best.get("plainLyrics") or plain
            logger.info(
                "LRCLIB search matched %s - %s: album=%r duration=%s (ours=%s)",
                artist_name, track_name, best.get("albumName"), best.get("duration"), duration,
            )

    return {"synced": synced, "plain": plain, "found": found, "source": source}


def download_lyrics(
    session: Session,
    track_id: str,
    mode: str = "normal",
    *,
    origin: str,  # sets this job's priority; queues nothing itself
) -> Dict[str, Any]:
    """
    Download lyrics for a track from LRCLIB into a .lrc file next to it
    (see _download_lyrics). An unexpected error is retried in an hour.
    """
    try:
        return _download_lyrics(session, track_id, mode)
    except Exception as e:
        session.rollback()
        logger.exception("download_lyrics failed for %s", track_id)
        return {"ok": False, "error": str(e), "retry_delay_seconds": 3600}


def _download_lyrics(session: Session, track_id: str, mode: str) -> Dict[str, Any]:
    """
    Modes:
    - "normal": Download lyrics, prefer synced, fall back to plain if allowed
    - "upgrade": Only replace existing lyrics if synced are found
    """
    # Jobs queued before the feature was switched off: drop them quietly.
    # The scheduler's retry sweep picks the track up again once re-enabled.
    if not settings_module.feature_enabled(session, "lyrics"):
        return {"ok": True, "message": "Lyrics feature disabled, skipped"}

    track = session.get(Track, track_id)
    if not track:
        return {"ok": False, "error": f"Track {track_id} not found in database"}
    if mode == "upgrade" and track.lyrics == "synced":
        return {"ok": True, "message": "Already has synced lyrics"}
    if not track.file_path:
        return {"ok": False, "error": "Track has no audio file yet"}
    audio_path = Path(track.file_path)
    if not audio_path.exists():
        return {"ok": False, "error": f"Audio file not found: {track.file_path}"}

    track_name = track.title or ""
    artist_name = (track.artists[0].get("name") or "") if track.artists else ""
    album_name = track.album.title if track.album else ""
    duration = track.duration or 0
    if not track_name or not artist_name:
        return {"ok": False, "error": "Missing track name or artist name"}

    logger.info("Fetching lyrics for: %s - %s (mode=%s)", artist_name, track_name, mode)
    try:
        found = _lrclib_lookup(track_name, artist_name, album_name, duration)
    except LrclibUnavailable as e:
        logger.warning("LRCLIB unavailable for track %s: %s", track_id, e)
        return {"ok": False, "error": f"LRCLIB unavailable: {e}", "retry_delay_seconds": 3600}

    if not found["found"]:
        logger.info("No lyrics found for track %s", track_id)
        return {"ok": False, "error": "Lyrics not found", "retry_delay_seconds": 86400}

    if found["synced"]:
        logger.info("Found synced lyrics for track %s via %s", track_id, found["source"])
        lyrics_to_save, lyrics_kind = found["synced"], "synced"
    elif mode == "upgrade":
        return {"ok": True, "message": "No synced lyrics available yet, keeping plain"}
    elif settings_module.get_setting(session, "features.synced_lyrics_only") or not found["plain"]:
        logger.info("Only plain lyrics available for track %s, will retry later", track_id)
        return {
            "ok": False,
            "error": "Only plain lyrics available (synced lyrics required)",
            "retry_delay_seconds": 86400,
        }
    else:
        lyrics_to_save, lyrics_kind = found["plain"], "plain"

    lrc_path = audio_path.with_suffix(".lrc")
    try:
        lrc_path.write_text(lyrics_to_save, encoding="utf-8")
    except OSError as e:
        logger.exception("Failed to save lyrics file %s", lrc_path)
        return {"ok": False, "error": f"Failed to save lyrics: {e}", "retry_delay_seconds": 300}

    track.lyrics = lyrics_kind
    track.lyrics_local = str(lrc_path)
    session.commit()
    logger.info("Saved %s lyrics for track %s to %s", lyrics_kind, track_id, lrc_path)
    return {"ok": True, "lyrics_path": str(lrc_path), "lyrics_type": lyrics_kind}


# ============================================================================
# TASK: IMPORT ALBUM
# ============================================================================

def import_album(
    session: Session,
    browse_id: str,
    artist_id: Optional[str] = None,
    *,
    origin: str,
) -> Dict[str, Any]:
    """
    Fetch a download-mode album's tracklist from YTMusic and store it, then
    write its album.nfo and queue the download of every track not on disk
    (albums_svc.complete_import).
    """
    album = session.get(Album, browse_id)
    # Unfollowed (or deleted) since it was queued
    if album is None or album.mode != "download":
        return {"ok": True, "skipped": "album not in download mode"}

    try:
        result = albums_svc.fetch_and_upsert_album(session, browse_id=browse_id, artist_id=artist_id)
        session.commit()
        queued = albums_svc.complete_import(session, result["album_id"], origin=Origin(origin))
    except Exception as e:
        session.rollback()
        logger.exception("import_album failed for %s", browse_id)
        return {"ok": False, "error": str(e), "retry_delay_seconds": 120}

    logger.info(
        "Imported album %s: %s new tracks, %s updated, %s downloads queued",
        browse_id, result["inserted_tracks"], result["updated_tracks"], queued,
    )
    return {
        "ok": True,
        "album_id": result["album_id"],
        "tracks_inserted": result["inserted_tracks"],
        "tracks_updated": result["updated_tracks"],
        "downloads_queued": queued,
    }


# ============================================================================
# TASK: SYNC ARTIST
# ============================================================================

def sync_artist(session: Session, artist_id: str, *, origin: str) -> Dict[str, Any]:
    """
    Fetch an artist from YTMusic: its details and pictures, and an Album row
    for each release not seen before.

    - "light" subscription: the albums stay metadata-only
    - "full" subscription: every album is in download mode, and those
      without tracks yet get an import (which queues their downloads)
    """
    subscription = subs_svc.get_artist_subscription(session, artist_id)
    if subscription is None:
        # Removed from the library since this job was queued
        return {"ok": True, "skipped": "artist not followed"}
    sync_mode = subscription.mode
    logger.info("Syncing artist %s in %s mode", artist_id, sync_mode)

    try:
        artist_data = artists_svc.fetch_and_upsert_artist(session, artist_id)
        session.commit()
    except Exception as e:
        logger.exception("Failed to fetch artist %s", artist_id)
        session.rollback()
        subs_svc.mark_artist_synced(session, artist_id, error=str(e))
        session.commit()
        # Mostly YouTube Music having a moment (YTMusicUnavailable): try
        # again shortly rather than wait for the next scheduled sync
        return {"ok": False, "error": str(e), "retry_delay_seconds": 120}

    artist = session.get(Artist, artist_id)
    try:
        artists_svc.ensure_artist_images(session, artist, thumbnails=artist_data["thumbnails"])
        session.commit()
    except Exception:
        logger.exception("Failed to download artist pictures for %s", artist_id)
        session.rollback()
    nfo_mod.write_artist_nfo(artist, folders_svc.artist_dir(session, artist))
    session.commit()  # its folder, when no picture named it

    # One commit per album: another sync running in parallel can create the
    # same album (one that is in both artists' discographies) between our
    # check and our commit. Its IntegrityError then only rolls back that one
    # album, which is left to the sync that created it -- the same outcome
    # as if it had already existed when this sync looked.
    album_mode = "download" if sync_mode == "full" else "metadata"
    new_releases = [r for r in albums_svc.list_artist_releases(artist_data) if session.get(Album, r["id"]) is None]
    albums_created = 0
    for release in new_releases:
        try:
            album = albums_svc.upsert_album(
                session,
                album_id=release["id"],
                title=release["title"],
                artist_id=artist_id,
                year=release["year"],
                album_type=release["type"],
            )
            album.mode = album_mode
            albums_svc.ensure_album_cover(session, album, thumbnails=release["thumbnails"])
            session.commit()
            albums_created += 1
        except IntegrityError:
            session.rollback()
            logger.info("Album %s was created by another sync meanwhile, skipping", release["id"])
        except Exception:
            session.rollback()
            logger.exception("Failed to create album %s", release["id"])

    # Full mode: metadata albums (from an earlier light follow) switch to
    # download mode, and every download-mode album still without tracks
    # gets an import -- the ones just created, and any whose earlier import
    # never landed, which nothing else would ever import again.
    imports_queued = 0
    if sync_mode == "full":
        try:
            imports_queued = subs_svc.upgrade_all_albums_to_download(session, artist_id, origin=Origin(origin))
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("Failed to queue album imports for artist %s", artist_id)

    try:
        genres_svc.queue_lookup(session, artist_id, origin=Origin(origin))
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Failed to queue genre lookup for artist %s", artist_id)

    subs_svc.mark_artist_synced(session, artist_id)
    session.commit()

    logger.info(
        "Synced artist %s (%s mode): %s new releases, %s albums created, %s imports queued",
        artist_id, sync_mode, len(new_releases), albums_created, imports_queued,
    )
    return {
        "ok": True,
        "mode": sync_mode,
        "new_albums": len(new_releases),
        "albums_created": albums_created,
        "jobs_queued": imports_queued,
    }


# ============================================================================
# TASK: SYNC CHART
# ============================================================================

def sync_chart(
    session: Session,
    country_code: str,
    *,
    origin: str,  # always BULK, see services/charts.enqueue_chart_sync
) -> Dict[str, Any]:
    """
    Fetch a country chart and follow its top N artists not followed in full
    yet. Following needs no network: each artist's sync job fetches it
    (and its pictures) like any other follow.
    """
    try:
        result = charts_svc.sync_chart(session, country_code)
    except YTMusicUnavailable as e:
        return {"ok": False, "error": str(e), "retry_delay_seconds": 900}
    if result.get("skipped"):
        logger.info("Chart sync skipped for %s: %s", country_code, result.get("reason"))
        return {**result, "ok": True}

    followed = 0
    for artist in result["artists_to_follow"]:
        # One short transaction per artist (single SQLite writer)
        if subs_svc.follow_artist(session, artist["id"], artist["name"], origin=Origin.BULK):
            followed += 1
        session.commit()

    logger.info("Chart sync for %s: %s artists followed", country_code, followed)
    return {**result, "ok": True, "artists_followed": followed}


# ============================================================================
# TASK: SYNC PLAYLIST
# ============================================================================

def sync_playlist(
    session: Session,
    playlist_id: str,
    fetch: bool = True,
    *,
    origin: str,
) -> Dict[str, Any]:
    """Scan a playlist added to the library (services/playlists.run_sync)."""
    return playlists_svc.run_sync(session, playlist_id, fetch=fetch, origin=Origin(origin))


# ============================================================================
# TASK: FETCH GENRES
# ============================================================================

def fetch_genres(session: Session, artist_id: str, *, origin: str) -> Dict[str, Any]:
    """
    Look up the genres of an artist and all its albums (services/genres.py),
    store them, then bring the files up to date: artist.nfo and album.nfo
    where they exist, and the genre tag of every track already downloaded
    from an album whose genres changed. Tracks still downloading tag
    themselves when they finish (download_track).

    Only worker-genres runs this, which is what keeps MusicBrainz at one
    request per second.
    """
    if not settings_module.feature_enabled(session, "genres"):
        return {"ok": True, "skipped": "genre lookups are switched off"}

    artist = session.get(Artist, artist_id)
    if not artist:
        return {"ok": True, "skipped": "artist not in DB"}
    albums = [(a.id, a.title, a.year) for a in session.query(Album).filter(Album.artist_id == artist_id).all()]
    name, musicbrainz_id, deezer_id = artist.name, artist.musicbrainz_id, artist.deezer_id
    session.rollback()  # nothing held while the sources answer (several seconds)

    try:
        found = genres_svc.lookup_artist(artist_id, name, albums, musicbrainz_id, deezer_id)
    except genres_svc.GenreSourceUnavailable as e:
        logger.warning("Genre lookup for %s postponed: %s", name, e)
        return {"ok": False, "error": str(e), "retry_delay_seconds": 900}

    # ===== Store (one short transaction) =====
    session.expire_all()
    artist = session.get(Artist, artist_id)
    if not artist:
        return {"ok": True, "skipped": "artist deleted meanwhile"}
    now = now_utc()
    artist_changed = (artist.genres or []) != found.genres
    artist.genres = found.genres
    artist.musicbrainz_id = found.musicbrainz_id
    artist.deezer_id = found.deezer_id
    artist.genres_checked_at = now
    changed: Dict[str, list] = {}
    for album in session.query(Album).filter(Album.id.in_(list(found.albums))).all():
        picked = found.albums[album.id]
        if (album.genres or []) != picked.genres:
            changed[album.id] = picked.genres
        album.genres = picked.genres
        album.genres_source = picked.source
        album.genres_checked_at = now
    session.commit()

    # ===== Files (no transaction) =====
    artist_folder = folders_svc.existing_artist_dir(artist)
    if artist_changed and artist_folder and artist_folder.is_dir():
        nfo_mod.write_artist_nfo(artist, artist_folder)
    retagged = 0
    if changed:
        for album in session.query(Album).filter(Album.id.in_(list(changed))).all():
            album_folder = folders_svc.existing_album_dir(album)
            if album_folder and album_folder.is_dir():
                nfo_mod.write_album_nfo(album, artist, album_folder)
        done_tracks = session.query(Track).filter(
            Track.album_id.in_(list(changed)),
            Track.status == "done",
            Track.file_path.is_not(None),
        ).all()
        for track in done_tracks:
            if embed_mod.set_genres(track.file_path, changed[track.album_id]):
                retagged += 1

    # Albums a sync added while this ran get a follow-up lookup
    try:
        if genres_svc.queue_lookup(session, artist_id, origin=Origin(origin), from_lookup=True):
            logger.info("Albums of %s added during the lookup: follow-up queued", name)
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Failed to queue follow-up genre lookup for %s", name)

    with_genres = sum(1 for g in found.albums.values() if g.genres)
    logger.info(
        "Genres for %s: %s/%s albums, %s changed, %s files re-tagged",
        name, with_genres, len(found.albums), len(changed), retagged,
    )
    return {
        "ok": True,
        "albums": len(found.albums),
        "albums_with_genres": with_genres,
        "albums_changed": len(changed),
        "files_retagged": retagged,
    }


# ============================================================================
# TASK DISPATCHER
# ============================================================================

_TASK_MAP = {
    "download_track": download_track,
    "download_lyrics": download_lyrics,
    "import_album": import_album,
    "sync_artist": sync_artist,
    "sync_chart": sync_chart,
    "fetch_genres": fetch_genres,
    "sync_playlist": sync_playlist,
}

ALL_JOB_TYPES = tuple(_TASK_MAP)


def run_job_task(session: Session, job: Job) -> Dict[str, Any]:
    """
    Run the handler of a reserved job with its payload as arguments. Never
    raises: an error comes back as {"ok": False, "error": ...}.
    """
    # Read now: once a task fails mid-transaction, touching `job` again
    # before the rollback raises a second error, and that one escaped to the
    # worker loop, leaving the job "reserved" until the orphan sweep.
    job_id, job_type, payload = job.id, job.type, dict(job.payload or {})
    handler = _TASK_MAP.get(job_type)
    if handler is None:
        logger.error("Unknown job type: %s", job_type)
        return {"ok": False, "error": f"Unknown job type: {job_type}"}

    try:
        return handler(session, **payload)
    except Exception as e:
        session.rollback()
        logger.exception("Job %s (%s) failed", job_id, job_type)
        return {"ok": False, "error": f"Unexpected error: {e}"}
