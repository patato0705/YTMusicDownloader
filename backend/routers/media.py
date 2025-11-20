"""
Media router for serving and caching thumbnails from external sources.
This prevents 429 errors from Google's servers by caching images locally.
DEBUG VERSION with extensive logging.
"""
import hashlib
import logging
import time
from pathlib import Path
from typing import Optional
import httpx
from fastapi import APIRouter, HTTPException, Query, Depends, Response as FastAPIResponse
from fastapi.responses import Response, JSONResponse
from starlette.background import BackgroundTask

from ..config import THUMBNAIL_CACHE_DIR, THUMBNAIL_CACHE_TTL

from backend.dependencies import require_auth, require_member_or_admin, require_admin
from backend.models import User

logger = logging.getLogger("routers.media")
logger.setLevel(logging.DEBUG)  # Force debug level

router = APIRouter(prefix="/api/media", tags=["Media"])

# Use cache directory from config
CACHE_DIR = THUMBNAIL_CACHE_DIR
CACHE_TTL = THUMBNAIL_CACHE_TTL

# Ensure cache directory exists
try:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"✓ Thumbnail cache directory ready: {CACHE_DIR}")
    logger.info(f"✓ Cache directory exists: {CACHE_DIR.exists()}")
    logger.info(f"✓ Cache directory is writable: {CACHE_DIR.is_dir()}")
except Exception as e:
    logger.error(f"✗ Failed to create cache directory {CACHE_DIR}: {e}")

# In-memory cache for recently accessed URLs (URL -> (timestamp, file_path))
_memory_cache: dict[str, tuple[float, Path]] = {}
_memory_cache_max_size = 1000

def _get_cache_path(url: str) -> Path:
    """Generate a cache file path from URL."""
    url_hash = hashlib.sha256(url.encode()).hexdigest()
    return CACHE_DIR / f"{url_hash}.jpg"

def _is_cache_valid(cache_path: Path) -> bool:
    """Check if cached file exists and is not expired."""
    if not cache_path.exists():
        return False
    
    file_age = time.time() - cache_path.stat().st_mtime
    return file_age < CACHE_TTL

def _cleanup_old_cache():
    """Background task to clean up old cache files."""
    try:
        now = time.time()
        cleaned = 0
        for cache_file in CACHE_DIR.glob("*.jpg"):
            file_age = now - cache_file.stat().st_mtime
            if file_age > CACHE_TTL:
                cache_file.unlink(missing_ok=True)
                cleaned += 1
        if cleaned > 0:
            logger.info(f"Cleaned up {cleaned} old cache files")
    except Exception as e:
        logger.warning(f"Cache cleanup failed: {e}")

def _evict_memory_cache():
    """Evict oldest entries from memory cache if it's too large."""
    if len(_memory_cache) <= _memory_cache_max_size:
        return
    
    # Remove oldest 20% of entries
    items = sorted(_memory_cache.items(), key=lambda x: x[1][0])
    to_remove = len(items) // 5
    for url, _ in items[:to_remove]:
        _memory_cache.pop(url, None)
    logger.debug(f"Evicted {to_remove} entries from memory cache")


@router.get("/thumbnail/debug")
async def debug_info(
    current_user: User = Depends(require_admin),
) -> JSONResponse:
    """Debug endpoint to check cache status."""
    return JSONResponse({
        "cache_dir": str(CACHE_DIR),
        "cache_dir_exists": CACHE_DIR.exists(),
        "cache_ttl_seconds": CACHE_TTL,
        "cached_files_count": len(list(CACHE_DIR.glob("*.jpg"))),
        "memory_cache_size": len(_memory_cache),
        "sample_cached_files": [f.name for f in list(CACHE_DIR.glob("*.jpg"))[:5]],
    })


