# backend/routers/playlists.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_session
from ..dependencies import require_auth
from ..models import User
from ..ytm_service import adapter

router = APIRouter(prefix="/api/playlists", tags=["Playlists"])


@router.get("/{playlist_id}")
def get_playlist(
    playlist_id: str,
    current_user: User = Depends(require_auth),
):
    """
    Get playlist details with track/album info.
    
    Use this to extract album IDs from playlists for bulk following.
    Playlists are not saved to library.
    """
    return adapter.get_playlist(playlist_id)


@router.get("/{playlist_id}/albums")
def extract_albums_from_playlist(
    playlist_id: str,
    current_user: User = Depends(require_auth),
    session: Session = Depends(get_session),
):
    """
    Extract unique album IDs from a playlist.
    Returns list of albums for bulk operations.
    """
    playlist = adapter.get_playlist(playlist_id)
    
    # Extract unique album IDs
    album_ids = set()
    for track in playlist.get("tracks", []):
        if track.get("album") and track["album"].get("id"):
            album_ids.add(track["album"]["id"])
    
    return {
        "playlist_id": playlist_id,
        "playlist_title": playlist.get("title"),
        "album_count": len(album_ids),
        "album_ids": list(album_ids),
    }