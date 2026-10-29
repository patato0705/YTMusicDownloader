# backend/db.py
"""
SQLAlchemy engine & session management for the application.
"""
from __future__ import annotations
import logging
import time
from typing import Generator

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import sessionmaker, Session

from .config import DB_PATH
from .models import Base

logger = logging.getLogger("db")

# A regular connection pool, not StaticPool. StaticPool hands the same single
# connection to every thread, which serialises every request in the web
# process behind whichever one is running (and, when that one is writing,
# behind the worker's write lock too). With WAL, readers never block on the
# writer, so a handful of connections per process lets the API keep
# answering while a big import is committing in the worker.
engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={
        "check_same_thread": False,
        "timeout": 30.0,  # 30 second timeout for lock acquisition
    },
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,    # Verify connections before using
)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    # Off by default in SQLite: without it the models' ON DELETE rules (a
    # deleted user's sessions, likes...) do nothing. Per connection.
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")          # Enable WAL mode
    cursor.execute("PRAGMA synchronous=NORMAL")        # Faster writes, still safe
    cursor.execute("PRAGMA cache_size=-64000")         # 64MB cache
    cursor.execute("PRAGMA busy_timeout=30000")        # 30 seconds in milliseconds
    cursor.execute("PRAGMA temp_store=MEMORY")         # Store temp tables in memory
    cursor.execute("PRAGMA mmap_size=268435456")       # 256MB memory-mapped I/O
    cursor.close()


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,  # Important for SQLite
    class_=Session
)


def init_db() -> None:
    """Create all tables, the first admin and the default settings."""
    from .services import auth as auth_svc
    from . import settings as settings_module

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        auth_svc.ensure_first_admin(session)
        settings_module.ensure_defaults(session)
    logger.info("Database is ready (%s)", DB_PATH)


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency: a Session for the request, closed afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def wait_for_db(max_retries: int = 30, delay: float = 1) -> None:
    """
    Wait until the web process has created the tables (workers and the
    scheduler start alongside it). Raises if they never appear.

    Logs at debug only: nine processes call this at once, and init_db
    already says "Database is ready" in the web process.
    """
    required = {"artists", "jobs", "refresh_tokens"}
    logger.debug("Waiting for database to be ready...")
    for attempt in range(1, max_retries + 1):
        try:
            missing = required - set(inspect(engine).get_table_names())
            if not missing:
                logger.debug("Database is ready")
                return
            logger.debug("Database not ready, missing tables %s (attempt %s/%s)", sorted(missing), attempt, max_retries)
        except Exception as e:
            logger.debug("Database not ready (attempt %s/%s): %s", attempt, max_retries, e)
        if attempt < max_retries:
            time.sleep(delay)
    raise RuntimeError(f"Database not ready after {max_retries} attempts")
