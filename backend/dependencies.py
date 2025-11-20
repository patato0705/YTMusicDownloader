# backend/dependencies.py
"""
FastAPI dependency functions for authentication and authorization.
"""
from __future__ import annotations
import logging
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from .db import get_session
from .services import auth as auth_svc
from .models import User
from . import config

logger = logging.getLogger("dependencies")

security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: Session = Depends(get_session),
) -> User:
    """
    Extract and validate JWT token from Authorization header.
    Returns current user or raises 401.
    """
    token = credentials.credentials
    
    # Verify token
    payload = auth_svc.verify_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Get user from database - FIX: cast user_id to int
    user_id = payload.get("user_id")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        user_id_int = int(user_id)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID in token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = auth_svc.get_user_by_id(session, user_id_int)
    
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user


def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    session: Session = Depends(get_session),
) -> Optional[User]:
    """
    Optional authentication - returns user if token provided, None otherwise.
    """
    if not credentials:
        return None
    
    try:
        return get_current_user(credentials, session)
    except HTTPException:
        return None


# Alias for consistency
require_auth = get_current_user


def require_role(required_role: str):
    """Factory function to create role-based dependencies."""
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires {required_role} role",
            )
        return current_user
    
    return role_checker


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require administrator role"""
    if current_user.role != config.ROLE_ADMINISTRATOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required",
        )
    return current_user


def require_member_or_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require member or administrator role (blocks visitors)"""
    if current_user.role not in [config.ROLE_MEMBER, config.ROLE_ADMINISTRATOR]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Member or Administrator access required",
        )
    return current_user


def can_modify_user(current_user: User, target_user_id: int) -> bool:
    """Check if current user can modify target user."""
    if current_user.role == config.ROLE_ADMINISTRATOR:
        return True
    return current_user.id == target_user_id


def check_user_modification_permission(
    current_user: User,
    target_user_id: int,
) -> None:
    """Raise 403 if current user cannot modify target user."""
    if not can_modify_user(current_user, target_user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only modify your own account",
        )