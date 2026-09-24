"""OllamaProvider against a mocked ``/api/chat`` transport (no Ollama server needed)."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from docintel.core.errors import (
    AIConfigurationError,
    AIProviderError,
    AIRequestRejectedError,
    AITimeoutError,
    AIUnavailableError,
)
from docintel.providers.llm.base import LLMRequest
from docintel.providers.llm.ollama import OllamaProvider

SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}
DOCUMENT = '<document>\n<page number="1">Operators shall wear gloves.</page>\n</document>'


def chat_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": "llama3.1:8b",
        "created_at": "2026-09-24T10:00:00Z",
        "message": {"role": "assistant", "content": '{"answer": "yes"}'},
        "done": True,
        "done_reason": "stop",
        "prompt_eval_count": 321,
        "eval_count": 12,
    }
    payload.update(overrides)
    return payload


class Recorder:
    def __init__(self, respond: Callable[[httpx.Request], httpx.Response]) -> None:
        self.respond = respond
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.respond(request)

    @property
    def body(self) -> dict[str, Any]:
        return json.loads(self.requests[-1].content)


def make_provider(
    respond: Callable[[httpx.Request], httpx.Response],
    *,
    base_url: str = "http://ollama.test:11434",
) -> tuple[OllamaProvider, Recorder]:
    recorder = Recorder(respond)
    client = httpx.Client(transport=httpx.MockTransport(recorder))
    provider = OllamaProvider(
        base_url=base_url,
        model="llama3.1:8b",
        num_ctx=32768,
        timeout_seconds=30,
        http_client=client,
    )
    return provider, recorder


def make_request(*, temperature: float | None = 0.0) -> LLMRequest:
    return LLMRequest(
        system="You analyze documents.",
        document_context=DOCUMENT,
        instruction="Return the answer as JSON.",
        json_schema=SCHEMA,
        schema_name="ask",
        max_output_tokens=4096,
        temperature=temperature,
    )


def ok(**overrides: Any) -> Callable[[httpx.Request], httpx.Response]:
    return lambda request: httpx.Response(200, json=chat_payload(**overrides))


def test_request_body_shape() -> None:
    provider, recorder = make_provider(ok())

    provider.generate_json(make_request(temperature=0.3))

    request = recorder.requests[0]
    assert request.method == "POST"
    assert str(request.url) == "http://ollama.test:11434/api/chat"
    assert recorder.body == {
        "model": "llama3.1:8b",
        "messages": [
            {"role": "system", "content": "You analyze documents."},
            {"role": "user", "content": f"{DOCUMENT}\n\nReturn the answer as JSON."},
        ],
        "format": SCHEMA,
        "stream": False,
        "options": {"num_ctx": 32768, "num_predict": 4096, "temperature": 0.3},
    }


def test_temperature_none_is_not_sent() -> None:
    provider, recorder = make_provider(ok())

    provider.generate_json(make_request(temperature=None))

    assert "temperature" not in recorder.body["options"]


def test_trailing_slash_in_base_url() -> None:
    provider, recorder = make_provider(ok(), base_url="http://ollama.test:11434/")

    provider.generate_json(make_request())

    assert str(recorder.requests[0].url) == "http://ollama.test:11434/api/chat"


def test_response_mapping() -> None:
    provider, _ = make_provider(ok())

    response = provider.generate_json(make_request())

    assert response.text == '{"answer": "yes"}'
    assert response.provider == "ollama"
    assert response.model == "llama3.1:8b"
    assert response.usage.input_tokens == 321
    assert response.usage.output_tokens == 12
    assert response.usage.cache_read_input_tokens is None
    assert response.latency_ms >= 0


def test_missing_usage_counts_are_none() -> None:
    payload = chat_payload()
    del payload["prompt_eval_count"], payload["eval_count"]
    provider, _ = make_provider(lambda request: httpx.Response(200, json=payload))

    response = provider.generate_json(make_request())

    assert response.usage.input_tokens is None
    assert response.usage.output_tokens is None


@pytest.mark.parametrize(
    ("done_reason", "expected"),
    [("stop", "end"), ("length", "max_tokens"), ("load", "other"), (None, "other")],
)
def test_done_reason_mapping(done_reason: str | None, expected: str) -> None:
    provider, _ = make_provider(ok(done_reason=done_reason))

    response = provider.generate_json(make_request())

    assert response.finish_reason == expected
    assert response.raw_finish_reason == done_reason


def _raise(exc: Exception) -> Callable[[httpx.Request], httpx.Response]:
    def respond(request: httpx.Request) -> httpx.Response:
        raise exc

    return respond


def test_connect_error_maps_to_unavailable() -> None:
    provider, _ = make_provider(_raise(httpx.ConnectError("connection refused")))

    with pytest.raises(AIUnavailableError) as info:
        provider.generate_json(make_request())

    assert info.value.message == "The local AI service (Ollama) is not reachable."
    assert info.value.retryable is True


@pytest.mark.parametrize(
    "exc", [httpx.ReadTimeout("read timed out"), httpx.ConnectTimeout("connect timed out")]
)
def test_timeout_maps_to_ai_timeout(exc: Exception) -> None:
    provider, _ = make_provider(_raise(exc))

    with pytest.raises(AITimeoutError) as info:
        provider.generate_json(make_request())

    assert info.value.code == "ai_timeout"


def test_other_transport_error_maps_to_unavailable() -> None:
    provider, _ = make_provider(_raise(httpx.RemoteProtocolError("peer closed connection")))

    with pytest.raises(AIUnavailableError):
        provider.generate_json(make_request())


def test_404_maps_to_configuration_error() -> None:
    provider, _ = make_provider(
        lambda request: httpx.Response(404, json={"error": "model 'llama3.1:8b' not found"})
    )

    with pytest.raises(AIConfigurationError) as info:
        provider.generate_json(make_request())

    assert info.value.code == "ai_not_configured"
    assert "llama3.1:8b" in info.value.message


def test_500_maps_to_unavailable() -> None:
    provider, _ = make_provider(lambda request: httpx.Response(500, json={"error": "oom"}))

    with pytest.raises(AIUnavailableError) as info:
        provider.generate_json(make_request())

    assert info.value.retryable is True


def test_400_maps_to_non_retryable_provider_error() -> None:
    provider, _ = make_provider(
        lambda request: httpx.Response(400, json={"error": "invalid format schema"})
    )

    with pytest.raises(AIProviderError) as info:
        provider.generate_json(make_request())

    assert type(info.value) is AIRequestRejectedError
    assert info.value.code == "ai_request_rejected"
    assert info.value.retryable is False
    assert "invalid format schema" not in info.value.message


def test_invalid_json_body_maps_to_provider_error() -> None:
    provider, _ = make_provider(lambda request: httpx.Response(200, text="<html>proxy</html>"))

    with pytest.raises(AIProviderError) as info:
        provider.generate_json(make_request())

    assert type(info.value) is AIProviderError


def test_missing_message_content_maps_to_provider_error() -> None:
    provider, _ = make_provider(lambda request: httpx.Response(200, json={"done": True}))

    with pytest.raises(AIProviderError):
        provider.generate_json(make_request())


def test_configured_and_repr() -> None:
    provider, _ = make_provider(ok())

    assert provider.configured is True
    assert provider.name == "ollama"
    assert provider.development_only is False
    assert "llama3.1:8b" in repr(provider)
