"""
Who may call each API route.

ACCESS below is the reference: every route, with the lowest role that may
call it. The tests fail when a route is missing from it, when a route asks
for something else than what's written here, and when a request from a
lower role isn't refused. So adding a route, or changing who may call one,
means updating this table: the access decision shows up in the diff.

Levels, from open to closed:
    public              no sign-in
    temporary_password  signed in, including a user who still has to
                        replace a temporary password (first admin, reset)
    visitor             any signed-in user
    member              member or administrator
    admin               administrator only

Only refusals are requested: while the access rules hold, no request gets
past them into the route's code, so nothing here touches the library, the
downloads or YouTube Music.
"""
from __future__ import annotations

import importlib
import pkgutil
import re

import pytest

from backend import config
from backend import routers

ACCESS = {
    # admin
    "GET /api/admin/users": "admin",
    "POST /api/admin/users": "admin",
    "PATCH /api/admin/users/{user_id}/role": "admin",
    "POST /api/admin/users/{user_id}/deactivate": "admin",
    "POST /api/admin/users/{user_id}/activate": "admin",
    "POST /api/admin/users/{user_id}/reset-password": "admin",
    "DELETE /api/admin/users/{user_id}": "admin",
    "GET /api/admin/settings": "admin",
    "PUT /api/admin/settings/{key}": "admin",
    "GET /api/admin/youtube-cookies": "admin",
    "PUT /api/admin/youtube-cookies": "admin",
    "DELETE /api/admin/youtube-cookies": "admin",
    # albums
    "GET /api/albums/{album_id}": "visitor",
    "POST /api/albums/{album_id}/download": "member",
    "POST /api/albums/{album_id}/retry": "member",
    # artists
    "GET /api/artists/{artist_id}": "visitor",
    "POST /api/artists/{artist_id}/follow": "member",
    "DELETE /api/artists/{artist_id}/follow": "member",
    "PUT /api/artists/{artist_id}/like": "member",
    "DELETE /api/artists/{artist_id}/like": "member",
    # auth
    "GET /api/auth/config": "public",
    "POST /api/auth/register": "public",
    "POST /api/auth/login": "public",
    "GET /api/auth/oidc/login": "public",
    "GET /api/auth/oidc/callback": "public",
    "POST /api/auth/refresh": "public",
    "POST /api/auth/logout": "public",
    "GET /api/auth/me": "temporary_password",
    "POST /api/auth/me/onboarding": "visitor",
    "POST /api/auth/change-password": "temporary_password",
    # charts
    "GET /api/charts/{country_code}": "visitor",
    "GET /api/charts": "visitor",
    "POST /api/charts/{country_code}/follow": "admin",
    "DELETE /api/charts/{country_code}/follow": "admin",
    "PATCH /api/charts/{country_code}": "admin",
    "POST /api/charts/{country_code}/sync": "admin",
    # export
    "GET /api/export/library": "visitor",
    "GET /api/export/backup": "admin",
    "POST /api/import": "admin",
    # features
    "GET /api/features": "visitor",
    # health
    "GET /api/health": "public",
    # jobs
    "GET /api/jobs/stats/summary": "visitor",
    # library
    "GET /api/library/artists": "visitor",
    "GET /api/library/albums": "visitor",
    "GET /api/library/tracks": "visitor",
    "GET /api/library/stats": "visitor",
    "DELETE /api/library/artists/{artist_id}": "admin",
    "DELETE /api/library/albums/{album_id}": "admin",
    "GET /api/library/exclusions": "visitor",
    "DELETE /api/library/exclusions/{kind}/{item_id}": "member",
    # media
    "GET /api/media/images/{full_path:path}": "visitor",
    "GET /api/media/thumbnail": "visitor",
    # playlists
    "GET /api/playlists": "visitor",
    "GET /api/playlists/{playlist_id}": "visitor",
    "POST /api/playlists/{playlist_id}": "member",
    "PATCH /api/playlists/{playlist_id}": "member",
    "POST /api/playlists/{playlist_id}/sync": "member",
    "DELETE /api/playlists/{playlist_id}": "member",
    # recommendations
    "GET /api/recommendations": "visitor",
    "GET /api/recommendations/dismissed": "member",
    "PUT /api/recommendations/dismissed/{artist_id}": "member",
    "DELETE /api/recommendations/dismissed/{artist_id}": "member",
    # search
    "GET /api/search": "visitor",
    # tracks
    "GET /api/tracks/{track_id}/lyrics": "visitor",
    "PUT /api/tracks/{track_id}/lyrics": "member",
}

