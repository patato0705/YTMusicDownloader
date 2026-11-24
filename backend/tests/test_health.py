"""
The public health check says which check fails, never why.

/api/health answers without sign-in (it's the Docker healthcheck), so its
response must not show the server's paths or error messages. The reasons
go to the log instead, once per change rather than at every 30 s poll.
"""
from __future__ import annotations

import logging

import pytest

from backend import config
from backend.routers import health

DB_ERROR = f"(sqlite3.OperationalError) unable to open database file {config.DB_PATH}"


def _walk_keys(value):
    if isinstance(value, dict):
        for key, inner in value.items():
            yield key
            yield from _walk_keys(inner)


@pytest.fixture
def checks(monkeypatch):
    """
    Every check passing, as `checks` (one dict per check, edited by the
    test), with the log of the last failures forgotten.
    """
    state = {
        "db": {"ok": True, "detail": "ok"},
        "binaries": {"ffmpeg": {"ok": True, "path": "/usr/local/bin/ffmpeg"}, "ffprobe": {"ok": True, "path": "/usr/local/bin/ffprobe"}},
        "fs": {"CONFIG_DIR": {"path": str(config.CONFIG_DIR), "exists": True, "writable": True}},
        "ytmusic": {"ok": True, "detail": "client_initialized"},
    }
    monkeypatch.setattr(health, "_check_db", lambda: state["db"])
    monkeypatch.setattr(health, "_check_binaries", lambda: state["binaries"])
    monkeypatch.setattr(health, "_check_fs", lambda: state["fs"])
    monkeypatch.setattr(health, "_check_ytmusic", lambda: state["ytmusic"])
    monkeypatch.setattr(health, "_last_failures", None)
    return state


def test_the_real_checks_show_no_paths_or_messages(client):
    response = client.get("/api/health")
    body = response.json()
    assert {"path", "detail"}.isdisjoint(_walk_keys(body))
    # The test's /config and /data are under this folder
    assert str(config.CONFIG_DIR.parent) not in response.text
    # What does show: each check's result
    assert {"db", "binaries", "fs", "ytmusic"} <= body["checks"].keys()
    assert body["checks"]["fs"]["CONFIG_DIR"] == {"exists": True, "writable": True}


def test_a_failing_check_is_named_but_not_explained(client, checks):
    checks["db"] = {"ok": False, "detail": DB_ERROR}
    checks["fs"]["CONFIG_DIR"]["writable"] = False

    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["ok"] is False
    assert response.json()["checks"]["db"] == {"ok": False}
    assert response.json()["checks"]["fs"]["CONFIG_DIR"] == {"exists": True, "writable": False}
    assert "sqlite3" not in response.text
    assert str(config.CONFIG_DIR) not in response.text


def test_the_reasons_go_to_the_log_once_per_change(client, checks, caplog):
    def warnings():
        return [r.getMessage() for r in caplog.records if r.name == "routers.health" and r.levelno == logging.WARNING]

    with caplog.at_level(logging.INFO, logger="routers.health"):
        checks["db"] = {"ok": False, "detail": DB_ERROR}
        client.get("/api/health")
        client.get("/api/health")
        assert warnings() == [f"Health check failing: database: {DB_ERROR}"]

        # A new reason is logged again, with the full list
        checks["binaries"]["ffmpeg"] = {"ok": False, "path": None}
        client.get("/api/health")
        assert len(warnings()) == 2
        assert "ffmpeg not found on PATH" in warnings()[-1]
        assert str(config.DB_PATH) in warnings()[-1]

        # And the recovery, once
        checks["db"] = {"ok": True, "detail": "ok"}
        checks["binaries"]["ffmpeg"] = {"ok": True, "path": "/usr/local/bin/ffmpeg"}
        assert client.get("/api/health").status_code == 200
        client.get("/api/health")
    recoveries = [r for r in caplog.records if r.getMessage() == "Health checks pass again"]
    assert len(recoveries) == 1


def test_a_healthy_start_logs_nothing(client, checks, caplog):
    with caplog.at_level(logging.INFO, logger="routers.health"):
        client.get("/api/health")
    assert not [r for r in caplog.records if r.name == "routers.health"]
