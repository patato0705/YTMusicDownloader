# backend/schemas/auth.py
"""
Pydantic schemas for authentication endpoints.
"""
from __future__ import annotations
from typing import Annotated, Literal, Optional
from datetime import datetime

from pydantic import AfterValidator, BaseModel, Field


# ============================================================================
# REQUEST SCHEMAS
# ============================================================================

def _check_username_characters(v: str) -> str:
    if not (v.isascii() and v.replace("_", "").replace("-", "").isalnum()):
        raise ValueError("Username must contain only letters, numbers, hyphens, and underscores")
    return v


# A username, wherever an account comes from (registration, admin panel,
# CLI, backup import; single sign-on names are reduced to the same rules).
# ASCII only, like the frontend's check: the database compares names
# ignoring case for ASCII only, and look-alike letters from other alphabets
# ("аdmin" with a Cyrillic а) would pass for another account.
Username = Annotated[str, Field(min_length=3, max_length=64), AfterValidator(_check_username_characters)]


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: Username
    password: str = Field(..., min_length=8)


class CreateUserRequest(RegisterRequest):
    """Request to create a new user (admin only)"""
    role: Literal["administrator", "member", "visitor"]


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)


# ============================================================================
# RESPONSE SCHEMAS
# ============================================================================

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    must_change_password: bool = False
    has_password: bool = True
    is_oidc: bool = False
    created_at: datetime
    last_login_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class LoginResponse(BaseModel):
    user: UserResponse
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class TemporaryPasswordResponse(BaseModel):
    """A generated password, shown to the admin once (never stored in clear)"""
    temporary_password: str
