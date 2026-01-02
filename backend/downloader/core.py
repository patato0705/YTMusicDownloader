# backend/downloader/core.py
from __future__ import annotations
import logging
import os
import time
import shutil
from typing import Any, Dict, List, Optional, Union, cast
from pathlib import Path

from yt_dlp import YoutubeDL

from ..config import DOWNLOAD_DIR, COVERS_DIR, MUSIC_DIR, LYRICS_DIR, YDL_FORMAT, YDL_PREFERRED_CODEC, YDL_COOKIEFILE

# relative package imports (downloader.cover, downloader.embed expected)
from . import cover as cover_mod  # type: ignore
from . import embed as embed_mod  # type: ignore

# optional lyrics helper (may not exist in new layout)
try:
    from ..lyrics import fetch_lyrics  # type: ignore
except Exception:
    fetch_lyrics = None  # type: ignore

logger = logging.getLogger("downloader.core")
if not logging.getLogger().handlers:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

def _cleanup_partial_files(directory: Union[str, Path]) -> None:
    d = Path(str(directory))
    if not d.exists() or not d.is_dir():
        return
    for f in d.iterdir():
        try:
            if f.name.endswith(".part"):
                f.unlink(missing_ok=True)
        except Exception:
            logger.debug("Ignoring leftover partial file %s", f, exc_info=True)


def _safe_name(s: Optional[str]) -> str:
    if not s:
        return "Unknown"
    return "".join(c for c in s if c.isalnum() or c in " .-_()").strip() or "Unknown"


def _find_downloaded_file(download_dir: Union[str, Path], prefix: str = "song.") -> Optional[Path]:
    try:
        d = Path(str(download_dir))
        for f in d.iterdir():
            if f.name.startswith(prefix) and not f.name.endswith(".part"):
                return f
    except Exception:
        logger.exception("Failed scanning download dir %s", download_dir)
    return None


