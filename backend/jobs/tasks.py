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
- download_lyrics: Download synced lyrics (backend/lyrics: LRCLIB, then YouTube Music)
- import_album: Fetch an album's tracklist from YTMusic, then queue its downloads
- sync_artist: Check artist for new releases
- sync_chart: Follow a chart's top artists
- sync_playlist: Scan a playlist added to the library
- find_video_songs: Look up the songs of a playlist's music videos (for its page)
- fetch_genres: Look up an artist's and its albums' genres (MusicBrainz, Deezer)
"""
from __future__ import annotations
import contextlib
import fcntl
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import config, settings as settings_module
from ..config import YDL_COOKIEFILE, YDL_USER_COOKIEFILE
from ..downloader import cover as cover_mod, embed as embed_mod, nfo as nfo_mod
from ..downloader.core import download_track_by_videoid
from ..lyrics import lrclib, ytmusic
from ..lyrics.base import Lyrics, LyricsQuery, ProviderUnavailable
from ..models import Job, Track, Album, Artist
from ..services import albums as albums_svc
from ..services import artists as artists_svc
from ..services import charts as charts_svc
from ..services import exclusions as exclusions_svc
from ..services import folders as folders_svc
from ..services import genres as genres_svc
from ..services import playlists as playlists_svc
from ..services import reissues as reissues_svc
from ..services import subscriptions as subs_svc
from ..services import tracks as tracks_svc
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
)

# "unable to download video data: HTTP Error 403: Forbidden": the googlevideo
# CDN refusing the download. That can be this IP/session (too many concurrent
# downloads get it before, or instead of, the bot check; a stale yt-dlp
# signature too) or just this one video, which YouTube sometimes refuses (or
# answers 503) for a while when the tracks around it download fine. Only a
# second track refused tells them apart (jobs.gate.note_download_refused).
_YOUTUBE_REFUSED_MARKER = "http error 403"

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


def _is_youtube_refused_error(error: Any) -> bool:
    """A 403 from YouTube: this video, or the IP (see _YOUTUBE_REFUSED_MARKER)."""
    return _YOUTUBE_REFUSED_MARKER in _error_text(error)


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
      - YouTube throttles or refuses us -> reset this worker's anonymous
        cookie jar (fresh session) and retry;
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

            throttled = _is_youtube_rate_limit_error(error)
            if (throttled or _is_youtube_refused_error(error)) and cookiefile != YDL_USER_COOKIEFILE:
                what = "rate limit" if throttled else "refusal (HTTP 403)"
                logger.warning("YouTube %s for track %s", what, track_id)
                if not cookies_reset and _reset_youtube_cookies():
                    cookies_reset = True
                    logger.info("Retrying download for track %s after cookie reset", track_id)
                    time.sleep(2)
                    continue
                logger.error("YouTube %s persists for track %s", what, track_id)
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
        _discard_orphan_download(session, track_id, file_path, moved_cover, dest_dir, album_id)
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

    # Same for its artist renamed meanwhile (sync_artist re-tags the tracks
    # that were already done)
    if album_id and metadata["artist_name"]:
        try:
            current_name = session.execute(
                select(Artist.name).join(Album, Album.artist_id == Artist.id).where(Album.id == album_id)
            ).scalar()
            if current_name and current_name != metadata["artist_name"]:
                embed_mod.set_artist(file_path, current_name)
        except Exception:
            logger.exception("Failed to re-tag the artist of track %s", track_id)

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


def _discard_orphan_download(
    session: Session,
    track_id: str,
    file_path: str,
    moved_cover: Optional[str],
    dest_dir: Path,
    album_id: Optional[str],
) -> None:
    """
    The track was deleted while it downloaded: its album or artist was
    deleted from the library (the only ways a track row goes). Take back
    what the download put on disk after the deletion cleaned up:
    - the audio file;
    - the cover, when this download moved it into the album folder: back
      to COVERS_DIR if the album row is still there (a deleted album stays
      as metadata, and shows its cover), deleted with the artist otherwise;
    - the album folder, then the artist folder, which the download
      recreated, if nothing else is left in them.
    """
    logger.info("Track %s was removed during its download, deleting %s", track_id, file_path)
    Path(file_path).unlink(missing_ok=True)
    if moved_cover:
        album = session.get(Album, album_id) if album_id else None
        if album is None:
            Path(moved_cover).unlink(missing_ok=True)
        else:
            back = cover_mod.move_file(Path(moved_cover), config.COVERS_DIR / f"{album.id}.jpg")
            album.image_local = str(back) if back else None
            session.commit()
    for folder in (dest_dir, dest_dir.parent):
        if folder == config.MUSIC_DIR:
            break
        try:
            folder.rmdir()
        except OSError:
            break  # not empty (the album's other files, the artist's own) or already gone


def _pause_downloads(session: Session, track_id: str, error: Exception) -> None:
    """
    Stop every download worker for a while rather than letting the others
    keep hammering a blocked IP (jobs.gate).
    """
    try:
        gate.pause_downloads(session, reason=f"track {track_id}: {tracks_svc.truncate_error(error)}")
    except Exception:
        logger.exception("Failed to pause downloads after rate limit")
        session.rollback()


def _download_failed(session: Session, track_id: str, error: Exception) -> Dict[str, Any]:
    """The task result for a failed download, with the reason recorded on the track."""
    session.rollback()
    throttled = _is_youtube_rate_limit_error(error)
    refused = not throttled and _is_youtube_refused_error(error)
    if throttled:
        logger.warning("Download of track %s hit YouTube's rate limit; requeued", track_id)
    elif not refused:
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

    if refused:
        # The IP or this one video? (jobs.gate.note_download_refused)
        try:
            ip_refused = gate.note_download_refused(session, track_id)
        except Exception:
            logger.exception("Failed to record the refused download of track %s", track_id)
            session.rollback()
            ip_refused = False
        if ip_refused:
            logger.warning("Download of track %s refused by YouTube (403) right after another refusal or pause: the IP, not the video", track_id)
            _pause_downloads(session, track_id, error)
        else:
            logger.warning("Download of track %s refused by YouTube (403); retrying it later, the queue carries on", track_id)
        # Never refunded, unlike a rate limit: if one video keeps being
        # refused, spending its attempts is what lets it fail for good
        # instead of holding up the queue after every pause.
        return {
            "ok": False,
            "error": f"Download failed: {error}",
            # Once the pause lifts, or, for the one video, after a while:
            # YouTube refusing a video tends to last a good half hour
            "retry_delay_seconds": 600 if ip_refused else 1800,
        }

    if throttled:
        # Still limited after a fresh session: it's the IP, not the cookies.
        _pause_downloads(session, track_id, error)
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

def download_lyrics(
    session: Session,
    track_id: str,
    mode: str = "normal",
    *,
    origin: str,  # sets this job's priority; queues nothing itself
) -> Dict[str, Any]:
    """
    Download lyrics for a track into a .lrc file next to it (see
    _download_lyrics). An unexpected error is retried in an hour.
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

    The first of these wins:
    1. LRCLIB's synced lyrics
    2. LRCLIB's plain lyrics, when allowed (not in an upgrade, nor with
       features.synced_lyrics_only)
    3. LRCLIB's word that the track is instrumental (not in an upgrade)
    4. YouTube Music's synced lyrics, then its plain ones when allowed. An
       upgrade asks it only when LRCLIB has no record of the song.
    Nothing found while a source was unavailable is retried in an hour,
    otherwise in a day.
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
    synced_lyrics_only = bool(settings_module.get_setting(session, "features.synced_lyrics_only"))
    if not track_name or not artist_name:
        return {"ok": False, "error": "Missing track name or artist name"}
    # Nothing held while the provider answers: a Retry-After can stretch the
    # lookup to minutes, and an open read keeps SQLite from checkpointing
    session.rollback()

    logger.info("Fetching lyrics for: %s - %s (mode=%s)", artist_name, track_name, mode)
    query = LyricsQuery(video_id=track_id, title=track_name, artist=artist_name, album=album_name, duration=duration)
    upgrade = mode == "upgrade"
    allow_plain = not synced_lyrics_only and not upgrade
    unavailable: List[str] = []

    def ask(provider: Any) -> Optional[Lyrics]:
        try:
            return provider.lookup(query)
        except ProviderUnavailable as e:
            logger.warning("%s unavailable for track %s: %s", provider.NAME, track_id, e)
            unavailable.append(f"{provider.NAME} unavailable: {e}")
            return None

    # LRCLIB is the authority: its synced lyrics, else its plain ones (when
    # allowed), else its word that the track is instrumental
    chosen: Optional[Tuple[str, str, str]] = None  # (lyrics, kind, where from)
    instrumental: Optional[str] = None  # where from
    primary = ask(lrclib)
    if primary and primary.synced:
        chosen = (primary.synced, "synced", f"{lrclib.NAME} {primary.source}")
    elif primary and allow_plain and primary.plain:
        chosen = (primary.plain, "plain", f"{lrclib.NAME} {primary.source}")
    elif primary and primary.instrumental and not upgrade:
        instrumental = f"{lrclib.NAME} {primary.source}"

    # YouTube Music only when LRCLIB has nothing usable: two YouTube
    # requests each, from the downloads' IP. An upgrade asks it only when
    # LRCLIB has no record of the song (one there, plain only, is LRCLIB's
    # answer until a synced upload comes), so not while LRCLIB is down.
    if chosen or instrumental:
        ask_youtube = False
    elif upgrade:
        ask_youtube = primary is not None and not primary.found
    else:
        ask_youtube = True
    fallback = ask(ytmusic) if ask_youtube else None
    if fallback and fallback.synced:
        chosen = (fallback.synced, "synced", f"{ytmusic.NAME} ({fallback.source})")
    elif fallback and allow_plain and fallback.plain:
        chosen = (fallback.plain, "plain", f"{ytmusic.NAME} ({fallback.source})")

    track = session.get(Track, track_id)
    if track is None:
        return {"ok": True, "skipped": "track removed during the lookup"}

    if instrumental:
        # No .lrc to write: the kind alone tells the UI and the retry sweep
        # (which only looks at tracks without lyrics) that there is none.
        track.lyrics = "instrumental"
        track.lyrics_local = None
        session.commit()
        logger.info("Track %s is instrumental per %s", track_id, instrumental)
        return {"ok": True, "lyrics_type": "instrumental"}

    if chosen is None:
        # A source that couldn't answer may have them: sooner than the
        # daily retry of a track nobody has lyrics for
        if unavailable:
            return {"ok": False, "error": "; ".join(unavailable), "retry_delay_seconds": 3600}
        if upgrade:
            return {"ok": True, "message": "No synced lyrics available yet, keeping plain"}
        if any(answer and answer.plain for answer in (primary, fallback)):
            logger.info("Only plain lyrics available for track %s, will retry later", track_id)
            return {
                "ok": False,
                "error": "Only plain lyrics available (synced lyrics required)",
                "retry_delay_seconds": 86400,
            }
        logger.info("No lyrics found for track %s", track_id)
        return {"ok": False, "error": "Lyrics not found", "retry_delay_seconds": 86400}

    lyrics_to_save, lyrics_kind, where = chosen
    logger.info("Found %s lyrics for track %s via %s", lyrics_kind, track_id, where)
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
    (albums_svc.complete_import). Also how an album in the library is
    refreshed (subs_svc.queue_album_refreshes): what changed on YouTube
    Music since is stored, and written to the tags of its files.
    """
    album = session.get(Album, browse_id)
    # Unfollowed (or deleted) since it was queued
    if album is None or album.mode != "download":
        return {"ok": True, "skipped": "album not in download mode"}

    try:
        result = albums_svc.fetch_and_upsert_album(session, browse_id=browse_id, artist_id=artist_id)
        session.commit()
        for path, tags in result["retag"]:
            embed_mod.set_tags(path, **tags)
        if result["cover_changed"]:
            albums_svc.embed_album_cover(session, result["album_id"])
        queued = albums_svc.complete_import(session, result["album_id"], origin=Origin(origin))
    except albums_svc.ArtistDeleted:
        session.rollback()
        logger.info("Artist %s was deleted during the import of album %s, nothing stored", artist_id, browse_id)
        return {"ok": True, "skipped": "artist deleted during the import"}
    except Exception as e:
        session.rollback()
        logger.exception("import_album failed for %s", browse_id)
        # Recorded, so its artist's syncs don't queue its refresh again
        # before ALBUM_REFRESH_INTERVAL (the job retries it meanwhile)
        album = session.get(Album, browse_id)
        if album is not None:
            album.last_synced_at = now_utc()
            album.last_error = tracks_svc.truncate_error(e)
            session.commit()
        return {"ok": False, "error": str(e), "retry_delay_seconds": 120}

    logger.info(
        "Imported album %s: %s new tracks, %s updated, %s no longer listed, %s files re-tagged, %s downloads queued",
        browse_id, result["inserted_tracks"], result["updated_tracks"], result["removed_tracks"],
        len(result["retag"]), queued,
    )
    return {
        "ok": True,
        "album_id": result["album_id"],
        "tracks_inserted": result["inserted_tracks"],
        "tracks_updated": result["updated_tracks"],
        "tracks_removed": result["removed_tracks"],
        "files_retagged": len(result["retag"]),
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

    Either way, its download-mode albums not read since
    ALBUM_REFRESH_INTERVAL get an import too, which brings their tracklist
    up to date (subs_svc.queue_album_refreshes).
    """
    subscription = subs_svc.get_artist_subscription(session, artist_id)
    if subscription is None:
        # Removed from the library since this job was queued
        return {"ok": True, "skipped": "artist not followed"}
    sync_mode = subscription.mode
    logger.info("Syncing artist %s in %s mode", artist_id, sync_mode)
    # Its name before this sync, to notice a rename
    known = session.get(Artist, artist_id)
    old_name = known.name if known else None

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

    if artist_data["channel"]:
        # Followed by id alone (the API, a playlist credit) before its page
        # was read: a YouTube user's channel has nothing to bring in
        artists_svc.drop_channel(session, artist_id)
        session.commit()
        logger.warning("Artist %s is a YouTube user's channel, not an artist: unfollowed", artist_id)
        return {"ok": True, "skipped": "not an artist (a YouTube user's channel)"}

    artist = session.get(Artist, artist_id)
    try:
        artists_svc.ensure_artist_images(
            session, artist, thumbnails=artist_data["thumbnails"], picture=artist_data["picture"]
        )
        session.commit()
    except Exception:
        logger.exception("Failed to download artist pictures for %s", artist_id)
        session.rollback()
    nfo_mod.write_artist_nfo(artist, folders_svc.artist_dir(session, artist))
    session.commit()  # its folder, when no picture named it
    if old_name is not None and artist.name != old_name:
        _follow_artist_rename(session, artist, old_name)

    # One commit per album: another sync running in parallel can create the
    # same album (one that is in both artists' discographies) between our
    # check and our commit. Its IntegrityError then only rolls back that one
    # album, which is left to the sync that created it -- the same outcome
    # as if it had already existed when this sync looked.
    album_mode = "download" if sync_mode == "full" else "metadata"
    releases = albums_svc.list_artist_releases(artist_data)
    # Albums no longer listed: reissued under a new id (moved to it, so not
    # new below) or gone from YouTube Music (services/reissues.py)
    listing = {"replaced": 0, "removed": 0}
    try:
        listing = reissues_svc.follow_listing(session, artist_id, releases)
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Failed to follow the releases listed for artist %s", artist_id)
    new_releases = [r for r in releases if session.get(Album, r["id"]) is None]
    covers_changed = _follow_cover_changes(session, [r for r in releases if r not in new_releases])
    # Deleted from the library before (its artist deleted with it, since
    # followed again): stays metadata-only (services/exclusions.py)
    excluded = exclusions_svc.blocked_album_ids(session, {r["id"]: artist_id for r in new_releases})
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
            album.mode = "metadata" if release["id"] in excluded else album_mode
            album.on_artist_page = True
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

    # Either mode: its albums in the library get their tracklist read again
    # once in a while (YouTube Music adds, removes and renames tracks of
    # albums long out). After the commit above: queue_album_refreshes then
    # sees the imports just queued, and doesn't queue them twice.
    try:
        imports_queued += subs_svc.queue_album_refreshes(session, artist_id, origin=Origin(origin))
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Failed to queue album refreshes for artist %s", artist_id)

    try:
        genres_svc.queue_lookup(session, artist_id, origin=Origin(origin), from_sync=True)
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Failed to queue genre lookup for artist %s", artist_id)

    subs_svc.mark_artist_synced(session, artist_id)
    session.commit()

    logger.info(
        "Synced artist %s (%s mode): %s new releases, %s albums created, %s imports queued, %s covers changed, "
        "%s albums reissued, %s removed from YouTube Music",
        artist_id, sync_mode, len(new_releases), albums_created, imports_queued, covers_changed,
        listing["replaced"], listing["removed"],
    )
    return {
        "ok": True,
        "mode": sync_mode,
        "new_albums": len(new_releases),
        "albums_created": albums_created,
        "jobs_queued": imports_queued,
    }


