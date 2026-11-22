"""
Alembic's entry point for every command. Runs on the connection that
runner.py or dev.py hands over (see runner.migration_engine for why it's
not the app's own engine), so there's no alembic.ini and the `alembic`
command line isn't used: see dev.py instead.
"""
from alembic import context
from alembic.operations import ops

from backend.models import Base


def _review_new_revision(_context, _revision, directives) -> None:
    """
    For dev.py revision: generate nothing, rather than an empty script, when
    the models haven't changed, and flag what autogenerate gets wrong on a
    database that already has rows (see dev.py's docstring):
    - a new NOT NULL column without a server default: passes every check
      on a new database, fails the upgrade of any other;
    - a column (or table) dropped and another added: if it's a rename,
      the data is lost.
    """
    upgrade_ops = directives[0].upgrade_ops
    if upgrade_ops.is_empty():
        directives[:] = []
        return
    warnings = context.config.attributes.setdefault("warnings", [])

    for table_ops in (op for op in upgrade_ops.ops if isinstance(op, ops.ModifyTableOps)):
        added = [op.column for op in table_ops.ops if isinstance(op, ops.AddColumnOp)]
        dropped = [op.column_name for op in table_ops.ops if isinstance(op, ops.DropColumnOp)]
        for column in added:
            if not column.nullable and column.server_default is None:
                warnings.append(
                    f"{table_ops.table_name}.{column.name} is NOT NULL without a server_default: "
                    "existing rows need one, add server_default=... to its sa.Column"
                )
        if added and dropped:
            warnings.append(
                f"{table_ops.table_name} drops {', '.join(dropped)} and adds "
                f"{', '.join(c.name for c in added)}: if one is the other renamed, use "
                "batch_op.alter_column(..., new_column_name=...) or copy the data with op.execute"
            )

    created = [op.table_name for op in upgrade_ops.ops if isinstance(op, ops.CreateTableOp)]
    dropped = [op.table_name for op in upgrade_ops.ops if isinstance(op, ops.DropTableOp)]
    if created and dropped:
        warnings.append(
            f"tables {', '.join(dropped)} dropped and {', '.join(created)} created: if one is "
            "the other renamed, use op.rename_table instead"
        )


def run() -> None:
    connection = context.config.attributes.get("connection")
    if context.is_offline_mode() or connection is None:
        raise RuntimeError("Run migrations through backend.migrations (runner.py or dev.py)")

    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        # SQLite can't alter most of a table in place: ALTER-type operations
        # copy the table instead (see runner.migration_engine)
        render_as_batch=True,
        # It is: runner.migration_engine makes the transaction cover DDL
        transactional_ddl=True,
        process_revision_directives=(
            _review_new_revision if context.config.attributes.get("new_revision") else None
        ),
    )
    # The caller's transaction, when there is one, covers the whole run
    with context.begin_transaction():
        context.run_migrations()


run()
