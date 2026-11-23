"""
Shared test setup: run the app against a throwaway folder instead of
/config and /data, so the tests need neither Docker nor root.

pytest loads this file before any test module, which is what makes the
redirect work: the paths in backend/config.py are read once, when the
modules using them are first imported (backend/db.py creates its engine
from DB_PATH at import time). So they're rewritten here, before anything
else from the app is imported.

Nothing here talks to YouTube Music: the tests only exercise what the app
decides on its own (startup, schema, who may call what).
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import pytest

# `import backend` works whichever folder pytest is started from
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend import config  # noqa: E402

_ROOT = Path(tempfile.mkdtemp(prefix="ytmd-tests-"))

# Every Path setting under /config or /data, moved under _ROOT. A loop rather
# than a list, so a path added to config.py later is covered too.
for _name, _value in list(vars(config).items()):
    if isinstance(_value, Path) and _value.parts[:2] in (("/", "config"), ("/", "data")):
        setattr(config, _name, _ROOT.joinpath(*_value.parts[1:]))

from fastapi.testclient import TestClient  # noqa: E402

from backend.db import SessionLocal  # noqa: E402
from backend.main import create_app  # noqa: E402
from backend.services import auth as auth_svc  # noqa: E402


def pytest_unconfigure(config):
    shutil.rmtree(_ROOT, ignore_errors=True)


@pytest.fixture(scope="session")
def client():
    """The app, started the way the container starts it (empty database included)."""
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def auth_headers(client):
    """
    auth_headers(role) -> Authorization header for a user with that role.

    One user per role for the whole run (hashing a password takes a
    quarter second). Tokens are issued directly rather than through
    /api/auth/login, so the login throttle doesn't come into play;
    test_startup.py covers login.
    """
    made = {}

    def make(role: str, must_change_password: bool = False) -> dict:
        key = (role, must_change_password)
        if key not in made:
            with SessionLocal() as session:
                user = auth_svc.create_user(
                    session,
                    username=f"test-{role}{'-temporary' if must_change_password else ''}",
                    password=auth_svc.generate_temporary_password(),
                    role=role,
                    must_change_password=must_change_password,
                )
                made[key] = {"Authorization": f"Bearer {auth_svc.create_access_token(user)}"}
        return made[key]

    return make
