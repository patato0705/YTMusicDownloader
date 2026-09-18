# backend/routers/admin.py
"""
Admin endpoints.

User Management:
- GET /api/admin/users - List all users
- POST /api/admin/users - Create new user
- PATCH /api/admin/users/{user_id}/role - Update user role
- POST /api/admin/users/{user_id}/deactivate - Deactivate user
- POST /api/admin/users/{user_id}/activate - Activate user
- DELETE /api/admin/users/{user_id} - Permanently delete user

YouTube account cookies (fallback for age-restricted videos only):
- GET /api/admin/youtube-cookies - Whether a jar is uploaded, and its size/age
- PUT /api/admin/youtube-cookies - Upload a Netscape cookies.txt
- DELETE /api/admin/youtube-cookies - Remove it

Settings Management:
- GET /api/admin/settings - Get all settings
- GET /api/admin/settings/{key} - Get specific setting
- PUT /api/admin/settings/{key} - Update or create setting
- DELETE /api/admin/settings/{key} - Delete setting (reset to default)
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.db import get_session
from backend.dependencies import require_admin
from backend.services import admin as admin_svc
from backend.services import auth as auth_svc  # For create_user
from backend import settings as settings_module
from backend.schemas import (
    UserResponse,
    CreateUserRequest,
    SettingResponse,
    SettingUpdateRequest,
    MessageResponse,
    YoutubeCookiesStatus,
    YoutubeCookiesUpload,
)
from backend import config
from backend.models import User, Setting

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
    This is separate from the public registration endpoint.
    """
    try:
        user = auth_svc.create_user(
            session=session,
            username=data.username,
            email=data.email,
            password=data.password,
            role=data.role,
        )
        
        return UserResponse.model_validate(user)
    
    except auth_svc.UsernameTakenError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="username_taken")
    except auth_svc.EmailTakenError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email_taken")
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
    setup with no one else able to restore admin access).
    """
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change your own role",
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


@router.get("/users/stats")
def get_user_stats(
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """
    Get user statistics (admin only).
    
    Returns counts of users by role and status.
    """
    return admin_svc.get_user_stats(session)


# ============================================================================
# SETTINGS MANAGEMENT ENDPOINTS
# ============================================================================

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
        SettingResponse(
            **setting,
            allowed_values=settings_module.get_allowed_values(setting["key"]),
            min=settings_module.get_min_value(setting["key"]),
            max=settings_module.get_max_value(setting["key"]),
        )
        for setting in settings_list
    ]


@router.get("/settings/{key}", response_model=SettingResponse)
def get_setting(
    key: str,
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """
    Get a specific setting by key (admin only).
    
    If the setting doesn't exist in the database but is a default setting,
    returns the default value.
    """
    setting = session.get(Setting, key)
    
    if not setting:
        # Check if it's a default setting
        if key in settings_module.DEFAULT_SETTINGS:
            default_config = settings_module.DEFAULT_SETTINGS[key]
            return SettingResponse(
                key=key,
                value=default_config["value"],
                type=default_config["type"],
                description=default_config["description"],
                allowed_values=settings_module.get_allowed_values(key),
                min=settings_module.get_min_value(key),
                max=settings_module.get_max_value(key),
                updated_at=None,
                updated_by=None,
            )

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Setting '{key}' not found",
        )

    return SettingResponse(
        **setting.to_dict(),
        allowed_values=settings_module.get_allowed_values(key),
        min=settings_module.get_min_value(key),
        max=settings_module.get_max_value(key),
    )


@router.put("/settings/{key}", response_model=SettingResponse)
def update_setting(
    key: str,
    data: SettingUpdateRequest,
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """
    Update or create a setting (admin only).
    
    The value will be type-converted based on the setting's type.
    If the setting doesn't exist, it will be created with type 'string'
    unless it's a default setting.
    """
    try:
        setting = settings_module.set_setting(
            session=session,
            key=key,
            value=data.value,
            user_id=current_user.id,
        )

        if key == "ytmusic.language":
            from ..ytm_service.client import reset_client
            reset_client()

        return SettingResponse(
            **setting.to_dict(),
            allowed_values=settings_module.get_allowed_values(key),
            min=settings_module.get_min_value(key),
            max=settings_module.get_max_value(key),
        )
    
    except Exception as e:
        logger.error(f"Error updating setting {key}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to update setting: {str(e)}",
        )


@router.delete("/settings/{key}", response_model=MessageResponse)
def delete_setting(
    key: str,
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """
    Delete a setting (admin only).
    
    If the setting is a default setting, this will reset it to its default value
    on next access. If it's a custom setting, it will be permanently deleted.
    """
    success = settings_module.delete_setting(session, key)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Setting '{key}' not found",
        )
    
    is_default = key in settings_module.DEFAULT_SETTINGS
    message = (
        f"Setting '{key}' deleted. It will reset to default value on next access."
        if is_default
        else f"Setting '{key}' permanently deleted."
    )
    
    return MessageResponse(message=message)

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
    from datetime import datetime, timezone
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
