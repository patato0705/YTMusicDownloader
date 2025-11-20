# backend/routers/search.py
"""
Search router - handles HTTP requests and delegates to service layer.

Architecture:
HTTP Request → Router (this file) → Service → Adapter → YTMusic API
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Depends

from ..services import search as search_service

from backend.dependencies import require_auth, require_member_or_admin, require_admin
from backend.models import User

logger = logging.getLogger("routers.search")

router = APIRouter(prefix="/api/search", tags=["Search"])


@router.get("", response_model=Dict[str, List[Dict[str, Any]]])
def search(
    current_user: User = Depends(require_auth),
    q: str = Query(..., min_length=1, description="Query string to search for"),
    limit: int = Query(10, ge=1, le=50, description="Max results per type"),
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Search all types (artists, albums, songs) using filtered searches.
    
    This is the recommended search endpoint - it uses filtered searches
    which provide more reliable and complete results than unfiltered search.
    
    Results are cached for 15 minutes.
    
    Returns:
        {"artists": [...], "albums": [...], "songs": [...]}
    """
    try:
        results = search_service.search_all(
            query=q,
            limit_per_type=limit,
            use_cache=True
        )
        return results
    except Exception as e:
        logger.exception(f"Search failed for query '{q}'")
        raise HTTPException(
            status_code=503,
            detail=f"Search service unavailable: {str(e)}"
        )


@router.get("/artists", response_model=List[Dict[str, Any]])
def search_artists_only(
    current_user: User = Depends(require_auth),
    q: str = Query(..., min_length=1, description="Query string"),
    limit: int = Query(10, ge=1, le=50, description="Max results"),
) -> List[Dict[str, Any]]:
    """
    Search for artists only.
    
    Returns:
        List of artist results
    """
    try:
        results = search_service.search_artists(
            query=q,
            limit=limit,
            use_cache=True
        )
        return results
    except Exception as e:
        logger.exception(f"Artist search failed for query '{q}'")
        raise HTTPException(
            status_code=503,
            detail=f"Artist search unavailable: {str(e)}"
        )


@router.get("/albums", response_model=List[Dict[str, Any]])
def search_albums_only(
    current_user: User = Depends(require_auth),
    q: str = Query(..., min_length=1, description="Query string"),
    limit: int = Query(10, ge=1, le=50, description="Max results"),
) -> List[Dict[str, Any]]:
    """
    Search for albums only.
    
    Returns:
        List of album results
    """
    try:
        results = search_service.search_albums(
            query=q,
            limit=limit,
            use_cache=True
        )
        return results
    except Exception as e:
        logger.exception(f"Album search failed for query '{q}'")
        raise HTTPException(
            status_code=503,
            detail=f"Album search unavailable: {str(e)}"
        )


@router.get("/songs", response_model=List[Dict[str, Any]])
def search_songs_only(
    current_user: User = Depends(require_auth),
    q: str = Query(..., min_length=1, description="Query string"),
    limit: int = Query(10, ge=1, le=50, description="Max results"),
) -> List[Dict[str, Any]]:
    """
    Search for songs only.
    
    Returns:
        List of song results
    """
    try:
        results = search_service.search_songs(
            query=q,
            limit=limit,
            use_cache=True
        )
        return results
    except Exception as e:
        logger.exception(f"Song search failed for query '{q}'")
        raise HTTPException(
            status_code=503,
            detail=f"Song search unavailable: {str(e)}"
        )


@router.get("/charts", response_model=Dict[str, Any])
def get_charts(
    current_user: User = Depends(require_auth),
    country: Optional[str] = Query("US", description="Country code (e.g., 'US', 'FR')"),
) -> Dict[str, Any]:
    """
    Get music charts for a country.
    
    Returns top artists and songs.
    Results are cached for 15 minutes.
    
    Returns:
        {"artists": [...], "songs": [...]}
    """
    try:
        results = search_service.get_charts(
            country=country,
            use_cache=True
        )
        return results
    except Exception as e:
        logger.exception(f"Charts failed for country '{country}'")
        raise HTTPException(
            status_code=503,
            detail=f"Charts service unavailable: {str(e)}"
        )


@router.delete("/cache", status_code=204)
def clear_search_cache(
    current_user: User = Depends(require_admin),
) -> None:
    """
    Clear the search cache.
    
    Admin endpoint to force refresh of cached search results.
    """
    try:
        search_service.clear_cache()
        logger.info("Search cache cleared via API")
    except Exception as e:
        logger.exception("Failed to clear search cache")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear cache: {str(e)}"
        )