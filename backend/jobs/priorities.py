# backend/jobs/priorities.py
"""
Job priorities: where a job came from decides how soon it runs.

Every job has one of three origins, and every job it queues in turn inherits
it (carried in the payload as "origin"), so a whole chain -- artist sync ->
album imports -> track downloads -> lyrics -- runs at the priority of
whatever started it:

- USER: something a person asked for (follow, download, retry, mode change).
- AUTO: routine upkeep of what's already followed (scheduled syncs picking up
  new releases, lyrics retries, requeued abandoned downloads).
- BULK: large batches nobody is waiting on track by track (charts, backup
  restore).

A higher class always goes first: a chart's thousands of downloads wait
while anything a user asked for is queued. Within a class, later steps of a
chain go first (_STAGE): an artist's album imports run before the next
artist's sync, so each artist completes -- and its downloads can start --
before the next one begins, and the queue never holds more than one
artist's imports. Ties go to the oldest job (jobqueue.reserve_job).
"""
from __future__ import annotations
from enum import Enum
from typing import Any


class Origin(str, Enum):
    USER = "user"
    AUTO = "auto"
    BULK = "bulk"


# Retries lower a job's priority by its attempt count (jobqueue.mark_job_failed),
# at most 1+2+3+4 = 10 with the default 5 attempts: far less than the gap
# between classes, so a retried job never drops into the class below.
_BASE = {Origin.BULK: 100, Origin.AUTO: 200, Origin.USER: 300}
_RANK = {Origin.BULK: 0, Origin.AUTO: 1, Origin.USER: 2}

# Only the metadata job types share a queue in which order between steps
# matters; download and lyrics jobs each have their own workers.
_STAGE = {"sync_chart": 0, "sync_playlist": 0, "sync_artist": 1, "import_album": 2}


def priority_for(job_type: str, origin: Origin) -> int:
    """The priority a new job of this type and origin is queued at."""
    return _BASE[Origin(origin)] + _STAGE.get(job_type, 0)


def job_origin(payload: dict[str, Any]) -> Origin:
    """The origin recorded in a job's payload (always set by enqueue_job)."""
    return Origin(payload["origin"])


def promote(job: Any, origin: Origin) -> bool:
    """
    Move a still-waiting job up to `origin`'s class -- never down. Used when
    a request meets work that's already queued: the existing job is reused
    rather than duplicated, so it has to take on the newcomer's urgency.
    The payload's origin changes too, so the jobs it queues inherit the new
    class. Does not commit. Returns whether the job changed.
    """
    origin = Origin(origin)
    if job.status != "queued" or _RANK[job_origin(job.payload)] >= _RANK[origin]:
        return False
    job.priority = priority_for(job.type, origin)
    # Reassigned, not mutated: the JSON column only notices a new value
    job.payload = {**(job.payload or {}), "origin": origin.value}
    return True
