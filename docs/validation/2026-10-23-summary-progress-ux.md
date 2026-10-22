# Summary progress UX — 2026-10-23

## Result

Historical completed results no longer appear as active progress on page load or
refresh. Current work uses a compact inline notice. Successful completion hides
after six seconds, paused during hover, keyboard focus or open details. Warnings
remain until dismissed. The latest retained result remains accessible from the
maintenance menu and individual Wiki-page controls.

Small detail results use wrapping document rows with a completed-result heading,
status and meaningful counters. Search/status filters appear for larger results
or existing filters; pagination appears only when needed. Historical failures
retain their job-level message and errors. Long error lists scroll inside the
dialog body so the close controls stay visible on small screens.

## Verification

- **32 frontend tests passed**, including job lifecycle, stale responses,
  dismissal/history, expired jobs, presentation controls and actual result HTML.
- Full frontend TypeScript check and focused ESLint passed.
- Production Docker QA build passed, including Next.js TypeScript checks.
- Independent spec-compliance and code-quality reviews passed.
- Browser tests used real components and the real polling hook with an isolated
  mock transport; these tests did not start real AI or document-processing jobs.

### Browser observations

| Case | Observed result |
| --- | --- |
| Historical completion on mount | No notice, completion callback count 0 |
| Open retained result | Available from maintenance menu; heading receives focus |
| Close details | Focus returns to the stable maintenance trigger |
| Active work | Compact notice, processed count, current page and progress |
| Active to complete | Callback count 1; title changes to completed-result wording |
| Dialog open past six seconds | Stays open with focus intact |
| Unfocused successful notice | Disappears after six seconds; result remains accessible |
| Warning past six seconds | Remains visible |
| Dismiss warning then refresh | Warning stays dismissed; history retains failure details |
| Eight rows / unmatched search | Filters remain available, empty state can clear filters |
| 52 rows / last page | Correct range 51–52 / 52 and navigation controls |
| One row at 390×640 | Dialog 358×286, heading focus, no horizontal overflow |
| Five long errors at 390×640 | Dialog fits at y=48..592; body scrolls (362px viewport / 596px content), close button visible |
| Status fetch fails then recovers | Retryable error without fake progress; retry clears it |
| Active job expires (404) | Spinner/polling stops; actionable failure message |

Browser screenshots of desktop, mobile and long-error states were displayed in
the chat. The optional fixture is in `frontend/scripts/summary-progress-fixture.tsx`.
It is not a production route. For reproduction, temporarily export its default
component from `src/app/summary-progress-qa/page.tsx` and run a local frontend build;
remove that route before building the deployment image.

## Deployment

Deployed at **2026-10-23 00:37 Asia/Bangkok** from revision
`3a8848524279bc371331fadb8a892f01e5aa75bc`:

- Frontend image: `cahy-wiki-frontend:summary-ux-261023-3a884852`.
- Final production build passed, including TypeScript; route list excludes QA.
- `GET http://localhost:3219/knowledge` returned 200.
- `GET http://localhost:3219/summary-progress-qa` returned 404.
- Backend `/health` remains healthy, revision `1bb420a2`.
- API and both worker start timestamps exactly match their pre-deployment values:
  API `2026-10-22T16:58:48.82250533Z`, worker
  `2026-10-22T16:59:00.402687096Z`, skills worker
  `2026-10-22T16:59:00.416421767Z`.
- Only FRONTEND_IMAGE was updated in the original runtime `.env`. The feature
  branch/worktree is retained for continued work. The QA container/tab was removed.
- Final rerun: 32/32 frontend tests passed; working tree contains only the final
  documentation update before its commit.

The temporary QA route has been removed from the source tree. Backend code,
summary generation, permissions and original uploads are outside this UI change.
