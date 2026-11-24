# backend/time_utils.py
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional


def now_utc() -> datetime:
    """Timezone-aware current time in UTC (what the DB stores)."""
    return datetime.now(timezone.utc)


def ensure_timezone_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """A naive datetime as UTC (SQLite hands them back naive); aware ones and None as they are."""
    if dt is not None and (dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None):
        return dt.replace(tzinfo=timezone.utc)
    return dt
