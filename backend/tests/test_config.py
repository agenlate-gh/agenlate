"""Configuration loading, validation, and secret masking."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agenlate.config import ConfigurationError, Settings, get_settings

REQUIRED = (
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_JWT_SECRET",
)


def test_missing_variables_name_every_problem(monkeypatch, tmp_path) -> None:
    """A fresh deployment should be fixable in one pass, not one variable at a time."""
    for name in REQUIRED:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)  # no .env to fall back on
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError) as exc_info:
        get_settings()

    message = str(exc_info.value)
    for name in REQUIRED:
        assert name in message

    get_settings.cache_clear()


def test_secrets_are_masked_in_repr(settings: Settings) -> None:
    """A traceback or log line must never carry the service-role key."""
    rendered = repr(settings)

    assert "test-service-role-key" not in rendered
    assert "test-jwt-secret" not in rendered
    assert "test-anon-key" not in rendered
    assert "**********" in rendered


def test_secret_value_is_still_reachable(settings: Settings) -> None:
    assert settings.supabase_service_role_key.get_secret_value() == "test-service-role-key"


def test_cors_origins_are_split_and_stripped(settings: Settings) -> None:
    settings.api_cors_origins = "http://a.test , https://b.test,  "

    assert settings.cors_origins == ["http://a.test", "https://b.test"]


def test_production_rejects_wildcard_cors() -> None:
    with pytest.raises(ValidationError):
        Settings(
            supabase_url="https://test.supabase.co",
            supabase_anon_key="k",
            supabase_service_role_key="k",
            supabase_jwt_secret="k",
            api_env="production",
            api_cors_origins="*",
        )


def test_supabase_url_requires_a_scheme() -> None:
    with pytest.raises(ValidationError):
        Settings(
            supabase_url="test.supabase.co",
            supabase_anon_key="k",
            supabase_service_role_key="k",
            supabase_jwt_secret="k",
        )


def test_supabase_url_trailing_slash_is_removed() -> None:
    settings = Settings(
        supabase_url="https://test.supabase.co/",
        supabase_anon_key="k",
        supabase_service_role_key="k",
        supabase_jwt_secret="k",
    )

    assert settings.supabase_url == "https://test.supabase.co"


def test_run_limits_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Settings(
            supabase_url="https://test.supabase.co",
            supabase_anon_key="k",
            supabase_service_role_key="k",
            supabase_jwt_secret="k",
            run_max_turns=0,
        )
