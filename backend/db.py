# backend/db.py
"""
SQLAlchemy engine & session management for the application.
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

# A regular connection pool, not StaticPool. StaticPool hands the same single
# connection to every thread, which serialises every request in the web
# process behind whichever one is running (and, when that one is writing,
# behind the worker's write lock too). With WAL, readers never block on the
# writer, so a handful of connections per process lets the API keep
# answering while a big import is committing in the worker.
engine = create_engine(
    sqlite_url,
    connect_args={
        "check_same_thread": False,
        "timeout": 30.0,  # 30 second timeout for lock acquisition
    },
    pool_size=5,
    max_overflow=10,
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