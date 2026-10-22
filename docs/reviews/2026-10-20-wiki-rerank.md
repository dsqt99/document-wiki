# Wiki search rerank verification

Implemented in feature_261019 without changing chatbot/RAG retrieval fallback behavior or the active compilation LLM. No migration, embedding rebuild, commit or push.

- Independent rerank model catalog: Anthropic, OpenAI, native Gemini and custom HTTP `/rerank` / OpenAI chat / Anthropic Messages.
- Existing HTTP endpoint retained as the initial active choice. First live endpoint probe succeeded in 0.75 seconds for three short public sample passages: 0.91186 for the relevant passage, 0.01781 and 0.0000168 for unrelated passages.
- Runtime settings/key encryption, strict `score > threshold` filtering, all-rejected empty results, original hybrid order plus explicit warning on unavailable/malformed/partial scoring.
- Both library search and quick search use the shared backend, with filters before candidate cap/scoring, scope-aware navigation, relevance ordering and loading/error/stale response handling.
- Existing list API preserved; fallback headers exposed for cross-origin consumers. Paginated library JSON carries mode, warning, threshold, candidate count and cap.
- Reviewed independently. Fixed debounce/Enter stale selection, null-threshold validation, and CORS metadata findings. Request-scoped LLM connections close after scoring.

## Completed checks

152 passed: test_wiki_rerank, test_custom_models, test_config_service_ocr, test_search_accuracy, test_rerank_mode, test_reranker_service, test_api_parity_fixes, test_processing_ops, test_wiki_write_guard.

Frontend TypeScript (`tsc --noEmit --incremental false`) and scoped ESLint passed. No production build run; the existing dev process on port 3219 was retained.

## Runtime limitation

After the initial endpoint probe, Docker Desktop Linux engine began returning HTTP 500 for container queries/exec (also with API 1.45). API port 5155 timed out. Frontend port 3219 initially timed out but a subsequent request to `/settings` returned HTTP 200. End-to-end real-data search, API reload and visual verification remain unconfirmed. No Docker Desktop restart or unrelated container/process shutdown was attempted. API must load the new sources after the environment recovers.
