# backend/settings.py
"""
Application settings management.
Handles default settings and database CRUD operations.
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .models import Setting
from .time_utils import now_utc

logger = logging.getLogger("settings")


# Default settings with descriptions
DEFAULT_SETTINGS = {
    # Scheduler settings
    # Schedules (backend/schedules.py): every N hours/days ("unit"), or at a
    # fixed time on chosen days of the week. Their *_last_run companions
    # record the last fixed run done, so one isn't repeated or caught up.
    "scheduler.artist_sync": {
        # A quiet hour, three times a week: plenty to catch new releases,
        # which mostly land on Fridays
        "value": {"mode": "fixed", "time": "02:00", "days": ["tue", "thu", "sat"]},
        "type": "schedule",
        "unit": "hours",
        "min": 1,
        "description": "When followed artists are checked for new releases",
    },
    "scheduler.artist_sync_last_run": {
        "value": "",
        "type": "string",
        "internal": True,
        "description": "Last fixed-time artist sync run",
    },
    "scheduler.chart_sync": {
        # YouTube Music publishes its charts weekly, so syncing more often
        # than once a week mostly fetches the same chart again.
        "value": {"mode": "fixed", "time": "04:00", "days": ["mon"]},
        "type": "schedule",
        "unit": "days",
        "min": 1,
        "description": "When followed charts are re-fetched (YouTube Music updates its charts weekly)",
    },
    "scheduler.chart_sync_last_run": {
        "value": "",
        "type": "string",
        "internal": True,
        "description": "Last fixed-time chart sync run",
    },
    "scheduler.playlist_sync": {
        # Daily: playlists change more often than artists release. Between
        # the artist sync (02:00) and the chart sync (04:00).
        "value": {"mode": "fixed", "time": "03:00", "days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]},
        "type": "schedule",
        "unit": "hours",
        "min": 1,
        "description": "When followed playlists are rescanned for new songs",
    },
    "scheduler.playlist_sync_last_run": {
        "value": "",
        "type": "string",
        "internal": True,
        "description": "Last fixed-time playlist sync run",
    },
    "scheduler.lyrics_retry": {
        "value": {"mode": "interval", "every": 24},
        "type": "schedule",
        "unit": "hours",
        "min": 1,
        "description": "When tracks with missing or plain lyrics are retried",
    },
    "scheduler.lyrics_retry_last_run": {
        "value": "",
        "type": "string",
        "internal": True,
        "description": "Last fixed-time lyrics retry run",
    },
    "scheduler.job_cleanup_days": {
        "value": 3,
        "type": "int",
        "min": 1,
        "description": "Days to keep finished jobs (done, failed, cancelled)",
    },

    # Registration settings
    "auth.registration_enabled": {
        "value": False,
        "type": "bool",
        "requires": "password_login",
        "description": "Allow public user registration",
    },

    # Failed password throttling (services/login_throttle.py). Read on every
    # attempt, so changes apply immediately.
    "auth.login_max_failures_per_ip": {
        "value": 10,
        "type": "int",
        "min": 0,
        "requires": "password_login",
        "description": "Failed sign-ins allowed from one IP address per window before it is blocked (set to 0 to turn this check off)",
    },
    "auth.login_max_failures_per_account": {
        # Browsers that already signed in to the account get their own
        # allowance of this size, so someone hammering the account (e.g. the
        # default "admin") can't lock its owner out of their usual browser.
        "value": 5,
        "type": "int",
        "min": 0,
        "requires": "password_login",
        "description": "Failed sign-ins allowed per account per window before it is blocked for new browsers (set to 0 to turn this check off)",
    },
    "auth.login_failure_window_minutes": {
        "value": 15,
        "type": "int",
        "min": 1,
        "requires": "password_login",
        "description": "Minutes failed sign-ins are remembered; a blocked IP or account is released as they expire",
    },

    # Single sign-on (services/oidc.py). Who gets in and with which role;
    # how sign-in works and which provider is trusted are env-only.
    "auth.oidc_signup_enabled": {
        "value": True,
        "type": "bool",
        "requires": "oidc",
        "description": "Create an account on the first single sign-on of someone without one (otherwise they are refused)",
    },
    "auth.oidc_default_role": {
        # No administrator: admins come from OIDC_ADMIN_GROUP, the CLI or the panel
        "value": "visitor",
        "type": "string",
        "requires": "oidc",
        "description": "Role of accounts created by single sign-on (and of everyone outside the configured groups)",
        "allowed_values": [
            {"value": "visitor", "label": "Visitor"},
            {"value": "member", "label": "Member"},
        ],
    },

    # Download settings
    "download.max_concurrent": {
        # How many of the download worker processes actually take jobs; the
        # rest idle. Every parallel stream from one IP raises the odds of
        # YouTube rate-limiting or bot-checking, so the default is one and
        # the ceiling is the number of processes supervisord started
        # (config.DOWNLOAD_WORKERS). Workers re-read this on every poll, so
        # a change in the admin panel applies within seconds, no restart.
        "value": 1,
        "type": "int",
        "min": 1,
        "max": lambda: config.DOWNLOAD_WORKERS,
        "description": "Maximum concurrent downloads",
    },
    "download.rate_limit_pause_minutes": {
        # When a download still hits YouTube's rate limit after a cookie
        # reset, *all* download workers stop taking jobs for this long
        # (jobs.gate.pause_downloads) -- with several workers, the others
        # carrying on is exactly how a soft limit turns into a ban.
        "value": 10,
        "type": "int",
        "min": 1,
        "description": "Minutes to pause all downloads after hitting YouTube's rate limit",
    },
    "download.pause_streak": {
        # How many rate-limit pauses in a row without a successful download
        # in between; each one doubles the pause (jobs.gate.pause_downloads).
        "value": 0,
        "type": "int",
        "min": 0,
        "internal": True,
        "description": "Consecutive rate-limit pauses (set automatically)",
    },
    "download.paused_until": {
        # ISO timestamp set by jobs.gate.pause_downloads; empty when not
        # paused. Bookkeeping, not a preference: hidden from the settings UI
        # (internal=True), surfaced read-only via /api/jobs/stats/summary.
        "value": "",
        "type": "string",
        "internal": True,
        "description": "Downloads are paused until this time (set automatically on rate limit)",
    },

    # Feature flags
    "features.lyrics_enabled": {
        "value": True,
        "type": "bool",
        "description": "Enable automatic lyrics download with LRCLIB",
    },
    "features.synced_lyrics_only": {
        "value": True,
        "type": "bool",
        "description": "Only keep synced lyrics (reject plain/unsynced lyrics)",
    },
    "features.genres_enabled": {
        "value": True,
        "type": "bool",
        "description": "Look up album and artist genres on MusicBrainz and Deezer",
    },
    "features.charts_enabled": {
        "value": True,
        "type": "bool",
        "description": "Enable charts import feature",
    },

    # YTMusic API
    "ytmusic.language": {
        "value": "en",
        "type": "string",
        "description": "Language code for localized YTMusic responses (artist bios, album descriptions, etc.)",
        "allowed_values": [
            {"value": "ar", "label": "Arabic"},
            {"value": "de", "label": "German"},
            {"value": "en", "label": "English"},
            {"value": "es", "label": "Spanish"},
            {"value": "fr", "label": "French"},
            {"value": "hi", "label": "Hindi"},
            {"value": "it", "label": "Italian"},
            {"value": "ja", "label": "Japanese"},
            {"value": "ko", "label": "Korean"},
            {"value": "nl", "label": "Dutch"},
            {"value": "pt", "label": "Portuguese"},
            {"value": "ru", "label": "Russian"},
            {"value": "tr", "label": "Turkish"},
            {"value": "ur", "label": "Urdu"},
            {"value": "zh_CN", "label": "Chinese (Mainland)"},
            {"value": "zh_TW", "label": "Chinese (Taiwan)"},
        ],
    },
}


def _spec(key: str) -> Dict[str, Any]:
    """The declaration of a setting ({} for unknown keys)."""
    return DEFAULT_SETTINGS.get(key, {})


def get_allowed_values(key: str) -> Optional[List[Dict[str, str]]]:
    """Return the allowed {value, label} options for a setting key, or None if unconstrained."""
    values = _spec(key).get("allowed_values")
    return list(values) if values else None


def get_default_value(key: str) -> Any:
    """Return the built-in default value for a setting key, or None if it has none."""
    return _spec(key).get("value")


def get_min_value(key: str) -> Optional[int]:
    """Return the lower bound for an int setting, or None if unconstrained."""
    return _spec(key).get("min")


def get_unit(key: str) -> Optional[str]:
    """The unit of a schedule setting's interval ("hours" or "days")."""
    return _spec(key).get("unit")


