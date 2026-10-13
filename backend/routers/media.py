# backend/routers/media.py
"""
Media endpoints for serving and caching thumbnails from external sources.

Endpoints:
- GET /api/media/images/{full_path:path} - Serve images from /config/covers or /data directories.
- GET /api/media/thumbnail - Proxy and cache thumbnail images from external sources.

Expired cache files are never served (see _is_cache_valid); deleting them
is the scheduler's job (Scheduler.cleanup_thumbnail_cache). The TTL alone
doesn't bound the folder, since every distinct URL (e.g. each =w..-h.. size
suffix of the same Google image) is its own file, so writes also enforce
THUMBNAIL_CACHE_MAX_BYTES by deleting the oldest files (see _trim_disk_cache).
"""
from __future__ import annotations
import hashlib
import logging
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import Response, FileResponse

from ..config import (
    THUMBNAIL_CACHE_DIR,
    THUMBNAIL_CACHE_TTL,
    THUMBNAIL_CACHE_MAX_BYTES,
    THUMBNAIL_MAX_IMAGE_BYTES,
    MUSIC_DIR,
    COVERS_DIR,
)
from ..dependencies import require_auth_flexible
from ..models import User

logger = logging.getLogger("routers.media")

router = APIRouter(prefix="/api/media", tags=["Media"])

# Running estimate of the disk cache's total size, so a write only rescans
# the folder once the cap looks exceeded. None until the first write scans
# it. It can only overestimate (the scheduler process deleting expired files,
# a write replacing an expired file of the same name), and an overestimate
# just triggers a rescan that corrects it.
_disk_cache_bytes: int | None = None

# A trim deletes down to this fraction of the cap, so the next few writes
# don't each trigger a rescan.
_TRIM_TARGET_RATIO = 0.9

# Hosts this proxy will actually fetch from. Without this, /thumbnail is a
# server-side fetch of any http(s) URL an attacker supplies -- an SSRF that
# could reach internal services or a cloud metadata endpoint (e.g.
# 169.254.169.254) from inside the container/host network. These are the
# only hosts the frontend ever actually asks for (see
# frontend/src/api/media.ts's getImageUrl).
_ALLOWED_THUMBNAIL_HOSTS = ("googleusercontent.com", "ytimg.com", "ggpht.com")


def _is_allowed_thumbnail_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    return any(host == domain or host.endswith("." + domain) for domain in _ALLOWED_THUMBNAIL_HOSTS)


async def _check_redirect_target(request: httpx.Request) -> None:
    """httpx request hook, run for every hop of a redirect chain. Checking
    only the URL the client asked for isn't enough: an open redirect on any
    allowed host would otherwise hand the fetch, and its response, to an
    arbitrary internal address."""
    if not _is_allowed_thumbnail_url(str(request.url)):
        logger.warning("Thumbnail fetch redirected to a disallowed URL: %s", str(request.url)[:80])
        raise HTTPException(status_code=502, detail="Thumbnail redirected to a disallowed host")


def _get_cache_path(url: str) -> Path:
    """Generate cache file path from URL hash."""
    url_hash = hashlib.sha256(url.encode()).hexdigest()
    return THUMBNAIL_CACHE_DIR / f"{url_hash}.jpg"


def _is_cache_valid(cache_path: Path) -> bool:
    """Check if cached file exists and hasn't expired."""
    if not cache_path.exists():
        return False
    file_age = time.time() - cache_path.stat().st_mtime
    return file_age < THUMBNAIL_CACHE_TTL


def _image_type(content: bytes) -> str:
    """The media type of image bytes (the cache keeps no headers)."""
    if content.startswith(b"\x89PNG"):
        return "image/png"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def _image_response(content: bytes, cache_status: str) -> Response:
    return Response(
        content=content,
        media_type=_image_type(content),
        headers={"Cache-Control": "private, max-age=604800", "X-Cache-Status": cache_status},
    )


def _trim_disk_cache() -> None:
    """Rescan the disk cache and, if it's over THUMBNAIL_CACHE_MAX_BYTES,
    delete the oldest files (by mtime, the same clock the TTL uses) until
    it's under _TRIM_TARGET_RATIO of the cap."""
    global _disk_cache_bytes
    files = []
    for f in THUMBNAIL_CACHE_DIR.glob("*.jpg"):
        try:
            st = f.stat()
        except FileNotFoundError:
            continue  # deleted by the scheduler meanwhile
        files.append((st.st_mtime, st.st_size, f))
    total = sum(size for _, size, _ in files)
    if total > THUMBNAIL_CACHE_MAX_BYTES:
        target = THUMBNAIL_CACHE_MAX_BYTES * _TRIM_TARGET_RATIO
        removed = 0
        files.sort(key=lambda x: x[0])
        for _, size, f in files:
            if total <= target:
                break
            f.unlink(missing_ok=True)
            total -= size
            removed += 1
        logger.info("Thumbnail cache over its size cap, removed the %s oldest file(s)", removed)
    _disk_cache_bytes = total


