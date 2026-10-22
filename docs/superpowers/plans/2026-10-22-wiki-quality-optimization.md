# Wiki quality optimization implementation plan

> For agentic workers: execute the independent frontend, retrieval and pipeline tasks in parallel, with root integrating serialization, chat validation and deployment. Preserve existing edits and review each diff before integration.

**Goal:** Make document quality visible and retrieval/publication behavior reliable across Wiki and chat.

**Architecture:** Keep current dual pipeline and access controls; add measured quality metadata and a shared rerank contract. Deploy a synchronized feature snapshot without dirty source mounts.

**Tech Stack:** FastAPI, SQLAlchemy, ARQ, Milvus, Next.js/React, Python LangGraph chatbot, Docker Compose.

- [x] Preserve deployed source changes in feature worktree and retain 200 MiB upload fix.
- [ ] Frontend: knowledge-table/index.tsx, status-dot.tsx, types.ts, upload-dialog.tsx; full-width expansion, quality panel, warnings, unified processing UI; focused UI tests and type/lint checks.
- [ ] Retrieval: retrieval_service.py, wiki_search_service.py, wiki_reranker.py, mcp/tools.py, knowledge_payloads.py; shared rerank configuration, lexical outage fallback, bounded/paginated reads and regression tests.
- [ ] Pipeline: worker.py, parsers/pdf_parser.py, ai/mrp/pipeline.py/verifier.py, embedding storage/indexing services and new source_quality.py; measured coverage, factual publish blockers, retained expired-review sources and regression tests.
- [ ] API: sources.py SourceResponse/_to_response; expose source_quality.public_source_quality consistently and test legacy records.
- [ ] Chat: evidence/export validators and focused regression tests; preserve unrelated branch edits and authorization boundaries.
- [ ] Integration: run Wiki suite and chatbot targeted tests, build frontend, inspect responsive browser fixture, resolve failures and review changes.
- [ ] Deployment: immutable matching backend/frontend tags from feature checkout, migration compatibility, safe worker transition, health/version/live upload verification; document exact checks and residual limits.
