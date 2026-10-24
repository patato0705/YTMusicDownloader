# backend/routers/artists.py
"""
Artist endpoints.

Endpoints :
- GET /api/artists/{artist_id} - Get artist details
- POST /api/artists/{artist_id}/follow - Follow artist (full mode)
- DELETE /api/artists/{artist_id}/follow - Unfollow artist (back to light mode)
- PUT /api/artists/{artist_id}/like - Like an artist of the library (for your recommendations)
- DELETE /api/artists/{artist_id}/like - Unlike it
"""
from __future__ import annotations
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db import get_session
from ..dependencies import require_auth, require_member_or_admin
from ..jobs.priorities import Origin
from ..models import Artist, User
from ..services import albums as albums_svc
from ..services import recommendations as recommendations_svc
from ..services import subscriptions as subs_svc
from ..ytm_service import adapter as ytm_adapter
from .albums import ytmusic_unavailable

logger = logging.getLogger("routers.artists")

router = APIRouter(prefix="/api/artists", tags=["Artists"])


@router.get("/{artist_id}", status_code=status.HTTP_200_OK)
def get_artist(
    artist_id: str,
    current_user: User = Depends(require_auth),
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """
    An artist and its releases. Followed in full, everything comes from
    the DB ("source": "database"); otherwise from YTMusic, each release
    marked with what the DB knows of it (in_database, mode, download_status).
    "liked": whether you like it (only artists of the library can be).
    """
    subscription = subs_svc.get_artist_subscription(session, artist_id)
    artist = session.get(Artist, artist_id)
    db_albums = albums_svc.list_albums_for_artist_from_db(session, artist_id) if artist else []
    liked = recommendations_svc.is_liked(session, current_user.id, artist_id)

    if subscription and subscription.mode == "full":
        return {
            "source": "database",
            "subscription_mode": "full",
            "liked": liked,
            "artist": {
                "id": artist.id,
                "name": artist.name,
                "thumbnail": artist.image_local,
                "genres": artist.genres or [],
            },
            "albums": [{**album, "in_database": True} for album in db_albums],
        }

    try:
        artist_data = ytm_adapter.get_artist(artist_id)
    except ytm_adapter.YTMusicUnavailable:
        raise ytmusic_unavailable()

    known = {album["id"]: album for album in db_albums}
    albums = []
    for release in artist_data["albums"] + artist_data["singles"]:
        album = known.get(release["id"])
        albums.append({
            "id": release["id"],
            "title": release["title"],
            "type": release["type"],
            "year": release["year"],
            "thumbnail": release["thumbnail"],
            "in_database": album is not None,
            "mode": album["mode"] if album else None,
            "download_status": album["download_status"] if album else None,
        })
    return {
        "source": "ytmusic",
        "subscription_mode": subscription.mode if subscription else None,
        "liked": liked,
        "artist": {
            "id": artist_data["id"],
            "name": artist_data["name"],
            # The picture already saved, else YouTube Music's
            "thumbnail": (artist.image_local if artist else None) or artist_data["thumbnail"],
            "genres": (artist.genres or []) if artist else [],
        },
        "albums": albums,
    }


@router.post("/{artist_id}/follow", status_code=status.HTTP_200_OK)
def follow_artist(
    artist_id: str,
    name: Optional[str] = Body(None, embed=True, max_length=255),
    current_user: User = Depends(require_member_or_admin),
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """
    Follow an artist in full (downloads everything), upgrading a light
    subscription, and like it (no longer "not interested" either):
    following is a choice of yours, unlike the follows of charts and
    playlists. `name` is the artist's name as the page shows it, for its
    row until the sync job fetches the artist and its releases.
    """
    followed = subs_svc.follow_artist(session, artist_id, name, user_id=current_user.id, origin=Origin.USER)
    session.flush()  # autoflush=False: the like checks the new subscription
    recommendations_svc.like(session, current_user.id, artist_id)
    recommendations_svc.restore(session, current_user.id, artist_id)
    session.commit()
    if followed:
        logger.info("Artist %s followed in full mode by user %s", artist_id, current_user.id)
    return {"artist_id": artist_id, "mode": "full", "liked": True}


@router.delete("/{artist_id}/follow", status_code=status.HTTP_200_OK)
def unfollow_artist(
    artist_id: str,
    current_user: User = Depends(require_member_or_admin),
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """
    Unfollow an artist: back to a light subscription, its albums to metadata
    mode and their pending downloads cancelled. Files and rows stay.
    """
    subscription = subs_svc.get_artist_subscription(session, artist_id)
    if not subscription:
        raise HTTPException(status_code=404, detail="Artist is not followed")

    downgraded = subs_svc.downgrade_all_albums_to_metadata(session, artist_id)
    subscription.mode = "light"
    session.commit()

    logger.info("Artist %s unfollowed: light mode, %s albums back to metadata", artist_id, downgraded)
    return {"artist_id": artist_id, "albums_downgraded": downgraded}


@router.put("/{artist_id}/like", status_code=status.HTTP_200_OK)
def like_artist(
    artist_id: str,
    current_user: User = Depends(require_member_or_admin),
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """Like an artist of the library: its similar artists join your recommendations."""
    if not recommendations_svc.like(session, current_user.id, artist_id):
        raise HTTPException(status_code=404, detail="Artist is not in the library")
    session.commit()
    return {"artist_id": artist_id, "liked": True}


@router.delete("/{artist_id}/like", status_code=status.HTTP_200_OK)
def unlike_artist(
    artist_id: str,
    current_user: User = Depends(require_member_or_admin),
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    recommendations_svc.unlike(session, current_user.id, artist_id)
    session.commit()
    return {"artist_id": artist_id, "liked": False}
