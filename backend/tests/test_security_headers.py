"""
Security headers: on every response, and the Content-Security-Policy on
the app's pages.

The policy allows inline scripts by hash only, worked out from the built
index.html. Tests run without a frontend build (the app then sends no
policy), so the pages are a small app of their own here, behind the same
middleware.
"""
from __future__ import annotations

import base64
import hashlib

import pytest
from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from backend.security_headers import SecurityHeadersMiddleware, content_security_policy

THEME_SCRIPT = "document.documentElement.classList.toggle('dark', localStorage.theme === 'dark')"
INDEX_HTML = f"""<!doctype html>
<html>
  <head>
    <script>{THEME_SCRIPT}</script>
    <script type="module" crossorigin src="/static/assets/index.js"></script>
  </head>
  <body><div id="root"></div></body>
</html>"""


def sha256(script: str) -> str:
    return "'sha256-" + base64.b64encode(hashlib.sha256(script.encode()).digest()).decode() + "'"


@pytest.fixture
def policy(tmp_path):
    index = tmp_path / "index.html"
    index.write_text(INDEX_HTML, encoding="utf-8")
    return content_security_policy(index)


def directives(policy: str) -> dict[str, list[str]]:
    return {name: values for name, *values in (part.split() for part in policy.split("; "))}


def test_inline_scripts_are_allowed_by_their_hash_only(policy):
    script_src = directives(policy)["script-src"]
    assert script_src == ["'self'", sha256(THEME_SCRIPT)]
    assert "'unsafe-inline'" not in policy


def test_everything_else_comes_from_the_apps_origin(policy):
    d = directives(policy)
    assert d["default-src"] == ["'self'"]
    assert d["connect-src"] == ["'self'"]
    # data: for the inline SVG of the select arrow; Google's images come through /api/media
    assert d["img-src"] == ["'self'", "data:"]
    assert d["object-src"] == ["'none'"]
    assert d["base-uri"] == ["'none'"]


def test_an_edited_script_gets_its_new_hash(tmp_path):
    index = tmp_path / "index.html"
    index.write_text(INDEX_HTML.replace(THEME_SCRIPT, "console.log(1)"), encoding="utf-8")
    assert sha256("console.log(1)") in content_security_policy(index)
    assert sha256(THEME_SCRIPT) not in content_security_policy(index)


def test_no_policy_without_a_frontend_build(tmp_path):
    assert content_security_policy(tmp_path / "index.html") is None


@pytest.fixture
def pages(policy):
    """An app with pages and API routes behind the middleware"""
    page = lambda request: HTMLResponse("<p>page</p>")  # noqa: E731
    own_policy = lambda request: HTMLResponse("<p>page</p>", headers={"Content-Security-Policy": "default-src 'none'"})  # noqa: E731
    app = Starlette(routes=[
        Route("/", page),
        Route("/library", page),
        Route("/static/index.html", page),
        Route("/api/docs", page),
        Route("/api/health", lambda request: JSONResponse({"ok": True})),
        Route("/own-policy", own_policy),
    ])
    return TestClient(SecurityHeadersMiddleware(app, content_security_policy=policy))


@pytest.mark.parametrize("path", ["/", "/library", "/static/index.html"])
def test_pages_get_the_policy(pages, policy, path):
    assert pages.get(path).headers["content-security-policy"] == policy


@pytest.mark.parametrize("path", ["/api/health", "/api/docs"])
def test_api_responses_do_not(pages, path):
    # /api/docs: Swagger UI loads from a CDN
    assert "content-security-policy" not in pages.get(path).headers


@pytest.mark.parametrize("path", ["/", "/api/health", "/api/docs"])
def test_every_response_gets_the_other_headers(pages, path):
    headers = pages.get(path).headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["referrer-policy"] == "strict-origin-when-cross-origin"


def test_a_route_setting_its_own_policy_keeps_it(pages):
    assert pages.get("/own-policy").headers["content-security-policy"] == "default-src 'none'"


def test_the_app_sends_them(client):
    headers = client.get("/api/health").headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["referrer-policy"] == "strict-origin-when-cross-origin"
