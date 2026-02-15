# backend/main.py
from __future__ import annotations
import os
import logging
import importlib
from typing import List, Optional
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from . import config
from .logging_config import configure_logging
from .db import init_db, get_engine
from .scheduler import start_default_scheduler, stop_default_scheduler

logger = logging.getLogger("backend.main")


def _include_router_safe(app: FastAPI, router_module_name: str) -> None:
    """
    Try to import backend.routers.<router_module_name> and include its `router` if present.
    Non-fatal: logs warnings/errors and continues.
    """
    pkg = __package__ or "backend"
    full_name = f"{pkg}.routers.{router_module_name}"
    try:
        mod = importlib.import_module(full_name)
    except Exception as e:
        logger.warning("Router module %s could not be imported: %s", full_name, e)
        return

    router = getattr(mod, "router", None)
    if router is None:
        logger.warning("Router module %s has no attribute 'router'; skipping", full_name)
        return

    try:
        app.include_router(router)
        logger.info("Included router %s", full_name)
    except Exception as e:
        logger.exception("Failed including router %s: %s", full_name, e)


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI app (factory).
    """
    # configure logging early
    log_local = os.environ.get("LOG_LOCAL_TIME", "1") not in ("0", "false", "False")
    configure_logging(level=logging.INFO, use_local_time=log_local)

    version = "0.1"
    try:
        # try to read ytm_service version if available
        from .ytm_service import __version__ as ytm_version  # type: ignore
        version = str(ytm_version)
    except Exception:
        # ignore if module missing
        pass

    # lifespan must be defined BEFORE creating the FastAPI app instance
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """
        Lifespan manager: runs once at startup, yields control to FastAPI, then runs shutdown.
        Replaces deprecated @app.on_event handlers.
        """
        # STARTUP
        logger.info("Application startup: ensuring config dirs, initializing DB and scheduler")
        try:
            # ensure all configured directories exist (CONFIG_DIR, TEMP_DIR, COVERS_DIR, etc.)
            try:
                config.ensure_dirs()
                logger.info(
                    "Config directories ensured (CONFIG_DIR=%s, DOWNLOAD_DIR=%s, MUSIC_DIR=%s)",
                    config.CONFIG_DIR,
                    config.DOWNLOAD_DIR,
                    config.MUSIC_DIR,
                )
            except Exception:
                logger.exception("Failed to ensure config directories")

            # initialize DB (create tables if missing)
            try:
                init_db()
                logger.info("Database initialized (engine=%s)", get_engine())
            except Exception:
                logger.exception("init_db failed")

            # start scheduler (default instance) — safe if already started
            try:
                start_default_scheduler()
                logger.info("Scheduler started")
            except Exception:
                logger.exception("Failed starting scheduler")

        except Exception:
            logger.exception("Unhandled error during startup")

        # give control to FastAPI (application runs)
        try:
            yield
        finally:
            # SHUTDOWN
            logger.info("Application shutdown: stopping scheduler")
            try:
                stop_default_scheduler()
                logger.info("Scheduler stopped")
            except Exception:
                logger.exception("Failed stopping scheduler")

    # create app with lifespan handler and move docs under /api
    app = FastAPI(
        title="YTMusicDownloader",
        version=version,
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )

    # CORS - allow origins from env or default to '*'
    cors_env = os.environ.get("CORS_ALLOWED_ORIGINS", "*")
    if cors_env.strip() == "*" or not cors_env.strip():
        origins = ["*"]
    else:
        # comma separated list
        origins = [o.strip() for o in cors_env.split(",") if o.strip()]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include API routers FIRST (these take precedence)
    routers_to_try: List[str] = [
        "admin",
        "albums",
        "artists",
        "auth",
        "health",
        "jobs",
        "library",
        "media",
        "playlists",
        "search",
        "tracks",
    ]
    for r in routers_to_try:
        _include_router_safe(app, r)

    # Provide a lightweight API root at /api returning version/service info
    @app.get("/api", tags=["root"])
    def api_root() -> dict:
        return {"ok": True, "service": "music-backend", "version": app.version}

    # API 404 handler - catches any /api/* routes that don't match
    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"], include_in_schema=False)
    async def api_404_handler(path: str):
        """Catch-all for unmatched API routes."""
        return JSONResponse(
            status_code=404,
            content={
                "detail": f"API endpoint not found: /api/{path}",
                "ok": False
            }
        )

    # Frontend static files setup
    static_dir = Path(__file__).resolve().parent / "static"
    index_file = static_dir / "index.html"
    
    if static_dir.exists() and index_file.exists():
        try:
            # Mount the entire static directory to serve all assets
            # The 'name' parameter is required for StaticFiles
            app.mount("/static", StaticFiles(directory=str(static_dir), html=True), name="static")
            logger.info("Mounted frontend static files from %s at /static", static_dir)
        except Exception as e:
            logger.exception("Failed mounting static directory: %s", e)

        # SPA root - serves index.html for frontend routes
        @app.get("/", response_class=HTMLResponse, include_in_schema=False)
        def spa_root() -> FileResponse:
            return FileResponse(index_file)

        # SPA catch-all - only catches non-API, non-static routes
        @app.get("/{full_path:path}", response_class=HTMLResponse, include_in_schema=False)
        async def spa_catchall(full_path: str, request: Request):
            """
            Catch-all for SPA routes.
            Returns index.html to let the frontend handle routing and 404s.
            This only runs for paths that don't match:
            - /api/* (handled by API routers above)
            - /static/* (handled by StaticFiles mount)
            """
            # Return index.html for all other routes - let React Router handle it
            return FileResponse(index_file)

        logger.info("Mounted SPA from %s - frontend will handle routing and 404s", static_dir)

    else:
        logger.info("No frontend static files found at %s; only API will be available", static_dir)
        
        # Basic root for API-only mode
        @app.get("/", tags=["root"])
        def root() -> dict:
            return {"ok": True, "service": "music-backend", "version": app.version}

    return app


# create module-level app for ASGI servers (uvicorn, etc.)
app = create_app()


if __name__ == "__main__":
    # allow running this module directly for local debugging
    import uvicorn

    # ensure logging configured for direct run
    configure_logging(level=logging.INFO, use_local_time=(os.environ.get("LOG_LOCAL_TIME", "1") not in ("0", "false", "False")))
    host = os.environ.get("HOST", config.HOST)
    port = int(os.environ.get("PORT", config.PORT))
    logger.info("Starting uvicorn on %s:%s", host, port)
    uvicorn.run("backend.main:app", host=host, port=port, reload=False, log_level="info")