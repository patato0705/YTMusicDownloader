# backend/time_utils.py
from __future__ import annotations
import os
from datetime import datetime, timezone, tzinfo
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None


def now_utc() -> datetime:
    """Datetime timezone-aware in UTC (to store in DB)."""
    return datetime.now(timezone.utc)


def get_local_zone() -> tzinfo:
    """
    Returns a local tzinfo based on TZ env var (ex: "Europe/Paris").
    If not possible, returns timezone.utc.
    """
    tzname = os.environ.get("TZ")
    if tzname and ZoneInfo is not None:
        try:
            return ZoneInfo(tzname)
        except Exception:
            # ignore invalid TZ name
            pass
    return timezone.utc


def now_local() -> datetime:
    """Datetime aware in local timezone (according to TZ)."""
    return now_utc().astimezone(get_local_zone())