def _record_disk_cache_write(size: int) -> None:
    global _disk_cache_bytes
    if _disk_cache_bytes is None:
        _trim_disk_cache()  # the scan counts the file just written
        return
    _disk_cache_bytes += size
    if _disk_cache_bytes > THUMBNAIL_CACHE_MAX_BYTES:
        _trim_disk_cache()


# Resolved once at import time; every request is checked against these real,
# symlink-free roots so a `..` segment can't walk the served path outside them.
_ALLOWED_IMAGE_ROOTS = [COVERS_DIR.resolve(), MUSIC_DIR.resolve()]

_IMAGE_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


@router.get("/images/{full_path:path}")
def get_local_image(
    full_path: str,
    current_user: User = Depends(require_auth_flexible),
):
    """Serve images from /config/covers or /data directories.

    Requires auth like every other route, but via require_auth_flexible()
    rather than the usual Authorization-header-only require_auth: the
    frontend loads these via plain <img src="..."> tags, which can't attach
    a header, so this also accepts the httpOnly access_token cookie the
    browser sends automatically. Path safety is enforced separately by
    resolving the path and checking it's contained within one of the
    allowed roots (see _ALLOWED_IMAGE_ROOTS) -- auth alone wouldn't stop
    traversal for a legitimately logged-in but malicious request. Only
    image files are served, not the music next to them.
    """
    try:
        resolved = (Path("/") / full_path).resolve()
    except (OSError, RuntimeError):
        raise HTTPException(status_code=400, detail="Invalid path")

    if not any(resolved.is_relative_to(root) for root in _ALLOWED_IMAGE_ROOTS):
        raise HTTPException(status_code=403, detail="Path not allowed")
    media_type = _IMAGE_TYPES.get(resolved.suffix.lower())
    if media_type is None:
        raise HTTPException(status_code=403, detail="Not an image")
    if not resolved.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(resolved, media_type=media_type)


@router.get("/thumbnail")
async def get_thumbnail(
    url: str = Query(..., description="Thumbnail URL to proxy and cache"),
    current_user: User = Depends(require_auth_flexible),
) -> Response:
    """
    Proxy and cache thumbnail images from YouTube/Google's thumbnail CDNs.

    Served from the disk cache when it holds a fresh copy, else fetched and
    cached.

    Requires auth via require_auth_flexible(), like /images: the
    thumbnails themselves are public, but each new URL costs an upstream
    fetch and a file on disk, so anonymous requests could otherwise fill
    the cache. Restricted to a fixed set of hosts (see
    _ALLOWED_THUMBNAIL_HOSTS), redirect targets included (see
    _check_redirect_target), so this can't be used as an open SSRF proxy
    to fetch arbitrary internal/external URLs, and to images of at most
    THUMBNAIL_MAX_IMAGE_BYTES so one file can't take a large share of the
    cache's size cap.
    """
    try:
        if not _is_allowed_thumbnail_url(url):
            raise HTTPException(status_code=400, detail="URL host not allowed")

        cache_path = _get_cache_path(url)
        if _is_cache_valid(cache_path):
            return _image_response(cache_path.read_bytes(), "HIT")

        logger.debug("Cache miss, fetching: %s", url[:80])

        async with httpx.AsyncClient(
            timeout=10.0,
            event_hooks={"request": [_check_redirect_target]},
        ) as client:
            try:
                async with client.stream(
                    "GET",
                    url,
                    follow_redirects=True,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                    },
                ) as response:
                    response.raise_for_status()
                    # Content-Length is only a hint (it may be absent or
                    # wrong), so the streamed byte count is what's enforced.
                    declared = response.headers.get("content-length")
                    if declared and declared.isdigit() and int(declared) > THUMBNAIL_MAX_IMAGE_BYTES:
                        raise HTTPException(status_code=502, detail="Thumbnail too large")
                    chunks = []
                    received = 0
                    async for chunk in response.aiter_bytes():
                        received += len(chunk)
                        if received > THUMBNAIL_MAX_IMAGE_BYTES:
                            raise HTTPException(status_code=502, detail="Thumbnail too large")
                        chunks.append(chunk)
                    content = b"".join(chunks)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    raise HTTPException(
                        status_code=503,
                        detail="Source temporarily unavailable"
                    )
                # The image host refused it (a URL it doesn't serve): the
                # page draws its fallback picture
                logger.warning("Thumbnail source answered %s for %s", e.response.status_code, url[:120])
                raise HTTPException(status_code=502, detail=f"Thumbnail source answered {e.response.status_code}")

        try:
            THUMBNAIL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(content)
            _record_disk_cache_write(len(content))
        except OSError as e:
            logger.warning("Failed to cache thumbnail: %s", e)

        return _image_response(content, "MISS")

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timeout fetching thumbnail")
    except httpx.RequestError as e:
        logger.error("Network error fetching thumbnail: %s", e)
        raise HTTPException(status_code=502, detail="Failed to fetch thumbnail")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected error in thumbnail proxy")
        raise HTTPException(status_code=500, detail=str(e))
