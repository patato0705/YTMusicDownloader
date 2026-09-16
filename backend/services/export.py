# backend/services/export.py
"""
Export / import of library manifests and admin backups.

Export builds a plain dict matching schemas.export.ExportDocument. Import
replays the document through the existing service functions (subscribe,
enqueue jobs, upsert rows, set settings) so it works the same regardless of
the database backend. A dry run walks the exact same code and rolls back
instead of committing, which is what keeps the preview honest.
"""
from __future__ import annotations
import logging
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from .. import config
from .. import settings as settings_module
from ..models import (
    Artist, Album, Track, ArtistSubscription, ChartSubscription, User, Setting, Job,
)
from ..schemas.export import (
    FORMAT_VERSION,
    ExportDocument,
    ImportResult,
    ImportWarning,
    LibraryImportResult,
    CatalogImportResult,
    UsersImportResult,
    SettingsImportResult,
)
from ..time_utils import now_utc
from ..jobs.jobqueue import enqueue_job
from . import subscriptions as subs_svc
from . import artists as artists_svc
from . import albums as albums_svc
from . import tracks as tracks_svc
from . import charts as charts_svc
from . import auth as auth_svc

logger = logging.getLogger("services.export")


# ============================================================================
# PATH HELPERS
# ============================================================================

def _music_root() -> Path:
    return Path(str(config.MUSIC_DIR)).resolve()


def relativize_path(value: Optional[str]) -> Optional[str]:
    """
    Turn an absolute path stored in the DB into a path relative to the music
    directory (posix separators). Anything outside the music directory is
    dropped: it can't be carried over to another instance anyway.
    """
    if not value:
        return None
    try:
        rel = Path(value).resolve().relative_to(_music_root())
    except (ValueError, OSError):
        return None
    return PurePosixPath(rel).as_posix()


def resolve_music_path(value: Optional[str]) -> Optional[Path]:
    """
    Turn a relative path from a document back into an absolute path under the
    music directory. Rejects absolute paths and anything escaping the root.
    Returns None when the value is unusable.
    """
    if not value:
        return None
    rel = PurePosixPath(value)
    if rel.is_absolute() or ".." in rel.parts:
        return None
    root = _music_root()
    try:
        full = (root / Path(*rel.parts)).resolve()
        full.relative_to(root)
    except (ValueError, OSError):
        return None
    return full


def _app_version() -> str:
    try:
        from ..ytm_service import __version__
        return str(__version__)
    except Exception:
        return "unknown"


# ============================================================================
# EXPORT
# ============================================================================

def _document_shell() -> Dict[str, Any]:
    return {
        "format_version": FORMAT_VERSION,
        "app_version": _app_version(),
        "exported_at": now_utc().isoformat(),
    }


def build_library_section(session: Session) -> Dict[str, Any]:
    """What this instance follows: artists, explicitly downloaded albums, charts."""
    artists = session.execute(
        select(Artist, ArtistSubscription)
        .join(ArtistSubscription, ArtistSubscription.artist_id == Artist.id)
        .where(ArtistSubscription.enabled == True)  # noqa: E712
        .order_by(Artist.name)
    ).all()

    # Albums of a full-mode artist are implied: sync_artist re-imports every
    # one of them. Only list albums downloaded on their own.
    full_artist_ids = {artist.id for artist, sub in artists if sub.mode == "full"}
    albums = [
        (album, artist)
        for album, artist in session.execute(
            select(Album, Artist)
            .outerjoin(Artist, Artist.id == Album.artist_id)
            .where(Album.mode == "download")
            .order_by(Album.title)
        ).all()
        if album.artist_id not in full_artist_ids
    ]

    charts = charts_svc.list_chart_subscriptions(session, include_disabled=True)

    return {
        "artists": [
            {"id": artist.id, "name": artist.name, "mode": sub.mode}
            for artist, sub in artists
        ],
        "albums": [
            {
                "id": album.id,
                "title": album.title,
                "artist_id": album.artist_id,
                "artist_name": artist.name if artist else None,
            }
            for album, artist in albums
        ],
        "charts": [
            {
                "country_code": sub.country_code,
                "top_n_artists": sub.top_n_artists,
                "enabled": bool(sub.enabled),
            }
            for sub in charts
        ],
    }


