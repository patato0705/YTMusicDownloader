# backend/routers/health.py
"""
Health endpoints.

Endpoints:
- GET /api/health - Get app state
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
from ..db import get_engine
from ..ytm_service.client import get_client, call

logger = logging.getLogger("routers.health")
router = APIRouter(prefix="/api/health", tags=["Health"])


def _check_db() -> Dict[str, Any]:
    engine = get_engine()
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
    """
    Check presence of some required binaries in PATH.
    """
    bins = {}
    for b in ("yt-dlp", "yt-dlp.exe", "ffmpeg", "ffprobe"):
        # prefer first match
        p = shutil.which(b)
        if p:
            bins[b] = {"ok": True, "path": p}
        else:
            bins[b] = {"ok": False, "path": None}
    return bins


def _check_fs() -> Dict[str, Any]:
    """
    Check that key directories exist and are writable.
    """
    checks = {}
    for name, path in (
        ("CONFIG_DIR", config.CONFIG_DIR),
        ("TEMP_DIR", config.TEMP_DIR),
        ("DOWNLOAD_DIR", config.DOWNLOAD_DIR),
        ("COVERS_DIR", config.COVERS_DIR),
        ("LYRICS_DIR", config.LYRICS_DIR),
        ("MUSIC_DIR", config.MUSIC_DIR),
        ("LOG_DIR", config.LOG_DIR),
    ):
        try:
            p = str(path)
            exists = os.path.exists(p)
            writable = False
            # if exists, try to test write (create+remove temp file) cheaply
            if exists and os.access(p, os.W_OK):
                try:
                    testfile = os.path.join(p, f".health_tmp_{int(time.time()*1000)}")
                    with open(testfile, "w") as fh:
                        fh.write("x")
                    os.remove(testfile)
                    writable = True
                except Exception:
                    writable = False
            checks[name] = {"path": p, "exists": exists, "writable": writable}
        except Exception as e:
            checks[name] = {"path": str(path), "exists": False, "writable": False, "error": str(e)}
    return checks


def _check_ytmusic(deep: bool = False) -> Dict[str, Any]:
    """
    Initialize YTMusic client and optionally perform a small call.
    deep=True will call get_charts (may take longer).
    """
    out: Dict[str, Any] = {"ok": False, "detail": None}
    try:
        # init client (may raise)
        client = get_client()
        out["ok"] = True
        out["detail"] = "client_initialized"
    except Exception as e:
        logger.debug("YTMusic client init failed", exc_info=True)
        out["ok"] = False
        out["detail"] = f"init_error: {e}"
        return out

    if deep:
        try:
            # attempt a light call; adapt the method if you prefer another one
            country = getattr(config, "CHARTS_COUNTRY", "US")
            # call may raise or return unexpected structure
            res = call("get_charts", country=country, max_retries=2)
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

    # binaries (yt-dlp, ffmpeg, ffprobe)
    bins = _check_binaries()
    result["checks"]["binaries"] = bins
    # mark overall as not ok if neither yt-dlp nor ffmpeg present
    if not any(v["ok"] for k, v in bins.items() if k in ("yt-dlp", "ffmpeg")):
        overall_ok = False

    # filesystem
    fs = _check_fs()
    result["checks"]["fs"] = fs
    if not all(v.get("exists") and v.get("writable") for v in fs.values()):
        # if some critical dirs missing or unwritable, fail
        overall_ok = False

    # ytmusic
    ytm_chk = _check_ytmusic(deep=deep)
    result["checks"]["ytmusic"] = ytm_chk
    if not ytm_chk.get("ok"):
        overall_ok = False

    result["ok"] = overall_ok

    status_code = 200 if overall_ok else 503
    return JSONResponse(status_code=status_code, content=result)