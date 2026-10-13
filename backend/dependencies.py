# backend/dependencies.py
"""
FastAPI dependency functions for authentication, authorization and feature flags.
"""
from __future__ import annotations
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from .db import get_session
from .services import auth as auth_svc
from .models import User
from . import config
from . import settings as settings_module

security = HTTPBearer()
# auto_error=False: missing/malformed Authorization header falls through to
# the access_token cookie check in require_auth_flexible() instead of
# raising immediately.
security_optional = HTTPBearer(auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _resolve_user_from_token(token: str, session: Session) -> User:
    """Shared validation: decode/verify a JWT access token and load its user."""
    payload = auth_svc.verify_access_token(token)
    if not payload:
        raise _unauthorized("Invalid or expired token")

    user = session.get(User, payload["user_id"])
    if not user or not user.is_active:
        raise _unauthorized("User not found or inactive")

    # Signed out by a password change since this token was issued
    if auth_svc.token_revoked(user, payload["issued_at"]):
        raise _unauthorized("Session revoked")

    return user


def require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: Session = Depends(get_session),
) -> User:
    """The user of the access token in the Authorization header, or 401."""
    return _resolve_user_from_token(credentials.credentials, session)


def require_auth_flexible(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional),
    session: Session = Depends(get_session),
) -> User:
    """
    Like require_auth, but also accepts the access_token cookie.

    For routes loaded via a plain <img src="..."> tag (browsers won't attach
    an Authorization header to those) rather than JS-driven fetch calls. The
    cookie carries the identical JWT the header would, just via a channel
    the browser sends automatically.
    """
    token = credentials.credentials if credentials else request.cookies.get("access_token")
    if not token:
        raise _unauthorized("Not authenticated")
    return _resolve_user_from_token(token, session)


def require_admin(current_user: User = Depends(require_auth)) -> User:
    """Require administrator role"""
    if current_user.role != config.ROLE_ADMINISTRATOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required",
        )
    return current_user


def require_member_or_admin(current_user: User = Depends(require_auth)) -> User:
    """Require member or administrator role (blocks visitors)"""
    if current_user.role not in (config.ROLE_MEMBER, config.ROLE_ADMINISTRATOR):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Member or Administrator access required",
        )
    return current_user


def require_charts_enabled(session: Session = Depends(get_session)) -> None:
    """Reject the request when the charts feature is switched off."""
    if not settings_module.feature_enabled(session, "charts"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Charts feature is disabled",
        )
