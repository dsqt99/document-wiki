# Wiki quality and operational UI

User authorization: continue the previously presented supplementary-information redesign and P0–P2 improvements on feature/optimize-261022. Preserve the source checkout and existing 200 MiB upload change.

## Design

Use a single reviewable feature checkout containing the currently deployed backend changes and their matching frontend. Build both runtime images from this checkout; do not deploy frontend from release against an unrelated mounted backend. Preserve legal article extraction followed by generated Wiki compilation. Remove obsolete processing-mode choices from the upload UI.

Supplementary information expands into a full-width detail row below its document, preserving column alignment and existing actions. Show document metadata in a compact responsive definition list, then distinct extraction, raw-index and Wiki results with explicit unknown/partial states. Display actionable warnings without presenting unknown coverage as complete.

Public Source.processing_quality is a derived report with extraction {status,total_pages,text_pages,empty_pages,ocr_pages}, source_index {status,expected,indexed}, wiki {status,expected,published,failed}, and warnings [{code,message}]. Unknown counters are null. Persist measured observations under metadata.processing_quality without a database schema migration. Keep attempt-scoped observations from leaking across retries.

Portal and MCP share configured reranker selection, threshold and fallback semantics. MCP still searches original source chunks and exact legal units and applies authorization. Query-embedding failures automatically retain lexical retrieval. Expose fallback warnings and stable identifiers, bounded/paginated reads and explicit truncation indicators.

Stop publication for concrete broken evidence/empty extraction conditions, without treating maturity/style warnings as factual failures. Preserve review-expired originals and allow retry. Record actual skipped pages and indexing failures. Chat evidence checks must reject unsupported conclusions and incomplete source snapshots before export. Export validation should inspect renderability of Office/PDF content as available, and must not claim visual QA without rendering.

## Validation

Run focused regression tests for retrieval fallback/configuration/ACL, quality measurements/failed publication/TTL preservation, chat evidence/export validation, and source serialization. Run the complete Wiki suite, frontend lint/type/build and chatbot focused suite. Verify responsive supplementary details and legal/nonlegal upload behavior with browser fixtures. Build tagged backend/frontend images, deploy together from the feature checkout after checks, verify health/version and live 200 MiB transport. Never enqueue synthetic ingest jobs into production for tests.
