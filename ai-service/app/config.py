"""AI service configuration (env-driven)."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Base URL of the HardwareOS REST API (v1), e.g. http://web:8000/api/v1
    hardwareos_api_url: str = "http://localhost:8000/api/v1"
    request_timeout_seconds: float = 15.0

    # Anthropic — natural-language querying. If unset, a deterministic engine is used.
    anthropic_api_key: str = ""
    # Default to the latest, most capable Claude model.
    anthropic_model: str = "claude-opus-4-8"
    anthropic_max_tokens: int = 800

    cors_allow_origins: str = "http://localhost:3000"


settings = Settings()
