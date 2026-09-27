import pytest

from app.core.security import (
    TokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_password_is_salted_and_verifiable() -> None:
    h1 = hash_password("correct horse")
    h2 = hash_password("correct horse")

    assert h1 != h2  # random salt per hash
    assert h1.startswith("scrypt$")
    assert verify_password("correct horse", h1)
    assert verify_password("correct horse", h2)


def test_verify_password_rejects_wrong_password() -> None:
    h = hash_password("s3cret-value")

    assert not verify_password("wrong", h)


def test_verify_password_handles_malformed_hash() -> None:
    assert not verify_password("x", "not-a-real-hash")
    assert not verify_password("x", "bcrypt$abc")


def test_token_roundtrip() -> None:
    token = create_access_token(subject="42")
    payload = decode_access_token(token)

    assert payload["sub"] == "42"
    assert payload["exp"] > payload["iat"]


def test_expired_token_is_rejected() -> None:
    token = create_access_token(subject="42", expires_in=-1)

    with pytest.raises(TokenError):
        decode_access_token(token)


def test_tampered_token_is_rejected() -> None:
    token = create_access_token(subject="42")
    header, payload, sig = token.split(".")
    tampered = f"{header}.{payload}.{sig[:-2]}xy"

    with pytest.raises(TokenError):
        decode_access_token(tampered)


def test_malformed_token_is_rejected() -> None:
    with pytest.raises(TokenError):
        decode_access_token("not.a.jwt.at.all")
    with pytest.raises(TokenError):
        decode_access_token("garbage")
