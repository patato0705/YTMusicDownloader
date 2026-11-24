# backend/schemas/__init__.py
"""
Pydantic schemas:
- auth.py: Authentication request/response schemas
- charts.py: Chart endpoints
- common.py: Shared schemas
- export.py: The export/import document and its import report
- settings.py: Settings management schemas
- ytmusic.py: YouTube Music data (external API, not our database)
"""
from .auth import (
    LoginRequest,
    RegisterRequest,
    CreateUserRequest,
    ChangePasswordRequest,
    TokenResponse,
    UserResponse,
    LoginResponse,
    TemporaryPasswordResponse,
)
from .common import MessageResponse
from .settings import (
    SettingResponse,
    SettingUpdateRequest,
    YoutubeCookiesStatus,
    YoutubeCookiesUpload,
)
from .ytmusic import (
    Thumbnail,
    ArtistRefSchema,
    AlbumRefSchema,
    TrackSchema,
    PlaylistSchema,
    AlbumSchema,
)

__all__ = [
    "LoginRequest",
    "RegisterRequest",
    "CreateUserRequest",
    "ChangePasswordRequest",
    "TokenResponse",
    "UserResponse",
    "LoginResponse",
    "TemporaryPasswordResponse",
    "MessageResponse",
    "SettingResponse",
    "SettingUpdateRequest",
    "YoutubeCookiesStatus",
    "YoutubeCookiesUpload",
    "Thumbnail",
    "ArtistRefSchema",
    "AlbumRefSchema",
    "TrackSchema",
    "PlaylistSchema",
    "AlbumSchema",
]
