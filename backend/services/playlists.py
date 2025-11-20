# backend/services/playlists.py
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from . import normalizers as N

from ..ytm_service import adapter as ytm_adapter
from ..models import Track
from .tracks import upsert_track

logger = logging.getLogger("services.playlists")

def fetch_and_upsert_playlist(session: Session, playlist_id: str, owner_artist_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetch playlist data from YTMusic adapter and upsert its tracks into DB.

    - session: SQLAlchemy session (caller controls commit)
    - playlist_id: audio playlist id (audioPlaylistId) or other playlist id understood by adapter
    - owner_artist_id: optional artist id to attach to each upserted track.album_id or to mark origin

    Returns a dict summary:
      {
        "playlist_id": str,
        "title": Optional[str],
        "inserted_tracks": int,
        "updated_tracks": int,
        "errors": int
      }
    """
    if not playlist_id:
        raise ValueError("playlist_id required")

    try:
        data = ytm_adapter.get_playlist(playlist_id) or {}
    except Exception:
        logger.exception("ytm_adapter.get_playlist failed for %s", playlist_id)
        data = {}

    title = data.get("title")
    thumbnails = data.get("thumbnails") or []
    tracks = data.get("tracks") or []

    inserted = 0
    updated = 0
    errors = 0

    for t in tracks or []:
        try:
            vid = t.get("id") or t.get("videoId") or None
            if not vid:
                logger.debug("Skipping playlist track without id in playlist %s: %r", playlist_id, t)
                continue

            track_title = t.get("title") or t.get("name") or ""
            duration = t.get("duration_seconds") or t.get("duration") or None
            artists_for_db = N.normalize_track_for_db(t)

            # try to detect existing track to determine insert vs update
            pre = session.get(Track, str(vid))
            # delegate to artists.upsert_track which centralizes Track upsert logic
            try:
                upsert_track(
                    session=session,
                    track_id=str(vid),
                    title=track_title or "",
                    duration_seconds=int(duration) if duration is not None else None,
                    artists_list=artists_for_db,
                    album_id=str(playlist_id),
                    # track_number unknown for playlists — leave None
                    track_number=None,
                    status="new" if (not pre or not getattr(pre, "file_path", None)) else getattr(pre, "status", "done"),
                    file_path=getattr(pre, "file_path", None) if pre else None,
                    artist_valid=True,
                )
            except Exception:
                logger.exception("Failed upsert_track %s for playlist %s", vid, playlist_id)
                errors += 1
                continue

            if pre is None:
                inserted += 1
            else:
                updated += 1
        except Exception:
            logger.exception("Error processing playlist track %r", t)
            errors += 1
            continue

    # flush so caller can commit if desired
    try:
        session.flush()
    except Exception:
        logger.debug("session.flush() failed after upsert playlist %s", playlist_id, exc_info=True)

    return {
        "playlist_id": str(playlist_id),
        "title": title,
        "inserted_tracks": inserted,
        "updated_tracks": updated,
        "errors": errors,
        "thumbnails": thumbnails,
    }


def list_tracks_for_playlist_from_db(session: Session, playlist_id: str) -> List[Dict[str, Optional[Any]]]:
    """
    Lightweight list of tracks for a playlist (based on Track.album_id == playlist_id).
    Returns list of dicts with keys: id, title, duration, file_path, status.
    """
    out: List[Dict[str, Optional[Any]]] = []
    if not playlist_id:
        return out
    try:
        q = session.query(Track).filter(Track.album_id == str(playlist_id)).order_by(Track.title.asc())
        for tr in q.all():
            out.append({
                "id": getattr(tr, "id", None),
                "title": getattr(tr, "title", None),
                "duration": getattr(tr, "duration", None),
                "file_path": getattr(tr, "file_path", None),
                "status": getattr(tr, "status", None),
            })
    except Exception:
        logger.exception("list_tracks_for_playlist_from_db failed for %s", playlist_id)
    return out