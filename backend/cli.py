# backend/cli.py
"""
Recovery / administration CLI, for whoever runs the container:

    docker compose exec ytmusicdownloader python -m backend.cli <command>

Meant for when nobody can (or should) use the admin panel: forgotten admin
password, hijacked admin account, sign-in locked by someone guessing
passwords. See README "Recovering access".

Commands:
- list-users
- create-user <user> --role <role> [--generate]
- reset-password <user> [--generate]
- set-role <user> <role>
- activate <user> / deactivate <user>
- deactivate-all [--except <user>]
- get-setting [key] / set-setting <key> <value>

Passwords are prompted for (hidden, twice) or generated, never taken as
arguments: those end up in shell history and `ps`.
"""
from __future__ import annotations
import argparse
import getpass
import json
import os
import sys
from pathlib import Path

# Same as config.CONFIG_DIR. Can't import config to get it yet: importing
# it (or backend.db) may create files, which must not happen as root.
_CONFIG_DIR = Path("/config")


def _drop_root() -> None:
    """
    `docker exec` runs as root by default, while the app runs as PUID:PGID
    (deploy/entrypoint.sh chowns /config to it on every start). SQLite in
    WAL mode creates db.sqlite-wal/-shm on demand; created by root, the web
    process could no longer write to the database. So switch to the owner
    of /config before anything touches it.
    """
    if os.geteuid() != 0:
        return
    try:
        st = _CONFIG_DIR.stat()
    except FileNotFoundError:
        return
    if st.st_uid == 0:
        return
    os.setgroups([])
    os.setgid(st.st_gid)
    os.setuid(st.st_uid)


class CliError(Exception):
    """Expected failure: printed as "error: ..." with exit code 1."""


# ============================================================================
# HELPERS
# ============================================================================

def _session():
    from .db import get_session
    return next(get_session())


def _get_user(session, username: str):
    from .services import auth as auth_svc
    user = auth_svc.get_user_by_username(session, username)
    if not user:
        raise CliError(f"no user named '{username}' (see list-users)")
    return user


def _validation_message(e) -> str:
    return "; ".join(f"{err['loc'][-1]}: {err['msg']}" for err in e.errors())


def _check_password(password: str) -> None:
    """Same rules as the API (ChangePasswordRequest.new_password)."""
    from pydantic import ValidationError
    from .schemas import ChangePasswordRequest
    try:
        ChangePasswordRequest(current_password="", new_password=password)
    except ValidationError as e:
        raise CliError(_validation_message(e))


def _new_password(generate: bool) -> str:
    from .services import auth as auth_svc
    if generate:
        return auth_svc.generate_temporary_password()
    password = getpass.getpass("New password: ")
    _check_password(password)
    if getpass.getpass("Confirm password: ") != password:
        raise CliError("passwords do not match")
    return password


def _warn_if_no_admin(session) -> None:
    from sqlalchemy import func, select
    from .models import User
    from . import config
    count = session.execute(
        select(func.count()).select_from(User).where(
            User.role == config.ROLE_ADMINISTRATOR, User.is_active.is_(True)
        )
    ).scalar()
    if not count:
        print(
            "warning: no active administrator left. Create one with "
            "create-user <name> --role administrator, or reset-password an existing one.",
            file=sys.stderr,
        )


# ============================================================================
# COMMANDS
# ============================================================================

def cmd_list_users(args) -> None:
    from sqlalchemy import select
    from .models import User
    session = _session()
    users = session.execute(select(User).order_by(User.id)).scalars().all()
    rows = [(u.username, u.role, "active" if u.is_active else "inactive") for u in users]
    widths = [max(len(r[i]) for r in rows + [("USERNAME", "ROLE", "STATUS")]) for i in range(3)]
    for row in [("USERNAME", "ROLE", "STATUS")] + rows:
        print("  ".join(col.ljust(w) for col, w in zip(row, widths)).rstrip())


def cmd_create_user(args) -> None:
    from pydantic import ValidationError
    from .schemas import CreateUserRequest
    from .services import auth as auth_svc
    session = _session()
    if auth_svc.get_user_by_username(session, args.username):
        raise CliError(f"user '{args.username}' already exists")
    # Check the username before asking for a password (placeholder password)
    try:
        CreateUserRequest(username=args.username, password="x" * 8, role=args.role)
    except ValidationError as e:
        raise CliError(_validation_message(e))
    password = _new_password(args.generate)
    data = CreateUserRequest(username=args.username, password=password, role=args.role)
    auth_svc.create_user(
        session, data.username, data.password, data.role, must_change_password=args.generate
    )
    if args.generate:
        print(f"Created '{data.username}' ({data.role}). Temporary password: {password}")
        print("They will have to choose a new one at next sign-in.")
    else:
        print(f"Created '{data.username}' ({data.role}).")


def cmd_reset_password(args) -> None:
    from .services import auth as auth_svc
    session = _session()
    user = _get_user(session, args.username)
    password = _new_password(args.generate)
    was_active = user.is_active
    # Reactivate too: a hijacked admin may have deactivated the account
    user.is_active = True
    revoked = auth_svc.change_password(session, user, password, must_change_password=args.generate)
    details = [f"{revoked} session(s) signed out"]
    if not was_active:
        details.insert(0, "account reactivated")
    print(f"Password reset for '{user.username}': {', '.join(details)}.")
    if args.generate:
        print(f"Temporary password: {password}")
        print("It will have to be changed at next sign-in.")


