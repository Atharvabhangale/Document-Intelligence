"""Prompt library: loading, front matter validation and version selection."""

from __future__ import annotations

from pathlib import Path

import pytest

from docintel.core.config import REPO_ROOT
from docintel.intelligence.prompts import PromptLibrary, PromptTemplate, load_prompt

REAL_PROMPTS = REPO_ROOT / "prompts"


def _write(directory: Path, name: str, text: str) -> Path:
    path = directory / name
    path.write_text(text, encoding="utf-8")
    return path


def _prompt_text(
    prompt_id: str = "demo",
    version: str = '"1"',
    *,
    instruction: str = "Do the task.",
    body: str = "You are a test system prompt.",
    description: str | None = "A demo prompt.",
) -> str:
    lines = ["---", f"id: {prompt_id}", f"version: {version}"]
    if description is not None:
        lines.append(f"description: {description}")
    lines.append(f"instruction: {instruction}")
    lines.append("---")
    return "\n".join(lines) + "\n" + body + "\n"


# --- real prompt files -------------------------------------------------------------------------


@pytest.mark.parametrize("prompt_id", ["summarize", "requirements", "risks", "ask"])
def test_loads_real_prompt_files(prompt_id: str) -> None:
    prompt = PromptLibrary(REAL_PROMPTS).get(prompt_id)

    assert isinstance(prompt, PromptTemplate)
    assert prompt.id == prompt_id
    assert prompt.version == "1"
    assert prompt.ref == f"{prompt_id}@1"
    assert prompt.path == REAL_PROMPTS / f"{prompt_id}.v1.md"
    assert prompt.description
    assert prompt.instruction and "JSON" in prompt.instruction
    # The body (system prompt) excludes the front matter and is stripped.
    assert prompt.system
    assert not prompt.system.startswith("---")
    assert "instruction:" not in prompt.system
    assert prompt.system == prompt.system.strip()
    assert "<document>" in prompt.system


def test_system_prompt_is_the_file_body() -> None:
    text = (REAL_PROMPTS / "summarize.v1.md").read_text(encoding="utf-8")
    body = text.split("---", 2)[2].strip()

    assert PromptLibrary(REAL_PROMPTS).get("summarize").system == body


def test_library_caches_templates() -> None:
    library = PromptLibrary(REAL_PROMPTS)

    assert library.get("ask") is library.get("ask")


# --- version selection -------------------------------------------------------------------------


def test_highest_integer_version_is_active(tmp_path: Path) -> None:
    _write(tmp_path, "demo.v1.md", _prompt_text(version='"1"', body="one"))
    _write(tmp_path, "demo.v2.md", _prompt_text(version='"2"', body="two"))
    _write(tmp_path, "demo.v10.md", _prompt_text(version='"10"', body="ten"))

    prompt = PromptLibrary(tmp_path).get("demo")

    assert prompt.version == "10"  # numeric, not lexicographic ("v2" > "v10" as strings)
    assert prompt.system == "ten"
    assert prompt.path.name == "demo.v10.md"


def test_version_selection_with_v1_and_v2(tmp_path: Path) -> None:
    _write(tmp_path, "demo.v1.md", _prompt_text(version='"1"', body="one"))
    _write(tmp_path, "demo.v2.md", _prompt_text(version="2", body="two"))  # unquoted int

    prompt = PromptLibrary(tmp_path).get("demo")

    assert prompt.version == "2"
    assert prompt.system == "two"


def test_unrelated_files_are_ignored(tmp_path: Path) -> None:
    _write(tmp_path, "demo.v1.md", _prompt_text(version='"1"', body="one"))
    _write(tmp_path, "demo.v9.md.bak", "not a prompt")
    _write(tmp_path, "demo.vX.md", "not a prompt")
    _write(tmp_path, "demo-extra.v5.md", _prompt_text("demo-extra", '"5"'))
    _write(tmp_path, "otherdemo.v7.md", _prompt_text("otherdemo", '"7"'))

    prompt = PromptLibrary(tmp_path).get("demo")

    assert prompt.version == "1"


def test_missing_prompt_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="nothing"):
        PromptLibrary(tmp_path).get("nothing")


def test_missing_directory_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        PromptLibrary(tmp_path / "does-not-exist").get("summarize")


@pytest.mark.parametrize("prompt_id", ["../summarize", "Summarize", "", "a/b", "sum marize"])
def test_invalid_prompt_ids_are_rejected(prompt_id: str) -> None:
    with pytest.raises(ValueError, match="Invalid prompt id"):
        PromptLibrary(REAL_PROMPTS).get(prompt_id)


# --- front matter validation -------------------------------------------------------------------


def test_minimal_prompt_without_description(tmp_path: Path) -> None:
    path = _write(tmp_path, "demo.v1.md", _prompt_text(description=None))

    prompt = load_prompt(path)

    assert prompt.description == ""
    assert prompt.instruction == "Do the task."
    assert prompt.system == "You are a test system prompt."


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("You are a prompt without front matter.\n", "missing YAML front matter"),
        ("---\nid: demo\nversion: '1'\ninstruction: x\nbody without closing\n", "not closed"),
        ("---\n- id\n- version\n---\nbody\n", "must be a YAML mapping"),
        ("---\nid: [unclosed\n---\nbody\n", "not valid YAML"),
        ("---\nversion: '1'\ninstruction: x\n---\nbody\n", "missing 'id'"),
        ("---\nid: demo\ninstruction: x\n---\nbody\n", "missing 'version'"),
        ("---\nid: demo\nversion: '1'\n---\nbody\n", "missing 'instruction'"),
        ("---\nid: demo\nversion: '1'\ninstruction: '  '\n---\nbody\n", "'instruction' must be"),
        ("---\nid: other\nversion: '1'\ninstruction: x\n---\nbody\n", "does not match the file"),
        ("---\nid: demo\nversion: '2'\ninstruction: x\n---\nbody\n", "version '2' does not match"),
        ("---\nid: demo\nversion: true\ninstruction: x\n---\nbody\n", "positive integer"),
        ("---\nid: demo\nversion: 'v1'\ninstruction: x\n---\nbody\n", "positive integer"),
        ("---\nid: demo\nversion: '1'\ninstruction: x\n---\n   \n", "system prompt"),
        ("---\nid: demo\nversion: '1'\ninstruction: x\ndescription: [1]\n---\nb\n", "description"),
    ],
)
def test_front_matter_errors(tmp_path: Path, text: str, message: str) -> None:
    path = _write(tmp_path, "demo.v1.md", text)

    with pytest.raises(ValueError, match=message):
        load_prompt(path)


def test_invalid_active_prompt_raises_through_library(tmp_path: Path) -> None:
    _write(tmp_path, "demo.v1.md", _prompt_text())
    _write(tmp_path, "demo.v2.md", "no front matter")

    with pytest.raises(ValueError, match=r"demo\.v2\.md"):
        PromptLibrary(tmp_path).get("demo")


def test_file_name_must_follow_convention(tmp_path: Path) -> None:
    path = _write(tmp_path, "demo.md", _prompt_text())

    with pytest.raises(ValueError, match="does not match"):
        load_prompt(path)


def test_byte_order_mark_is_tolerated(tmp_path: Path) -> None:
    path = _write(tmp_path, "demo.v1.md", "\ufeff" + _prompt_text())

    assert load_prompt(path).id == "demo"
