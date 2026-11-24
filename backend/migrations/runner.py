"""
Brings the database schema up to date. Run by the web process at startup
(db.init_db); the workers and the scheduler wait for it (db.wait_for_db).

What an upgrade does, all in one transaction:
1. Copies the database to db-backups/ next to it, unless it is new.
2. A database from before migrations existed (tables but no
   alembic_version) is rebuilt as the baseline creates it (see _adopt).
3. Applies every script in versions/ the database hasn't had yet.
4. Checks that the resulting schema matches backend/models.py and that
   no foreign key points at a missing row.
Any failure rolls all of it back and deletes the copy: the database and
db-backups/ stay as they were, and the web process stops with the reason
in the log.
"""
from __future__ import annotations

import datetime
import logging
import sqlite3
from pathlib import Path
from typing import Optional

# Before importing alembic, which logs one line per comparison plugin as it
# loads them, saying nothing useful
logging.getLogger("alembic.runtime.plugins").setLevel(logging.WARNING)

from alembic import command  # noqa: E402
from alembic.autogenerate import compare_metadata  # noqa: E402
from alembic.config import Config  # noqa: E402
from alembic.runtime.migration import MigrationContext  # noqa: E402
from alembic.script import ScriptDirectory  # noqa: E402
from sqlalchemy import Connection, Engine, create_engine, event, inspect  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from .. import config  # noqa: E402
from ..models import Base  # noqa: E402

logger = logging.getLogger("db")

# The first script in versions/: the schema as it was when migrations were
# introduced, which databases created before then are rebuilt to.
BASELINE = "0001"
# Pre-upgrade copies kept in db-backups/
KEEP_BACKUPS = 3

_SCRIPTS_DIR = Path(__file__).parent
_VERSION_TABLE = "alembic_version"


def alembic_config() -> Config:
    """Alembic settings, without an alembic.ini."""
    cfg = Config()
    cfg.set_main_option("script_location", str(_SCRIPTS_DIR))
    return cfg


_head: Optional[str] = None


def head() -> str:
    """The latest revision in versions/. Raises if the history has forked."""
    global _head
    if _head is None:
        _head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    return _head


def migration_engine(path: Path) -> Engine:
    """
    An engine for running migrations on the database at `path`.

    Not db.engine, for two reasons:
    - foreign_keys is off. SQLite can't alter most of a table in place,
      so a migration copies it to a new table, drops the old one and
      renames the copy (Alembic's "batch" mode). With foreign keys on,
      dropping the old table would run every ON DELETE CASCADE pointing
      at it: dropping `artists` would empty `albums`. The check at the
      end of upgrade() makes up for having them off.
    - The whole upgrade is one real transaction. Python's sqlite3 driver
      opens transactions on its own and doesn't include CREATE/ALTER in
      them; with that turned off and BEGIN sent here instead, a failed
      migration rolls back everything, schema changes included.
    """
    engine = create_engine(f"sqlite:///{path}", poolclass=NullPool, connect_args={"timeout": 30.0})

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _record):
        dbapi_conn.isolation_level = None
        dbapi_conn.execute("PRAGMA foreign_keys=OFF")
        # As db.engine sets it, so a new database starts out the same way
        dbapi_conn.execute("PRAGMA journal_mode=WAL")

    @event.listens_for(engine, "begin")
    def _on_begin(conn):
        # IMMEDIATE: takes the write lock now rather than at the first write
        conn.exec_driver_sql("BEGIN IMMEDIATE")

    return engine


def current_revision(connection: Connection) -> Optional[str]:
    """
    The database's revision, None if it has none (new or pre-migrations).
    Read directly rather than through Alembic, which logs two lines each
    time: the workers ask every second while they wait.
    """
    exists = connection.exec_driver_sql(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (_VERSION_TABLE,)
    ).first()
    if not exists:
        return None
    row = connection.exec_driver_sql(f"SELECT version_num FROM {_VERSION_TABLE}").first()
    return row[0] if row else None


def is_up_to_date(connection: Connection) -> bool:
    return current_revision(connection) == head()


def upgrade(path: Path = config.DB_PATH) -> None:
    """Bring the database at `path` (created if missing) to the latest revision."""
    target = head()
    # The usual case, read without taking the write lock: the web process
    # can restart while a worker holds it through a long import
    if Path(path).exists() and _read_revision(path) == target:
        return

    engine = migration_engine(path)
    backup = None
    try:
        with engine.connect() as conn, conn.begin():
            current = current_revision(conn)
            if current == target:
                return
            cfg = alembic_config()
            if current is not None and not _known(cfg, current):
                raise RuntimeError(
                    f"The database is at schema {current}, from a newer version of the app than this "
                    f"one (which goes up to {target}). Run that newer version, or restore the copy "
                    "taken before it upgraded the database (see README > Updating)."
                )
            tables = set(inspect(conn).get_table_names())
            pre_migrations = current is None and bool(tables)

            if tables:
                backup = _backup(path, current or "unversioned", target)
            cfg.attributes["connection"] = conn
            if pre_migrations:
                _adopt(conn, cfg)
            command.upgrade(cfg, "head")
            _verify(conn)
    except BaseException:
        # The upgrade rolled back: a copy of the unchanged database is no use
        if backup is not None:
            backup.unlink(missing_ok=True)
        raise
    finally:
        engine.dispose()

    if backup is not None:
        _prune_backups(backup.parent)
    if current is None and not pre_migrations:
        logger.info("Database created at schema %s", target)
    else:
        logger.info("Database schema upgraded from %s to %s (copy of the previous one: %s)",
                    current or "pre-migrations", target, backup)


