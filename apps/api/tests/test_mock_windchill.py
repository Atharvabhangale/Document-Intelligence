"""MockWindchillDocumentProvider (DEVELOPMENT ONLY sample catalog)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from docintel.core.config import REPO_ROOT, Settings
from docintel.core.errors import (
    ContentNotAvailableError,
    DocumentNotFoundError,
    WindchillProviderError,
)
from docintel.core.models import Requester
from docintel.providers.windchill import (
    MockWindchillDocumentProvider,
    create_windchill_provider,
)
from pdf_factory import make_pdf

REQUESTER = Requester(user_id="dev.user", display_name="Development User")

CATALOG_ENTRIES: list[dict[str, Any]] = [
    {
        "reference": "mock://wtdocument/SOP-00123/A.3",
        "file": "SOP-00123_Machine_Maintenance_A.3.pdf",
        "metadata": {
            "number": "SOP-00123",
            "name": "Machine Maintenance SOP",
            "revision": "A",
            "iteration": "3",
            "state": "Released",
            "location": "Manufacturing SOP Library / Maintenance",
            "documentType": "SOP",
            "modifiedDate": "2026-03-14T09:30:00Z",
            "modifiedBy": "J. Alvarez",
            "sourceRef": "mock://wtdocument/SOP-00123/A.3",
        },
    },
    {
        "reference": "mock://wtdocument/SOP-00087/B.2",
        "file": "SOP-00087_Lockout_Tagout_B.2.pdf",
        "metadata": {
            "number": "SOP-00087",
            "name": "Lockout/Tagout (LOTO) Procedure",
            "revision": "B",
            "iteration": "2",
            "state": "Released",
            "location": "Manufacturing SOP Library / Safety",
            "documentType": "SOP",
        },
    },
]


def write_catalog(
    directory: Path,
    entries: list[dict[str, Any]] | None = None,
    *,
    with_pdfs: bool = True,
) -> Path:
    """Write a catalog (and, by default, a small PDF per entry) into ``directory``."""
    entries = CATALOG_ENTRIES if entries is None else entries
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "catalog.json").write_text(
        json.dumps({"developmentOnly": True, "documents": entries}), encoding="utf-8"
    )
    if with_pdfs:
        for entry in entries:
            name = entry.get("file", "")
            if re.fullmatch(r"[A-Za-z0-9][\w .-]*\.pdf", name):  # plain names only
                number = entry.get("metadata", {}).get("number", "DOC")
                (directory / name).write_bytes(make_pdf([f"{number} page one", "Page two"]))
    return directory


@pytest.fixture
def provider(tmp_path: Path) -> MockWindchillDocumentProvider:
    return MockWindchillDocumentProvider(write_catalog(tmp_path / "samples"))


def test_identity_is_development_only(provider: MockWindchillDocumentProvider) -> None:
    assert provider.name == "mock-windchill"
    assert provider.development_only is True


def test_module_docstring_states_development_only() -> None:
    from docintel.providers.windchill import mock

    assert mock.__doc__ is not None
    assert "DEVELOPMENT ONLY" in mock.__doc__
    assert "NOT connected to Windchill" in mock.__doc__


def test_list_returns_catalog_in_order(provider: MockWindchillDocumentProvider) -> None:
    items = provider.list_documents(requester=REQUESTER)
    assert [d.metadata.number for d in items] == ["SOP-00123", "SOP-00087"]
    assert all(d.development_only for d in items)
    first = items[0]
    assert first.reference == "mock://wtdocument/SOP-00123/A.3"
    assert first.metadata.version_label == "A.3"
    assert first.metadata.state == "Released"
    assert first.primary_content is not None
    assert first.primary_content.media_type == "application/pdf"
    assert first.primary_content.size_bytes and first.primary_content.size_bytes > 0


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("sop-00087", ["SOP-00087"]),  # number, case-insensitive
        ("MAINTENANCE sop", ["SOP-00123"]),  # name
        ("/ safety", ["SOP-00087"]),  # location
        ("manufacturing", ["SOP-00123", "SOP-00087"]),
        ("   ", ["SOP-00123", "SOP-00087"]),  # blank query = everything
        ("no such thing", []),
    ],
)
def test_list_filters_by_substring(
    provider: MockWindchillDocumentProvider, query: str, expected: list[str]
) -> None:
    items = provider.list_documents(requester=REQUESTER, query=query)
    assert [d.metadata.number for d in items] == expected


def test_list_respects_limit(provider: MockWindchillDocumentProvider) -> None:
    assert len(provider.list_documents(requester=REQUESTER, limit=1)) == 1
    assert provider.list_documents(requester=REQUESTER, limit=0) == []


def test_get_document(provider: MockWindchillDocumentProvider) -> None:
    doc = provider.get_document("mock://wtdocument/SOP-00087/B.2", requester=REQUESTER)
    assert doc.metadata.name == "Lockout/Tagout (LOTO) Procedure"
    assert doc.primary_content is not None
    assert doc.primary_content.filename == "SOP-00087_Lockout_Tagout_B.2.pdf"


def test_returned_metadata_is_a_copy(provider: MockWindchillDocumentProvider) -> None:
    ref = "mock://wtdocument/SOP-00087/B.2"
    provider.get_document(ref, requester=REQUESTER).metadata.name = "changed"
    assert provider.get_document(ref, requester=REQUESTER).metadata.name != "changed"


def test_get_primary_content(provider: MockWindchillDocumentProvider, tmp_path: Path) -> None:
    content = provider.get_primary_content("mock://wtdocument/SOP-00123/A.3", requester=REQUESTER)
    assert content.media_type == "application/pdf"
    assert content.filename == "SOP-00123_Machine_Maintenance_A.3.pdf"
    assert content.role == "primary"
    assert content.data == (tmp_path / "samples" / content.filename).read_bytes()
    assert content.data.startswith(b"%PDF-")


def test_unknown_reference(provider: MockWindchillDocumentProvider) -> None:
    with pytest.raises(DocumentNotFoundError):
        provider.get_document("mock://wtdocument/NOPE/A.1", requester=REQUESTER)
    with pytest.raises(DocumentNotFoundError):
        provider.get_primary_content("mock://wtdocument/NOPE/A.1", requester=REQUESTER)


def test_missing_pdf_is_content_not_available(tmp_path: Path) -> None:
    provider = MockWindchillDocumentProvider(write_catalog(tmp_path, with_pdfs=False))
    doc = provider.get_document("mock://wtdocument/SOP-00123/A.3", requester=REQUESTER)
    assert doc.primary_content is not None
    assert doc.primary_content.size_bytes is None
    with pytest.raises(ContentNotAvailableError) as info:
        provider.get_primary_content("mock://wtdocument/SOP-00123/A.3", requester=REQUESTER)
    assert "scripts/generate_samples.py" in info.value.message


@pytest.mark.parametrize(
    "unsafe_file",
    [
        "../outside.pdf",
        "..\\outside.pdf",
        "sub/inner.pdf",
        "/etc/passwd.pdf",
        ".hidden.pdf",
        "..",
        "notes.txt",
        "bad\x00name.pdf",
    ],
)
def test_catalog_file_names_cannot_escape_samples_dir(tmp_path: Path, unsafe_file: str) -> None:
    samples = tmp_path / "samples"
    (tmp_path / "outside.pdf").write_bytes(make_pdf(["secret outside the samples dir"]))
    entries = [
        CATALOG_ENTRIES[0],
        {"reference": "mock://evil", "file": unsafe_file, "metadata": {"name": "Evil"}},
    ]
    provider = MockWindchillDocumentProvider(write_catalog(samples, entries))

    listed = [d.reference for d in provider.list_documents(requester=REQUESTER)]
    assert listed == ["mock://wtdocument/SOP-00123/A.3"]
    with pytest.raises(DocumentNotFoundError):
        provider.get_primary_content("mock://evil", requester=REQUESTER)


def test_symlink_pointing_outside_is_rejected(tmp_path: Path) -> None:
    samples = tmp_path / "samples"
    secret = tmp_path / "secret.pdf"
    secret.write_bytes(make_pdf(["secret"]))
    entries = [{"reference": "mock://link", "file": "link.pdf", "metadata": {"name": "Link"}}]
    write_catalog(samples, entries, with_pdfs=False)
    (samples / "link.pdf").symlink_to(secret)

    provider = MockWindchillDocumentProvider(samples)
    with pytest.raises(DocumentNotFoundError):
        provider.get_primary_content("mock://link", requester=REQUESTER)


def test_invalid_entries_and_duplicates_are_skipped(tmp_path: Path) -> None:
    entries = [
        CATALOG_ENTRIES[0],
        {"reference": "mock://no-metadata", "file": "x.pdf"},
        {**CATALOG_ENTRIES[0], "metadata": {"name": "Duplicate"}},
    ]
    provider = MockWindchillDocumentProvider(write_catalog(tmp_path, entries))
    items = provider.list_documents(requester=REQUESTER)
    assert [d.metadata.name for d in items] == ["Machine Maintenance SOP"]


@pytest.mark.parametrize("catalog_text", [None, "{not json", '{"documents": {}}', "[]"])
def test_unreadable_catalog(tmp_path: Path, catalog_text: str | None) -> None:
    if catalog_text is not None:
        (tmp_path / "catalog.json").write_text(catalog_text, encoding="utf-8")
    provider = MockWindchillDocumentProvider(tmp_path)
    with pytest.raises(WindchillProviderError) as info:
        provider.list_documents(requester=REQUESTER)
    assert str(tmp_path) not in info.value.message  # no server paths in client messages


def test_factory_creates_mock(tmp_path: Path) -> None:
    settings = Settings(windchill_provider="mock", samples_dir=write_catalog(tmp_path))
    provider = create_windchill_provider(settings)
    assert isinstance(provider, MockWindchillDocumentProvider)
    assert len(provider.list_documents(requester=REQUESTER)) == 2


# --- the committed sample catalog ------------------------------------------------------------

SAMPLES_DIR = REPO_ROOT / "samples"


def _repo_provider() -> MockWindchillDocumentProvider:
    provider = MockWindchillDocumentProvider(SAMPLES_DIR)
    items = provider.list_documents(requester=REQUESTER)
    missing = [d.primary_content.filename for d in items if d.primary_content.size_bytes is None]
    if missing:
        pytest.skip(f"sample PDFs not generated (run scripts/generate_samples.py): {missing}")
    return provider


def test_repository_catalog_lists_all_samples() -> None:
    catalog = json.loads((SAMPLES_DIR / "catalog.json").read_text(encoding="utf-8"))
    provider = MockWindchillDocumentProvider(SAMPLES_DIR)
    items = provider.list_documents(requester=REQUESTER, limit=100)
    assert [d.reference for d in items] == [e["reference"] for e in catalog["documents"]]
    assert all(d.development_only for d in items)


def test_repository_samples_have_pdf_content() -> None:
    provider = _repo_provider()
    for doc in provider.list_documents(requester=REQUESTER, limit=100):
        content = provider.get_primary_content(doc.reference, requester=REQUESTER)
        assert content.data.startswith(b"%PDF-")
        assert len(content.data) == doc.primary_content.size_bytes
