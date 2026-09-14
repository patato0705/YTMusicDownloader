# backend/routers/features.py
"""
Feature flag endpoints.

Endpoints:
- GET /api/features - Which optional features are enabled (any authenticated user)

Admins manage the flags through /api/admin/settings; this endpoint exists so
that non-admin clients (e.g. the navbar) can read them without admin rights.
"""
from __future__ import annotations
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.db import get_session
from backend.dependencies import require_auth
from backend.models import User
from backend.settings import get_setting

logger = logging.getLogger("routers.features")

router = APIRouter(prefix="/api/features", tags=["Features"])


def charts_enabled(session: Session) -> bool:
    return bool(get_setting(session, "features.charts_enabled", True))


def lyrics_enabled(session: Session) -> bool:
    return bool(get_setting(session, "features.lyrics_enabled", True))


def require_charts_enabled(session: Session = Depends(get_session)) -> None:
    """Dependency: reject the request when the charts feature is switched off."""
    if not charts_enabled(session):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Charts feature is disabled",
        )


@router.get("")
def get_features(
    current_user: User = Depends(require_auth),
    session: Session = Depends(get_session),
) -> dict:
    """Return the state of every user-visible feature flag."""
    return {
        "charts_enabled": charts_enabled(session),
        "lyrics_enabled": lyrics_enabled(session),
    }
