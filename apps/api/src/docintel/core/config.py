"""Application settings.

All configuration comes from environment variables (optionally a local ``.env`` file that is
git-ignored). Secrets are held as ``SecretStr`` and must never be logged or returned by the API.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# apps/api/src/docintel/core/config.py -> repository root is five levels up.
REPO_ROOT = Path(__file__).resolve().parents[5]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # --- AI provider -------------------------------------------------------------------------
    # "fake" is DEVELOPMENT ONLY: deterministic canned output derived from the document text,
    # used for offline UI development and end-to-end tests. Never use it for real analysis.
    ai_provider: Literal["anthropic", "ollama", "fake"] = Field(
        default="anthropic", validation_alias=AliasChoices("AI_PROVIDER")
    )
    # Default is the Haiku model reported by the Models API in the development environment.
    ai_model: str = Field(
        default="claude-haiku-4-5-20251001", validation_alias=AliasChoices("AI_MODEL")
    )
    ai_max_output_tokens: int = Field(
        default=16000, ge=256, validation_alias=AliasChoices("AI_MAX_OUTPUT_TOKENS")
    )
    ai_timeout_seconds: float = Field(
        default=120.0, gt=0, validation_alias=AliasChoices("AI_TIMEOUT_SECONDS")
    )
    # Sampling temperature. Claude Haiku 4.5 accepts it (sent via ``extra_body`` because the
    # 1.x SDK removed the keyword); Claude Opus 4.7+ and other newer models reject sampling
    # parameters — set ``AI_TEMPERATURE=none`` for those.
    ai_temperature: float | None = Field(
        default=0.0, ge=0.0, le=1.0, validation_alias=AliasChoices("AI_TEMPERATURE")
    )
    # Number of additional "repair" attempts when the model output fails schema validation.
    ai_max_repair_attempts: int = Field(
        default=1, ge=0, le=3, validation_alias=AliasChoices("AI_MAX_REPAIR_ATTEMPTS")
    )

    # Anthropic credential. ``CAD_ANTHROPIC_API_KEY`` is the variable provided by the
    # Claude Code Web development environment; ``ANTHROPIC_API_KEY`` takes precedence.
    anthropic_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "CAD_ANTHROPIC_API_KEY"),
        repr=False,
    )
    anthropic_base_url: str | None = Field(
        default=None, validation_alias=AliasChoices("ANTHROPIC_BASE_URL")
    )

    ollama_base_url: str = Field(
        default="http://127.0.0.1:11434", validation_alias=AliasChoices("OLLAMA_BASE_URL")
    )
    ollama_num_ctx: int = Field(
        default=32768, ge=2048, validation_alias=AliasChoices("OLLAMA_NUM_CTX")
    )

    # --- Windchill ---------------------------------------------------------------------------
    windchill_provider: Literal["mock", "windchill12"] = Field(
        default="mock", validation_alias=AliasChoices("WINDCHILL_PROVIDER")
    )
    samples_dir: Path = Field(
        default=REPO_ROOT / "samples", validation_alias=AliasChoices("SAMPLES_DIR")
    )

    # Identity of the (single) development user. The real integration will derive the
    # requester from the authenticated Windchill session.
    dev_user_id: str = Field(default="dev.user", validation_alias=AliasChoices("DEV_USER_ID"))

    # --- Storage & limits --------------------------------------------------------------------
    data_dir: Path = Field(default=REPO_ROOT / ".data", validation_alias=AliasChoices("DATA_DIR"))
    prompts_dir: Path = Field(
        default=REPO_ROOT / "prompts", validation_alias=AliasChoices("PROMPTS_DIR")
    )
    max_upload_mb: int = Field(
        default=25, ge=1, le=200, validation_alias=AliasChoices("MAX_UPLOAD_MB")
    )
    max_pages: int = Field(default=300, ge=1, validation_alias=AliasChoices("MAX_PAGES"))
    # Conservative estimate of the document size (in tokens) we send in a single request.
    max_document_tokens: int = Field(
        default=120_000, ge=1000, validation_alias=AliasChoices("MAX_DOCUMENT_TOKENS")
    )
    max_question_chars: int = Field(
        default=1000, ge=10, validation_alias=AliasChoices("MAX_QUESTION_CHARS")
    )

    # --- HTTP --------------------------------------------------------------------------------
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"],
        validation_alias=AliasChoices("CORS_ORIGINS"),
    )
    serve_web_dist: Path | None = Field(
        default=REPO_ROOT / "apps" / "web" / "dist",
        validation_alias=AliasChoices("SERVE_WEB_DIST"),
    )
    log_level: str = Field(default="INFO", validation_alias=AliasChoices("LOG_LEVEL"))

    @field_validator("ai_temperature", mode="before")
    @classmethod
    def _empty_temperature_is_none(cls, value: object) -> object:
        if isinstance(value, str) and value.strip().lower() in {"", "none", "null"}:
            return None
        return value

    @model_validator(mode="after")
    def _model_matches_provider(self) -> Settings:
        # The default AI_MODEL is a Claude model; a local runtime would reject it with a
        # confusing "model not found". Fail fast with a clear message instead.
        if self.ai_provider == "ollama" and self.ai_model.startswith("claude-"):
            raise ValueError(
                "AI_PROVIDER=ollama requires AI_MODEL to name a local Ollama model "
                f"(got {self.ai_model!r})."
            )
        return self

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
