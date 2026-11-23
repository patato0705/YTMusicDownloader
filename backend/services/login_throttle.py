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
- login_account_key() - Bucket of an account's failed sign-ins
- ip_key() - What a per-IP bucket is keyed by (an IPv6 /64)
"""
from __future__ import annotations
import hashlib
import ipaddress
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


def login_account_key(username: str) -> str:
    """
    Bucket for failed sign-ins on an account from browsers it doesn't know.
    Keyed by the name as typed (lowercased), existing account or not, so a
    429 doesn't reveal which accounts exist. Hashed: the name is whatever
    the request sent, up to the 2 MiB body limit, and buckets are kept for
    the whole window.
    """
    return "login:user:" + hashlib.sha256(username.lower().encode("utf-8")).hexdigest()


def ip_key(host: str) -> str:
    """
    The address a per-IP bucket counts: an IPv6 address by its /64, which
    is what one connection (a home, a server) is handed, so cycling through
    it doesn't make a new bucket per attempt. An IPv4 address as is, also
    when written IPv4-mapped (::ffff:a.b.c.d).
    """
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return host  # "unknown", or a test client's name
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped:
            return str(ip.ipv4_mapped)
        return str(ipaddress.IPv6Network((ip, 64), strict=False))
    return str(ip)


def clear(key: str) -> None:
    """Forget every failure recorded for a bucket."""
    with _lock:
        _failures.pop(key, None)
