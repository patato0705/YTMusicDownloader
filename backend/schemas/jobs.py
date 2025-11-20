# backend/schemas/jobs.py
"""
Job-related request/response schemas.
"""
from __future__ import annotations
from typing import Any, Dict, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class EnqueueRequest(BaseModel):
    """Request to enqueue a new job"""
    type: str = Field(..., description="Job type (e.g. 'download_track', 'sync_artist')")
    payload: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Job payload data")
    scheduled_at: Optional[datetime] = Field(None, description="Schedule for future (UTC)")
    priority: Optional[int] = Field(0, description="Priority (higher = first)")
    max_attempts: Optional[int] = Field(5, description="Max retry attempts")


class EnqueueResponse(BaseModel):
    """Response after enqueueing a job"""
    ok: bool
    job_id: Optional[int] = None
    message: Optional[str] = None


class JobOut(BaseModel):
    """Job output schema"""
    id: int
    type: str
    status: Optional[str] = None
    attempts: Optional[int] = None
    max_attempts: Optional[int] = None
    priority: Optional[int] = None
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    reserved_by: Optional[str] = None
    last_error: Optional[str] = None
    result: Optional[Any] = None
    payload: Optional[Any] = None
    user_id: Optional[int] = None  # NEW: user who created the job
    
    model_config = {"from_attributes": True}


class CancelRequest(BaseModel):
    """Request to cancel a job"""
    message: Optional[str] = Field(None, description="Cancellation reason")


class RequeueRequest(BaseModel):
    """Request to requeue a job"""
    delay_seconds: Optional[int] = Field(None, description="Delay before job runs")