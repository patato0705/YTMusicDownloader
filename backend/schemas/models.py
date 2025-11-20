# backend/schemas/models.py
"""
Pydantic schemas for database model outputs (API responses).
These represent data going OUT to API clients from our database.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class ArtistOut(BaseModel):
    """Artist database model output"""
    id: Optional[str] = None
    name: Optional[str] = None
    thumbnails: List[Any] = Field(default_factory=list)
    image_local: Optional[str] = None
    followed: bool = False  # Changed from 'monitored' to match your models
    created_at: Optional[datetime] = None
    
    model_config = {"from_attributes": True}  # Replaces orm_mode in Pydantic v2


class AlbumOut(BaseModel):
    """Album database model output"""
    id: Optional[str] = None
    title: Optional[str] = None
    artist_id: Optional[str] = None
    thumbnails: List[Any] = Field(default_factory=list)
    playlist_id: Optional[str] = None
    year: Optional[str] = None
    image_local: Optional[str] = None
    
    model_config = {"from_attributes": True}


class TrackArtist(BaseModel):
    """Artist reference in track output"""
    name: Optional[str] = None
    id: Optional[str] = None
    
    model_config = {"from_attributes": True}


class TrackOut(BaseModel):
    """Track database model output"""
    id: Optional[str] = None
    title: Optional[str] = None
    duration: Optional[int] = None
    artists: List[Dict[str, Optional[str]] | TrackArtist] = Field(default_factory=list)
    album_id: Optional[str] = None
    has_lyrics: bool = False
    lyrics_local: Optional[str] = None
    file_path: Optional[str] = None
    status: Optional[str] = None
    artist_valid: bool = True
    created_at: Optional[datetime] = None
    
    model_config = {"from_attributes": True}


class JobOut(BaseModel):
    """Job database model output"""
    id: Optional[int] = None
    type: Optional[str] = None
    payload: Optional[Dict[str, Any]] = Field(default_factory=dict)
    status: Optional[str] = None
    attempts: Optional[int] = 0
    max_attempts: Optional[int] = 5
    priority: Optional[int] = 0
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    last_error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    reserved_by: Optional[str] = None
    
    model_config = {"from_attributes": True}