# backend/services/oidc.py
"""
Single sign-on: OpenID Connect relying party (Authorization Code flow with
PKCE, state and nonce). Configured from env vars only (see config.py).

Signature, key and claim checks are done by joserfc; this module only does
the HTTP plumbing around them and maps provider identities to accounts.

Functions:
- get_metadata() - Provider discovery document (cached)
- start_flow() - Authorization URL plus the values the callback must check
- encode_flow_state() / decode_flow_state() - Those values, in a signed cookie
- complete_flow() - Code exchange, ID token validation, userinfo -> claims
- sign_in() - Find or create the account for verified claims, apply roles

Exceptions:
- OidcError - .code is the short reason sent to /login?oidc_error=...
"""
from __future__ import annotations
import base64
import hashlib
import logging
import re
import secrets
import threading
import time
import unicodedata
from datetime import timedelta
from typing import Any, Dict, Optional, Set
from urllib.parse import quote, urlencode

import httpx
import jwt as pyjwt
from joserfc import jwt as jose_jwt
from joserfc.errors import InvalidKeyIdError, JoseError, MissingKeyError
from joserfc.jwk import KeySet
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..models import User
from ..secrets import jwt_secret
from ..settings import get_setting
from ..time_utils import now_utc
from . import auth as auth_svc

logger = logging.getLogger("services.oidc")

CALLBACK_PATH = "/api/auth/oidc/callback"

_HTTP_TIMEOUT = 10
_METADATA_TTL = 3600
_FLOW_TTL = timedelta(minutes=10)
# ID tokens must be signed with the provider's private key: no "none", and no
# HMAC (that would use the client secret, which we hold, as the signing key)
_ALLOWED_ALGS = {"RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512", "EdDSA"}
_CLOCK_LEEWAY = 60

_lock = threading.Lock()
_metadata: Optional[Dict[str, Any]] = None
_metadata_at = 0.0
_keys: Optional[KeySet] = None


class OidcError(Exception):
    """
    Sign-in can't complete. `code` is what the login page shows a message
    for: denied, not_allowed, inactive, unavailable, failed.
    """

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def redirect_uri() -> str:
    return config.PUBLIC_URL + CALLBACK_PATH


# ============================================================================
# PROVIDER METADATA AND KEYS
# ============================================================================

def _get_json(url: str, **kwargs) -> Dict[str, Any]:
    try:
        response = httpx.get(url, timeout=_HTTP_TIMEOUT, follow_redirects=True, **kwargs)
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as e:
        raise OidcError("unavailable", f"GET {url} failed: {e}")
    if not isinstance(data, dict):
        raise OidcError("unavailable", f"GET {url} did not return a JSON object")
    return data


def get_metadata() -> Dict[str, Any]:
    """
    The provider's discovery document, cached for an hour. Fetched on first
    use rather than at startup, so a provider that's down doesn't keep the
    app from starting (password sign-in keeps working meanwhile).
    """
    global _metadata, _metadata_at, _keys
    with _lock:
        if _metadata and time.monotonic() - _metadata_at < _METADATA_TTL:
            return _metadata
    issuer_url = config.OIDC_ISSUER_URL.rstrip("/")
    data = _get_json(f"{issuer_url}/.well-known/openid-configuration")
    missing = [k for k in ("issuer", "authorization_endpoint", "token_endpoint", "jwks_uri") if not data.get(k)]
    if missing:
        raise OidcError("unavailable", f"provider discovery document lacks {', '.join(missing)}")
    # Spec: the advertised issuer must be the one we were configured with
    # (trailing slash aside, which providers and admins write inconsistently)
    if str(data["issuer"]).rstrip("/") != issuer_url:
        raise OidcError(
            "unavailable",
            f"provider says its issuer is {data['issuer']!r}, not OIDC_ISSUER_URL {config.OIDC_ISSUER_URL!r}",
        )
    with _lock:
        _metadata, _metadata_at = data, time.monotonic()
        _keys = None  # re-read alongside, the provider may have rotated them
    return data


def _get_keys(force: bool = False) -> KeySet:
    global _keys
    with _lock:
        if _keys is not None and not force:
            return _keys
    jwks = _get_json(get_metadata()["jwks_uri"])
    try:
        keys = KeySet.import_key_set(jwks)
    except (JoseError, ValueError, TypeError) as e:
        raise OidcError("unavailable", f"provider signing keys unreadable: {e}")
    with _lock:
        _keys = keys
    return keys


