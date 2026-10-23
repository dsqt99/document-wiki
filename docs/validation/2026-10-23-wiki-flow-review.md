# Wiki flow review — 2026-10-23

Recorded at 2026-10-23 01:09 Asia/Bangkok (runtime PostgreSQL clock: 2026-10-22 18:09:19 UTC). Read-only review of code, runtime database and Redis; no ingestion, retry, deployment, live AI calls, or database changes were performed. This report is the only added artifact. Live Chat tests belong to the parent review and are not counted here.

## Conclusion

There is no evidence that all Wiki questions and cases pass. The tested contracts pass, but the current corpus has unfinished/partially failed Wiki compilation, historical coverage measurements are largely absent, and the legal-validity warning path cannot report the corpus's unresolved amendment/repeal/replacement relations. Database availability and unit-test success are distinct from correct end-to-end answers.

## Version and runtime

- Authoritative worktree: `C:/Users/DEV/.codex/worktrees/cahy-wiki-source-info-20261022`; branch `feature/optimize-261022`; HEAD `51fd35e`.
- API and both workers: `cahy-wiki-backend:quality-261022-1bb420a2`. API healthy at inspection. Frontend: `cahy-wiki-frontend:ui-261023-51fd35e0`.
- Code assertions below are against HEAD; corpus observations are against the running API's database. The differing backend/front-end source revisions must be retained when interpreting results.
- SHA-256 comparison confirmed byte-identical API/worktree copies of all nine directly reviewed files: `source_status.py`, `source_quality.py`, `retrieval_service.py`, `legal_service.py`, `legal_relation_extractor.py`, MCP `tools.py`, `knowledge_payloads.py`, `_wiki_search.py` and MRP `pipeline.py`. This resolves runtime/source drift for the cited backend paths, without asserting equivalence of every file in the image.

## Runtime evidence

| Observation | Result |
| --- | --- |
| Sources | 50; all 50 have nonempty extracted text and `chunk_status=ready` |
| Aggregate/Wiki status | 44 `ready/ready`; 2 `partial/error`; 2 `processing/queued`; 2 `processing/refining` |
| Extraction quality measurements | 0/50 recorded; public quality reports `unknown` |
| Raw source-index quality measurements | 0/50 recorded; public quality reports `unknown` |
| Wiki quality measurements | 6/50 recorded: 4 complete, 2 partial; remaining sources unknown or active |
| Raw PostgreSQL index | Dimension 1024: 2,556 chunks across all 50 sources; other dimensions empty |
| Wiki pages | 1,771 total: 1,638 mature, 99 evergreen, 21 developing, 13 seed |
| Wiki PostgreSQL chunk index | Dimension 1024: 5,291 chunks across 1,760 pages; all 11 excluded pages are reserved `_index`/`_log` pages, so this difference is not a demonstrated defect |
| Legal graph | 13,197 units; 558 relations; only 54 relations have linked target units, all `dan_chieu` |
| Redis queue | 37 jobs; all four processing sources are referenced by queued/running jobs |
| Historical dead letters | 110 pending records: TimeoutError 31; UpstreamUnavailable 32; CancelledError 23; APIConnectionError 5; ConnectionError 4; InternalServerError 6; ValueError 6; ChunkedEncodingError/IntegrityError/MissingGreenlet 1 each |

Redis membership establishes that the four sources are queued or running, not that they are hung. Their last source updates were approximately 37–79 minutes old at the earlier snapshot. Do not label these four as orphaned jobs without job heartbeat/progress evidence. Historical dead letters are not 110 currently broken sources; the table retains failures from earlier attempts.

The two partial sources are:

- `fd55525c-15a2-4f28-b789-8cd1857e985c` — Thông tư 79/2024/TT-BCA: 6/8 planned Wiki pages published, 2 failed (`chuong-ii-quy-dinh-ve-cac-loai-hinh`, `chuong-vi-quy-dinh-ve-ky-thuat`).
- `a99024d5-f30a-4ca9-85e5-e88aec26505b` — Nghị định 189/2025/NĐ-CP: 7/8 published, 1 failed (`phan-ii-quan-ly-chung`).

Both retain original text and raw chunks. Neither is in the PA08 source allow-list returned by `source_ids_for_departments` for department `956aab20-f853-4da4-966c-9302e98a56eb`; a PA08 positive test must not assume those sources are accessible.

## Findings and priorities

### P1 — Legal-validity warnings have no linked modifying relations in this corpus

