# backend/db.py
"""
SQLAlchemy engine & session management for the application.
"""

from __future__ import annotations
import os
from typing import Generator, Optional

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from .config import DB_PATH, ensure_dirs
from .models import Base  # requires backend/models.py to define Base

# Ensure parent directory exists before creating sqlite file
ensure_dirs()

# SQLite URL
sqlite_url = f"sqlite:///{str(DB_PATH)}"

# create engine with optimized settings for SQLite concurrency
engine = create_engine(
    sqlite_url,
    connect_args={
        "check_same_thread": False,
        "timeout": 30.0,  # 30 second timeout for lock acquisition
    },
    poolclass=StaticPool,  # Single connection pool (optimal for SQLite)
    pool_pre_ping=True,    # Verify connections before using
    future=True,
)

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")          # Enable WAL mode
    cursor.execute("PRAGMA synchronous=NORMAL")        # Faster writes, still safe
    cursor.execute("PRAGMA cache_size=-64000")         # 64MB cache
    cursor.execute("PRAGMA busy_timeout=30000")        # 30 seconds in milliseconds
    cursor.execute("PRAGMA temp_store=MEMORY")         # Store temp tables in memory
    cursor.execute("PRAGMA mmap_size=268435456")       # 256MB memory-mapped I/O
    cursor.execute("PRAGMA page_size=4096")            # 4KB pages
    cursor.close()

# Session factory
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,  # Important for SQLite
    class_=Session
)

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