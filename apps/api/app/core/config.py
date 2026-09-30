from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# apps/api/.env, resolved from this file's location so it loads regardless of
# the current working directory (config.py -> app -> core; parents[2] == apps/api).
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    app_name: str = "DevPilot API"
    environment: str = "development"
    debug: bool = True

    database_url: str = "postgresql+psycopg://devpilot:devpilot@localhost:5432/devpilot"

    # Auth. secret_key MUST be overridden via environment in any non-dev
    # deployment; the default below is for local development only.
    secret_key: str = "dev-only-insecure-change-me"
    access_token_expire_minutes: int = 60 * 24  # 24 hours

    # Rate limiting (in-memory; per-process). For multi-process deployments
    # this should move to a shared store (Redis) — see roadmap Phase 15.
    rate_limit_enabled: bool = True
    auth_rate_limit_max: int = 10
    auth_rate_limit_window_seconds: int = 60

    # Comma-separated list of allowed browser origins for CORS.
    cors_origins: str = "http://localhost:3000"

    # LLM. Provider-neutral; provider + model are configuration, never
    # hard-coded in business logic.
    llm_provider: str = "groq"
    llm_model: str = "openai/gpt-oss-120b"
    llm_timeout_seconds: int = 60

    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"

    openai_api_key: str = ""
    hf_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"

    # Sandbox for running untrusted repository code.
    sandbox_image: str = "python:3.11-slim"
    sandbox_timeout_seconds: int = 120

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
