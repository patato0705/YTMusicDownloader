# backend/body_limit.py
"""
Request body size limit (uvicorn has none of its own).

FastAPI reads and parses a route's body before running its dependencies,
authentication included, so without this anyone could have the server
buffer and parse a body of any size on any route. A declared
Content-Length over the limit is refused upfront (uvicorn never delivers
more than declared); a body without one (chunked) is counted as it arrives
and cut off once over.
"""
from __future__ import annotations
from typing import Dict

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .size_limits import ByteBudget, declared_too_large

# Well above any JSON body the app sends: lyrics (200,000 characters), an
# uploaded cookies.txt (512 KiB)...
DEFAULT_LIMIT = 2 * 1024 * 1024
# Imports carry a whole library, every track of it
LIMITS: Dict[str, int] = {
    "/api/import": 256 * 1024 * 1024,
}


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit = LIMITS.get(scope["path"], DEFAULT_LIMIT)
        declared = next((value for name, value in scope["headers"] if name == b"content-length"), None)
        if declared_too_large(declared, limit):
            await JSONResponse({"detail": _detail(limit)}, status_code=413)(scope, receive, send)
            return
        if declared is not None:
            await self.app(scope, receive, send)
            return

        budget = ByteBudget(limit)

        async def limited_receive() -> Message:
            message = await receive()
            if message["type"] == "http.request" and budget.add(len(message.get("body", b""))):
                # FastAPI passes an HTTPException raised while it reads
                # the body on as is, so this becomes the response
                raise HTTPException(status_code=413, detail=_detail(limit))
            return message

        await self.app(scope, limited_receive, send)


def _detail(limit: int) -> str:
    return f"Request body too large (limit {limit // (1024 * 1024)} MiB)"
