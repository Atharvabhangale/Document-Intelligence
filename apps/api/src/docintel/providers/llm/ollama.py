"""Ollama provider for local / on-premise models (``POST /api/chat``).

NOTE: this provider has NOT been validated against a live Ollama server yet. It follows the
documented ``/api/chat`` request/response fields only and is covered by mocked-transport tests.
Validate it (structured-output quality, context size, latency) with the chosen local model before
relying on it.

The request's JSON Schema is passed as ``format`` (Ollama structured outputs). The document text
and the instruction are sent in one user message; the system prompt as a system message.
Nothing from the request or the response body is logged.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from docintel.core.errors import (
    AIConfigurationError,
    AIProviderError,
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

_DONE_REASONS: dict[str, FinishReason] = {"stop": "end", "length": "max_tokens"}


class OllamaProvider(LLMProvider):
    """LLM provider backed by an Ollama server's chat endpoint (non-streaming)."""

    name = "ollama"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        num_ctx: int,
        timeout_seconds: float,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.model = model
        self._chat_url = f"{base_url.rstrip('/')}/api/chat"
        self._num_ctx = num_ctx
        self._timeout_seconds = timeout_seconds
        self._http = http_client or httpx.Client(timeout=timeout_seconds)

    @property
    def configured(self) -> bool:
        """Configuration is complete when a model is set; reachability is checked per call."""
        return bool(self.model)

    def __repr__(self) -> str:
        return f"OllamaProvider(model={self.model!r}, url={self._chat_url!r})"

    def generate_json(self, request: LLMRequest) -> LLMResponse:
        body = self._build_body(request)
        started = time.perf_counter()
        try:
            response = self._http.post(self._chat_url, json=body, timeout=self._timeout_seconds)
        except httpx.TimeoutException:
            self._log_failure("timeout")
            raise AITimeoutError() from None
        except httpx.ConnectError:
            self._log_failure("connect_error")
            raise AIUnavailableError("The local AI service (Ollama) is not reachable.") from None
        except httpx.TransportError as exc:
            self._log_failure(type(exc).__name__)
            raise AIUnavailableError("The local AI service (Ollama) is not reachable.") from None
        latency_ms = round((time.perf_counter() - started) * 1000)

        self._raise_for_status(response)
        payload = self._parse_payload(response)

        raw_done = payload.get("done_reason")
        raw_done = raw_done if isinstance(raw_done, str) else None
        return LLMResponse(
            text=payload["message"]["content"],
            model=payload.get("model") or self.model,
            provider=self.name,
            finish_reason=_DONE_REASONS.get(raw_done or "", "other"),
            raw_finish_reason=raw_done,
            usage=LLMUsage(
                input_tokens=_int_or_none(payload.get("prompt_eval_count")),
                output_tokens=_int_or_none(payload.get("eval_count")),
            ),
            latency_ms=latency_ms,
        )

    def _build_body(self, request: LLMRequest) -> dict[str, Any]:
        options: dict[str, Any] = {
            "num_ctx": self._num_ctx,
            # Maximum number of tokens to generate (documented Ollama option).
            "num_predict": request.max_output_tokens,
        }
        if request.temperature is not None:
            options["temperature"] = request.temperature
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": request.system},
                {
                    "role": "user",
                    "content": f"{request.document_context}\n\n{request.instruction}",
                },
            ],
            "format": request.json_schema,
            "stream": False,
            "options": options,
        }

    def _raise_for_status(self, response: httpx.Response) -> None:
        status = response.status_code
        if status < 400:
            return
        self._log_failure("http_error", status)
        if status == 404:
            raise AIConfigurationError(
                f"The configured local AI model is not available in Ollama: {self.model}. "
                "Make sure the model has been pulled."
            )
        if status >= 500:
            raise AIUnavailableError("The local AI service (Ollama) returned a server error.")
        error = AIProviderError("The local AI service (Ollama) rejected the request.")
        error.retryable = False
        raise error

    def _parse_payload(self, response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError:
            self._log_failure("invalid_json", response.status_code)
            raise AIProviderError(
                "The local AI service (Ollama) returned an invalid response."
            ) from None
        message = payload.get("message") if isinstance(payload, dict) else None
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            self._log_failure("unexpected_response", response.status_code)
            raise AIProviderError("The local AI service (Ollama) returned an invalid response.")
        return payload

    def _log_failure(self, kind: str, status: int | None = None) -> None:
        logger.warning("Ollama request failed: error=%s status=%s", kind, status)


def _int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
