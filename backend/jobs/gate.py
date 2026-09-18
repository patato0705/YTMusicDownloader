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
  carrying on is how a soft limit turns into a ban.

Other job types (metadata, lyrics) are never gated.
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from .. import config
from ..settings import get_setting, set_setting
from ..time_utils import now_utc

logger = logging.getLogger("jobs.gate")

DOWNLOAD_JOB_TYPE = "download_track"


def active_download_slots(session: Session) -> int:
    """How many download workers may take jobs right now (>= 1)."""
    try:
        wanted = int(get_setting(session, "download.max_concurrent", 1) or 1)
    except (TypeError, ValueError):
        wanted = 1
    return max(1, min(wanted, config.DOWNLOAD_WORKERS))


def downloads_paused_until(session: Session) -> Optional[datetime]:
    """The end of the current rate-limit pause, or None if downloads run."""
    raw = get_setting(session, "download.paused_until", "") or ""
    if not raw:
        return None
    try:
        until = datetime.fromisoformat(str(raw))
    except ValueError:
        logger.warning("Ignoring unparseable download.paused_until=%r", raw)
        return None
    if until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)
    return until if until > now_utc() else None


# Each consecutive pause (no successful download in between) doubles the
# duration, up to base * 2**MAX_PAUSE_DOUBLINGS: 10 min -> 20 -> 40 -> 80 ->
# 160 at the default. A bot check can last hours, and probing it every ten
# minutes with several workers is what keeps it going.
MAX_PAUSE_DOUBLINGS = 4


def _int_setting(session: Session, key: str, default: int) -> int:
    try:
        return int(get_setting(session, key, default) or default)
    except (TypeError, ValueError):
        return default


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


def note_download_succeeded(session: Session) -> None:
    """Reset the pause escalation once a download gets through. Commits if needed."""
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
