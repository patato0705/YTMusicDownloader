# backend/schedules.py
"""
Schedules of the scheduler's recurring work (artist syncs, chart syncs,
lyrics retries), set from the admin panel.

Each is one setting of type "schedule", in one of two modes:

- {"mode": "interval", "every": 6}: every N hours (or days, depending on
  the setting's unit), counted from the last time -- for artist and chart
  syncs, from each one's own last sync, so they spread over the day.
- {"mode": "fixed", "time": "07:00", "days": ["mon", "fri"]}: at that time
  of day, on those days of the week. Everything due then is queued at once.

Times are in the container's time zone (TZ). A fixed run the app wasn't up
for -- more than GRACE after its time -- is skipped, not caught up: whoever
picks 07:00 to stay out of busy hours doesn't want it at 15:00 instead.
"""
from __future__ import annotations
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger("schedules")

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")  # datetime.weekday() order
GRACE = timedelta(minutes=30)
_TIME = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


@dataclass(frozen=True)
class Schedule:
    mode: str                       # "interval" or "fixed"
    every: int = 0                  # interval mode, in the setting's unit
    time: str = ""                  # fixed mode, "HH:MM"
    days: tuple = ()                # fixed mode, subset of DAYS in week order

    @property
    def fixed(self) -> bool:
        return self.mode == "fixed"


def validate(value: Any, minimum: int = 1, maximum: Optional[int] = None) -> dict:
    """
    Check a schedule setting's value and return it normalized (days in week
    order, no duplicates). Raises ValueError, worded for the admin panel.
    """
    if not isinstance(value, dict):
        raise ValueError("must be a schedule")
    mode = value.get("mode")
    if mode == "interval":
        every = value.get("every")
        if isinstance(every, bool) or not isinstance(every, (int, float)) or int(every) != every:
            raise ValueError("the interval must be a whole number")
        every = int(every)
        if every < minimum or (maximum is not None and every > maximum):
            bound = f"between {minimum} and {maximum}" if maximum is not None else f"at least {minimum}"
            raise ValueError(f"the interval must be {bound}")
        return {"mode": "interval", "every": every}
    if mode == "fixed":
        time = str(value.get("time") or "")
        if not _TIME.match(time):
            raise ValueError("the time must be HH:MM (24-hour)")
        days = value.get("days")
        if not isinstance(days, list) or not days or any(d not in DAYS for d in days):
            raise ValueError("pick at least one day of the week")
        return {"mode": "fixed", "time": time, "days": [d for d in DAYS if d in days]}
    raise ValueError("the mode must be 'interval' or 'fixed'")


def parse(value: Any, default: dict) -> Schedule:
    """A stored schedule setting as a Schedule; the default if it's unusable."""
    try:
        value = validate(value)
    except ValueError:
        logger.warning("Ignoring invalid schedule %r, using %r", value, default)
        value = default
    if value["mode"] == "fixed":
        return Schedule("fixed", time=value["time"], days=tuple(value["days"]))
    return Schedule("interval", every=value["every"])


def timezone() -> ZoneInfo:
    """The container's time zone (TZ), UTC when unset or unknown."""
    name = (os.environ.get("TZ") or "").strip() or "UTC"
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning("Unknown TZ %r, scheduling in UTC", name)
        return ZoneInfo("UTC")


def _runs_around(schedule: Schedule, now: datetime) -> List[datetime]:
    """The fixed runs from 8 days before `now` to 8 days after, in order."""
    tz = timezone()
    local_now = now.astimezone(tz)
    hour, minute = (int(x) for x in schedule.time.split(":"))
    runs = []
    for offset in range(-8, 9):
        day = (local_now + timedelta(days=offset)).date()
        if DAYS[day.weekday()] in schedule.days:
            runs.append(datetime(day.year, day.month, day.day, hour, minute, tzinfo=tz))
    return runs


def previous_run(schedule: Schedule, now: datetime) -> Optional[datetime]:
    """The latest fixed run at or before `now`."""
    past = [r for r in _runs_around(schedule, now) if r <= now]
    return past[-1] if past else None


def next_run(schedule: Schedule, now: datetime) -> Optional[datetime]:
    """The first fixed run after `now`; None in interval mode."""
    if not schedule.fixed:
        return None
    future = [r for r in _runs_around(schedule, now) if r > now]
    return future[0] if future else None


def due_run(schedule: Schedule, last_done: Optional[datetime], now: datetime) -> Optional[datetime]:
    """
    The fixed run to do now, if any: the latest one, when it hasn't been done
    yet (last_done is before it) and is less than GRACE old. Older ones were
    missed and are skipped.
    """
    run = previous_run(schedule, now)
    if run is None or now - run > GRACE:
        return None
    if last_done is not None and last_done >= run:
        return None
    return run
