# backend/routers/charts.py
"""
Charts endpoints.

Endpoints:
- GET /api/charts/{country_code} - Get chart for a country
- POST /api/charts/{country_code}/follow - Follow a chart (admin only)
- DELETE /api/charts/{country_code}/follow - Unfollow a chart (admin only)
- PATCH /api/charts/{country_code} - Update chart subscription (admin only)
- GET /api/charts - List all chart subscriptions
"""
from __future__ import annotations
import logging
from typing import Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, status, Path, Body
from sqlalchemy.orm import Session

from backend.db import get_session
from backend.dependencies import require_auth, require_admin
from backend.services import charts as charts_svc
from backend.jobs.jobqueue import enqueue_job
from backend.schemas.charts import (
    FollowChartRequest,
    UpdateChartRequest,
    ChartResponse,
    ChartArtist,
    ChartSubscriptionResponse,
)
from backend.schemas import MessageResponse
from backend.models import User, Artist

logger = logging.getLogger("routers.charts")

router = APIRouter(prefix="/api/charts", tags=["Charts"])


# ============================================================================
# PUBLIC ENDPOINTS (require auth)
# ============================================================================

@router.get("/{country_code}", response_model=ChartResponse)
def get_chart(
    country_code: str = Path(..., min_length=2, max_length=2, description="2-letter country code (e.g., US, FR)"),
    current_user: User = Depends(require_auth),
    session: Session = Depends(get_session),
) -> ChartResponse:
    """
    Get music chart for a country.
    
    Returns top artists with their current rankings.
    Also returns whether this chart is currently being followed.
    """
    country_code = country_code.upper()
    
    try:
        # Fetch chart data
        chart_data = charts_svc.fetch_chart(session, country_code)
        artists_data = chart_data.get("artists", [])
        
        # Get followed artist IDs
        followed_ids = charts_svc.get_followed_artist_ids(session)
        
        # Build artist list with follow status
        artists = []
        for artist_data in artists_data:
            artist_id = artist_data.get("id")
            artists.append(ChartArtist(
                id=artist_id,
                name=artist_data.get("name"),
                thumbnails=artist_data.get("thumbnails", []),
                rank=artist_data.get("rank"),
                trend=artist_data.get("trend"),
                followed=artist_id in followed_ids if artist_id else False,
            ))
        
        # Check if chart is followed
        subscription = charts_svc.get_chart_subscription(session, country_code)
        
        return ChartResponse(
            country_code=country_code,
            artists=artists,
            followed=subscription is not None,
            subscription=ChartSubscriptionResponse.model_validate(subscription) if subscription else None,
            cached=False,
        )
        
    except Exception as e:
        logger.exception(f"Failed to get chart for {country_code}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to fetch chart: {str(e)}",
        )


@router.get("", response_model=List[ChartSubscriptionResponse])
def list_chart_subscriptions(
    include_disabled: bool = False,
    current_user: User = Depends(require_auth),
    session: Session = Depends(get_session),
) -> List[ChartSubscriptionResponse]:
    """
    List all chart subscriptions (admin only).
    
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
        
        logger.info(f"Chart {country_code} followed by user {current_user.username}")
        
        # Queue sync job
        try:
            job = enqueue_job(
                session,
                job_type="sync_chart",
                payload={"country_code": country_code},
                priority=20,
                user_id=current_user.id,
            )
            session.commit()
            logger.info(f"Queued sync_chart job {job.id} for {country_code}")
        except Exception as e:
            logger.exception(f"Failed to queue sync_chart job for {country_code}")
            # Don't fail the request if job queueing fails
        
        return ChartSubscriptionResponse.model_validate(subscription)
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        session.rollback()
        logger.exception(f"Failed to follow chart {country_code}")
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
        
        logger.info(f"Chart {country_code} unfollowed by user {current_user.username}")
        
        return MessageResponse(
            message=f"Chart {country_code} unfollowed successfully. Artists remain followed."
        )
        
    except HTTPException:
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        logger.exception(f"Failed to unfollow chart {country_code}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to unfollow chart: {str(e)}",
        )


@router.patch("/{country_code}", response_model=ChartSubscriptionResponse)
def update_chart(
    country_code: str = Path(..., min_length=2, max_length=2, description="2-letter country code"),
    data: UpdateChartRequest = Body(...),  # This tells FastAPI "required body parameter"
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
        
        # If top_n increased, queue a sync job
        new_top_n = subscription.top_n_artists
        if data.top_n_artists is not None and new_top_n > old_top_n:
            logger.info(f"Chart {country_code} top_n increased from {old_top_n} to {new_top_n}, queueing sync")
            try:
                job = enqueue_job(
                    session,
                    job_type="sync_chart",
                    payload={"country_code": country_code},
                    priority=20,
                    user_id=current_user.id,
                )
                session.commit()
                logger.info(f"Queued sync_chart job {job.id} for {country_code}")
            except Exception as e:
                logger.exception(f"Failed to queue sync_chart job for {country_code}")
        
        logger.info(f"Chart {country_code} updated by user {current_user.username}")
        
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
        logger.exception(f"Failed to update chart {country_code}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update chart: {str(e)}",
        )