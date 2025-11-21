# backend/services/search.py
"""
Search service layer - handles caching and business logic for all search operations.

Architecture:
Router → Service (this file) → Adapter → YTMusic API
"""
from __future__ import annotations
import logging
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from ..config import SEARCH_CACHE_TTL
from ..ytm_service import adapter as ytm_adapter
from . import normalizers

logger = logging.getLogger("services.search")

# Cache key: (query, search_type, limit)
# search_type: "all", "artists", "albums", "songs", or "legacy"
CacheKey = Tuple[str, str, int]

_cache_lock = threading.Lock()
_cache: Dict[CacheKey, Tuple[float, Any]] = {}


def _get_from_cache(key: CacheKey) -> Optional[Any]:
    """Thread-safe cache retrieval with expiry check."""
    now = time.time()
    with _cache_lock:
        entry = _cache.get(key)
        if not entry:
            return None
        expiry, value = entry
        if expiry < now:
            _cache.pop(key, None)
            return None
        return value


def _set_in_cache(key: CacheKey, value: Any, ttl: Optional[int] = None) -> None:
    """Thread-safe cache storage."""
    ttl = int(ttl or SEARCH_CACHE_TTL or 900)  # Default 15 min
    expiry = time.time() + ttl
    with _cache_lock:
        _cache[key] = (expiry, value)


def clear_cache() -> None:
    """Clear all cached search results."""
    with _cache_lock:
        _cache.clear()
    logger.info("Search cache cleared")


def search_all(
    query: str,
    limit_per_type: int = 10,
    use_cache: bool = True
) -> Dict[str, List[dict]]:
    """
    Search all types (artists, albums, songs) using filtered searches.
    This is the recommended search method for most use cases.
    
    Args:
        query: Search query string
        limit_per_type: Maximum results per type
        use_cache: Whether to use cached results
        
    Returns:
        Dict with keys "artists", "albums", "songs"
        
    Raises:
        Exception: If adapter call fails
    """
    query = query.strip()
    if not query:
        return {"artists": [], "albums": [], "songs": []}
    
    limit_per_type = max(1, min(limit_per_type, 50))  # Clamp to reasonable range
    cache_key: CacheKey = (query, "all", limit_per_type)
    
    # Check cache
    if use_cache:
        cached = _get_from_cache(cache_key)
        if cached is not None:
            logger.debug(f"Cache HIT for search_all: {query}")
            return cached
    
    # Call adapter
    logger.debug(f"Cache MISS for search_all: {query} - calling adapter")
    try:
        raw_results = ytm_adapter.search_all_filtered(
            q=query,
            limit_per_type=limit_per_type,
            include_raw=False
        )
    except Exception as e:
        logger.exception(f"Adapter search_all_filtered failed for query '{query}'")
        raise Exception(f"Search service unavailable: {str(e)}")
    
    # Normalize results for consistency
    normalized_results = normalizers.normalize_search_results(raw_results)
    
    # Cache results
    if use_cache:
        _set_in_cache(cache_key, normalized_results)
    
    return normalized_results


def search_artists(
    query: str,
    limit: int = 10,
    use_cache: bool = True
) -> List[dict]:
    """
    Search for artists only.
    
    Args:
        query: Search query string
        limit: Maximum results
        use_cache: Whether to use cached results
        
    Returns:
        List of artist results
    """
    query = query.strip()
    if not query:
        return []
    
    limit = max(1, min(limit, 50))
    cache_key: CacheKey = (query, "artists", limit)
    
    if use_cache:
        cached = _get_from_cache(cache_key)
        if cached is not None:
            logger.debug(f"Cache HIT for search_artists: {query}")
            return cached
    
    logger.debug(f"Cache MISS for search_artists: {query}")
    try:
        results = ytm_adapter.search_artists(q=query, limit=limit, include_raw=False)
    except Exception as e:
        logger.exception(f"Adapter search_artists failed for query '{query}'")
        raise Exception(f"Artist search unavailable: {str(e)}")
    
    if use_cache:
        _set_in_cache(cache_key, results)
    
    return results


def search_albums(
    query: str,
    limit: int = 10,
    use_cache: bool = True
) -> List[dict]:
    """
    Search for albums only.
    
    Args:
        query: Search query string
        limit: Maximum results
        use_cache: Whether to use cached results
        
    Returns:
        List of album results
    """
    query = query.strip()
    if not query:
        return []
    
    limit = max(1, min(limit, 50))
    cache_key: CacheKey = (query, "albums", limit)
    
    if use_cache:
        cached = _get_from_cache(cache_key)
        if cached is not None:
            logger.debug(f"Cache HIT for search_albums: {query}")
            return cached
    
    logger.debug(f"Cache MISS for search_albums: {query}")
    try:
        results = ytm_adapter.search_albums(q=query, limit=limit, include_raw=False)
    except Exception as e:
        logger.exception(f"Adapter search_albums failed for query '{query}'")
        raise Exception(f"Album search unavailable: {str(e)}")
    
    if use_cache:
        _set_in_cache(cache_key, results)
    
    return results


def search_songs(
    query: str,
    limit: int = 10,
    use_cache: bool = True
) -> List[dict]:
    """
    Search for songs only.
    
    Args:
        query: Search query string
        limit: Maximum results
        use_cache: Whether to use cached results
        
    Returns:
        List of song results
    """
    query = query.strip()
    if not query:
        return []
    
    limit = max(1, min(limit, 50))
    cache_key: CacheKey = (query, "songs", limit)
    
    if use_cache:
        cached = _get_from_cache(cache_key)
        if cached is not None:
            logger.debug(f"Cache HIT for search_songs: {query}")
            return cached
    
    logger.debug(f"Cache MISS for search_songs: {query}")
    try:
        results = ytm_adapter.search_songs(q=query, limit=limit, include_raw=False)
    except Exception as e:
        logger.exception(f"Adapter search_songs failed for query '{query}'")
        raise Exception(f"Song search unavailable: {str(e)}")
    
    if use_cache:
        _set_in_cache(cache_key, results)
    
    return results


def get_charts(
    country: Optional[str] = None,
    use_cache: bool = True
) -> Dict[str, Any]:
    """
    Get charts (top artists and songs) for a country.
    
    Args:
        country: Country code (e.g., "US", "FR")
        use_cache: Whether to use cached results
        
    Returns:
        Dict with keys "artists" and "songs"
    """
    country_code = (country or "US").strip().upper()
    cache_key: CacheKey = (f"__charts__{country_code}", "charts", 1)
    
    if use_cache:
        cached = _get_from_cache(cache_key)
        if cached is not None:
            logger.debug(f"Cache HIT for charts: {country_code}")
            return cached
    
    logger.debug(f"Cache MISS for charts: {country_code}")
    try:
        raw_charts = ytm_adapter.get_charts(country=country_code)
    except Exception as e:
        logger.exception(f"Adapter get_charts failed for country '{country_code}'")
        raise Exception(f"Charts service unavailable: {str(e)}")
    
    # Ensure structure
    result = {
        "artists": raw_charts.get("artists", []),
        "songs": raw_charts.get("songs", []),
    }
    
    if use_cache:
        _set_in_cache(cache_key, result)
    
    return result