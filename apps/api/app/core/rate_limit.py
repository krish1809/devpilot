"""A small in-memory, per-process sliding-window rate limiter.

Suitable for a single API process (the current deployment shape). For
multi-process/replicated deployments this must move to a shared store such as
Redis; see roadmap Phase 15. State is keyed by ``scope:client-ip``.
"""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

_hits: dict[str, deque[float]] = defaultdict(deque)


def reset_rate_limits() -> None:
    """Clear all counters (used by tests)."""
    _hits.clear()


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def rate_limiter(scope: str, max_requests: int, window_seconds: int):
    """Build a FastAPI dependency enforcing ``max_requests`` per window per IP."""

    def dependency(request: Request) -> None:
        # Imported lazily so tests can toggle settings before each request.
        from app.core.config import get_settings

        if not get_settings().rate_limit_enabled:
            return

        key = f"{scope}:{_client_ip(request)}"
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

    return dependency
