# Architecture

AI Document Intelligence for Windchill is one Python backend (FastAPI) plus one web client
(React). It is deliberately not a set of microservices. Every external dependency sits behind an
interface, so the two parts that will change can be swapped without touching the pipeline or the
UI:

- the document source: mock provider today, Windchill REST Services later;
- the model runtime: Anthropic today, local Ollama later.

```
 Browser (React + TypeScript)                       ── apps/web
   │  JSON over /api only (never calls an AI service directly)
   ▼
 FastAPI app (routes, errors, security headers)     ── apps/api/src/docintel/api
   │
   ├─ DocumentService (ingestion)                    ── docintel/documents.py
   │     ├─ WindchillDocumentProvider ──┬─ MockWindchillDocumentProvider   (DEVELOPMENT ONLY)
   │     │                               └─ Windchill12DocumentProvider     (stub, not implemented)
   │     ├─ TextExtractor ── PdfPlumberExtractor (page-aware; OCR hook for later)
   │     └─ DocumentRepository (file-based)
   │
   └─ DocumentIntelligenceService (pipeline)         ── docintel/intelligence
         ├─ PromptLibrary      versioned prompt files in /prompts
         ├─ context builder    page-tagged document text, size guard
         ├─ LLMProvider ──┬─ AnthropicProvider (Claude Haiku 4.5 in development)
         │                ├─ OllamaProvider    (local runtime; not yet validated live)
         │                └─ DevFakeLLMProvider (DEVELOPMENT ONLY canned output)
         ├─ parsing            strict Pydantic validation + bounded repair
         ├─ citations          quote verification against extracted page text
         ├─ assemble           ids, verification summary, warnings, provenance
         └─ ReportRepository   content-addressed report cache
```

## Request flow: "Analyze document"

1. **Ingest.** The document enters through `POST /api/documents/from-windchill` (the provider
   reference) or `POST /api/documents` (upload, a development path).
   - The PDF is validated: magic bytes, size, encryption, page limit.
   - Text is extracted **page by page**: page N of the result is physical page N.
   - The record, original bytes and page texts are stored under `DATA_DIR/documents/<id>/`.
   - Windchill imports get a deterministic id derived from provider + reference + content hash.
     Re-opening the same iteration therefore reuses the stored extraction.
2. **Guard.** No extractable text raises `no_extractable_text`. A document above
   `MAX_DOCUMENT_TOKENS` (estimated) raises `document_too_large`. Nothing is truncated silently.
3. **Cache.** The report cache key is
   `sha256(content hash | task | prompt id@version | provider | model | pipeline version |
   schema version | extractor)`. Changing any of these produces a new analysis. Old results are
   never reused under a new configuration.
4. **Prompt.** The request is built from four parts:
   - the system prompt from `prompts/<task>.v<N>.md`;
   - the page-tagged document context, byte-stable so Anthropic can prompt-cache it across tasks;
   - the task instruction;
   - a JSON Schema generated from the strict Pydantic output model.
5. **Generate.** Output is schema-constrained where the backend supports it: `output_config`
   JSON schema on Anthropic, `format` on Ollama.
   - `max_tokens` → `ai_output_truncated`; `refusal` → `ai_refused`.
6. **Validate.** The text is parsed and validated against the strict model (no extra fields,
   all fields required, enums). If validation fails, the model is asked to repair its output up
   to `AI_MAX_REPAIR_ATTEMPTS` times, with a compact list of problems. After that the request
   fails with `ai_output_invalid`, and **no partial result is shown**.
7. **Verify citations.** Every source quote is checked against the extracted page text
   (details below).
8. **Assemble.**
   - Stable ids are assigned (`REQ-001`, `C1`, …).
   - Document metadata comes from the provider record, **never from the model**.
   - Warnings are added: non-Released state, OCR-needed pages, unverified citations, truncated
     lists.
   - Provenance is recorded: prompt, model, pipeline, schema, extractor, timing, tokens.
9. **Store and return.** The report is stored under its cache key and returned to the UI.

`POST /api/documents/{id}/ask` uses the same flow, without caching.

## Contracts and versioning

| Contract | Where | Version marker |
|---|---|---|
| LLM output models (what the model must return) | `schemas/report.py` (`LLM*`) | part of `schemaVersion` |
| API report models | `schemas/report.py`, exported to `packages/schemas/document-intelligence.v1.schema.json` | `schemaVersion: "1.0"` |
| Web client types | `apps/web/src/api/generated.ts`, generated from the JSON Schema | regenerate with `npm run gen:types` |
| Prompts | `prompts/<task>.v<N>.md` (YAML front matter + system prompt) | `provenance.promptVersion` |
| Pipeline logic | `intelligence/service.py` `PIPELINE_VERSION` | `provenance.pipelineVersion` |

A test (`scripts/export_schemas.py --check`) fails when the exported schema drifts from the
Pydantic models.

## Citation verification

The model cites `{page, quote}` pairs. Quotes are meant to be verbatim excerpts of 5–25 words.
The verifier normalizes the quote and the page text in the same way:

- Unicode NFKC;
- quote and dash variants unified;
- soft hyphens and zero-width characters removed;
- line-break hyphenation joined;
- whitespace collapsed;
- case-folded.

It then classifies each citation:

| Status | Meaning |
|---|---|
| `verified` | The quote occurs on the cited page. |
| `relocated` | The quote occurs, but on a different page (`matchedPage`). |
| `approximate` | Fuzzy match (≥ 0.88 similarity over word windows). |
| `unverified` | The quote was not found in the document. |
| `invalid_page` | The cited page does not exist and the quote was not found elsewhere. |

The UI shows the status on every source chip. The analysis panel reports how many sources were
verified. Items without a verified or relocated source are counted in
`verification.itemsWithoutVerifiedSource`.

## Extension points

| To add… | Change |
|---|---|
| A new analysis task (e.g. revision comparison) | A prompt file, an `LLM*Output` model, an API report model, an assembler, and a `TaskSpec` in `intelligence/tasks.py`. Then a route. |
| A new prompt version | Add `prompts/<task>.v<N+1>.md`. It becomes active on restart, and the cache key changes automatically. |
| A local model | `AI_PROVIDER=ollama AI_MODEL=<model>`. `OllamaProvider` implements the same interface. It needs validation against a live Ollama server. |
| Windchill | Implement `Windchill12DocumentProvider` against validated WRS endpoints, including per-user authorization (see `docs/windchill-integration.md`). |
| OCR | Implement `extraction.base.OcrEngine` and pass it to `PdfPlumberExtractor(ocr=...)`. |
| Other Windchill object types | New provider methods for that object type's content. The pipeline works on `ExtractedDocument` and is object-type agnostic. |
| Database storage | Implement `DocumentRepository` / `ReportRepository`. |

## Known V1 limitations

- **Single-pass analysis.** Documents larger than `MAX_DOCUMENT_TOKENS` are rejected rather than
  chunked; map-reduce is a later step.
- **PDF only.** Scanned pages are detected and reported but not OCR'd.
- **No authentication or per-user authorization.** There is one development user. This is
  required before any real Windchill data is used.
- **File-based storage** with no retention policy.
- **No single-flight protection:** concurrent identical first-time analyses may both call the
  model.
