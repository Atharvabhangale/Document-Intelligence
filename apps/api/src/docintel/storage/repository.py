"""File-based storage for documents, extracted text and analysis reports.

Layout under ``DATA_DIR``::

    documents/<document_id>/record.json      DocumentRecord
    documents/<document_id>/content.bin      original bytes (never served by filename)
    documents/<document_id>/pages.json       ExtractedDocument
    reports/<cache_key>.json                 cached report JSON (keyed by content + pipeline)
    reports/index/<document_id>/<task>.json  pointer to the latest report per document/task

Identifiers are generated server-side and validated before touching the filesystem, so user
input (file names, references) never becomes a path. Writes are atomic (temp file + rename).

This is deliberately simple for V1; the interfaces allow a database-backed implementation.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from docintel.core.errors import DocumentNotFoundError
from docintel.core.models import DocumentRecord, ExtractedDocument

_ID_RE = re.compile(r"^[a-f0-9]{32}$")
_KEY_RE = re.compile(r"^[a-f0-9]{64}$")
_TASK_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")


def _check_id(document_id: str) -> str:
    if not _ID_RE.fullmatch(document_id):
        raise DocumentNotFoundError()
    return document_id


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


class DocumentRepository(ABC):
    @abstractmethod
    def save(self, record: DocumentRecord, content: bytes, extracted: ExtractedDocument) -> None: ...

    @abstractmethod
    def get(self, document_id: str) -> DocumentRecord: ...

    @abstractmethod
    def get_content(self, document_id: str) -> bytes: ...

    @abstractmethod
    def get_extracted(self, document_id: str) -> ExtractedDocument: ...

    @abstractmethod
    def exists(self, document_id: str) -> bool: ...

    @abstractmethod
    def list(self, limit: int = 50) -> list[DocumentRecord]: ...


class ReportRepository(ABC):
    @abstractmethod
    def get(self, cache_key: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def put(self, cache_key: str, document_id: str, task: str, report: dict[str, Any]) -> None: ...

    @abstractmethod
    def latest(self, document_id: str, task: str) -> dict[str, Any] | None: ...


class FileDocumentRepository(DocumentRepository):
    def __init__(self, data_dir: Path) -> None:
        self._root = Path(data_dir) / "documents"
        self._lock = threading.Lock()

    def _dir(self, document_id: str) -> Path:
        return self._root / _check_id(document_id)

    def save(self, record: DocumentRecord, content: bytes, extracted: ExtractedDocument) -> None:
        d = self._dir(record.id)
        with self._lock:
            _atomic_write(d / "content.bin", content)
            _atomic_write(d / "pages.json", extracted.model_dump_json().encode("utf-8"))
            # record.json last: its presence marks a complete document.
            _atomic_write(d / "record.json", record.model_dump_json().encode("utf-8"))

    def get(self, document_id: str) -> DocumentRecord:
        path = self._dir(document_id) / "record.json"
        if not path.is_file():
            raise DocumentNotFoundError()
        return DocumentRecord.model_validate_json(path.read_bytes())

    def get_content(self, document_id: str) -> bytes:
        path = self._dir(document_id) / "content.bin"
        if not (self._dir(document_id) / "record.json").is_file() or not path.is_file():
            raise DocumentNotFoundError()
        return path.read_bytes()

    def get_extracted(self, document_id: str) -> ExtractedDocument:
        path = self._dir(document_id) / "pages.json"
        if not (self._dir(document_id) / "record.json").is_file() or not path.is_file():
            raise DocumentNotFoundError()
        return ExtractedDocument.model_validate_json(path.read_bytes())

    def exists(self, document_id: str) -> bool:
        try:
            return (self._dir(document_id) / "record.json").is_file()
        except DocumentNotFoundError:
            return False

    def list(self, limit: int = 50) -> list[DocumentRecord]:
        if not self._root.is_dir():
            return []
        records: list[DocumentRecord] = []
        for child in self._root.iterdir():
            rec = child / "record.json"
            if _ID_RE.fullmatch(child.name) and rec.is_file():
                try:
                    records.append(DocumentRecord.model_validate_json(rec.read_bytes()))
                except ValueError:
                    continue  # skip corrupt entries rather than failing the listing
        records.sort(key=lambda r: r.created_at, reverse=True)
        return records[:limit]


class FileReportRepository(ReportRepository):
    def __init__(self, data_dir: Path) -> None:
        self._root = Path(data_dir) / "reports"
        self._lock = threading.Lock()

    def get(self, cache_key: str) -> dict[str, Any] | None:
        if not _KEY_RE.fullmatch(cache_key):
            return None
        path = self._root / f"{cache_key}.json"
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_bytes())
        except ValueError:
            return None

    def put(self, cache_key: str, document_id: str, task: str, report: dict[str, Any]) -> None:
        if not _KEY_RE.fullmatch(cache_key) or not _TASK_RE.fullmatch(task):
            raise ValueError("invalid cache key or task")
        _check_id(document_id)
        payload = json.dumps(report, ensure_ascii=False).encode("utf-8")
        pointer = json.dumps({"cacheKey": cache_key}).encode("utf-8")
        with self._lock:
            _atomic_write(self._root / f"{cache_key}.json", payload)
            _atomic_write(self._root / "index" / document_id / f"{task}.json", pointer)

    def latest(self, document_id: str, task: str) -> dict[str, Any] | None:
        try:
            _check_id(document_id)
        except DocumentNotFoundError:
            return None
        if not _TASK_RE.fullmatch(task):
            return None
        pointer = self._root / "index" / document_id / f"{task}.json"
        if not pointer.is_file():
            return None
        try:
            key = json.loads(pointer.read_bytes())["cacheKey"]
        except (ValueError, KeyError):
            return None
        return self.get(key)


class InMemoryReportRepository(ReportRepository):
    """Report cache for tests."""

    def __init__(self) -> None:
        self._items: dict[str, dict[str, Any]] = {}
        self._latest: dict[tuple[str, str], str] = {}

    def get(self, cache_key: str) -> dict[str, Any] | None:
        item = self._items.get(cache_key)
        return json.loads(json.dumps(item)) if item is not None else None

    def put(self, cache_key: str, document_id: str, task: str, report: dict[str, Any]) -> None:
        self._items[cache_key] = json.loads(json.dumps(report))
        self._latest[(document_id, task)] = cache_key

    def latest(self, document_id: str, task: str) -> dict[str, Any] | None:
        key = self._latest.get((document_id, task))
        return self.get(key) if key else None
