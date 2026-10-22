# Summary progress UX (draft for approval)

## Problem and evidence

The knowledge page promotes `active_job || recent_job` into its visible progress
state on every mount/refresh. A completed job can consequently reappear after
dismissal and after navigation, despite no task being active. Initial historical
results also trigger the completion callback. The detail dialog always calls
itself progress, shows active-task guidance, filters and pagination even for one
completed item, and automatically focuses the search field.

## Recommended interaction

1. Idle: render no progress banner. Keep the most recent retained job accessible
   under the existing summary maintenance menu as “Kết quả cập nhật gần nhất”.
   The backend currently retains one recent result for 24 hours; do not imply a
   complete permanent activity history.
2. Queued/running: show a compact inline status with a clear state label, pages
   processed, the current page when available, and “Xem tiến trình”. Closing
   details leaves the job running. Poll only active jobs.
3. Completed without warnings: briefly show a compact success result for a job
   started/observed in the current view, then hide it after 6 seconds. Historical
   completed jobs do not announce themselves as new completions. The result
   remains available from the menu. Do not automatically open a modal.
   Pause auto-hide while the notice is hovered, contains keyboard focus, or its
   details are open, so reading or keyboard interaction is not interrupted.
4. Failed/completed with failures: keep an actionable, dismissible warning result
   until dismissed. A refresh does not revive a dismissed historical result.
   A new active job still appears even if a previous result was dismissed.
5. Fetch failures: a separate compact retryable error, not an invented running
   job. A missing/expired retained result has clear copy and no endless spinner.

## Details

- Active title: “Tiến trình cập nhật tóm tắt”. Terminal title:
  “Kết quả cập nhật tóm tắt”. Show a readable state badge and concise counts.
- Completed view uses completed-result guidance. Hide zero-valued statistics
  except meaningful totals, and avoid active-task wording after completion.
- For small unfiltered results (up to 5), use compact document rows that wrap
  naturally on mobile. No horizontal table scrolling for a single item.
- Show search/status filtering for larger results or an already applied filter.
  Retain filters while a user edits them, even if matches shrink below 6 items.
- Show pagination only when there is more than one page or an offset is active.
- Show “Làm mới” for an active job or a failed detail fetch, not an immutable
  successfully loaded completion result. Focus the dialog heading initially,
  preserve escape/close behavior, keyboard focus and the existing visual theme.
  The dialog uses Base UI Popup's documented `initialFocus` for a heading ref.
- Own detail selection independently of the transient notice. Auto-hide removes
  only the notice; an open dialog stays open until explicitly closed and tracks
  the same job's live updates. Return focus to a stable trigger on close.
- The individual Wiki-page action has no maintenance menu: add a compact
  “Kết quả cập nhật gần nhất” text action beside its existing summary button when
  a retained result exists. This supplies the same recovery route after hiding
  or dismissing a notice without keeping a large idle panel visible.
- Preserve the separate source-ellipsis inspection flow and source page links.

## Alternatives considered

- Always retain a collapsed result strip: discoverable but still leaves stale
  maintenance chrome occupying the knowledge list when nothing is active.
- Hide all completed results permanently: very clean but loses access to errors
  and audit details. Prefer the existing menu as the recovery point.

## Scope and verification

Frontend-only change to shared summary maintenance/detail components, including
knowledge, Wiki library and individual-page consumers. Keep backend retention,
permissions, summary generation and document processing unchanged. Verify idle
mount, old-result dismissal/refresh/navigation, active-to-completed transition,
immediate zero-work completion, persistent errors, new jobs, expired results,
single result, many results, filtered empty results and keyboard/mobile layouts.
Run focused behavioral checks, TypeScript, relevant lint and production build;
inspect the resulting UI before deployment. Do not restart active backend jobs
for a frontend-only update.
