# Legal End Matter Implementation Plan

> **For agentic workers:** Use the existing test-driven workflow; preserve the workspace's unrelated changes. Review scoped changes before runtime reload.

**Goal:** Keep terminal notes/appendices separate from article chunks and avoid interpreting their internal legal labels as main document structure.

**Architecture:** A shared read-only detector returns exact section offsets. The source chunker uses those boundaries for opaque tail spans while retaining existing main-body article, table and token behavior.

**Tech Stack:** Python, existing PDF/Word normalized text, pytest, ARQ worker.

---

### Task 1: End-section detection

- Add failing regression tests in the tracked `tests/test_chunk_budget.py` for explicit notes/appendices, styling, quoted/code/table/prose false matches and notes before the next main article.
- Implement a focused `legal_endmatter.py` detector retaining exact raw offsets and per-section labels.
- Verify detector tests pass.

### Task 2: Chunk integration

- Add failing tests for main article/tail isolation, independent breadcrumbs, internal Điều/Chương labels, multiple tails, cross-page spans and long tail windows.
- Integrate boundaries into `_article_boundaries`, `_find_headings`, and `build_source_chunks`, preserving all existing main-document behavior.
- Verify chunk/retrieval/hierarchy tests and exact source slices.

### Task 3: Verification and runtime

- Review the scoped diff and run related regression suites.
- Dry-run representative stored documents and report detected boundaries/counts without modifying raw text or Wiki edits.
- Reload the affected worker after tests pass. Reindex affected existing source chunks only when a concrete stored-tail sample is available.
- User confirmed separate Wiki pages: isolate hierarchy tails; persist them as extracted pages with stable identity and manual-edit protection; include full-text API/rendering support and opaque Wiki chunk indexing.
