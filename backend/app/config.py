"""Application settings, loaded from environment variables (and ``.env`` in development)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent

InferenceBackend = Literal["bedrock", "hf", "ollama", "mistral", "fake"]
StorageBackend = Literal["sqlite", "dynamodb", "memory"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR / ".env", BACKEND_DIR.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["dev", "test", "prod"] = "dev"
    log_level: str = "INFO"

    # Demo mode: scripted bots + template commentary. No API keys needed.
    demo_mode: bool = False

    # Players
    inference_backend: InferenceBackend = "hf"
    models_file: Path = BACKEND_DIR / "models.yaml"
    hf_token: SecretStr | None = None
    hf_base_url: str = "https://router.huggingface.co/v1"
    ollama_base_url: str = "http://localhost:11434/v1"
    mistral_api_key: SecretStr | None = None
    mistral_base_url: str = "https://api.mistral.ai/v1"
    aws_region: str = "us-east-1"

    # Analyst / commentator / judge. "bedrock" = the model in models.yaml (prod, no extra key);
    # "openai_compat" = any OpenAI-compatible API (e.g. Gemini's free tier); "none" = templates.
    analyst_backend: Literal["none", "bedrock", "openai_compat"] = "none"
    analyst_model: str = ""  # override the models.yaml choice
    analyst_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    analyst_api_key: SecretStr | None = None
    analyst_budget_usd: float = Field(default=0.25, ge=0)

    # Storage
    storage_backend: StorageBackend = "sqlite"
    sqlite_path: Path = BACKEND_DIR / "data" / "outsmart.db"
    dynamodb_table: str = "outsmart-games"

    # Access control & spend guards
    admin_passcode: SecretStr | None = None
    max_games_per_day: int = Field(default=20, ge=0)
    max_concurrent_games: int = Field(default=2, ge=1)
    start_rate_limit: str = "5/hour"
    auth_rate_limit: str = "10/minute"
    max_body_bytes: int = Field(default=16_384, ge=1024)
    max_ws_connections: int = Field(default=300, ge=1)
    max_ws_per_client: int = Field(default=8, ge=1)
    # Only trust CloudFront-Viewer-Address when CloudFront is the sole way in (prod).
    trust_cloudfront_headers: bool = False

    # Gameplay pacing (ms between streamed events so humans can follow along)
    event_pacing_ms: int = Field(default=600, ge=0)
    cors_origins: list[str] = ["http://localhost:5173"]
    # Built React app to serve from the API container (single-container mode); None = off.
    static_dir: Path | None = None

    @property
    def analyst_enabled(self) -> bool:
        return not self.demo_mode and self.analyst_backend != "none"

    @property
    def effective_backend(self) -> InferenceBackend:
        return "fake" if self.demo_mode else self.inference_backend


@lru_cache
def get_settings() -> Settings:
    return Settings()
