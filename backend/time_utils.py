# backend/time_utils.py
from __future__ import annotations
import os
from datetime import datetime, timezone, tzinfo
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None


def now_utc() -> datetime:
    """Datetime timezone-aware en UTC (à stocker en BDD)."""
    return datetime.now(timezone.utc)


def get_local_zone() -> tzinfo:
    """
    Retourne un tzinfo local basé sur TZ env var (ex: "Europe/Paris").
    Si impossible, retourne timezone.utc.
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
    """Datetime aware dans le fuseau local (selon TZ)."""
    return now_utc().astimezone(get_local_zone())