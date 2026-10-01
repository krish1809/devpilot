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

    # GitHub. A fine-grained PAT, server-side only. If empty, falls back to the
    # host's authenticated `gh` CLI token.
    github_token: str = ""
    github_timeout_seconds: int = 20

    # Agent (LangGraph) bounds — every run is capped so a runaway repair loop
    # can't burn unbounded tokens or time.
    agent_max_attempts: int = 3  # coder → tester iterations
    agent_max_llm_calls: int = 8
    agent_max_tokens: int = 100_000  # prompt + completion, per run
    agent_run_timeout_seconds: int = 900  # wall clock per execution
    agent_review_max_changed_lines: int = 300

    # Repository RAG (Phase 6). Local embeddings by default (no API key).
    rag_enabled: bool = True  # default for new runs; overridable per run
    embedding_model: str = "BAAI/bge-small-en-v1.5"  # must produce 384-d vectors
    embedding_cache_dir: str = ""  # fastembed model cache ("" = library default)
    rag_max_files: int = 3000
    rag_max_chunks: int = 8000
    rag_context_chars: int = 12_000  # retrieved context budget per prompt
    rag_candidate_files: int = 8  # files offered to the planner for localization

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
