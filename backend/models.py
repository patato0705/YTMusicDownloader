# backend/models.py
from __future__ import annotations
import datetime
import json
from typing import Any, Dict, List, Optional

from sqlalchemy import String, Integer, Boolean, DateTime, Text, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .time_utils import now_utc, ensure_timezone_aware


class Base(DeclarativeBase):
    pass


class Artist(Base):
    __tablename__ = "artists"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # Its folder in MUSIC_DIR, picked once when its first file is written so
    # a later name change never splits its files (see services/folders.py)
    folder: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Square picture (folder.jpg), shown round in the app; the wide banner of
    # the YouTube Music artist page (backdrop.jpg) is only for media servers
    image_local: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    banner_local: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Genres (see services/genres.py): the artist's own, used for albums the
    # genre sources know nothing specific about. The ids are this artist on
    # each source, matched once and reused by later lookups.
    genres: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    musicbrainz_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    deezer_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    genres_checked_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)

    # relationship: Artist -> Album
    albums: Mapped[List["Album"]] = relationship(
        "Album",
        back_populates="artist",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    # Its "Fans might also like" (see services/recommendations.py). Deleted
    # by the ORM: SQLite isn't enforcing foreign keys here.
    related: Mapped[List["RelatedArtist"]] = relationship(
        "RelatedArtist",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Artist id={self.id!r} name={self.name!r}>"


class Album(Base):
    __tablename__ = "albums"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # Its folder inside its artist's, picked once like Artist.folder
    folder: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    artist_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("artists.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    playlist_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    year: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    image_local: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    # Up to 3 genres and where they came from (services/genres.py): e.g.
    # "musicbrainz-album", or "musicbrainz-artist" when the album itself had none
    genres: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    genres_source: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    genres_checked_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # What the library does with it, and its download progress (see services/subscriptions.py)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="metadata")  # "metadata" or "download"
    download_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, default=None)
    last_synced_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)

    # relationships
    artist: Mapped[Optional[Artist]] = relationship("Artist", back_populates="albums")
    tracks: Mapped[List["Track"]] = relationship(
        "Track",
        back_populates="album",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Album id={self.id!r} title={self.title!r}>"


class Track(Base):
    __tablename__ = "tracks"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    title: Mapped[str] = mapped_column(String(1024), nullable=False, index=True)
    duration: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    artists: Mapped[Optional[List[Dict[str, Optional[str]]]]] = mapped_column(JSON, nullable=True)
    album_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("albums.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    track_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    lyrics: Mapped[Optional[str]] = mapped_column(String(16), nullable=True, default=None)
    lyrics_local: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    # When the scheduler last queued a lyrics recovery/upgrade for this track.
    # Its sweeps take the oldest first, so every track gets a turn.
    lyrics_retried_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    # Audio file size in bytes, recorded when the download completes so the
    # library stats can sum real sizes instead of guessing.
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # available | queued | downloading | done | failed -- see services/tracks.py
    status: Mapped[str] = mapped_column(String(64), default="available", nullable=False)
    # Why the download last failed. Jobs carry the same message but get
    # cleaned up; this one stays with the track until a later attempt clears it.
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    artist_valid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)

    album: Mapped[Optional[Album]] = relationship("Album", back_populates="tracks")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "artists": self.artists or [],
            "album_id": self.album_id,
            "track_number": self.track_number,
            "duration": self.duration,
            "status": self.status,
            "last_error": self.last_error,
            "lyrics": self.lyrics,
            "lyrics_local": self.lyrics_local,
        }

    def __repr__(self) -> str:
        return f"<Track id={self.id!r} title={self.title!r}>"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    scheduled_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    started_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    reserved_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    # Touched periodically by the worker holding the job; a "reserved" job
    # whose heartbeat has gone stale belongs to a dead worker and gets
    # requeued (see jobqueue.reclaim_orphaned_jobs).
    heartbeat_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Who asked for it, when a user did (jobs queued by other jobs or the scheduler have none)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )


# Subscriptions

class ArtistSubscription(Base):
    __tablename__ = "artist_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, nullable=False)
    artist_id: Mapped[str] = mapped_column(String(64), ForeignKey("artists.id", ondelete="CASCADE"), nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="full")  # "light" or "full"
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    last_synced_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# Playlists (see services/playlists.py)

