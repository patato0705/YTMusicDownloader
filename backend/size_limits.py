# backend/size_limits.py
"""
Byte limits on bodies read as a stream: the requests the API receives
(body_limit.py) and the thumbnails it fetches (routers/media.py).

Content-Length is only a hint (absent on a chunked body, or wrong), so the
bytes actually read are what's enforced; a declared size over the limit
just lets the caller refuse before reading anything.
"""
from __future__ import annotations
from typing import Optional, Union


def declared_too_large(content_length: Optional[Union[str, bytes]], limit: int) -> bool:
    """
    A Content-Length over `limit`, or one that isn't a plain number (a
    sender that can't state its size properly isn't worth reading).
    False when there is none: count with ByteBudget instead.
    """
    if content_length is None:
        return False
    if isinstance(content_length, bytes):
        content_length = content_length.decode("latin-1")
    return not content_length.isdigit() or int(content_length) > limit


class ByteBudget:
    """Bytes read so far against a limit."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.received = 0

    def add(self, size: int) -> bool:
        """Count `size` more bytes. True once over the limit."""
        self.received += size
        return self.received > self.limit
