"""Application configuration.

Every setting comes from the environment. Secrets are held as ``SecretStr`` so
they mask themselves in reprs, log lines, and tracebacks — the default failure
mode for a plain ``str`` is that an unhandled exception prints it.

Missing required variables fail at import of the settings object rather than at
first use, so a misconfigured deployment dies on startup instead of halfway
through a user's run.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr


class ConfigurationError(RuntimeError):
    """Raised when the environment is missing or malformed.

    Carries the full list of problems rather than the first one, so a fresh
    deployment can be fixed in a single pass.
    """


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -- Supabase -----------------------------------------------------------
    supabase_url: str
    supabase_anon_key: SecretStr
    supabase_service_role_key: SecretStr
    supabase_jwt_secret: SecretStr

    # -- API ----------------------------------------------------------------
    api_env: Literal["development", "staging", "production"] = "development"
    api_cors_origins: str = "http://localhost:5173"

    # -- OpenRouter ---------------------------------------------------------
    # User API keys are deliberately absent. Under BYOK the key arrives per-run
    # from the browser, lives in memory for that run, and is never persisted.
    openrouter_default_model: str = "anthropic/claude-sonnet-4.5"
    openrouter_app_url: str = "https://agenlate.ai"
    openrouter_app_title: str = "Agenlate"

    # -- Run limits ---------------------------------------------------------
    # Termination guarantees. A run must always stop for a named reason.
    run_max_turns: int = Field(default=25, gt=0)
    run_spend_cap_usd: float = Field(default=1.00, gt=0)
    run_stall_repeat_limit: int = Field(default=3, gt=1)
    run_no_progress_limit: int = Field(default=3, gt=0)
    run_unpriced_call_limit: int = Field(default=10, gt=0)
    run_tool_rounds_per_dispatch: int = Field(default=5, gt=0)

    @field_validator("supabase_url")
    @classmethod
    def _validate_supabase_url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("must be a full URL including scheme")
        return value.rstrip("/")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.api_env == "production"

    @model_validator(mode="after")
    def _no_wildcard_cors_in_production(self) -> "Settings":
        if self.is_production and "*" in self.cors_origins:
            raise ValueError(
                "api_cors_origins may not contain '*' in production; "
                "list the deployed frontend origin explicitly"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, constructing them on first call.

    Translates pydantic's validation error into a message that names every
    missing or malformed variable at once.
    """
    try:
        return Settings()  # type: ignore[call-arg]  # values come from the environment
    except ValidationError as exc:
        problems = []
        for error in exc.errors():
            name = ".".join(str(part) for part in error["loc"]).upper()
            problems.append(f"  {name}: {error['msg']}")
        raise ConfigurationError(
            "Invalid backend configuration:\n"
            + "\n".join(problems)
            + "\n\nSee backend/.env.example for the expected variables."
        ) from exc
