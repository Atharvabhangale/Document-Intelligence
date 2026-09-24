# Windchill integration boundary

> **Status: not implemented.** V1 runs against `MockWindchillDocumentProvider`, which is
> **DEVELOPMENT ONLY** and is not connected to Windchill. `Windchill12DocumentProvider` is a
> stub that raises `windchill_not_implemented` (HTTP 501). No Windchill endpoints are assumed
> anywhere in the code.

## Confirmed context

These are the only Windchill facts the implementation relies on today:

- Windchill **12.0.2.19**.
- SOPs are **WTDocuments** stored in Windchill **Libraries** and folders within them.
- WTDocuments carry normal version/iteration information (e.g. `A.3`).
- **Released** is the business state for the approved, current SOP.
- Standard metadata is available: number, name, version, iteration, lifecycle state, modified date.
- **Windchill REST Services (WRS) is enabled.**
- An **integration/service account** can call the relevant Document Management REST APIs and
  download document content.

Everything else must be validated on the target system before implementation (see below).

## Target flow

```
Windchill WTDocument (info page / table row)
        │  user clicks "AI Summarize" (custom action — name must not collide with PTC's own
        │  "Summarize Document" action from the Windchill AI Assistant plugin)
        ▼
Windchill action opens the AI UI with the object reference only
        │  (never credentials or tokens in the URL)
        ▼
AI backend  ──►  WindchillDocumentProvider  ──►  Windchill (WRS)
        │         • resolve reference → WTDocument iteration + metadata
        │         • authorize the *requesting user* (Read + Download)
        │         • fetch primary content (PDF)
        ▼
Extraction → AI Gateway (LLM) → validation → citation verification → structured report
        ▼
AI Document Intelligence UI
```

In development the launch is simulated with `/?wtRef=<reference>&autorun=1`, which imports the
document through the configured provider and starts the analysis.

## Interface contract

`apps/api/src/docintel/providers/windchill/base.py`:

| Method | Purpose |
|---|---|
| `list_documents(*, requester, query, limit)` | Development browsing. A real provider may not need it (the flow starts from a Windchill action). |
| `get_document(reference, *, requester)` | Metadata: number, name, revision, iteration, state, location, type, modified date/by. |
| `get_primary_content(reference, *, requester)` | Primary content bytes + file name + media type. |

Every method receives the `Requester` (the end user). The backend never talks to Windchill outside
this interface, so the intelligence pipeline, API and UI do not change when the real provider is
implemented.

## Security requirement: the service-account gap

The confirmed deployment uses an **integration/service account** for WRS. A service account
usually sees more documents than any individual user. Windchill also distinguishes **Read**
(metadata) from **Download** (content) permissions (see `WINDCHILL_AI_RESEARCH.md` §8).
Therefore:

1. The real provider **must not** return content, or anything derived from it, unless the
   *requesting user* is authorized to download that document iteration in Windchill.
2. This applies to cached reports too. A cached summary may only be served after a fresh
   authorization check for the current user.
3. Where the user's identity comes from (the Windchill session, SSO, a signed launch token) and
   how per-user authorization is checked are **open design decisions**. They must be validated
   on 12.0.2.19. Candidate approaches are compared in `WINDCHILL_AI_RESEARCH.md` §8.5 and §9.3.

Until this is resolved, the backend's `get_requester()` returns a fixed development user.

## To validate on Windchill 12.0.2.19 before implementing

Record each answer, with evidence, in this document:

- [ ] Installed WRS version and available domains. On 12.0.x, WRS was a separately versioned
      module; the version-to-release mapping is in PTC KB CS318837.
- [ ] How to identify a WTDocument from the Windchill action: object reference format, and
      version vs. iteration references.
- [ ] How to read the metadata we need (number, name, revision, iteration, lifecycle state,
      folder/library location, modified date/by) from the Document Management domain's
      `$metadata` on the target server.
- [ ] How to resolve the latest iteration, and how to confirm a document is in the Released state.
- [ ] How to download primary content: the download URL flow, redirects, and which authentication
      applies.
- [ ] Behaviour for documents whose PDF is an attachment or a published representation rather
      than primary content.
- [ ] How per-user Read + Download authorization will be enforced for the requester, with
      negative tests: a user with Read but not Download, and a user with no access.
- [ ] CSRF nonce requirements for any non-GET calls. V1 needs only reads.
- [ ] Timeouts, paging and size limits for large PDFs.

## Metadata mapping (target)

| `DocumentMetadata` field | Meaning | Windchill source (to validate) |
|---|---|---|
| `number` | Document number | WTDocumentMaster number |
| `name` | Document name | WTDocumentMaster name |
| `revision` | Revision label (e.g. `A`) | version identifier |
| `iteration` | Iteration (e.g. `3`) | iteration identifier |
| `state` | Lifecycle state (e.g. `Released`) | lifecycle state (display value) |
| `location` | `Library / Folder / …` | container + folder path |
| `documentType` | e.g. `SOP` | soft type / subtype display name |
| `modifiedDate`, `modifiedBy` | Last modification | iteration modify timestamp / modifier |
| `sourceRef` | Opaque object reference | object/version reference |
