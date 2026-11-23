# backend/routers/health.py
"""
Health endpoints.

Endpoints:
- GET /api/health - Get app state (the Docker healthcheck, so no auth)

Public, so the response says which check fails but never why: paths and
error messages are left out (_public). The reasons go to the log instead,
once when a check starts failing or its reason changes, and once when all
pass again (_log_changes): polled every 30 s, it would otherwise repeat.
"""
from __future__ import annotations
import logging
import shutil
import os
import threading
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .. import config
from ..db import engine
from ..ytm_service.client import get_client

logger = logging.getLogger("routers.health")
router = APIRouter(prefix="/api/health", tags=["Health"])


def _check_db() -> Dict[str, Any]:
    try:
        with engine.connect() as conn:
            # simple lightweight query
            res = conn.execute(text("SELECT 1")).scalar()
            ok = (res == 1)
            return {"ok": ok, "detail": "ok" if ok else f"unexpected result: {res}"}
    except Exception as e:
        logger.debug("DB health check failed", exc_info=True)
        return {"ok": False, "detail": str(e)}


def _check_binaries() -> Dict[str, Any]:
    """The binaries yt-dlp's audio extraction needs (yt-dlp itself is a Python package)."""
    bins = {}
    for b in ("ffmpeg", "ffprobe"):
        p = shutil.which(b)
        bins[b] = {"ok": p is not None, "path": p}
    return bins


def _check_fs() -> Dict[str, Any]:
    """Whether the app's directories exist and are writable (permissions only: nothing is written)."""
    return {
        name: {"path": str(path), "exists": path.is_dir(), "writable": os.access(path, os.W_OK)}
        for name, path in (
            ("CONFIG_DIR", config.CONFIG_DIR),
            ("TEMP_DIR", config.TEMP_DIR),
            ("DOWNLOAD_DIR", config.DOWNLOAD_DIR),
            ("COVERS_DIR", config.COVERS_DIR),
            ("MUSIC_DIR", config.MUSIC_DIR),
            ("LOG_DIR", config.LOG_DIR),
        )
    }


def _check_ytmusic() -> Dict[str, Any]:
    """
    Whether the YTMusic client can be initialized. No call to YouTube Music:
    this endpoint is public and polled, and every request from this IP
    counts toward YouTube's rate limiting.
    """
    try:
        get_client()
        return {"ok": True, "detail": "client_initialized"}
    except Exception as e:
        logger.debug("YTMusic client init failed", exc_info=True)
        return {"ok": False, "detail": f"init_error: {e}"}


# Keys of a check's result that only the operator should see
_PRIVATE_KEYS = frozenset({"path", "detail"})


def _public(value: Any) -> Any:
    """The checks without paths and error messages."""
    if isinstance(value, dict):
        return {k: _public(v) for k, v in value.items() if k not in _PRIVATE_KEYS}
    return value


def _failures(checks: Dict[str, Any]) -> List[str]:
    """Each failing check, with its reason, for the log."""
    failures = []
    if not checks["db"]["ok"]:
        failures.append(f"database: {checks['db']['detail']}")
    failures += [f"{name} not found on PATH" for name, b in checks["binaries"].items() if not b["ok"]]
    for name, d in checks["fs"].items():
        if not d["exists"]:
            failures.append(f"{name} ({d['path']}) does not exist")
        elif not d["writable"]:
            failures.append(f"{name} ({d['path']}) is not writable by the app's user")
    if not checks["ytmusic"]["ok"]:
        failures.append(f"YouTube Music client: {checks['ytmusic']['detail']}")
    return failures


# The failures last logged: None until the first check, [] while healthy
_last_failures: Optional[List[str]] = None
_last_failures_lock = threading.Lock()


def _log_changes(failures: List[str]) -> None:
    """Log the failures when they differ from the last ones, and the recovery."""
    global _last_failures
    with _last_failures_lock:
        previous, _last_failures = _last_failures, failures
    if failures == previous:
        return
    if failures:
        logger.warning("Health check failing: %s", "; ".join(failures))
    elif previous:
        logger.info("Health checks pass again")


@router.get("", status_code=status.HTTP_200_OK)
def health_check() -> JSONResponse:
    """
    Health endpoint returning a JSON summary.

    DB connectivity, presence of required binaries, FS permissions, YTMusic
    client init. 503 when any of them fails. Which one is in the response,
    why in the log (see the module docstring).
    """
    overall_ok = True
    result: Dict[str, Any] = {"ok": True, "checks": {}, "timestamp": int(time.time())}

    # DB
    db_chk = _check_db()
    result["checks"]["db"] = db_chk
    if not db_chk.get("ok"):
        overall_ok = False

    bins = _check_binaries()
    result["checks"]["binaries"] = bins
    if not all(v["ok"] for v in bins.values()):
        overall_ok = False

    # filesystem
    fs = _check_fs()
    result["checks"]["fs"] = fs
    if not all(v["exists"] and v["writable"] for v in fs.values()):
        overall_ok = False

    # ytmusic
    ytm_chk = _check_ytmusic()
    result["checks"]["ytmusic"] = ytm_chk
    if not ytm_chk.get("ok"):
        overall_ok = False

    result["ok"] = overall_ok
    _log_changes(_failures(result["checks"]))

    status_code = 200 if overall_ok else 503
    return JSONResponse(status_code=status_code, content=_public(result))
