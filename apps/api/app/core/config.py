from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    llm_provider: str = "openai"
    llm_model: str = ""

    openai_api_key: str = ""
    hf_api_key: str = ""

    ollama_base_url: str = "http://localhost:11434"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