def _follow_cover_changes(session: Session, releases: List[Dict[str, Any]]) -> int:
    """
    The artist page's cards show each release's current cover: one that
    changed since it was saved replaces it, on disk and in the album's
    files (albums_svc.ensure_album_cover). Only a changed cover is
    downloaded. Errors are logged, not raised. Returns how many changed.
    """
    changed = 0
    for release in releases:
        try:
            album = session.get(Album, release["id"])
            if album is None or not albums_svc.ensure_album_cover(session, album, release["thumbnails"]):
                continue
            session.commit()
            albums_svc.embed_album_cover(session, album.id)
            changed += 1
        except Exception:
            session.rollback()
            logger.exception("Failed to follow the cover of album %s", release["id"])
    session.commit()  # the pictures recorded the first time round
    return changed


def _follow_artist_rename(session: Session, artist: Artist, old_name: str) -> None:
    """
    The artist has a new name: renamed on YouTube Music, or first named from
    an album page that spells it differently (services/albums.py). Its files
    catch up: the album.nfo of each album on disk and the artist tags of its
    downloaded tracks. Its folders keep their names (services/folders.py), and
    every sync rewrites artist.nfo anyway. Tracks still downloading tag
    themselves when they finish (download_track). Errors are logged, not raised.
    """
    try:
        nfos = 0
        for album in session.query(Album).filter(Album.artist_id == artist.id).all():
            folder = folders_svc.existing_album_dir(album)
            if folder and folder.is_dir() and nfo_mod.write_album_nfo(album, artist, folder):
                nfos += 1
        paths = session.execute(
            select(Track.file_path)
            .join(Album, Album.id == Track.album_id)
            .where(Album.artist_id == artist.id, Track.status == "done", Track.file_path.is_not(None))
        ).scalars().all()
        retagged = sum(embed_mod.set_artist(path, artist.name) for path in paths)
        logger.info(
            "Artist %s renamed from %r to %r: %s album.nfo rewritten, %s of %s tracks re-tagged",
            artist.id, old_name, artist.name, nfos, retagged, len(paths),
        )
    except Exception:
        logger.exception("Failed to bring the files of artist %s up to its new name", artist.id)


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
    (and its pictures) like any other follow. Then unfollow the artists the
    charts followed that have been out of them long enough
    (charts_svc.unfollow_dropped_artists).
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
        if subs_svc.follow_artist(session, artist["id"], artist["name"], origin=Origin.BULK, by_chart=True):
            followed += 1
        session.commit()

    unfollowed = charts_svc.unfollow_dropped_artists(session, country_code, result.pop("top_ids"))
    logger.info("Chart sync for %s: %s artists followed, %s unfollowed", country_code, followed, len(unfollowed))
    return {**result, "ok": True, "artists_followed": followed, "artists_unfollowed": unfollowed}


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
# TASK: FIND VIDEO SONGS
# ============================================================================

def find_video_songs(
    session: Session,
    playlist_id: str,
    videos: List[Dict[str, Any]],
    *,
    origin: str,
) -> Dict[str, Any]:
    """
    Look up the songs of a playlist's music videos, for its page
    (services/playlists.look_up_songs): the page shows them once this is
    done. Searches that failed are retried.
    """
    failed = playlists_svc.look_up_songs(session, videos)
    if failed:
        return {
            "ok": False,
            "error": f"the songs of {failed} music video(s) couldn't be looked up",
            "retry_delay_seconds": 120,
        }
    return {"ok": True, "playlist_id": playlist_id, "videos": len(videos)}


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

    # Albums added while this ran get a follow-up lookup (unless a sync of
    # the artist is still at it: it queues one when it's done)
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
    "find_video_songs": find_video_songs,
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
