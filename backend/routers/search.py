# backend/routers/search.py
"""
Search endpoints.

Endpoints:
- GET /api/search - Search artists, albums and songs
"""
from __future__ import annotations
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Query

from ..dependencies import require_auth
from ..models import User
from ..services import search as search_service
from ..ytm_service.adapter import YTMusicUnavailable
from .albums import ytmusic_unavailable

router = APIRouter(prefix="/api/search", tags=["Search"])


@router.get("", response_model=Dict[str, List[Dict[str, Any]]])
def search(
    current_user: User = Depends(require_auth),
    q: str = Query(..., min_length=1, description="Query string to search for"),
    limit: int = Query(10, ge=1, le=50, description="Max results per type"),
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Search YouTube Music: {"artists": [...], "albums": [...], "songs": [...]},
    from one filtered search per type. Results are cached for 15 minutes.
    """
    try:
        return search_service.search_all(q, limit_per_type=limit)
    except YTMusicUnavailable:
        raise ytmusic_unavailable()
