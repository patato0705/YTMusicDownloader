# backend/secrets.py
"""
The JWT signing key, generated on first use and kept in
CONFIG_DIR/secrets.json so sessions survive restarts. Only the web process
signs and checks tokens, so only it ever reads (or creates) the file.
"""
from __future__ import annotations
import functools
import json
import logging
import os
import secrets

from . import config

logger = logging.getLogger("secrets")


@functools.cache
def jwt_secret() -> str:
    """
    The key, read once per process. Raises if a new one can't be saved:
    an unsaved key would sign everyone out at every restart.
    """
    path = config.CONFIG_DIR / "secrets.json"
    try:
        secret = json.loads(path.read_text(encoding="utf-8")).get("jwt_secret")
        if secret:
            return secret
        logger.warning("No jwt_secret in %s, generating a new one", path)
    except FileNotFoundError:
        # First start: the "Saved a new JWT signing key" line below says it all
        logger.debug("No %s yet, generating the JWT signing key", path)
    except (OSError, ValueError, AttributeError) as e:
        logger.warning("Unreadable %s (%s), generating a new key: every session is signed out", path, e)

    secret = secrets.token_urlsafe(64)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Readable by the app's user only, from the moment it exists
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"jwt_secret": secret}, f, indent=2)
    logger.info("Saved a new JWT signing key to %s: losing this file signs everyone out", path)
    return secret
