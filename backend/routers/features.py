# backend/routers/features.py
"""
Feature flag endpoints.

Endpoints:
- GET /api/features - Which optional features are enabled (any authenticated user)

Admins manage the flags through /api/admin/settings; this endpoint exists so
that non-admin clients (e.g. the navbar) can read them without admin rights.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_session
from ..dependencies import require_auth
from ..models import User
from ..settings import feature_enabled

router = APIRouter(prefix="/api/features", tags=["Features"])


@router.get("")
def get_features(
    current_user: User = Depends(require_auth),
    session: Session = Depends(get_session),
) -> dict:
    """Return the state of every feature flag the UI depends on."""
    return {"charts_enabled": feature_enabled(session, "charts")}
