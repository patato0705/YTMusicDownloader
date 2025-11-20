# backend/config.py
"""
Centralised configuration read from environment variables.
Keep defaults aligned with your docker-compose envs.
"""
from __future__ import annotations
import os
from pathlib import Path

# Directories (use defaults)
CONFIG_DIR = Path("/config")
TEMP_DIR = Path("/config/temp")
DOWNLOAD_DIR = Path("/config/temp/downloads")
COVERS_DIR = Path("/config/temp/covers")
LYRICS_DIR = Path("/config/temp/lyrics_raw")
CACHE_DIR = Path("/config/cache")  # Cache directory 
THUMBNAIL_CACHE_DIR = Path("/config/cache/thumbnails")  # Thumbnail cache
DB_PATH = Path("/config/db.sqlite")
LOG_DIR = Path("/config/logs")
MUSIC_DIR = Path("/data")

# App params
VITE_API_BASE = "http://localhost:8000/api"
SEARCH_CACHE_TTL = 900
THUMBNAIL_CACHE_TTL = 7 * 24 * 60 * 60  # 7 days for thumbnails
YTM_MAX_CONC = 5
YTM_BACKOFF_BASE = 0.5
YTM_BACKOFF_MAX = 8.0
HEADERS_AUTH = os.environ.get("HEADERS_AUTH", None)

# JWT / Auth settings
# Secret loaded from secrets.json (auto-generated on first startup)
try:
    from .secrets import get_jwt_secret
    JWT_SECRET_KEY = get_jwt_secret()
except Exception:
    # Fallback for initial import (before secrets module loads)
    JWT_SECRET_KEY = "TEMPORARY_KEY_WILL_BE_REPLACED"
JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 15
JWT_REFRESH_TOKEN_EXPIRE_DAYS = 7

# Password hashing
BCRYPT_ROUNDS = 12  # Balance between security and performance

# First-time setup
FIRST_ADMIN_USERNAME = os.environ.get("FIRST_ADMIN_USERNAME", "admin")
FIRST_ADMIN_EMAIL = os.environ.get("FIRST_ADMIN_EMAIL", "admin@localhost")
FIRST_ADMIN_PASSWORD = os.environ.get("FIRST_ADMIN_PASSWORD", "default")

# User roles
ROLE_ADMINISTRATOR = "administrator"
ROLE_MEMBER = "member"
ROLE_VISITOR = "visitor"

VALID_ROLES = [ROLE_ADMINISTRATOR, ROLE_MEMBER, ROLE_VISITOR]

# yt-dlp
YDL_FORMAT = "m4a/bestaudio/best"
YDL_PREFERRED_CODEC = "m4a"

# Server / docker
PORT = int(os.environ.get("PORT", 8000))
HOST = os.environ.get("HOST", "0.0.0.0")

# Helper: ensure directories exist (call from startup)
def ensure_dirs() -> None:
    for p in (CONFIG_DIR, TEMP_DIR, DOWNLOAD_DIR, COVERS_DIR, LYRICS_DIR, LOG_DIR, MUSIC_DIR, CACHE_DIR, THUMBNAIL_CACHE_DIR):
        try:
            Path(p).mkdir(parents=True, exist_ok=True)
        except Exception:
            # ignore failures here; callers should log if needed
            pass