def get_max_value(key: str) -> Optional[int]:
    """
    Return the upper bound for an int setting, or None if unconstrained.
    A bound may be declared as a callable for values only known at runtime
    (e.g. how many worker processes this container was started with).
    """
    maximum = _spec(key).get("max")
    return maximum() if callable(maximum) else maximum


def is_applicable(key: str) -> bool:
    """
    False for settings the sign-in configuration makes moot (password sign-in
    off, or single sign-on not configured): hidden from the settings panel.
    They keep their value, and still travel in backups.
    """
    requires = _spec(key).get("requires")
    if requires == "password_login":
        return config.PASSWORD_LOGIN_ENABLED
    if requires == "oidc":
        return config.OIDC_ENABLED
    return True


def is_internal(key: str) -> bool:
    """True for settings that are app bookkeeping rather than user preferences."""
    return bool(_spec(key).get("internal"))


def is_user_setting(key: str) -> bool:
    """A known setting people may change (admin panel, CLI, backup import): not app bookkeeping."""
    return key in DEFAULT_SETTINGS and not is_internal(key)


def validate_value(key: str, setting_type: str, value: Any) -> Any:
    """
    Check `value` against the constraints declared for `key` and return it
    coerced to the setting's type. Raises ValueError on a bad value.
    """
    allowed = get_allowed_values(key)
    if allowed is not None:
        valid = [opt["value"] for opt in allowed]
        if str(value) not in valid:
            raise ValueError(
                f"Invalid value for {key}: must be one of {', '.join(valid)}"
            )

    if setting_type == "int":
        if isinstance(value, bool) or value is None:
            raise ValueError(f"Invalid value for {key}: must be an integer")
        if isinstance(value, float) and not value.is_integer():
            raise ValueError(f"Invalid value for {key}: must be an integer")
        try:
            value = int(value)
        except (TypeError, ValueError):
            raise ValueError(f"Invalid value for {key}: must be an integer")
        minimum = get_min_value(key)
        if minimum is not None and value < minimum:
            raise ValueError(f"Invalid value for {key}: must be at least {minimum}")
        maximum = get_max_value(key)
        if maximum is not None and value > maximum:
            raise ValueError(f"Invalid value for {key}: must be at most {maximum}")

    elif setting_type == "bool":
        if not isinstance(value, bool):
            raise ValueError(f"Invalid value for {key}: must be true or false")

    elif setting_type == "schedule":
        from . import schedules
        try:
            value = schedules.validate(value, get_min_value(key) or 1, get_max_value(key))
        except ValueError as e:
            raise ValueError(f"Invalid value for {key}: {e}")

    return value


