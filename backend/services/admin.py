# backend/services/admin.py
"""
User management for the admin panel and the recovery CLI:
- list_users() - List all users with pagination
- update_user_role() - Change user's role
- activate_user() - Reactivate deactivated user
- deactivate_user() - Deactivate user (soft delete) and sign them out
- delete_user() - Permanently delete user and associated data
"""
from __future__ import annotations
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import User
from .. import config
from . import auth as auth_svc

logger = logging.getLogger("services.admin")


# ============================================================================
# USER MANAGEMENT
# ============================================================================

def list_users(
    session: Session,
    include_inactive: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> list[User]:
    """
    List all users with pagination.

    Args:
        session: SQLAlchemy session
        include_inactive: Include deactivated users
        limit: Max results (default: 100)
        offset: Pagination offset

    Returns:
        List of User instances
    """
    stmt = select(User)
    if not include_inactive:
        stmt = stmt.where(User.is_active.is_(True))
    stmt = stmt.order_by(User.created_at.desc()).limit(limit).offset(offset)
    return list(session.execute(stmt).scalars().all())


def update_user_role(session: Session, user_id: int, new_role: str) -> User:
    """
    Update user's role.

    Args:
        session: SQLAlchemy session
        user_id: User ID to update
        new_role: New role (administrator, member, visitor)

    Returns:
        Updated User instance

    Raises:
        ValueError: If user not found or invalid role
    """
    if new_role not in config.VALID_ROLES:
        raise ValueError(f"Invalid role: {new_role}. Must be one of {config.VALID_ROLES}")

    user = session.get(User, user_id)
    if not user:
        raise ValueError(f"User {user_id} not found")

    old_role = user.role
    user.role = new_role
    session.add(user)
    session.commit()
    session.refresh(user)

    logger.info("Updated user %s role from %s to %s", user_id, old_role, new_role)
    return user


def activate_user(session: Session, user_id: int) -> User:
    """
    Reactivate a deactivated user.

    Args:
        session: SQLAlchemy session
        user_id: User ID to activate

    Returns:
        Activated User instance

    Raises:
        ValueError: If user not found
    """
    user = session.get(User, user_id)
    if not user:
        raise ValueError(f"User {user_id} not found")

    user.is_active = True
    session.add(user)
    session.commit()
    session.refresh(user)

    logger.info("Activated user %s (%s)", user_id, user.username)
    return user


def deactivate_user(session: Session, user_id: int) -> User:
    """
    Deactivate a user (soft delete) and sign them out everywhere.

    Args:
        session: SQLAlchemy session
        user_id: User ID to deactivate

    Returns:
        Deactivated User instance

    Raises:
        ValueError: If user not found
    """
    user = session.get(User, user_id)
    if not user:
        raise ValueError(f"User {user_id} not found")

    user.is_active = False
    auth_svc.revoke_sessions(session, user)
    session.commit()
    session.refresh(user)

    logger.info("Deactivated user %s (%s)", user_id, user.username)
    return user


def delete_user(session: Session, user_id: int) -> bool:
    """
    Permanently delete a user and all associated data.

    This is a hard delete that removes:
    - The user record
    - All refresh tokens, so every session (ON DELETE CASCADE)
    - The artists they like and dismissed from recommendations (CASCADE)
    - All jobs created by user (user_id set to NULL via SET NULL)
    - All settings updated by user (updated_by set to NULL via SET NULL)

    Access tokens already handed out need nothing: they name a user that no
    longer exists, and a token issued before an account was created is
    never accepted for it (services/auth.token_revoked).

    Args:
        session: SQLAlchemy session
        user_id: User ID to delete

    Returns:
        True if deleted successfully

    Raises:
        ValueError: If user not found
    """
    user = session.get(User, user_id)
    if not user:
        raise ValueError(f"User {user_id} not found")

    username = user.username
    # Refresh tokens, likes, dismissals: CASCADE. Jobs, settings, charts, playlists: SET NULL
    session.delete(user)
    session.commit()

    logger.warning("PERMANENTLY DELETED user %s (%s)", user_id, username)
    return True
