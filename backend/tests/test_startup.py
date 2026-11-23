"""
A fresh install: the app starts on an empty database, creates the first
administrator, and password sign-in works.
"""
from __future__ import annotations

from sqlalchemy import select

from backend import config
from backend.db import SessionLocal
from backend.models import User
from backend.services import auth as auth_svc


def test_starts_on_an_empty_database(client):
    # Starting the client ran the schema upgrade, which raises if the result
    # doesn't match the models (migrations/runner.py, _verify)
    response = client.get("/api/health")
    checks = response.json()["checks"]
    assert checks["db"]["ok"]
    assert all(d["exists"] and d["writable"] for d in checks["fs"].values())
    # Not the overall status: it also needs ffmpeg on PATH, which the test
    # machine may not have


def test_first_admin_password_only_allows_choosing_a_new_one(client):
    with SessionLocal() as session:
        admin = session.execute(
            select(User).where(User.username == config.FIRST_ADMIN_USERNAME)
        ).scalar_one()
        assert admin.role == config.ROLE_ADMINISTRATOR
        assert admin.must_change_password
        headers = {"Authorization": f"Bearer {auth_svc.create_access_token(admin)}"}

    # The generated password is in the log: until it's replaced, it only
    # opens what the change-password page needs
    assert client.get("/api/auth/me", headers=headers).status_code == 200
    response = client.get("/api/admin/users", headers=headers)
    assert response.status_code == 403
    assert response.json()["detail"] == "password_change_required"


def test_password_login(client):
    password = auth_svc.generate_temporary_password()
    with SessionLocal() as session:
        auth_svc.create_user(session, "login-test", password, role=config.ROLE_MEMBER)

    response = client.post("/api/auth/login", json={"username": "login-test", "password": password})
    assert response.status_code == 200
    token = response.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["username"] == "login-test"

    wrong = client.post("/api/auth/login", json={"username": "login-test", "password": "not-it"})
    assert wrong.status_code == 401
