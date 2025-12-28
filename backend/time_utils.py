# backend/time_utils.py
from __future__ import annotations
import os
from datetime import datetime, timezone, tzinfo
from typing import Optional
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


def ensure_timezone_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Ensure a datetime is timezone-aware.
    
    If the datetime is naive (no timezone), assumes it's in UTC and adds timezone info.
    If already aware, returns as-is.
    If None, returns None.
    
    Args:
        dt: Datetime that may be naive or aware
    
    Returns:
        Timezone-aware datetime in UTC, or None
    """
    if dt is None:
        return None
    
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        # Naive datetime - assume UTC
        return dt.replace(tzinfo=timezone.utc)
    
    # Already aware
    return dt