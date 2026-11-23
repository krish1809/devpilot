"""Verify Google ID tokens ("Sign in with Google").

The browser runs Google's sign-in button and receives an *ID token*: a JWT
signed by Google (RS256) that says who the user is. The API never trusts the
browser's word for it; it checks the token itself:

- the signature, against Google's published public keys (JWKS, fetched over
  HTTPS and cached);
- ``aud`` is *our* client ID (a token minted for another site is rejected);
- ``iss`` is Google, and ``exp``/``iat`` are present and not expired;
- ``email_verified`` is true, since the email is what links accounts.

No client secret is involved: ID-token sign-in doesn't need one.
Tests override :func:`get_google_verifier` with a fake.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import jwt

from app.core.config import get_settings

GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = ("accounts.google.com", "https://accounts.google.com")
# Tolerate small clock differences between Google and this server.
_LEEWAY_SECONDS = 60


@dataclass(frozen=True)
class GoogleIdentity:
    sub: str
    email: str
    email_verified: bool


class GoogleTokenError(Exception):
    """The ID token is missing, forged, expired, or for another client."""


class GoogleVerifier(Protocol):
    def verify(self, credential: str) -> GoogleIdentity: ...


# One client per process: PyJWKClient caches Google's keys between requests.
_jwks_client = jwt.PyJWKClient(GOOGLE_JWKS_URL, cache_keys=True, lifespan=3600)


class JwksGoogleVerifier:
    def __init__(self, client_id: str) -> None:
        self._client_id = client_id

    def verify(self, credential: str) -> GoogleIdentity:
        if not self._client_id:
            raise GoogleTokenError("Google sign-in is not configured")
        try:
            key = _jwks_client.get_signing_key_from_jwt(credential)
            claims = jwt.decode(
                credential,
                key.key,
                algorithms=["RS256"],
                audience=self._client_id,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
                leeway=_LEEWAY_SECONDS,
            )
        except (jwt.PyJWTError, jwt.PyJWKClientError) as exc:
            raise GoogleTokenError(type(exc).__name__) from None
        return identity_from_claims(claims)


def identity_from_claims(claims: dict) -> GoogleIdentity:
    """Validate the claims that PyJWT doesn't check itself."""
    if claims.get("iss") not in GOOGLE_ISSUERS:
        raise GoogleTokenError("wrong issuer")
    sub, email = claims.get("sub"), claims.get("email")
    if not isinstance(sub, str) or not sub or not isinstance(email, str) or "@" not in email:
        raise GoogleTokenError("missing subject or email")
    return GoogleIdentity(
        sub=sub,
        email=email.strip().lower(),
        email_verified=claims.get("email_verified") is True,
    )


def get_google_verifier() -> GoogleVerifier:
    """FastAPI dependency."""
    return JwksGoogleVerifier(get_settings().google_client_id)
