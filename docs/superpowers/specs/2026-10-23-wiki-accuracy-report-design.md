# Wiki accuracy report CLI

## Intent and scope

The user requested repeatable accuracy reports for extraction, OCR, embedding/search and reranking using current Wiki settings. They selected CLI + HTML/JSON/CSV instead of an admin UI. Build one local Python toolkit in this repository, without a new service, UI, ingestion job or changes to operating settings.

Alternative: an admin dashboard would add authentication, persistence and job orchestration before the measurements themselves are useful. A pytest-only solution would check contracts but not supply provider/corpus accuracy reports. The selected CLI provides reusable measurements and readable artifacts first.

## Execution model

Commands:

- `python -m app.evaluation init --directory <path>` creates deterministic synthetic fixtures, independent reference files and a manifest. Refuse to overwrite existing files. All generated documents identify themselves as QA data.
- `python -m app.evaluation run --manifest <file> --output <directory> [--stages extraction,ocr,embedding,rerank,search]` runs the requested stages with current DB/environment configuration. Unknown stages, invalid manifests and missing requested tests are errors rather than an empty green report.
- `python -m app.evaluation compare --baseline <report.json> --current <report.json> --output <directory>` reports per-case/stage deltas and incompatible configuration/dataset warnings. Reports are data, never executable instructions.
- `python -m app.evaluation validate --manifest <file>` validates inputs without loading credentials or calling providers.

Defaults: serial requests; one attempt per benchmark case at the runner level; stage timeout and whole-run deadline; configurable small limits for cases/corpus/pages/bytes. The default stages are extraction, OCR, embedding and rerank; live search is opt-in and requires real-ID judgments. Provider-internal retries remain observable configuration, not redefined as independent samples. Execute model/parser stage work in a child process with a hard parent deadline, because OCR uses a blocking SDK in a thread. On timeout/interrupt terminate that child, retain completed results and start no further calls. Communicate only sanitized structured results; never retain raw child stderr. Write a partial report atomically after each case so interruption preserves evidence. Ctrl-C produces an interrupted run; no automatic background monitor.

Four report outputs: `report.json` (versioned complete structured evidence), `cases.csv` (one stage/case row), `report.html` (offline Vietnamese report with inline styles and no remote assets/scripts), and `run.json` (source revision, times and sanitized configuration). Comparison creates the corresponding comparison JSON/CSV/HTML.

Each run records UTC timestamps and Asia/Bangkok display times, run ID, source Git revision, manifest and input SHA256s, fixture provenance, stage statuses, actual model/engine/dimension, latency, counts and safe error codes. Configuration snapshots use an allowlist and never contain API keys, passwords, tokens, authorization headers, credential-bearing URLs or exception bodies. CLI diagnostics must sanitize upstream failures too. Actual source/output text is omitted by default; an explicit local `--include-text` option may include excerpts in the report. Treat all labels/text/filenames as untrusted when rendering HTML or CSV (escape HTML; prevent spreadsheet formulas).

## Ground truth and manifest

JSON manifest schema version 1; stable unique case/document IDs. References must be independently authored/reviewed or generated from an explicit synthetic blueprint, never produced by the same parser/OCR/model being evaluated. Reference file checksums and provenance labels distinguish synthetic examples from manually reviewed real documents. Missing reference data means `unscored`, not zero error or passed. Invalid/missing files, duplicate IDs, non-finite grades, unknown relevant IDs, malformed vectors and empty expected text are validated explicitly.

Relative fixture/reference paths resolve under the manifest directory; reject escaping paths. Default corpus/case limits keep accidental huge runs bounded; explicit overrides are recorded. A scored extraction/OCR case has a reference text per logical page, optional expected ordered headings, exact critical values and table rows/cells. A valid blank-page reference declares `expect_blank: true`; blank is never inferred from a missing reference.

Retrieval cases have a query and graded relevance judgments over stable document IDs (0–3). Include Vietnamese accents, accentless queries, paraphrases, exact document/article identifiers, numeric/table queries, irrelevant distractors and answer-absent queries. Live search cases add expected source/page IDs, an optional exact-match target, forbidden IDs and an explicitly supplied identity token via environment variable. Fixtures never contain real secrets.

Starter fixtures cover TXT/Markdown, DOCX, XLSX, PPTX, digital PDF, image/scanned PDF, a mixed PDF and blank scan, plus a small independently authored retrieval corpus and graded queries. Generation may use already available Office/Pillow libraries; PDF generation/font requirements are reported clearly. No skip silently counts as completed coverage. Synthetic scans are labeled synthetic and do not certify real degraded scans. The manifest supports adding reviewed real files without modifying Python code.

## Metrics and statuses

Statuses: `passed`, `failed`, `error`, `blocked`, `disabled`, `unscored`, `skipped`. A run is complete only when every requested eligible case has a terminal result and every requested stage has cases. Report total/requested/executed/scored denominators separately. Do not collapse all stages into a fabricated single accuracy percentage.

