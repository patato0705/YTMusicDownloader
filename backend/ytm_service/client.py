# backend/ytm_service/client.py
from __future__ import annotations
import logging
import threading
import time
from typing import Any, Callable, Optional

from ytmusicapi import YTMusic

from ..config import HEADERS_AUTH, YTM_MAX_CONC, YTM_BACKOFF_BASE, YTM_BACKOFF_MAX

logger = logging.getLogger("ytm_service.client")

# Module-level lazy client and concurrency control
_ytm_lock = threading.Lock()
_ytm_client: Optional[YTMusic] = None

_YTM_MAX_CONC = int(YTM_MAX_CONC)
_ytm_sem = threading.BoundedSemaphore(_YTM_MAX_CONC)

_BACKOFF_BASE = float(YTM_BACKOFF_BASE)

_BACKOFF_MAX = float(YTM_BACKOFF_MAX)


def _init_client() -> YTMusic:
    """
    Initialise l'instance YTMusic une seule fois.
    HEADERS_AUTH can be:
      - None: no headers file (anonymous)
      - Path to headers_auth.json to re-use an authenticated session
    """
    global _ytm_client
    with _ytm_lock:
        if _ytm_client is not None:
            return _ytm_client
        try:
            if HEADERS_AUTH:
                # HEADERS_AUTH expected to be a path (string) to headers_auth.json
                logger.info("Initializing YTMusic with headers file: %s", HEADERS_AUTH)
                _ytm_client = YTMusic(auth=HEADERS_AUTH,language="en")
            else:
                logger.info("Initializing anonymous YTMusic client")
                _ytm_client = YTMusic(language="en")
        except Exception as e:
            logger.exception("Failed to initialize YTMusic client: %s", e)
            raise
        return _ytm_client


def get_client() -> YTMusic:
    """
    Return the lazily initialized YTMusic instance.
    Use this when you want to call YTMusic methods directly (e.g. get_playlist()).
    """
    global _ytm_client
    if _ytm_client is None:
        return _init_client()
    return _ytm_client


def call(method_name: str, *args: Any, max_retries: int = 4, **kwargs: Any) -> Any:
    """
    Safe call helper that:
      - acquires a semaphore to limit concurrent calls
      - retries with exponential backoff on exceptions
      - logs errors

    Usage:
      from backend.ytm_service.client import call
      call("get_playlist", playlistId="...")
    or:
      client = get_client(); client.get_playlist(...)
    """
    client = get_client()

    # bound method lookup
    if not hasattr(client, method_name):
        raise AttributeError(f"YTMusic client has no method {method_name!r}")

    method: Callable[..., Any] = getattr(client, method_name)

    attempt = 0
    while True:
        attempt += 1
        acquired = _ytm_sem.acquire(timeout=30)
        if not acquired:
            # semaphore acquisition timed out; keep trying a few times before failing
            logger.warning("Timeout acquiring YTMusic semaphore for method %s (attempt %s)", method_name, attempt)
        try:
            try:
                return method(*args, **kwargs)
            except Exception as e:
                # Decide whether to retry
                if attempt >= max_retries:
                    logger.exception("YTMusic call %s failed after %s attempts: %s", method_name, attempt, e)
                    raise
                # compute backoff
                backoff = min(_BACKOFF_MAX, _BACKOFF_BASE * (2 ** (attempt - 1)))
                logger.warning("YTMusic call %s failed (attempt %s/%s): %s — retrying in %.2fs",
                               method_name, attempt, max_retries, e, backoff)
                time.sleep(backoff)
                continue
        finally:
            try:
                _ytm_sem.release()
            except Exception:
                # semaphore release should not crash the app; log and continue
                logger.debug("Failed to release YTMusic semaphore", exc_info=True)