def build_catalog_section(session: Session) -> Dict[str, Any]:
    """
    Every artist, plus every download-mode album and its tracks, with paths
    relative to the music directory. Metadata-only albums are cache that
    sync_artist rebuilds, so they stay out of the file.
    """
    artists = session.execute(select(Artist).order_by(Artist.id)).scalars().all()
    albums = session.execute(
        select(Album).where(Album.mode == "download").order_by(Album.id)
    ).scalars().all()
    tracks = session.execute(
        select(Track)
        .join(Album, Album.id == Track.album_id)
        .where(Album.mode == "download")
        .order_by(Track.id)
    ).scalars().all()

    return {
        "artists": [
            {
                "id": a.id,
                "name": a.name,
                "image_local": relativize_path(a.image_local),
                "description": a.description,
            }
            for a in artists
        ],
        "albums": [
            {
                "id": al.id,
                "title": al.title,
                "type": al.type,
                "artist_id": al.artist_id,
                "playlist_id": al.playlist_id,
                "year": al.year,
                "image_local": relativize_path(al.image_local),
                "mode": al.mode,
                "download_status": al.download_status,
            }
            for al in albums
        ],
        "tracks": [
            {
                "id": t.id,
                "title": t.title,
                "duration": t.duration,
                "artists": t.artists,
                "album_id": t.album_id,
                "track_number": t.track_number,
                "lyrics": t.lyrics,
                "lyrics_local": relativize_path(t.lyrics_local),
                "file_path": relativize_path(t.file_path),
                "status": t.status,
                "artist_valid": bool(t.artist_valid),
            }
            for t in tracks
        ],
    }


