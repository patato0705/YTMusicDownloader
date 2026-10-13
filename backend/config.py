# backend/config.py
"""
Centralised configuration read from environment variables.
Keep defaults aligned with your docker-compose envs.
"""
from __future__ import annotations
import logging
import os
from pathlib import Path

logger = logging.getLogger("config")

APP_VERSION = "0.1.0"

# Directories
CONFIG_DIR = Path("/config")
TEMP_DIR = Path("/config/temp")
DOWNLOAD_DIR = Path("/config/temp/downloads")
COVERS_DIR = Path("/config/covers")
CACHE_DIR = Path("/config/cache")
THUMBNAIL_CACHE_DIR = Path("/config/cache/thumbnails")
DB_PATH = Path("/config/db.sqlite")
LOG_DIR = Path("/config/logs")
MUSIC_DIR = Path("/data")


def _bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _positive_int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, "") or default))
    except ValueError:
        return default


def _secret_env(name: str) -> str:
    """NAME, or the contents of the file NAME_FILE points to (Docker/Kubernetes secrets)."""
    path = os.environ.get(f"{name}_FILE", "").strip()
    if path:
        try:
            return Path(path).read_text(encoding="utf-8").strip()
        except OSError:
            # Reported by validate_auth_config() at startup
            return ""
    return os.environ.get(name, "").strip()


# App params
SEARCH_CACHE_TTL = 900
THUMBNAIL_CACHE_TTL = 7 * 24 * 60 * 60  # 7 days for thumbnails
THUMBNAIL_CACHE_MAX_BYTES = 500 * 1024 * 1024  # oldest files deleted past this
THUMBNAIL_MAX_IMAGE_BYTES = 5 * 1024 * 1024  # larger responses are refused, not cached
YTM_MAX_CONC = 5
YTM_BACKOFF_BASE = 0.5
YTM_BACKOFF_MAX = 8.0
HEADERS_AUTH = os.environ.get("HEADERS_AUTH") or None

# JWT / Auth settings. The signing key itself is generated on first use and
# kept in CONFIG_DIR/secrets.json (see backend/secrets.py).
JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 15
JWT_REFRESH_TOKEN_EXPIRE_DAYS = 7
# How long a browser stays "known" to an account after its last successful
# sign-in (gives it its own failed-attempt allowance, see services/login_throttle)
DEVICE_TOKEN_EXPIRE_DAYS = 365

# Auth cookies (access_token, refresh_token): mark Secure only if this
# deployment is reached over HTTPS (e.g. behind a TLS-terminating reverse
# proxy). Defaults to off so plain-HTTP/LAN homeserver setups work
# out of the box -- browsers silently refuse to ever send a Secure cookie
# back over plain HTTP, which would otherwise break login persistence.
# Set COOKIE_SECURE=true if you've put this behind HTTPS.
COOKIE_SECURE = _bool_env("COOKIE_SECURE", False)

# Password hashing
BCRYPT_ROUNDS = 12  # Balance between security and performance

# First-time setup
FIRST_ADMIN_USERNAME = os.environ.get("FIRST_ADMIN_USERNAME", "admin")
FIRST_ADMIN_PASSWORD = os.environ.get("FIRST_ADMIN_PASSWORD", "default")


# Single sign-on (OpenID Connect). Deployment settings, so env-only: whoever
# can change them decides who may sign in as anyone (see README). Enabled
# when issuer, client id and secret are all set.
PASSWORD_LOGIN_ENABLED = _bool_env("PASSWORD_LOGIN_ENABLED", True)
PUBLIC_URL = os.environ.get("PUBLIC_URL", "").strip().rstrip("/")
OIDC_ISSUER_URL = os.environ.get("OIDC_ISSUER_URL", "").strip()
OIDC_CLIENT_ID = os.environ.get("OIDC_CLIENT_ID", "").strip()
OIDC_CLIENT_SECRET = _secret_env("OIDC_CLIENT_SECRET")
OIDC_SCOPES = os.environ.get("OIDC_SCOPES", "").strip() or "openid profile"
OIDC_GROUPS_CLAIM = os.environ.get("OIDC_GROUPS_CLAIM", "").strip() or "groups"
# When either is set, the provider owns roles: re-applied at every sign-in
OIDC_ADMIN_GROUP = os.environ.get("OIDC_ADMIN_GROUP", "").strip()
OIDC_MEMBER_GROUP = os.environ.get("OIDC_MEMBER_GROUP", "").strip()
OIDC_PROVIDER_NAME = os.environ.get("OIDC_PROVIDER_NAME", "").strip() or "SSO"

