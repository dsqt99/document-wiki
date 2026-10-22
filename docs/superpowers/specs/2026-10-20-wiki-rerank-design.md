# Wiki search reranking

User approved: use reranking in both Wiki search surfaces; score must be strictly greater than the saved threshold (default 0.3). On reranker failure return hybrid results with an explicit warning. Model setup must use the same Anthropic/OpenAI/Gemini/Custom picker as other AI providers.

## Design

Add an independent `rerank` model kind and active model key. Reuse provider presets and custom-model CRUD/key encryption. Custom supports `/rerank`, OpenAI chat, and Anthropic Messages protocols; known providers use their existing native clients. Preserve the currently configured HTTP reranker as a legacy catalog entry until an administrator selects another model. No global LLM switch or reindexing is needed.

Retrieve at most 100 readable candidates using hybrid chunk search plus title/slug/summary matches (including pages without chunks). Apply source/type/tag/status and authorization filters before sending candidates to any model. Score title plus winning chunk; use bounded batches for LLM rerank with JSON-only indexed scores. Validate finite scores, unique indexes and complete coverage. Reject malformed/partial model responses and fall back to original hybrid order, explicitly labelled. Never compare a fallback heuristic or RRF score against the model threshold. A successful rerank with no passing scores returns an empty result.

`/wiki/library?q=` and `/wiki/search` share this service. Filter by score > threshold, sort descending, then paginate. Library returns search metadata (mode, warning, threshold, candidate limit and count). Existing `/wiki/search` list shape is retained with metadata headers. Empty search remains a normal paginated library query. Search totals describe the bounded candidate set, not every possible database match.

Quick search uses the server search, debounces requests, rejects stale responses, preserves relevance order instead of grouping by page type, and retains scope when navigating. Both UI surfaces show fallback warnings and actionable errors.

Settings reuse the existing picker with a dedicated rerank card: model activation, encrypted provider/custom keys, enable switch, threshold, and a labelled sample test showing actual scores and elapsed time. Threshold uses the selected model's native scale; changing models requires recalibration.

Implementation details: candidate selection is independent of pagination, with page-level reciprocal-rank fusion (k=60) of hybrid and title matches, deduplication by page ID and ID tie-break before the 100-page cap. Metadata separates candidate count from passing total. LLM scores use 0–1, batches of 10, two concurrent calls, 2400-character scoring inputs and a 30-second whole-request deadline; one bad batch discards every score. Native rerank requests ask for all candidates. Disabled mode is `hybrid`; failed mode is `hybrid_fallback` with a warning. All settings, model CRUD/activation and sample tests require `org:settings:manage`.

## Verification

Tests cover strict threshold including equality/zero/all-rejected, malformed scores and partial/duplicate indexes, LLM protocols and batching, dynamic config/key masking, ACL/filter-before-rerank, both routes, pagination/order and fallback labels. Run existing reranker/search and settings regressions, frontend type/lint checks, and a real existing endpoint probe. Keep the running frontend in dev mode; restart only API after confirming changes.
