# LLM summaries for Wiki pages

- Use the configured LLM on all current page content; separate this from source metadata extraction and deterministic opening-paragraph summaries.
- Split long content without dropping text, summarize each part, then combine. Vietnamese prompts preserve duties, conditions, exceptions, numbers and deadlines; treat page text as data and disclose damaged OCR. Validate complete structured output; never silently fall back to an excerpt.
- Reuse owner-scoped background jobs and per-page progress. Support one page or the readable library; checkpoint and continue large batches. Do not hold a database transaction during model calls. Recheck title, content, scope and previous summary before saving.
- Keep existing TEXT storage and no schema migration. Add an AI action beside each page summary and explicit AI labels plus a review dialog for bulk regeneration. Preserve multiline summaries.
- Verify full-content input, long-page coverage, invalid output rejection, stale-edit protection, scope filtering, checkpoint continuation, frontend types/build and one targeted real LLM run. Do not run all library pages for QA.

Source audit: metadata extraction and MRP Wiki compilation already call LLMs; there is no separate persisted source-content summary pipeline. This change adds page summaries only.

Verified: 102 backend tests pass (processing, clipping, legal fulltext, Wiki guard and draft publication); TypeScript and changed-component ESLint pass; Docker frontend production build succeeds and is deployed on localhost:3219. API/worker restarted only after the queue was idle. Real Qwen/Qwen3.5-9B job for Điều 19 completed with summary and indexing saved; later clauses and OCR uncertainty appear in the displayed summary. Browser verified single-page action, details popup, AI bulk menu and bulk confirmation/cancel. No library-wide LLM job was executed.
