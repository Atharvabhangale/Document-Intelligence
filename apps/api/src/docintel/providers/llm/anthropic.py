"""Anthropic Claude provider (Messages API, structured JSON output).

The page-tagged document text is sent as its own content block marked for prompt caching, so
several tasks over the same document (summarize, requirements, risks, ask) can reuse the cached
prefix. The response is constrained to the request's JSON Schema via ``output_config``.

Security: the API key is handed straight to the SDK client and is not stored on this object.
Only the SDK error class, HTTP status and request id are logged — never prompts, document text,
model output or provider error bodies.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import anthropic

from docintel.core.errors import (
    AIAuthenticationError,
    AIConfigurationError,
    AIProviderError,
    AIRateLimitError,
    AITimeoutError,
    AIUnavailableError,
)
from docintel.providers.llm.base import (
    FinishReason,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    LLMUsage,
)

logger = logging.getLogger(__name__)

_STOP_REASONS: dict[str, FinishReason] = {
    "end_turn": "end",
    "stop_sequence": "end",
    "max_tokens": "max_tokens",
    # The response was cut off because the context window filled up: also a truncation.
    "model_context_window_exceeded": "max_tokens",
    "refusal": "refusal",
}

# Status codes for which a later retry can reasonably succeed.
_RETRYABLE_CLIENT_STATUSES = {408, 409}


class AnthropicProvider(LLMProvider):
    """LLM provider backed by the Anthropic Messages API."""

    name = "anthropic"

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        base_url: str | None = None,
        timeout_seconds: float = 120,
        max_retries: int = 2,
        client: object | None = None,
    ) -> None:
        """Create the provider.

        ``client`` injects a pre-built client exposing ``messages.create`` (used by tests).
        Without a client and without an API key the provider is created unconfigured: it does
        not fail here (so the API can start and report its health) but every ``generate_json``
        call raises ``AIConfigurationError``.
        """
        self.model = model
        self._client: Any | None
        if client is not None:
            self._client = client
        elif api_key:
            self._client = anthropic.Anthropic(
                api_key=api_key,
                base_url=base_url or None,
                timeout=timeout_seconds,
                max_retries=max_retries,
            )
        else:
            self._client = None

    @property
    def configured(self) -> bool:
        """True when a client (and therefore a credential) is available."""
        return self._client is not None

    def __repr__(self) -> str:
        return f"AnthropicProvider(model={self.model!r}, configured={self.configured})"

    def generate_json(self, request: LLMRequest) -> LLMResponse:
        if self._client is None:
            raise AIConfigurationError("The Anthropic API key is not configured.")

        params = self._build_params(request)
        started = time.perf_counter()
        try:
            response = self._client.messages.create(**params)
        except anthropic.AnthropicError as exc:
            # ``from None``: do not chain the SDK exception, whose message can contain the
            # provider's error body; the mapped error carries a user-safe message only.
            raise self._map_error(exc) from None
        latency_ms = round((time.perf_counter() - started) * 1000)

        raw_stop = getattr(response, "stop_reason", None)
        usage = getattr(response, "usage", None)
        result = LLMResponse(
            text=_join_text(getattr(response, "content", None) or []),
            model=getattr(response, "model", None) or self.model,
            provider=self.name,
            finish_reason=_STOP_REASONS.get(raw_stop or "", "other"),
            raw_finish_reason=raw_stop,
            usage=LLMUsage(
                input_tokens=getattr(usage, "input_tokens", None),
                output_tokens=getattr(usage, "output_tokens", None),
                cache_read_input_tokens=getattr(usage, "cache_read_input_tokens", None),
            ),
            latency_ms=latency_ms,
        )
        logger.debug(
            "Anthropic request completed: model=%s stop_reason=%s input_tokens=%s "
            "output_tokens=%s cache_read_input_tokens=%s latency_ms=%s",
            result.model,
            raw_stop,
            result.usage.input_tokens,
            result.usage.output_tokens,
            result.usage.cache_read_input_tokens,
            latency_ms,
        )
        return result

    def _build_params(self, request: LLMRequest) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": request.max_output_tokens,
            "system": [{"type": "text", "text": request.system}],
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": request.document_context,
                            "cache_control": {"type": "ephemeral"},
                        },
                        {"type": "text", "text": request.instruction},
                    ],
                }
            ],
            "output_config": {"format": {"type": "json_schema", "schema": request.json_schema}},
        }
        if request.temperature is not None:
            # The 1.x SDK has no ``temperature`` keyword; the API still accepts it on models
            # that support sampling parameters.
            params["extra_body"] = {"temperature": request.temperature}
        return params

    def _map_error(self, exc: anthropic.AnthropicError) -> AIProviderError:
        """Translate an SDK exception into a user-safe domain error (most specific first)."""
        status = getattr(exc, "status_code", None)
        logger.warning(
            "Anthropic request failed: error=%s status=%s request_id=%s",
            type(exc).__name__,
            status,
            getattr(exc, "request_id", None),
        )
        if isinstance(exc, anthropic.AuthenticationError | anthropic.PermissionDeniedError):
            return AIAuthenticationError()
        if isinstance(exc, anthropic.NotFoundError):
            return AIConfigurationError(f"The configured AI model is not available: {self.model}")
        if isinstance(exc, anthropic.RateLimitError):
            return AIRateLimitError()
        # APITimeoutError subclasses APIConnectionError, so it must be checked first.
        if isinstance(exc, anthropic.APITimeoutError):
            return AITimeoutError()
        if isinstance(exc, anthropic.APIConnectionError):
            return AIUnavailableError()
        if isinstance(exc, anthropic.InternalServerError) or (
            isinstance(status, int) and status >= 500
        ):
            return AIUnavailableError()
        if isinstance(exc, anthropic.BadRequestError):
            return _non_retryable("The AI service rejected the request.")
        if isinstance(exc, anthropic.RequestTooLargeError):
            return _non_retryable("The request is too large for the AI service.")
        if isinstance(exc, anthropic.APIStatusError):
            if status in _RETRYABLE_CLIENT_STATUSES:
                return AIProviderError()
            return _non_retryable("The AI service rejected the request.")
        return AIProviderError()


def _join_text(blocks: list[Any]) -> str:
    """Concatenate the text of all ``text`` content blocks (other block types are ignored)."""
    return "".join(
        block.text
        for block in blocks
        if getattr(block, "type", None) == "text" and isinstance(getattr(block, "text", None), str)
    )


def _non_retryable(message: str) -> AIProviderError:
    error = AIProviderError(message)
    error.retryable = False
    return error
