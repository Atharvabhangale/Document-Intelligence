"""Construct the configured LLM provider from settings."""

from __future__ import annotations

from typing import NamedTuple

from docintel.core.config import Settings
from docintel.core.errors import AIConfigurationError
from docintel.providers.llm.anthropic import AnthropicProvider
from docintel.providers.llm.base import LLMProvider
from docintel.providers.llm.dev_fake import DevFakeLLMProvider
from docintel.providers.llm.ollama import OllamaProvider


class ProviderDescription(NamedTuple):
    """Non-secret provider facts reported by ``/api/health``."""

    name: str
    model: str
    configured: bool
    development_only: bool


def create_llm_provider(settings: Settings) -> LLMProvider:
    """Return the provider selected by ``settings.ai_provider``.

    A missing Anthropic key does not fail here: the provider is created unconfigured so the API
    can start, report ``configured: false`` and return a clear error on analysis requests.
    """
    if settings.ai_provider == "anthropic":
        secret = settings.anthropic_api_key
        return AnthropicProvider(
            api_key=(secret.get_secret_value() or None) if secret is not None else None,
            model=settings.ai_model,
            base_url=settings.anthropic_base_url,
            timeout_seconds=settings.ai_timeout_seconds,
        )
    if settings.ai_provider == "ollama":
        return OllamaProvider(
            base_url=settings.ollama_base_url,
            model=settings.ai_model,
            num_ctx=settings.ollama_num_ctx,
            timeout_seconds=settings.ai_timeout_seconds,
        )
    if settings.ai_provider == "fake":
        return DevFakeLLMProvider()
    raise AIConfigurationError(f"Unknown AI provider: {settings.ai_provider}")


def describe_provider(provider: LLMProvider) -> ProviderDescription:
    """Describe ``provider`` without exposing configuration secrets.

    Providers without a ``configured`` property (e.g. test doubles) are treated as configured.
    """
    return ProviderDescription(
        name=provider.name,
        model=provider.model,
        configured=bool(getattr(provider, "configured", True)),
        development_only=provider.development_only,
    )
