# Wiki Rerank Implementation Plan

> Execute inline, preserving the existing dirty feature branch. Review the completed change independently.

**Goal:** Provider-configurable reranking shared by Wiki search surfaces with strict score filtering and explicit hybrid fallback.

**Architecture:** Independent model-kind/config adapter, common permission-filtered search service, existing provider picker and custom-model persistence. No schema migration or changes to chatbot retrieval fallback semantics.

**Tech Stack:** FastAPI, SQLAlchemy, existing HTTP/LLM providers, Next.js client components.

- [x] Write failing tests for the scorer (complete indexed finite scores), strict threshold and fallback.
- [x] Implement `app/services/wiki_reranker.py`; extend only custom-kind/config registration required for rerank.
- [x] Write failing tests for common search, authorization constraints, filtering before pagination, and route integration.
- [x] Implement `wiki_search_service.py`, wire library/search routes and return search metadata.
- [x] Add protected rerank catalog/switch/test routes and validation for runtime search settings; verify keys encrypted/masked and active custom model deletion blocked.
- [x] Reuse `ProviderModelPicker` in `rerank-settings-card.tsx`, add rerank custom protocol choices, and mount in Settings.
- [x] Connect quick search to backend, keep relevance order/scope, and show pending/error/fallback states. Add warnings/count scope to library.
- [x] Run targeted pytest and frontend type/lint checks; independently review diff and fix findings.
- [ ] Reload API and verify live search/UI after Docker Desktop engine recovers. See docs/reviews/2026-10-20-wiki-rerank.md.
