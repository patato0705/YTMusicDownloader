# backend/routers/charts.py
"""
Charts endpoints.

Endpoints:
- GET /api/charts/{country_code} - Get chart for a country
- POST /api/charts/{country_code}/follow - Follow a chart (admin only)
- DELETE /api/charts/{country_code}/follow - Unfollow a chart (admin only)
- PATCH /api/charts/{country_code} - Update chart subscription (admin only)
- POST /api/charts/{country_code}/sync - Queue a sync now (admin only)
- GET /api/charts - List all chart subscriptions
"""
from __future__ import annotations
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, Path, Body
from sqlalchemy.orm import Session

from ..db import get_session
from ..dependencies import require_auth, require_admin, require_charts_enabled
from ..models import User
from ..schemas import MessageResponse
from ..schemas.charts import (
    FollowChartRequest,
    UpdateChartRequest,
    ChartResponse,
    ChartArtist,
    ChartSubscriptionResponse,
)
from ..services import charts as charts_svc
from ..ytm_service import adapter as ytm_adapter
from .albums import ytmusic_unavailable

logger = logging.getLogger("routers.charts")

# Every chart endpoint (admin ones included) is switched off by the
# `features.charts_enabled` setting.
router = APIRouter(
    prefix="/api/charts",
    tags=["Charts"],
    dependencies=[Depends(require_charts_enabled)],
)


# ============================================================================
# ENDPOINTS FOR EVERY SIGNED-IN USER
# ============================================================================

@router.get("/{country_code}", response_model=ChartResponse)
def get_chart(
    country_code: str = Path(..., min_length=2, max_length=2, description="2-letter country code (e.g., US, FR)"),
    current_user: User = Depends(require_auth),
    session: Session = Depends(get_session),
) -> ChartResponse:
    """
    A country's top artists chart, each marked when followed in full, and
    whether the chart itself is followed.
    """
    country_code = country_code.upper()
    try:
        chart = ytm_adapter.get_charts(country_code)
    except ytm_adapter.YTMusicUnavailable:
        raise ytmusic_unavailable()

    followed_ids = charts_svc.get_followed_artist_ids(session)
    subscription = charts_svc.get_chart_subscription(session, country_code)
    return ChartResponse(
        country_code=country_code,
        artists=[ChartArtist(**artist, followed=artist["id"] in followed_ids) for artist in chart["artists"]],
        followed=subscription is not None,
        subscription=ChartSubscriptionResponse.model_validate(subscription) if subscription else None,
    )


@router.get("", response_model=List[ChartSubscriptionResponse])
def list_chart_subscriptions(
    include_disabled: bool = False,
    current_user: User = Depends(require_auth),
    session: Session = Depends(get_session),
) -> List[ChartSubscriptionResponse]:
    """
    List all chart subscriptions.

    Args:
        include_disabled: Include disabled subscriptions
    """
    subscriptions = charts_svc.list_chart_subscriptions(
        session=session,
        include_disabled=include_disabled,
    )

    return [ChartSubscriptionResponse.model_validate(sub) for sub in subscriptions]


# ============================================================================
# ADMIN ENDPOINTS
# ============================================================================


@router.post("/{country_code}/follow", response_model=ChartSubscriptionResponse, status_code=status.HTTP_201_CREATED)
def follow_chart(
    country_code: str = Path(..., min_length=2, max_length=2, description="2-letter country code"),
    data: FollowChartRequest = FollowChartRequest(),
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> ChartSubscriptionResponse:
    """
    Follow a chart (admin only).

    Creates a subscription and immediately queues a sync_chart job
    to follow the top N artists.
    """
    country_code = country_code.upper()

    try:
        # Create subscription
        subscription = charts_svc.create_chart_subscription(
            session=session,
            country_code=country_code,
            top_n_artists=data.top_n_artists,
            created_by=current_user.id,
        )

        session.commit()

        logger.info("Chart %s followed by user %s", country_code, current_user.username)

        # Queue sync job; the subscription is already saved, so a queueing
        # failure must not fail the request.
        try:
            charts_svc.enqueue_chart_sync(session, country_code, user_id=current_user.id)
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("Failed to queue sync_chart job for %s", country_code)

        return ChartSubscriptionResponse.model_validate(subscription)

    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        session.rollback()
        logger.exception("Failed to follow chart %s", country_code)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to follow chart: {str(e)}",
        )


