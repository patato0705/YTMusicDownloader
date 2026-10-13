# backend/services/charts.py
"""
Chart subscriptions: a country's YouTube Music top artists chart, whose top
N artists are followed in full (re-checked on the scheduler.chart_sync schedule).
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from ..jobs.jobqueue import enqueue_job, pending_jobs
from ..jobs.priorities import Origin
from ..models import ArtistSubscription, ChartSubscription, Job
from ..time_utils import now_utc
from ..ytm_service import adapter as ytm_adapter

logger = logging.getLogger("services.charts")

MAX_TOP_N = 40


def _check_top_n(top_n_artists: int) -> None:
    if not 1 <= top_n_artists <= MAX_TOP_N:
        raise ValueError(f"top_n_artists must be between 1 and {MAX_TOP_N}")


# ============================================================================
# CHART SUBSCRIPTIONS CRUD
# ============================================================================

def get_chart_subscription(session: Session, country_code: str) -> Optional[ChartSubscription]:
    """Get chart subscription by country code."""
    stmt = select(ChartSubscription).where(ChartSubscription.country_code == country_code.upper())
    return session.execute(stmt).scalars().first()


def list_chart_subscriptions(session: Session, include_disabled: bool = False) -> List[ChartSubscription]:
    """The chart subscriptions by country code, the disabled ones only if asked."""
    stmt = select(ChartSubscription).order_by(ChartSubscription.country_code)
    if not include_disabled:
        stmt = stmt.where(ChartSubscription.enabled.is_(True))
    return list(session.execute(stmt).scalars().all())


def create_chart_subscription(
    session: Session,
    country_code: str,
    top_n_artists: int,
    created_by: Optional[int] = None,
) -> ChartSubscription:
    """
    Subscribe to a country's chart. Raises ValueError for a bad country
    code or count, or when it's already followed. Does not commit.
    """
    country_code = country_code.upper().strip()
    if len(country_code) != 2:
        raise ValueError("Country code must be 2 letters")
    _check_top_n(top_n_artists)
    if get_chart_subscription(session, country_code):
        raise ValueError(f"Chart subscription for {country_code} already exists")

    subscription = ChartSubscription(
        country_code=country_code,
        enabled=True,
        top_n_artists=top_n_artists,
        created_at=now_utc(),
        created_by=created_by,
    )
    session.add(subscription)
    session.flush()
    logger.info("Created chart subscription: %s (top %s artists)", country_code, top_n_artists)
    return subscription


def update_chart_subscription(
    session: Session,
    country_code: str,
    top_n_artists: Optional[int] = None,
    enabled: Optional[bool] = None,
) -> ChartSubscription:
    """Change a chart subscription. Raises ValueError if it doesn't exist or for a bad count. Does not commit."""
    subscription = get_chart_subscription(session, country_code)
    if not subscription:
        raise ValueError(f"Chart subscription for {country_code} not found")
    if top_n_artists is not None:
        _check_top_n(top_n_artists)
        subscription.top_n_artists = top_n_artists
    if enabled is not None:
        subscription.enabled = enabled
    session.flush()
    logger.info("Updated chart subscription: %s", country_code)
    return subscription


def delete_chart_subscription(session: Session, country_code: str) -> bool:
    """Unfollow a chart (its artists stay followed). False if it wasn't followed. Does not commit."""
    subscription = get_chart_subscription(session, country_code)
    if not subscription:
        return False
    session.delete(subscription)
    session.flush()
    logger.info("Deleted chart subscription: %s", country_code)
    return True


def get_chart_subscriptions_needing_sync(session: Session, cutoff: datetime) -> List[ChartSubscription]:
    """Enabled subscriptions never synced, or last synced before `cutoff`."""
    stmt = (
        select(ChartSubscription)
        .where(
            ChartSubscription.enabled.is_(True),
            or_(
                ChartSubscription.last_synced_at.is_(None),
                ChartSubscription.last_synced_at < cutoff,
            ),
        )
        .order_by(ChartSubscription.country_code)
    )
    return list(session.execute(stmt).scalars().all())


def enqueue_chart_sync(
    session: Session,
    country_code: str,
    user_id: Optional[int] = None,
) -> Tuple[Job, bool]:
    """
    Queue a sync_chart job for a country, reusing one that is already
    waiting or running. Does not commit. Returns (the job, whether it's new).
    """
    country_code = country_code.upper()
    existing = pending_jobs(session, "sync_chart", country_code=country_code)
    if existing:
        logger.debug("sync_chart job %s already pending for %s", existing[0].id, country_code)
        return existing[0], False

    job = enqueue_job(
        session,
        job_type="sync_chart",
        payload={"country_code": country_code},
        # Even when a user follows the chart or syncs it by hand: it's the
        # whole chart's worth of artists, albums and tracks
        origin=Origin.BULK,
        user_id=user_id,
        commit=False,
    )
    session.flush()
    logger.info("Queued sync_chart job %s for %s", job.id, country_code)
    return job, True


# ============================================================================
# CHART SYNC
# ============================================================================

def get_followed_artist_ids(session: Session) -> set[str]:
    """Artists followed in full (a light subscription only covers an album or two)."""
    stmt = select(ArtistSubscription.artist_id).where(
        ArtistSubscription.enabled.is_(True),
        ArtistSubscription.mode == "full",
    )
    return set(session.execute(stmt).scalars().all())


def sync_chart(session: Session, country_code: str) -> Dict[str, Any]:
    """
    Fetch a followed chart and pick its top N artists not followed in full
    yet. Records the sync (and its error, re-raised, if the fetch fails).
    Commits. Returns {"artists_to_follow": [{"id", "name"}], ...}, or
    {"skipped": True, "reason"} for a disabled or removed subscription.
    """
    country_code = country_code.upper()
    subscription = get_chart_subscription(session, country_code)
    if not subscription:
        return {"skipped": True, "reason": "not followed"}
    if not subscription.enabled:
        return {"skipped": True, "reason": "disabled"}

    try:
        artists = ytm_adapter.get_charts(country_code)["artists"]
    except ytm_adapter.YTMusicUnavailable as e:
        logger.warning("Chart sync failed for %s: %s", country_code, e)
        subscription.last_synced_at = now_utc()
        subscription.last_error = str(e)
        session.commit()
        raise

    top = [a for a in artists[:subscription.top_n_artists] if a.get("id")]
    followed_ids = get_followed_artist_ids(session)
    to_follow = [{"id": a["id"], "name": a.get("name")} for a in top if a["id"] not in followed_ids]

    subscription.last_synced_at = now_utc()
    subscription.last_error = None
    session.commit()

    logger.info(
        "Chart %s: %s new artists to follow, %s already followed",
        country_code, len(to_follow), len(top) - len(to_follow),
    )
    return {
        "country_code": country_code,
        "total_artists": len(artists),
        "top_n": subscription.top_n_artists,
        "artists_to_follow": to_follow,
        "already_followed": len(top) - len(to_follow),
    }
