"""Registry of intelligence tasks.

A task binds a prompt, the model output schema, the assembler that turns validated output into
the API result, and whether results are cached. Adding a task means adding a prompt file
(``prompts/<id>.v1.md``), an output model and a result model (``schemas/report.py``), an
assembler (``assemble.py``) and an entry here.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel

from docintel.intelligence.assemble import (
    AssemblyContext,
    assemble_answer,
    assemble_requirements,
    assemble_risks,
    assemble_summarize,
)
from docintel.schemas.report import (
    AskResponse,
    DocumentIntelligenceReport,
    LLMAnswerOutput,
    LLMModel,
    LLMRequirementsOutput,
    LLMRisksOutput,
    LLMSummarizeOutput,
    RequirementsReport,
    RisksReport,
    TaskName,
)

OutputT = TypeVar("OutputT", bound=LLMModel)
ResultT = TypeVar("ResultT", bound=BaseModel)

#: Tasks whose results are reports (cacheable, retrievable later).
ReportTaskName = Literal["summarize", "requirements", "risks"]


@dataclass(frozen=True)
class TaskSpec(Generic[OutputT, ResultT]):
    name: TaskName
    prompt_id: str
    output_model: type[OutputT]  # what the model must return (validated)
    result_model: type[ResultT]  # what the API returns (also used to re-validate cache entries)
    assembler: Callable[[OutputT, AssemblyContext], ResultT]
    cacheable: bool


SUMMARIZE: TaskSpec[LLMSummarizeOutput, DocumentIntelligenceReport] = TaskSpec(
    name="summarize",
    prompt_id="summarize",
    output_model=LLMSummarizeOutput,
    result_model=DocumentIntelligenceReport,
    assembler=assemble_summarize,
    cacheable=True,
)

REQUIREMENTS: TaskSpec[LLMRequirementsOutput, RequirementsReport] = TaskSpec(
    name="requirements",
    prompt_id="requirements",
    output_model=LLMRequirementsOutput,
    result_model=RequirementsReport,
    assembler=assemble_requirements,
    cacheable=True,
)

RISKS: TaskSpec[LLMRisksOutput, RisksReport] = TaskSpec(
    name="risks",
    prompt_id="risks",
    output_model=LLMRisksOutput,
    result_model=RisksReport,
    assembler=assemble_risks,
    cacheable=True,
)

ASK: TaskSpec[LLMAnswerOutput, AskResponse] = TaskSpec(
    name="ask",
    prompt_id="ask",
    output_model=LLMAnswerOutput,
    result_model=AskResponse,
    assembler=assemble_answer,
    cacheable=False,
)

TASKS: Mapping[str, TaskSpec[Any, Any]] = MappingProxyType(
    {spec.name: spec for spec in (SUMMARIZE, REQUIREMENTS, RISKS, ASK)}
)


def get_task(name: str) -> TaskSpec[Any, Any]:
    """Return the task named ``name``.

    Raises:
        KeyError: no such task.
    """
    try:
        return TASKS[name]
    except KeyError:
        raise KeyError(f"Unknown intelligence task {name!r}.") from None
