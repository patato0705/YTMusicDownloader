# backend/routers/media.py
"""
Media router for serving and caching thumbnails from external sources.
Prevents 429 errors from Google's servers by caching images locally.
"""
import hashlib
import logging
import time
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import Response, JSONResponse, FileResponse
from starlette.background import BackgroundTask

from sqlalchemy.orm import Session
from ..deps import get_db

from ..config import THUMBNAIL_CACHE_DIR, THUMBNAIL_CACHE_TTL, MUSIC_DIR
from ..dependencies import require_auth, require_admin
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


def _cleanup_old_cache():
    """Background task to remove expired cache files."""
    try:
        now = time.time()
        cleaned = 0
        for cache_file in CACHE_DIR.glob("*.jpg"):
            if now - cache_file.stat().st_mtime > CACHE_TTL:
                cache_file.unlink(missing_ok=True)
                cleaned += 1
        if cleaned > 0:
            logger.info(f"Cleaned up {cleaned} expired cache files")
    except Exception as e:
        logger.warning(f"Cache cleanup failed: {e}")


def _evict_memory_cache():
    """Evict oldest 20% of entries if memory cache is full."""
    if len(_memory_cache) <= _memory_cache_max_size:
        return
    
    items = sorted(_memory_cache.items(), key=lambda x: x[1][0])
    to_remove = len(items) // 5
    for url, _ in items[:to_remove]:
        _memory_cache.pop(url, None)

@router.get("/images/{full_path:path}")
def get_local_image(full_path: str):
    """Serve images from /config/temp/covers or /data directories."""
    
    # Reconstruct absolute path
    absolute_path = "/" + full_path
    
    logger.info(f"Serving image: {absolute_path}")
    
    # Check allowed directories
    if not (absolute_path.startswith('/config/temp/covers/') or absolute_path.startswith('/data/')):
        raise HTTPException(status_code=403, detail="Path not allowed")
    
    # Create Path object
    file_path = Path(absolute_path)
    
    # Check file exists
    if not file_path.exists() or not file_path.is_file():
        logger.warning(f"File not found: {absolute_path}")
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
        "memory_cache_size": len(_memory_cache),
        "music_dir": str(MUSIC_DIR),
    })


@router.get("/thumbnail")
async def get_thumbnail(
    url: str = Query(..., description="Thumbnail URL to proxy and cache"),
) -> Response:
    """
    Proxy and cache thumbnail images from external sources (YouTube, Google, etc.).
    
    Flow:
    1. Check memory cache
    2. Check disk cache
    3. Fetch from source and cache
    
    No authentication required - thumbnails are public.
    """
    try:
        # Validate URL
        if not url.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="Invalid URL")
        
        # Check memory cache
        if url in _memory_cache:
            timestamp, cache_path = _memory_cache[url]
            if _is_cache_valid(cache_path):
                return Response(
                    content=cache_path.read_bytes(),
                    media_type="image/jpeg",
                    headers={
                        "Cache-Control": "public, max-age=604800",
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
                    "Cache-Control": "public, max-age=604800",
                    "X-Cache-Status": "HIT-DISK",
                },
                background=BackgroundTask(_cleanup_old_cache),
            )
        
        # Fetch from source
        logger.info(f"Cache miss, fetching: {url[:80]}...")
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get(
                    url,
                    follow_redirects=True,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                    },
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    raise HTTPException(
                        status_code=503,
                        detail="Source temporarily unavailable"
                    )
                raise
            
            content = response.content
            content_type = response.headers.get("content-type", "image/jpeg")
        
        # Save to cache
        try:
            cache_path.write_bytes(content)
            logger.debug(f"Cached: {cache_path.name} ({len(content)} bytes)")
            
            _memory_cache[url] = (time.time(), cache_path)
            _evict_memory_cache()
        except Exception as e:
            logger.warning(f"Failed to cache thumbnail: {e}")
        
        return Response(
            content=content,
            media_type=content_type,
            headers={
                "Cache-Control": "public, max-age=604800",
                "X-Cache-Status": "MISS",
            },
            background=BackgroundTask(_cleanup_old_cache),
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
    try:
        count = 0
        for cache_file in CACHE_DIR.glob("*.jpg"):
            cache_file.unlink(missing_ok=True)
            count += 1
        
        _memory_cache.clear()
        
        logger.info(f"Cleared {count} cached thumbnails")
        return {
            "status": "success",
            "files_deleted": count,
            "message": f"Cleared {count} cached thumbnails"
        }
    except Exception as e:
        logger.exception("Failed to clear cache")
        raise HTTPException(status_code=500, detail=str(e))