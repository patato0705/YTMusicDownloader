# backend/routers/auth.py
"""
Authentication endpoints.

Endpoints:
- GET /api/auth/config - Which sign-in methods are available (public)
- POST /api/auth/register - Register new user (public registration)
- POST /api/auth/login - Login with username/password
- GET /api/auth/oidc/login - Start single sign-on (redirects to the provider)
- GET /api/auth/oidc/callback - Single sign-on return point
- POST /api/auth/refresh - Refresh access token
- POST /api/auth/logout - Revoke refresh token
- GET /api/auth/me - Get current user info
- POST /api/auth/change-password - Change password
"""
from __future__ import annotations
import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .. import config
from ..db import get_session
from ..dependencies import require_auth
from ..models import User
from ..schemas import (
    LoginRequest,
    RegisterRequest,
    ChangePasswordRequest,
    LoginResponse,
    TokenResponse,
    UserResponse,
    MessageResponse,
)
from ..services import auth as auth_svc
from ..services import login_throttle
from ..services import oidc
from ..settings import get_setting

logger = logging.getLogger("routers.auth")

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


# ============================================================================
# COOKIE HELPERS
#
# The refresh token (and a copy of the access token) live in httpOnly
# cookies rather than the response body. This keeps them out of reach of
# JavaScript (so an XSS bug can't read them out of localStorage), and lets
# the access_token cookie ride along automatically on plain <img> requests
# to /api/media/images/... and /api/media/thumbnail, which can't carry an
# Authorization header.
# See backend/config.py for the COOKIE_SECURE toggle.
# ============================================================================

def _set_access_cookie(response: Response, access_token: str) -> None:
    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=config.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=config.COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        max_age=config.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        httponly=True,
        secure=config.COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    # Signing out is the "this browser isn't mine" signal (public PC...): it
    # stops being a known browser. A session that simply expires keeps it.
    response.delete_cookie("device_token", path="/api/auth")


# The device token marks a browser that has signed in to an account and not
# signed out since (see login()). Scoped to /api/auth since only login reads it.
def _set_device_cookie(response: Response, device_token: str) -> None:
    response.set_cookie(
        key="device_token",
        value=device_token,
        max_age=config.DEVICE_TOKEN_EXPIRE_DAYS * 86400,
        httponly=True,
        secure=config.COOKIE_SECURE,
        samesite="lax",
        path="/api/auth",
    )


# Carries state/nonce/PKCE verifier from /oidc/login to /oidc/callback. Lax is
# enough: the provider sends the browser back with a top-level GET.
_OIDC_FLOW_COOKIE = "oidc_flow"
_OIDC_FLOW_PATH = "/api/auth/oidc"


def _start_session(response: Response, session: Session, user: User) -> str:
    """Open a session for an authenticated user: cookies set, access token returned."""
    access_token = auth_svc.create_access_token(user)
    refresh_token = auth_svc.create_refresh_token(session, user.id)
    auth_svc.update_last_login(session, user.id)
    _set_access_cookie(response, access_token)
    _set_refresh_cookie(response, refresh_token)
    return access_token


def _require_password_login() -> None:
    if not config.PASSWORD_LOGIN_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="password_login_disabled",
        )


# ============================================================================
# FAILED ATTEMPT THROTTLING (services/login_throttle.py)
# ============================================================================

def _throttle_settings(session: Session) -> tuple[int, int, int]:
    """(per-IP limit, per-account limit, window in seconds); a limit of 0 is off."""
    return (
        get_setting(session, "auth.login_max_failures_per_ip"),
        get_setting(session, "auth.login_max_failures_per_account"),
        get_setting(session, "auth.login_failure_window_minutes") * 60,
    )


def _client_ip(request: Request) -> str:
    # Behind a reverse proxy this is only the real client if uvicorn trusts
    # the proxy's X-Forwarded-For (FORWARDED_ALLOW_IPS, see README)
    return request.client.host if request.client else "unknown"


# ============================================================================
# PUBLIC ENDPOINTS
# ============================================================================

