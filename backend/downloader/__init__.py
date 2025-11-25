# backend/downloader/__init__.py
from __future__ import annotations

"""
Downloader package: reexports submodules and some utilities functions
to allow access like:

    import backend.downloader as downloader
    downloader.core.download_track_by_videoid(...)
    downloader.lyrics.get_synced_lyrics(...)

Reexport common functions (package level) is optional but practical.
"""

# submodules import (make accessible via `downloader.core`, etc.)
from . import core
from . import cover
from . import metadata
from . import embed

# commonly used utilities functions — expose at package level
# (optional but practical for tasks.py and others)
download_track_by_videoid = core.download_track_by_videoid

try:
    select_best_thumbnail_url = cover.select_best_thumbnail_url
except Exception:
    select_best_thumbnail_url = None

# public package control
__all__ = [
    "core",
    "cover",
    "metadata",
    "embed",
    "download_track_by_videoid",
    "select_best_thumbnail_url",
]