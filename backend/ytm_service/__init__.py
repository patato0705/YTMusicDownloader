# backend/ytm_service/__init__.py
from __future__ import annotations
"""
Light interface for ytm_service package.

Lazily exposes submodules :
 - adapter, client, normalizers, schemas

Usage:
    from backend.ytm_service import adapter
    adapter.search(...)
"""

from typing import Any, Iterable, List
import importlib
import sys
from . import adapter,client,normalizers

__all__ = ["adapter", "client", "normalizers", "__version__"]

__version__ = "0.1.0"

# loaded modules cache
_modules: dict[str, Any] = {}

# authorized names list
_ALLOWED = {"adapter", "client", "normalizers"}


def _load(name: str) -> Any:
    """
    Loads and caches backend.ytm_service.<name>.
    """
    if name not in _modules:
        _modules[name] = importlib.import_module(f"{__name__}.{name}")
    return _modules[name]


def __getattr__(name: str) -> Any:
    """
    Module-level getattr to allow:
        from backend.ytm_service import adapter
    and load lazily backend.ytm_service.adapter.
    """
    if name in _ALLOWED:
        return _load(name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> List[str]:
    names: List[str] = list(globals().keys())
    names.extend(sorted(_ALLOWED))
    return sorted(set(names))