"""Settings validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from docintel.core.config import Settings


def test_ollama_requires_a_local_model_name(tmp_path) -> None:
    with pytest.raises(ValidationError, match="AI_MODEL"):
        Settings(ai_provider="ollama", ai_model="claude-haiku-4-5-20251001", data_dir=tmp_path)

    settings = Settings(ai_provider="ollama", ai_model="llama3.1:8b", data_dir=tmp_path)
    assert settings.ai_model == "llama3.1:8b"


@pytest.mark.parametrize("raw", ["", "none", "NULL"])
def test_temperature_can_be_disabled(raw: str, tmp_path) -> None:
    assert Settings(ai_temperature=raw, data_dir=tmp_path).ai_temperature is None


def test_api_key_is_secret(tmp_path) -> None:
    settings = Settings(anthropic_api_key="sk-ant-test-value", data_dir=tmp_path)
    assert "sk-ant-test-value" not in repr(settings)
    assert "sk-ant-test-value" not in str(settings.model_dump())


def test_cad_variable_is_accepted_as_anthropic_key(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("CAD_ANTHROPIC_API_KEY", "sk-ant-from-environment")
    settings = Settings(data_dir=tmp_path)
    assert settings.anthropic_api_key is not None
    assert settings.anthropic_api_key.get_secret_value() == "sk-ant-from-environment"
