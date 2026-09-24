"""Shared pytest fixtures."""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

# Make ``tests`` helpers (pdf_factory) importable as top-level modules.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from docintel.core.config import REPO_ROOT, Settings
from docintel.core.models import (
    ContentFile,
    DocumentMetadata,
    DocumentRecord,
    DocumentSource,
    ExtractedDocument,
    ExtractedPage,
    ExtractionSummary,
)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Isolated settings: temp data dir, fake-free defaults, no real credentials needed."""
    return Settings(
        ai_provider="anthropic",
        ai_model="claude-haiku-4-5-20251001",
        anthropic_api_key="test-key-not-real",
        data_dir=tmp_path / "data",
        prompts_dir=REPO_ROOT / "prompts",
        samples_dir=REPO_ROOT / "samples",
        windchill_provider="mock",
        serve_web_dist=None,
    )


def make_extracted(pages: list[str], extractor: str = "test-extractor 1.0") -> ExtractedDocument:
    return ExtractedDocument(
        page_count=len(pages),
        pages=[
            ExtractedPage(
                number=i + 1,
                text=t,
                char_count=len(t),
                has_text_layer=bool(t),
                needs_ocr=False,
            )
            for i, t in enumerate(pages)
        ],
        extractor=extractor,
    )


def make_record(
    extracted: ExtractedDocument,
    *,
    document_id: str = "0" * 31 + "1",
    sha256: str = "a" * 64,
    state: str | None = "Released",
) -> DocumentRecord:
    return DocumentRecord(
        id=document_id,
        source=DocumentSource.WINDCHILL,
        source_provider="mock-windchill",
        development_only=True,
        metadata=DocumentMetadata(
            number="SOP-00123",
            name="Machine Maintenance SOP",
            revision="A",
            iteration="3",
            state=state,
            location="Library / Maintenance",
            document_type="SOP",
            modified_date=datetime(2026, 3, 14, 9, 30, tzinfo=UTC),
            modified_by="J. Alvarez",
            source_ref="mock://wtdocument/SOP-00123/A.3",
        ),
        content=ContentFile(
            filename="SOP-00123_Machine_Maintenance_A.3.pdf",
            size_bytes=1234,
            sha256=sha256,
            role="primary",
        ),
        extraction=ExtractionSummary.from_extracted(extracted),
        created_at=datetime(2026, 9, 24, 10, 0, tzinfo=UTC),
    )


def live_tests_enabled() -> bool:
    return os.environ.get("DOCINTEL_LIVE_TESTS") == "1"
