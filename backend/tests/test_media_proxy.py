"""
The media routes: the thumbnail proxy only fetches from Google's image
hosts, and the image route only serves images from the app's folders.

/api/media/thumbnail fetches a URL the browser chooses. Anywhere else,
that's a server-side request forgery: the container's network, a cloud
metadata endpoint (169.254.169.254). The check has to use the URL exactly
as httpx will fetch it, redirects included.

Nothing here reaches the network: httpx is handed a fake image host
(httpx.MockTransport) that records what it was asked for.
"""
from __future__ import annotations

import uuid
from urllib.parse import quote

import httpx
import pytest

from backend import config
from backend.routers import media

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 32


@pytest.fixture
def image_host(monkeypatch):
    """
    httpx.AsyncClient answering from `image_host.reply(request)` instead of
    the network; `image_host.requests` lists the URLs it was asked for.
    """
    class Host:
        requests: list[str] = []

        @staticmethod
        def reply(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=PNG, headers={"content-type": "image/png"})

    host = Host()
    host.requests = []
    real_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        host.requests.append(str(request.url))
        return host.reply(request)

    def fake_client(*args, **kwargs):
        return real_client(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", fake_client)
    return host


@pytest.fixture
def visitor(auth_headers):
    return auth_headers(config.ROLE_VISITOR)


def thumbnail(client, headers, url):
    return client.get("/api/media/thumbnail", params={"url": url}, headers=headers)


def unique(url: str) -> str:
    """The URL made new, so no test gets another's cached copy"""
    return f"{url}?test={uuid.uuid4().hex}"


# ============================================================================
# THE HOST CHECK
# ============================================================================

@pytest.mark.parametrize("url", [
    "https://lh3.googleusercontent.com/abc=w544-h544",
    "https://i.ytimg.com/vi/abc/hqdefault.jpg",
    "https://yt3.ggpht.com/abc",
    "https://www.gstatic.com/youtube/img/avatar.png",
    "HTTPS://I.YTIMG.COM/vi/abc",
])
def test_googles_image_hosts_are_allowed(url):
    parsed = media._parse_thumbnail_url(url)
    assert parsed is not None
    assert parsed.host == httpx.URL(url).host


@pytest.mark.parametrize("url", [
    "http://i.ytimg.com/vi/abc",              # not https
    "https://169.254.169.254/latest/meta-data",
    "https://localhost/",
    "https://[::1]/",
    "https://evil.com/i.ytimg.com",
    "https://notytimg.com/abc",               # a suffix, not a subdomain
    "https://ytimg.com.evil.com/abc",
    "https://i.ytimg.com@evil.com/abc",       # user info before the real host
    "https://evil.com#@i.ytimg.com/abc",
    "https://evil.com?@i.ytimg.com/abc",
    "https://i.ytimg.com\t.evil.com/abc",     # urllib reads i.ytimg.com.evil.com
    "file:///etc/passwd",
    "i.ytimg.com/abc",
    "",
])
def test_any_other_url_is_refused(url):
    assert media._parse_thumbnail_url(url) is None


@pytest.mark.parametrize("url", [
    "https://169.254.169.254/latest/meta-data",
    "https://i.ytimg.com@evil.com/abc",
    "https://i.ytimg.com\t.evil.com/abc",
])
def test_the_proxy_refuses_them_without_fetching(client, visitor, image_host, url):
    response = thumbnail(client, visitor, url)
    assert response.status_code == 400
    assert image_host.requests == []


def test_the_proxy_fetches_the_url_it_checked(client, visitor, image_host):
    url = unique("https://i.ytimg.com/vi/abc/hqdefault.jpg")
    response = thumbnail(client, visitor, url)
    assert response.status_code == 200
    assert response.content == PNG
    assert response.headers["content-type"] == "image/png"
    assert [httpx.URL(u).host for u in image_host.requests] == ["i.ytimg.com"]

    # Then from the cache, without fetching again
    again = thumbnail(client, visitor, url)
    assert again.headers["x-cache-status"] == "HIT"
    assert len(image_host.requests) == 1


def test_a_redirect_elsewhere_is_not_followed(client, visitor, image_host):
    """An open redirect on an allowed host mustn't hand the fetch to any address."""
    image_host.reply = lambda request: (
        httpx.Response(302, headers={"location": "https://169.254.169.254/latest/meta-data"})
        if request.url.host == "i.ytimg.com"
        else httpx.Response(200, content=b"instance secrets")
    )
    response = thumbnail(client, visitor, unique("https://i.ytimg.com/redirect"))
    assert response.status_code == 502
    assert b"instance secrets" not in response.content
    assert all(httpx.URL(u).host == "i.ytimg.com" for u in image_host.requests)


def test_a_redirect_to_another_allowed_host_is_followed(client, visitor, image_host):
    image_host.reply = lambda request: (
        httpx.Response(302, headers={"location": "https://lh3.googleusercontent.com/abc"})
        if request.url.host == "i.ytimg.com"
        else httpx.Response(200, content=PNG)
    )
    response = thumbnail(client, visitor, unique("https://i.ytimg.com/moved"))
    assert response.status_code == 200
    assert [httpx.URL(u).host for u in image_host.requests] == ["i.ytimg.com", "lh3.googleusercontent.com"]


def test_an_unexpected_error_keeps_its_reason_in_the_log(client, visitor, image_host, caplog):
    def broken(request):
        raise RuntimeError(f"something about {config.CONFIG_DIR}")
    image_host.reply = broken

    response = thumbnail(client, visitor, unique("https://i.ytimg.com/broken"))
    assert response.status_code == 500
    assert response.json() == {"detail": "Thumbnail proxy error"}
    assert str(config.CONFIG_DIR) in caplog.text


# ============================================================================
# LOCAL IMAGES
# ============================================================================

def local_image(client, headers, path):
    # Percent-encoded, so neither httpx nor the test client tidies the path up first
    return client.get("/api/media/images/" + quote(str(path).replace("\\", "/").lstrip("/"), safe="/"), headers=headers)


def test_images_in_the_app_folders_are_served(client, visitor):
    config.COVERS_DIR.mkdir(parents=True, exist_ok=True)
    cover = config.COVERS_DIR / "test-cover.png"
    cover.write_bytes(PNG)
    response = local_image(client, visitor, cover)
    assert response.status_code == 200
    assert response.content == PNG


def test_files_that_arent_images_are_not(client, visitor):
    song = config.MUSIC_DIR / "Artist" / "song.opus"
    song.parent.mkdir(parents=True, exist_ok=True)
    song.write_bytes(b"OggS")
    assert local_image(client, visitor, song).status_code == 403


def test_nothing_outside_the_app_folders_is_served(client, visitor):
    assert local_image(client, visitor, "/etc/passwd").status_code == 403
    # The database is in /config, next to the covers, not in them
    assert local_image(client, visitor, f"{config.COVERS_DIR}/../db.sqlite").status_code == 403
    assert local_image(client, visitor, f"{config.COVERS_DIR}/../../etc/x.png").status_code == 403


def test_a_nul_character_is_an_invalid_path(client, visitor):
    response = client.get("/api/media/images/config/covers/a%00b.png", headers=visitor)
    assert response.status_code == 400
