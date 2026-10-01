"""Showcase ("demo") mode for a public deployment.

Free hosting can't run the agent's Docker sandbox, so a public deployment is a
read-only showcase of real runs and benchmark results recorded locally. With
``DEMO_MODE=true``:

- every state-changing request is refused (403) except logging in, so no one
  can start agent runs, approve PRs, register, or create data;
- the GitHub endpoints are disabled entirely (the server holds no token);
- ``POST /api/v1/auth/demo`` signs visitors in as a read-only demo user, so
  nobody needs an account to look around.
"""

from __future__ import annotations

import secrets

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.config import get_settings
from app.core.security import hash_password
from app.models.user import User
from app.services.user import get_user_by_email

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_ALLOWED_WRITES = {"/api/v1/auth/login", "/api/v1/auth/demo"}
_BLOCKED_PREFIXES = ("/api/v1/github",)


class ReadOnlyShowcaseMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if get_settings().demo_mode:
            path = request.url.path.rstrip("/")
            if path.startswith(_BLOCKED_PREFIXES) or (
                request.method not in _SAFE_METHODS and path not in _ALLOWED_WRITES
            ):
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": "This is a read-only showcase. Run DevPilot locally to "
                        "start agent runs."
                    },
                )
        return await call_next(request)


def get_or_create_demo_user(db: Session) -> User:
    email = get_settings().demo_user_email
    user = get_user_by_email(db, email)
    if user is None:
        # Random, never-shown password: the account is only reachable via /auth/demo.
        user = User(email=email, hashed_password=hash_password(secrets.token_urlsafe(32)))
        db.add(user)
        db.commit()
        db.refresh(user)
    return user