- **Extraction/OCR:** character error rate (CER) and word error rate (WER) via edit distance against the reference; NFC Vietnamese normalization and whitespace normalization are explicit policies. Preserve accents, punctuation and numbers in the strict comparison. Error rates may exceed 1 when insertions dominate; never clamp them into a misleading percentage. Blank references use hallucinated character/token counts rather than division by zero. Score logical-page coverage and critical-value exact matches separately from text similarity. Optional table-cell/heading measurements are reported only where annotated. Formats without physical pages use logical parser units (sheet/slide/section), not invented page fidelity.
- **Embedding calibration:** use the active `ProviderRegistry` document and `search_query` embedders on the fixed reference corpus, with identical passage content across runs. Validate dimensions, finite values and nonzero vectors. In-memory cosine ordering is an isolated provider test, explicitly not a production index measurement. Deduplicate stable document IDs before scoring.
- **Retrieval:** Recall@k, Precision@k, reciprocal rank, nDCG@k and expected-target hit rate; grades and k are recorded. Precision@k uses k as denominator, including short results. No-relevant-result cases measure false positives separately, not a fabricated Recall/nDCG. Report query macro means alongside case counts; failed/blocked queries remain in reliability denominators and are never silently dropped to improve apparent accuracy.
- **Rerank:** score the exact same fixed candidate pool before and after `configured_rank_candidates`, using the actual configured scorer and threshold. Record nDCG/MRR delta, removed relevant items and latency. A disabled reranker is `disabled`; hybrid fallback is `blocked` for reranker accuracy and remains a separately visible baseline. Never relabel lexical/RRF scores as model scores.
- **Live search:** authenticated Wiki search API with current index and ACL; report actual retrieval/fallback modes, matching IDs, latency and any forbidden-ID violations. The portal endpoint currently returns a page-summary list plus search-mode headers, not raw-source/exact-legal-route evidence or candidate counts. Those fields remain unavailable; never infer them from result count. This is separate from the in-memory embedding test and does not certify the MCP exact-legal/raw-source route. A denied/unavailable identity is `blocked`, never elevated automatically.

Thresholds are explicit configurable benchmark acceptance criteria, not product quality guarantees: example fixtures start with CER <= 0.02, WER <= 0.05, full expected logical-unit/critical-value coverage, Recall@5 >= 0.8 and nDCG@5 >= 0.7. Report them as initial QA thresholds with sample sizes. Reliability/errors and ACL violations cannot be hidden by favorable means. Missing annotations leave that metric unscored.

## Production integration boundaries

Reuse production extraction dispatch `kb_service._extract_text_from_file`, its effective document config loader and the same PDF/Excel/Office parsers. Do not route through preview-only endpoints: the current preview handler has differing options and is not proof of ingestion behavior. Fail preflight if the DB settings snapshot cannot be read; do not let the loader's permissive default fallback masquerade as testing current settings. Obtain the configured vision provider when the production path permits vision fallback.

OCR stage uses `OcrService.ocr_image` with the DB/prompt/model currently selected; test image/PDF pages directly and report the effective path. Extraction-stage scan cases separately exercise the production OCR trigger/fallback, so a direct OCR pass does not prove ingestion invoked OCR. Record raw-versus-refined path where refinement is configured.

Use `ProviderRegistry.get_embedding(task='document'/'search_query')` and `configured_rank_candidates`; use the authenticated `/api/wiki/search` contract for live-index tests after inspecting its exact request/response schema. No `all_scopes=True`, forged identity headers, account promotion, persistent test sources, database writes, re-embedding or indexing actions. Read-only benchmark DB sessions and close/rollback on exit. Reject a detected configuration change during the run or mark the affected run non-comparable; do not silently change operating settings to test alternatives.

The initial starter run may score extraction offline while OCR/embedding/rerank are blocked by missing/unavailable configured providers. Publish that honest report. Live search requires the caller's existing authorized token and explicit real-ID judgments; no automatic token discovery or saving.

## Comparison and validation

Match stage + case ID + dataset/reference hashes. Show incompatible/missing/added cases instead of subtracting unrelated aggregate scores. Show metric direction (CER/WER lower is better; ranking higher is better). Provider/engine/config changes are visible as the independent variable; dataset or normalization changes prevent direct accuracy regression claims. Compare paired scored cases, and show reliability/status regressions separately.

Tests must include known metric values and insertions, accents and blank pages; retrieval duplicates/ties, short/empty outputs, no-relevant cases and graded nDCG; actual parser fixtures; fake providers only for deterministic runner/error/secret-leak contracts; configuration drift, disabled/fallback rerank, deadline/interruption and partial persistence; HTML/CSV escaping and comparison mismatch handling. Run actual configured-provider smoke cases when available and label them separately from offline tests.

## Non-goals

No LLM-as-judge sole accuracy score, chat response grading, legal-validity certification, new monitoring service, admin UI, broad automatic corpus ingestion or automatic tuning/model switching. No claim of end-to-end Wiki readiness from connection tests or synthetic benchmark scores.
