# backend/services/login_throttle.py
"""
Failed password attempt throttling.

Each bucket (an IP, an account, a trusted browser...) keeps the timestamps
of its recent failures. Once a bucket holds `limit` failures inside the
window, further attempts are refused (TooManyAttempts) *before* the password
is checked, until the oldest of them ages out. Refusing instead of sleeping
matters: the auth routes run in FastAPI's threadpool, so a sleep would hold
a thread per attacker request and starve the rest of the API.

State is in-memory: the API is a single uvicorn process (deploy/
supervisord.conf), and losing the counters on a restart is acceptable.

Functions:
- check() - Raise TooManyAttempts if any bucket is full
- record_failure() - Add a failure to buckets
- clear() - Forget a bucket's failures
"""
from __future__ import annotations
import math
import threading
import time
from collections import deque
from typing import Deque, Dict, Iterable, Tuple

# Sweep buckets whose failures all expired once there are this many, so
# attempts against many different usernames can't grow memory without bound
_SWEEP_THRESHOLD = 1024

_failures: Dict[str, Deque[float]] = {}
_lock = threading.Lock()


class TooManyAttempts(Exception):
    """A bucket is full; retry_after is the wait in seconds."""

    def __init__(self, retry_after: int):
        super().__init__(f"Too many failed attempts, retry in {retry_after}s")
        self.retry_after = retry_after


def check(buckets: Iterable[Tuple[str, int]], window_seconds: int) -> None:
    """
    Raise TooManyAttempts if any (key, limit) bucket holds `limit` failures
    within the window. A limit of 0 disables that bucket.
    """
    now = time.monotonic()
    retry_after = 0
    with _lock:
        for key, limit in buckets:
            if limit <= 0:
                continue
            q = _failures.get(key)
            if not q or len(q) < limit:
                continue
            # The limit-th most recent failure is the one that has to expire
            # (the limit may have been lowered since these were recorded)
            wait = q[-limit] + window_seconds - now
            if wait > 0:
                retry_after = max(retry_after, math.ceil(wait))
    if retry_after:
        raise TooManyAttempts(retry_after)


def record_failure(buckets: Iterable[Tuple[str, int]], window_seconds: int) -> None:
    """Record a failed attempt in each (key, limit) bucket whose limit isn't 0."""
    now = time.monotonic()
    with _lock:
        for key, limit in buckets:
            if limit <= 0:
                continue
            q = _failures.setdefault(key, deque())
            q.append(now)
            # Only the newest `limit` failures can ever decide a check
            while len(q) > limit:
                q.popleft()
        if len(_failures) > _SWEEP_THRESHOLD:
            cutoff = now - window_seconds
            for key in [k for k, q in _failures.items() if q[-1] <= cutoff]:
                del _failures[key]


def clear(key: str) -> None:
    """Forget every failure recorded for a bucket."""
    with _lock:
        _failures.pop(key, None)
