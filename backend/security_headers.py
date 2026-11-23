# backend/security_headers.py
"""
Security headers on the app's responses (main.py adds the middleware).

- Every response: no MIME sniffing (a user-supplied file is never run as a
  script or page), and no full URLs sent to the external sites the app
  links to.
- The pages: a Content-Security-Policy (content_security_policy()).

No X-Frame-Options or frame-ancestors: dashboards (Homarr, Organizr...)
embed self-hosted apps in a frame, and the SameSite=Lax cookies already
keep a cross-site frame signed out.
"""
from __future__ import annotations
import base64
import hashlib
import re
from pathlib import Path
from typing import Optional

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# An inline <script> of index.html (no src): what the policy has to allow by hash
_INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.DOTALL | re.IGNORECASE)


def content_security_policy(index_file: Path) -> Optional[str]:
    """
    The Content-Security-Policy of the app's pages: everything from this
    origin only, and of inline scripts only those the built index.html
    holds (the theme set before first paint), allowed by their hash. Read
    from the file actually served, so editing that script needs nothing
    else. Should an injected script ever get into a page, it can't run
    inline, load code from elsewhere or send anything to another site.

    Images also allow data: (the select arrow is an inline SVG); images on
    other hosts are refused, the Google ones come through /api/media.
    No upgrade-insecure-requests, which would break plain-HTTP setups by
    sending the app's own files to https.
    None without a frontend build (the Vite dev server serves the pages).
    """
    if not index_file.exists():
        return None
    html = index_file.read_text(encoding="utf-8")
    hashes = " ".join(
        "'sha256-" + base64.b64encode(hashlib.sha256(script.encode("utf-8")).digest()).decode("ascii") + "'"
        for script in _INLINE_SCRIPT.findall(html)
    )
    return "; ".join((
        "default-src 'self'",
        f"script-src 'self' {hashes}".rstrip(),
        "style-src 'self'",
        "img-src 'self' data:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'self'",
    ))


class SecurityHeadersMiddleware:
    """
    The headers above on every response, and the Content-Security-Policy
    on every page outside /api: the app at any path, /static/index.html
    included (the same app, which mustn't be a way around it). Not on
    /api/docs, whose Swagger UI comes from a CDN.
    """

    def __init__(self, app: ASGIApp, content_security_policy: Optional[str] = None) -> None:
        self.app = app
        self.csp = content_security_policy

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
                if (
                    self.csp
                    and headers.get("content-type", "").startswith("text/html")
                    and not scope["path"].startswith("/api/")
                ):
                    headers.setdefault("Content-Security-Policy", self.csp)
            await send(message)

        await self.app(scope, receive, send_with_headers)