OIDC_ENABLED = bool(OIDC_ISSUER_URL and OIDC_CLIENT_ID and OIDC_CLIENT_SECRET)
OIDC_ROLES_FROM_GROUPS = bool(OIDC_ADMIN_GROUP or OIDC_MEMBER_GROUP)


def validate_auth_config() -> None:
    """
    Refuse to start on a sign-in setup that can't work, rather than failing
    later at someone's first sign-in. Called by the web app factory only:
    the recovery CLI must keep working whatever the configuration.
    """
    errors = []
    if os.environ.get("OIDC_CLIENT_SECRET_FILE", "").strip() and not OIDC_CLIENT_SECRET:
        errors.append("OIDC_CLIENT_SECRET_FILE is set but the file is missing, unreadable or empty")
    oidc_vars = {"OIDC_ISSUER_URL": OIDC_ISSUER_URL, "OIDC_CLIENT_ID": OIDC_CLIENT_ID, "OIDC_CLIENT_SECRET": OIDC_CLIENT_SECRET}
    if any(oidc_vars.values()) and not all(oidc_vars.values()):
        missing = ", ".join(name for name, value in oidc_vars.items() if not value)
        errors.append(f"single sign-on is partly configured, missing: {missing}")
    if OIDC_ENABLED:
        if not PUBLIC_URL.startswith(("http://", "https://")):
            errors.append("PUBLIC_URL (e.g. https://music.example.com) is required with single sign-on")
        if "openid" not in OIDC_SCOPES.split():
            errors.append("OIDC_SCOPES must include 'openid'")
    elif OIDC_ROLES_FROM_GROUPS:
        errors.append("OIDC_ADMIN_GROUP / OIDC_MEMBER_GROUP are set but single sign-on is not configured")
    if not PASSWORD_LOGIN_ENABLED and not OIDC_ENABLED:
        errors.append("PASSWORD_LOGIN_ENABLED=false needs single sign-on configured, or nobody can sign in")
    if errors:
        raise RuntimeError("Invalid sign-in configuration: " + "; ".join(errors))


# User roles
ROLE_ADMINISTRATOR = "administrator"
ROLE_MEMBER = "member"
ROLE_VISITOR = "visitor"

VALID_ROLES = (ROLE_ADMINISTRATOR, ROLE_MEMBER, ROLE_VISITOR)

# yt-dlp
YDL_FORMAT = "m4a/bestaudio/best"
YDL_PREFERRED_CODEC = "m4a"
YDL_COOKIEFILE = Path("/config/ytcookies.txt")
# Optional cookies exported from a signed-in YouTube account (uploaded via the
# admin panel). Used ONLY as a fallback for age-restricted videos, never for
# ordinary downloads and never to get around a rate limit -- keeping its
# request count tiny is what keeps the account from being flagged.
YDL_USER_COOKIEFILE = Path("/config/ytcookies-user.txt")

# Number of download worker *processes* supervisord starts (deploy/entrypoint.sh
# exports it; deploy/supervisord.conf reads it as numprocs). This is the
# ceiling: how many of them actually take jobs is the runtime-tunable
# download.max_concurrent setting. The 3 mirrors the entrypoint default.
DOWNLOAD_WORKERS = _positive_int_env("DOWNLOAD_WORKERS", 3)

# Server / docker
PORT = int(os.environ.get("PORT", 8000))
HOST = os.environ.get("HOST", "0.0.0.0")


def ensure_dirs() -> None:
    """Create the configured directories (called once at web startup)."""
    for p in (CONFIG_DIR, TEMP_DIR, DOWNLOAD_DIR, COVERS_DIR, LOG_DIR, MUSIC_DIR, CACHE_DIR, THUMBNAIL_CACHE_DIR):
        try:
            p.mkdir(parents=True, exist_ok=True)
        except OSError:
            # Best-effort: keep starting up so the health endpoint stays reachable,
            # but this directory being unwritable will surface as failures later
            # (downloads, DB writes, etc.) unless someone sees this log line.
            logger.error("Failed to create directory %s: check volume permissions", p, exc_info=True)
