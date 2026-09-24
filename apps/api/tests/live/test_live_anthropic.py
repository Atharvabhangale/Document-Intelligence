"""One small real call to the configured Anthropic model (costs a few hundred tokens).

Run with: ``DOCINTEL_LIVE_TESTS=1 uv run --project apps/api pytest apps/api/tests/live -q``
The credential is read by ``Settings`` from ``ANTHROPIC_API_KEY`` / ``CAD_ANTHROPIC_API_KEY``.
"""

from __future__ import annotations

import os

import pytest

from docintel.core.config import Settings
from docintel.providers.llm.anthropic import AnthropicProvider
from docintel.providers.llm.base import LLMRequest
from docintel.schemas.report import LLMAnswerOutput, llm_json_schema

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("DOCINTEL_LIVE_TESTS") != "1", reason="set DOCINTEL_LIVE_TESTS=1"
    ),
]

PAGE_1 = (
    "1. PURPOSE\nThis procedure defines the daily start-up check of the hydraulic press HP-200."
)
PAGE_2 = (
    "2. START-UP\n"
    "The hydraulic oil temperature shall be between 40-60 °C before the press is started.\n"
    "Operators shall wear safety glasses at all times."
)
DOCUMENT = (
    f'<document>\n<page number="1">{PAGE_1}</page>\n<page number="2">{PAGE_2}</page>\n</document>'
)
SYSTEM = (
    "You answer questions about a single controlled document. Answer ONLY from the content "
    "inside <document>. Cite passages: page = the number attribute of the <page> element; "
    "quote = a 5-25 word excerpt copied character-for-character from that page. "
    "Plain text only."
)


def test_live_answer_validates() -> None:
    settings = Settings()
    if settings.anthropic_api_key is None or not settings.anthropic_api_key.get_secret_value():
        pytest.skip("no Anthropic credential configured")
    provider = AnthropicProvider(
        api_key=settings.anthropic_api_key.get_secret_value(),
        model=settings.ai_model,
        base_url=settings.anthropic_base_url,
        timeout_seconds=60,
    )
    request = LLMRequest(
        system=SYSTEM,
        document_context=DOCUMENT,
        instruction=(
            "Answer the user's question about the document above.\n"
            "<question>What oil temperature is required before starting the press?</question>"
        ),
        json_schema=llm_json_schema(LLMAnswerOutput),
        schema_name="ask",
        max_output_tokens=1024,
        temperature=settings.ai_temperature,
    )

    response = provider.generate_json(request)

    assert response.finish_reason == "end", response.raw_finish_reason
    assert response.provider == "anthropic"
    assert response.usage.input_tokens and response.usage.output_tokens
    answer = LLMAnswerOutput.model_validate_json(response.text)
    assert answer.answerable is True
    assert "40" in answer.answer
    assert answer.sources
    assert any(source.page == 2 for source in answer.sources)
