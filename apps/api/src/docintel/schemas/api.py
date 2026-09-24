"""API request/response models that are not part of the AI report contract."""

from __future__ import annotations

from typing import Any, Literal

from docintel.core.models import ApiModel, DocumentRecord, ExtractedPage
from docintel.providers.windchill.base import WindchillDocument


class ErrorBody(ApiModel):
    code: str
    message: str
    retryable: bool
    details: dict[str, Any] | None = None


class ErrorResponse(ApiModel):
    error: ErrorBody


class SourceProviderInfo(ApiModel):
    name: str
    development_only: bool


class AIInfo(ApiModel):
    provider: str
    model: str
    configured: bool
    development_only: bool


class Limits(ApiModel):
    max_upload_mb: int
    max_pages: int
    max_question_chars: int


class HealthResponse(ApiModel):
    status: Literal["ok"] = "ok"
    version: str
    ai: AIInfo
    windchill: SourceProviderInfo
    limits: Limits


class WindchillDocumentList(ApiModel):
    provider: SourceProviderInfo
    items: list[WindchillDocument]


class ImportFromWindchillRequest(ApiModel):
    reference: str


class DocumentList(ApiModel):
    items: list[DocumentRecord]


class DocumentPages(ApiModel):
    document_id: str
    pages: list[ExtractedPage]
