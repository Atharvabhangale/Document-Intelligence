# Security

This is an enterprise PLM capability that handles controlled engineering documents. V1 is a
**development build**. It runs on synthetic sample documents and a single development user. This
page lists the controls that exist today and the ones that are required before any real Windchill
data is processed.

## Data flow and residency (read first)

- With `AI_PROVIDER=anthropic` (the development default), **document text is sent to the
  Anthropic API** (`api.anthropic.com`). Use only synthetic or approved documents in this mode.
  The bundled samples are fictitious.
- The target production deployment uses a **locally hosted model** (`AI_PROVIDER=ollama`), so
  document content stays on the company network.
- `AI_PROVIDER=fake` makes no external calls. Its output is canned and clearly labeled in the UI.

## Controls in V1

**Secrets**
- The Anthropic key is read only from the environment: `ANTHROPIC_API_KEY`, falling back to
  `CAD_ANTHROPIC_API_KEY`. It is held as a `SecretStr` and passed straight to the SDK client.
- It is never logged, stored, returned by the API, or exposed to the browser.
- `.env` is git-ignored, and `.env.example` contains no secrets.

**AI isolation**
- The browser talks only to the backend (`/api`). There are no AI-service calls from the client
  and no CORS exposure of AI services.

**Upload and ingestion**
- Size limit, enforced while reading: `MAX_UPLOAD_MB`.
- PDF magic-byte check and page limit.
- Encrypted PDFs are rejected.
- File names are sanitized. Server-generated ids are the only path components; user input never
  becomes a path.
- The original bytes are stored as `content.bin`, never under the uploaded name.

**Content endpoint**
- `GET /api/documents/{id}/content` returns the PDF with `Content-Disposition: inline` and a safe
  RFC 5987 file name, `X-Content-Type-Options: nosniff`, `Cache-Control: private` and a
  `frame-ancestors 'self'` CSP. Stricter directives are omitted so browsers' built-in PDF viewers
  keep working.

**HTTP hardening**
- A CSP is sent on every response:
  `default-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'self'; …`.
- Also: `X-Content-Type-Options`, `Referrer-Policy: no-referrer`,
  `X-Frame-Options: SAMEORIGIN`, `Permissions-Policy`.
- CORS is limited to the configured development origins, with GET/POST only.
- Swagger UI is disabled because it would load a third-party CDN.

**Errors**
- There is one error envelope: `{"error": {"code", "message", "retryable"}}`.
- Messages are user-safe: no stack traces, library messages, document text or secrets.
- Validation errors report field locations only, not input values.

**Logging hygiene**
- Logs contain ids, counts, timings and error classes only, never prompts, document text or model
  output.
- The pdfminer/pdfplumber loggers are silenced because pdfminer can log content-stream operands,
  which may contain document text.

**Prompt-injection resistance**
- The document is framed as untrusted data, and the prompts instruct the model to ignore
  embedded instructions.
- Tag-like sequences that could break out of the page, document or question containers are
  neutralized.
- Output is schema-constrained and strictly validated.
- The model has no tools and cannot act.

**Output handling**
- Model output is rendered as text only (React text nodes). The UI never renders
  model-supplied HTML, links or images.

**Hallucination controls**
- Every item carries page citations, checked by deterministic code (`verified`, `relocated`,
  `approximate`, `unverified`).
- Unverified sources are visibly flagged, and inferred items are labeled as inferred.

**Honest labeling**
- Mock Windchill data and fake AI output are labeled **DEVELOPMENT ONLY** in API responses
  (`developmentOnly`) and in a persistent UI banner.

**Metadata integrity**
- Document number, revision, iteration and state come from the provider, never from the model.

## Required before production

1. **Authentication and identity.** Derive the requester from the authenticated Windchill
   session or corporate SSO. Never trust client-supplied identity.
2. **Per-user authorization.** The confirmed integration uses a WRS service account, which can
   see more than any single user. Every request must confirm that the requesting user has Read
   **and** Download permission on the exact document iteration before content, or anything
   derived from it, is returned. That includes cached reports. See
   `docs/windchill-integration.md` and `WINDCHILL_AI_RESEARCH.md` §8.
3. **Local inference.** Deploy Ollama bound to localhost or a private interface, behind an
   authenticating proxy that allowlists only the inference endpoints. Set `OLLAMA_NO_CLOUD=1`,
   pin a patched version, and never expose Ollama's model-management routes.
4. **TLS everywhere.** The PoC popup ran over plain HTTP ("Not secure"). Browser, backend,
   Windchill and model traffic must all use HTTPS.
5. **Rate limiting and quotas** per user, plus request timeouts, to prevent unbounded
   consumption.
6. **Audit trail** of analysis requests: user, document iteration, task, time, model, and
   authorization decision. Ids only, no content.
7. **Retention and deletion policy** for stored PDFs, extracted text and cached reports. Also
   purge them when a document is deleted or superseded.
8. **Data classification.** Decide whether documents with security labels or export control
   may be processed at all, and enforce that decision server-side.
9. **Dependency and vulnerability management** for Python and npm packages and for model
   artifacts.
