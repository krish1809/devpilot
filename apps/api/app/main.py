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

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Backend API for the DevPilot AI software engineering platform.",
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


@app.get("/api/v1/config", tags=["system"])
def public_config() -> dict[str, bool]:
    """Public, non-secret flags the web app adapts to."""
    return {"demo_mode": get_settings().demo_mode}


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
