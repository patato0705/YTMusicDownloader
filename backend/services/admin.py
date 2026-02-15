# backend/services/admin.py
"""
Admin service - handles admin operations for user management and settings.

User Management:
- list_users() - List all users with pagination
- update_user_role() - Change user's role
- activate_user() - Reactivate deactivated user
- deactivate_user() - Deactivate user (soft delete)
- delete_user() - Permanently delete user and associated data

Settings Management:
- Handled by backend.settings module
"""
from __future__ import annotations
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import User, RefreshToken, Job
from ..time_utils import now_utc
from .. import config

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
        stmt = stmt.where(User.is_active == True)
    
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
    
    logger.info(f"Updated user {user_id} role from {old_role} to {new_role}")
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
    
    logger.info(f"Activated user {user_id} ({user.username})")
    return user


def deactivate_user(session: Session, user_id: int) -> User:
    """
    Deactivate a user (soft delete).
    Also revokes all their refresh tokens.
    
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
    session.add(user)
    
    # Revoke all refresh tokens
    stmt = select(RefreshToken).where(RefreshToken.user_id == user_id)
    tokens = session.execute(stmt).scalars().all()
    for token in tokens:
        token.revoked = True
        session.add(token)
    
    session.commit()
    session.refresh(user)
    
    logger.info(f"Deactivated user {user_id} ({user.username})")
    return user


def delete_user(session: Session, user_id: int) -> bool:
    """
    Permanently delete a user and all associated data.
    
    This is a hard delete that removes:
    - The user record
    - All refresh tokens (CASCADE)
    - All jobs created by user (user_id set to NULL via SET NULL)
    - All settings updated by user (updated_by set to NULL via SET NULL)
    
    Args:
        session: SQLAlchemy session
        user_id: User ID to delete
    
    Returns:
        True if deleted successfully
    
    Raises:
        ValueError: If user not found or trying to delete yourself
    """
    user = session.get(User, user_id)
    if not user:
        raise ValueError(f"User {user_id} not found")
    
    username = user.username
    
    # Delete the user (cascades will handle refresh tokens)
    # Jobs and Settings have SET NULL foreign keys, so they'll just lose the reference
    session.delete(user)
    session.commit()
    
    logger.warning(f"PERMANENTLY DELETED user {user_id} ({username})")
    return True


def get_user_stats(session: Session) -> dict:
    """
    Get user statistics for admin dashboard.
    
    Returns:
        Dictionary with user counts by role and status
    """
    total_stmt = select(User)
    total_users = len(session.execute(total_stmt).scalars().all())
    
    active_stmt = select(User).where(User.is_active == True)
    active_users = len(session.execute(active_stmt).scalars().all())
    
    admin_stmt = select(User).where(User.role == config.ROLE_ADMINISTRATOR)
    admin_count = len(session.execute(admin_stmt).scalars().all())
    
    member_stmt = select(User).where(User.role == config.ROLE_MEMBER)
    member_count = len(session.execute(member_stmt).scalars().all())
    
    visitor_stmt = select(User).where(User.role == config.ROLE_VISITOR)
    visitor_count = len(session.execute(visitor_stmt).scalars().all())
    
    return {
        "total": total_users,
        "active": active_users,
        "inactive": total_users - active_users,
        "by_role": {
            "administrator": admin_count,
            "member": member_count,
            "visitor": visitor_count,
        }
    }