"""
What a failed sign-in may cost the server, and bcrypt's 72-byte limit.

The sign-in form is public: whatever it's sent must neither grow memory
(the throttle keeps a bucket per name and per IP for the whole window)
nor reach bcrypt in a shape it raises on.
"""
from __future__ import annotations

import bcrypt
import pytest
from pydantic import ValidationError

from backend import config
from backend.db import SessionLocal
from backend.schemas.auth import ChangePasswordRequest, LoginRequest, RegisterRequest
from backend.services import auth as auth_svc
from backend.services import login_throttle


@pytest.fixture
def fresh_throttle(monkeypatch):
    """The throttle's buckets, empty and private to the test."""
    monkeypatch.setattr(login_throttle, "_failures", {})
    return login_throttle._failures


# ============================================================================
# THROTTLE
# ============================================================================

def test_account_buckets_are_keyed_by_a_hash_of_the_name():
    huge = "a" * 1_000_000
    key = login_throttle.login_account_key(huge)
    assert huge[:100] not in key
    assert len(key) == len(login_throttle.login_account_key("admin"))
    # The name as typed, lowercased: "Admin" and "admin" share a bucket
    assert login_throttle.login_account_key("Admin") == login_throttle.login_account_key("admin")
    assert login_throttle.login_account_key("admin") != login_throttle.login_account_key("admin2")


def test_ipv6_addresses_share_their_64_bucket():
    # One connection is handed a whole /64: cycling through it mustn't make a bucket per attempt
    assert login_throttle.ip_key("2001:db8:1:2::1") == login_throttle.ip_key("2001:db8:1:2:ffff:ffff:ffff:ffff")
    assert login_throttle.ip_key("2001:db8:1:2::1") == "2001:db8:1:2::/64"
    assert login_throttle.ip_key("2001:db8:1:3::1") != login_throttle.ip_key("2001:db8:1:2::1")


def test_ipv4_addresses_are_counted_one_by_one():
    assert login_throttle.ip_key("203.0.113.7") == "203.0.113.7"
    # Also when written IPv4-mapped, as a dual-stack socket reports it
    assert login_throttle.ip_key("::ffff:203.0.113.7") == "203.0.113.7"
    assert login_throttle.ip_key("unknown") == "unknown"


def test_a_bucket_keeps_no_more_failures_than_its_limit(fresh_throttle):
    for _ in range(50):
        login_throttle.record_failure([("k", 3)], window_seconds=60)
    assert len(fresh_throttle["k"]) == 3


def test_a_full_bucket_refuses_until_its_failures_expire(fresh_throttle):
    login_throttle.record_failure([("k", 2)], window_seconds=60)
    login_throttle.check([("k", 2)], window_seconds=60)
    login_throttle.record_failure([("k", 2)], window_seconds=60)
    with pytest.raises(login_throttle.TooManyAttempts) as refused:
        login_throttle.check([("k", 2)], window_seconds=60)
    assert 0 < refused.value.retry_after <= 60
    # A limit of 0 turns the bucket off
    login_throttle.check([("k", 0)], window_seconds=60)
    login_throttle.record_failure([("off", 0)], window_seconds=60)
    assert "off" not in fresh_throttle


def test_expired_buckets_are_swept_once_there_are_many(fresh_throttle, monkeypatch):
    monkeypatch.setattr(login_throttle, "_SWEEP_THRESHOLD", 10)
    for n in range(10):
        login_throttle.record_failure([(f"name-{n}", 5)], window_seconds=3600)
    assert len(fresh_throttle) == 10
    # Past the threshold, a window of 0 has every bucket expired, this one included
    login_throttle.record_failure([("one-more", 5)], window_seconds=0)
    assert fresh_throttle == {}


def test_a_failed_sign_in_keeps_neither_the_name_nor_the_password(client, fresh_throttle):
    name = "someone-" + "x" * 100_000
    response = client.post("/api/auth/login", json={"username": name, "password": "p" * 100_000})
    # Wrong, not invalid: a 422 would say something about the account
    assert response.status_code == 401
    assert len(fresh_throttle) == 2
    assert all(len(key) < 100 for key in fresh_throttle)


# ============================================================================
# BCRYPT'S 72 BYTES
# ============================================================================

def test_new_passwords_are_at_most_72_bytes():
    RegisterRequest(username="new-user", password="a" * 72)
    ChangePasswordRequest(current_password="x", new_password="é" * 36)
    for too_long in ("a" * 73, "é" * 37, "🎵" * 19):
        with pytest.raises(ValidationError, match="at most 72 bytes"):
            RegisterRequest(username="new-user", password=too_long)
        with pytest.raises(ValidationError, match="at most 72 bytes"):
            ChangePasswordRequest(current_password="x", new_password=too_long)


def test_new_passwords_are_at_least_8_characters():
    with pytest.raises(ValidationError):
        RegisterRequest(username="new-user", password="1234567")


def test_sign_in_takes_passwords_of_any_length():
    # A password over 72 bytes is a wrong one, not a malformed request
    LoginRequest(username="x" * 1000, password="p" * 1000)


def test_a_password_set_before_bcrypt_5_still_signs_in(client):
    """
    bcrypt 4 (this app until September 2026) hashed the first 72 bytes of
    a longer password; bcrypt 5 raises on one instead of ignoring the rest.
    """
    typed = "correct horse battery staple " * 4  # 116 bytes
    with SessionLocal() as session:
        user = auth_svc.create_user(session, "bcrypt4-user", "temporary-pass", role=config.ROLE_MEMBER)
        user.password_hash = bcrypt.hashpw(typed.encode()[:72], bcrypt.gensalt(rounds=4)).decode()
        session.commit()

    assert auth_svc.verify_password(typed, user.password_hash)
    assert not auth_svc.verify_password(typed[:71], user.password_hash)

    response = client.post("/api/auth/login", json={"username": "bcrypt4-user", "password": typed})
    assert response.status_code == 200
    wrong = client.post("/api/auth/login", json={"username": "bcrypt4-user", "password": "x" * 200})
    assert wrong.status_code == 401