# The dependency (backend/dependencies.py) that sets each level, strictest first
_LEVEL_BY_DEPENDENCY = (
    ("require_admin", "admin"),
    ("require_member_or_admin", "member"),
    ("require_auth_allow_temporary_password", "temporary_password"),
    ("require_auth", "visitor"),
    ("require_auth_flexible", "visitor"),
)


def _dependency_names(dependant) -> set[str]:
    names = set()
    for sub in dependant.dependencies:
        names.add(getattr(sub.call, "__name__", ""))
        names |= _dependency_names(sub)
    return names


def _declared_routes() -> dict[str, str]:
    """Every route in backend/routers/, with the level its dependencies give it."""
    found = {}
    for module in pkgutil.iter_modules(routers.__path__):
        router = importlib.import_module(f"{routers.__name__}.{module.name}").router
        for route in router.routes:
            names = _dependency_names(route.dependant)
            level = next((lvl for dep, lvl in _LEVEL_BY_DEPENDENCY if dep in names), "public")
            for method in route.methods:
                found[f"{method} {route.path}"] = level
    return found


def _request(client, route: str, headers: dict | None = None):
    """Call the route with "1" for each path parameter (refused before it's read)."""
    method, path = route.split(" ", 1)
    return client.request(method, re.sub(r"\{[^}]+\}", "1", path), headers=headers)


def _routes_at(*levels: str) -> list[str]:
    return [route for route, level in ACCESS.items() if level in levels]


def test_every_route_is_listed_with_its_access():
    declared = _declared_routes()
    missing = sorted(set(declared) - set(ACCESS))
    gone = sorted(set(ACCESS) - set(declared))
    changed = sorted(f"{r}: listed {ACCESS[r]}, declares {declared[r]}"
                     for r in set(ACCESS) & set(declared) if ACCESS[r] != declared[r])
    assert not missing, f"Routes missing from ACCESS (add them with their level): {missing}"
    assert not gone, f"Routes in ACCESS that no longer exist (remove them): {gone}"
    assert not changed, f"Routes whose access differs from ACCESS: {changed}"


def test_admin_routes_are_under_admin_access():
    """Anything under /api/admin/ is for administrators, whatever the table says."""
    assert all(level == "admin" for route, level in ACCESS.items() if " /api/admin/" in route)


@pytest.mark.parametrize("route", _routes_at("temporary_password", "visitor", "member", "admin"))
def test_refused_without_sign_in(client, route):
    assert _request(client, route).status_code == 401


@pytest.mark.parametrize("route", _routes_at("visitor", "member", "admin"))
def test_refused_with_a_temporary_password(client, auth_headers, route):
    headers = auth_headers(config.ROLE_ADMINISTRATOR, must_change_password=True)
    response = _request(client, route, headers)
    assert response.status_code == 403
    assert response.json()["detail"] == "password_change_required"


@pytest.mark.parametrize("route", _routes_at("member", "admin"))
def test_refused_to_visitors(client, auth_headers, route):
    assert _request(client, route, auth_headers(config.ROLE_VISITOR)).status_code == 403


@pytest.mark.parametrize("route", _routes_at("admin"))
def test_refused_to_members(client, auth_headers, route):
    assert _request(client, route, auth_headers(config.ROLE_MEMBER)).status_code == 403
