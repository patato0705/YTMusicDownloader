# backend/schemas/ytmusic.py
"""
Pydantic schemas for YouTube Music API responses.
These represent data coming FROM the ytmusicapi, not from our database.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class Thumbnail(BaseModel):
    """Image thumbnail with dimensions"""
    url: str
    width: Optional[int] = None
    height: Optional[int] = None
    
    model_config = {"extra": "ignore"}


class ArtistRefSchema(BaseModel):
    """Lightweight artist reference (used in tracks, albums, etc.)"""
    id: Optional[str] = None
    name: Optional[str] = None
    
    model_config = {"extra": "ignore"}

class AlbumRefSchema(BaseModel):
    """Lightweight album reference (used in tracks, albums, etc.)"""
    id: Optional[str] = None
    name: Optional[str] = None
    
    model_config = {"extra": "ignore"}


class TrackSchema(BaseModel):
    """Track/song from YTMusic"""
    id: str
    title: str
    artists: List[ArtistRefSchema] = Field(default_factory=list)
    album: Optional[AlbumRefSchema] = None  # Changed from List to Optional single object
    cover: Optional[str] = None
    duration_seconds: int
    track_number: Optional[int] = None
    isExplicit: bool = False
    raw: Optional[Any] = None
    
    model_config = {"extra": "ignore"}


class PlaylistSchema(BaseModel):
    """Playlist from YTMusic (including albums as playlists)"""
    id: str
    title: Optional[str] = None
    thumbnails: List[Thumbnail] = Field(default_factory=list)
    tracks: List[TrackSchema] = Field(default_factory=list)
    raw: Optional[Any] = None
    
    model_config = {"extra": "ignore"}


class AlbumItemSchema(BaseModel):
    """
    Lightweight album reference used in lists, search results, and artist albums.
    Does NOT include full track listing.
    """
    id: str  # browseId or playlistId
    browseId: Optional[str] = None
    playlistId: Optional[str] = None
    title: Optional[str] = None
    type: Optional[str] = None  # "Album", "Single", "EP"
    thumbnails: List[Thumbnail] = Field(default_factory=list)
    cover: Optional[str] = None  # Best thumbnail URL
    year: Optional[str] = None
    artists: List[ArtistRefSchema] = Field(default_factory=list)
    raw: Optional[Any] = None
    
    model_config = {"extra": "ignore"}


class AlbumSchema(BaseModel):
    """
    Full album details with complete track listing.
    Used when fetching a specific album.
    """
    id: str
    playlistId: Optional[str] = None
    title: str
    type: Optional[str] = None  # "Album", "Single", "EP"
    thumbnails: List[Thumbnail] = Field(default_factory=list)
    cover: Optional[str] = None  # Best thumbnail URL
    isExplicit: bool = False
    description: Optional[str] = None
    year: Optional[str] = None
    artists: List[ArtistRefSchema] = Field(default_factory=list)
    trackCount: Optional[int] = None
    duration: Optional[str] = None  # Human readable (e.g., "21 minutes")
    duration_seconds: Optional[int] = None  # Total duration in seconds
    tracks: List[TrackSchema] = Field(default_factory=list)
    
    model_config = {"extra": "ignore"}


class ArtistSchema(BaseModel):
    """Artist from YTMusic"""
    id: str
    name: Optional[str] = None
    thumbnails: List[Thumbnail] = Field(default_factory=list)
    image: Optional[str] = None
    albums_count: Optional[int] = None
    raw: Optional[Any] = None
    
    model_config = {"extra": "ignore"}


class SongSchema(BaseModel):
    """Song/video details from YTMusic"""
    videoId: str
    title: Optional[str] = None
    videoDetails: Optional[Dict[str, Any]] = None
    thumbnails: List[Thumbnail] = Field(default_factory=list)
    raw: Optional[Any] = None
    
    model_config = {"extra": "ignore"}