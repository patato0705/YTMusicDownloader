"""
Every change to backend/models.py comes with a migration (README >
Development > Database schema changes).
"""
from __future__ import annotations

from backend.migrations import dev


def test_models_match_the_migrations(capsys):
    # The same check as `python -m backend.migrations.dev check`
    assert dev.cmd_check() == 0, capsys.readouterr().err
