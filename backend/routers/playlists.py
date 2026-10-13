# backend/routers/playlists.py
"""
Playlist endpoints (see services/playlists.py).

Endpoints :
- GET /api/playlists - Playlists added to the library
- GET /api/playlists/{playlist_id} - A YouTube Music playlist with its tracks, and
  how it's added to the library ("saved", null if it isn't)
- POST /api/playlists/{playlist_id} - Add a playlist (mode, followed, m3u)
- PATCH /api/playlists/{playlist_id} - Change how it's added
- POST /api/playlists/{playlist_id}/sync - Rescan a followed playlist now
- DELETE /api/playlists/{playlist_id} - Remove it (and its M3U; the music stays)
"""
from __future__ import annotations
import logging
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..dependencies import require_auth, require_member_or_admin
from ..jobs.priorities import Origin
from ..models import Album, ArtistSubscription, Playlist, User
from ..services import playlists as playlists_svc
from ..ytm_service import adapter
from ..ytm_service.adapter import YTMusicUnavailable

logger = logging.getLogger("routers.playlists")

router = APIRouter(prefix="/api/playlists", tags=["Playlists"])


class AddPlaylistRequest(BaseModel):
    mode: Literal["albums", "artists"]
    followed: bool
    m3u: bool


class UpdatePlaylistRequest(BaseModel):
    mode: Optional[Literal["albums", "artists"]] = None
    followed: Optional[bool] = None
    m3u: Optional[bool] = None


def _unreadable() -> HTTPException:
    """Private playlists can't be told apart from YouTube Music not answering: one code for both."""
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="playlist_unavailable")


def _saved(session: Session, playlist_id: str) -> Playlist:
    playlist = session.get(Playlist, playlist_id)
    if playlist is None:
        raise HTTPException(status_code=404, detail="Playlist not added")
    return playlist


@router.get("")
def list_playlists(
    current_user: User = Depends(require_auth),
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    return {"playlists": playlists_svc.list_playlists(session)}


@router.get("/{playlist_id}")
def get_playlist(
    playlist_id: str,
    current_user: User = Depends(require_auth),
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """The playlist from YouTube Music, with how it's added to the library ("saved")."""
    try:
        data = adapter.get_playlist(playlist_id)
    except YTMusicUnavailable:
        raise _unreadable()
    playlist = session.get(Playlist, playlist_id)
    tracks = data.get("tracks") or []
    artist_ids = {a["id"] for t in tracks for a in t.get("artists") or [] if a.get("id")}
    album_ids = {(t.get("album") or {}).get("id") for t in tracks} - {None}
    # What's already in the library, so the page shows Followed / Downloaded
    followed_artists = session.scalars(
        select(ArtistSubscription.artist_id).where(
            ArtistSubscription.artist_id.in_(artist_ids),
            ArtistSubscription.enabled.is_(True),
            ArtistSubscription.mode == "full",
        )
    ).all() if artist_ids else []
    downloaded_albums = session.scalars(
        select(Album.id).where(Album.id.in_(album_ids), Album.mode == "download")
    ).all() if album_ids else []
    return {
        **data,
        "saved": playlists_svc.summary(session, playlist) if playlist else None,
        "followed_artists": list(followed_artists),
        "downloaded_albums": list(downloaded_albums),
    }


@router.post("/{playlist_id}", status_code=status.HTTP_201_CREATED)
def add_playlist(
    playlist_id: str,
    body: AddPlaylistRequest,
    current_user: User = Depends(require_member_or_admin),
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    try:
        playlist = playlists_svc.add_playlist(
            session, playlist_id,
            mode=body.mode, followed=body.followed, m3u=body.m3u, user_id=current_user.id,
        )
    except playlists_svc.PlaylistAlreadyAdded:
        raise HTTPException(status_code=409, detail="Playlist already added")
    except YTMusicUnavailable:
        session.rollback()
        raise _unreadable()
    except ValueError as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    logger.info("User %s added playlist %s", current_user.username, playlist_id)
    return playlists_svc.summary(session, playlist)


@router.patch("/{playlist_id}")
def update_playlist(
    playlist_id: str,
    body: UpdatePlaylistRequest,
    current_user: User = Depends(require_member_or_admin),
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    playlist = _saved(session, playlist_id)
    try:
        playlists_svc.update_playlist(session, playlist, mode=body.mode, followed=body.followed, m3u=body.m3u)
    except ValueError as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    logger.info("User %s changed playlist %s: %s", current_user.username, playlist_id, body.model_dump(exclude_none=True))
    return playlists_svc.summary(session, playlist)


@router.post("/{playlist_id}/sync")
def sync_playlist(
    playlist_id: str,
    current_user: User = Depends(require_member_or_admin),
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    playlist = _saved(session, playlist_id)
    if not playlist.followed:
        raise HTTPException(status_code=400, detail="Only a followed playlist is rescanned")
    # Like a scheduled rescan: it only brings in what's new
    playlists_svc.queue_sync(session, playlist, origin=Origin.AUTO, fetch=True)
    session.commit()
    return playlists_svc.summary(session, playlist)


@router.delete("/{playlist_id}")
def remove_playlist(
    playlist_id: str,
    current_user: User = Depends(require_member_or_admin),
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    playlist = _saved(session, playlist_id)
    playlists_svc.remove_playlist(session, playlist)
    logger.info("User %s removed playlist %s", current_user.username, playlist_id)
    return {"ok": True, "playlist_id": playlist_id}
