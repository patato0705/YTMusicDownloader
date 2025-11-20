# backend/routers/playlists.py
from __future__ import annotations
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..deps import get_db

logger = logging.getLogger("routers.playlists")

router = APIRouter(prefix="/api/playlists", tags=["Playlists"])


@router.get("/{playlist_id}", response_model=Dict[str, Any])
def get_playlist(playlist_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Return playlist metadata (including tracks when provided by adapter/service).
    Prefers services.playlists.get_playlist(...) if present, otherwise falls back to ytm_service.adapter.get_playlist(...).
    """
    if not playlist_id:
        raise HTTPException(status_code=400, detail="playlist_id required")
    try:
        # Adapter
        try:
            from ..ytm_service import adapter as ytm_adapter
            return ytm_adapter.get_playlist(playlist_id)
        except Exception as e:
            logger.exception("ytm_service.adapter.get_playlist failed for %s: %s", playlist_id, e)
            raise HTTPException(status_code=500, detail="Failed fetching playlist")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unhandled error in get_playlist %s", playlist_id)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{playlist_id}/tracks", response_model=List[Dict[str, Any]])
def get_playlist_tracks(playlist_id: str, db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    """
    Return a lightweight list of tracks for the playlist.
    Prefer services.playlists.list_tracks(...) if present, otherwise use adapter.get_playlist(...).
    """
    if not playlist_id:
        raise HTTPException(status_code=400, detail="playlist_id required")
    try:
        # Try service first
        try:
            from .. import services

            svc = getattr(services, "playlists", None)
            if svc and hasattr(svc, "list_tracks"):
                try:
                    return svc.list_tracks(db=db, playlist_id=playlist_id)  # type: ignore
                except TypeError:
                    return svc.list_tracks(playlist_id=playlist_id)  # type: ignore
        except Exception:
            logger.debug("services.playlists.list_tracks not available; falling back to adapter", exc_info=True)

        # Fallback: adapter
        try:
            from ..ytm_service import adapter as ytm_adapter

            pl = ytm_adapter.get_playlist(playlist_id)
            tracks = pl.get("tracks") or []
            # ensure list of dicts
            if not isinstance(tracks, list):
                return []
            return tracks
        except Exception as e:
            logger.exception("Failed obtaining playlist tracks for %s: %s", playlist_id, e)
            raise HTTPException(status_code=500, detail="Failed fetching playlist tracks")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unhandled error in get_playlist_tracks %s", playlist_id)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/{playlist_id}/import", response_model=Dict[str, Any])
def import_playlist(playlist_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Import (fetch + upsert) playlist into the local DB.
    Requires services.playlists to implement a function such as `fetch_and_upsert_playlist`
    (common names: fetch_and_upsert_playlist, import_playlist, upsert_playlist).
    If no suitable service function exists, returns 400.
    """
    if not playlist_id:
        raise HTTPException(status_code=400, detail="playlist_id required")
    try:
        from .. import services

        svc = getattr(services, "playlists", None)
        if not svc:
            logger.warning("services.playlists not available; cannot import playlist %s", playlist_id)
            raise HTTPException(status_code=400, detail="Import service not available")

        # try a few likely function names
        try_names = ["fetch_and_upsert_playlist", "import_playlist", "upsert_playlist", "ensure_playlist"]
        for nm in try_names:
            fn = getattr(svc, nm, None)
            if fn is None:
                continue
            try:
                # prefer call with db if accepted
                try:
                    res = fn(session=db, playlist_id=playlist_id)  # type: ignore
                except TypeError:
                    res = fn(playlist_id=playlist_id)  # type: ignore
                return {"ok": True, "result": res}
            except Exception:
                logger.exception("services.playlists.%s failed for %s", nm, playlist_id)
                raise HTTPException(status_code=500, detail=f"Import failed ({nm})")
        # no suitable function found
        logger.warning("No suitable import function in services.playlists for %s", playlist_id)
        raise HTTPException(status_code=400, detail="No import function available for playlists")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unhandled error importing playlist %s", playlist_id)
        raise HTTPException(status_code=500, detail=str(exc))