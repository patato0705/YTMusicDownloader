# backend/secrets.py
"""
Manage security-sensitive configuration (JWT secret, etc).
Generates and persists secrets to a JSON file on first startup.
"""
from __future__ import annotations
import json
import logging
import secrets
from pathlib import Path
from typing import Dict, Any

from . import config

logger = logging.getLogger("secrets")

SECRETS_FILE = config.CONFIG_DIR / "secrets.json"


def generate_jwt_secret() -> str:
    """Generate a cryptographically secure JWT secret key"""
    return secrets.token_urlsafe(64)


def load_secrets() -> Dict[str, Any]:
    """
    Load secrets from file. If file doesn't exist, generate and save defaults.
    
    Returns:
        Dict with at minimum: {"jwt_secret": "..."}
    """
    if not SECRETS_FILE.exists():
        logger.info("Secrets file not found, generating new secrets")
        return _generate_and_save_secrets()
    
    try:
        with open(SECRETS_FILE, "r") as f:
            data = json.load(f)
        
        # Validate required keys
        if not data.get("jwt_secret"):
            logger.warning("jwt_secret missing from secrets file, regenerating")
            return _generate_and_save_secrets()
        
        logger.info("Loaded secrets from %s", SECRETS_FILE)
        return data
    
    except Exception as e:
        logger.exception(f"Failed to load secrets file: {e}")
        logger.warning("Regenerating secrets")
        return _generate_and_save_secrets()


def _generate_and_save_secrets() -> Dict[str, Any]:
    """Generate fresh secrets and save to file"""
    secrets_data = {
        "jwt_secret": generate_jwt_secret(),
        # Add other secrets here as needed
        # "api_key": secrets.token_urlsafe(32),
    }
    
    try:
        # Ensure config directory exists
        config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        
        # Write with restricted permissions (readable only by owner)
        with open(SECRETS_FILE, "w") as f:
            json.dump(secrets_data, f, indent=2)
        
        # Set file permissions to 600 (owner read/write only) on Unix
        try:
            SECRETS_FILE.chmod(0o600)
        except Exception:
            pass  # Windows doesn't support this
        
        logger.info("Generated and saved new secrets to %s", SECRETS_FILE)
        logger.warning(
            "⚠️  IMPORTANT: Backup %s - losing this file will invalidate all JWT tokens!",
            SECRETS_FILE
        )
        
        return secrets_data
    
    except Exception as e:
        logger.exception(f"Failed to save secrets: {e}")
        # Return generated secrets even if save failed (so app can start)
        return secrets_data


def get_jwt_secret() -> str:
    """Get JWT secret key (loads from file if needed)"""
    return load_secrets()["jwt_secret"]


# Load secrets on module import
_SECRETS = load_secrets()


def get_secret(key: str, default: Any = None) -> Any:
    """Get a secret value by key"""
    return _SECRETS.get(key, default)