# Document Intelligence — web client

React 19 + TypeScript + Vite 8 + Tailwind CSS 4. It talks only to the backend's `/api`. The
browser never calls an AI service directly.

## Commands

```bash
npm install
npm run dev         # http://localhost:5173, proxies /api -> http://127.0.0.1:8000
npm test            # vitest (jsdom, mocked fetch)
npm run typecheck
npm run build       # -> dist/ (the backend can serve it, see SERVE_WEB_DIST)
npm run gen:types   # regenerate src/api/generated.ts from packages/schemas
```

Set `API_PROXY_TARGET=http://host:port` to point the dev and preview servers at another backend.

## Contract

`src/api/generated.ts` is generated from
`packages/schemas/document-intelligence.v1.schema.json`, which is exported from the backend's
Pydantic models. After the backend contract changes, run `npm run gen:types` and commit the
result. Import types from `src/api/types.ts` and use `src/api/client.ts` for requests.

## URLs

| URL | View |
|---|---|
| `/` | Home: choose a (mock) Windchill document or upload a PDF |
| `/?doc=<documentId>` | Document workspace |
| `/?wtRef=<reference>&autorun=1` | Simulated Windchill "AI Summarize" launch: imports the document, opens it and starts the analysis if no cached report exists |

Example: `/?wtRef=mock%3A%2F%2Fwtdocument%2FSOP-00123%2FA.3&autorun=1`

## Structure

```
src/api/            client.ts (typed fetch + ApiError), generated.ts, types.ts
src/components/     AppBar, DevelopmentBanner, ErrorState, ui/ (Button, Badge, Card, ...)
src/features/home/        document browser, upload, recent documents
src/features/document/    workspace, header, launch flow, lifecycle state badge
src/features/report/      report sections, citation chips, source viewer, analysis rail
src/features/ask/         "Ask this Document"
src/lib/            formatting, quote matching, URL routing, clipboard, error copy
src/test/           test setup and SOP-00123 fixtures
```

## Rules

- Render AI and document text as React text nodes only. Never use `dangerouslySetInnerHTML`.
- Build links only from our API (`contentUrl`). Never render links or images from model output.
- Always show the development banner when the data or the AI output is not real.
