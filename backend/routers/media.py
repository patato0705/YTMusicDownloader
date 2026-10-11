# backend/routers/media.py
"""
Media endpoints for serving and caching thumbnails from external sources.

Endpoints:
- GET /api/media/images/{full_path:path} - Serve images from /config/covers or /data directories.
- GET /api/media/thumbnail/debug - Cache status debug endpoint (admin only).
- GET /api/media/thumbnail - Proxy and cache thumbnail images from external sources.
- DELETE /api/media/cache/clear - Clear thumbnail cache (admin only).

Expired cache files are never served (see _is_cache_valid); deleting them
is the scheduler's job (Scheduler.cleanup_thumbnail_cache). The TTL alone
doesn't bound the folder, since every distinct URL (e.g. each =w..-h.. size
suffix of the same Google image) is its own file, so writes also enforce
THUMBNAIL_CACHE_MAX_BYTES by deleting the oldest files (see _trim_disk_cache).
"""
import hashlib
import logging
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import Response, JSONResponse, FileResponse

from ..config import (
    THUMBNAIL_CACHE_DIR,
    THUMBNAIL_CACHE_TTL,
    THUMBNAIL_CACHE_MAX_BYTES,
    THUMBNAIL_MAX_IMAGE_BYTES,
    MUSIC_DIR,
    COVERS_DIR,
)
from ..dependencies import require_admin, get_current_user_flexible
from ..models import User

logger = logging.getLogger("routers.media")

router = APIRouter(prefix="/api/media", tags=["Media"])

CACHE_DIR = THUMBNAIL_CACHE_DIR
CACHE_TTL = THUMBNAIL_CACHE_TTL

# Ensure cache directory exists
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# In-memory cache for recently accessed URLs
_memory_cache: dict[str, tuple[float, Path]] = {}
_memory_cache_max_size = 1000

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
        logger.warning(f"Thumbnail fetch redirected to a disallowed URL: {str(request.url)[:80]}")
        raise HTTPException(status_code=502, detail="Thumbnail redirected to a disallowed host")


def _get_cache_path(url: str) -> Path:
    """Generate cache file path from URL hash."""
    url_hash = hashlib.sha256(url.encode()).hexdigest()
    return CACHE_DIR / f"{url_hash}.jpg"


def _is_cache_valid(cache_path: Path) -> bool:
    """Check if cached file exists and hasn't expired."""
    if not cache_path.exists():
        return False
    file_age = time.time() - cache_path.stat().st_mtime
    return file_age < CACHE_TTL


def _evict_memory_cache():
    """Evict oldest 20% of entries if memory cache is full."""
    if len(_memory_cache) <= _memory_cache_max_size:
        return
    
    items = sorted(_memory_cache.items(), key=lambda x: x[1][0])
    to_remove = len(items) // 5
    for url, _ in items[:to_remove]:
        _memory_cache.pop(url, None)


def _trim_disk_cache() -> None:
    """Rescan the disk cache and, if it's over THUMBNAIL_CACHE_MAX_BYTES,
    delete the oldest files (by mtime, the same clock the TTL uses) until
    it's under _TRIM_TARGET_RATIO of the cap."""
    global _disk_cache_bytes
    files = []
    for f in CACHE_DIR.glob("*.jpg"):
        try:
            st = f.stat()
        except FileNotFoundError:
            continue  # deleted by the scheduler or the admin endpoint meanwhile
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
        logger.info(f"Thumbnail cache over its size cap, removed the {removed} oldest file(s)")
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


@router.get("/images/{full_path:path}")
def get_local_image(
    full_path: str,
    current_user: User = Depends(get_current_user_flexible),
):
    """Serve images from /config/covers or /data directories.

    Requires auth like every other route, but via get_current_user_flexible()
    rather than the usual Authorization-header-only require_auth: the
    frontend loads these via plain <img src="..."> tags, which can't attach
    a header, so this also accepts the httpOnly access_token cookie the
    browser sends automatically. Path safety is enforced separately by
    resolving the path and checking it's contained within one of the
    allowed roots (see _ALLOWED_IMAGE_ROOTS) -- auth alone wouldn't stop
    traversal for a legitimately logged-in but malicious request.
    """

    # Reconstruct absolute path and resolve it (collapses any ".." segments)
    try:
        resolved = (Path("/") / full_path).resolve()
    except (OSError, RuntimeError):
        raise HTTPException(status_code=400, detail="Invalid path")

    logger.info(f"Serving image: {resolved}")

    if not any(resolved.is_relative_to(root) for root in _ALLOWED_IMAGE_ROOTS):
        raise HTTPException(status_code=403, detail="Path not allowed")

    file_path = resolved

    # Check file exists
    if not file_path.exists() or not file_path.is_file():
        logger.warning(f"File not found: {resolved}")
        raise HTTPException(status_code=404, detail="Image not found")
    
    # Determine media type
    media_type = "image/jpeg"
    if file_path.suffix.lower() in ['.png']:
        media_type = "image/png"
    elif file_path.suffix.lower() in ['.webp']:
        media_type = "image/webp"
    
    return FileResponse(file_path, media_type=media_type)

