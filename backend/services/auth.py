# backend/services/auth.py
"""
Authentication service - handles user auth, JWT tokens, password hashing.

Functions:
- hash_password() - Hash password using bcrypt
- verify_password() - Verify password against hash
- create_access_token() - Generate JWT access token
- refresh_token_lifetime() - How long a sign-in lasts (shorter for single sign-on)
- create_refresh_token() - Generate and store refresh token (hashed)
- verify_access_token() - Decode and validate access token
- rotate_refresh_token() - Use a refresh token: replaced by a new one, replays revoke the sign-in
- revoke_refresh_family() - Revoke every token of a sign-in
- create_device_token() / verify_device_token() - Known-browser marker for login throttling
- token_revoked() - Whether a token predates the user's tokens_valid_after or the account
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
import hashlib
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple

import bcrypt
import jwt
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import User, RefreshToken
from ..secrets import jwt_secret
from ..settings import get_setting
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
        logger.exception("Password verification failed: %s", e)
        return False


# ============================================================================
# JWT TOKEN MANAGEMENT
# ============================================================================

def create_access_token(user: User) -> str:
    """
    Create a JWT access token for the user.

    Payload:
    - sub: user id
    - typ: "access" (so other tokens signed with the same key, like device
      tokens, can't be used as one)
    - exp: expiration timestamp
    - iat: issued at timestamp (checked against token_revoked())
    """
    now = now_utc()
    payload = {
        "sub": str(user.id),
        "typ": "access",
        "exp": now + timedelta(minutes=config.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
        "iat": now,
    }
    return jwt.encode(payload, jwt_secret(), algorithm=config.JWT_ALGORITHM)


def verify_access_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decode and verify JWT access token.

    Returns:
        {"user_id", "issued_at"} if valid, None if invalid/expired

    Callers must still reject it if token_revoked() says so (needs the user).
    """
    try:
        payload = jwt.decode(token, jwt_secret(), algorithms=[config.JWT_ALGORITHM])
        if payload.get("typ") != "access":
            logger.debug("Token is not an access token")
            return None
        return {"user_id": int(payload["sub"]), "issued_at": int(payload["iat"])}
    except jwt.ExpiredSignatureError:
        logger.debug("Access token expired")
    except (jwt.InvalidTokenError, KeyError, ValueError, TypeError) as e:
        logger.debug("Invalid access token: %s", e)
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
    return jwt.encode(payload, jwt_secret(), algorithm=config.JWT_ALGORITHM)


def verify_device_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decode a device token.

    Returns:
        {"user_id", "jti", "issued_at"} if valid
        None if invalid/expired/not a device token

    Callers must still reject it if token_revoked() says so (needs the user).
    """
    try:
        payload = jwt.decode(token, jwt_secret(), algorithms=[config.JWT_ALGORITHM])
        if payload.get("typ") != "device":
            return None
        return {"user_id": int(payload["sub"]), "jti": str(payload["jti"]), "issued_at": int(payload["iat"])}
    except (jwt.InvalidTokenError, KeyError, ValueError, TypeError):
        return None


def token_revoked(user: User, issued_at: int) -> bool:
    """
    True if a token issued at `issued_at` (JWT "iat", whole seconds) was
    issued before the user's tokens_valid_after, or before the account
    itself was created: then it was issued to a deleted account whose id
    this one reuses. A token from the very second of the cutoff is still
    accepted: "iat" can't tell before from after within it.
    """
    for cutoff in (user.tokens_valid_after, user.created_at):
        cutoff = ensure_timezone_aware(cutoff)
        if cutoff is not None and issued_at < int(cutoff.timestamp()):
            return True
    return False


# How long a refresh token that was just replaced still works: two tabs
# refreshing at once both send it, and only the first one rotates it
REFRESH_REUSE_GRACE = timedelta(seconds=30)


def _hash_token(token: str) -> str:
    """
    What the database keeps of a refresh token. A plain hash is enough: the
    token is 64 random bytes, nothing to guess, unlike a password.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _find_refresh_token(session: Session, token: str) -> Optional[RefreshToken]:
    stmt = select(RefreshToken).where(RefreshToken.token_hash == _hash_token(token))
    return session.execute(stmt).scalars().first()


def refresh_token_lifetime(session: Session, user: User) -> timedelta:
    """
    How long a sign-in lasts before signing in again. Shorter for single
    sign-on accounts (auth.oidc_session_hours): the provider's role changes
    and deactivations only reach this app when they sign in.
    """
    if user.is_oidc:
        return timedelta(hours=get_setting(session, "auth.oidc_session_hours"))
    return timedelta(days=config.JWT_REFRESH_TOKEN_EXPIRE_DAYS)


def create_refresh_token(session: Session, user_id: int, expires_at: datetime) -> str:
    """
    Create and store the refresh token of a new sign-in, which starts a
    family (only its hash is stored). Commits.

    Returns:
        Refresh token string
    """
    _, token = _add_refresh_token(session, user_id, expires_at, None)
    session.commit()
    logger.debug("Created refresh token for user %s", user_id)
    return token


def _add_refresh_token(
    session: Session, user_id: int, expires_at: datetime, family_id: Optional[str],
) -> Tuple[RefreshToken, str]:
    """A new refresh token's row (flushed, so it has an id) and the token. Doesn't commit."""
    token = secrets.token_urlsafe(64)
    row = RefreshToken(
        token_hash=_hash_token(token),
        family_id=family_id or secrets.token_hex(16),
        user_id=user_id,
        expires_at=expires_at,
        created_at=now_utc(),
        revoked=False,
    )
    session.add(row)
    session.flush()
    return row, token


def rotate_refresh_token(session: Session, token: str) -> Optional[Tuple[User, Optional[str], datetime]]:
    """
    Use a refresh token: it's replaced by a new one of the same sign-in,
    expiring at the same time (a sign-in never outlives its first
    lifetime). Commits.

    A token already replaced is accepted without a new one for
    REFRESH_REUSE_GRACE (another tab got there first and the browser
    already holds its replacement). Past that, it depends on its
    replacement:
    - never used: most likely the response carrying it never reached the
      browser (network drop, tab closed). The token is replaced again, and
      the unused replacement is marked replaced. Should this have been a
      thief replaying an old copy, the owner presenting that replacement
      later lands in the case below.
    - used: two parties hold tokens of this sign-in, one of them stolen.
      The whole sign-in is revoked, the thief's and the owner's alike.

    Returns:
        (user, the new token, when the sign-in expires) when valid; no new
        token within the grace period
        None if invalid/expired/revoked, or replayed
    """
    refresh_token = _find_refresh_token(session, token)
    if not refresh_token or not refresh_token.is_valid():
        logger.debug("Refresh token unknown, revoked or expired")
        return None

    user = session.get(User, refresh_token.user_id)
    if not user or not user.is_active:
        logger.debug("User %s not found or inactive", refresh_token.user_id)
        return None

    now = now_utc()
    expires_at = ensure_timezone_aware(refresh_token.expires_at)
    if refresh_token.replaced_at is not None:
        if now - ensure_timezone_aware(refresh_token.replaced_at) <= REFRESH_REUSE_GRACE:
            return user, None, expires_at
        successor = session.get(RefreshToken, refresh_token.replaced_by_id) if refresh_token.replaced_by_id else None
        if successor is None or successor.replaced_at is not None or not successor.is_valid():
            revoked = revoke_refresh_family(session, refresh_token.family_id)
            session.commit()
            logger.warning(
                "A replaced refresh token of user %s was used again: possible theft, signed out that session (%s token(s))",
                user.username, revoked,
            )
            return None
        # Never used: superseded, with nothing to point to (so presenting
        # it later counts as the reuse above)
        logger.info("Refresh token of user %s replaced again: its replacement was never used", user.username)
        successor.replaced_at = now

    row, new_token = _add_refresh_token(session, user.id, expires_at, refresh_token.family_id)
    refresh_token.replaced_at = now
    refresh_token.replaced_by_id = row.id
    session.commit()
    return user, new_token, expires_at


def revoke_refresh_family(session: Session, family_id: str) -> int:
    """Revoke every token of a sign-in. Doesn't commit. Returns how many were still valid."""
    stmt = select(RefreshToken).where(RefreshToken.family_id == family_id, RefreshToken.revoked.is_(False))
    tokens = session.execute(stmt).scalars().all()
    for t in tokens:
        t.revoked = True
    return len(tokens)


def revoke_refresh_token(session: Session, token: str) -> bool:
    """
    Sign out the session a refresh token belongs to (logout): its whole
    family, older tokens included. Commits.

    Returns:
        True if revoked, False if not found
    """
    refresh_token = _find_refresh_token(session, token)
    if not refresh_token:
        return False

    revoke_refresh_family(session, refresh_token.family_id)
    session.commit()

    logger.info("Revoked refresh token for user %s", refresh_token.user_id)
    return True


def cleanup_expired_tokens(session: Session) -> int:
    """Delete expired refresh tokens. Commits. Returns how many."""
    deleted = session.execute(delete(RefreshToken).where(RefreshToken.expires_at < now_utc())).rowcount
    session.commit()
    return deleted


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
        logger.debug("Authentication failed: user '%s' not found", username)
        return None

    if not user.is_active:
        verify_password(password, _dummy_password_hash())
        logger.debug("Authentication failed: user '%s' is inactive", username)
        return None

    if not user.password_hash:
        # Single sign-on account: same timing as a wrong password
        verify_password(password, _dummy_password_hash())
        logger.debug("Authentication failed: '%s' has no password (single sign-on)", username)
        return None

    if not verify_password(password, user.password_hash):
        logger.debug("Authentication failed: invalid password for '%s'", username)
        return None

    logger.info("User '%s' authenticated successfully", username)
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

    keep = _find_refresh_token(session, keep_refresh_token) if keep_refresh_token else None
    stmt = select(RefreshToken).where(
        RefreshToken.user_id == user.id,
        RefreshToken.revoked.is_(False),
    )
    revoked = 0
    for token in session.execute(stmt).scalars().all():
        # The whole family of the kept session: its older tokens stay
        # recognisable as replaced ones (see rotate_refresh_token)
        if keep is not None and token.family_id == keep.family_id:
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

    logger.info("Created user: %s (role=%s)", username, role)
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

    if not config.PASSWORD_LOGIN_ENABLED:
        # A password account couldn't sign in; the first admin comes from SSO
        logger.warning(
            "No users yet and password sign-in is disabled. To get a first administrator: "
            "set OIDC_ADMIN_GROUP to a provider group you're in, or sign in once with SSO "
            "and run `python -m backend.cli set-role <username> administrator` (see README)."
        )
        return

    # Create first admin. Generated, never a known default: whoever reaches
    # a fresh instance first would otherwise get an administrator account.
    # It ends up in the log files, which is why it only works to choose a
    # new password (must_change_password, enforced by dependencies.py).
    password = generate_temporary_password()
    try:
        admin = create_user(
            session=session,
            username=config.FIRST_ADMIN_USERNAME,
            password=password,
            role=config.ROLE_ADMINISTRATOR,
            must_change_password=True,
        )
        logger.warning(
            "Created the first administrator. Sign in as %r with the password %s "
            "(you'll be asked to choose a new one right away)",
            admin.username, password,
        )
    except Exception:
        logger.exception("Failed to create first admin user")
