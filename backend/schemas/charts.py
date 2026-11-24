# backend/schemas/charts.py
"""
Pydantic schemas for charts endpoints.
"""
from __future__ import annotations
from typing import Optional, List
from datetime import datetime

from pydantic import BaseModel, Field


# ============================================================================
# REQUEST SCHEMAS
# ============================================================================

_KEEP_WEEKS = "Weeks out of the chart after which the artists it followed are unfollowed (1-104); null: never"


class FollowChartRequest(BaseModel):
    """Request to follow a chart"""
    top_n_artists: int = Field(default=40, ge=1, le=40, description="Number of top artists to auto-follow (1-40)")
    keep_weeks: Optional[int] = Field(None, ge=1, le=104, description=_KEEP_WEEKS)


class UpdateChartRequest(BaseModel):
    """Request to update chart subscription settings"""
    top_n_artists: Optional[int] = Field(None, ge=1, le=40, description="Number of top artists to auto-follow (1-40)")
    enabled: Optional[bool] = Field(None, description="Enable/disable chart sync")
    # Left out: unchanged; null: never (see model_fields_set)
    keep_weeks: Optional[int] = Field(None, ge=1, le=104, description=_KEEP_WEEKS)


# ============================================================================
# RESPONSE SCHEMAS
# ============================================================================

class ChartArtist(BaseModel):
    """Artist in a chart"""
    id: str
    name: Optional[str] = None
    thumbnail: Optional[str] = None
    rank: Optional[int] = None
    trend: Optional[str] = None  # "up", "down" or "neutral"
    followed: bool = False  # Whether this artist is already followed

    model_config = {"from_attributes": True}


class ChartSubscriptionResponse(BaseModel):
    """Chart subscription details"""
    id: int
    country_code: str
    enabled: bool
    top_n_artists: int
    keep_weeks: Optional[int] = None
    created_at: datetime
    created_by: Optional[int] = None
    last_synced_at: Optional[datetime] = None
    last_error: Optional[str] = None

    model_config = {"from_attributes": True}


class ChartResponse(BaseModel):
    """Chart data with subscription status"""
    country_code: str
    artists: List[ChartArtist]
    followed: bool = False
    subscription: Optional[ChartSubscriptionResponse] = None
