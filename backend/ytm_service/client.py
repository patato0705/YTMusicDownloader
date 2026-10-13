# backend/ytm_service/client.py
from __future__ import annotations
import logging
import threading
import time
from typing import Any, Optional

from ytmusicapi import YTMusic

from ..config import HEADERS_AUTH, YTM_MAX_CONC, YTM_BACKOFF_BASE, YTM_BACKOFF_MAX

logger = logging.getLogger("ytm_service.client")

# One client per process, created on first use; at most YTM_MAX_CONC calls at once
_ytm_lock = threading.Lock()
_ytm_client: Optional[YTMusic] = None
_ytm_sem = threading.BoundedSemaphore(YTM_MAX_CONC)


def _get_language() -> str:
    """The ytmusic.language setting, 'en' if it can't be read."""
    from ..db import SessionLocal
    from ..settings import get_setting
    try:
        with SessionLocal() as session:
            return str(get_setting(session, "ytmusic.language") or "en")
    except Exception:
        logger.exception("Failed to read ytmusic.language setting; falling back to 'en'")
        return "en"


def get_client() -> YTMusic:
    """
    The YTMusic instance, created on first use. HEADERS_AUTH, when set, is
    the path of a headers_auth.json to reuse an authenticated session;
    otherwise the client is anonymous.
    """
    global _ytm_client
    with _ytm_lock:
        if _ytm_client is None:
            language = _get_language()
            if HEADERS_AUTH:
                logger.info("Initializing YTMusic with headers file: %s (language=%s)", HEADERS_AUTH, language)
                _ytm_client = YTMusic(auth=HEADERS_AUTH, language=language)
            else:
                logger.info("Initializing anonymous YTMusic client (language=%s)", language)
                _ytm_client = YTMusic(language=language)
        return _ytm_client


def reset_client() -> None:
    """
    Invalidate the cached YTMusic client. The next call to get_client() will
    re-initialize it, picking up any changed settings (e.g. language).
    """
    global _ytm_client
    with _ytm_lock:
        _ytm_client = None
    logger.info("YTMusic client cache cleared")


def call(method_name: str, *args: Any, max_retries: int = 4, **kwargs: Any) -> Any:
    """
    Call a YTMusic method, retrying with exponential backoff (YouTube Music
    sends empty or unparseable pages at times). Raises the last error once
    out of retries; the caller decides how to report it.

        call("get_playlist", playlistId="...")
    """
    method = getattr(get_client(), method_name)
    for attempt in range(1, max_retries + 1):
        try:
            with _ytm_sem:
                return method(*args, **kwargs)
        except Exception as e:
            if attempt == max_retries:
                raise
            backoff = min(YTM_BACKOFF_MAX, YTM_BACKOFF_BASE * (2 ** (attempt - 1)))
            logger.warning("YTMusic call %s failed (attempt %s/%s): %s, retrying in %.2fs",
                           method_name, attempt, max_retries, e, backoff)
            time.sleep(backoff)
