# backend/schemas/__init__.py
"""
Centralized schema imports for easy access throughout the application.

Schema Organization:
- auth.py: Authentication request/response schemas
- common.py: Shared schemas (MessageResponse, ErrorResponse, Pagination)
- jobs.py: Job management schemas
- ytmusic.py: YouTube Music API response schemas
- settings.py: Settings management schemas (NEW)

Note: We use SQLAlchemy models directly for database outputs.
      They have .to_dict() methods and work with Pydantic's from_attributes=True
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
)

# Job schemas
from .jobs import (
    EnqueueRequest,
    EnqueueResponse,
    JobOut,
    CancelRequest,
    RequeueRequest,
)

# Settings schemas
from .settings import (
    SettingResponse,
    SettingUpdateRequest,
)

# YTMusic API schemas (external API, not our database)
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
    
    # Job schemas
    "EnqueueRequest",
    "EnqueueResponse",
    "JobOut",
    "CancelRequest",
    "RequeueRequest",
    
    # Settings
    "SettingResponse",
    "SettingUpdateRequest",
    
    # YTMusic (external API schemas)
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