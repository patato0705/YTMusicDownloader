# backend/routers/search.py
"""
Search endpoints.

Endpoints:
- GET /api/search - Search artists, albums and songs
"""
from __future__ import annotations
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..dependencies import require_auth
from ..models import ArtistSubscription, User
from ..services import search as search_service
from ..ytm_service.adapter import YTMusicUnavailable
from .albums import ytmusic_unavailable

router = APIRouter(prefix="/api/search", tags=["Search"])


@router.get("", response_model=Dict[str, List[Dict[str, Any]]])
def search(
    current_user: User = Depends(require_auth),
    q: str = Query(..., min_length=1, description="Query string to search for"),
    limit: int = Query(10, ge=1, le=50, description="Max results per type"),
    session: Session = Depends(get_session),
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Search YouTube Music: {"artists": [...], "albums": [...], "songs": [...]},
    from one filtered search per type. Results are cached for 15 minutes;
    each artist's "followed" (in full) is read fresh, for its follow button.
    """
    try:
        results = search_service.search_all(q, limit_per_type=limit)
    except YTMusicUnavailable:
        raise ytmusic_unavailable()

    artist_ids = [a["id"] for a in results["artists"]]
    followed = set(session.execute(
        select(ArtistSubscription.artist_id).where(
            ArtistSubscription.artist_id.in_(artist_ids),
            ArtistSubscription.enabled == True,  # noqa: E712
            ArtistSubscription.mode == "full",
        )
    ).scalars()) if artist_ids else set()
    # Copies: the cached results stay as YouTube Music gave them
    return {**results, "artists": [{**a, "followed": a["id"] in followed} for a in results["artists"]]}
