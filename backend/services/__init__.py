# backend/services/__init__.py
"""
Services package - provides lazy module loading for service modules.
This allows scheduler and other components to access services without circular imports.
"""
from __future__ import annotations
import importlib
from typing import Any

from . import albums
from . import artists
from . import normalizers
from . import playlists
from . import search
from . import subscriptions
from . import tracks
