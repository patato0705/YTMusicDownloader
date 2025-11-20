# backend/simple_cache.py
from __future__ import annotations
import threading, time
from typing import Any, Optional, Dict, Tuple, Callable

_cache: Dict[str, Tuple[float, Any]] = {}
_lock = threading.Lock()

def set(key: str, value: Any, ttl: Optional[int] = None) -> None:
    expiry = time.time() + (ttl if ttl is not None else 0)
    with _lock:
        _cache[key] = (expiry, value)

def get(key: str) -> Optional[Any]:
    now = time.time()
    with _lock:
        ent = _cache.get(key)
        if not ent:
            return None
        expiry, value = ent
        if expiry and expiry < now:
            del _cache[key]
            return None
        return value

def delete(key: str) -> None:
    with _lock:
        _cache.pop(key, None)

def clear() -> None:
    with _lock:
        _cache.clear()

def memoize(ttl: Optional[int] = None) -> Callable:
    def deco(fn):
        def wrapper(*args, **kwargs):
            key = f"{fn.__module__}.{fn.__name__}:{args}:{kwargs}"
            v = get(key)
            if v is not None:
                return v
            r = fn(*args, **kwargs)
            set(key, r, ttl)
            return r
        return wrapper
    return deco