def _read_revision(path: Path) -> Optional[str]:
    """The revision of the database at `path`, read on a plain connection."""
    conn = sqlite3.connect(path, timeout=30.0)
    try:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (_VERSION_TABLE,)
        ).fetchone()
        row = conn.execute(f"SELECT version_num FROM {_VERSION_TABLE}").fetchone() if exists else None
        return row[0] if row else None
    finally:
        conn.close()


def _known(cfg: Config, revision: str) -> bool:
    return any(s.revision == revision for s in ScriptDirectory.from_config(cfg).walk_revisions())


def _adopt(conn: Connection, cfg: Config) -> None:
    """
    Rebuild a database created before migrations existed (by create_all)
    as the baseline creates a new one. Its tables and columns are mostly
    the baseline's, but not its constraint names: create_all left them
    unnamed, and a later migration couldn't refer to them. So every table
    is moved aside, the baseline creates them anew, and the rows are
    copied over.

    create_all never removed anything, and foreign keys were only enforced
    from 2026-10-29, so what was left behind goes now: tables and columns
    the app no longer has, and rows pointing at a deleted row (removed, or
    their link cleared, as their ON DELETE says).
    """
    logger.info("Database predates schema migrations: rebuilding it as schema %s", BASELINE)
    old_tables = [
        t for t in inspect(conn).get_table_names()
        if not t.startswith("sqlite_") and t != _VERSION_TABLE
    ]
    # AUTOINCREMENT tables never reuse an id, even a deleted one's: carried over
    has_sequences = conn.exec_driver_sql("SELECT 1 FROM sqlite_master WHERE name = 'sqlite_sequence'").first()
    sequences = dict(conn.exec_driver_sql("SELECT name, seq FROM sqlite_sequence").fetchall()) if has_sequences else {}

    inspector = inspect(conn)
    for table in old_tables:
        # Index names are database-wide: the baseline creates the same ones
        for index in inspector.get_indexes(table):
            conn.exec_driver_sql(f'DROP INDEX "{index["name"]}"')
        conn.exec_driver_sql(f'ALTER TABLE "{table}" RENAME TO "_pre_migrations_{table}"')
    # One left from a failed stamp, say: the baseline creates its own
    conn.exec_driver_sql(f"DROP TABLE IF EXISTS {_VERSION_TABLE}")

    command.upgrade(cfg, BASELINE)

    inspector = inspect(conn)
    new_tables = set(inspector.get_table_names())
    dropped_tables, dropped_columns = [], []
    for table in old_tables:
        moved = f"_pre_migrations_{table}"
        if table not in new_tables:
            dropped_tables.append(table)
            conn.exec_driver_sql(f'DROP TABLE "{moved}"')
            continue
        old_columns = {c["name"] for c in inspector.get_columns(moved)}
        new_columns = inspector.get_columns(table)
        missing = [
            c["name"] for c in new_columns
            if c["name"] not in old_columns and not c["nullable"] and c["default"] is None
        ]
        if missing:
            raise RuntimeError(
                f"This database predates schema migrations and its {table!r} table lacks "
                f"{', '.join(missing)}, which the schema they start from requires, so it can't be "
                "upgraded. Export a backup from an instance running the previous version (Admin "
                "Panel > Backup), start this one with a new database and import it."
            )
        dropped_columns += [f"{table}.{c}" for c in sorted(old_columns - {c["name"] for c in new_columns})]
        columns = ", ".join(f'"{c["name"]}"' for c in new_columns if c["name"] in old_columns)
        conn.exec_driver_sql(f'INSERT INTO "{table}" ({columns}) SELECT {columns} FROM "{moved}"')
        conn.exec_driver_sql(f'DROP TABLE "{moved}"')

    for table, seq in sequences.items():
        if table not in new_tables:
            continue
        # The copy made a row for the table if it had any rows to copy
        if not conn.exec_driver_sql("UPDATE sqlite_sequence SET seq = MAX(seq, ?) WHERE name = ?", (seq, table)).rowcount:
            conn.exec_driver_sql("INSERT INTO sqlite_sequence (name, seq) VALUES (?, ?)", (table, seq))

    if dropped_tables or dropped_columns:
        logger.info("Dropped what the app no longer uses: %s", ", ".join(dropped_tables + dropped_columns))
    _apply_on_delete_to_orphans(conn)


