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
        "min": 1,
        "description": "Hours between new-release checks for each followed artist",
    },
    "scheduler.job_cleanup_days": {
        "value": 3,
        "type": "int",
        "min": 1,
        "description": "Days to keep completed jobs",
    },
    "scheduler.token_cleanup_days": {
        "value": 1,
        "type": "int",
        "min": 1,
        "description": "Days between expired token cleanup",
    },
    "scheduler.lyrics_retry_interval_hours": {
        "value": 24,
        "type": "int",
        "min": 1,
        "description": "Hours between lyrics recovery/upgrade checks",
    },
    "scheduler.chart_sync_interval_hours": {
        "value": 168,
        "type": "int",
        "min": 1,
        "description": "Hours between re-syncs of each followed chart",
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
        "min": 1,
        "description": "Maximum concurrent downloads",
    },

    # Feature flags
    "features.lyrics_enabled": {
        "value": True,
        "type": "bool",
        "description": "Enable automatic lyrics download with LRCLIB",
    },
    "features.synced_lyrics_only": {
        "value": True,
        "type": "bool",
        "description": "Only keep synced lyrics (reject plain/unsynced lyrics)",
    },
    "features.charts_enabled": {
        "value": True,
        "type": "bool",
        "description": "Enable charts import feature",
    },

    # YTMusic API
    "ytmusic.language": {
        "value": "en",
        "type": "string",
        "description": "Language code for localized YTMusic responses (artist bios, album descriptions, etc.)",
        "allowed_values": [
            {"value": "ar", "label": "Arabic"},
            {"value": "de", "label": "German"},
            {"value": "en", "label": "English"},
            {"value": "es", "label": "Spanish"},
            {"value": "fr", "label": "French"},
            {"value": "hi", "label": "Hindi"},
            {"value": "it", "label": "Italian"},
            {"value": "ja", "label": "Japanese"},
            {"value": "ko", "label": "Korean"},
            {"value": "nl", "label": "Dutch"},
            {"value": "pt", "label": "Portuguese"},
            {"value": "ru", "label": "Russian"},
            {"value": "tr", "label": "Turkish"},
            {"value": "ur", "label": "Urdu"},
            {"value": "zh_CN", "label": "Chinese (Mainland)"},
            {"value": "zh_TW", "label": "Chinese (Taiwan)"},
        ],
    },
}


def get_allowed_values(key: str) -> Optional[List[Dict[str, str]]]:
    """Return the allowed {value, label} options for a setting key, or None if unconstrained."""
    config = DEFAULT_SETTINGS.get(key)
    if not config:
        return None
    values = config.get("allowed_values")
    return list(values) if values else None


def get_min_value(key: str) -> Optional[int]:
    """Return the lower bound for an int setting, or None if unconstrained."""
    config = DEFAULT_SETTINGS.get(key)
    if not config:
        return None
    return config.get("min")


def validate_value(key: str, setting_type: str, value: Any) -> Any:
    """
    Check `value` against the constraints declared for `key` and return it
    coerced to the setting's type. Raises ValueError on a bad value.
    """
    allowed = get_allowed_values(key)
    if allowed is not None:
        valid = [opt["value"] for opt in allowed]
        if str(value) not in valid:
            raise ValueError(
                f"Invalid value for {key}: must be one of {', '.join(valid)}"
            )

    if setting_type == "int":
        if isinstance(value, bool) or value is None:
            raise ValueError(f"Invalid value for {key}: must be an integer")
        if isinstance(value, float) and not value.is_integer():
            raise ValueError(f"Invalid value for {key}: must be an integer")
        try:
            value = int(value)
        except (TypeError, ValueError):
            raise ValueError(f"Invalid value for {key}: must be an integer")
        minimum = get_min_value(key)
        if minimum is not None and value < minimum:
            raise ValueError(f"Invalid value for {key}: must be at least {minimum}")

    elif setting_type == "bool":
        if not isinstance(value, bool):
            raise ValueError(f"Invalid value for {key}: must be true or false")

    return value


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
    commit: bool = True,
) -> Setting:
    """
    Update or create a setting.
    
    Args:
        session: Database session
        key: Setting key
        value: New value (will be type-converted based on setting type)
        user_id: User making the change (for audit)
        commit: Whether to commit immediately (callers batching several
            changes in one transaction pass False)
    
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

    value = validate_value(key, setting.type, value)
    setting.set_value(value)
    setting.updated_at = now_utc()
    setting.updated_by = user_id
    
    session.add(setting)
    if commit:
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