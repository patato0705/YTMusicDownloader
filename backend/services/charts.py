# backend/services/charts.py
"""
Charts service - handles chart subscriptions and sync operations.
"""
from __future__ import annotations
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ChartSubscription, ChartSnapshot, Artist
from ..ytm_service import adapter as ytm_adapter
from ..time_utils import now_utc

logger = logging.getLogger("services.charts")


# ============================================================================
# CHART SUBSCRIPTIONS CRUD
# ============================================================================

def get_chart_subscription(session: Session, country_code: str) -> Optional[ChartSubscription]:
    """Get chart subscription by country code."""
    stmt = select(ChartSubscription).where(ChartSubscription.country_code == country_code.upper())
    return session.execute(stmt).scalars().first()


def list_chart_subscriptions(
    session: Session,
    include_disabled: bool = False
) -> List[ChartSubscription]:
    """List all chart subscriptions."""
    stmt = select(ChartSubscription)
    
    if not include_disabled:
        stmt = stmt.where(ChartSubscription.enabled == True)
    
    stmt = stmt.order_by(ChartSubscription.country_code)
    
    return list(session.execute(stmt).scalars().all())


def create_chart_subscription(
    session: Session,
    country_code: str,
    top_n_artists: int,
    created_by: Optional[int] = None,
) -> ChartSubscription:
    """
    Create a chart subscription.
    
    Args:
        session: SQLAlchemy session
        country_code: 2-letter country code (e.g., "US", "FR")
        top_n_artists: Number of top artists to follow (1-40)
        created_by: User ID who created the subscription
    
    Returns:
        Created ChartSubscription instance
    
    Raises:
        ValueError: If subscription already exists or invalid parameters
    """
    country_code = country_code.upper().strip()
    
    if len(country_code) != 2:
        raise ValueError("Country code must be 2 letters")
    
    if not 1 <= top_n_artists <= 40:
        raise ValueError("top_n_artists must be between 1 and 40")
    
    # Check if already exists
    existing = get_chart_subscription(session, country_code)
    if existing:
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
    
    logger.info(f"Created chart subscription: {country_code} (top {top_n_artists} artists)")
    return subscription


def update_chart_subscription(
    session: Session,
    country_code: str,
    top_n_artists: Optional[int] = None,
    enabled: Optional[bool] = None,
) -> ChartSubscription:
    """
    Update chart subscription settings.
    
    Returns:
        Updated ChartSubscription instance
    
    Raises:
        ValueError: If subscription not found or invalid parameters
    """
    subscription = get_chart_subscription(session, country_code)
    if not subscription:
        raise ValueError(f"Chart subscription for {country_code} not found")
    
    old_top_n = subscription.top_n_artists
    
    if top_n_artists is not None:
        if not 1 <= top_n_artists <= 40:
            raise ValueError("top_n_artists must be between 1 and 40")
        subscription.top_n_artists = top_n_artists
    
    if enabled is not None:
        subscription.enabled = enabled
    
    session.add(subscription)
    session.flush()
    
    logger.info(f"Updated chart subscription: {country_code}")
    
    # Return both the subscription and whether top_n increased
    return subscription


def delete_chart_subscription(session: Session, country_code: str) -> bool:
    """
    Delete a chart subscription.
    
    Returns:
        True if deleted, False if not found
    """
    subscription = get_chart_subscription(session, country_code)
    if not subscription:
        return False
    
    session.delete(subscription)
    session.flush()
    
    logger.info(f"Deleted chart subscription: {country_code}")
    return True


def update_sync_status(
    session: Session,
    country_code: str,
    success: bool = True,
    error: Optional[str] = None,
) -> None:
    """Update chart subscription sync status."""
    subscription = get_chart_subscription(session, country_code)
    if not subscription:
        return
    
    subscription.last_synced_at = now_utc()
    subscription.last_error = error if not success else None
    
    session.add(subscription)


# ============================================================================
# CHART DATA
# ============================================================================