def _apply_on_delete_to_orphans(conn: Connection) -> None:
    """
    Do to rows pointing at a missing row what their foreign key's ON DELETE
    would have done when it went: delete them (CASCADE) or clear the link
    (SET NULL). Deleting can orphan rows further down (an album's tracks),
    hence the rounds. Anything else is left for _verify to report.
    """
    for _ in range(10):
        broken = conn.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
        actions = {}
        for table, rowid, _parent, fk_id in broken:
            if table not in actions:
                actions[table] = {}
                for row in conn.exec_driver_sql(f'PRAGMA foreign_key_list("{table}")').fetchall():
                    # id, seq, table, from, to, on_update, on_delete, match
                    action = actions[table].setdefault(row[0], {"on_delete": row[6], "columns": []})
                    action["columns"].append(row[3])
        fixed = 0
        for table, rowid, parent, fk_id in broken:
            action = actions[table][fk_id]
            if action["on_delete"] == "CASCADE":
                fixed += conn.exec_driver_sql(f'DELETE FROM "{table}" WHERE rowid = ?', (rowid,)).rowcount
            elif action["on_delete"] == "SET NULL":
                assignments = ", ".join(f'"{c}" = NULL' for c in action["columns"])
                fixed += conn.exec_driver_sql(f'UPDATE "{table}" SET {assignments} WHERE rowid = ?', (rowid,)).rowcount
        if not fixed:
            return
        logger.info("Fixed %s row(s) pointing at deleted rows, as their ON DELETE says", fixed)


def diffs_alembic_misses(conn: Connection) -> list[str]:
    """
    Differences from the models that Alembic's comparison (and so
    autogenerate) doesn't look at: primary keys and AUTOINCREMENT. Each
    says how a migration makes the change, which has to be written by hand.
    """
    inspector = inspect(conn)
    existing = set(inspector.get_table_names())
    diffs = []
    for table in Base.metadata.sorted_tables:
        if table.name not in existing:
            continue  # compare_metadata reports it
        want = [c.name for c in table.primary_key.columns]
        have = inspector.get_pk_constraint(table.name)["constrained_columns"]
        if set(want) != set(have):
            diffs.append(
                f"{table.name}: primary key ({', '.join(have)}), the models say ({', '.join(want)}); "
                f"batch_op.create_primary_key('pk_{table.name}', {want}) makes it"
            )
        sql = conn.exec_driver_sql("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
                                   (table.name,)).scalar() or ""
        want_autoincrement = bool(table.dialect_options["sqlite"]["autoincrement"])
        if want_autoincrement != ("AUTOINCREMENT" in sql.upper()):
            diffs.append(
                f"{table.name}: AUTOINCREMENT is {'off' if want_autoincrement else 'on'}, the models "
                f"say {'on' if want_autoincrement else 'off'}; op.batch_alter_table('{table.name}', "
                f"recreate='always', table_kwargs={{'sqlite_autoincrement': {want_autoincrement}}}) makes it"
            )
    return diffs


def _verify(conn: Connection) -> None:
    """Raise (rolling the upgrade back) if the result isn't what the models expect."""
    diffs = compare_metadata(MigrationContext.configure(conn, opts={"transactional_ddl": True}), Base.metadata)
    diffs += diffs_alembic_misses(conn)
    if diffs:
        listed = "\n".join(f"  {d}" for d in diffs)
        raise RuntimeError(
            "After the upgrade, the database schema doesn't match the models: a migration in "
            f"backend/migrations/versions/ is missing or wrong. Nothing was changed. Differences:\n{listed}"
        )

    broken = conn.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
    if broken:
        sample = ", ".join(f"{row[0]} row {row[1]} -> {row[2]}" for row in broken[:10])
        raise RuntimeError(
            f"The upgrade left {len(broken)} row(s) pointing at missing rows ({sample}). "
            "Nothing was changed."
        )


def _backup(path: Path, current: str, target: str) -> Path:
    """
    Copy the database before upgrading it. The transaction rolls back a
    failed upgrade; this is for one that succeeds but turns out wrong, and
    for going back to the previous image (which can't read the new schema).
    """
    backup_dir = Path(path).parent / "db-backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    dest = backup_dir / f"db-{current}-before-{target}-{datetime.datetime.now():%Y%m%d-%H%M%S}.sqlite"

    # SQLite's backup API: a consistent copy including what's still in the WAL
    source = sqlite3.connect(path)
    copy = sqlite3.connect(dest)
    try:
        source.backup(copy)
    finally:
        copy.close()
        source.close()
    return dest


def _prune_backups(backup_dir: Path) -> None:
    """Keep the KEEP_BACKUPS newest copies (only called once an upgrade has committed)."""
    copies = sorted(backup_dir.glob("db-*.sqlite"), key=lambda p: p.stat().st_mtime)
    for old in copies[:-KEEP_BACKUPS]:
        old.unlink(missing_ok=True)
