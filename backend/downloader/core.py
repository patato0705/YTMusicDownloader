# backend/downloader/core.py
from __future__ import annotations
import logging
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from yt_dlp import YoutubeDL

from ..config import DOWNLOAD_DIR, YDL_FORMAT, YDL_PREFERRED_CODEC
from . import cover as cover_mod
from . import embed as embed_mod

logger = logging.getLogger("downloader.core")


def safe_name(s: Optional[str]) -> str:
    """
    Sanitize a string (artist/album/track name) for use as a filesystem
    path component. Security-relevant: this is what keeps metadata-derived
    strings from injecting path traversal or special characters into
    download destination paths. Keep it in one place (also used by
    services/folders.py and services/playlists.py) rather than drifting copies.
    """
    name = "".join(c for c in s or "" if c.isalnum() or c in " .-_()").strip()
    # Nothing left, or only dots: "." and ".." would point at the folder
    # itself or its parent
    return name if name.strip(".") else "Unknown"


def _job_download_dir(video_id: str) -> Path:
    """
    Scratch directory for one download. Each download gets its own so that
    several download workers (deploy/supervisord.conf) can run at once
    without clobbering each other's song.* / .part files. Wiped before use
    so a retry never picks up a stale file from a previous attempt.
    """
    d = DOWNLOAD_DIR / safe_name(video_id)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _find_downloaded_file(download_dir: Path) -> Optional[Path]:
    for f in download_dir.iterdir():
        if f.name.startswith("song.") and not f.name.endswith(".part"):
            return f
    return None


def download_track_by_videoid(
    video_id: str,
    cookiefile: Union[str, Path],
    dest_dir: Path,
    artist_name: Optional[str] = None,
    album_name: Optional[str] = None,
    track_title: Optional[str] = None,
    track_number: Optional[int] = None,
    year: Optional[str] = None,
    cover_path: Optional[Union[str, Path]] = None,
    genres: Optional[List[str]] = None,
) -> Tuple[str, Optional[str]]:
    """
    Download a track with yt-dlp into dest_dir, tagged.

    Args:
        cookiefile: yt-dlp cookie jar to read from and write back to.
            Concurrent download workers each pass their own (see jobs.tasks)
        dest_dir: the album's folder (services/folders.py)
        cover_path: the album's cover (Album.image_local). The first track
            of an album moves it from COVERS_DIR into the album folder as
            cover.jpg; later tracks find it there.
        genres: The album's genres, for the genre tag

    Returns:
        (file path, the cover's new path when this call moved it, else None)
    """
    job_dir = _job_download_dir(video_id)
    try:
        with YoutubeDL(_ydl_options(job_dir, cookiefile)) as ydl:
            logger.info("Downloading %s", video_id)
            ydl.download([f"https://www.youtube.com/watch?v={video_id}"])

        downloaded = _find_downloaded_file(job_dir)
        if not downloaded:
            raise FileNotFoundError("Downloaded file not found in downloads directory")

        dest_dir.mkdir(parents=True, exist_ok=True)
        title = safe_name(track_title or f"track_{video_id}")
        filename = f"{track_number:02d} - {title}" if track_number and track_number > 0 else title
        dest_path = dest_dir / f"{filename}{downloaded.suffix}"
        if dest_path.exists():
            dest_path = dest_dir / f"{filename}_{int(time.time())}{downloaded.suffix}"
        dest_path = cover_mod.move_file(downloaded, dest_path)
        if dest_path is None:
            raise OSError(f"Failed to move the download into {dest_dir}")
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)

    # The album's cover goes into its folder once, with its first track
    album_cover = dest_dir / "cover.jpg"
    cover = Path(cover_path) if cover_path else None
    moved_cover: Optional[str] = None
    if cover and cover != album_cover and cover.is_file():
        moved = cover_mod.move_file(cover, album_cover)
        if moved:
            moved_cover = str(moved)
            logger.info("Moved cover to album folder: %s", moved)
    # Another download of the album may have moved it a moment ago
    if not album_cover.is_file():
        album_cover = None

    embed_mod.embed_tags(
        dest_path,
        title=track_title or f"track_{video_id}",
        album=album_name or "Unknown Album",
        artist=artist_name or "Unknown",
        cover_path=album_cover,
        track_number=track_number,
        year=year,
        genres=genres,
    )

    try:
        dest_path.chmod(0o644)
        if album_cover:
            album_cover.chmod(0o644)
    except OSError:
        pass

    return str(dest_path), moved_cover


def _ydl_options(job_dir: Path, cookiefile: Union[str, Path]) -> Dict[str, Any]:
    return {
        "format": YDL_FORMAT,
        "cookiefile": str(cookiefile),
        "outtmpl": str(job_dir / "song.%(ext)s"),
        # Route yt-dlp's own messages through logging so they reach the log
        # file, not just stdout. Its progress lines arrive at DEBUG (i.e.
        # dropped at INFO); its "ERROR: [youtube] ..." lines at ERROR.
        "logger": logging.getLogger("yt_dlp"),
        "quiet": False,
        "no_warnings": True,
        "noplaylist": True,
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": YDL_PREFERRED_CODEC}
        ],
        "retries": 3,
        "continuedl": True,
    }