@router.get("/thumbnail")
async def get_thumbnail(
    url: str = Query(..., description="Thumbnail URL to proxy and cache"),
) -> Response:
    """
    Proxy and cache thumbnail images from external sources.
    This prevents rate limiting by serving cached copies.
    """
    logger.info(f"📥 Thumbnail request: {url[:100]}...")
    
    try:
        # Validate URL
        if not url.startswith(("http://", "https://")):
            logger.warning(f"✗ Invalid URL scheme: {url}")
            raise HTTPException(status_code=400, detail="Invalid URL")
        
        # Check memory cache first
        if url in _memory_cache:
            timestamp, cache_path = _memory_cache[url]
            if _is_cache_valid(cache_path):
                logger.info(f"✓ Memory cache HIT: {cache_path.name}")
                return Response(
                    content=cache_path.read_bytes(),
                    media_type="image/jpeg",
                    headers={
                        "Cache-Control": "public, max-age=604800",
                        "X-Cache-Status": "HIT-MEMORY",
                    },
                )
            else:
                logger.debug(f"Memory cache expired: {cache_path.name}")
                _memory_cache.pop(url, None)
        
        # Check disk cache
        cache_path = _get_cache_path(url)
        logger.debug(f"Disk cache path: {cache_path}")
        
        if _is_cache_valid(cache_path):
            logger.info(f"✓ Disk cache HIT: {cache_path.name}")
            
            # Update memory cache
            _memory_cache[url] = (time.time(), cache_path)
            _evict_memory_cache()
            
            content = cache_path.read_bytes()
            logger.debug(f"Serving {len(content)} bytes from disk")
            
            return Response(
                content=content,
                media_type="image/jpeg",
                headers={
                    "Cache-Control": "public, max-age=604800",
                    "X-Cache-Status": "HIT-DISK",
                },
                background=BackgroundTask(_cleanup_old_cache),
            )
        
        # Fetch from source
        logger.info(f"✗ Cache MISS - fetching from source...")
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
                logger.info(f"✓ Fetch success: status={response.status_code}, size={len(response.content)} bytes")
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    logger.warning(f"✗ Rate limited (429) by source")
                    raise HTTPException(
                        status_code=503,
                        detail="Source temporarily unavailable, try again later"
                    )
                logger.error(f"✗ HTTP error: {e.response.status_code}")
                raise
            except Exception as e:
                logger.error(f"✗ Network error: {e}")
                raise
            
            content = response.content
            content_type = response.headers.get("content-type", "image/jpeg")
            logger.debug(f"Content-Type: {content_type}")
        
        # Save to cache
        try:
            cache_path.write_bytes(content)
            logger.info(f"✓ Cached to disk: {cache_path.name} ({len(content)} bytes)")
            
            # Verify write
            if cache_path.exists():
                logger.debug(f"✓ Cache file verified: {cache_path.stat().st_size} bytes")
            else:
                logger.error(f"✗ Cache file not found after write!")
            
            # Update memory cache
            _memory_cache[url] = (time.time(), cache_path)
            _evict_memory_cache()
        except Exception as e:
            logger.error(f"✗ Failed to write cache: {e}")
        
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
        logger.error(f"✗ Timeout fetching: {url[:100]}")
        raise HTTPException(status_code=504, detail="Timeout fetching thumbnail")
    except httpx.RequestError as e:
        logger.error(f"✗ Network error: {e}")
        raise HTTPException(status_code=502, detail="Failed to fetch thumbnail")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"✗ Unexpected error for: {url[:100]}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/cache/clear")
async def clear_thumbnail_cache(
    current_user: User = Depends(require_admin),
) -> dict:
    """
    Clear the thumbnail cache (admin endpoint).
    """
    try:
        count = 0
        for cache_file in CACHE_DIR.glob("*.jpg"):
            cache_file.unlink(missing_ok=True)
            count += 1
        
        _memory_cache.clear()
        
        logger.info(f"✓ Cleared {count} cached thumbnails")
        return {
            "status": "success",
            "files_deleted": count,
            "message": f"Cleared {count} cached thumbnails"
        }
    except Exception as e:
        logger.exception("✗ Failed to clear cache")
        raise HTTPException(status_code=500, detail=str(e))