# backend/services/search.py
"""YouTube Music search, with its results cached for a while (SEARCH_CACHE_TTL)."""
from __future__ import annotations
import logging
import threading
import time
from typing import Any, Dict, List, Tuple

from ..config import SEARCH_CACHE_TTL
from ..ytm_service import adapter as ytm_adapter

logger = logging.getLogger("services.search")

# (query, limit per type) -> (expiry, results)
_cache: Dict[Tuple[str, int], Tuple[float, Any]] = {}
_cache_lock = threading.Lock()


def search_all(query: str, limit_per_type: int = 10) -> Dict[str, List[dict]]:
    """
    Artists, albums and songs matching the query: {"artists", "albums",
    "songs"}. Raises ytm_adapter.YTMusicUnavailable when YouTube Music
    can't be searched.
    """
    query = query.strip()
    if not query:
        return {"artists": [], "albums": [], "songs": []}
    key = (query, max(1, min(limit_per_type, 50)))
    now = time.time()

    with _cache_lock:
        cached = _cache.get(key)
        if cached and cached[0] > now:
            return cached[1]

    results = ytm_adapter.search_all(query, key[1])

    with _cache_lock:
        # Expired entries are dropped as new ones come in, so the cache only
        # ever holds the searches of the last SEARCH_CACHE_TTL seconds
        for stale in [k for k, (expiry, _) in _cache.items() if expiry <= now]:
            del _cache[stale]
        _cache[key] = (now + SEARCH_CACHE_TTL, results)
    return results
