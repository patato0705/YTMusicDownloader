# backend/dependencies.py
"""
FastAPI dependency functions for authentication and authorization.
"""
from __future__ import annotations
import logging
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from .db import get_session
from .services import auth as auth_svc
from .models import User
from . import config

logger = logging.getLogger("dependencies")

security = HTTPBearer()
# auto_error=False: missing/malformed Authorization header falls through to
# the access_token cookie check in get_current_user_flexible() instead of
# raising immediately.
security_optional = HTTPBearer(auto_error=False)


def _resolve_user_from_token(token: str, session: Session) -> User:
    """Shared validation: decode/verify a JWT access token and load its user."""
    payload = auth_svc.verify_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

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


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: Session = Depends(get_session),
) -> User:
    """
    Extract and validate JWT token from the Authorization header.
    Returns current user or raises 401.
    """
    return _resolve_user_from_token(credentials.credentials, session)


def get_current_user_flexible(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional),
    session: Session = Depends(get_session),
) -> User:
    """
    Like get_current_user, but also accepts the access_token cookie.

    For routes loaded via a plain <img src="..."> tag (browsers won't attach
    an Authorization header to those) rather than JS-driven fetch calls. The
    cookie carries the identical JWT the header would, just via a channel
    the browser sends automatically.
    """
    token = credentials.credentials if credentials else request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _resolve_user_from_token(token, session)


# Alias for consistency
require_auth = get_current_user


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