@router.get("/config")
def get_auth_config(
    session: Session = Depends(get_session),
) -> dict:
    """
    Which sign-in methods the login and registration pages should offer.
    Public: needed before anyone is signed in.
    """
    return {
        "password_login_enabled": config.PASSWORD_LOGIN_ENABLED,
        "registration_enabled": config.PASSWORD_LOGIN_ENABLED
        and bool(get_setting(session, "auth.registration_enabled")),
        "oidc_enabled": config.OIDC_ENABLED,
        "oidc_provider_name": config.OIDC_PROVIDER_NAME if config.OIDC_ENABLED else None,
        # Role changes for SSO accounts would be undone at their next sign-in
        "oidc_roles_from_groups": config.OIDC_ENABLED and config.OIDC_ROLES_FROM_GROUPS,
    }


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(
    data: RegisterRequest,
    session: Session = Depends(get_session),
):
    """
    Register a new user (public registration).

    Registration must be enabled via the 'auth.registration_enabled' setting.
    """
    _require_password_login()
    # Check if registration is enabled
    if not get_setting(session, "auth.registration_enabled"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is currently disabled. If you think this is a mistake, please contact an administrator.",
        )

    try:
        user = auth_svc.create_user(
            session=session,
            username=data.username,
            password=data.password,
            role=config.ROLE_VISITOR,  # Default role for public registration
        )

        return UserResponse.model_validate(user)

    except auth_svc.UsernameTakenError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="username_taken")
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/login", response_model=LoginResponse)
def login(
    data: LoginRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
):
    """
    Login with username and password.

    Sets the access token (15min) and refresh token (7 days) as httpOnly
    cookies, and also returns the access token in the body for use in the
    Authorization header on regular API calls.

    Failed attempts are throttled per IP and per account (429 with
    Retry-After once over the limit). A browser holding a device token for
    the account (set on a previous successful login) is counted in its own
    bucket instead of the account's, so failures from elsewhere can't lock
    the owner out of the browser they normally use.
    """
    _require_password_login()
    ip_limit, account_limit, window = _throttle_settings(session)

    device = None
    device_cookie = request.cookies.get("device_token")
    if device_cookie:
        device = auth_svc.verify_device_token(device_cookie)
    target = auth_svc.get_user_by_username(session, data.username)
    # A password change since the token was issued revokes the trust too
    if device and target and device["user_id"] == target.id and not auth_svc.token_revoked(target, device["issued_at"]):
        account_bucket = f"login:device:{device['jti']}"
    else:
        device = None
        account_bucket = login_throttle.login_account_key(data.username)
    buckets = [(f"login:ip:{_client_ip(request)}", ip_limit), (account_bucket, account_limit)]

    login_throttle.check(buckets, window)

    # Authenticate user
    user = auth_svc.authenticate_user(session, data.username, data.password)

    if not user:
        login_throttle.record_failure(buckets, window)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = _start_session(response, session, user)

    # The IP and account buckets are left alone: clearing them on success
    # would let someone with any valid account reset their allowance
    if device:
        login_throttle.clear(account_bucket)
    _set_device_cookie(response, auth_svc.create_device_token(user.id))

    return LoginResponse(
        user=UserResponse.model_validate(user),
        access_token=access_token,
        token_type="bearer",
        expires_in=config.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get("/oidc/login")
def oidc_login():
    """
    Start single sign-on: redirect the browser to the provider. The values
    the callback has to check travel in a short-lived signed cookie.
    """
    if not config.OIDC_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Single sign-on is not configured")
    try:
        flow = oidc.start_flow()
    except oidc.OidcError as e:
        logger.error("Single sign-on unavailable: %s", e)
        return RedirectResponse(f"/login?oidc_error={e.code}", status_code=status.HTTP_303_SEE_OTHER)

    response = RedirectResponse(flow["url"], status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key=_OIDC_FLOW_COOKIE,
        value=oidc.encode_flow_state(flow),
        max_age=600,
        httponly=True,
        secure=config.COOKIE_SECURE,
        samesite="lax",
        path=_OIDC_FLOW_PATH,
    )
    return response


@router.get("/oidc/callback")
def oidc_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    session: Session = Depends(get_session),
):
    """
    Where the provider sends the browser back. Checks state, exchanges the
    code, validates the ID token, then opens a normal session (same cookies
    as a password sign-in) and lands on the app. Failures land on the login
    page with ?oidc_error=<reason>.
    """
    if not config.OIDC_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Single sign-on is not configured")

    def fail(reason: str, detail: str) -> RedirectResponse:
        log = logger.info if reason in ("denied", "not_allowed", "inactive") else logger.warning
        log("Single sign-on failed (%s): %s", reason, detail)
        response = RedirectResponse(f"/login?oidc_error={reason}", status_code=status.HTTP_303_SEE_OTHER)
        response.delete_cookie(_OIDC_FLOW_COOKIE, path=_OIDC_FLOW_PATH)
        return response

    if error:
        return fail("denied", f"provider returned error={error}")
    flow = oidc.decode_flow_state(request.cookies.get(_OIDC_FLOW_COOKIE, ""))
    if not flow:
        return fail("failed", "missing or expired flow cookie (sign-in took over 10 minutes, or cookies are blocked)")
    # Constant-time compare: the state is what ties this callback to our redirect
    if not state or not code or not secrets.compare_digest(state, flow["state"]):
        return fail("failed", "state mismatch")

    try:
        claims = oidc.complete_flow(code, flow)
        user = oidc.sign_in(session, claims)
    except oidc.OidcError as e:
        return fail(e.code, str(e))

    response = RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(_OIDC_FLOW_COOKIE, path=_OIDC_FLOW_PATH)
    _start_session(response, session, user)
    logger.info("User %s signed in with single sign-on", user.username)
    return response


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
):
    """
    Exchange the refresh_token cookie for a new access token.

    Refresh token remains valid until expiration (7 days).
    """
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token cookie present",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify refresh token
    user = auth_svc.verify_refresh_token(session, refresh_token)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = auth_svc.create_access_token(user)
    _set_access_cookie(response, access_token)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=config.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/logout", response_model=MessageResponse)