All 281 modifying relations have `target_unit_id=NULL`: 97 `bai_bo`, 9 `bo_sung`, 65 `sua_doi`, 110 `thay_the`. The warning query requires equality on `target_unit_id` in `app/services/legal_service.py:1206`, so none can produce a unit-level validity warning. Whole-document changes have no target article by design; `relink_legal_relations` excludes them at `app/services/legal_relation_extractor.py:285`. There are 189 whole-document changes (79 repeals and 110 replacements). For 121 of those, the named target document already exists in `legal_units` (38 repeal, 83 replacement); this is not explained solely by missing documents. Two article-level amendments also have an exact matching document/article present but remain unlinked.

Proposed work: model document-level lifecycle separately from article targets, normalize document identifiers, repair links with ambiguity reporting, relink incoming as well as newly ingested outgoing relations, and propagate document-level warnings to article reads. Ingestion currently relinks only outgoing relations from the current source (`app/services/legal_service.py:971`), which is sensitive to ingest order. Add tests where the modifying document arrives before its target and tests for whole-document replacement/repeal.

This is a database/code finding, not a legal opinion about which law is currently effective. `is_effective=True` is assigned at extraction (`app/services/legal_service.py:1130`, `:1145`); external authority, effective dates, expiry and conflicts were not verified here. A response must not infer “still valid” merely from missing warnings.

### P1 — Finish/recover the two partial and four processing sources before corpus acceptance

The two partial jobs have three explicitly missing planned Wiki pages. Existing safeguards correctly expose partial failure rather than silently claiming full success: aggregation uses `partial` for raw-ready/Wiki-error (`app/services/source_status.py:74`), and the commit phase records skipped-page quality (`app/ai/mrp/pipeline.py:187`, `:192`). Proposed work: inspect persisted failed drafts and safe reason codes, repair the provider/content issue, retry the failed Wiki branch, and verify publication and searchability of each planned page. This review did not retry anything. Four still-pending sources need completion/monitoring, with Redis state considered before intervention.

### P1 — Establish measurable coverage for historical sources

Ready flags alone are not proof of complete extraction or indexing. `public_source_quality` intentionally reports unknown when evidence is missing (`app/services/source_quality.py:84`), while aggregate readiness is based on branch state (`app/services/source_status.py:54`). All 50 sources lack measured extraction/raw-index quality; only 6 have measured Wiki quality. The PostgreSQL chunk counts above show rows exist, but do not prove original page coverage, correct OCR, expected chunk count, Milvus parity or retrieved answer completeness.

Proposed work: audit/backfill factual counters from preserved files/pages/plans and actual PostgreSQL/Milvus rows without inventing measurements; expose unknown/partial warnings to reviewers; set explicit acceptance thresholds. Review scanned/mixed PDF, long tables, DOC/DOCX, XLS/XLSX, PPT/PPTX, empty pages and truncation cases with original-file comparisons.

### P2 — Add live answer and failure-mode acceptance cases

The 481 passing tests below cover important contracts but largely mock providers/search/database responses. Build a repeatable golden-question matrix with expected source/page/article IDs and facts, using authorized users for global, department, personal and higher-clearance cases. Include raw fallback while Wiki fails, lexical fallback while embeddings fail, independent-arm failures, both-arm failure, reranker outage, exact article/clause reads, continuation beyond the first window, source replacement and citation checks. Require task completion and coverage separately from answer quality.

### P2 — Keep ACL filtering on legal warnings when links are repaired

Search arms and source/page reads carry allowed-source and clearance filters; unit tests cover these flows. However, `get_legal_unit_validity_warnings` has no identity/allow-list parameter (`app/services/legal_service.py:1190`), and MCP `_validity_callout` invokes it directly (`app/mcp/tools.py:557`). A linked modifier outside the reader's scope could contribute its document number/quote to an otherwise accessible read. There are currently zero resolved cross-scope relations, so this is an unexercised risk, not a demonstrated runtime leak. Make warning provenance scope-aware and add a cross-scope modifying-document test as part of repairing legal links.

## Verified code contracts

- Unified search isolates exact/Wiki/raw arms using sequential savepoints (`app/services/retrieval_service.py:281`) and returns failed-arm metadata. Partial failures preserve surviving results.
- MCP embedding failures fall back to lexical search and propagate clearance, page filter and allowed source IDs (`app/mcp/tools.py:793`, `:801`). Both Wiki/raw arms failing yields structured error (`:833`).
- Extracted original text remains eligible independently of downstream status (`app/services/_wiki_search.py:226`); explicit original-text keyword search has the same intent (`app/mcp/tools.py:1301`).
- Bounded reads default to 20,000 characters, cap at 50,000 and 20 pages, expose continuation offsets and content hashes (`app/mcp/knowledge_payloads.py:23`, `:35`, `:49`). Huge page ranges are intersected with actual pages before expansion. These are unit/contract checks, not a live Chat proof that an agent follows every cursor.
- Read-by-ID rechecks scoped page/source access (`app/mcp/knowledge_payloads.py:210`, `:229`; `app/mcp/tools.py:573`).
- Retry selects a failed branch while preserving the surviving branch; branch attempts reject stale work. Real PostgreSQL concurrent-lock tests were skipped, so race safety is not established by this run.

