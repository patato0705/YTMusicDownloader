# backend/deps.py
from __future__ import annotations
import logging
import time
from typing import Generator

from sqlalchemy.orm import Session
from .db import SessionLocal

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


def wait_for_db(max_retries=30, delay=1):
    """Wait for database to be initialized with required tables."""
    from sqlalchemy import inspect

    logger.info("Waiting for database to be ready...")

    for attempt in range(max_retries):
        try:
            with SessionLocal() as session:
                # Check if required tables exist
                engine = session.get_bind()
                inspector = inspect(engine)
                tables = inspector.get_table_names()
                required_tables = ['artists', 'jobs', 'refresh_tokens']

                if all(table in tables for table in required_tables):
                    logger.info("Database is ready")
                    return True
                else:
                    # Tables don't exist yet, keep waiting
                    missing = [t for t in required_tables if t not in tables]
                    logger.debug(f"Database not ready - missing tables: {missing} (attempt {attempt + 1}/{max_retries})")

        except Exception as e:
            # Any exception means DB is not ready yet
            logger.debug(f"Database not ready (attempt {attempt + 1}/{max_retries}): {e}")

        # Always sleep between attempts (except on last attempt)
        if attempt < max_retries - 1:
            time.sleep(delay)
        else:
            logger.error("Database failed to become ready after %s attempts", max_retries)
            raise Exception(f"Database not ready after {max_retries} attempts")

    return False
