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
- create_device_token() / verify_device_token() - Known-browser marker for login throttling
- token_revoked() - Whether a token predates the user's tokens_valid_after
- revoke_refresh_token() - Invalidate refresh token (logout)
- cleanup_expired_tokens() - Remove expired tokens from database
- authenticate_user() - Verify username/password
- create_user() - Register new user
- get_user_by_username() - Fetch user by username
- get_user_by_id() - Fetch user by ID
- update_last_login() - Update user's last_login_at
- revoke_sessions() - Sign a user out everywhere (but one session)
- change_password() - Set a new password and sign out the user's other sessions
- generate_temporary_password() - Random password for resets
- ensure_first_admin() - Create first admin user on startup

Exceptions:
- UsernameTakenError - raised by create_user() on conflicts
  (subclass ValueError so generic handlers keep working)
"""
from __future__ import annotations
import functools
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import bcrypt
import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import User, RefreshToken
from ..time_utils import now_utc, ensure_timezone_aware
from .. import config

logger = logging.getLogger("services.auth")


class UsernameTakenError(ValueError):
    """Username is already registered."""


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
    - typ: "access" (so other tokens signed with the same key, like device
      tokens, can't be used as one)
    - exp: expiration timestamp
    - iat: issued at timestamp
    """
    now = now_utc()
    expires = now + timedelta(minutes=config.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "typ": "access",
        "exp": expires,
        "iat": now,
    }
    
    token = jwt.encode(payload, config.JWT_SECRET_KEY, algorithm=config.JWT_ALGORITHM)
    return token


def verify_access_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decode and verify JWT access token.
    
    Returns:
        Payload dict with user_id, username, role, issued_at if valid
        None if invalid/expired

    Callers must still reject it if token_revoked() says so (needs the user).
    """
    try:
        payload = jwt.decode(
            token,
            config.JWT_SECRET_KEY,
            algorithms=[config.JWT_ALGORITHM]
        )
        if payload.get("typ") != "access":
            logger.debug("Token is not an access token")
            return None
        
        return {
            "user_id": int(payload["sub"]),
            "username": payload["username"],
            "role": payload["role"],
            "issued_at": int(payload["iat"]),
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


def create_device_token(user_id: int) -> str:
    """
    Create a device token: proof that this browser has signed in to this
    account before. It authenticates nothing; login uses it to give known
    browsers their own failed-attempt allowance (see services/login_throttle).

    Payload:
    - sub: user_id
    - jti: random id, the browser's throttling bucket
    - typ: "device"
    - exp: expiration timestamp
    - iat: issued at timestamp (checked against token_revoked())
    """
    now = now_utc()
    payload = {
        "sub": str(user_id),
        "jti": secrets.token_urlsafe(16),
        "typ": "device",
        "exp": now + timedelta(days=config.DEVICE_TOKEN_EXPIRE_DAYS),
        "iat": now,
    }
    return jwt.encode(payload, config.JWT_SECRET_KEY, algorithm=config.JWT_ALGORITHM)


def verify_device_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decode a device token.

    Returns:
        {"user_id", "jti", "issued_at"} if valid
        None if invalid/expired/not a device token

    Callers must still reject it if token_revoked() says so (needs the user).
    """
    try:
        payload = jwt.decode(token, config.JWT_SECRET_KEY, algorithms=[config.JWT_ALGORITHM])
        if payload.get("typ") != "device":
            return None
        return {"user_id": int(payload["sub"]), "jti": str(payload["jti"]), "issued_at": int(payload["iat"])}
    except (jwt.InvalidTokenError, KeyError, ValueError, TypeError):
        return None


def token_revoked(user: User, issued_at: int) -> bool:
    """
    True if a token issued at `issued_at` (JWT "iat", whole seconds) was
    issued before the user's tokens_valid_after. A token from the very
    second of the cutoff is still accepted: "iat" can't tell before from
    after within it.
    """
    cutoff = ensure_timezone_aware(user.tokens_valid_after)
    return cutoff is not None and issued_at < int(cutoff.timestamp())


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
    """Fetch user by username (case-insensitive via the column's NOCASE collation)"""
    # Plain equality, not ilike: LIKE treats "%" and "_" as wildcards
    stmt = select(User).where(User.username == username)
    return session.execute(stmt).scalars().first()


def get_user_by_id(session: Session, user_id: int) -> Optional[User]:
    """Fetch user by ID"""
    return session.get(User, user_id)


@functools.cache
def _dummy_password_hash() -> str:
    """A hash no password matches, computed once at the configured cost."""
    return hash_password(secrets.token_urlsafe(32))


