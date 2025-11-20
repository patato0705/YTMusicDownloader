# backend/logging_config.py
from __future__ import annotations
import time
import logging


# --- Logging config -------------------------------------------------------
def configure_logging(level: int = logging.INFO, use_local_time: bool = True) -> None:
    """
    Configure root logger with a simple formatter.
    If use_local_time is True, the formatter will show local time (TZ env).
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
    handler = logging.StreamHandler()
    formatter = logging.Formatter(fmt)

    if not use_local_time:
        # force UTC timestamps in logs
        formatter.converter = time.gmtime

    handler.setFormatter(formatter)
    root.handlers = [handler]