@router.get("/thumbnail/debug")
async def debug_info(
    current_user: User = Depends(require_admin),
) -> JSONResponse:
    """Cache status debug endpoint (admin only)."""
    return JSONResponse({
        "cache_dir": str(CACHE_DIR),
        "cache_dir_exists": CACHE_DIR.exists(),
        "cache_ttl_seconds": CACHE_TTL,
        "cached_files_count": len(list(CACHE_DIR.glob("*.jpg"))),
        "cache_bytes_estimate": _disk_cache_bytes,
        "cache_max_bytes": THUMBNAIL_CACHE_MAX_BYTES,
        "memory_cache_size": len(_memory_cache),
        "music_dir": str(MUSIC_DIR),
    })


@router.get("/thumbnail")
async def get_thumbnail(
    url: str = Query(..., description="Thumbnail URL to proxy and cache"),
    current_user: User = Depends(get_current_user_flexible),
) -> Response:
    """
    Proxy and cache thumbnail images from YouTube/Google's thumbnail CDNs.

    Flow:
    1. Check memory cache
    2. Check disk cache
    3. Fetch from source and cache

    Requires auth via get_current_user_flexible(), like /images: the
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

        # Check memory cache
        if url in _memory_cache:
            timestamp, cache_path = _memory_cache[url]
            if _is_cache_valid(cache_path):
                return Response(
                    content=cache_path.read_bytes(),
                    media_type="image/jpeg",
                    headers={
                        "Cache-Control": "private, max-age=604800",
                        "X-Cache-Status": "HIT-MEMORY",
                    },
                )
            _memory_cache.pop(url, None)
        
        # Check disk cache
        cache_path = _get_cache_path(url)
        if _is_cache_valid(cache_path):
            logger.debug(f"Cache hit: {cache_path.name}")
            
            _memory_cache[url] = (time.time(), cache_path)
            _evict_memory_cache()
            
            return Response(
                content=cache_path.read_bytes(),
                media_type="image/jpeg",
                headers={
                    "Cache-Control": "private, max-age=604800",
                    "X-Cache-Status": "HIT-DISK",
                },
            )
        
        # Fetch from source
        logger.info(f"Cache miss, fetching: {url[:80]}...")
        
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
                    content_type = response.headers.get("content-type", "image/jpeg")
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    raise HTTPException(
                        status_code=503,
                        detail="Source temporarily unavailable"
                    )
                raise
        
        # Save to cache
        try:
            cache_path.write_bytes(content)
            logger.debug(f"Cached: {cache_path.name} ({len(content)} bytes)")
            
            _memory_cache[url] = (time.time(), cache_path)
            _evict_memory_cache()
            _record_disk_cache_write(len(content))
        except Exception as e:
            logger.warning(f"Failed to cache thumbnail: {e}")
        
        return Response(
            content=content,
            media_type=content_type,
            headers={
                "Cache-Control": "private, max-age=604800",
                "X-Cache-Status": "MISS",
            },
        )
    
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timeout fetching thumbnail")
    except httpx.RequestError as e:
        logger.error(f"Network error fetching thumbnail: {e}")
        raise HTTPException(status_code=502, detail="Failed to fetch thumbnail")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected error in thumbnail proxy")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/cache/clear")
async def clear_thumbnail_cache(
    current_user: User = Depends(require_admin),
) -> dict:
    """Clear thumbnail cache (admin only)."""
    global _disk_cache_bytes
    try:
        count = 0
        for cache_file in CACHE_DIR.glob("*.jpg"):
            cache_file.unlink(missing_ok=True)
            count += 1
        
        _memory_cache.clear()
        _disk_cache_bytes = 0
        
        logger.info(f"Cleared {count} cached thumbnails")
        return {
            "status": "success",
            "files_deleted": count,
            "message": f"Cleared {count} cached thumbnails"
        }
    except Exception as e:
        logger.exception("Failed to clear cache")
        raise HTTPException(status_code=500, detail=str(e))