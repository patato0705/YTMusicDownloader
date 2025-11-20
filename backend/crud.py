# backend/crud.py
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple, cast

from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

from .models import Artist, Album, Track, Job


# ---- Artists ----
def list_artists(session: Session, limit: int = 100, offset: int = 0) -> List[Artist]:
    stmt = select(Artist).order_by(Artist.name).limit(limit).offset(offset)
    res = session.execute(stmt).scalars()
    return cast(List[Artist], list(res))


def count_artists(session: Session) -> int:
    stmt = select(func.count()).select_from(Artist)
    return int(session.execute(stmt).scalar_one_or_none() or 0)


def get_artist(session: Session, artist_id: str) -> Optional[Artist]:
    if not artist_id:
        return None
    return session.get(Artist, artist_id)


# ---- Albums ----
def list_albums(session: Session, artist_id: Optional[str] = None, limit: int = 200, offset: int = 0) -> List[Album]:
    if artist_id:
        stmt = select(Album).where(Album.artist_id == artist_id).order_by(Album.year.desc(), Album.title).limit(limit).offset(offset)
    else:
        stmt = select(Album).order_by(Album.year.desc(), Album.title).limit(limit).offset(offset)
    res = session.execute(stmt).scalars()
    return cast(List[Album], list(res))


def count_albums(session: Session, artist_id: Optional[str] = None) -> int:
    if artist_id:
        stmt = select(func.count()).select_from(Album).where(Album.artist_id == artist_id)
    else:
        stmt = select(func.count()).select_from(Album)
    return int(session.execute(stmt).scalar_one_or_none() or 0)


def get_album(session: Session, album_id: str) -> Optional[Album]:
    if not album_id:
        return None
    return session.get(Album, album_id)


# ---- Tracks ----
def list_tracks(session: Session, album_id: Optional[str] = None, status: Optional[str] = None, limit: int = 500, offset: int = 0) -> List[Track]:
    stmt = select(Track)
    if album_id:
        stmt = stmt.where(Track.album_id == album_id)
    if status:
        stmt = stmt.where(Track.status == status)
    stmt = stmt.order_by(Track.created_at.desc()).limit(limit).offset(offset)
    res = session.execute(stmt).scalars()
    return cast(List[Track], list(res))


def count_tracks(session: Session, album_id: Optional[str] = None) -> int:
    stmt = select(func.count()).select_from(Track)
    if album_id:
        stmt = stmt.where(Track.album_id == album_id)
    return int(session.execute(stmt).scalar_one_or_none() or 0)


def get_track(session: Session, track_id: str) -> Optional[Track]:
    if not track_id:
        return None
    return session.get(Track, track_id)


# ---- Jobs (convenience) ----
def list_jobs(session: Session, job_type: Optional[str] = None, limit: int = 100, offset: int = 0) -> List[Job]:
    stmt = select(Job)
    if job_type:
        stmt = stmt.where(Job.type == job_type)
    stmt = stmt.order_by(Job.created_at.desc()).limit(limit).offset(offset)
    res = session.execute(stmt).scalars()
    return cast(List[Job], list(res))


def get_job(session: Session, job_id: int) -> Optional[Job]:
    if job_id is None:
        return None
    return session.get(Job, job_id)