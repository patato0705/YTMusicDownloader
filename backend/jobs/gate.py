# backend/jobs/gate.py
"""
Throttle for the download workers.

Several download worker processes run side by side (deploy/supervisord.conf),
but how many of them may actually talk to YouTube at once is decided here,
from two settings the workers re-read on every poll:

- download.max_concurrent: how many workers are active. Worker N (from its
  WORKER_NAME suffix) takes download jobs only while N < max_concurrent;
  the rest idle. Tunable live from the admin panel, capped at the number
  of processes supervisord started (config.DOWNLOAD_WORKERS).
- download.paused_until: set by pause_downloads() when a download still
  hits YouTube's rate limit after a cookie reset. While it's in the future
  *no* worker takes download jobs -- with one IP, the other workers
  carrying on is how a soft limit turns into a ban. A plain 403 only
  pauses once note_download_refused() rules out one video YouTube won't
  serve.

Other job types (metadata, lyrics) are never gated.
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from .. import config
from ..settings import get_setting, set_setting
from ..time_utils import now_utc, ensure_timezone_aware

logger = logging.getLogger("jobs.gate")

DOWNLOAD_JOB_TYPE = "download_track"


def _int_setting(session: Session, key: str, default: int) -> int:
    try:
        return int(get_setting(session, key) or default)
    except (TypeError, ValueError):
        return default


def active_download_slots(session: Session) -> int:
    """How many download workers may take jobs right now (>= 1)."""
    return max(1, min(_int_setting(session, "download.max_concurrent", 1), config.DOWNLOAD_WORKERS))


def _time_setting(session: Session, key: str) -> Optional[datetime]:
    """A setting holding an ISO time; None when empty or unparseable."""
    raw = get_setting(session, key)
    if not raw:
        return None
    try:
        return ensure_timezone_aware(datetime.fromisoformat(str(raw)))
    except ValueError:
        logger.warning("Ignoring unparseable %s=%r", key, raw)
        return None


def downloads_paused_until(session: Session) -> Optional[datetime]:
    """The end of the current rate-limit pause, or None if downloads run."""
    until = _time_setting(session, "download.paused_until")
    return until if until and until > now_utc() else None


# Each consecutive pause (no successful download in between) doubles the
# duration, up to base * 2**MAX_PAUSE_DOUBLINGS: 10 min -> 20 -> 40 -> 80 ->
# 160 at the default. A bot check can last hours, and probing it every ten
# minutes with several workers is what keeps it going.
MAX_PAUSE_DOUBLINGS = 4


def pause_downloads(session: Session, reason: str) -> datetime:
    """
    Stop every download worker from taking jobs. Commits. Returns the
    resume time. Never shortens a pause already in place, and only counts
    as a new strike when no pause is currently running -- several workers
    tripping over the same limit within seconds is one event.
    """
    current = downloads_paused_until(session)
    if current:
        return current

    base = max(1, _int_setting(session, "download.rate_limit_pause_minutes", 10))
    streak = max(0, _int_setting(session, "download.pause_streak", 0))
    minutes = base * (2 ** min(streak, MAX_PAUSE_DOUBLINGS))
    until = now_utc() + timedelta(minutes=minutes)

    set_setting(session, "download.paused_until", until.isoformat(), commit=False)
    set_setting(session, "download.pause_streak", streak + 1, commit=False)
    session.commit()
    logger.warning(
        "Paused all downloads for %s min (strike %s) until %s: %s",
        minutes, streak + 1, until.isoformat(timespec="seconds"), reason,
    )
    return until


# How long a refused download, or the end of a pause, is remembered when
# telling one video YouTube won't serve apart from the whole IP being
# refused (note_download_refused). A success in between forgets the
# refused download sooner.
REFUSAL_WINDOW = timedelta(minutes=30)


def note_download_refused(session: Session, track_id: str) -> bool:
    """
    Record that YouTube refused this track's download (HTTP 403) and say
    whether that means the IP is refused rather than the one video. One
    video YouTube won't serve for now must not pause the whole queue (it
    would be retried first after every pause and hold everything up); with
    an IP block, the very next track gets the same 403. So it is the IP when,
    within REFUSAL_WINDOW:
    - a *different* track was refused with no download getting through
      since, or
    - a pause ended with no download getting through since (pause_streak):
      the block is still on, and probing it with one more track after
      every pause would only spend that track's attempts too.
    Commits.
    """
    now = now_utc()
    paused_until = _time_setting(session, "download.paused_until")
    ip_refused = (
        _int_setting(session, "download.pause_streak", 0) > 0
        and paused_until is not None
        and now - paused_until <= REFUSAL_WINDOW
    )

    raw = str(get_setting(session, "download.last_refused") or "")
    previous_track, _, previous_at = raw.partition(" ")
    if not ip_refused and previous_track and previous_track != track_id:
        try:
            at = ensure_timezone_aware(datetime.fromisoformat(previous_at))
            ip_refused = now - at <= REFUSAL_WINDOW
        except ValueError:
            logger.warning("Ignoring unparseable download.last_refused=%r", raw)

    set_setting(session, "download.last_refused", f"{track_id} {now.isoformat()}")
    return ip_refused


def note_download_succeeded(session: Session) -> None:
    """
    A download got through: forget the last refused one (a 403 since then
    is that video's own problem again) and reset the pause escalation.
    Commits if needed.

    The escalation is kept while a pause is in force: with several
    workers, one tripping the limit while the others are mid-download is
    the normal case, and those downloads started *before* the block --
    them finishing says nothing about whether it has lifted. Without this
    the streak was wiped within a second of every pause and never
    escalated past 10 min.
    """
    if get_setting(session, "download.last_refused"):
        set_setting(session, "download.last_refused", "")
    if downloads_paused_until(session):
        return
    if _int_setting(session, "download.pause_streak", 0) > 0:
        set_setting(session, "download.pause_streak", 0)
        logger.info("Download succeeded; rate-limit pause escalation reset")


def worker_may_download(session: Session, worker_index: int) -> tuple[bool, str]:
    """
    Whether download worker number `worker_index` should reserve download
    jobs on this poll. Returns (allowed, reason-when-not).
    """
    paused = downloads_paused_until(session)
    if paused:
        return False, f"downloads paused until {paused.isoformat(timespec='seconds')} (rate limit)"
    slots = active_download_slots(session)
    if worker_index >= slots:
        return False, f"idle: download.max_concurrent={slots}, this is worker #{worker_index + 1}"
    return True, ""
