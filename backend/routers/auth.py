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

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.db import get_session
from backend.dependencies import get_current_user, require_admin
from backend.services import auth as auth_svc
from backend.schemas import (
    LoginRequest,
    RegisterRequest,
    RefreshTokenRequest,
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
# PUBLIC ENDPOINTS
# ============================================================================

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(
    data: RegisterRequest,
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """
    Register a new user (Admin only).
    """
    try:
        user = auth_svc.create_user(
            session=session,
            username=data.username,
            email=data.email,
            password=data.password,
            role=config.ROLE_VISITOR,  # Default role
        )
        
        return UserResponse.model_validate(user)
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/login", response_model=LoginResponse)
def login(
    data: LoginRequest,
    session: Session = Depends(get_session),
):
    """
    Login with username and password.
    
    Returns access token (15min) and refresh token (7 days).
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
    
    return LoginResponse(
        user=UserResponse.model_validate(user),
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=config.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    data: RefreshTokenRequest,
    session: Session = Depends(get_session),
):
    """
    Exchange refresh token for new access token.
    
    Refresh token remains valid until expiration (7 days).
    """
    # Verify refresh token
    user = auth_svc.verify_refresh_token(session, data.refresh_token)
    
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
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=data.refresh_token,  # Same refresh token
        token_type="bearer",
        expires_in=config.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/logout", response_model=MessageResponse)
def logout(
    data: RefreshTokenRequest,
    session: Session = Depends(get_session),
):
    """
    Revoke refresh token (logout).
    
    Access token will remain valid until expiration (15min),
    but cannot be refreshed after logout.
    """
    success = auth_svc.revoke_refresh_token(session, data.refresh_token)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Refresh token not found",
        )
    
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