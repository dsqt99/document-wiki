# Wiki Library and Summary Maintenance Implementation Plan

> **For agentic workers:** Use subagent-driven-development for independent frontend tasks and review. User approved implementation; do not ask again for execution mode.

**Goal:** Make wiki browsing and editing spacious and allow operators to rebuild summaries from current content.

**Architecture:** Reuse the existing permission-filtered wiki listing, cache, UI controls and ARQ worker. Keep the library, reading catalogue and background summary service in separate modules, integrated by the knowledge page and existing worker wrappers.

**Tech Stack:** Next.js/React/TypeScript, existing Tailwind/Base UI components, FastAPI/SQLAlchemy, Redis/ARQ, pytest.

## Task 1: Wiki library

Files: create frontend/src/components/knowledge/wiki-library.tsx; modify frontend/src/app/(portal)/knowledge/page.tsx and app/routers/wiki.py. Controller owns backend; frontend worker owns the component and knowledge tabs.

- [x] Add GET /api/wiki/library with q, source_id, page_type, status, limit=30, offset=0; apply existing wiki read filter to both count and rows. Return {items, total, limit, offset}. Frontend uses this API for horizontal search/source/type/status filters, updated sorting, page count and pagination. Reuse current scope link encoding and cached source labels; handle loading, error, empty and zero matches.
- [x] Add a Wiki tab between Documents and Knowledge types, persist tab in ?tab=wiki, support refresh and count updates, and preserve unrelated URL parameters. Leave processing menu integration to controller.
- [x] Check touched files with ESLint and TypeScript; report any pre-existing diagnostics separately.

## Task 2: Reading catalogue

Files: frontend/src/components/wiki/wiki-page-tree.tsx, frontend/src/app/(portal)/wiki/[...slug]/wiki-page-view.tsx, frontend/src/lib/wiki-store.ts if required.

- [x] Replace permanently reserved tree column with labelled Danh mục trigger and existing accessible Sheet overlay.
- [x] Scope initial catalogue to active page source; preserve deliberate user changes. Show current context and controls in a compact header without duplicate sidebar strips. Close overlay on page selection, allow all documents, retain creation/search/delete and scope routing.
- [x] Verify small/large viewport, keyboard and reader-mode interactions; run targeted lint/types.

## Task 3: Summary service and jobs

Files: create app/services/wiki_summary_service.py; modify app/routers/wiki.py, app/tasks/wiki_tasks.py, app/worker.py; add tests to tracked tests/test_processing_ops.py (tests/ is ignored for new files).

- [x] Write failing tests for complete legal/generic summary extraction and missing/clipped-only candidate selection from current wiki content; test scope filters and reserved/empty exclusion.
- [x] Define missing/clipped as empty summary, ellipsis-ending summary, or legacy-length summary (180/280/300/400) that is a strict prefix of the computed current paragraph. Preserve other nonempty custom summaries in missing/clipped mode; all mode explicitly replaces them.
- [x] Implement deterministic summary extraction reusing refresh_article_summary on a copy for legal pages; no LLM or source re-ingestion is required.
- [x] Implement permission-filtered POST /wiki/summaries/rebuild and GET /wiki/summaries/jobs/{id}, Redis status with finite TTL, active-job dedupe and clear queue errors.
- [x] Register rebuild_wiki_summaries_task and implement per-page transactions/current-row locking, progress and error counts, best-effort existing vector indexing. Process explicit candidate IDs scoped at submission.
- [x] Run focused tests for service, API, worker and earlier legal fixes.

## Task 4: Integration and review

Files: frontend/src/app/(portal)/knowledge/page.tsx and a focused processing status component/type if needed.

- [x] Add both summary actions, count candidate pages, disable duplicate start, poll active job and show accessible progress, completed counts and errors. Refresh wiki cache on completion.
- [x] Review spec compliance and code correctness with a fresh agent; fix actionable findings.
- [x] Run backend targeted suites, frontend lint/types/build where available, git diff --check, and browser QA with fixture APIs when live services are unavailable. Report actual validation and any runtime limitations.

Do not modify the pre-existing app/config.py edits, commit or push unrelated changes, deploy, or require an additional approval of this already-approved plan.

## Verification results

103 focused backend tests passed. Full frontend TypeScript, targeted ESLint and the navigation regression harness passed. Browser QA covered real 1,711-page data, source/search filters, scoped reader overlay, preserved return filters and 1366px/390px layouts. A real Redis/ARQ job completed against a nonexistent test page ID, modifying zero database pages. At the user request, the frontend now runs with `npm run dev -- --port 3219 --hostname 127.0.0.1` against the real API on 5155; API and the idle worker were restarted to load the new routes/task. No frontend production build was requested for this debug session.
