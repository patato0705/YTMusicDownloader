# backend/deps.py
from __future__ import annotations
import logging
import importlib
from typing import Generator, Any, Optional

from sqlalchemy.orm import Session  # <--- import nécessaire pour les annotations de type

logger = logging.getLogger("backend.deps")


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a SQLAlchemy Session.

    Implementation:
      - Delegates to backend.db.get_session() (lazily imported) to avoid import cycles.
      - Yields the session and ensures it is closed.
    """
    try:
        # import lazily to avoid import-time cycles
        from .db import get_session  # type: ignore
    except Exception as e:
        logger.exception("Failed to import backend.db.get_session")
        raise RuntimeError("Database session factory not available") from e

    # get_session is itself a generator that yields a Session
    yield from get_session()  # type: ignore[func-returns-value]


def get_engine() -> Any:
    """
    Helper to access the SQLAlchemy engine.
    Returns the engine object from backend.db or raises if not available.
    """
    try:
        from .db import get_engine as _get_engine  # type: ignore
        return _get_engine()
    except Exception:
        logger.exception("Failed to import/get engine from backend.db")
        raise RuntimeError("Database engine not available")


def get_settings() -> Any:
    """
    Return the settings module (backend.config).

    Currently we expose the module object; if later you want a Pydantic Settings
    object, replace this to return an instance (e.g. ConfigSettings()).
    """
    try:
        cfg = importlib.import_module("backend.config")
        return cfg
    except Exception:
        logger.exception("Failed to import backend.config")
        raise RuntimeError("Settings/config not available")


def get_ytm_adapter() -> Optional[Any]:
    """Return the ytm_service.adapter module."""
    try:
        from backend.ytm_service import adapter
        return adapter
    except Exception:
        logger.debug("ytm_service.adapter not available", exc_info=True)
        return None


def get_ytm_client() -> Optional[Any]:
    """Return the YTMusic client instance."""
    try:
        from backend.ytm_service import client
        if hasattr(client, "get_client"):
            return client.get_client()
        logger.debug("ytm_service.client has no get_client()/get_ytm()")
        return None
    except Exception:
        logger.debug("ytm_service.client not available", exc_info=True)
        return None


def get_jobqueue() -> Optional[Any]:
    """
    Return the jobqueue module (backend.jobs.jobqueue) or None if not available.

    Useful to call jobqueue.enqueue_job(...) from routers/services without importing at module level.
    """
    try:
        jq = importlib.import_module("backend.jobs.jobqueue")
        return jq
    except Exception:
        logger.debug("backend.jobs.jobqueue not available", exc_info=True)
        return None


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Small helper to inject a named logger as dependency.
    """
    return logging.getLogger(name or "app")