def logout(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
):
    """
    Revoke the refresh token (logout) and clear auth cookies.

    Idempotent: succeeds even if there's no refresh_token cookie (or it's
    already invalid) so the client always ends up logged out.
    """
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        auth_svc.revoke_refresh_token(session, refresh_token)

    _clear_auth_cookies(response)

    return MessageResponse(message="Logged out successfully")


# ============================================================================
# PROTECTED ENDPOINTS
# ============================================================================

@router.get("/me", response_model=UserResponse)
def get_current_user_info(
    current_user: User = Depends(require_auth),
):
    """
    Get current authenticated user's information.

    """
    return UserResponse.model_validate(current_user)


@router.post("/change-password", response_model=TokenResponse)
def change_password(
    data: ChangePasswordRequest,
    request: Request,
    response: Response,
    current_user: User = Depends(require_auth),
    session: Session = Depends(get_session),
):
    """
    Change current user's password.

    Requires current password for verification. Wrong current passwords
    count against the per-account limit, so a stolen session can't be used
    to brute-force the password.

    Signs the user out of every other session (their access tokens stop
    working right away, not when they expire) and forgets other known
    browsers. This session stays signed in: it keeps its refresh token and
    gets a new access token (body + cookie) and device token.
    """
    if not current_user.has_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This account signs in with single sign-on; its password is managed by the provider",
        )
    _, account_limit, window = _throttle_settings(session)
    buckets = [(f"change_password:{current_user.id}", account_limit)]
    login_throttle.check(buckets, window)

    # Verify current password
    if not auth_svc.verify_password(data.current_password, current_user.password_hash):
        login_throttle.record_failure(buckets, window)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    revoked = auth_svc.change_password(
        session,
        current_user,
        data.new_password,
        keep_refresh_token=request.cookies.get("refresh_token"),
    )
    login_throttle.clear(buckets[0][0])

    logger.info("Password changed for user %s, %s other session(s) signed out", current_user.username, revoked)

    access_token = auth_svc.create_access_token(current_user)
    _set_access_cookie(response, access_token)
    _set_device_cookie(response, auth_svc.create_device_token(current_user.id))

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=config.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
