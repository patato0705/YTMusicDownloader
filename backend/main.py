# backend/main.py
from __future__ import annotations
import logging
import os
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from . import config
from .body_limit import BodySizeLimitMiddleware
from .logging_config import configure_logging
from .db import init_db
from .routers import (
    admin, albums, artists, auth, charts, export, features, health,
    jobs, library, media, playlists, recommendations, search, tracks,
)
from .secrets import jwt_secret
from .services.login_throttle import TooManyAttempts

logger = logging.getLogger("backend.main")

# Vite names every built asset after its content hash, so a file under
# /static/assets never changes: a new build is new names
_ASSETS_CACHE_CONTROL = "public, max-age=31536000, immutable"
# index.html is the one file that changes in place from one image to the
# next: always revalidated (a 304 when unchanged), or a browser holding an
# old copy asks for assets the new image no longer has and shows a blank page
_INDEX_CACHE_CONTROL = "no-cache"
# Icons requested at the site root by convention (frontend/public)
_ROOT_ICONS = frozenset({"favicon.ico", "apple-touch-icon.png"})


class SecurityHeadersMiddleware:
    """
    Headers for every response: no MIME sniffing (a user-supplied file is
    never run as a script or page), and no full URLs sent to the external
    sites the app links to. No X-Frame-Options: dashboards (Homarr,
    Organizr...) embed self-hosted apps in a frame, and the SameSite=Lax
    cookies already keep a cross-site frame signed out.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
            await send(message)

        await self.app(scope, receive, send_with_headers)


class _AssetFiles(StaticFiles):
    """StaticFiles with the caching each kind of file allows."""

    def file_response(self, full_path, stat_result, scope, status_code=200):
        response = super().file_response(full_path, stat_result, scope, status_code)
        is_asset = Path(full_path).parent.name == "assets"
        response.headers["Cache-Control"] = _ASSETS_CACHE_CONTROL if is_asset else _INDEX_CACHE_CONTROL
        return response


def create_app() -> FastAPI:
    """Create and configure the FastAPI app (factory)."""
    configure_logging(
        level=logging.INFO,
        use_local_time=os.environ.get("LOG_LOCAL_TIME", "1") not in ("0", "false", "False"),
        process_name="web",
    )

    # A broken sign-in setup must stop the web process with a clear message,
    # not start half-working
    config.validate_auth_config()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info(
            "Starting (CONFIG_DIR=%s, DOWNLOAD_DIR=%s, MUSIC_DIR=%s)",
            config.CONFIG_DIR, config.DOWNLOAD_DIR, config.MUSIC_DIR,
        )
        config.ensure_dirs()
        # Both raise: the app can't work without its database or a saved
        # signing key, so the process stops with the reason in the log
        init_db()
        jwt_secret()
        yield
        logger.info("Application shutdown")

    # Docs under /api, so the SPA owns every other path
    app = FastAPI(
        title="YTMusicDownloader",
        version=config.APP_VERSION,
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )

    # Before any route reads a body (backend/body_limit.py). Added before
    # CORS so CORS wraps it: the last middleware added is the outermost,
    # and its 413s need CORS headers like any other response.
    app.add_middleware(BodySizeLimitMiddleware)

    # JSON and the frontend bundle shrink tenfold or more (the albums list
    # of a 5,000-album library: 2.6 MB to 140 KB), and the Library page
    # refetches it every few seconds while downloads run. Starlette leaves
    # images and audio alone (already compressed). Level 6: level 9 takes
    # twice as long for no smaller output on this JSON.
    app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=6)
    app.add_middleware(SecurityHeadersMiddleware)

    # CORS - default to same-origin only (no cross-origin access at all).
    # The standard deployment (this Dockerfile) serves the frontend from
    # the same origin as the API, which browsers never subject to CORS
    # checks in the first place -- so this default costs nothing for the
    # normal setup. If you're running the frontend on a different origin
    # (a custom/split deployment), set CORS_ALLOWED_ORIGINS to a
    # comma-separated list of the exact origin(s) to allow. Auth now rides
    # on cookies, so a wildcard here would mean any origin could make
    # credentialed requests -- deliberately not offered as an option.
    cors_env = os.environ.get("CORS_ALLOWED_ORIGINS", "")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in cors_env.split(",") if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Failed password throttling (services/login_throttle.py). retry_after is
    # repeated in the body because the frontend's ApiError doesn't keep headers.
    @app.exception_handler(TooManyAttempts)
    async def too_many_attempts_handler(request: Request, exc: TooManyAttempts) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={"detail": "too_many_attempts", "retry_after": exc.retry_after},
            headers={"Retry-After": str(exc.retry_after)},
        )

    # API routers first: they take precedence over the SPA catch-all below
    for module in (admin, albums, artists, auth, charts, export, features, health,
                   jobs, library, media, playlists, recommendations, search, tracks):
        app.include_router(module.router)

    @app.get("/api", tags=["root"])
    def api_root() -> dict:
        return {"ok": True, "service": "music-backend", "version": app.version}

    # Unmatched /api/* paths get a JSON 404 instead of the SPA
    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"], include_in_schema=False)
    async def api_404_handler(path: str):
        return JSONResponse(status_code=404, content={"detail": f"API endpoint not found: /api/{path}"})

    # Frontend build (copied in by the Dockerfile; absent in a dev checkout,
    # where the Vite dev server serves it)
    static_dir = Path(__file__).resolve().parent / "static"
    index_file = static_dir / "index.html"

    if index_file.exists():
        app.mount("/static", _AssetFiles(directory=str(static_dir)), name="static")

        # Every other path is a frontend route: React Router handles it (404s
        # included). Except the icons browsers and iOS look for at the root
        # without reading index.html first: those are the files under /static.
        @app.get("/{full_path:path}", response_class=HTMLResponse, include_in_schema=False)
        def spa(full_path: str) -> FileResponse:
            if full_path in _ROOT_ICONS:
                return FileResponse(static_dir / full_path, headers={"Cache-Control": _INDEX_CACHE_CONTROL})
            return FileResponse(index_file, headers={"Cache-Control": _INDEX_CACHE_CONTROL})

        logger.debug("Serving the frontend from %s", static_dir)
    else:
        logger.info("No frontend build at %s; only the API is served", static_dir)

    return app


# Module-level app for ASGI servers (uvicorn, etc.)
app = create_app()


if __name__ == "__main__":
    # Local debugging: python -m backend.main
    import uvicorn

    uvicorn.run("backend.main:app", host=config.HOST, port=config.PORT, log_level="info")
