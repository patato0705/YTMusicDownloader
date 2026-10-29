# backend/schemas/export.py
"""
Pydantic schemas for the export/import file format.

One document format with optional sections. A "library" export carries only
the `library` section (what you follow); an admin "backup" adds any of
`catalog`, `users` and `settings`. The importer handles whichever sections
are present.

Every reference is a natural key (YTMusic ID, country code, username,
setting key) so a document is portable between instances and database
backends. File paths are relative to the music directory.
"""
from __future__ import annotations
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, computed_field, model_validator

from ..text_utils import VIDEO_ID_PATTERN
from .auth import Username

FORMAT_VERSION = 1

# Caps on list sizes so a malicious document can't exhaust memory. Well above
# anything a real library produces.
MAX_ARTISTS = 50_000
MAX_ALBUMS = 200_000
MAX_TRACKS = 2_000_000
MAX_USERS = 10_000
MAX_SETTINGS = 1_000
MAX_CHARTS = 300
MAX_PLAYLISTS = 1_000
MAX_PLAYLIST_ENTRIES = 50_000


# ============================================================================
# LIBRARY SECTION - what you follow
# ============================================================================

class LibraryArtist(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    name: Optional[str] = Field(None, max_length=255)
    mode: Literal["light", "full"] = "full"


class LibraryAlbum(BaseModel):
    """An album explicitly in download mode."""
    id: str = Field(..., min_length=1, max_length=64)
    title: Optional[str] = Field(None, max_length=255)
    artist_id: Optional[str] = Field(None, max_length=64)
    artist_name: Optional[str] = Field(None, max_length=255)


class LibraryChart(BaseModel):
    country_code: str = Field(..., min_length=2, max_length=2)
    top_n_artists: int = Field(10, ge=1, le=40)
    enabled: bool = True


class LibraryPlaylistEntry(BaseModel):
    video_id: Optional[str] = Field(None, max_length=64)
    title: str = Field(..., min_length=1, max_length=1024)
    artist_id: Optional[str] = Field(None, max_length=64)
    artist_name: Optional[str] = Field(None, max_length=255)
    album_id: Optional[str] = Field(None, max_length=64)
    album_title: Optional[str] = Field(None, max_length=255)
    duration: Optional[int] = Field(None, ge=0)


class LibraryPlaylist(BaseModel):
    """A playlist added to the library, with its songs (a one-time playlist is never fetched again)."""
    id: str = Field(..., min_length=1, max_length=64)
    title: str = Field(..., min_length=1, max_length=255)
    mode: Literal["albums", "artists"] = "albums"
    followed: bool = True
    m3u: bool = False
    # Its file in MUSIC_DIR/Playlists, reused on restore (with the data
    # folder copied over, the file is already there)
    m3u_name: Optional[str] = Field(None, max_length=255, pattern=r"^[^/\\]+\.m3u8$")
    entries: List[LibraryPlaylistEntry] = Field(default_factory=list, max_length=MAX_PLAYLIST_ENTRIES)


class LibrarySection(BaseModel):
    artists: List[LibraryArtist] = Field(default_factory=list, max_length=MAX_ARTISTS)
    albums: List[LibraryAlbum] = Field(default_factory=list, max_length=MAX_ALBUMS)
    charts: List[LibraryChart] = Field(default_factory=list, max_length=MAX_CHARTS)
    playlists: List[LibraryPlaylist] = Field(default_factory=list, max_length=MAX_PLAYLISTS)


# ============================================================================
# CATALOG SECTION - full database state (admin backup)
# ============================================================================

class CatalogArtist(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    name: Optional[str] = Field(None, max_length=255)
    folder: Optional[str] = Field(None, max_length=255)
    image_local: Optional[str] = Field(None, max_length=1024)
    banner_local: Optional[str] = Field(None, max_length=1024)
    description: Optional[str] = None


class CatalogAlbum(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    title: Optional[str] = Field(None, max_length=255)
    folder: Optional[str] = Field(None, max_length=255)
    type: Optional[str] = Field(None, max_length=32)
    artist_id: Optional[str] = Field(None, max_length=64)
    playlist_id: Optional[str] = Field(None, max_length=255)
    year: Optional[str] = Field(None, max_length=16)
    image_local: Optional[str] = Field(None, max_length=2048)
    mode: Literal["metadata", "download"] = "metadata"
    download_status: Optional[str] = Field(None, max_length=32)


class CatalogTrack(BaseModel):
    # A YouTube video id: what tracks are downloaded by
    id: str = Field(..., pattern=VIDEO_ID_PATTERN)
    title: Optional[str] = Field(None, max_length=1024)
    duration: Optional[int] = Field(None, ge=0)
    artists: Optional[List[Dict[str, Optional[str]]]] = None
    album_id: Optional[str] = Field(None, max_length=64)
    track_number: Optional[int] = Field(None, ge=0)
    lyrics: Optional[str] = Field(None, max_length=16)
    lyrics_local: Optional[str] = Field(None, max_length=1024)
    file_path: Optional[str] = Field(None, max_length=2048)
    status: str = Field("available", max_length=64)
    artist_valid: bool = True


class CatalogSection(BaseModel):
    artists: List[CatalogArtist] = Field(default_factory=list, max_length=MAX_ARTISTS)
    albums: List[CatalogAlbum] = Field(default_factory=list, max_length=MAX_ALBUMS)
    tracks: List[CatalogTrack] = Field(default_factory=list, max_length=MAX_TRACKS)


# ============================================================================
# USERS / SETTINGS SECTIONS (admin backup)
# ============================================================================

class DismissedArtist(BaseModel):
    """An artist a user marked "not interested" in recommendations."""
    id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=255)
    thumbnail: Optional[str] = Field(None, max_length=1024)


class ExportedUser(BaseModel):
    username: Username
    # bcrypt hashes are self-contained (salt embedded), so they move between
    # instances as-is. Anything else can't be verified by this app.
    password_hash: Optional[str] = Field(None, pattern=r"^\$2[aby]\$\d{2}\$.{53}$")
    # Single sign-on identity (same provider expected on the new instance)
    oidc_issuer: Optional[str] = Field(None, min_length=1, max_length=512)
    oidc_subject: Optional[str] = Field(None, min_length=1, max_length=255)
    role: Literal["administrator", "member", "visitor"] = "visitor"
    is_active: bool = True
    must_change_password: bool = False
    created_at: Optional[str] = None
    # What their recommendations come from, and leave out
    liked_artists: List[str] = Field(default_factory=list, max_length=MAX_ARTISTS)
    dismissed_recommendations: List[DismissedArtist] = Field(default_factory=list, max_length=MAX_ARTISTS)

    @model_validator(mode="after")
    def _can_sign_in(self) -> "ExportedUser":
        if bool(self.oidc_issuer) != bool(self.oidc_subject):
            raise ValueError("oidc_issuer and oidc_subject go together")
        if not self.password_hash and not self.oidc_subject:
            raise ValueError("a user needs a password_hash or a single sign-on identity")
        return self


class ExportedSetting(BaseModel):
    # Its type is this build's declaration of the key (settings.py)
    key: str = Field(..., min_length=1, max_length=128)
    value: Any = None


# ============================================================================
# DOCUMENT
# ============================================================================

class ExportDocument(BaseModel):
    format_version: int = Field(..., ge=1, le=FORMAT_VERSION)
    app_version: Optional[str] = None
    exported_at: Optional[str] = None
    library: Optional[LibrarySection] = None
    catalog: Optional[CatalogSection] = None
    users: Optional[List[ExportedUser]] = Field(None, max_length=MAX_USERS)
    settings: Optional[List[ExportedSetting]] = Field(None, max_length=MAX_SETTINGS)


# ============================================================================
# IMPORT RESULT
# ============================================================================

class ImportWarning(BaseModel):
    """Machine-readable so the frontend can translate it."""
    code: str
    detail: Optional[str] = None


class LibraryImportResult(BaseModel):
    artists_followed: int = 0
    artists_existing: int = 0
    albums_queued: int = 0
    albums_existing: int = 0
    # Albums whose artist is followed in full mode: sync_artist picks them up
    albums_covered_by_artist: int = 0
    charts_created: int = 0
    charts_existing: int = 0
    charts_skipped: int = 0
    playlists_added: int = 0
    playlists_existing: int = 0


class CatalogImportResult(BaseModel):
    artists: int = 0
    albums: int = 0
    tracks: int = 0
    tracks_on_disk: int = 0
    tracks_to_download: int = 0
    # Albums re-fetched from YTMusic (missing tracks or cover)
    albums_to_import: int = 0


class CreatedUser(BaseModel):
    """An account the import creates, listed so the preview shows who gets in, and as what."""
    username: str
    role: str
    single_sign_on: bool


class UsersImportResult(BaseModel):
    created_users: List[CreatedUser] = Field(default_factory=list)
    skipped: List[str] = Field(default_factory=list)
    # Added to the accounts, created or already there
    likes: int = 0
    # Liked artists not in the library once the import is done
    likes_skipped: int = 0
    dismissed: int = 0

    @computed_field
    @property
    def created(self) -> int:
        return len(self.created_users)


class SettingsImportResult(BaseModel):
    applied: int = 0
    ignored: List[str] = Field(default_factory=list)


class ImportResult(BaseModel):
    dry_run: bool
    format_version: int
    library: Optional[LibraryImportResult] = None
    catalog: Optional[CatalogImportResult] = None
    users: Optional[UsersImportResult] = None
    settings: Optional[SettingsImportResult] = None
    warnings: List[ImportWarning] = Field(default_factory=list)