def ensure_defaults(session: Session) -> None:
    """Create the rows of declared settings that don't have one yet. Commits."""
    for key, spec in DEFAULT_SETTINGS.items():
        if session.get(Setting, key) is None:
            setting = Setting(key=key, type=spec["type"], description=spec["description"])
            setting.set_value(spec["value"])
            session.add(setting)
            logger.debug("Created default setting: %s = %r", key, spec["value"])
    session.commit()


def get_setting(session: Session, key: str, default: Any = None) -> Any:
    """
    A setting's typed value (int, bool, str, schedule dict...). A declared
    setting without a row yet gives its built-in default; an unknown key
    gives `default`.
    """
    setting = session.get(Setting, key)
    if setting is None:
        return _spec(key).get("value", default)
    return setting.get_typed_value()


def feature_enabled(session: Session, name: str) -> bool:
    """Whether the features.<name>_enabled flag is on (charts, lyrics, genres)."""
    return bool(get_setting(session, f"features.{name}_enabled"))


def set_setting(
    session: Session,
    key: str,
    value: Any,
    user_id: Optional[int] = None,
    commit: bool = True,
) -> Setting:
    """
    Validate and store a declared setting. Raises ValueError for an unknown
    key or a bad value. Callers batching several changes in one transaction
    pass commit=False.
    """
    spec = _spec(key)
    if not spec:
        raise ValueError(f"Unknown setting: {key}")
    value = validate_value(key, spec["type"], value)

    setting = session.get(Setting, key)
    if setting is None:
        setting = Setting(key=key, type=spec["type"], description=spec["description"])
        session.add(setting)
    setting.set_value(value)
    setting.updated_at = now_utc()
    setting.updated_by = user_id
    if commit:
        session.commit()

    logger.info("Setting updated: %s = %r (by user %s)", key, value, user_id)
    return setting


def get_all_settings(session: Session) -> List[Dict[str, Any]]:
    """
    The settings as dicts, for the settings panel: internal bookkeeping keys
    and settings moot under the current sign-in configuration left out.
    """
    settings = session.execute(select(Setting)).scalars().all()
    # In the order they're declared above, which keeps related settings
    # together (each schedule next to the others); unknown keys last
    declared = {key: i for i, key in enumerate(DEFAULT_SETTINGS)}
    settings = sorted(settings, key=lambda s: (declared.get(s.key, len(declared)), s.key))
    return [
        s.to_dict() for s in settings
        if not is_internal(s.key) and is_applicable(s.key)
    ]
