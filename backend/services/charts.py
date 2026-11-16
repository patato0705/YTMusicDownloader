# backend/services/charts.py
"""
Chart subscriptions: a country's YouTube Music top artists chart, whose top
N artists are followed in full (re-checked on the scheduler.chart_sync schedule).

The follows a chart makes are its own (ArtistSubscription.chart_followed),
and each sync notes which artists its top N lists (ChartSighting). Once an
artist a chart followed has been out of it for the chart's keep_weeks, it's
unfollowed like the Unfollow button does (its files stay), unless:
  - another chart still keeps it: lists it, saw it within its own
    keep_weeks, never unfollows (keep_weeks None), or is disabled (no fresh
    data, so no verdict)
  - someone likes it
  - a followed artists-mode playlist lists it: its follow becomes the
    playlist's (the next rescan would follow it again anyway)
Only a successful sync decides, so a YouTube Music outage doesn't age
artists out. Re-entering the chart follows it again: an unfollow by a chart
isn't an exclusion (services/exclusions.py), an unfollow by someone is.
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta

from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from ..jobs.jobqueue import enqueue_job, pending_jobs
from ..jobs.priorities import Origin
from ..models import (
    Artist, ArtistLike, ArtistSubscription, ChartSighting, ChartSubscription, Job, Playlist, PlaylistEntry,
)
from ..time_utils import ensure_timezone_aware, now_utc
from ..ytm_service import adapter as ytm_adapter
from . import exclusions as exclusions_svc

logger = logging.getLogger("services.charts")

MAX_TOP_N = 40
# Two years: anything longer is as good as never (keep_weeks None)
MAX_KEEP_WEEKS = 104
# Marks "leave keep_weeks as it is" in update_chart_subscription (None means never)
UNCHANGED: Any = object()


def _check_top_n(top_n_artists: int) -> None:
    if not 1 <= top_n_artists <= MAX_TOP_N:
        raise ValueError(f"top_n_artists must be between 1 and {MAX_TOP_N}")


def _check_keep_weeks(keep_weeks: Optional[int]) -> None:
    if keep_weeks is not None and not 1 <= keep_weeks <= MAX_KEEP_WEEKS:
        raise ValueError(f"keep_weeks must be between 1 and {MAX_KEEP_WEEKS}, or none")


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
    keep_weeks: Optional[int] = None,
) -> ChartSubscription:
    """
    Subscribe to a country's chart. Raises ValueError for a bad country
    code, count or keep_weeks, or when it's already followed. Does not commit.
    """
    country_code = country_code.upper().strip()
    if len(country_code) != 2:
        raise ValueError("Country code must be 2 letters")
    _check_top_n(top_n_artists)
    _check_keep_weeks(keep_weeks)
    if get_chart_subscription(session, country_code):
        raise ValueError(f"Chart subscription for {country_code} already exists")

    subscription = ChartSubscription(
        country_code=country_code,
        enabled=True,
        top_n_artists=top_n_artists,
        keep_weeks=keep_weeks,
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
    keep_weeks: Optional[int] = UNCHANGED,
) -> ChartSubscription:
    """
    Change a chart subscription (keep_weeks: None for never, UNCHANGED to
    leave it). Raises ValueError if it doesn't exist or for a bad value.
    Takes effect at its next sync. Does not commit.
    """
    subscription = get_chart_subscription(session, country_code)
    if not subscription:
        raise ValueError(f"Chart subscription for {country_code} not found")
    if top_n_artists is not None:
        _check_top_n(top_n_artists)
        subscription.top_n_artists = top_n_artists
    if keep_weeks is not UNCHANGED:
        _check_keep_weeks(keep_weeks)
        subscription.keep_weeks = keep_weeks
    if enabled is not None:
        subscription.enabled = enabled
    session.flush()
    logger.info("Updated chart subscription: %s", country_code)
    return subscription


def delete_chart_subscription(session: Session, country_code: str) -> bool:
    """
    Unfollow a chart. Its artists stay followed: those no other chart has
    listed become ordinary follows, which no chart unfollows. Its sightings
    go with it (ON DELETE CASCADE). False if it wasn't followed. Does not commit.
    """
    subscription = get_chart_subscription(session, country_code.upper())
    if not subscription:
        return False
    elsewhere = select(ChartSighting.artist_id).where(ChartSighting.country_code != subscription.country_code)
    here = select(ChartSighting.artist_id).where(ChartSighting.country_code == subscription.country_code)
    for sub in session.scalars(select(ArtistSubscription).where(
        ArtistSubscription.chart_followed.is_(True),
        ArtistSubscription.artist_id.in_(here),
        ArtistSubscription.artist_id.not_in(elsewhere),
    )):
        sub.chart_followed = False
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
    _note_sightings(session, country_code, {a["id"] for a in top})
    followed_ids = get_followed_artist_ids(session)
    # Unfollowed or deleted from the library: not followed again
    # (services/exclusions.py)
    excluded_ids = exclusions_svc.excluded_artist_ids(session)
    to_follow = [
        {"id": a["id"], "name": a.get("name")}
        for a in top if a["id"] not in followed_ids and a["id"] not in excluded_ids
    ]
    excluded = sum(1 for a in top if a["id"] in excluded_ids and a["id"] not in followed_ids)

    subscription.last_synced_at = now_utc()
    subscription.last_error = None
    session.commit()

    logger.info(
        "Chart %s: %s new artists to follow, %s already followed, %s excluded",
        country_code, len(to_follow), len(top) - len(to_follow) - excluded, excluded,
    )
    return {
        "country_code": country_code,
        "total_artists": len(artists),
        "top_n": subscription.top_n_artists,
        "artists_to_follow": to_follow,
        "already_followed": len(top) - len(to_follow) - excluded,
        "excluded": excluded,
        "top_ids": [a["id"] for a in top],
    }


def _note_sightings(session: Session, country_code: str, artist_ids: set[str]) -> None:
    """The chart lists these artists in its top N now. Does not commit."""
    now = now_utc()
    known = {
        s.artist_id: s for s in session.scalars(
            select(ChartSighting).where(ChartSighting.country_code == country_code, ChartSighting.artist_id.in_(artist_ids))
        )
    }
    for artist_id in artist_ids:
        sighting = known.get(artist_id)
        if sighting is None:
            session.add(ChartSighting(country_code=country_code, artist_id=artist_id, last_seen_at=now))
        else:
            sighting.last_seen_at = now


def _keeps(chart: ChartSubscription, last_seen_at: datetime, now: datetime) -> bool:
    """Whether a chart that once listed an artist still keeps it followed."""
    if not chart.enabled or chart.keep_weeks is None:
        return True
    return ensure_timezone_aware(last_seen_at) >= now - timedelta(weeks=chart.keep_weeks)


def unfollow_dropped_artists(session: Session, country_code: str, top_ids: List[str]) -> List[Dict[str, str]]:
    """
    After a successful sync of this chart: unfollow the artists the charts
    followed that it no longer lists, once no chart keeps them (see the top
    of this file). Commits. Returns them, as [{"id", "name"}].
    """
    from . import subscriptions as subs_svc

    country_code = country_code.upper()
    now = now_utc()
    candidates = session.scalars(
        select(ArtistSubscription)
        .join(ChartSighting, ChartSighting.artist_id == ArtistSubscription.artist_id)
        .where(
            ChartSighting.country_code == country_code,
            ChartSighting.artist_id.not_in(top_ids),
            ArtistSubscription.chart_followed.is_(True),
            ArtistSubscription.mode == "full",
        )
    ).all()
    if not candidates:
        return []

    ids = [sub.artist_id for sub in candidates]
    charts = {c.country_code: c for c in session.scalars(select(ChartSubscription))}
    sightings: Dict[str, List[ChartSighting]] = {}
    for s in session.scalars(select(ChartSighting).where(ChartSighting.artist_id.in_(ids))):
        sightings.setdefault(s.artist_id, []).append(s)
    liked = set(session.scalars(select(ArtistLike.artist_id).where(ArtistLike.artist_id.in_(ids))))
    in_playlists = set(session.scalars(
        select(PlaylistEntry.artist_id)
        .join(Playlist, Playlist.id == PlaylistEntry.playlist_id)
        .where(Playlist.followed.is_(True), Playlist.mode == "artists", PlaylistEntry.artist_id.in_(ids))
    ))

    unfollowed = []
    for sub in candidates:
        artist_id = sub.artist_id
        if any(_keeps(charts[s.country_code], s.last_seen_at, now) for s in sightings.get(artist_id, []) if s.country_code in charts):
            continue
        if artist_id in liked:
            continue
        if artist_id in in_playlists:
            sub.chart_followed = False
            logger.info("Artist %s left chart %s, but an artists-mode playlist follows it now", artist_id, country_code)
            continue
        subs_svc.downgrade_all_albums_to_metadata(session, artist_id)
        sub.mode = "light"
        sub.chart_followed = False
        artist = session.get(Artist, artist_id)
        unfollowed.append({"id": artist_id, "name": artist.name if artist else ""})
        logger.info("Artist %s (%s) unfollowed: out of chart %s for too long", artist_id, artist.name if artist else "", country_code)
    session.commit()
    return unfollowed
