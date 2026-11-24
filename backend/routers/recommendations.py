# backend/routers/recommendations.py
"""
Artist recommendations (see services/recommendations.py).

Endpoints :
- GET /api/recommendations - Your recommended artists, how many artists you like and how many you dismissed
- GET /api/recommendations/dismissed - Your dismissed artists
- PUT /api/recommendations/dismissed/{artist_id} - Dismiss an artist ("not interested"), for you only
- DELETE /api/recommendations/dismissed/{artist_id} - Restore an artist you dismissed
"""
from __future__ import annotations
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..db import get_session
from ..dependencies import require_auth, require_member_or_admin
from ..models import User
from ..services import recommendations as recommendations_svc

logger = logging.getLogger("routers.recommendations")

router = APIRouter(prefix="/api/recommendations", tags=["Recommendations"])


@router.get("", status_code=status.HTTP_200_OK)
def get_recommendations(
    limit: int = Query(recommendations_svc.DEFAULT_LIMIT, ge=1, le=100),
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_session),
) -> Dict[str, Any]:
    return {
        "recommendations": recommendations_svc.list_recommendations(db, current_user.id, limit=limit),
        "liked_count": recommendations_svc.count_liked(db, current_user.id),
        "dismissed_count": recommendations_svc.count_dismissed(db, current_user.id),
    }


@router.get("/dismissed", status_code=status.HTTP_200_OK)
def get_dismissed(
    current_user: User = Depends(require_member_or_admin),
    db: Session = Depends(get_session),
) -> Dict[str, Any]:
    return {"dismissed": recommendations_svc.list_dismissed(db, current_user.id)}


@router.put("/dismissed/{artist_id}", status_code=status.HTTP_200_OK)
def dismiss_artist(
    artist_id: str,
    current_user: User = Depends(require_member_or_admin),
    db: Session = Depends(get_session),
) -> Dict[str, Any]:
    if not recommendations_svc.dismiss(db, current_user.id, artist_id):
        raise HTTPException(status_code=404, detail="Unknown artist")
    db.commit()
    logger.info("User %s dismissed recommended artist %s", current_user.username, artist_id)
    return {"ok": True, "artist_id": artist_id}


@router.delete("/dismissed/{artist_id}", status_code=status.HTTP_200_OK)
def restore_artist(
    artist_id: str,
    current_user: User = Depends(require_member_or_admin),
    db: Session = Depends(get_session),
) -> Dict[str, Any]:
    if not recommendations_svc.restore(db, current_user.id, artist_id):
        raise HTTPException(status_code=404, detail="Artist not dismissed")
    db.commit()
    logger.info("User %s restored recommended artist %s", current_user.username, artist_id)
    return {"ok": True, "artist_id": artist_id}
