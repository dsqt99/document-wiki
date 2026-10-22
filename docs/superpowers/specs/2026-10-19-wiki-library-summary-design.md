# Wiki library and summary maintenance

Approved by the user on 2026-10-19: implement this design in feature_261019.

## Navigation and reading

UX revision requested on 2026-10-19/20: the original three-tab layout duplicated the sidebar's Documents and Knowledge destinations. Documents (`/knowledge`) now owns uploads, processing and source operations. Knowledge types are a contextual configuration view. Knowledge (`/wiki/law`) owns the reading library with Văn bản and Wiki views. Preserve primary sidebar labels and existing route slugs. Legacy `/knowledge?tab=wiki` links migrate to `/wiki/law?view=wiki`, retaining filters and pagination; the return destination remains strictly limited to these local library paths.

Wiki lists readable pages with a horizontal search/filter toolbar (source document, page kind, status), useful counts, summaries and links to read/edit with the correct scope. Show article names without an exact repeated source suffix; source provenance remains below each result. Remove the redundant Read button since the title is the read link. Legal document lists use a full-width search/results layout and an accessible filter Sheet with removable condition chips. Detail-page tabs belong in the detail page rather than being repeated on every result.

Documents show seven operational columns, with progressive disclosure for supporting metadata and responsive column visibility. Keep errors, progress, row/bulk actions, sorting, source previews, scope and all original metadata accessible. Preserve the existing blue accent, sans type, Base UI components and theme tokens. Applied design-taste-frontend context: public-sector internal application, variance 3, motion 2, density 5; no marketing hero or additional component system.

The reading/editing view no longer reserves a second persistent sidebar by default. A labelled Danh mục button opens the catalogue as an accessible overlay, defaulting to the active page's document; users can still choose all documents. Mobile uses the same overlay. Avoid resetting explicit filter changes on each page navigation. Keep create, search, scope-aware navigation, and reader mode working.

## Summary maintenance

The Wiki view's Tóm tắt Wiki menu and Documents' Xử lý nội dung menu share the same summary actions and job/progress logic. Both offer update missing/clipped summaries and regenerate all summaries. The processing menu omits duplicate status shortcuts (the table already has a status filter), explains document information extraction, and moves search index maintenance into a submenu. Metadata extraction labels distinguish first extraction (records without extracted_at) from extracting all records again; manual field corrections remain protected by the existing service.

Both summary operations use the latest stored wiki content, including human corrections, excluding reserved/empty pages. Legal article summaries reuse the complete opening paragraph logic. Other page summaries use a complete meaningful opening paragraph, stripped of presentation markup and citation metadata. Do not regenerate the full wiki or overwrite content, titles, version history or access scopes.

Run as registered background worker jobs, deduplicate simultaneous starts, expose queued/running/completed/failed status with processed/updated/failed counts and progress, and show completion/errors in the UI. Authorize start and status with existing processing management permission, constrain candidate selection to the requester's readable wiki pages, and use the same scope for counts. Update affected search embeddings through the existing indexing path. Per-page errors do not prevent remaining pages from being processed. Queue/Redis failures must be visible, never report false success. Handle edits made while a job runs by reading and locking current page rows before summary calculation. Persist summaries before best-effort indexing and report indexing failures separately.

## Verification

Backend regression tests cover candidate selection, scope restriction, legal/generic summaries, edited pages, queued jobs, duplicate submission, progress and per-page failure. Frontend must pass targeted lint and TypeScript checks, plus browser verification of all tabs, filters, overlay, edit navigation and processing status at laptop/mobile sizes where runtime permits.