def fetch_chart(session: Session, country_code: str) -> Dict[str, Any]:
    """
    Fetch chart data from YTMusic.
    
    Returns:
        Dict with "artists" list
    """
    country_code = country_code.upper().strip()
    
    try:
        chart_data = ytm_adapter.get_charts(country=country_code)
        return chart_data
    except Exception as e:
        logger.exception(f"Failed to fetch chart for {country_code}")
        raise RuntimeError(f"Failed to fetch chart: {e}")


def save_chart_snapshot(
    session: Session,
    country_code: str,
    chart_data: Dict[str, Any],
) -> ChartSnapshot:
    """
    Save a chart snapshot to database.
    
    Args:
        session: SQLAlchemy session
        country_code: Country code
        chart_data: Chart data from adapter
    
    Returns:
        Created ChartSnapshot instance
    """
    snapshot = ChartSnapshot(
        country_code=country_code.upper(),
        snapshot_date=now_utc(),
        data=chart_data,
    )
    
    session.add(snapshot)
    session.flush()
    
    logger.info(f"Saved chart snapshot for {country_code}")
    return snapshot


def get_latest_snapshot(
    session: Session,
    country_code: str
) -> Optional[ChartSnapshot]:
    """Get the most recent chart snapshot for a country."""
    stmt = (
        select(ChartSnapshot)
        .where(ChartSnapshot.country_code == country_code.upper())
        .order_by(ChartSnapshot.snapshot_date.desc())
        .limit(1)
    )
    return session.execute(stmt).scalars().first()


# ============================================================================
# CHART SYNC
# ============================================================================

def get_followed_artist_ids(session: Session) -> set[str]:
    """Get set of all followed artist IDs."""
    stmt = select(Artist.id).where(Artist.followed == True)
    results = session.execute(stmt).scalars().all()
    return set(results)


def sync_chart(
    session: Session,
    country_code: str,
) -> Dict[str, Any]:
    """
    Sync a chart: fetch latest data and follow top N artists.
    
    This is called by the sync_chart job worker.
    
    Args:
        session: SQLAlchemy session
        country_code: Country code to sync
    
    Returns:
        Dict with sync results
    """
    country_code = country_code.upper()
    
    # Get subscription
    subscription = get_chart_subscription(session, country_code)
    if not subscription:
        raise ValueError(f"No chart subscription for {country_code}")
    
    if not subscription.enabled:
        logger.info(f"Chart subscription for {country_code} is disabled, skipping sync")
        return {"skipped": True, "reason": "disabled"}
    
    try:
        # Fetch chart data
        chart_data = fetch_chart(session, country_code)
        artists = chart_data.get("artists", [])
        
        # Save snapshot
        save_chart_snapshot(session, country_code, chart_data)
        
        # Get top N artists to follow
        top_n = subscription.top_n_artists
        artists_to_follow = artists[:top_n]
        
        logger.info(f"Syncing chart {country_code}: {len(artists_to_follow)} artists to follow")
        
        # Get currently followed artists
        followed_ids = get_followed_artist_ids(session)
        
        # Collect artist IDs to follow
        artist_ids_to_follow = []
        for artist in artists_to_follow:
            artist_id = artist.get("id")
            if artist_id and artist_id not in followed_ids:
                artist_ids_to_follow.append(artist_id)
        
        # Update sync status
        update_sync_status(session, country_code, success=True)
        session.commit()
        
        logger.info(
            f"Chart sync complete for {country_code}: "
            f"{len(artist_ids_to_follow)} new artists to follow, "
            f"{len(artists_to_follow) - len(artist_ids_to_follow)} already followed"
        )
        
        return {
            "country_code": country_code,
            "total_artists": len(artists),
            "top_n": top_n,
            "artists_to_follow": artist_ids_to_follow,
            "already_followed": len(artists_to_follow) - len(artist_ids_to_follow),
        }
        
    except Exception as e:
        logger.exception(f"Chart sync failed for {country_code}")
        update_sync_status(session, country_code, success=False, error=str(e))
        session.commit()
        raise