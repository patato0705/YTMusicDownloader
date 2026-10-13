# backend/routers/jobs.py
"""
Job endpoints.

Endpoints:
- GET /api/jobs/stats/summary - The queue's activity (the navbar badge, live page refreshes)
"""
from __future__ import annotations
from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from .. import config
from ..db import get_session
from ..dependencies import require_auth
from ..jobs import gate
from ..models import Job, User
from ..time_utils import now_utc

router = APIRouter(prefix="/api/jobs", tags=["Jobs"])


@router.get("/stats/summary")
def get_job_stats(
    current_user: User = Depends(require_auth),
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """
    Job counts of the whole queue, the same for every user: the library is
    shared, so everyone sees the downloads it's waiting on.
    """
    now = now_utc()
    stats: Dict[str, int] = dict(session.query(Job.status, func.count(Job.id)).group_by(Job.status).all())

    # Of the "queued" jobs, how many are actually sitting in a retry
    # backoff (scheduled_at in the future) rather than eligible to run
    # right now. Callers like the navbar's "active jobs" indicator need
    # this to avoid counting a job waiting out a multi-hour backoff as
    # "in progress".
    stats["pending_scheduled"] = session.query(func.count(Job.id)).filter(
        Job.status == "queued", Job.scheduled_at > now,
    ).scalar() or 0

    # Breakdown of the in-flight work by job type. The count above lumps
    # everything together, so a finished album can still show a non-zero
    # badge while its per-track lyrics jobs drain -- callers use this to
    # say what those jobs actually are.
    active_by_type = dict(
        session.query(Job.type, func.count(Job.id))
        .filter(
            or_(
                Job.status == "reserved",
                and_(Job.status == "queued", or_(Job.scheduled_at.is_(None), Job.scheduled_at <= now)),
            )
        )
        .group_by(Job.type)
        .all()
    )

    # Download throttle state (jobs.gate): how many download workers are
    # active and whether a rate-limit pause is in force.
    paused_until = gate.downloads_paused_until(session)
    return {
        "downloads": {
            "active_workers": gate.active_download_slots(session),
            "max_workers": config.DOWNLOAD_WORKERS,
            "paused_until": paused_until.isoformat() if paused_until else None,
        },
        "stats": stats,
        "active_by_type": active_by_type,
    }
