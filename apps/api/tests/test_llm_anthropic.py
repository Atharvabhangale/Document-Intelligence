"""AnthropicProvider: request shape, response mapping and error mapping (no network)."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
import pytest

from docintel.core.errors import (
    AIAuthenticationError,
    AIConfigurationError,
    AIProviderError,
    AIRateLimitError,
    AITimeoutError,
    AIUnavailableError,
)
from docintel.providers.llm.anthropic import AnthropicProvider
from docintel.providers.llm.base import LLMRequest

SECRET = "sk-ant-api03-TEST-SECRET-DO-NOT-LEAK"
MODEL = "claude-haiku-4-5-20251001"
SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}
DOCUMENT = '<document>\n<page number="1">Operators shall wear gloves.</page>\n</document>'


class FakeMessages:
    """Stands in for ``client.messages``: records kwargs, returns or raises a scripted item."""

    def __init__(self, result: Any) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


def make_response(
    *,
    content: list[Any] | None = None,
    stop_reason: str | None = "end_turn",
    usage: Any = None,
    model: str = MODEL,
) -> SimpleNamespace:
    return SimpleNamespace(
        content=content if content is not None else [SimpleNamespace(type="text", text="{}")],
        stop_reason=stop_reason,
        usage=usage
        if usage is not None
        else SimpleNamespace(input_tokens=1200, output_tokens=80, cache_read_input_tokens=1000),
        model=model,
    )


def make_provider(result: Any) -> tuple[AnthropicProvider, FakeMessages]:
    messages = FakeMessages(result)
    client = SimpleNamespace(messages=messages)
    return AnthropicProvider(api_key=None, model=MODEL, client=client), messages


def make_request(*, temperature: float | None = 0.0) -> LLMRequest:
    return LLMRequest(
        system="You analyze documents.",
        document_context=DOCUMENT,
        instruction="Return the answer as JSON.",
        json_schema=SCHEMA,
        schema_name="ask",
        max_output_tokens=2048,
        temperature=temperature,
    )


# --- Request shape ----------------------------------------------------------------------------


def test_request_shape() -> None:
    provider, messages = make_provider(make_response())

    provider.generate_json(make_request(temperature=0.2))

    assert len(messages.calls) == 1
    kwargs = messages.calls[0]
    assert kwargs["model"] == MODEL
    assert kwargs["max_tokens"] == 2048
    assert kwargs["system"] == [{"type": "text", "text": "You analyze documents."}]
    assert kwargs["messages"] == [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": DOCUMENT, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": "Return the answer as JSON."},
            ],
        }
    ]
    assert kwargs["output_config"] == {"format": {"type": "json_schema", "schema": SCHEMA}}
    assert kwargs["extra_body"] == {"temperature": 0.2}
    assert "temperature" not in kwargs


def test_zero_temperature_is_sent() -> None:
    provider, messages = make_provider(make_response())

    provider.generate_json(make_request(temperature=0.0))

    assert messages.calls[0]["extra_body"] == {"temperature": 0.0}


def test_temperature_none_omits_extra_body() -> None:
    provider, messages = make_provider(make_response())

    provider.generate_json(make_request(temperature=None))

    assert "extra_body" not in messages.calls[0]
    assert "temperature" not in messages.calls[0]


# --- Response mapping -------------------------------------------------------------------------


def test_joins_text_blocks_and_ignores_other_blocks() -> None:
    content = [
        SimpleNamespace(type="thinking", thinking="internal"),
        SimpleNamespace(type="text", text='{"answer": '),
        SimpleNamespace(type="text", text='"yes"}'),
    ]
    provider, _ = make_provider(make_response(content=content))

    response = provider.generate_json(make_request())

    assert response.text == '{"answer": "yes"}'
    assert response.provider == "anthropic"
    assert response.model == MODEL
    assert response.latency_ms >= 0


def test_model_is_taken_from_response() -> None:
    provider, _ = make_provider(make_response(model="claude-haiku-4-5-served"))

    assert provider.generate_json(make_request()).model == "claude-haiku-4-5-served"


@pytest.mark.parametrize(
    ("stop_reason", "expected"),
    [
        ("end_turn", "end"),
        ("stop_sequence", "end"),
        ("max_tokens", "max_tokens"),
        ("model_context_window_exceeded", "max_tokens"),
        ("refusal", "refusal"),
        ("pause_turn", "other"),
        ("tool_use", "other"),
        (None, "other"),
    ],
)
def test_stop_reason_mapping(stop_reason: str | None, expected: str) -> None:
    provider, _ = make_provider(make_response(stop_reason=stop_reason))

    response = provider.generate_json(make_request())

    assert response.finish_reason == expected
    assert response.raw_finish_reason == stop_reason


def test_usage_mapping() -> None:
    provider, _ = make_provider(make_response())

    usage = provider.generate_json(make_request()).usage

    assert (usage.input_tokens, usage.output_tokens, usage.cache_read_input_tokens) == (
        1200,
        80,
        1000,
    )


def test_usage_missing_fields_are_none() -> None:
    usage = SimpleNamespace(input_tokens=10, output_tokens=5)  # no cache_read_input_tokens
    provider, _ = make_provider(make_response(usage=usage))

    response = provider.generate_json(make_request())

    assert response.usage.input_tokens == 10
    assert response.usage.cache_read_input_tokens is None


# --- Configuration and secrets ----------------------------------------------------------------


def test_missing_key_is_not_configured_and_fails_on_use() -> None:
    provider = AnthropicProvider(api_key=None, model=MODEL)

    assert provider.configured is False
    with pytest.raises(AIConfigurationError) as info:
        provider.generate_json(make_request())
    assert info.value.message == "The Anthropic API key is not configured."
    assert info.value.code == "ai_not_configured"


def test_empty_key_is_not_configured() -> None:
    assert AnthropicProvider(api_key="", model=MODEL).configured is False


def test_key_is_not_exposed() -> None:
    provider = AnthropicProvider(api_key=SECRET, model=MODEL, timeout_seconds=5, max_retries=0)

    assert provider.configured is True
    assert SECRET not in repr(provider)
    assert SECRET not in str(provider)
    # The key lives only inside the SDK client, not in any other attribute of the provider.
    for attribute, value in vars(provider).items():
        if attribute != "_client":
            assert SECRET not in repr(value)


def test_success_logs_contain_no_prompt_or_document(caplog: pytest.LogCaptureFixture) -> None:
    provider, _ = make_provider(make_response())

    with caplog.at_level(logging.DEBUG, logger="docintel.providers.llm.anthropic"):
        provider.generate_json(make_request())

    assert "Operators shall wear gloves" not in caplog.text
    assert "You analyze documents" not in caplog.text


# --- Error mapping ----------------------------------------------------------------------------

_REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def _status_error(cls: type[anthropic.APIStatusError], status: int) -> anthropic.APIStatusError:
    response = httpx2.Response(status, request=_REQUEST, headers={"request-id": "req_test_123"})
    # The SDK message embeds the provider's error body; it must never reach users or logs.
    body = {"type": "error", "error": {"type": "x", "message": f"body mentions {SECRET}"}}
    return cls(f"Error code: {status} - {body}", response=response, body=body)


@pytest.mark.parametrize(
    ("exception", "expected_type", "code", "retryable"),
    [
        (
            _status_error(anthropic.AuthenticationError, 401),
            AIAuthenticationError,
            "ai_authentication_failed",
            False,
        ),
        (
            _status_error(anthropic.PermissionDeniedError, 403),
            AIAuthenticationError,
            "ai_authentication_failed",
            False,
        ),
        (
            _status_error(anthropic.NotFoundError, 404),
            AIConfigurationError,
            "ai_not_configured",
            False,
        ),
        (_status_error(anthropic.RateLimitError, 429), AIRateLimitError, "ai_rate_limited", True),
        (
            _status_error(anthropic.BadRequestError, 400),
            AIProviderError,
            "ai_provider_error",
            False,
        ),
        (
            _status_error(anthropic.RequestTooLargeError, 413),
            AIProviderError,
            "ai_provider_error",
            False,
        ),
        (
            _status_error(anthropic.InternalServerError, 500),
            AIUnavailableError,
            "ai_unavailable",
            True,
        ),
        (
            _status_error(anthropic.InternalServerError, 502),
            AIUnavailableError,
            "ai_unavailable",
            True,
        ),
        (
            _status_error(anthropic.ServiceUnavailableError, 503),
            AIUnavailableError,
            "ai_unavailable",
            True,
        ),
        (_status_error(anthropic.OverloadedError, 529), AIUnavailableError, "ai_unavailable", True),
        (_status_error(anthropic.APIStatusError, 418), AIProviderError, "ai_provider_error", False),
        (_status_error(anthropic.ConflictError, 409), AIProviderError, "ai_provider_error", True),
        (anthropic.APITimeoutError(request=_REQUEST), AITimeoutError, "ai_timeout", True),
        (
            anthropic.APIConnectionError(request=_REQUEST),
            AIUnavailableError,
            "ai_unavailable",
            True,
        ),
    ],
    ids=lambda value: type(value).__name__ if isinstance(value, Exception) else None,
)
def test_error_mapping(
    exception: Exception,
    expected_type: type[AIProviderError],
    code: str,
    retryable: bool,
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider, _ = make_provider(exception)

    with (
        caplog.at_level(logging.DEBUG, logger="docintel.providers.llm.anthropic"),
        pytest.raises(AIProviderError) as info,
    ):
        provider.generate_json(make_request())

    error = info.value
    assert type(error) is expected_type
    assert error.code == code
    assert error.retryable is retryable
    assert SECRET not in error.message
    assert SECRET not in str(error)
    # The SDK exception is not chained, so tracebacks cannot print its message.
    assert error.__cause__ is None
    assert error.__suppress_context__ is True
    # Logs carry only the error class, status and request id.
    assert type(exception).__name__ in caplog.text
    assert SECRET not in caplog.text
    assert "body mentions" not in caplog.text


def test_status_error_log_includes_status_and_request_id(caplog: pytest.LogCaptureFixture) -> None:
    provider, _ = make_provider(_status_error(anthropic.RateLimitError, 429))

    with (
        caplog.at_level(logging.WARNING, logger="docintel.providers.llm.anthropic"),
        pytest.raises(AIRateLimitError),
    ):
        provider.generate_json(make_request())

    assert "status=429" in caplog.text
    assert "request_id=req_test_123" in caplog.text


def test_not_found_names_the_model() -> None:
    provider, _ = make_provider(_status_error(anthropic.NotFoundError, 404))

    with pytest.raises(AIConfigurationError) as info:
        provider.generate_json(make_request())

    assert info.value.message == f"The configured AI model is not available: {MODEL}"


def test_bad_request_has_safe_message() -> None:
    provider, _ = make_provider(_status_error(anthropic.BadRequestError, 400))

    with pytest.raises(AIProviderError) as info:
        provider.generate_json(make_request())

    assert info.value.message == "The AI service rejected the request."
    # Non-retryable on this instance only; the class default is unchanged.
    assert AIProviderError.retryable is True