# --- main public function ---
def download_track_by_videoid(
    video_id: str,
    artist_name: Optional[str] = None,
    album_name: Optional[str] = None,
    track_title: Optional[str] = None,
    track_number: Optional[int] = None,
    year: Optional[Union[str, int]] = None,
    cover_path_override: Optional[Union[str, Path]] = None,
    skip_metadata: bool = True,  # NEW: Skip metadata extraction
) -> tuple[str, Optional[str]]:
    """
    Downloads track (yt-dlp), puts final file under MUSIC_DIR/{artist}/{album}/
    and returns (file_path, cover_path).

    Args:
        video_id: YouTube video ID
        artist_name: Artist name for metadata
        album_name: Album name for metadata
        track_title: Track title for metadata
        track_number: Track number for metadata
        year: Release year for metadata
        cover_path_override: Path to already existing cover (used if valid)
        skip_metadata: If True, skip metadata extraction (faster, fewer requests)

    Returns:
        tuple: (final_track_path, final_cover_path or None)
    """
    _cleanup_partial_files(DOWNLOAD_DIR)

    url = f"https://www.youtube.com/watch?v={video_id}"
    outtmpl = str(Path(str(DOWNLOAD_DIR)) / "song.%(ext)s")
    ydl_opts: Dict[str, Any] = {
        "format": YDL_FORMAT or "bestaudio/best",
        'cookiefile': YDL_COOKIEFILE,
        "outtmpl": outtmpl,
        "quiet": False,
        "no_warnings": True,
        "noplaylist": True,
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": YDL_PREFERRED_CODEC or "m4a"}
        ],
        "retries": 3,
        "continuedl": True,
    }

    info_dict: Dict[str, Any] = {}
    duration_sec: Optional[int] = None

    # Download with or without metadata extraction
    try:
        with YoutubeDL(ydl_opts) as ydl:  # type: ignore
            if skip_metadata:
                # FAST MODE: Download directly without metadata extraction
                logger.info(f"Downloading {video_id} (no metadata)")
                ydl.download([url])
            else:
                # SLOW MODE: Extract metadata first (original behavior)
                logger.info(f"Downloading {video_id} (with metadata)")
                tmp_info = ydl.extract_info(url, download=False)
                if isinstance(tmp_info, dict):
                    info_dict = cast(Dict[str, Any], tmp_info)
                    dval = info_dict.get("duration") or info_dict.get("duration_seconds") or info_dict.get("lengthSeconds")
                    try:
                        duration_sec = int(dval) if dval is not None else None
                    except Exception:
                        duration_sec = None
                ydl.download([url])
    except Exception:
        logger.exception("yt-dlp failed for %s", url)
        raise

    downloaded_file = _find_downloaded_file(DOWNLOAD_DIR)
    if not downloaded_file:
        raise FileNotFoundError("Downloaded file not found in downloads directory")

    # metadata fallback - use provided metadata since we skipped extraction
    final_title = track_title or f"track_{video_id}"
    final_artist = artist_name or "Unknown"
    final_album = album_name or "Unknown Album"
    artists_list: List[str] = [final_artist] if final_artist else []

    # Cover handling - use provided cover since we skipped thumbnail extraction
    cover_path_file: Optional[Path] = None
    if cover_path_override:
        try:
            cand = Path(str(cover_path_override))
            if cand.is_file() and os.access(str(cand), os.R_OK):
                cover_path_file = cand
        except Exception:
            cover_path_file = None

    # If no cover provided and we didn't skip metadata, try to get thumbnail
    if not cover_path_file and not skip_metadata and info_dict:
        thumb_candidates: List[Union[str, Dict[str, Any]]] = []
        t = info_dict.get("thumbnails")
        if isinstance(t, list):
            thumb_candidates = [x for x in t if x is not None]
        elif isinstance(t, dict):
            inner = t.get("thumbnails")
            if isinstance(inner, list):
                thumb_candidates = [x for x in inner if x is not None]
        else:
            th = info_dict.get("thumbnail")
            if isinstance(th, list):
                thumb_candidates = [x for x in th if x is not None]
            elif isinstance(th, (str, dict)):
                thumb_candidates = [th]
        
        thumb_url: Optional[str] = None
        try:
            if hasattr(cover_mod, "select_best_thumbnail_url"):
                thumb_url = cover_mod.select_best_thumbnail_url(thumb_candidates)
            else:
                for item in reversed(thumb_candidates):
                    if isinstance(item, dict) and item.get("url"):
                        thumb_url = item.get("url")
                        break
                    if isinstance(item, str):
                        thumb_url = item
                        break
        except Exception:
            logger.debug("Thumbnail selection failed", exc_info=True)

        if thumb_url:
            try:
                dest_cover = Path(str(COVERS_DIR)) / f"{video_id}.jpg"
                if hasattr(cover_mod, "save_cover_from_url"):
                    got = cover_mod.save_cover_from_url(thumb_url, dest_cover)
                elif hasattr(cover_mod, "save_and_convert_cover"):
                    got = cover_mod.save_and_convert_cover(thumb_url, dest_cover)
                else:
                    got = None
                if isinstance(got, Path):
                    cover_path_file = got
            except Exception:
                logger.exception("Failed saving cover for %s", video_id)

    # prepare destination path
    safe_artist = _safe_name(final_artist)
    safe_album = _safe_name(final_album)
    safe_title = _safe_name(final_title)
    dest_dir = Path(str(MUSIC_DIR)) / safe_artist / safe_album
    dest_dir.mkdir(parents=True, exist_ok=True)

    try:
        if track_number and int(track_number) > 0:
            filename = f"{int(track_number):02d} - {safe_title}"
        else:
            filename = safe_title
    except Exception:
        filename = safe_title

    ext = downloaded_file.suffix.lstrip(".") if downloaded_file else (YDL_PREFERRED_CODEC or "m4a")
    dest_path = dest_dir / f"{filename}.{ext}"
    if dest_path.exists():
        dest_path = dest_dir / f"{filename}_{int(time.time())}.{ext}"

    # move/copy downloaded file
    try:
        moved = shutil.move(str(downloaded_file), str(dest_path))
        dest_path = Path(str(moved))
    except Exception:
        logger.exception("Move failed, trying copy fallback")
        shutil.copyfile(str(downloaded_file), str(dest_path))
        try:
            downloaded_file.unlink(missing_ok=True)
        except Exception:
            pass

    # lyrics - skip if we don't have duration (which we won't in skip_metadata mode)
    lyrics_lrc_path: Optional[Path] = None
    if not skip_metadata:  # Only try lyrics if we have metadata
        try:
            if fetch_lyrics and artists_list and final_title and final_album and isinstance(duration_sec, int) and duration_sec > 0:
                temp_lrc = fetch_lyrics(artists_list, final_title, final_album, duration_sec)
                if temp_lrc:
                    dest_lyrics = dest_dir / Path(str(temp_lrc)).name
                    try:
                        moved = None
                        if hasattr(cover_mod, "move_if_exists"):
                            moved = cover_mod.move_if_exists(temp_lrc, dest_lyrics)
                        else:
                            moved = shutil.move(str(temp_lrc), str(dest_lyrics))
                            moved = Path(str(moved))
                        if isinstance(moved, Path):
                            lyrics_lrc_path = moved
                    except Exception:
                        logger.exception("Failed to move lyrics file")
        except Exception:
            logger.exception("Lyrics fetch failed")

    # move cover into album folder as cover.jpg if present
    final_cover_path: Optional[str] = None
    try:
        if cover_path_file and cover_path_file.exists():
            album_cover = dest_dir / "cover.jpg"
            try:
                moved_cover = None
                if hasattr(cover_mod, "move_cover_if_exists"):
                    moved_cover = cover_mod.move_cover_if_exists(cover_path_file, album_cover)
                elif hasattr(cover_mod, "move_if_exists"):
                    moved_cover = cover_mod.move_if_exists(cover_path_file, album_cover)
                else:
                    moved_cover = shutil.move(str(cover_path_file), str(album_cover))
                    moved_cover = Path(str(moved_cover))
                if isinstance(moved_cover, Path) and moved_cover.exists():
                    cover_path_file = moved_cover
                    final_cover_path = str(moved_cover)
                    logger.info(f"Moved cover to album folder: {final_cover_path}")
            except Exception:
                logger.exception("Failed to move cover to album folder")
    except Exception:
        logger.exception("Cover placement error")

    # embed tags
    try:
        if hasattr(embed_mod, "embed_tags"):
            embed_mod.embed_tags(
                str(dest_path),
                title=str(final_title),
                album=str(final_album),
                artists=artists_list,
                album_artist=(artists_list[0] if artists_list else final_artist),
                lyrics_path=str(lyrics_lrc_path) if lyrics_lrc_path else None,
                cover_path=str(cover_path_file) if cover_path_file else None,
                track_number=(int(track_number) if track_number else None),
                year=str(year) if year else None,
            )
        else:
            logger.debug("embed_mod.embed_tags not available; skipping embedding")
    except Exception:
        logger.exception("Failed embedding tags for %s", dest_path)

    # set permissions
    try:
        dest_path.chmod(0o644)
        if cover_path_file and cover_path_file.exists():
            cover_path_file.chmod(0o644)
        if lyrics_lrc_path and lyrics_lrc_path.exists():
            lyrics_lrc_path.chmod(0o644)
    except Exception:
        pass

    return str(dest_path), final_cover_path