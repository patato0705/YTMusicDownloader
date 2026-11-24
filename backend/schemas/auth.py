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


# bcrypt reads at most 72 bytes of a password, and bcrypt 5 refuses longer
# ones outright rather than ignoring the rest. In bytes: an accented letter
# takes two, most emoji four.
PASSWORD_MAX_BYTES = 72


def _check_password_bytes(v: str) -> str:
    if len(v.encode("utf-8")) > PASSWORD_MAX_BYTES:
        raise ValueError(f"Password must be at most {PASSWORD_MAX_BYTES} bytes (fewer characters with accents or emoji)")
    return v


# A password being set, wherever (registration, admin panel, change password, CLI)
NewPassword = Annotated[str, Field(min_length=8), AfterValidator(_check_password_bytes)]


class LoginRequest(BaseModel):
    # Unbounded on purpose: a name over 64 characters or a password over 72
    # bytes is just a wrong one (a 422 would be the form's only odd error).
    # Neither is kept: the throttle hashes the name (login_throttle).
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: Username
    password: NewPassword


class CreateUserRequest(RegisterRequest):
    """Request to create a new user (admin only)"""
    role: Literal["administrator", "member", "visitor"]


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: NewPassword


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
    # The welcome tour was closed (it opens until then)
    onboarding_seen: bool = False
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