# ============================================================================
# FLOW
# ============================================================================

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def start_flow() -> Dict[str, str]:
    """
    Authorization URL to send the browser to, plus the state/nonce/PKCE
    verifier that the callback must find again (see encode_flow_state).
    """
    metadata = get_metadata()
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    params = {
        "response_type": "code",
        "client_id": config.OIDC_CLIENT_ID,
        "redirect_uri": redirect_uri(),
        "scope": config.OIDC_SCOPES,
        "state": state,
        "nonce": nonce,
        "code_challenge": _b64url(hashlib.sha256(verifier.encode("ascii")).digest()),
        "code_challenge_method": "S256",
    }
    endpoint = metadata["authorization_endpoint"]
    url = endpoint + ("&" if "?" in endpoint else "?") + urlencode(params)
    return {"url": url, "state": state, "nonce": nonce, "verifier": verifier}


def encode_flow_state(flow: Dict[str, str]) -> str:
    """The callback's half of start_flow(), as a short-lived signed token."""
    payload = {
        "typ": "oidc_flow",
        "state": flow["state"],
        "nonce": flow["nonce"],
        "verifier": flow["verifier"],
        "exp": now_utc() + _FLOW_TTL,
    }
    return pyjwt.encode(payload, jwt_secret(), algorithm=config.JWT_ALGORITHM)


def decode_flow_state(token: str) -> Optional[Dict[str, str]]:
    try:
        payload = pyjwt.decode(token, jwt_secret(), algorithms=[config.JWT_ALGORITHM])
    except pyjwt.InvalidTokenError:
        return None
    if payload.get("typ") != "oidc_flow":
        return None
    return payload


def _client_auth(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """httpx kwargs authenticating us at the token endpoint."""
    methods = metadata.get("token_endpoint_auth_methods_supported") or ["client_secret_basic"]
    if "client_secret_basic" not in methods and "client_secret_post" in methods:
        return {"data": {"client_id": config.OIDC_CLIENT_ID, "client_secret": config.OIDC_CLIENT_SECRET}}
    # RFC 6749 2.3.1: both parts are form-urlencoded before going into Basic
    credentials = f"{quote(config.OIDC_CLIENT_ID, safe='')}:{quote(config.OIDC_CLIENT_SECRET, safe='')}"
    return {"headers": {"Authorization": "Basic " + base64.b64encode(credentials.encode()).decode()}}


def _exchange_code(metadata: Dict[str, Any], code: str, verifier: str) -> Dict[str, Any]:
    auth = _client_auth(metadata)
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri(),
        "code_verifier": verifier,
        **auth.get("data", {}),
    }
    try:
        response = httpx.post(
            metadata["token_endpoint"], data=data, headers=auth.get("headers"), timeout=_HTTP_TIMEOUT
        )
    except httpx.HTTPError as e:
        raise OidcError("unavailable", f"token endpoint unreachable: {e}")
    try:
        tokens = response.json()
    except ValueError:
        tokens = {}
    if response.status_code != 200 or not isinstance(tokens, dict):
        error = tokens.get("error") if isinstance(tokens, dict) else None
        raise OidcError("failed", f"token endpoint answered {response.status_code} ({error or 'no error code'})")
    if not tokens.get("id_token"):
        raise OidcError("failed", "token response has no id_token (is 'openid' in OIDC_SCOPES?)")
    return tokens


def _validate_id_token(metadata: Dict[str, Any], id_token: str, nonce: str) -> Dict[str, Any]:
    advertised = metadata.get("id_token_signing_alg_values_supported") or ["RS256"]
    algorithms = [alg for alg in advertised if alg in _ALLOWED_ALGS]
    if not algorithms:
        raise OidcError("failed", f"provider signs ID tokens with {advertised}, none of which is accepted")

    try:
        try:
            token = jose_jwt.decode(id_token, _get_keys(), algorithms=algorithms)
        except (InvalidKeyIdError, MissingKeyError):
            # Signed with a key we haven't seen: the provider rotated its keys
            token = jose_jwt.decode(id_token, _get_keys(force=True), algorithms=algorithms)
        jose_jwt.JWTClaimsRegistry(
            leeway=_CLOCK_LEEWAY,
            iss={"essential": True, "value": metadata["issuer"]},
            aud={"essential": True, "value": config.OIDC_CLIENT_ID},
            sub={"essential": True},
            exp={"essential": True},
            iat={"essential": True},
            nonce={"essential": True, "value": nonce},
        ).validate(token.claims)
    except JoseError as e:
        raise OidcError("failed", f"ID token rejected: {e.__class__.__name__}: {e}")

    claims = dict(token.claims)
    # OIDC Core 3.1.3.7: with several audiences, azp must name us
    aud = claims["aud"]
    if (isinstance(aud, list) and len(aud) > 1 or "azp" in claims) and claims.get("azp") != config.OIDC_CLIENT_ID:
        raise OidcError("failed", "ID token was issued to another client (azp)")
    return claims


