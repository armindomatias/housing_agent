"""
Application configuration using pydantic-settings.
Loads environment variables from .env file.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # API Keys
    openai_api_key: str
    apify_token: str = ""

    # Supabase
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_password: str = ""

    # OpenAI Model Configuration
    openai_vision_model: str = "gpt-4o"
    openai_classification_model: str = "gpt-4o-mini"

    # LangSmith / Observability
    langsmith_api_key: str = ""
    langsmith_project: str = "rehabify"
    langchain_tracing_v2: bool = False  # Explicit opt-in

    # App Settings
    debug: bool = False
    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