class Playlist(Base):
    """
    A YouTube Music playlist added to the library: what its songs bring in
    (their albums, or their main artists), whether it's rescanned on a
    schedule (followed) or kept as added (once), and whether it's written
    out as an M3U file.
    """
    __tablename__ = "playlists"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # YouTube Music playlist id
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    author: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    thumbnail: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="albums")  # "albums" or "artists"
    followed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    m3u: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # File name in MUSIC_DIR/Playlists, picked once so a title change or a
    # namesake playlist never moves or overwrites it
    m3u_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Songs found in the library at the last M3U refresh (written or not)
    available_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    created_by: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    last_synced_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # In playlist order. Deleted by the ORM: SQLite isn't enforcing foreign keys here.
    entries: Mapped[List["PlaylistEntry"]] = relationship(
        "PlaylistEntry",
        cascade="all, delete-orphan",
        order_by="PlaylistEntry.position",
    )


class PlaylistEntry(Base):
    """
    One song of a playlist, as YouTube Music lists it. Its video id is often
    not the id of the album track downloaded for it, hence the title, artist
    and album kept to find that track (services/playlists.resolve_entries).
    """
    __tablename__ = "playlist_entries"

    playlist_id: Mapped[str] = mapped_column(String(64), ForeignKey("playlists.id", ondelete="CASCADE"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    artist_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # main artist
    artist_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    album_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    album_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    duration: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


# Recommendations (see services/recommendations.py)

class RelatedArtist(Base):
    """
    One of an artist's similar artists ("Fans might also like" on YouTube
    Music), as of its last fetch. The similar artist usually isn't in the
    library, hence its name and thumbnail kept here.
    """
    __tablename__ = "related_artists"

    artist_id: Mapped[str] = mapped_column(String(64), ForeignKey("artists.id", ondelete="CASCADE"), primary_key=True)
    related_id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    thumbnail: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)  # 0 = most similar


class DismissedRecommendation(Base):
    """An artist someone marked "not interested": never recommended again, until restored."""
    __tablename__ = "dismissed_recommendations"

    artist_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # Kept to list it, as the artist usually isn't in the library
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    thumbnail: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    dismissed_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    dismissed_by: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )


# Charts

class ChartSubscription(Base):
    """
    Chart subscriptions - tracks which country charts to sync weekly.
    Auto-follows top N artists from the chart.
    """
    __tablename__ = "chart_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), unique=True, nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    top_n_artists: Mapped[int] = mapped_column(Integer, nullable=False, default=10)  # 1-40
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    created_by: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    last_synced_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<ChartSubscription country={self.country_code} top_n={self.top_n_artists} enabled={self.enabled}>"


# Authentication

class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("oidc_issuer", "oidc_subject"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # NOCASE: equality and the unique index are case-insensitive (ASCII), so
    # "Admin" and "admin" are the same account at the DB level
    username: Mapped[str] = mapped_column(String(64, collation="NOCASE"), unique=True, nullable=False, index=True)
    # None for single sign-on accounts (until given one by the recovery CLI)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Single sign-on identity: accounts are matched on these, never on names
    oidc_issuer: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    oidc_subject: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="member")  # administrator, member, visitor
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Set for the first admin and on password resets (temporary password);
    # the frontend sends the user to the change-password page until cleared
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    last_login_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Access and device tokens issued before this are rejected (set when the
    # password changes, see services/auth.change_password). Whole seconds,
    # like JWT "iat".
    tokens_valid_after: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def has_password(self) -> bool:
        return bool(self.password_hash)

    @property
    def is_oidc(self) -> bool:
        return bool(self.oidc_subject)

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
        """Not revoked and not expired"""
        return not self.revoked and now_utc() < ensure_timezone_aware(self.expires_at)

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
    type: Mapped[str] = mapped_column(String(32), nullable=False, default="string")  # string, int, bool, schedule (stored as JSON)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)
    updated_by: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "value": self.get_typed_value(),
            "type": self.type,
            "description": self.description,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "updated_by": self.updated_by,
        }

    def get_typed_value(self) -> Any:
        """The stored text as its setting type (None when unparseable)"""
        if self.value is None:
            return None
        if self.type == "int":
            try:
                return int(self.value)
            except ValueError:
                return None
        if self.type == "bool":
            return self.value.lower() in ("true", "1", "yes", "on")
        if self.type == "schedule":
            try:
                return json.loads(self.value)
            except ValueError:
                return None
        return self.value

    def set_value(self, value: Any) -> None:
        """Store value as text, according to the setting type"""
        if value is None:
            self.value = None
        elif self.type == "schedule":
            self.value = json.dumps(value)
        elif self.type == "bool":
            self.value = "true" if value else "false"
        else:
            self.value = str(value)

    def __repr__(self) -> str:
        return f"<Setting key={self.key!r} value={self.value!r}>"