def _fetch_userinfo(metadata: Dict[str, Any], access_token: Optional[str], subject: str) -> Dict[str, Any]:
    """
    Claims from the userinfo endpoint: several providers only put profile
    or group claims there, not in the ID token.
    """
    endpoint = metadata.get("userinfo_endpoint")
    if not endpoint or not access_token:
        return {}
    info = _get_json(endpoint, headers={"Authorization": f"Bearer {access_token}"})
    # Spec: must be about the same user, or none of it can be trusted
    if info.get("sub") != subject:
        raise OidcError("failed", "userinfo is about a different subject than the ID token")
    return info


def complete_flow(code: str, flow: Dict[str, str]) -> Dict[str, Any]:
    """Exchange the code and return the verified identity claims."""
    metadata = get_metadata()
    tokens = _exchange_code(metadata, code, flow["verifier"])
    claims = _validate_id_token(metadata, tokens["id_token"], flow["nonce"])
    userinfo = _fetch_userinfo(metadata, tokens.get("access_token"), claims["sub"])
    # Userinfo may add or refresh profile/group claims, but the ID token is
    # authoritative for who this is
    return {**claims, **userinfo, **{k: claims[k] for k in ("iss", "sub", "aud")}}


# ============================================================================
# ACCOUNTS
# ============================================================================

def groups_of(claims: Dict[str, Any]) -> Set[str]:
    value = claims.get(config.OIDC_GROUPS_CLAIM)
    if isinstance(value, str):
        return {value}
    if isinstance(value, list):
        return {g for g in value if isinstance(g, str)}
    return set()


def role_from_groups(groups: Set[str]) -> Optional[str]:
    if config.OIDC_ADMIN_GROUP and config.OIDC_ADMIN_GROUP in groups:
        return config.ROLE_ADMINISTRATOR
    if config.OIDC_MEMBER_GROUP and config.OIDC_MEMBER_GROUP in groups:
        return config.ROLE_MEMBER
    return None


def _username_for(session: Session, claims: Dict[str, Any]) -> str:
    """
    A free username from the provider's, reduced to the characters local
    usernames allow (accents transliterated). Never an existing account's:
    "admin" at the provider becomes "admin-2" if a local admin exists.
    """
    raw = str(claims.get("preferred_username") or claims.get("name") or "")
    ascii_name = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    base = re.sub(r"[^A-Za-z0-9_-]+", "-", ascii_name).strip("-_")[:60]
    if len(base) < 3:
        base = "user"
    candidate, n = base, 2
    while auth_svc.get_user_by_username(session, candidate):
        candidate, n = f"{base}-{n}", n + 1
    return candidate


def sign_in(session: Session, claims: Dict[str, Any]) -> User:
    """
    The account for these verified claims, created if allowed. With a group
    mapping configured the provider owns roles: re-applied every sign-in.
    """
    issuer = get_metadata()["issuer"]
    subject = claims["sub"]
    user = session.execute(
        select(User).where(User.oidc_issuer == issuer, User.oidc_subject == subject)
    ).scalars().first()
    mapped = role_from_groups(groups_of(claims)) if config.OIDC_ROLES_FROM_GROUPS else None

    if user is None:
        # Being in a group named in the config means being an intended user
        if mapped is None and not get_setting(session, "auth.oidc_signup_enabled"):
            raise OidcError("not_allowed", f"no account for {subject!r} and new sign-ins are off")
        user = User(
            username=_username_for(session, claims),
            password_hash=None,
            oidc_issuer=issuer,
            oidc_subject=subject,
            role=mapped or get_setting(session, "auth.oidc_default_role"),
            is_active=True,
            created_at=now_utc(),
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        logger.info("Created single sign-on account %s (role=%s)", user.username, user.role)
        return user

    if not user.is_active:
        raise OidcError("inactive", f"account {user.username} is deactivated")
    if config.OIDC_ROLES_FROM_GROUPS:
        role = mapped or get_setting(session, "auth.oidc_default_role")
        if role != user.role:
            logger.info("Role of %s set to %s from provider groups (was %s)", user.username, role, user.role)
            user.role = role
            session.add(user)
            session.commit()
    return user
