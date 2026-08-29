#!/usr/bin/python
# -*- coding:utf-8 -*-

from datetime import timedelta

import pytest

import app.core.security.jwt_auth as jwt_module
from app.core.security.jwt_auth import JWTAuth


@pytest.fixture
def jwt_auth() -> JWTAuth:
    return JWTAuth(
        secret_key="test-secret-key-with-sufficient-length",
        expire_days=1,
        algorithm="HS256",
    )


def test_valid_token_can_be_verified_and_decoded(jwt_auth):
    token = jwt_auth.create_token("alice", token_type="refresh")

    assert jwt_auth.verify_token(token) == "alice"
    assert jwt_auth.decode_token(token, verify=True)["type"] == "refresh"


def test_expected_invalid_token_errors_remain_authentication_failures(jwt_auth):
    assert jwt_auth.verify_token("not-a-token") is None
    assert jwt_auth.decode_token("not-a-token", verify=True) is None
    assert jwt_auth.get_token_info("not-a-token") == {
        "error": "Invalid token",
        "valid": False,
    }


def test_expired_token_remains_an_expected_authentication_failure(jwt_auth):
    token = jwt_auth.create_token(
        "alice",
        expires_delta=timedelta(seconds=-1),
    )

    assert jwt_auth.verify_token(token) is None
    assert jwt_auth.decode_token(token, verify=True) is None


@pytest.mark.parametrize("method_name", ["verify_token", "decode_token", "get_token_info"])
def test_unexpected_decode_failure_is_not_misreported_as_invalid_token(
    monkeypatch,
    jwt_auth,
    method_name,
):
    def broken_decode(*args, **kwargs):
        raise RuntimeError("configuration failure")

    monkeypatch.setattr(jwt_module.jwt, "decode", broken_decode)

    with pytest.raises(RuntimeError, match="configuration failure"):
        getattr(jwt_auth, method_name)("token")


def test_token_creation_does_not_intercept_unexpected_encoder_failure(
    monkeypatch,
    jwt_auth,
):
    def broken_encode(*args, **kwargs):
        raise RuntimeError("encoder configuration failure")

    monkeypatch.setattr(jwt_module.jwt, "encode", broken_encode)

    with pytest.raises(RuntimeError, match="encoder configuration failure"):
        jwt_auth.create_token("alice")


def test_invalid_timestamp_is_handled_without_exposing_raw_error(
    monkeypatch,
    jwt_auth,
):
    monkeypatch.setattr(
        jwt_module.jwt,
        "decode",
        lambda *args, **kwargs: {
            "sub": "alice",
            "exp": "invalid-timestamp",
            "iat": 1,
        },
    )

    assert jwt_auth.get_token_info("token") == {
        "error": "Invalid token",
        "valid": False,
    }
