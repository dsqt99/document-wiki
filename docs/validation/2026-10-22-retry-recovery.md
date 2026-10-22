# Wiki retry recovery, 2026-10-22

## Observed runtime failure

The live database initially contained 50 sources: 40 ready and 10 partial.
All 10 partial sources had a ready raw-text index and a failed Wiki branch.
Nine plans retained page-generation failure stubs containing `APIConnectionError`
or `[ai_unavailable]`; the source-level error retained only failed slugs. The
outage recovery cron therefore did not recognize these historical failures.
One source had stopped during REFINE and was marked failed by the stuck-worker
sweeper. Its plan contained 79 pages and no persisted drafts.

The active AI provider passed a real generation probe. A manual Wiki-only retry
of source `9562c748-7fdb-4a08-948e-952fe59640a6` then completed in 48 seconds:
4 planned, 4 published, 0 failed, no vector-index failures, aggregate ready.
This distinguishes a historical upstream outage from a corrupt uploaded file.

## Code fix

Revision `de7b5e4`:

- Detect historical AI outages from actual failed drafts when the source error
  lacks the marker. Fetch plans in one batch restricted to candidate source IDs.
- Use the same classification in the processing-menu failure counts and cron.
- When retry resumes VERIFY/COMMIT, regenerate failed, empty, incomplete or
  factually blocked drafts rather than replaying that invalid checkpoint.
- Keep a valid checkpoint reusable for a downstream persistence/index retry.

Existing ready raw indexes and original uploads are retained by Wiki-only retry.
This patch does not change the planner or add per-page checkpoint persistence;
an interrupted REFINE job can still need to regenerate that stage.

## Verification

- Regression cases reproduced before the implementation (11 failures).
- Full suite after initial retry fix: **748 passed, 30 skipped, 10 warnings**.
- Independent code review: no actionable regression finding.
- Backend and frontend production images rebuilt from revision `de7b5e4`.

## Live recovery

The deployed classifier detected 8 historical AI failures among the remaining
9 sources. The ninth was the interrupted worker job. All 9 were requeued as
Wiki-only jobs, starting with the smallest plans. The railway-law source
`bed6f731-084c-4fb0-9657-c2aaa0359e5b` recovered with 8/8 pages published.

The first retry of Decree 238 generated 3 real drafts, but all were blocked for
unsupported legal references. One draft referred to `100/2019/NĐ-CP` while the
source amends `168/2024/NĐ-CP`; others copied an incorrect `NCCP` identifier from
the historical plan. This is a generation-quality failure, not an upload/parser
failure. The publication gate correctly remained closed.

Follow-up code revision `a19d12a` adds explicit source authority over plan/slugs
and one bounded corrective generation for objectively blocked drafts. Corrected
output must pass the same factual gate, lose no table row, and retain at least
85% of draft length. Invalid correction remains blocked. A real read-only test
against the three failed drafts corrected 2/3; the third remained blocked. This
does not establish semantic factual accuracy for arbitrary generated text.
Failure reasons are now stored by slug and exposed in quality warnings/errors.

Follow-up verification: **756 passed, 30 skipped, 10 warnings**; 8 repair regression
cases; independent review found no actionable issue. The worker was gracefully
drained for deployment; one 8-page job completed and one long-running job was
cancelled by ARQ after the shutdown grace period and retained for retry. Remaining
jobs stay queued. Queue acceptance alone is not successful processing.
