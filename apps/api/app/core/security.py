"""Password hashing and signed access tokens.

Implemented with the Python standard library only:

* Passwords are hashed with ``hashlib.scrypt`` (a memory-hard KDF) using a
  random per-password salt. The stored value is a self-describing string
  ``scrypt$n$r$p$<salt_b64>$<hash_b64>`` so parameters can evolve over time.
* Access tokens are compact JWTs signed with HMAC-SHA256 (the JWT ``HS256``
  algorithm), produced and verified with ``hmac``/``hashlib``.

This keeps the project fully testable without external dependencies. The module
is intentionally the single place that touches crypto, so it can later be
swapped for ``passlib[bcrypt]`` / ``PyJWT`` without changing callers.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

from app.core.config import get_settings

# scrypt parameters (RFC 7914). n must be a power of two; these are a reasonable
# interactive-login cost that runs in well under a second.
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32
_SALT_BYTES = 16

_JWT_ALG = "HS256"


# --------------------------------------------------------------------------- #
# base64url helpers (no padding, per JWT spec)
# --------------------------------------------------------------------------- #
def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


# --------------------------------------------------------------------------- #
# Passwords
# --------------------------------------------------------------------------- #
def hash_password(password: str) -> str:
    """Return a self-describing scrypt hash string for ``password``."""
    salt = secrets.token_bytes(_SALT_BYTES)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return "$".join(
        [
            "scrypt",
            str(_SCRYPT_N),
            str(_SCRYPT_R),
            str(_SCRYPT_P),
            _b64url_encode(salt),
            _b64url_encode(derived),
        ]
    )


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check of ``password`` against a stored scrypt hash."""
    try:
        scheme, n_str, r_str, p_str, salt_b64, hash_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        n, r, p = int(n_str), int(r_str), int(p_str)
        salt = _b64url_decode(salt_b64)
        expected = _b64url_decode(hash_b64)
    except (ValueError, TypeError):
        return False

    candidate = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        dklen=len(expected),
    )
    return hmac.compare_digest(candidate, expected)


# --------------------------------------------------------------------------- #
# Access tokens (JWT HS256)
# --------------------------------------------------------------------------- #
def _sign(signing_input: bytes) -> bytes:
    secret = get_settings().secret_key.encode("utf-8")
    return hmac.new(secret, signing_input, hashlib.sha256).digest()


def create_access_token(subject: str, expires_in: int | None = None) -> str:
    """Create a signed JWT whose ``sub`` claim is ``subject``."""
    settings = get_settings()
    if expires_in is None:
        expires_in = settings.access_token_expire_minutes * 60

    now = int(time.time())
    header = {"alg": _JWT_ALG, "typ": "JWT"}
    payload = {"sub": subject, "iat": now, "exp": now + expires_in}

    segments = [
        _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8")),
        _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
    ]
    signing_input = ".".join(segments).encode("ascii")
    segments.append(_b64url_encode(_sign(signing_input)))
    return ".".join(segments)


class TokenError(Exception):
    """Raised when a token is malformed, tampered with, or expired."""


def decode_access_token(token: str) -> dict:
    """Verify signature and expiry; return the payload or raise TokenError.

    The algorithm is fixed server-side (never read from the token header) to
    avoid algorithm-confusion attacks.
    """
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
    except ValueError as exc:
        raise TokenError("malformed token") from exc

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected_sig = _sign(signing_input)
    try:
        actual_sig = _b64url_decode(sig_b64)
    except (ValueError, TypeError) as exc:
        raise TokenError("malformed signature") from exc

    if not hmac.compare_digest(expected_sig, actual_sig):
        raise TokenError("bad signature")

    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except (ValueError, TypeError) as exc:
        raise TokenError("malformed payload") from exc

    exp = payload.get("exp")
    if not isinstance(exp, int) or exp < int(time.time()):
        raise TokenError("token expired")

    return payload
