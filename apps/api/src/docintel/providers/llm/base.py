"""LLM provider abstraction.

The intelligence pipeline depends only on this interface. Providers turn an ``LLMRequest``
into raw JSON text constrained (where the backend supports it) by ``json_schema``. Parsing and
validation of that text is the pipeline's job, so every provider gets identical safety checks.

Contract for implementations:

* Map transport/service failures to ``docintel.core.errors`` AI errors
  (``AIAuthenticationError``, ``AIRateLimitError``, ``AITimeoutError``, ``AIUnavailableError``,
  ``AIProviderError`` for other API errors, ``AIConfigurationError`` for missing config).
* Do NOT raise for truncation or refusal — report them via ``finish_reason`` so the pipeline
  can decide (it raises ``AIOutputTruncatedError`` / ``AIRefusalError``).
* Never log prompts, document text, model output or credentials.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

FinishReason = Literal["end", "max_tokens", "refusal", "other"]


@dataclass(frozen=True)
class LLMRequest:
    system: str
    # Large content that is stable for a document (the page-tagged document text). Providers
    # may cache it (e.g. Anthropic prompt caching) — keep it byte-identical across tasks.
    document_context: str
    # Task-specific instruction (and, for Q&A, the question). Varies per request.
    instruction: str
    json_schema: dict[str, Any]
    schema_name: str  # task name, e.g. "summarize" | "requirements" | "risks" | "ask"
    max_output_tokens: int
    temperature: float | None = None


@dataclass(frozen=True)
class LLMUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_input_tokens: int | None = None


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str  # model identifier as reported by the backend
    provider: str
    finish_reason: FinishReason
    raw_finish_reason: str | None = None
    usage: LLMUsage = field(default_factory=LLMUsage)
    latency_ms: int = 0


class LLMProvider(ABC):
    """Base class for LLM providers."""

    #: Short provider id, e.g. "anthropic", "ollama", "fake".
    name: str
    #: Configured model identifier.
    model: str
    #: True for providers that must never be used for real analysis (fake/canned output).
    development_only: bool = False

    @abstractmethod
    def generate_json(self, request: LLMRequest) -> LLMResponse:
        """Generate a JSON response for ``request``. See module docstring for the contract."""
