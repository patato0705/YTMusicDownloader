# backend/routers/admin.py
"""
Admin endpoints.

User Management:
- GET /api/admin/users - List all users
- PATCH /api/admin/users/{user_id}/role - Update user role
- POST /api/admin/users/{user_id}/deactivate - Deactivate user
- POST /api/admin/users/{user_id}/activate - Activate user

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
from backend.services import auth as auth_svc
from backend import settings as settings_module
from backend.schemas import (
    UserResponse,
    SettingResponse,
    SettingUpdateRequest,
    MessageResponse,
)
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
    users = auth_svc.list_users(
        session=session,
        include_inactive=include_inactive,
        limit=limit,
        offset=offset,
    )
    
    return [UserResponse.model_validate(u) for u in users]


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
    """
    try:
        user = auth_svc.update_user_role(session, user_id, role)
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
        user = auth_svc.deactivate_user(session, user_id)
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
    user = auth_svc.get_user_by_id(session, user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    user.is_active = True
    session.add(user)
    session.commit()
    session.refresh(user)
    
    logger.info(f"Activated user {user_id}")
    
    return UserResponse.model_validate(user)


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
    return [SettingResponse(**setting) for setting in settings_list]


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
                updated_at=None,
                updated_by=None,
            )
        
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Setting '{key}' not found",
        )
    
    return SettingResponse(**setting.to_dict())


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
        
        return SettingResponse(**setting.to_dict())
    
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