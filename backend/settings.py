# backend/settings.py
"""
Application settings management.
Handles default settings and database CRUD operations.
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Setting
from .time_utils import now_utc

logger = logging.getLogger("settings")


# Default settings with descriptions
DEFAULT_SETTINGS = {
    # Scheduler settings
    "scheduler.sync_interval_hours": {
        "value": 6,
        "type": "int",
        "description": "Hours between artist sync checks",
    },
    "scheduler.job_cleanup_days": {
        "value": 3,
        "type": "int",
        "description": "Days to keep completed jobs",
    },
    "scheduler.token_cleanup_days": {
        "value": 1,
        "type": "int",
        "description": "Days between expired token cleanup",
    },
    
    # Registration settings
    "auth.registration_enabled": {
        "value": False,
        "type": "bool",
        "description": "Allow public user registration",
    },
    
    # Download settings
    "download.max_concurrent": {
        "value": 3,
        "type": "int",
        "description": "Maximum concurrent downloads",
    },
    "download.audio_quality": {
        "value": "best",
        "type": "string",
        "description": "Audio quality preference (best, high, medium)",
    },
    
    # Feature flags
    "features.lyrics_enabled": {
        "value": True,
        "type": "bool",
        "description": "Enable automatic lyrics download",
    },
    "features.charts_enabled": {
        "value": True,
        "type": "bool",
        "description": "Enable charts import feature",
    },
}


def ensure_defaults(session: Session) -> None:
    """
    Ensure all default settings exist in database.
    Call on startup.
    """
    for key, config in DEFAULT_SETTINGS.items():
        existing = session.get(Setting, key)
        if not existing:
            setting = Setting(
                key=key,
                type=config["type"],
                description=config["description"],
                updated_at=now_utc(),
            )
            setting.set_value(config["value"])
            session.add(setting)
            logger.debug(f"Created default setting: {key} = {config['value']}")
    
    session.commit()


def get_setting(session: Session, key: str, default: Any = None) -> Any:
    """
    Get a setting value by key.
    Returns typed value (int, bool, str, etc).
    """
    setting = session.get(Setting, key)
    if not setting:
        # Check if it's a default setting
        if key in DEFAULT_SETTINGS:
            return DEFAULT_SETTINGS[key]["value"]
        return default
    
    return setting.get_typed_value()


def set_setting(
    session: Session,
    key: str,
    value: Any,
    user_id: Optional[int] = None,
) -> Setting:
    """
    Update or create a setting.
    
    Args:
        session: Database session
        key: Setting key
        value: New value (will be type-converted based on setting type)
        user_id: User making the change (for audit)
    
    Returns:
        Updated Setting instance
    """
    setting = session.get(Setting, key)
    
    if not setting:
        # Create new setting
        setting = Setting(
            key=key,
            type="string",  # Default type
            updated_at=now_utc(),
            updated_by=user_id,
        )
        
        # Use default type if available
        if key in DEFAULT_SETTINGS:
            setting.type = DEFAULT_SETTINGS[key]["type"]
            setting.description = DEFAULT_SETTINGS[key]["description"]
        
        session.add(setting)
    
    setting.set_value(value)
    setting.updated_at = now_utc()
    setting.updated_by = user_id
    
    session.add(setting)
    session.commit()
    session.refresh(setting)
    
    logger.info(f"Setting updated: {key} = {value} (by user {user_id})")
    
    return setting


def get_all_settings(session: Session) -> List[Dict[str, Any]]:
    """Get all settings as list of dicts"""
    stmt = select(Setting).order_by(Setting.key)
    settings = session.execute(stmt).scalars().all()
    return [s.to_dict() for s in settings]


def delete_setting(session: Session, key: str) -> bool:
    """
    Delete a setting (resets to default if it's a default setting).
    
    Returns:
        True if deleted, False if not found
    """
    setting = session.get(Setting, key)
    if not setting:
        return False
    
    session.delete(setting)
    session.commit()
    
    logger.info(f"Setting deleted: {key}")
    return True