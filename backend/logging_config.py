# backend/logging_config.py
from __future__ import annotations
import logging
import os
import time
from logging.handlers import RotatingFileHandler
from typing import Optional

# Per-process log files under config.LOG_DIR: web.log, worker-download-0.log,
# scheduler.log, ... Each process writes its own file because several of
# them run at once (deploy/supervisord.conf) and RotatingFileHandler is not
# safe to share across processes -- two of them rotating the same file
# truncate each other's output.
LOG_FILE_MAX_BYTES = 5 * 1024 * 1024
LOG_FILE_BACKUPS = 3


# --- Logging config -------------------------------------------------------
def configure_logging(
    level: int = logging.INFO,
    use_local_time: bool = True,
    process_name: Optional[str] = None,
) -> None:
    """
    Configure the root logger: stdout (for `docker logs`) plus a rotating
    file in config.LOG_DIR named after the process.

    process_name defaults to WORKER_NAME (set per worker by supervisord),
    then "app". If use_local_time is True, timestamps use local time (TZ env).
    """
    # call tzset if available on this platform (POSIX). Use getattr to silence static checks.
    tzset_fn = getattr(time, "tzset", None)
    if callable(tzset_fn):
        try:
            tzset_fn()
        except Exception:
            # ignore if tzset fails
            pass

    root = logging.getLogger()
    root.setLevel(level)

    fmt = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
    formatter = logging.Formatter(fmt)
    if not use_local_time:
        # force UTC timestamps in logs
        formatter.converter = time.gmtime

    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    handlers: list[logging.Handler] = [stream]

    name = process_name or os.environ.get("WORKER_NAME", "").strip() or "app"
    safe = "".join(c for c in name if c.isalnum() or c in "-_.") or "app"
    try:
        from . import config
        config.LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            config.LOG_DIR / f"{safe}.log",
            maxBytes=LOG_FILE_MAX_BYTES,
            backupCount=LOG_FILE_BACKUPS,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)
    except Exception as e:
        # A read-only or missing /config/logs shouldn't take the process
        # down; stdout still has everything.
        logging.getLogger("logging_config").warning("File logging disabled: %s", e)

    root.handlers = handlers

    if name == "web":
        _route_uvicorn_through_root()


class _DropHealthchecks(logging.Filter):
    """Keep the docker healthcheck's GET /api/health every 30s out of the access log."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            return "/api/health" not in record.getMessage()
        except Exception:
            return True


def _route_uvicorn_through_root() -> None:
    """
    uvicorn installs its own stdout handlers on "uvicorn", "uvicorn.error"
    and "uvicorn.access" with propagate=False, so by default its access log
    never reaches our file. Strip those and let the records propagate to
    the root handlers (stdout + file) in our format.
    """
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(logger_name)
        lg.handlers = []
        lg.propagate = True
    logging.getLogger("uvicorn.access").addFilter(_DropHealthchecks())
