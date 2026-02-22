# backend/schemas/charts.py
"""
Pydantic schemas for charts endpoints.
"""
from __future__ import annotations
from typing import Optional, List, Dict, Any
from datetime import datetime

from pydantic import BaseModel, Field


# ============================================================================
# REQUEST SCHEMAS
# ============================================================================

class FollowChartRequest(BaseModel):
    """Request to follow a chart"""
    top_n_artists: int = Field(default=40, ge=1, le=40, description="Number of top artists to auto-follow (1-40)")


class UpdateChartRequest(BaseModel):
    """Request to update chart subscription settings"""
    top_n_artists: Optional[int] = Field(None, ge=1, le=40, description="Number of top artists to auto-follow (1-40)")
    enabled: Optional[bool] = Field(None, description="Enable/disable chart sync")


# ============================================================================
# RESPONSE SCHEMAS
# ============================================================================

class ChartArtist(BaseModel):
    """Artist in a chart"""
    id: str
    name: Optional[str] = None
    thumbnails: List[Dict[str, Any]] = Field(default_factory=list)
    rank: Optional[int] = None
    trend: Optional[str] = None  # "up", "down", "same", "new"
    followed: bool = False  # Whether this artist is already followed
    
    model_config = {"from_attributes": True}


class ChartSubscriptionResponse(BaseModel):
    """Chart subscription details"""
    id: int
    country_code: str
    enabled: bool
    top_n_artists: int
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
    cached: bool = False