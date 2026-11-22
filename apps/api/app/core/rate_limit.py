"""A small in-memory, per-process sliding-window rate limiter.

Suitable for a single API process (the current deployment shape). A
multi-process/replicated deployment would need a shared store such as Redis.
State is keyed by an arbitrary string — ``scope:client-ip`` for the per-IP
dependency, or any caller-chosen key (e.g. a hashed email) via
:func:`check_rate_limit`.

Client IPs come from ``request.client.host``. Behind a reverse proxy (Render),
uvicorn only rewrites that from ``X-Forwarded-For`` when the proxy is trusted
(``FORWARDED_ALLOW_IPS``); see docs/DEPLOY.md.
"""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

_hits: dict[str, deque[float]] = defaultdict(deque)


def reset_rate_limits() -> None:
    """Clear all counters (used by tests)."""
    _hits.clear()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def check_rate_limit(key: str, max_requests: int, window_seconds: int) -> None:
    """Count one hit for ``key``; raise 429 if it exceeds the window's budget."""
    # Imported lazily so tests can toggle settings before each request.
    from app.core.config import get_settings

    if not get_settings().rate_limit_enabled:
        return

    now = time.monotonic()
    cutoff = now - window_seconds
    bucket = _hits[key]

    while bucket and bucket[0] < cutoff:
        bucket.popleft()

    if len(bucket) >= max_requests:
        retry_after = int(bucket[0] + window_seconds - now) + 1
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests, please try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    bucket.append(now)


def rate_limiter(scope: str, max_requests: int, window_seconds: int):
    """Build a FastAPI dependency enforcing ``max_requests`` per window per IP."""

    def dependency(request: Request) -> None:
        check_rate_limit(f"{scope}:{client_ip(request)}", max_requests, window_seconds)

    return dependency
