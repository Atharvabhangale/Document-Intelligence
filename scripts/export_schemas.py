"""Export the API JSON Schema bundle to packages/schemas.

Usage (from the repository root):

    uv run --project apps/api python scripts/export_schemas.py          # write
    uv run --project apps/api python scripts/export_schemas.py --check  # fail if out of date

The web client generates its TypeScript types from this file (``npm run gen:types``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from docintel.schemas.report import api_json_schema

REPO_ROOT = Path(__file__).resolve().parents[1]
TARGET = REPO_ROOT / "packages" / "schemas" / "document-intelligence.v1.schema.json"


def render() -> str:
    return json.dumps(api_json_schema(), indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit 1 if the file is stale")
    args = parser.parse_args()
    content = render()
    if args.check:
        current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        if current != content:
            print(
                f"{TARGET} is out of date. Run scripts/export_schemas.py.",
                file=sys.stderr,
            )
            return 1
        print("schemas up to date")
        return 0
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(content, encoding="utf-8")
    print(f"wrote {TARGET.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
