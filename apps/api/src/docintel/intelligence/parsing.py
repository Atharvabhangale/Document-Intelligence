"""Parsing and validation of raw LLM output.

Providers return raw text that *should* be a single JSON object matching the task's output
model. This module tolerates the common harmless deviations (surrounding whitespace, one
Markdown code fence, prose around the object) and validates the result with Pydantic.

On failure it raises ``OutputValidationFailure`` with a compact list of problems (JSON path and
message only, never the model's output) that the service sends back to the model as repair
feedback and logs as counts/paths.
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

FailureKind = Literal["empty", "invalid_json", "not_object", "schema"]

#: Maximum number of problems listed in a failure (the rest are summarized as a count).
MAX_PROBLEMS = 20
_MAX_MESSAGE_CHARS = 160
_MAX_PATH_SEGMENT_CHARS = 60

_FENCE_RE = re.compile(r"\A```[A-Za-z0-9_+-]*[ \t]*\r?\n?(?P<body>.*?)\r?\n?[ \t]*```\Z", re.DOTALL)


class OutputValidationFailure(Exception):
    """The model output is not valid JSON for the expected model (internal, not an API error).

    Attributes:
        kind: what went wrong at the top level.
        problems: human-readable problems (``"<json path>: <message>"``), at most
            ``MAX_PROBLEMS`` entries plus a trailing "... and N more" line.
        paths: JSON paths of the listed problems (safe to log).
        total: total number of problems found.
    """

    def __init__(
        self,
        kind: FailureKind,
        problems: list[str],
        *,
        paths: list[str] | None = None,
        total: int | None = None,
    ) -> None:
        self.kind = kind
        self.problems = problems
        self.paths = paths or []
        self.total = total if total is not None else len(problems)
        super().__init__(f"LLM output failed validation ({kind}, {self.total} problem(s))")

    def feedback(self) -> str:
        """The problem list as a bullet list, for the repair instruction."""
        return "\n".join(f"- {problem}" for problem in self.problems)


def parse_llm_output(text: str, model_cls: type[T]) -> T:
    """Parse ``text`` as JSON and validate it as ``model_cls``.

    Raises:
        OutputValidationFailure: the text is not a JSON object matching ``model_cls``.
    """
    data = _load_json_object(text)
    try:
        return model_cls.model_validate(data)
    except ValidationError as exc:
        raise _schema_failure(exc) from None


def _load_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if not stripped:
        raise OutputValidationFailure("empty", ["(root): the response was empty"], paths=["(root)"])
    fenced = _FENCE_RE.match(stripped)
    if fenced:
        stripped = fenced.group("body").strip()

    try:
        data = json.loads(stripped)
    except ValueError as exc:
        data = _outermost_object(stripped)
        if data is None:
            raise OutputValidationFailure(
                "invalid_json",
                [f"(root): the response is not valid JSON ({_describe_json_error(exc)})"],
                paths=["(root)"],
            ) from None

    if not isinstance(data, dict):
        raise OutputValidationFailure(
            "not_object",
            [f"(root): expected a JSON object, got {_json_type(data)}"],
            paths=["(root)"],
        )
    return data


def _outermost_object(text: str) -> dict[str, Any] | None:
    """Return the JSON object spanning the first ``{`` to the last ``}``, if it parses."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _describe_json_error(exc: ValueError) -> str:
    if isinstance(exc, json.JSONDecodeError):
        # Message and position only; never echo the document.
        return f"{exc.msg} at line {exc.lineno} column {exc.colno}"
    return "unparseable input"


def _schema_failure(exc: ValidationError) -> OutputValidationFailure:
    problems: list[str] = []
    paths: list[str] = []
    seen: set[str] = set()
    for error in exc.errors(include_url=False, include_input=False, include_context=False):
        path = _format_path(error.get("loc", ()))
        problem = f"{path}: {_truncate(error.get('msg', 'invalid value'), _MAX_MESSAGE_CHARS)}"
        if problem in seen:
            continue
        seen.add(problem)
        problems.append(problem)
        paths.append(path)
    total = len(problems)
    if total > MAX_PROBLEMS:
        problems = [*problems[:MAX_PROBLEMS], f"... and {total - MAX_PROBLEMS} more problem(s)"]
        paths = paths[:MAX_PROBLEMS]
    return OutputValidationFailure("schema", problems, paths=paths, total=total)


def _format_path(loc: tuple[int | str, ...]) -> str:
    """``("summary", "keyPoints", 2, "text")`` -> ``"summary.keyPoints[2].text"``."""
    path = ""
    for segment in loc:
        if isinstance(segment, int):
            path += f"[{segment}]"
        else:
            name = _truncate(str(segment), _MAX_PATH_SEGMENT_CHARS)
            path += f".{name}" if path else name
    return path or "(root)"


def _json_type(value: object) -> str:
    if isinstance(value, list):
        return "an array"
    if isinstance(value, str):
        return "a string"
    if isinstance(value, bool):
        return "a boolean"
    if isinstance(value, int | float):
        return "a number"
    if value is None:
        return "null"
    return type(value).__name__


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "\u2026"
