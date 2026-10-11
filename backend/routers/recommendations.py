# backend/routers/recommendations.py

"""
Artist recommendations (see services/recommendations.py).

Endpoints :
- GET /api/recommendations - Recommended artists, and how many are dismissed
- GET /api/recommendations/dismissed - Dismissed artists
- PUT /api/recommendations/dismissed/{artist_id} - Dismiss an artist ("not interested")
- DELETE /api/recommendations/dismissed/{artist_id} - Restore a dismissed artist
"""
from __future__ import annotations
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..deps import get_db
from ..services import recommendations as recommendations_svc
from backend.dependencies import require_auth, require_member_or_admin
from backend.models import User

logger = logging.getLogger("routers.recommendations")

router = APIRouter(prefix="/api/recommendations", tags=["Recommendations"])


@router.get("", status_code=status.HTTP_200_OK)
def get_recommendations(
    limit: int = Query(recommendations_svc.DEFAULT_LIMIT, ge=1, le=100),
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return {
        "recommendations": recommendations_svc.list_recommendations(db, limit=limit),
        "dismissed_count": recommendations_svc.count_dismissed(db),
    }


@router.get("/dismissed", status_code=status.HTTP_200_OK)
def get_dismissed(
    current_user: User = Depends(require_member_or_admin),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return {"dismissed": recommendations_svc.list_dismissed(db)}


@router.put("/dismissed/{artist_id}", status_code=status.HTTP_200_OK)
def dismiss_artist(
    artist_id: str,
    current_user: User = Depends(require_member_or_admin),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    if not recommendations_svc.dismiss(db, artist_id, user_id=current_user.id):
        raise HTTPException(status_code=404, detail="Unknown artist")
    db.commit()
    logger.info("User %s dismissed recommended artist %s", current_user.username, artist_id)
    return {"ok": True, "artist_id": artist_id}


@router.delete("/dismissed/{artist_id}", status_code=status.HTTP_200_OK)
def restore_artist(
    artist_id: str,
    current_user: User = Depends(require_member_or_admin),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    if not recommendations_svc.restore(db, artist_id):
        raise HTTPException(status_code=404, detail="Artist not dismissed")
    db.commit()
    logger.info("User %s restored recommended artist %s", current_user.username, artist_id)
    return {"ok": True, "artist_id": artist_id}
