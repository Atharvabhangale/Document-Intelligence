"""Provider factory and health description."""

from __future__ import annotations

from pathlib import Path

from pydantic import SecretStr

from docintel.core.config import Settings
from docintel.providers.llm import (
    AnthropicProvider,
    DevFakeLLMProvider,
    OllamaProvider,
    ProviderDescription,
    create_llm_provider,
    describe_provider,
)
from docintel.providers.llm.fake import ScriptedLLMProvider


def test_anthropic_with_key(settings: Settings) -> None:
    provider = create_llm_provider(settings)

    assert isinstance(provider, AnthropicProvider)
    assert provider.model == "claude-haiku-4-5-20251001"
    assert describe_provider(provider) == ProviderDescription(
        name="anthropic",
        model="claude-haiku-4-5-20251001",
        configured=True,
        development_only=False,
    )
    assert "test-key-not-real" not in repr(provider)


def test_anthropic_without_key_is_not_configured(settings: Settings) -> None:
    for key in (None, SecretStr("")):
        provider = create_llm_provider(settings.model_copy(update={"anthropic_api_key": key}))

        assert isinstance(provider, AnthropicProvider)
        assert provider.configured is False
        assert describe_provider(provider).configured is False


def test_anthropic_without_key_from_constructor(tmp_path: Path) -> None:
    # Explicit init values take precedence over any credential in the environment.
    settings = Settings(ai_provider="anthropic", anthropic_api_key=None, data_dir=tmp_path)

    assert describe_provider(create_llm_provider(settings)).configured is False


def test_ollama(settings: Settings) -> None:
    configured = settings.model_copy(
        update={
            "ai_provider": "ollama",
            "ai_model": "llama3.1:8b",
            "ollama_base_url": "http://ollama.internal:11434/",
            "ollama_num_ctx": 8192,
        }
    )

    provider = create_llm_provider(configured)

    assert isinstance(provider, OllamaProvider)
    assert provider.model == "llama3.1:8b"
    assert tuple(describe_provider(provider)) == ("ollama", "llama3.1:8b", True, False)
    assert provider._chat_url == "http://ollama.internal:11434/api/chat"
    assert provider._num_ctx == 8192


def test_fake_is_development_only(settings: Settings) -> None:
    provider = create_llm_provider(settings.model_copy(update={"ai_provider": "fake"}))

    assert isinstance(provider, DevFakeLLMProvider)
    name, model, configured, development_only = describe_provider(provider)
    assert (name, model, configured, development_only) == ("fake", "dev-fake-1", True, True)


def test_describe_provider_without_configured_property() -> None:
    description = describe_provider(ScriptedLLMProvider([]))

    assert description.name == "scripted"
    assert description.configured is True
    assert description.development_only is True
