# Development guide

## Prerequisites

- Python 3.11+ and [uv](https://docs.astral.sh/uv/)
- Node.js 22.12+ and npm
- For live AI calls: an Anthropic credential in the environment, as `ANTHROPIC_API_KEY` or
  `CAD_ANTHROPIC_API_KEY`. Never put it in a file that is committed.

## Setup

```bash
uv sync --project apps/api          # backend virtualenv (apps/api/.venv)
npm --prefix apps/web install       # web dependencies
cp .env.example .env                # optional local overrides (git-ignored)
```

## Run

**Two processes (hot reload):**

```bash
uv run --project apps/api uvicorn docintel.api.app:app --reload --port 8000
npm --prefix apps/web run dev       # http://localhost:5173 (proxies /api to :8000)
```

**Single process (built UI served by FastAPI):**

```bash
npm --prefix apps/web run build
uv run --project apps/api uvicorn docintel.api.app:app --port 8000   # http://localhost:8000
```

**Offline, no API calls:** prefix the backend command with `AI_PROVIDER=fake`. The UI shows that
the AI output is simulated.

**Simulated Windchill launch:** open
`http://localhost:5173/?wtRef=mock://wtdocument/SOP-00123/A.3&autorun=1`. This is what a
Windchill "AI Summarize" action will do: open the UI with the object reference. The document is
then imported through the configured provider and analyzed.

## Tests

```bash
uv run --project apps/api pytest apps/api/tests            # backend (no network)
DOCINTEL_LIVE_TESTS=1 uv run --project apps/api pytest apps/api/tests/live   # one real API call
npm --prefix apps/web test                                  # web unit/component tests
npm --prefix apps/web run typecheck
uv run --project apps/api ruff check apps/api scripts
uv run --project apps/api ruff format --check apps/api scripts
uv run --project apps/api python scripts/export_schemas.py --check          # schema drift
```

Automated tests never call a real LLM. They use `ScriptedLLMProvider` for exact responses,
including malformed, truncated and refused output, and `DevFakeLLMProvider` for end-to-end flows.

## Pipeline harness

Runs PDFs through the real pipeline (extractor, provider, validation, citation verification) and
prints a quality line per document. It never prints document text.

```bash
uv run --project apps/api python scripts/harness.py                  # all samples, configured provider
uv run --project apps/api python scripts/harness.py --provider fake  # offline
uv run --project apps/api python scripts/harness.py -v path/to/file.pdf
uv run --project apps/api python scripts/harness.py --task ask --question "What PPE is required?"
```

Reports are written to `.data/harness/<timestamp>/`.

## Regenerating artifacts

| Artifact | Command |
|---|---|
| Sample SOP PDFs (`samples/*.pdf`) | `uv run --project apps/api python scripts/generate_samples.py` |
| JSON Schema bundle (`packages/schemas/`) | `uv run --project apps/api python scripts/export_schemas.py` |
| Web client types (`apps/web/src/api/generated.ts`) | `npm --prefix apps/web run gen:types` |

After changing any Pydantic model in `schemas/`, regenerate both the schema bundle and the web
types.

## Changing a prompt

1. Copy `prompts/<task>.v<N>.md` to `prompts/<task>.v<N+1>.md` and edit it. Keep the front matter
   `id` equal to the file's task name.
2. Restart the backend. The highest version becomes active, and cached reports from the old
   version are no longer used, because the prompt version is part of the cache key.
3. Run the harness on the samples, then on representative real documents, and compare
   verification rates and item counts with the previous version.

## Switching models

- **Another Claude model:** set `AI_MODEL`. Newer models (Opus 4.7+) reject sampling parameters,
  so also set `AI_TEMPERATURE=none`.
- **Ollama:** set `AI_PROVIDER=ollama`, `AI_MODEL=<local model>` and
  `OLLAMA_BASE_URL`/`OLLAMA_NUM_CTX`. `OllamaProvider` has not yet been validated against a live
  Ollama server. Run the harness and the live checks before relying on it.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `ai_not_configured` | No Anthropic credential in the environment (`ANTHROPIC_API_KEY` / `CAD_ANTHROPIC_API_KEY`). |
| `content_not_available` for a mock document | Sample PDFs are missing. Run `scripts/generate_samples.py`. |
| `no_extractable_text` | Scanned PDF. OCR is not available in this version. |
| `document_too_large` | The estimated tokens exceed `MAX_DOCUMENT_TOKENS`, or pages exceed `MAX_PAGES`. |
| Old results after a prompt change | Restart the backend; prompts are loaded once per process. |
