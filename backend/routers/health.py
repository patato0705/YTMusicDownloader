# backend/routers/health.py
"""
Health endpoints.

Endpoints:
- GET /api/health - Get app state (the Docker healthcheck, so no auth)
"""
from __future__ import annotations
import logging
import shutil
import os
import time
from typing import Any, Dict

from fastapi import APIRouter, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .. import config
from ..db import engine
from ..ytm_service.client import get_client, call

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


def _check_ytmusic(deep: bool = False) -> Dict[str, Any]:
    """
    Initialize YTMusic client and optionally perform a small call.
    deep=True will call get_charts (may take longer).
    """
    out: Dict[str, Any] = {"ok": False, "detail": None}
    try:
        get_client()
        out["ok"] = True
        out["detail"] = "client_initialized"
    except Exception as e:
        logger.debug("YTMusic client init failed", exc_info=True)
        out["ok"] = False
        out["detail"] = f"init_error: {e}"
        return out

    if deep:
        try:
            res = call("get_charts", country="US", max_retries=2)
            # simple heuristics for success: expect dict with 'artists' or 'songs'
            if isinstance(res, dict) and ("artists" in res or "songs" in res):
                out["ok"] = True
                out["detail"] = "deep_call_ok"
            else:
                out["ok"] = False
                out["detail"] = f"deep_call_unexpected_response_type:{type(res)}"
        except Exception as e:
            logger.debug("YTMusic deep call failed", exc_info=True)
            out["ok"] = False
            out["detail"] = f"deep_call_error: {e}"
    return out


@router.get("", status_code=status.HTTP_200_OK)
def health_check(deep: bool = Query(False, description="If true, perform deeper checks (YTMusic network call)")) -> JSONResponse:
    """
    Health endpoint returning a JSON summary.

    - shallow checks (default): DB connectivity, presence of required binaries, FS permissions, YTMusic client init.
    - deep checks (deep=true): attempt a lightweight YTMusic call.
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
    ytm_chk = _check_ytmusic(deep=deep)
    result["checks"]["ytmusic"] = ytm_chk
    if not ytm_chk.get("ok"):
        overall_ok = False

    result["ok"] = overall_ok

    status_code = 200 if overall_ok else 503
    return JSONResponse(status_code=status_code, content=result)