def cmd_set_role(args) -> None:
    from .services import admin as admin_svc
    session = _session()
    user = _get_user(session, args.username)
    try:
        admin_svc.update_user_role(session, user.id, args.role)
    except ValueError as e:
        raise CliError(str(e))
    print(f"'{user.username}' is now {args.role}.")
    _warn_if_no_admin(session)


def cmd_activate(args) -> None:
    from .services import admin as admin_svc
    session = _session()
    user = _get_user(session, args.username)
    admin_svc.activate_user(session, user.id)
    print(f"Activated '{user.username}'.")


def cmd_deactivate(args) -> None:
    from .services import admin as admin_svc
    session = _session()
    user = _get_user(session, args.username)
    admin_svc.deactivate_user(session, user.id)
    print(f"Deactivated '{user.username}' and signed out their sessions.")
    _warn_if_no_admin(session)


def cmd_deactivate_all(args) -> None:
    from sqlalchemy import select
    from .models import User
    from .services import admin as admin_svc
    from .services import auth as auth_svc
    session = _session()
    keep = _get_user(session, args.keep) if args.keep else None
    others = [
        u for u in session.execute(select(User).where(User.is_active.is_(True))).scalars().all()
        if keep is None or u.id != keep.id
    ]
    for user in others:
        admin_svc.deactivate_user(session, user.id)
    names = ", ".join(u.username for u in others) or "none"
    print(f"Deactivated {len(others)} account(s) and signed out their sessions: {names}")
    if keep:
        # Its sessions too: the attacker may be using this very account
        revoked = auth_svc.revoke_sessions(session, keep)
        session.commit()
        print(f"Kept '{keep.username}', signed out its {revoked} session(s). Consider reset-password next.")
    _warn_if_no_admin(session)


def cmd_get_setting(args) -> None:
    from . import settings as settings_module
    session = _session()
    if args.key:
        if args.key not in settings_module.DEFAULT_SETTINGS or settings_module.is_internal(args.key):
            raise CliError(f"unknown setting '{args.key}' (run get-setting without a key to list them)")
        print(json.dumps(settings_module.get_setting(session, args.key)))
        return
    for s in settings_module.get_all_settings(session):
        print(f"{s['key']} = {json.dumps(s['value'])}")


def _parse_setting_value(setting_type: str, raw: str):
    if setting_type == "int":
        try:
            return int(raw)
        except ValueError:
            raise CliError(f"'{raw}' is not a whole number")
    if setting_type == "bool":
        lowered = raw.strip().lower()
        if lowered in ("1", "true", "yes", "on"):
            return True
        if lowered in ("0", "false", "no", "off"):
            return False
        raise CliError(f"'{raw}' is not true/false")
    if setting_type == "json":
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            raise CliError(f"invalid JSON: {e}")
    return raw


def cmd_set_setting(args) -> None:
    from . import settings as settings_module
    if args.key not in settings_module.DEFAULT_SETTINGS or settings_module.is_internal(args.key):
        raise CliError(f"unknown setting '{args.key}' (run get-setting to list them)")
    value = _parse_setting_value(settings_module.DEFAULT_SETTINGS[args.key]["type"], args.value)
    session = _session()
    try:
        settings_module.set_setting(session, args.key, value)
    except ValueError as e:
        raise CliError(str(e))
    print(f"{args.key} = {json.dumps(settings_module.get_setting(session, args.key))}")


# ============================================================================
# ENTRY POINT
# ============================================================================

ROLES = ("administrator", "member", "visitor")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m backend.cli",
        description="YTMusicDownloader recovery and administration commands.",
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    p = sub.add_parser("list-users", help="list accounts with their role and status")
    p.set_defaults(func=cmd_list_users)

    p = sub.add_parser("create-user", help="create an account")
    p.add_argument("username")
    p.add_argument("--role", required=True, choices=ROLES)
    p.add_argument("--generate", action="store_true",
                   help="generate a temporary password (to be changed at first sign-in) instead of prompting")
    p.set_defaults(func=cmd_create_user)

    p = sub.add_parser("reset-password", help="set a new password, reactivate the account and sign it out everywhere")
    p.add_argument("username")
    p.add_argument("--generate", action="store_true",
                   help="generate a temporary password (to be changed at next sign-in) instead of prompting")
    p.set_defaults(func=cmd_reset_password)

    p = sub.add_parser("set-role", help="change an account's role")
    p.add_argument("username")
    p.add_argument("role", choices=ROLES)
    p.set_defaults(func=cmd_set_role)

    p = sub.add_parser("activate", help="reactivate an account")
    p.add_argument("username")
    p.set_defaults(func=cmd_activate)

    p = sub.add_parser("deactivate", help="deactivate an account and sign it out")
    p.add_argument("username")
    p.set_defaults(func=cmd_deactivate)

    p = sub.add_parser("deactivate-all", help="lockdown: deactivate every account and sign everyone out")
    p.add_argument("--except", dest="keep", metavar="USERNAME",
                   help="keep this account active (its sessions are still signed out)")
    p.set_defaults(func=cmd_deactivate_all)

    p = sub.add_parser("get-setting", help="show one setting, or all of them")
    p.add_argument("key", nargs="?")
    p.set_defaults(func=cmd_get_setting)

    p = sub.add_parser("set-setting", help="change a setting (same validation as the admin panel)")
    p.add_argument("key")
    p.add_argument("value")
    p.set_defaults(func=cmd_set_setting)

    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    _drop_root()
    from . import config
    if not config.DB_PATH.exists():
        print(f"error: no database at {config.DB_PATH}, start the app once first", file=sys.stderr)
        return 1
    try:
        args.func(args)
    except CliError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print(file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
