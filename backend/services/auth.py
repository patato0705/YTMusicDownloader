# backend/services/auth.py
"""
Authentication service - handles user auth, JWT tokens, password hashing.

Functions:
- hash_password() - Hash password using bcrypt
- verify_password() - Verify password against hash
- create_access_token() - Generate JWT access token
- create_refresh_token() - Generate and store refresh token
- verify_access_token() - Decode and validate access token
- verify_refresh_token() - Verify refresh token and return user
- revoke_refresh_token() - Invalidate refresh token (logout)
- cleanup_expired_tokens() - Remove expired tokens from database
- authenticate_user() - Verify username/password
- create_user() - Register new user
- get_user_by_username() - Fetch user by username
- get_user_by_email() - Fetch user by email
- get_user_by_id() - Fetch user by ID
- update_last_login() - Update user's last_login_at
- ensure_first_admin() - Create first admin user on startup
"""
from __future__ import annotations
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import bcrypt
import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import User, RefreshToken
from ..time_utils import now_utc
from .. import config

logger = logging.getLogger("services.auth")


# ============================================================================
# PASSWORD HASHING
# ============================================================================

def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    if not password:
        raise ValueError("Password cannot be empty")
    
    salt = bcrypt.gensalt(rounds=config.BCRYPT_ROUNDS)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash"""
    if not password or not password_hash:
        return False
    
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception as e:
        logger.exception(f"Password verification failed: {e}")
        return False


# ============================================================================
# JWT TOKEN MANAGEMENT
# ============================================================================

def create_access_token(user_id: int, username: str, role: str) -> str:
    """
    Create a JWT access token.
    
    Payload:
    - sub: user_id
    - username: username
    - role: user role
    - exp: expiration timestamp
    - iat: issued at timestamp
    """
    now = now_utc()
    expires = now + timedelta(minutes=config.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "exp": expires,
        "iat": now,
    }
    
    token = jwt.encode(payload, config.JWT_SECRET_KEY, algorithm=config.JWT_ALGORITHM)
    return token


def verify_access_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decode and verify JWT access token.
    
    Returns:
        Payload dict with user_id, username, role if valid
        None if invalid/expired
    """
    try:
        payload = jwt.decode(
            token,
            config.JWT_SECRET_KEY,
            algorithms=[config.JWT_ALGORITHM]
        )
        
        return {
            "user_id": int(payload["sub"]),
            "username": payload["username"],
            "role": payload["role"],
        }
    except jwt.ExpiredSignatureError:
        logger.debug("Access token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.debug(f"Invalid access token: {e}")
        return None
    except Exception as e:
        logger.exception(f"Token verification error: {e}")
        return None


def create_refresh_token(session: Session, user_id: int) -> str:
    """
    Create and store a refresh token in the database.
    
    Returns:
        Refresh token string
    """
    token = secrets.token_urlsafe(64)
    expires = now_utc() + timedelta(days=config.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    
    refresh_token = RefreshToken(
        token=token,
        user_id=user_id,
        expires_at=expires,
        created_at=now_utc(),
        revoked=False,
    )
    
    session.add(refresh_token)
    session.commit()
    session.refresh(refresh_token)
    
    logger.debug(f"Created refresh token for user {user_id}")
    return token


def verify_refresh_token(session: Session, token: str) -> Optional[User]:
    """
    Verify refresh token and return associated user.
    
    Returns:
        User instance if valid
        None if invalid/expired/revoked
    """
    stmt = select(RefreshToken).where(RefreshToken.token == token)
    refresh_token = session.execute(stmt).scalars().first()
    
    if not refresh_token:
        logger.debug("Refresh token not found")
        return None
    
    if not refresh_token.is_valid():
        logger.debug("Refresh token invalid or expired")
        return None
    
    # Get associated user
    user = session.get(User, refresh_token.user_id)
    if not user or not user.is_active:
        logger.debug(f"User {refresh_token.user_id} not found or inactive")
        return None
    
    return user


def revoke_refresh_token(session: Session, token: str) -> bool:
    """
    Revoke a refresh token (logout).
    
    Returns:
        True if revoked, False if not found
    """
    stmt = select(RefreshToken).where(RefreshToken.token == token)
    refresh_token = session.execute(stmt).scalars().first()
    
    if not refresh_token:
        return False
    
    refresh_token.revoked = True
    session.add(refresh_token)
    session.commit()
    
    logger.info(f"Revoked refresh token for user {refresh_token.user_id}")
    return True


def cleanup_expired_tokens(session: Session) -> int:
    """
    Delete expired refresh tokens from database.
    Call periodically to prevent bloat.
    
    Returns:
        Number of tokens deleted
    """
    now = now_utc()
    stmt = select(RefreshToken).where(RefreshToken.expires_at < now)
    expired_tokens = session.execute(stmt).scalars().all()
    
    count = len(expired_tokens)
    for token in expired_tokens:
        session.delete(token)
    
    session.commit()
    
    if count > 0:
        logger.info(f"Cleaned up {count} expired refresh tokens")
    
    return count


# ============================================================================
# USER AUTHENTICATION & LOOKUP
# ============================================================================

def get_user_by_username(session: Session, username: str) -> Optional[User]:
    """Fetch user by username (case-insensitive)"""
    stmt = select(User).where(User.username.ilike(username))
    return session.execute(stmt).scalars().first()


def get_user_by_email(session: Session, email: str) -> Optional[User]:
    """Fetch user by email (case-insensitive)"""
    stmt = select(User).where(User.email.ilike(email))
    return session.execute(stmt).scalars().first()


def get_user_by_id(session: Session, user_id: int) -> Optional[User]:
    """Fetch user by ID"""
    return session.get(User, user_id)


def authenticate_user(session: Session, username: str, password: str) -> Optional[User]:
    """
    Authenticate user with username/password.
    
    Returns:
        User instance if valid credentials
        None if invalid
    """
    user = get_user_by_username(session, username)
    
    if not user:
        logger.debug(f"Authentication failed: user '{username}' not found")
        return None
    
    if not user.is_active:
        logger.debug(f"Authentication failed: user '{username}' is inactive")
        return None
    
    if not verify_password(password, user.password_hash):
        logger.debug(f"Authentication failed: invalid password for '{username}'")
        return None
    
    logger.info(f"User '{username}' authenticated successfully")
    return user


def update_last_login(session: Session, user_id: int) -> None:
    """Update user's last_login_at timestamp"""
    user = session.get(User, user_id)
    if user:
        user.last_login_at = now_utc()
        session.add(user)
        session.commit()


# ============================================================================
# USER REGISTRATION
# ============================================================================

def create_user(
    session: Session,
    username: str,
    email: str,
    password: str,
    role: str = config.ROLE_VISITOR,
) -> User:
    """
    Create a new user.
    
    Args:
        session: SQLAlchemy session
        username: Unique username
        email: Unique email address
        password: Plain text password (will be hashed)
        role: User role (default: visitor)
    
    Returns:
        Created User instance
    
    Raises:
        ValueError: If username/email already exists or invalid role
    """
    # Validate inputs
    if not username or not email or not password:
        raise ValueError("Username, email, and password are required")
    
    if role not in config.VALID_ROLES:
        raise ValueError(f"Invalid role: {role}. Must be one of {config.VALID_ROLES}")
    
    # Check for existing username
    if get_user_by_username(session, username):
        raise ValueError(f"Username '{username}' already exists")
    
    # Check for existing email
    if get_user_by_email(session, email):
        raise ValueError(f"Email '{email}' already exists")
    
    # Hash password
    password_hash = hash_password(password)
    
    # Create user
    user = User(
        username=username,
        email=email,
        password_hash=password_hash,
        role=role,
        is_active=True,
        created_at=now_utc(),
    )
    
    session.add(user)
    session.commit()
    session.refresh(user)
    
    logger.info(f"Created user: {username} (role={role})")
    return user


# ============================================================================
# FIRST-TIME SETUP
# ============================================================================

def ensure_first_admin(session: Session) -> None:
    """
    Create first admin user if no users exist.
    Called on app startup.
    """
    # Check if any users exist
    stmt = select(User).limit(1)
    existing_user = session.execute(stmt).scalars().first()
    
    if existing_user:
        logger.debug("Users already exist, skipping first admin creation")
        return
    
    # Create first admin
    try:
        admin = create_user(
            session=session,
            username=config.FIRST_ADMIN_USERNAME,
            email=config.FIRST_ADMIN_EMAIL,
            password=config.FIRST_ADMIN_PASSWORD,
            role=config.ROLE_ADMINISTRATOR,
        )
        logger.info(f"Created first admin user: {admin.username}")
        logger.warning(
            f"DEFAULT ADMIN CREATED! Username: {admin.username}, "
            f"Password: {config.FIRST_ADMIN_PASSWORD} - CHANGE IMMEDIATELY!"
        )
    except Exception as e:
        logger.exception(f"Failed to create first admin user: {e}")