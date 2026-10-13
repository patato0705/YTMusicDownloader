# backend/routers/admin.py
"""
Admin endpoints.

User Management:
- GET /api/admin/users - List all users
- POST /api/admin/users - Create new user
- PATCH /api/admin/users/{user_id}/role - Update user role
- POST /api/admin/users/{user_id}/deactivate - Deactivate user
- POST /api/admin/users/{user_id}/activate - Activate user
- POST /api/admin/users/{user_id}/reset-password - Set a temporary password
- DELETE /api/admin/users/{user_id} - Permanently delete user

YouTube account cookies (fallback for age-restricted videos only):
- GET /api/admin/youtube-cookies - Whether a jar is uploaded, and its size/age
- PUT /api/admin/youtube-cookies - Upload a Netscape cookies.txt
- DELETE /api/admin/youtube-cookies - Remove it

Settings Management:
- GET /api/admin/settings - Get all settings
- PUT /api/admin/settings/{key} - Update a setting
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import config, schedules
from .. import settings as settings_module
from ..db import get_session
from ..dependencies import require_admin
from ..models import User
from ..schemas import (
    UserResponse,
    CreateUserRequest,
    SettingResponse,
    SettingUpdateRequest,
    MessageResponse,
    TemporaryPasswordResponse,
    YoutubeCookiesStatus,
    YoutubeCookiesUpload,
)
from ..services import admin as admin_svc
from ..services import auth as auth_svc
from ..services import login_throttle
from ..time_utils import now_utc
from ..ytm_service.client import reset_client

logger = logging.getLogger("routers.admin")

router = APIRouter(prefix="/api/admin", tags=["Admin"])


# ============================================================================
# USER MANAGEMENT ENDPOINTS
# ============================================================================

@router.get("/users", response_model=list[UserResponse])
def list_users(
    include_inactive: bool = False,
    limit: int = 100,
    offset: int = 0,
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """
    List all users (admin only).

    Args:
        include_inactive: Include deactivated users
        limit: Maximum number of users to return
        offset: Number of users to skip
    """
    users = admin_svc.list_users(
        session=session,
        include_inactive=include_inactive,
        limit=limit,
        offset=offset,
    )

    return [UserResponse.model_validate(u) for u in users]


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    data: CreateUserRequest,
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """
    Create a new user (admin only).

    Allows admins to create users with any role.
    This is separate from the public registration endpoint. Creates password
    accounts, so unavailable when password sign-in is off (single sign-on
    accounts are created at their first sign-in).
    """
    if not config.PASSWORD_LOGIN_ENABLED:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="password_login_disabled")
    try:
        user = auth_svc.create_user(
            session=session,
            username=data.username,
            password=data.password,
            role=data.role,
        )

        return UserResponse.model_validate(user)

    except auth_svc.UsernameTakenError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="username_taken")
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.patch("/users/{user_id}/role", response_model=UserResponse)
def update_user_role(
    user_id: int,
    role: str,
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """
    Update user's role (admin only).

    Valid roles: administrator, member, visitor
    Cannot change your own role (avoids self-lockout, e.g. on a single-admin
    setup with no one else able to restore admin access). Nor that of a
    single sign-on account when roles come from provider groups: it would be
    undone at their next sign-in.
    """
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change your own role",
        )
    target = auth_svc.get_user_by_id(session, user_id)
    if target and target.is_oidc and config.OIDC_ROLES_FROM_GROUPS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This account's role comes from its single sign-on groups",
        )

    try:
        user = admin_svc.update_user_role(session, user_id, role)
        return UserResponse.model_validate(user)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/users/{user_id}/deactivate", response_model=UserResponse)
def deactivate_user(
    user_id: int,
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """
    Deactivate a user (admin only).

    Prevents login and revokes all refresh tokens.
    Cannot deactivate yourself.
    """
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate your own account",
        )

    try:
        user = admin_svc.deactivate_user(session, user_id)
        return UserResponse.model_validate(user)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.post("/users/{user_id}/activate", response_model=UserResponse)
def activate_user(
    user_id: int,
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """
    Reactivate a deactivated user (admin only).
    """
    try:
        user = admin_svc.activate_user(session, user_id)
        return UserResponse.model_validate(user)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.post("/users/{user_id}/reset-password", response_model=TemporaryPasswordResponse)
def reset_user_password(
    user_id: int,
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """
    Give a user a generated temporary password (admin only).

    The password is returned once, for the admin to pass on; the user has to
    choose a new one at next sign-in. Signs the user out everywhere and
    clears their failed sign-in lock. Works on other admins too (an admin
    can already demote or delete them), but not on yourself: that would
    skip the current-password check of /api/auth/change-password. Nor on
    single sign-on accounts: their sign-in is the provider's business (the
    recovery CLI can still give one a password, as a last resort).
    """
    if not config.PASSWORD_LOGIN_ENABLED:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="password_login_disabled")
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot reset your own password, change it instead",
        )

    user = auth_svc.get_user_by_id(session, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )
    if user.is_oidc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This account signs in with single sign-on; it has no password to reset",
        )

    temporary_password = auth_svc.generate_temporary_password()
    revoked = auth_svc.change_password(session, user, temporary_password, must_change_password=True)
    login_throttle.clear(login_throttle.login_account_key(user.username))

    logger.info(
        "Admin %s reset the password of %s (%s session(s) signed out)",
        current_user.username, user.username, revoked,
    )
    return TemporaryPasswordResponse(temporary_password=temporary_password)


@router.delete("/users/{user_id}", response_model=MessageResponse)
def delete_user(
    user_id: int,
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """
    Permanently delete a user (admin only).

    WARNING: This is a hard delete that removes the user and all associated data.
    This action cannot be undone.

    Cannot delete yourself.
    """
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account",
        )

    try:
        admin_svc.delete_user(session, user_id)
        return MessageResponse(message=f"User {user_id} permanently deleted")

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


# ============================================================================
# SETTINGS MANAGEMENT ENDPOINTS
# ============================================================================

def _setting_meta(key: str, value=None) -> dict:
    """
    What a SettingResponse carries besides the stored row: constraints and
    default, and for a schedule its unit, next fixed run and time zone --
    computed here because the container's TZ needn't be the browser's.
    """
    meta = {
        "allowed_values": settings_module.get_allowed_values(key),
        "min": settings_module.get_min_value(key),
        "max": settings_module.get_max_value(key),
        "default": settings_module.get_default_value(key),
        "unit": settings_module.get_unit(key),
    }
    if settings_module.DEFAULT_SETTINGS.get(key, {}).get("type") == "schedule":
        upcoming = schedules.next_run(schedules.parse(value, meta["default"]), now_utc())
        meta["next_run"] = upcoming.isoformat() if upcoming else None
        meta["timezone"] = str(schedules.timezone())
    return meta


@router.get("/settings", response_model=list[SettingResponse])
def get_all_settings(
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """
    Get all application settings (admin only).

    Returns all settings with their current values, types, and descriptions.
    """
    settings_list = settings_module.get_all_settings(session)
    return [
        SettingResponse(**setting, **_setting_meta(setting["key"], setting["value"]))
        for setting in settings_list
    ]


@router.put("/settings/{key}", response_model=SettingResponse)
def update_setting(
    key: str,
    data: SettingUpdateRequest,
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """
    Update a setting (admin only), validated against its declaration
    (settings.py). Internal bookkeeping keys and settings moot under the
    current sign-in configuration can't be set.
    """
    if not settings_module.is_user_setting(key):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown setting '{key}'")
    if not settings_module.is_applicable(key):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Setting '{key}' doesn't apply to the current sign-in configuration",
        )
    try:
        setting = settings_module.set_setting(session, key, data.value, user_id=current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if key == "ytmusic.language":
        reset_client()

    return SettingResponse(**setting.to_dict(), **_setting_meta(key, setting.get_typed_value()))


# ============================================================================
# YOUTUBE ACCOUNT COOKIES
# ============================================================================

def _count_netscape_cookies(content: str) -> int:
    """
    Number of well-formed cookie lines in a Netscape cookies.txt. Raises
    ValueError if the text isn't one at all, or has no youtube.com cookies
    (a jar for the wrong site would just silently never help).
    """
    count = 0
    youtube = 0
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) != 7:
            raise ValueError("not a Netscape cookies.txt: expected 7 tab-separated fields per cookie line")
        count += 1
        if fields[0].lstrip(".").endswith("youtube.com"):
            youtube += 1
    if count == 0:
        raise ValueError("no cookies found in file")
    if youtube == 0:
        raise ValueError("no youtube.com cookies in file (export while on youtube.com)")
    return count


def _youtube_cookies_status() -> YoutubeCookiesStatus:
    path = config.YDL_USER_COOKIEFILE
    try:
        st = path.stat()
    except FileNotFoundError:
        return YoutubeCookiesStatus(present=False)
    try:
        count = _count_netscape_cookies(path.read_text(encoding="utf-8", errors="replace"))
    except ValueError:
        count = 0
    return YoutubeCookiesStatus(
        present=True,
        cookie_count=count,
        size_bytes=st.st_size,
        modified_at=datetime.fromtimestamp(st.st_mtime, tz=timezone.utc),
    )


@router.get("/youtube-cookies", response_model=YoutubeCookiesStatus)
def get_youtube_cookies(current_user: User = Depends(require_admin)) -> YoutubeCookiesStatus:
    """
    Whether an account cookie jar is uploaded (admin only). Never returns the
    cookies themselves: they're a login session.
    """
    return _youtube_cookies_status()


@router.put("/youtube-cookies", response_model=YoutubeCookiesStatus)
def upload_youtube_cookies(
    payload: YoutubeCookiesUpload,
    current_user: User = Depends(require_admin),
) -> YoutubeCookiesStatus:
    """
    Store a browser-exported cookies.txt as the account jar. Used only as a
    fallback for age-restricted tracks (see jobs.tasks.download_track).
    """
    try:
        count = _count_netscape_cookies(payload.content)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    path = config.YDL_USER_COOKIEFILE
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(payload.content if payload.content.endswith("\n") else payload.content + "\n", encoding="utf-8")
        tmp.chmod(0o600)  # a login session: keep it off other users of the box
        tmp.replace(path)
    except OSError as e:
        logger.exception("Failed to write YouTube account cookies")
        raise HTTPException(status_code=500, detail=f"Failed to save cookies: {e}")

    logger.info("YouTube account cookies uploaded by user %s (%d cookies)", current_user.id, count)
    return _youtube_cookies_status()


@router.delete("/youtube-cookies", response_model=MessageResponse)
def delete_youtube_cookies(current_user: User = Depends(require_admin)) -> MessageResponse:
    """Remove the account jar; age-restricted tracks will fail again until a new one is uploaded."""
    path = config.YDL_USER_COOKIEFILE
    try:
        path.unlink()
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No account cookies uploaded")
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete cookies: {e}")
    logger.info("YouTube account cookies deleted by user %s", current_user.id)
    return MessageResponse(message="YouTube account cookies deleted")
