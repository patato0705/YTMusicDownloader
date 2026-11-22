"""
Database schema migrations (Alembic).

- runner.py: brings the database up to date at startup (db.init_db) and
  tells the other processes when it is (db.wait_for_db).
- dev.py: generates a new migration from a change to backend/models.py,
  and checks that the models and migrations agree.
- versions/: one script per schema change, applied in order.
"""
