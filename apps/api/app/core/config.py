from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "DevPilot API"
    environment: str = "development"
    debug: bool = True

    database_url: str = "postgresql+psycopg://devpilot:devpilot@localhost:5432/devpilot"

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
