"""Unit tests for auth_service: password hashing and JWT."""
import time

import pytest

from app.services.auth_service import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
import uuid
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def test_hash_password_returns_string():
    hashed = hash_password("mysecretpassword")
    assert isinstance(hashed, str)
    assert hashed != "mysecretpassword"


def test_verify_password_correct():
    hashed = hash_password("correctpassword")
    assert verify_password("correctpassword", hashed) is True


def test_verify_password_wrong():
    hashed = hash_password("correctpassword")
    assert verify_password("wrongpassword", hashed) is False


def test_hash_is_different_each_time():
    hashed1 = hash_password("same")
    hashed2 = hash_password("same")
    assert hashed1 != hashed2  # bcrypt uses random salt


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------

def test_create_and_decode_token():
    user_id = uuid.uuid4()
    token = create_access_token(user_id, "developer")
    payload = decode_access_token(token)
    assert payload["sub"] == str(user_id)
    assert payload["role"] == "developer"


def test_decode_invalid_token_raises_401():
    with pytest.raises(HTTPException) as exc:
        decode_access_token("not.a.valid.token")
    assert exc.value.status_code == 401


def test_decode_expired_token_raises_401(monkeypatch):
    import app.services.auth_service as svc
    # Temporarily set expiration to 0 hours
    monkeypatch.setattr(svc.settings, "JWT_EXPIRATION_HOURS", 0)
    # Wait a tiny bit to ensure expiry
    import jwt as pyjwt
    from datetime import datetime, timezone, timedelta
    payload = {"sub": str(uuid.uuid4()), "role": "user", "exp": datetime.now(timezone.utc) - timedelta(seconds=1)}
    expired_token = pyjwt.encode(payload, svc.settings.JWT_SECRET, algorithm=svc.settings.JWT_ALGORITHM)
    with pytest.raises(HTTPException) as exc:
        decode_access_token(expired_token)
    assert exc.value.status_code == 401
