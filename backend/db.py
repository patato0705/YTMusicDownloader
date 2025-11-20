# backend/db.py
"""
SQLAlchemy engine & session management for the application.

Usage:
    from backend.db import get_session, init_db
    with get_session() as session:
        ...
or as dependency in FastAPI:
    from backend.db import get_session
    db: Session = Depends(get_session)
"""

from __future__ import annotations
import os
from typing import Generator, Optional

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session

from .config import DB_PATH, ensure_dirs
from .models import Base  # requires backend/models.py to define Base

# Ensure parent directory exists before creating sqlite file
ensure_dirs()

# SQLite URL
sqlite_url = f"sqlite:///{str(DB_PATH)}"

# create engine with check_same_thread for multithreaded apps/workers
engine = create_engine(
    sqlite_url,
    connect_args={"timeout": 30,"check_same_thread": False, "timeout": 30},
    future=True,
)

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")  # 30 seconds
    cursor.close()

# Session factory
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, class_=Session)

def init_db() -> None:
    """
    Create all tables, ensure first admin, and initialize default settings.
    """
    # Create tables
    Base.metadata.create_all(bind=engine)
    
    # Create first admin user if needed
    from .services import auth as auth_svc
    with SessionLocal() as session:
        auth_svc.ensure_first_admin(session)
    
    # Initialize default settings
    from . import settings as settings_module
    with SessionLocal() as session:
        settings_module.ensure_defaults(session)

def get_engine():
    return engine

def get_session() -> Generator[Session, None, None]:
    """
    Dependency / context manager to get DB session.
    Yields a Session, caller should commit/rollback as needed.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def cleanup_expired_tokens_job() -> None:
    """
    Background job to clean up expired refresh tokens.
    Should be called periodically (e.g., daily via scheduler).
    """
    import logging
    logger = logging.getLogger("db")
    
    try:
        from .services import auth as auth_svc
        with SessionLocal() as session:
            count = auth_svc.cleanup_expired_tokens(session)
            if count > 0:
                logger.info(f"Token cleanup: removed {count} expired tokens")
    except Exception as e:
        logger.exception(f"Token cleanup failed: {e}")