@router.delete("/{country_code}/follow", response_model=MessageResponse)
def unfollow_chart(
    country_code: str = Path(..., min_length=2, max_length=2, description="2-letter country code"),
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> MessageResponse:
    """
    Unfollow a chart (admin only).

    Removes the chart subscription but keeps followed artists.
    """
    country_code = country_code.upper()

    try:
        success = charts_svc.delete_chart_subscription(session, country_code)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chart subscription for {country_code} not found",
            )

        session.commit()

        logger.info("Chart %s unfollowed by user %s", country_code, current_user.username)

        return MessageResponse(
            message=f"Chart {country_code} unfollowed successfully. Artists remain followed."
        )

    except HTTPException:
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        logger.exception("Failed to unfollow chart %s", country_code)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to unfollow chart: {str(e)}",
        )


@router.patch("/{country_code}", response_model=ChartSubscriptionResponse)
def update_chart(
    country_code: str = Path(..., min_length=2, max_length=2, description="2-letter country code"),
    data: UpdateChartRequest = Body(...),
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> ChartSubscriptionResponse:
    """
    Update chart subscription settings (admin only).

    If top_n_artists is increased, a sync job is queued to follow additional artists.
    """
    country_code = country_code.upper()

    if data.top_n_artists is None and data.enabled is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one field must be provided",
        )

    try:
        # Get current subscription to check if top_n is increasing
        old_subscription = charts_svc.get_chart_subscription(session, country_code)
        if not old_subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chart subscription for {country_code} not found",
            )

        old_top_n = old_subscription.top_n_artists

        # Update subscription
        subscription = charts_svc.update_chart_subscription(
            session=session,
            country_code=country_code,
            top_n_artists=data.top_n_artists,
            enabled=data.enabled,
        )

        session.commit()

        # If top_n increased, queue a sync job so the extra artists get followed
        new_top_n = subscription.top_n_artists
        if subscription.enabled and new_top_n > old_top_n:
            logger.info("Chart %s top_n increased from %s to %s, queueing sync", country_code, old_top_n, new_top_n)
            try:
                charts_svc.enqueue_chart_sync(session, country_code, user_id=current_user.id)
                session.commit()
            except Exception:
                session.rollback()
                logger.exception("Failed to queue sync_chart job for %s", country_code)

        logger.info("Chart %s updated by user %s", country_code, current_user.username)

        return ChartSubscriptionResponse.model_validate(subscription)

    except HTTPException:
        session.rollback()
        raise
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        session.rollback()
        logger.exception("Failed to update chart %s", country_code)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update chart: {str(e)}",
        )


@router.post("/{country_code}/sync", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED)
def sync_chart_now(
    country_code: str = Path(..., min_length=2, max_length=2, description="2-letter country code"),
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> MessageResponse:
    """
    Queue a sync of a followed chart right away (admin only).

    The sync fetches the current chart and follows any of the top N artists
    that are not followed yet. A sync already waiting in the queue is reused.
    """
    country_code = country_code.upper()

    subscription = charts_svc.get_chart_subscription(session, country_code)
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chart subscription for {country_code} not found",
        )
    if not subscription.enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Chart {country_code} is disabled; enable it before syncing",
        )

    try:
        job, _ = charts_svc.enqueue_chart_sync(session, country_code, user_id=current_user.id)
        session.commit()
    except Exception as e:
        session.rollback()
        logger.exception("Failed to queue sync_chart job for %s", country_code)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to queue chart sync: {str(e)}",
        )

    logger.info("Chart %s sync requested by user %s (job %s)", country_code, current_user.username, job.id)
    return MessageResponse(message=f"Chart {country_code} sync queued (job {job.id})")
