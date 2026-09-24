"""Development test harness: run PDFs through the complete pipeline and print a quality report.

Runs the same components as the API (extractor, LLM provider, intelligence service) without the
HTTP layer. Catalog samples are imported through the mock Windchill provider (DEVELOPMENT ONLY)
so they carry realistic metadata; any other PDF is ingested like an upload.

Examples (from the repository root):

    # all catalog samples, configured provider (Anthropic Haiku by default)
    uv run --project apps/api python scripts/harness.py

    # offline, deterministic canned output (no API calls)
    uv run --project apps/api python scripts/harness.py --provider fake

    # one file, a different task, or a question
    uv run --project apps/api python scripts/harness.py samples/SOP-00087_Lockout_Tagout_B.2.pdf
    uv run --project apps/api python scripts/harness.py --task requirements
    uv run --project apps/api python scripts/harness.py --task ask --question "What PPE is needed?"

Each run uses a fresh data directory under .data/harness/<timestamp>/ (so the report cache never
hides a regression) and writes every report there as JSON. The exit code is 1 if any document
fails. Document text and prompts are never printed.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from docintel.api.deps import build_container
from docintel.core.config import REPO_ROOT, Settings
from docintel.core.errors import DocIntelError
from docintel.core.models import DocumentRecord, Requester

TASKS = ("summarize", "requirements", "risks", "ask")


@dataclass
class Outcome:
    label: str
    ok: bool
    seconds: float
    line: str
    detail: list[str]


def _catalog_references(samples_dir: Path) -> dict[str, str]:
    """Map sample file name -> mock Windchill reference."""
    catalog = samples_dir / "catalog.json"
    if not catalog.is_file():
        return {}
    data = json.loads(catalog.read_text(encoding="utf-8"))
    return {doc["file"]: doc["reference"] for doc in data.get("documents", [])}


def _load(
    container, path: Path, references: dict[str, str], requester: Requester
) -> DocumentRecord:
    reference = references.get(path.name)
    if reference and path.resolve().parent == container.settings.samples_dir.resolve():
        return container.document_service.import_from_windchill(reference, requester=requester)
    return container.document_service.ingest_upload(path.name, path.read_bytes())


def _run_task(container, record: DocumentRecord, task: str, question: str | None):
    extracted = container.documents.get_extracted(record.id)
    service = container.intelligence
    if task == "summarize":
        return service.summarize(record, extracted, refresh=True)
    if task == "requirements":
        return service.extract_requirements(record, extracted, refresh=True)
    if task == "risks":
        return service.identify_risks(record, extracted, refresh=True)
    return service.ask(record, extracted, question or "What is the purpose of this document?")


def _describe(result, task: str) -> tuple[str, list[str]]:
    v = result.verification
    p = result.provenance
    verified = v.verified + v.relocated
    counts = {
        "summarize": lambda r: (
            f"kp={len(r.summary.key_points)} req={len(r.requirements)} "
            f"spec={len(r.specifications)} risk={len(r.risks)} act={len(r.actions)}"
        ),
        "requirements": lambda r: f"req={len(r.requirements)}",
        "risks": lambda r: f"risk={len(r.risks)}",
        "ask": lambda r: f"answerable={r.answerable}",
    }[task](result)
    line = (
        f"{counts} | citations {verified}/{v.total_citations} verified "
        f"(relocated {v.relocated}, approx {v.approximate}, unverified {v.unverified}, "
        f"invalid {v.invalid_page}) | items w/o verified source {v.items_without_verified_source}/"
        f"{v.items_total} | tokens {p.usage.input_tokens}->{p.usage.output_tokens} "
        f"| attempts {p.attempts} | {p.model}"
    )
    detail = [f"warning: {w}" for w in result.warnings]
    detail += [f"limitation: {x}" for x in getattr(result, "limitations", [])]
    for c in result.citations:
        if c.status not in ("verified", "relocated"):
            detail.append(f"{c.status} {c.id} p.{c.page} score={c.match_score}")
    return line, detail


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("pdfs", nargs="*", type=Path, help="PDF files (default: catalog samples)")
    parser.add_argument(
        "--provider", choices=["anthropic", "ollama", "fake"], help="override AI_PROVIDER"
    )
    parser.add_argument("--model", help="override AI_MODEL")
    parser.add_argument("--task", choices=TASKS, default="summarize")
    parser.add_argument("--question", help="question for --task ask")
    parser.add_argument("--out", type=Path, help="output directory (default .data/harness/<ts>)")
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="print warnings and unverified citations"
    )
    args = parser.parse_args(argv)

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = args.out or REPO_ROOT / ".data" / "harness" / stamp
    overrides: dict[str, object] = {"data_dir": out_dir / "data", "serve_web_dist": None}
    if args.provider:
        overrides["ai_provider"] = args.provider
    if args.model:
        overrides["ai_model"] = args.model
    settings = Settings(**overrides)
    container = build_container(settings)
    requester = Requester(user_id=settings.dev_user_id, display_name="Harness")

    pdfs = args.pdfs or sorted(settings.samples_dir.glob("*.pdf"))
    if not pdfs:
        print("No PDFs found. Run scripts/generate_samples.py first.", file=sys.stderr)
        return 1
    references = _catalog_references(settings.samples_dir)

    print(
        f"Document Intelligence harness | provider={container.llm.name} "
        f"model={container.llm.model} | task={args.task} | output={out_dir}"
    )
    if getattr(container.llm, "development_only", False):
        print("NOTE: development-only provider — output is canned, not real AI analysis.")

    outcomes: list[Outcome] = []
    for path in pdfs:
        started = time.perf_counter()
        try:
            record = _load(container, path, references, requester)
            result = _run_task(container, record, args.task, args.question)
        except DocIntelError as exc:
            outcomes.append(
                Outcome(
                    path.name,
                    False,
                    time.perf_counter() - started,
                    f"ERROR {exc.code}: {exc.message}",
                    [],
                )
            )
        else:
            line, detail = _describe(result, args.task)
            target = out_dir / f"{path.stem}.{args.task}.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(result.model_dump_json(by_alias=True, indent=2), encoding="utf-8")
            outcomes.append(Outcome(path.name, True, time.perf_counter() - started, line, detail))
        o = outcomes[-1]
        print(f"{'OK ' if o.ok else 'FAIL'} {o.label} ({o.seconds:.1f}s): {o.line}")
        if args.verbose:
            for d in o.detail:
                print(f"      {d}")

    failed = sum(1 for o in outcomes if not o.ok)
    print(f"\n{len(outcomes) - failed}/{len(outcomes)} succeeded. Reports written to {out_dir}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
