# Summary progress UX Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline. Steps use checkbox syntax.

**Goal:** Show progress only for active work, keep recent results accessible, and simplify small-result details.

**Architecture:** Separate pure job-state transitions from the React polling hook and presentation. Own selected details in the hook so hiding a notice never removes an open dialog. Keep backend APIs and source workers unchanged.

**Tech Stack:** Existing Next 16.4.2, React 19, Base UI Dialog, Tailwind 4, node:test. Reuse installed tools; no new runtime dependency.

## Task 1: Job lifecycle regression coverage

Files: create `frontend/src/components/knowledge/summary-job-state.ts`,
`frontend/src/components/knowledge/use-summary-maintenance.ts`,
`frontend/tests/summary-job-state.test.mjs`; modify `summary-maintenance.tsx` to re-export the existing hook/types.

- [x] Write failing node:test cases for historical completed jobs remaining hidden with no completion callback, observed active completion notifying once, dismissal surviving refresh, new jobs reappearing, immediate completion, and stale poll responses not replacing a new job.
- [x] Run `node --experimental-strip-types --test tests/summary-job-state.test.mjs`; confirm missing-module/failing assertions before implementing.
- [x] Implement a typed reducer with snapshot/receive/dismiss actions. State separates tracked job, recent result, visible notice and completion event ID. Only receive from a started job or transition out of observed active work emits completion. A terminal same-ID job cannot regress to queued/running.
- [x] Extract the polling hook. Keep pending fetch generation guards; poll only the tracked active ID. Missing job (404) becomes an actionable terminal failure. Expose visible job, latest result, detail selection, open/close details, refresh and existing menu/confirmation actions.
- [x] Re-run lifecycle tests and existing frontend tests; ensure no historical onComplete/cache invalidation on mount.

## Task 2: Compact notices and retained result access

Files: `summary-maintenance.tsx`, `wiki-summary-actions.tsx`,
`frontend/src/app/(portal)/knowledge/page.tsx`.

- [x] Render a compact inline status with active/queued/terminal labels, counts and details link. Successful terminal notices dismiss after 6000ms; errors persist. Pause timer for hover, contained focus and open details.
- [x] Add latest-result item to shared maintenance menu and a text action to individual-page controls. Render selected job dialog through the shared companion component independently of notice visibility.
- [x] Wire retry to refresh and stable detail actions to all three consumers. Preserve permissions and original confirmation for rebuilding all summaries.

## Task 3: Responsive result details

Files: `summary-job-details.tsx`, presentation tests and narrowly scoped browser fixtures if needed.

- [x] Add regression coverage for compact rows at <=5 items; history/active headings; filters for >5 or active filters; pagination only when necessary; errors and empty results.
- [x] Use terminal-result wording, readable state badge and nonzero metrics. Render small results as wrapping rows; retain table for larger desktop batches and mobile wrapping rows.
- [x] Focus heading via Base UI `initialFocus`, preserve close/Escape and focus restoration. Show manual refresh only for active work or fetch errors. Keep source-ellipsis inspection intact.

## Task 4: Verification, review and frontend deployment

- [x] Run all frontend tests, `tsc --noEmit` and focused ESLint; fix concrete failures.
- [x] Inspect actual components in a local browser with isolated mock summary responses: idle, running, completion/autohide, warning, history, one row, many rows, search empty and mobile. No live AI jobs needed.
- [x] Independent code review; address actionable findings and rerun affected checks.
- [x] Commit code and build production frontend image with existing API URL args and revision label. Deploy only `frontend` using original runtime project directory and existing backend image. Persist only FRONTEND_IMAGE in runtime .env.
- [x] Verify container revision, host HTTP response and worker start times unchanged. Save screenshots and validation report.
