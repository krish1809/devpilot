import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.agent import router as agent_router
from app.api.audit import router as audit_router
from app.api.auth import router as auth_router
from app.api.evals import router as evals_router
from app.api.github import router as github_router
from app.api.projects import router as projects_router
from app.core.config import get_settings
from app.core.demo import ReadOnlyShowcaseMiddleware
from app.integrations.email import email_config_problems

settings = get_settings()
logger = logging.getLogger("app.startup")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Say once, loudly, why outgoing email won't work, instead of failing
    # silently in a background task the first time someone resets a password.
    current = get_settings()
    problems = email_config_problems(current)
    for problem in problems:
        logger.warning("Email is misconfigured: %s", problem)
    if not problems:
        logger.info("Email backend: %s", current.email_backend)
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Backend API for the DevPilot AI software engineering platform.",
    lifespan=lifespan,
)

_cors_origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]

app.add_middleware(ReadOnlyShowcaseMiddleware)
# Added last so it runs first: even refused responses carry CORS headers.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(
    auth_router,
    prefix="/api/v1",
)

app.include_router(
    projects_router,
    prefix="/api/v1",
)

app.include_router(
    audit_router,
    prefix="/api/v1",
)

app.include_router(
    agent_router,
    prefix="/api/v1",
)


app.include_router(
    github_router,
    prefix="/api/v1",
)


app.include_router(
    evals_router,
    prefix="/api/v1",
)


@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    """A friendly landing response for anyone who opens the API URL directly."""
    return {
        "name": "DevPilot API",
        "mode": "read-only showcase" if get_settings().demo_mode else "full",
        "docs": "/docs",
        "health": "/health",
        "source": "https://github.com/krish1809/devpilot",
    }


@app.get("/api/v1/config", tags=["system"])
def public_config() -> dict[str, bool | str]:
    """Public, non-secret settings the web app adapts to.

    The Google client ID is public by design (it's embedded in every Google
    sign-in page); serving it here keeps it configured in one place.
    """
    current = get_settings()
    return {
        "demo_mode": current.demo_mode,
        "registration_open": not current.demo_mode,
        "google_client_id": current.google_client_id,
    }


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