def build_users_section(session: Session) -> List[Dict[str, Any]]:
    users = session.execute(select(User).order_by(User.id)).scalars().all()
    return [
        {
            "username": u.username,
            "email": u.email,
            "password_hash": u.password_hash,
            "role": u.role,
            "is_active": bool(u.is_active),
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


def build_settings_section(session: Session) -> List[Dict[str, Any]]:
    settings = session.execute(select(Setting).order_by(Setting.key)).scalars().all()
    return [
        {"key": s.key, "type": s.type, "value": s.get_typed_value()}
        for s in settings
    ]


def build_library_export(session: Session) -> Dict[str, Any]:
    doc = _document_shell()
    doc["library"] = build_library_section(session)
    return doc


def build_backup_export(
    session: Session,
    include_library: bool = True,
    include_charts: bool = True,
    include_catalog: bool = True,
    include_users: bool = True,
    include_settings: bool = True,
) -> Dict[str, Any]:
    doc = _document_shell()
    if include_library or include_charts:
        # Charts live inside the library section; either half can be left out
        library = build_library_section(session)
        if not include_library:
            library["artists"] = []
            library["albums"] = []
        if not include_charts:
            library["charts"] = []
        doc["library"] = library
    if include_catalog:
        doc["catalog"] = build_catalog_section(session)
    if include_users:
        doc["users"] = build_users_section(session)
    if include_settings:
        doc["settings"] = build_settings_section(session)
    return doc


# ============================================================================
# IMPORT
# ============================================================================

def _import_settings(session: Session, doc: ExportDocument, user_id: Optional[int], warnings: List[ImportWarning]) -> SettingsImportResult:
    result = SettingsImportResult()
    for item in doc.settings or []:
        # Only keys this build knows about, each through the same validation
        # the settings panel uses. Unknown keys are the compatibility story
        # between app versions.
        if item.key not in settings_module.DEFAULT_SETTINGS:
            result.ignored.append(item.key)
            continue
        try:
            settings_module.set_setting(session, item.key, item.value, user_id=user_id, commit=False)
            result.applied += 1
        except ValueError as e:
            result.ignored.append(item.key)
            warnings.append(ImportWarning(code="invalid_setting", detail=f"{item.key}: {e}"))
    if result.ignored:
        warnings.append(ImportWarning(code="settings_ignored", detail=", ".join(result.ignored)))
    return result


def _import_users(session: Session, doc: ExportDocument, warnings: List[ImportWarning]) -> UsersImportResult:
    result = UsersImportResult()
    for item in doc.users or []:
        # Never touch an existing account (that includes the admin running the
        # import): conflicts are reported, not resolved.
        if auth_svc.get_user_by_username(session, item.username) or auth_svc.get_user_by_email(session, item.email):
            result.skipped.append(item.username)
            continue
        session.add(User(
            username=item.username,
            email=item.email,
            password_hash=item.password_hash,
            role=item.role,
            is_active=item.is_active,
            created_at=now_utc(),
        ))
        session.flush()
        result.created += 1
    if result.skipped:
        warnings.append(ImportWarning(code="users_skipped", detail=", ".join(result.skipped)))
    return result


def _import_catalog(session: Session, doc: ExportDocument, user_id: Optional[int], warnings: List[ImportWarning]) -> CatalogImportResult:
    result = CatalogImportResult()
    catalog = doc.catalog
    assert catalog is not None

    for a in catalog.artists:
        image = resolve_music_path(a.image_local)
        artists_svc.upsert_artist(
            session,
            artist_id=a.id,
            name=a.name,
            image_local=str(image) if image and image.exists() else None,
            description=a.description,
        )
        result.artists += 1
    session.flush()

    # Only download-mode albums are restored as rows. Metadata-only albums
    # are cache: their covers live outside the music dir (so they never make
    # it into an export) and sync_artist rebuilds them, covers included.
    download_albums: Dict[str, Optional[str]] = {}
    albums_needing_import: set[str] = set()
    for al in catalog.albums:
        if al.mode != "download":
            continue
        image = resolve_music_path(al.image_local)
        cover_on_disk = bool(image and image.exists())
        obj = albums_svc.upsert_album(
            session,
            album_id=al.id,
            title=al.title,
            artist_id=al.artist_id,
            image_local=str(image) if cover_on_disk else None,
            year=al.year,
            album_type=al.type,
            playlist_id=al.playlist_id,
        )
        obj.mode = "download"
        obj.download_status = al.download_status
        download_albums[al.id] = al.artist_id
        result.albums += 1
        if not cover_on_disk and not (obj.image_local and Path(obj.image_local).exists()):
            albums_needing_import.add(al.id)
    session.flush()

    for t in catalog.tracks:
        if t.album_id not in download_albums:
            continue
        audio = resolve_music_path(t.file_path)
        on_disk = bool(audio and audio.exists())
        lrc = resolve_music_path(t.lyrics_local) if on_disk else None
        lrc_on_disk = bool(lrc and lrc.exists())

        obj = tracks_svc.upsert_track(
            session,
            track_id=t.id,
            title=t.title or "",
            track_number=t.track_number,
            duration_seconds=t.duration,
            artists_list=t.artists,
            album_id=t.album_id,
            status="done" if on_disk else "new",
            file_path=str(audio) if on_disk else None,
            artist_valid=t.artist_valid,
            lyrics=t.lyrics if lrc_on_disk else None,
            lyrics_local=str(lrc) if lrc_on_disk else None,
        )
        result.tracks += 1

        if on_disk:
            result.tracks_on_disk += 1
            continue

        # upsert_track leaves file_path/lyrics untouched when passed None, so a
        # row already present on this instance keeps its own file if it has one.
        if obj.file_path and Path(obj.file_path).exists():
            obj.status = "done"
            result.tracks_on_disk += 1
            continue

        obj.file_path = None
        obj.lyrics = None
        obj.lyrics_local = None
        obj.status = "new"
        result.tracks_to_download += 1
        albums_needing_import.add(t.album_id)
    session.flush()

    # One import_album per album rather than a download_track per track: it
    # re-fetches the cover (download_track only reuses whatever the album row
    # points at), writes album.nfo, keeps tracks that already have a file and
    # queues downloads for the rest.
    pending_imports = {
        str((job.payload or {}).get("browse_id"))
        for job in session.execute(
            select(Job).where(Job.type == "import_album", Job.status.in_(("queued", "reserved")))
        ).scalars()
    }
    for album_id in sorted(albums_needing_import):
        if album_id in pending_imports:
            continue
        enqueue_job(
            session,
            job_type="import_album",
            payload={"browse_id": album_id, "artist_id": download_albums[album_id]},
            priority=20,
            user_id=user_id,
            commit=False,
        )
        result.albums_to_import += 1
        subs_svc.check_and_update_album_download_status(session, album_id)

    return result


def _queue_missing_album_imports(session: Session, artist_id: str, user_id: Optional[int]) -> int:
    """After a light->full upgrade, import albums that have no tracks yet (mirrors follow_artist)."""
    album_ids = session.execute(
        select(Album.id).where(Album.artist_id == artist_id, Album.mode == "download")
    ).scalars().all()
    queued = 0
    for aid in album_ids:
        track_count = session.query(func.count(Track.id)).filter(Track.album_id == aid).scalar()
        if not track_count:
            enqueue_job(
                session,
                job_type="import_album",
                payload={"browse_id": aid, "artist_id": artist_id},
                priority=20,
                user_id=user_id,
                commit=False,
            )
            queued += 1
    return queued


def _import_library(session: Session, doc: ExportDocument, user_id: Optional[int], warnings: List[ImportWarning]) -> LibraryImportResult:
    result = LibraryImportResult()
    library = doc.library
    assert library is not None

    # --- Artists: replay follow ---
    full_artists: set[str] = set()
    for item in library.artists:
        existing = subs_svc.get_artist_subscription(session, item.id)
        old_mode = existing.mode if existing else None
        if old_mode == "full" or old_mode == item.mode:
            if old_mode == "full":
                full_artists.add(item.id)
            result.artists_existing += 1
            continue

        artists_svc.upsert_artist(session, artist_id=item.id, name=item.name)
        subs_svc.subscribe_to_artist(session, artist_id=item.id, mode=item.mode)
        if item.mode == "full":
            full_artists.add(item.id)
            if old_mode == "light":
                subs_svc.upgrade_all_albums_to_download(session, item.id)
                session.flush()
                _queue_missing_album_imports(session, item.id, user_id)
        enqueue_job(
            session,
            job_type="sync_artist",
            payload={"artist_id": item.id},
            priority=30,
            user_id=user_id,
            commit=False,
        )
        result.artists_followed += 1
    session.flush()

    # --- Albums: replay download ---
    for item in library.albums:
        album = session.get(Album, item.id)
        if album and album.mode == "download":
            result.albums_existing += 1
            continue
        if item.artist_id and item.artist_id in full_artists:
            # sync_artist imports every album of a full-mode artist
            result.albums_covered_by_artist += 1
            continue

        if item.artist_id:
            artists_svc.upsert_artist(session, artist_id=item.artist_id, name=item.artist_name)
            if not subs_svc.get_artist_subscription(session, item.artist_id):
                subs_svc.subscribe_to_artist(session, artist_id=item.artist_id, mode="light")
                enqueue_job(
                    session,
                    job_type="sync_artist",
                    payload={"artist_id": item.artist_id},
                    priority=30,
                    user_id=user_id,
                    commit=False,
                )

        album = albums_svc.upsert_album(session, album_id=item.id, title=item.title, artist_id=item.artist_id)
        album.mode = "download"
        enqueue_job(
            session,
            job_type="import_album",
            payload={"browse_id": item.id, "artist_id": item.artist_id},
            priority=20,
            user_id=user_id,
            commit=False,
        )
        result.albums_queued += 1
    session.flush()

    # --- Charts ---
    if library.charts:
        charts_enabled = bool(settings_module.get_setting(session, "features.charts_enabled", True))
        if not charts_enabled:
            result.charts_skipped = len(library.charts)
            warnings.append(ImportWarning(code="charts_disabled"))
        else:
            for item in library.charts:
                code = item.country_code.upper()
                if charts_svc.get_chart_subscription(session, code):
                    result.charts_existing += 1
                    continue
                try:
                    sub = charts_svc.create_chart_subscription(
                        session, country_code=code, top_n_artists=item.top_n_artists, created_by=user_id,
                    )
                except ValueError as e:
                    result.charts_skipped += 1
                    warnings.append(ImportWarning(code="invalid_chart", detail=f"{code}: {e}"))
                    continue
                if item.enabled:
                    charts_svc.enqueue_chart_sync(session, code, user_id=user_id)
                else:
                    sub.enabled = False
                result.charts_created += 1

    return result


def run_import(
    session: Session,
    doc: ExportDocument,
    user_id: Optional[int],
    dry_run: bool,
) -> ImportResult:
    """
    Apply a document to this instance. Section order matters: settings first
    (charts flag gates the chart import), then users, then catalog rows so the
    library replay finds them, then library.

    With dry_run the whole thing is rolled back and the summary reports what
    would have happened.
    """
    result = ImportResult(dry_run=dry_run, format_version=doc.format_version)
    warnings = result.warnings

    try:
        if doc.settings is not None:
            result.settings = _import_settings(session, doc, user_id, warnings)
        if doc.users is not None:
            result.users = _import_users(session, doc, warnings)
        if doc.catalog is not None:
            result.catalog = _import_catalog(session, doc, user_id, warnings)
        if doc.library is not None:
            result.library = _import_library(session, doc, user_id, warnings)

        if dry_run:
            session.rollback()
            return result

        session.commit()
    except Exception:
        session.rollback()
        raise

    if result.settings and result.settings.applied:
        # Same as the settings endpoint: a language change needs a fresh client
        try:
            from ..ytm_service.client import reset_client
            reset_client()
        except Exception:
            logger.exception("Failed to reset YTMusic client after settings import")

    logger.info("Import applied: %s", result.model_dump(exclude={"warnings"}))
    return result
