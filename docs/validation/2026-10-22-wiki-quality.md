# Wiki quality verification — 22 October 2026

## Deployed snapshot

Both Wiki frontend and backend/worker images use code revision `534c76e7f6c5ba75a1e7c7b34fdf5fdfaf585eca` on `feature/optimize-261022`.

- Backend/API/workers: `cahy-wiki-backend:quality-261022-534c76e7`.
- Frontend: `cahy-wiki-frontend:quality-261022-534c76e7`.
- Chatbot guards: `cahy-chatbot:wiki-quality-261022-652f004`.
- Terminal: `cahy-open-terminal:quality-261022-v3`.

Backend images contain the complete reviewed feature source. Production has no app/alembic source bind mounts. The existing absolute temp_uploads location and durable volumes were retained. Development mounts require docker-compose.dev.yml. Main checkout's unfinished source edits were preserved; only its deployment image settings/source-mount configuration changed.

Dockerfile.runtime reuses verified dependency image `sha256:d489956adcf5b4993420db521ec541560cd696f1d2cce0d1d2614681e4774540`, replaces application/migration/skill sources, and smoke-imports the resulting application. requirements-runtime.lock records all 158 installed runtime dependency versions. The alternative full dependency rebuild with -FreshRuntime was not completed in this session because package downloads were slow; it was stopped before deployment. The verified dependency-base build and deployment succeeded.

Database was already at migration 053_document_manager. Parser configuration was normalized from legacy alias pymupdf4llm to pdfplumber without changing extraction implementation. Upload file limit remains 209715200 bytes.

## Checks

- Full Wiki pytest: **735 passed, 30 skipped**, 10 pre-existing warnings.
- Frontend tests: **10 passed**; focused ESLint, full TypeScript and production Docker/Next build passed.
- Chatbot evidence/export/graph/harness/knowledge/route suites: **242 passed**; one existing LangGraph deprecation warning.
- Independent code review reproduced and fixed empty/partial page batches, stale-version supersession, validity uncertainty false positives, quality JSON races, stale attempts, legal identifier normalization and OCR incompleteness.
- Actual exported DOCX/XLSX/PPTX/PDF opened and rendered via LibreOffice/PDFium, with original numeric values checked after conversion; CSV parsed. Repeated under UID 1000 with capabilities dropped and no-new-privileges. A renamed plain-text Office file is rejected. Export preview inspected in export-preview.png in the chatbot verification folder.
- Actual KnowledgeTable rendered with repository CSS at desktop and 390 px; screenshots inspected. Fixture mocked routing/translations, used static expansion handlers, and hid external-font icons. Temporary server/fixture removed.
- Post-deploy /health: database/Redis/MinIO healthy, exact build_revision verified.
- Post-deploy /api/health: API/database/worker healthy. Frontend /login and /api/health HTTP 200.
- Full 200 MiB multipart request through frontend reached authentication (401), proving transport without creating a synthetic production Source/job. Oversized complete request returned 413. Endpoint size-gate tests also covered exactly 200 MiB and +1 byte, plus declared/chunked request limits.
- In-memory runtime MCP discovery exposes 16 read tools with Wiki offset/max_chars and source-page offset/char_offset/max_chars/limit continuations. No production document data or LLM was queried by this discovery check.

## Practical limits

Legacy documents have unknown measured coverage until reprocessed. Concurrency regressions use mocked sessions; skipped infrastructure tests were not exercised. Publication/evidence gates catch concrete defects, not every incorrect semantic claim. Export QA is a render smoke check (up to 300 pages), not a universal guarantee against every layout problem. No synthetic document ingestion or live OCR/LLM acceptance batch was run against production. Changes remain on the feature branch; no new release merge was performed.