## Test runs

Python executable: `D:/code/dsqt/conganhungyen/chatbot_cahy/final_ban_giao/cahy_wiki/.venv/Scripts/python.exe`. CWD is the authoritative worktree above. Both commands exited 0.

```powershell
& $python -m pytest -q tests/test_source_status.py tests/test_source_status_pg.py tests/test_source_quality.py tests/test_source_quality_response.py tests/test_source_retry.py tests/test_stuck_sweep.py tests/test_worker_idempotency.py tests/test_mrp_retry_checkpoint.py tests/test_mrp_evidence_repair.py tests/test_dual_pipeline_retrieval.py tests/test_retrieval_runtime_contract.py tests/test_legal_hierarchy_retrieval_and_validity.py tests/test_exact_legal_route.py tests/test_mcp_scope.py tests/test_mcp_read_windows.py tests/test_mcp_forwarded_identity.py tests/test_legal_scope_enforcement.py tests/test_ingest_formats.py tests/test_legal_graph_ingest.py tests/test_wiki_draft_publish.py tests/test_wiki_write_guard.py
# 154 passed, 4 skipped, 1 warning in 31.01s

& $python -m pytest -q -rs tests/test_legal_relation_extractor.py tests/test_legal_hierarchy_parser.py tests/test_legal_graph_models.py tests/test_search_accuracy.py tests/test_graph_expanded_search.py tests/test_chunk_budget.py tests/test_citation_verifier.py tests/test_upload_guard.py tests/test_upload_dedup.py tests/test_pdf_parser.py tests/test_pdf_parser_options.py tests/test_docx_parser.py tests/test_excel_parser.py tests/test_pptx_parser.py tests/test_processing_mode.py tests/test_processing_ops.py tests/test_dead_letter_and_timings.py tests/test_ocr_validate.py tests/test_ocr_refine.py tests/test_text_clipping.py
# 327 passed, 2 warnings in 11.45s
```

Combined: **481 passed, 4 skipped, 3 warnings**, across 41 explicitly selected test modules. This was not the entire repository test suite. Three skips are `test_source_status_pg.py` requiring an absent throwaway `ARKON_IT_DATABASE_URL`; the fourth is XLS generation coverage skipped because `xlwt` is absent (`tests/test_ingest_formats.py:12`). Warnings are unawaited `AsyncMock` substitutes for SQLAlchemy `session.add` in one legal-scope test and two failure/timing tests. No test failure occurred, but these warnings reduce confidence in those mocks.

## Reproducing read-only observations

Commands used `docker ps --format '{{.Names}} {{.Image}} {{.Status}}'`, then PowerShell here-string Python scripts piped to `docker exec -i cahy_wiki_api python -`. Scripts imported `async_session_factory`, executed only SELECTs, printed whitelisted counts/statuses, and called the read-only `public_source_quality` helper. Representative SQL:

```sql
SELECT status, chunk_status, wiki_status, count(*) FROM sources GROUP BY 1,2,3;
SELECT count(*) FILTER (WHERE metadata->'processing_quality'->'extraction' IS NOT NULL) extraction_measured,
       count(*) FILTER (WHERE metadata->'processing_quality'->'source_index' IS NOT NULL) raw_measured,
       count(*) FILTER (WHERE metadata->'processing_quality'->'wiki' IS NOT NULL) wiki_measured FROM sources;
SELECT relation_type, is_effective, count(*),
       count(*) FILTER (WHERE target_unit_id IS NULL) unresolved
FROM legal_relations GROUP BY 1,2;
SELECT count(*), count(DISTINCT source_id) FROM source_chunk_embeddings_1024;
SELECT count(*), count(DISTINCT page_id) FROM wiki_page_chunk_embeddings_1024;
SELECT status, error_type, count(*) FROM task_failures GROUP BY 1,2;
```

Redis inspection called `get_arq_pool()`, `redis.queued_jobs()` and `_source_ids_with_pending_jobs(redis)` (`app/worker.py:970`), intersected the returned source UUIDs with the four processing rows, then closed the client. No job was enqueued, retried or removed.

Not established: original-file extraction fidelity, current external legal validity, Milvus/PostgreSQL parity, every user/clearance combination, live provider outage recovery, and production concurrent-write behavior. These require separate controlled acceptance evidence.
