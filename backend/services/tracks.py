# backend/services/tracks.py
"""
Track entity CRUD operations and track-specific business logic.

Track.status is one of:
- "available":   known, nothing planned (metadata-only album, cancelled job)
- "queued":      a download_track job is waiting for it (incl. retry backoff
                 and rate-limit pauses; last_error says why it's retrying)
- "downloading": a worker is on it
- "done":        on disk
- "failed":      its download job ran out of attempts

"queued" must always mean a live job exists: whatever creates, requeues or
drops a download_track job updates its track in the same transaction
(queue_track_downloads here, and the helpers in jobs/jobqueue.py).
"""
from __future__ import annotations
import logging
from typing import Any, Dict, Iterable, List, Optional, Set

from sqlalchemy.orm import Session

from ..jobs.jobqueue import enqueue_job, pending_jobs
from ..jobs.priorities import Origin, promote
from ..models import Track

logger = logging.getLogger("services.tracks")


# ============================================================================
# TRACK CRUD
# ============================================================================

def upsert_track(
    session: Session,
    track_id: str,
    title: str,
    track_number: Optional[int],
    duration_seconds: Optional[int],
    artists_list: Optional[List[Dict[str, Optional[str]]]] = None,
    album_id: Optional[str] = None,
    status: Optional[str] = "available",
    file_path: Optional[str] = None,
    artist_valid: bool = True,
    lyrics: Optional[str] = None,
    lyrics_local: Optional[str] = None,
) -> Track:
    """
    Create or update a Track row. `artists_list` is a list of dicts {id, name}.
    Fields passed as None are left untouched on an existing row (a new row
    with status=None starts "available"). Does not commit.
    """
    if not track_id:
        raise ValueError("track_id required")

    track = session.get(Track, track_id)
    if track is None:
        track = Track(id=track_id, title=title or "", status=status or "available")
        session.add(track)
    elif title is not None:
        track.title = title
    for field, value in (
        ("duration", duration_seconds),
        ("artists", artists_list),
        ("album_id", album_id),
        ("track_number", track_number),
        ("file_path", file_path),
        ("status", status),
        ("lyrics", lyrics),
        ("lyrics_local", lyrics_local),
    ):
        if value is not None:
            setattr(track, field, value)
    track.artist_valid = bool(artist_valid)
    return track


# yt-dlp messages can run for pages; keep enough for debugging, not the whole trace.
MAX_ERROR_LENGTH = 2000


def truncate_error(error: Optional[Any]) -> Optional[str]:
    if not error:
        return None
    text = str(error).strip()
    return text[:MAX_ERROR_LENGTH] if text else None


# ============================================================================
# DOWNLOAD QUEUEING
# ============================================================================

# A track on disk or in a worker's hands never gets another job
_NOT_QUEUEABLE = ("done", "downloading")


def active_download_track_ids(session: Session) -> Set[str]:
    """Tracks that already have a download_track job waiting or running."""
    return {str(job.payload.get("track_id")) for job in pending_jobs(session, "download_track")}


def queue_track_downloads(
    session: Session,
    tracks: Iterable[Track],
    user_id: Optional[int] = None,
    *,
    origin: Origin,
) -> int:
    """
    Queue a download_track job for each track that needs one, mark it
    "queued" and roll the affected albums up. Does not commit: the job and
    the status have to land in the same transaction.

    Tracks on disk, being downloaded, or already waiting on a job are
    skipped, so this is safe to call on a whole album any number of times.
    A waiting job is moved up to `origin`'s class if that's higher (see
    jobs/priorities.py): a user downloading an album a chart already queued
    shouldn't wait behind the rest of the chart.

    Returns the number of jobs queued.
    """
    from . import subscriptions as subs_svc

    tracks = list(tracks)
    active = active_download_track_ids(session)
    waiting = {t.id for t in tracks if t.id in active}
    if waiting:
        for job in pending_jobs(session, "download_track", statuses=("queued",), track_id=waiting):
            promote(job, origin)
    albums: Set[str] = set()
    queued = 0

    for track in tracks:
        if track.status in _NOT_QUEUEABLE or track.id in active:
            continue
        enqueue_job(
            session,
            job_type="download_track",
            payload={"track_id": track.id},
            origin=origin,
            user_id=user_id,
            commit=False,
        )
        track.status = "queued"
        track.last_error = None
        active.add(track.id)
        queued += 1
        if track.album_id:
            albums.add(track.album_id)

    if albums:
        session.flush()  # autoflush=False: the rollup has to see the new statuses
        for album_id in albums:
            subs_svc.check_and_update_album_download_status(session, album_id)

    return queued


def queue_album_downloads(
    session: Session,
    album_id: str,
    user_id: Optional[int] = None,
    *,
    origin: Origin,
) -> int:
    """queue_track_downloads() for every track of an album. Does not commit."""
    tracks = session.query(Track).filter(Track.album_id == album_id).all()
    return queue_track_downloads(session, tracks, user_id=user_id, origin=origin)
