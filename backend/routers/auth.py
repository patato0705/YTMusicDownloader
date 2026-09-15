# backend/routers/auth.py
"""
Authentication endpoints.

Endpoints:
- POST /api/auth/register - Register new user (Admin only)
- POST /api/auth/login - Login with username/password
- POST /api/auth/refresh - Refresh access token
- POST /api/auth/logout - Revoke refresh token
- GET /api/auth/me - Get current user info
- POST /api/auth/change-password - Change password
"""
from __future__ import annotations
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from backend.db import get_session
from backend.dependencies import get_current_user, require_admin
from backend.settings import get_setting
from backend.services import auth as auth_svc
from backend.schemas import (
    LoginRequest,
    RegisterRequest,
    ChangePasswordRequest,
    LoginResponse,
    TokenResponse,
    UserResponse,
    MessageResponse,
)
from backend.models import User
from .. import config

logger = logging.getLogger("routers.auth")

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


# ============================================================================
# COOKIE HELPERS
#
# The refresh token (and a copy of the access token) live in httpOnly
# cookies rather than the response body. This keeps them out of reach of
# JavaScript (so an XSS bug can't read them out of localStorage), and lets
# the access_token cookie ride along automatically on plain <img> requests
# to /api/media/images/... which can't carry an Authorization header.
# See backend/config.py for the COOKIE_SECURE toggle.
# ============================================================================

def _set_access_cookie(response: Response, access_token: str) -> None:
    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=config.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=config.COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        max_age=config.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        httponly=True,
        secure=config.COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")


# ============================================================================
# PUBLIC ENDPOINTS
# ============================================================================

@router.get("/registration-status")
async def get_registration_status(
    session: Session = Depends(get_session),
) -> dict:
    """
    Public endpoint to check if registration is enabled.
    """
    
    enabled = get_setting(session, "auth.registration_enabled", default=False)
    return {"enabled": enabled}


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(
    data: RegisterRequest,
    session: Session = Depends(get_session),
):
    """
    Register a new user (public registration).
    
    Registration must be enabled via the 'auth.registration_enabled' setting.
    """
    # Check if registration is enabled
    if not get_setting(session, "auth.registration_enabled", default=False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is currently disabled. If you think this is a mistake, please contact an administrator.",
        )
    
    try:
        user = auth_svc.create_user(
            session=session,
            username=data.username,
            email=data.email,
            password=data.password,
            role=config.ROLE_VISITOR,  # Default role for public registration
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


@router.post("/login", response_model=LoginResponse)
def login(
    data: LoginRequest,
    response: Response,
    session: Session = Depends(get_session),
):
    """
    Login with username and password.

    Sets the access token (15min) and refresh token (7 days) as httpOnly
    cookies, and also returns the access token in the body for use in the
    Authorization header on regular API calls.
    """
    # Authenticate user
    user = auth_svc.authenticate_user(session, data.username, data.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create tokens
    access_token = auth_svc.create_access_token(
        user_id=user.id,
        username=user.username,
        role=user.role,
    )

    refresh_token = auth_svc.create_refresh_token(session, user.id)

    # Update last login
    auth_svc.update_last_login(session, user.id)

    # Refresh user object to get updated last_login_at
    session.refresh(user)

    _set_access_cookie(response, access_token)
    _set_refresh_cookie(response, refresh_token)

    return LoginResponse(
        user=UserResponse.model_validate(user),
        access_token=access_token,
        token_type="bearer",
        expires_in=config.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
):
    """
    Exchange the refresh_token cookie for a new access token.

    Refresh token remains valid until expiration (7 days).
    """
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token cookie present",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify refresh token
    user = auth_svc.verify_refresh_token(session, refresh_token)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create new access token
    access_token = auth_svc.create_access_token(
        user_id=user.id,
        username=user.username,
        role=user.role,
    )

    _set_access_cookie(response, access_token)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=config.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/logout", response_model=MessageResponse)
def logout(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
):
    """
    Revoke the refresh token (logout) and clear auth cookies.

    Idempotent: succeeds even if there's no refresh_token cookie (or it's
    already invalid) so the client always ends up logged out.
    """
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        auth_svc.revoke_refresh_token(session, refresh_token)

    _clear_auth_cookies(response)

    return MessageResponse(message="Logged out successfully")


# ============================================================================
# PROTECTED ENDPOINTS
# ============================================================================

@router.get("/me", response_model=UserResponse)
def get_current_user_info(
    current_user: User = Depends(get_current_user),
):
    """
    Get current authenticated user's information.
    
    Requires valid access token in Authorization header.
    """
    return UserResponse.model_validate(current_user)


@router.post("/change-password", response_model=MessageResponse)
def change_password(
    data: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    Change current user's password.
    
    Requires current password for verification.
    """
    # Verify current password
    if not auth_svc.verify_password(data.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    
    # Hash and update new password
    new_hash = auth_svc.hash_password(data.new_password)
    current_user.password_hash = new_hash
    session.add(current_user)
    session.commit()
    
    logger.info(f"Password changed for user {current_user.username}")
    
    return MessageResponse(message="Password changed successfully")