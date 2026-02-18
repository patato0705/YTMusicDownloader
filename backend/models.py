# backend/models.py
from __future__ import annotations
import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import String, Integer, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.dialects.sqlite import JSON as SQLiteJSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from backend.time_utils import now_utc, ensure_timezone_aware

logger = __import__("logging").getLogger("models")

# Declarative base (SQLAlchemy 2.0)
class Base(DeclarativeBase):
    pass


# JSON column alias (SQLite uses its dialect JSON)
JSONCol = SQLiteJSON


class Artist(Base):
    __tablename__ = "artists"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    thumbnails: Mapped[Optional[List[Any]]] = mapped_column(JSONCol, nullable=True)
    image_local: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    followed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # CHANGED from monitored
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)

    # relationship: Artist -> Album
    albums: Mapped[List["Album"]] = relationship(
        "Album",
        back_populates="artist",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def to_dict(self) -> Dict[str, Any]:
        thumbs = getattr(self, "thumbnails", None) or []
        image_local = getattr(self, "image_local", None)
        followed = bool(getattr(self, "followed", False))  # CHANGED from monitored
        created_at_val = getattr(self, "created_at", None)
        created_at = created_at_val.isoformat() if created_at_val is not None else None

        return {
            "id": getattr(self, "id", None),
            "name": getattr(self, "name", None),
            "thumbnails": thumbs,
            "image_local": image_local,
            "followed": followed,  # CHANGED from monitored
            "created_at": created_at,
        }

    def __repr__(self) -> str:
        return f"<Artist id={self.id!r} name={self.name!r}>"


class Album(Base):
    __tablename__ = "albums"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    artist_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("artists.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    thumbnails: Mapped[Optional[List[Any]]] = mapped_column(JSONCol, nullable=True)
    playlist_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    year: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    image_local: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)

    # relationships
    artist: Mapped[Optional[Artist]] = relationship("Artist", back_populates="albums")
    tracks: Mapped[List["Track"]] = relationship(
        "Track",
        back_populates="album",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def to_dict(self) -> Dict[str, Any]:
        thumbs = getattr(self, "thumbnails", None) or []
        return {
            "id": getattr(self, "id", None),
            "title": getattr(self, "title", None),
            "artist_id": getattr(self, "artist_id", None),
            "thumbnails": thumbs,
            "playlist_id": getattr(self, "playlist_id", None),
            "year": getattr(self, "year", None),
            "image_local": getattr(self, "image_local", None),
        }

    def __repr__(self) -> str:
        return f"<Album id={self.id!r} title={self.title!r}>"


class Track(Base):
    __tablename__ = "tracks"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    title: Mapped[str] = mapped_column(String(1024), nullable=False, index=True)
    duration: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    artists: Mapped[Optional[List[Dict[str, Optional[str]]]]] = mapped_column(JSONCol, nullable=True)
    album_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("albums.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    track_number: Mapped[int] = mapped_column(Integer, nullable=True)
    has_lyrics: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    lyrics_local: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    status: Mapped[str] = mapped_column(String(64), default="new", nullable=False)
    artist_valid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)

    album: Mapped[Optional[Album]] = relationship("Album", back_populates="tracks")

    def to_dict(self) -> Dict[str, Any]:
        artists_val = getattr(self, "artists", None) or []
        created_at_val = getattr(self, "created_at", None)
        created_at_iso = created_at_val.isoformat() if isinstance(created_at_val, datetime.datetime) else None

        return {
            "id": getattr(self, "id", None),
            "title": getattr(self, "title", None),
            "duration": getattr(self, "duration", None),
            "artists": artists_val,
            "album_id": getattr(self, "album_id", None),
            "has_lyrics": bool(getattr(self, "has_lyrics", False)),
            "lyrics_local": getattr(self, "lyrics_local", None),
            "file_path": getattr(self, "file_path", None),
            "status": getattr(self, "status", None),
            "artist_valid": bool(getattr(self, "artist_valid", True)),
            "created_at": created_at_iso,
        }

    def __repr__(self) -> str:
        return f"<Track id={self.id!r} title={self.title!r}>"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[Optional[Any]] = mapped_column(JSONCol, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    scheduled_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    started_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result: Mapped[Optional[Any]] = mapped_column(JSONCol, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    reserved_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": getattr(self, "id", None),
            "type": getattr(self, "type", None),
            "payload": getattr(self, "payload", None) or {},
            "status": getattr(self, "status", None),
            "attempts": getattr(self, "attempts", 0),
            "max_attempts": getattr(self, "max_attempts", 0),
            "priority": getattr(self, "priority", 0),
            "scheduled_at": scheduled.isoformat() if (scheduled := getattr(self, "scheduled_at", None)) else None,
            "started_at": started.isoformat() if (started := getattr(self, "started_at", None)) else None,
            "finished_at": finished.isoformat() if (finished := getattr(self, "finished_at", None)) else None,
            "last_error": getattr(self, "last_error", None),
            "result": getattr(self, "result", None),
            "created_at": created.isoformat() if (created := getattr(self, "created_at", None)) else None,
            "reserved_by": getattr(self, "reserved_by", None),
            "user_id": getattr(self, "user_id", None),  # NEW
        }


# Subscriptions
class ArtistSubscription(Base):
    __tablename__ = "artist_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, nullable=False)
    artist_id: Mapped[str] = mapped_column(String(64), ForeignKey("artists.id", ondelete="CASCADE"), nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="full")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    last_synced_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class AlbumSubscription(Base):
    __tablename__ = "album_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, nullable=False)
    album_id: Mapped[str] = mapped_column(String(64), ForeignKey("albums.id", ondelete="CASCADE"), nullable=False, index=True)
    artist_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("artists.id", ondelete="CASCADE"), nullable=True, index=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="download")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    last_synced_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    download_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, default="idle")
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# Authentication

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="member")  # administrator, member, visitor
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    last_login_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        """Return user data (excluding password)"""
        created = getattr(self, "created_at", None)
        last_login = getattr(self, "last_login_at", None)
        
        return {
            "id": getattr(self, "id", None),
            "username": getattr(self, "username", None),
            "email": getattr(self, "email", None),
            "role": getattr(self, "role", "member"),
            "is_active": bool(getattr(self, "is_active", True)),
            "created_at": created.isoformat() if created else None,
            "last_login_at": last_login.isoformat() if last_login else None,
        }

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r} role={self.role}>"


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(String(512), unique=True, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    def is_valid(self) -> bool:
        """Check if token is still valid"""
        if self.revoked:
            return False
        
        # Ensure expires_at is timezone-aware before comparison
        expires = ensure_timezone_aware(self.expires_at)
        if expires is None:
            # Should never happen since expires_at is non-nullable
            return False
        
        return now_utc() < expires
    
    def __repr__(self) -> str:
        return f"<RefreshToken id={self.id} user_id={self.user_id} revoked={self.revoked}>"


# App settings

class Setting(Base):
    """
    Application settings - user-configurable values.
    Key-value store for settings like schedules, feature flags, etc.
    """
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False, default="string")  # string, int, bool, json
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)
    updated_by: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    def to_dict(self) -> Dict[str, Any]:
        updated = getattr(self, "updated_at", None)
        return {
            "key": getattr(self, "key", None),
            "value": self.get_typed_value(),
            "type": getattr(self, "type", "string"),
            "description": getattr(self, "description", None),
            "updated_at": updated.isoformat() if updated else None,
            "updated_by": getattr(self, "updated_by", None),
        }
    
    def get_typed_value(self) -> Any:
        """Return value with proper type conversion"""
        value = getattr(self, "value", None)
        setting_type = getattr(self, "type", "string")
        
        if value is None:
            return None
        
        if setting_type == "int":
            try:
                return int(value)
            except (ValueError, TypeError):
                return None
        
        elif setting_type == "bool":
            return value.lower() in ("true", "1", "yes", "on")
        
        elif setting_type == "json":
            try:
                import json
                return json.loads(value)
            except Exception:
                return None
        
        else:  # string
            return value
    
    def set_value(self, value: Any) -> None:
        """Set value with type conversion to string"""
        if value is None:
            self.value = None
        elif self.type == "json":
            import json
            self.value = json.dumps(value)
        elif self.type == "bool":
            self.value = "true" if value else "false"
        else:
            self.value = str(value)

    def __repr__(self) -> str:
        return f"<Setting key={self.key!r} value={self.value!r}>"