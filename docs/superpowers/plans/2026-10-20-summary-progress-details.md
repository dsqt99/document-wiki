# Summary repair and progress details

Requested: explain four processed Wiki pages with zero summary updates and expand job progress into a detailed popup.

- [x] Reproduce against current data and ensure trailing dots in Wiki/template text do not cause permanent false positives. All four stored summaries matched the computed opening paragraph, including their literal trailing dots.
- [x] Add regression coverage for unchanged summaries, unavailable text, page outcomes, indexing failures and owner-only paginated details.
- [x] Store per-page queued/running/updated/unchanged/skipped/error outcomes in Redis separately from lightweight job progress. Include source document names, current stage and readable reasons. Preserve the most recent job for reopening results after a reload.
- [x] Add an expandable progress dialog with status filters, page/document search, pagination and live updates; preserve compatibility with older jobs without stored details.
- [x] Show Wiki ellipsis diagnostics separately from summaries that actually need regeneration.
- [x] Verify tests, types/lint, live counts and browser UI. Update API/worker only when the job queue is idle, then rebuild the frontend Docker instance serving localhost.

Verification: 69 relevant backend tests passed; frontend TypeScript and Docker production build passed. Ran a real targeted verification job for the four former candidates after asserting that all computed summaries match existing summaries: processed 4, unchanged 4, updated 0, failed 0. No Wiki content or summaries were rewritten. Browser checks verified the expanded popup, four explanatory rows, document-name search, failure filter, corrected missing-summary count of zero and separate four-page diagnostic popup. Screenshot: summary-job-details.png in the current task visualization directory.

Keep changes in the shared checkout; no commits and no changes to auth/session work.
