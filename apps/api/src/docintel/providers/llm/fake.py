"""Scripted LLM provider for automated tests.

Returns queued responses in order and records every request, so tests can assert on prompt
construction and exercise malformed-output, truncation, refusal and error paths without calling
a real model.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from docintel.providers.llm.base import (
    FinishReason,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    LLMUsage,
)

ScriptItem = str | Exception | LLMResponse | Callable[[LLMRequest], str | LLMResponse]


class ScriptedLLMProvider(LLMProvider):
    name = "scripted"
    development_only = True

    def __init__(
        self,
        responses: Sequence[ScriptItem],
        *,
        model: str = "scripted-model",
        finish_reason: FinishReason = "end",
    ) -> None:
        self.model = model
        self._responses = list(responses)
        self._finish_reason = finish_reason
        self.requests: list[LLMRequest] = []

    def generate_json(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if not self._responses:
            raise AssertionError("ScriptedLLMProvider ran out of scripted responses")
        item = self._responses.pop(0)
        if callable(item) and not isinstance(item, LLMResponse):
            item = item(request)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, LLMResponse):
            return item
        return LLMResponse(
            text=item,
            model=self.model,
            provider=self.name,
            finish_reason=self._finish_reason,
            raw_finish_reason=self._finish_reason,
            usage=LLMUsage(input_tokens=100, output_tokens=50),
            latency_ms=1,
        )