def authenticate_user(session: Session, username: str, password: str) -> Optional[User]:
    """
    Authenticate user with username/password.
    
    Returns:
        User instance if valid credentials
        None if invalid
    """
    user = get_user_by_username(session, username)
    
    if not user:
        # Spend the same bcrypt time as a real check, so response times
        # don't reveal which usernames exist
        verify_password(password, _dummy_password_hash())
        logger.debug(f"Authentication failed: user '{username}' not found")
        return None
    
    if not user.is_active:
        verify_password(password, _dummy_password_hash())
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


def revoke_sessions(session: Session, user: User, keep_refresh_token: Optional[str] = None) -> int:
    """
    Sign the user out everywhere but `keep_refresh_token`'s session: their
    refresh tokens are revoked, and access/device tokens issued so far stop
    being accepted (tokens_valid_after). Doesn't commit.

    Returns:
        Number of refresh tokens revoked
    """
    user.tokens_valid_after = now_utc().replace(microsecond=0)
    session.add(user)

    stmt = select(RefreshToken).where(
        RefreshToken.user_id == user.id,
        RefreshToken.revoked.is_(False),
    )
    revoked = 0
    for token in session.execute(stmt).scalars().all():
        if keep_refresh_token is not None and token.token == keep_refresh_token:
            continue
        token.revoked = True
        session.add(token)
        revoked += 1
    return revoked


def change_password(
    session: Session,
    user: User,
    new_password: str,
    keep_refresh_token: Optional[str] = None,
    must_change_password: bool = False,
) -> int:
    """
    Set a new password and sign the user out everywhere else: every refresh
    token but `keep_refresh_token` (the session making the change) is
    revoked, and access/device tokens issued so far stop being accepted
    (tokens_valid_after). The caller hands the current session fresh ones.

    Used for resets too (no session kept): pass must_change_password=True
    when the new password is a temporary one someone else knows.

    Returns:
        Number of refresh tokens revoked
    """
    user.password_hash = hash_password(new_password)
    user.must_change_password = must_change_password
    session.add(user)
    revoked = revoke_sessions(session, user, keep_refresh_token)

    session.commit()
    session.refresh(user)
    return revoked


# No 0/O, 1/l/I: temporary passwords get read out or retyped by hand
_TEMP_PASSWORD_ALPHABET = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_temporary_password() -> str:
    """Random password like 7hKq-3mPz-Xw9t-Ld2c (~90 bits)."""
    groups = ("".join(secrets.choice(_TEMP_PASSWORD_ALPHABET) for _ in range(4)) for _ in range(4))
    return "-".join(groups)


# ============================================================================
# USER REGISTRATION
# ============================================================================

def create_user(
    session: Session,
    username: str,
    password: str,
    role: str = config.ROLE_VISITOR,
    must_change_password: bool = False,
) -> User:
    """
    Create a new user.
    
    Args:
        session: SQLAlchemy session
        username: Unique username
        password: Plain text password (will be hashed)
        must_change_password: Password is a temporary one (generated, or
            from the environment for the first admin)
        role: User role (default: visitor)
    
    Returns:
        Created User instance
    
    Raises:
        UsernameTakenError: If username already exists
        ValueError: If inputs are missing or role is invalid
    """
    # Validate inputs
    if not username or not password:
        raise ValueError("Username and password are required")
    
    if role not in config.VALID_ROLES:
        raise ValueError(f"Invalid role: {role}. Must be one of {config.VALID_ROLES}")
    
    # Check for existing username
    if get_user_by_username(session, username):
        raise UsernameTakenError(f"Username '{username}' already exists")
    
    # Hash password
    password_hash = hash_password(password)
    
    # Create user
    user = User(
        username=username,
        password_hash=password_hash,
        role=role,
        is_active=True,
        must_change_password=must_change_password,
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
            password=config.FIRST_ADMIN_PASSWORD,
            role=config.ROLE_ADMINISTRATOR,
            # Even a custom FIRST_ADMIN_PASSWORD sits in plain text in the
            # compose file, so the first sign-in always asks for a new one
            must_change_password=True,
        )
        logger.info(f"Created first admin user: {admin.username}")
        logger.warning(
            f"DEFAULT ADMIN CREATED! Username: {admin.username}, "
            f"Password: {config.FIRST_ADMIN_PASSWORD} - CHANGE IMMEDIATELY!"
        )
    except Exception as e:
        logger.exception(f"Failed to create first admin user: {e}")