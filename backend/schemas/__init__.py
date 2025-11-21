# backend/schemas/__init__.py
"""
Centralized schema imports for easy access throughout the application.

Usage:
    from backend.schemas import ArtistOut, AlbumSchema, UserResponse
    from backend.schemas.auth import LoginRequest
    from backend.schemas.ytmusic import TrackSchema
"""

# Auth schemas
from .auth import (
    LoginRequest,
    RegisterRequest,
    RefreshTokenRequest,
    ChangePasswordRequest,
    UpdateUserRequest,
    TokenResponse,
    UserResponse,
    LoginResponse,
    MessageResponse as AuthMessageResponse,
)

# Job schemas
from .jobs import (
    EnqueueRequest,
    EnqueueResponse,
    JobOut,
    CancelRequest,
    RequeueRequest,
)
from .models import (
    ArtistOut,
    AlbumOut,
    TrackOut,
    TrackArtist,
    JobOut,
)

# YTMusic API schemas
from .ytmusic import (
    Thumbnail,
    ArtistRefSchema,
    AlbumRefSchema,
    TrackSchema,
    PlaylistSchema,
    AlbumItemSchema,
    AlbumSchema,
    ArtistSchema,
    SongSchema,
)

# Common schemas
from .common import (
    MessageResponse,
    ErrorResponse,
    PaginationParams,
    PaginatedResponse,
)

__all__ = [
    # Auth
    "LoginRequest",
    "RegisterRequest",
    "RefreshTokenRequest",
    "ChangePasswordRequest",
    "UpdateUserRequest",
    "TokenResponse",
    "UserResponse",
    "LoginResponse",
    "AuthMessageResponse",
    
    # Job schemas
    "EnqueueRequest",
    "EnqueueResponse",
    "JobOut",
    "CancelRequest",
    "RequeueRequest",
    
    # Database models
    "ArtistOut",
    "AlbumOut",
    "TrackOut",
    "TrackArtist",
    "JobOut",
    
    # YTMusic
    "Thumbnail",
    "ArtistRefSchema",
    "AlbumRefSchema",
    "TrackSchema",
    "PlaylistSchema",
    "AlbumItemSchema",
    "AlbumSchema",
    "ArtistSchema",
    "SongSchema",
    
    # Common
    "MessageResponse",
    "ErrorResponse",
    "PaginationParams",
    "PaginatedResponse",
]