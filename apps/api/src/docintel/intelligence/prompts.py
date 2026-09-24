"""Versioned prompt library.

Prompts live in ``prompts/<id>.v<N>.md`` (repository root). Each file has a YAML front matter
block followed by the system prompt::

    ---
    id: summarize
    version: "1"
    description: >-
      One-line description.
    instruction: >-
      Task instruction sent after the document.
    ---
    System prompt ...

The active version of a prompt is the file with the highest integer ``N``. Prompt id and version
are recorded in every report's provenance and are part of the report cache key, so changing a
prompt means adding a new version file rather than editing a released one.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_PROMPT_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_FRONT_MATTER_DELIMITER = "---"
_REQUIRED_KEYS = ("id", "version", "instruction")


@dataclass(frozen=True)
class PromptTemplate:
    """A loaded, validated prompt version."""

    id: str
    version: str
    description: str
    instruction: str
    system: str
    path: Path

    @property
    def ref(self) -> str:
        """``"<id>@<version>"``, e.g. ``"summarize@1"``."""
        return f"{self.id}@{self.version}"


class PromptLibrary:
    """Loads prompt templates from a directory and caches them (thread-safe)."""

    def __init__(self, prompts_dir: Path) -> None:
        self._dir = Path(prompts_dir)
        self._cache: dict[str, PromptTemplate] = {}
        self._lock = threading.Lock()

    @property
    def prompts_dir(self) -> Path:
        return self._dir

    def get(self, prompt_id: str) -> PromptTemplate:
        """Return the active (highest) version of ``prompt_id``.

        Raises:
            ValueError: ``prompt_id`` is malformed or the prompt file is invalid.
            FileNotFoundError: no version of the prompt exists.
        """
        if not _PROMPT_ID_RE.fullmatch(prompt_id):
            raise ValueError(f"Invalid prompt id {prompt_id!r}.")
        with self._lock:
            cached = self._cache.get(prompt_id)
            if cached is None:
                cached = load_prompt(self._active_path(prompt_id))
                self._cache[prompt_id] = cached
            return cached

    def _active_path(self, prompt_id: str) -> Path:
        pattern = re.compile(rf"^{re.escape(prompt_id)}\.v(\d+)\.md$")
        versions: list[tuple[int, Path]] = []
        if self._dir.is_dir():
            for path in self._dir.iterdir():
                match = pattern.fullmatch(path.name)
                if match and path.is_file():
                    versions.append((int(match.group(1)), path))
        if not versions:
            raise FileNotFoundError(f"No prompt file '{prompt_id}.v<N>.md' found in {self._dir}.")
        return max(versions, key=lambda item: item[0])[1]


def load_prompt(path: Path) -> PromptTemplate:
    """Parse and validate one prompt file.

    The file name must be ``<id>.v<N>.md`` and agree with the front matter ``id`` and
    ``version``.

    Raises:
        ValueError: the file is malformed.
    """
    match = re.fullmatch(r"(?P<id>[a-z][a-z0-9_-]*)\.v(?P<version>\d+)\.md", path.name)
    if match is None:
        raise ValueError(f"Prompt file name {path.name!r} does not match '<id>.v<N>.md'.")
    front_matter, body = _split_front_matter(path.read_text(encoding="utf-8"), path)
    for key in _REQUIRED_KEYS:
        if key not in front_matter:
            raise ValueError(f"Prompt {path.name}: front matter is missing '{key}'.")

    prompt_id = _require_text(front_matter, "id", path)
    if prompt_id != match.group("id"):
        raise ValueError(
            f"Prompt {path.name}: front matter id {prompt_id!r} does not match the file name."
        )
    version = _version_text(front_matter["version"], path)
    if int(version) != int(match.group("version")):
        raise ValueError(
            f"Prompt {path.name}: front matter version {version!r} does not match the file name."
        )
    description = front_matter.get("description") or ""
    if not isinstance(description, str):
        raise ValueError(f"Prompt {path.name}: 'description' must be a string.")
    system = body.strip()
    if not system:
        raise ValueError(f"Prompt {path.name}: the system prompt (file body) is empty.")

    return PromptTemplate(
        id=prompt_id,
        version=version,
        description=description.strip(),
        instruction=_require_text(front_matter, "instruction", path),
        system=system,
        path=path,
    )


def _split_front_matter(text: str, path: Path) -> tuple[dict[str, Any], str]:
    lines = text.lstrip("\ufeff").splitlines(keepends=True)
    if not lines or lines[0].strip() != _FRONT_MATTER_DELIMITER:
        raise ValueError(f"Prompt {path.name}: missing YAML front matter (must start with '---').")
    for index in range(1, len(lines)):
        if lines[index].strip() == _FRONT_MATTER_DELIMITER:
            raw_front_matter = "".join(lines[1:index])
            body = "".join(lines[index + 1 :])
            break
    else:
        raise ValueError(f"Prompt {path.name}: front matter is not closed with '---'.")
    try:
        data = yaml.safe_load(raw_front_matter)
    except yaml.YAMLError as exc:
        raise ValueError(f"Prompt {path.name}: front matter is not valid YAML.") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Prompt {path.name}: front matter must be a YAML mapping.")
    return data, body


def _require_text(data: dict[str, Any], key: str, path: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Prompt {path.name}: '{key}' must be a non-empty string.")
    return value.strip()


def _version_text(value: object, path: Path) -> str:
    # ``version: 1`` (int) and ``version: "1"`` (str) are both accepted; bools are not.
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise ValueError(f"Prompt {path.name}: 'version' must be a positive integer.")
    text = str(value).strip()
    if not (text.isascii() and text.isdigit()) or int(text) < 1:
        raise ValueError(f"Prompt {path.name}: 'version' must be a positive integer.")
    return str(int(text))
