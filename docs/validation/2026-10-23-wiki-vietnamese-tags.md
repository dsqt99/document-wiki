# Review upload labels and Vietnamese Wiki tags — 2026-10-23

Source commit: `cf4171a`, branch `feature/optimize-261022`.

## Review of the supplied fix

The currently deployed upload changes add `security_label` to Wiki upload and source edit, preserve the independent scope/management department fields, and use the same four values and Vietnamese names as Chat. Wiki scope hints explain that scope and clearance both apply. The runtime API still restricts label changes to admins or `doc:edit:all` and rejects explicit labels above the actor's clearance.

Two concrete Wiki UI defects were corrected alongside the requested translation:

- The form initially selected INTERNAL even for a PUBLIC uploader, and the selector kept an out-of-clearance current option selectable. New uploads now default to PUBLIC for PUBLIC users and INTERNAL for eligible users. Invalid higher options are omitted. Two component regressions failed before the fix, then passed.
- Source edit exposed an active label selector to own-department editors, although the server rejects that operation. The control is now read-only with a permission explanation unless the user is admin or has `doc:edit:all`; unchanged labels are not sent. No server permissions or user clearances were changed.

The six frontend files added by the preceding label rollout were retained from its build snapshot, compared against this worktree before editing. The original dirty checkouts were left untouched.

One remaining Chat-side review point: `Knowledge.svelte` still initializes/resets `uploadLabel` to INTERNAL while its options are filtered by clearance. The PUBLIC upload scenario was not accepted end-to-end in this run. This Wiki-only build does not claim that every Chat upload scenario has passed.

## Vietnamese labels

| Value retained in API/database | Vietnamese UI |
|---|---|
| seed | Sơ khởi |
| developing | Đang phát triển |
| mature | Tương đối đầy đủ |
| evergreen | Cốt lõi ổn định |

The badge, status menu, existing facets and graph legend share the status vocabulary. English remains available for status badges in the English locale. The type badges/group headings now display Trang Wiki, Văn bản nguồn, Mục lục, Nhật ký and Trang tổng hợp. Graph scope/relation labels and page-type hover labels were also translated. Existing identifiers, lifecycle behavior, colors and source data remain unchanged.

## Verification

- Production Docker/Next.js build succeeded, including TypeScript and generation of 20 static routes. Local standalone `tsc` initially encountered stale generated types for an old removed QA page; the fresh Docker build excludes that cache and completed TypeScript successfully.
- Targeted ESLint passed, including the final graph changes.
- 6 Node tests passed (4 security-label cases and 2 existing source-search cases).
- Existing source workflow, Wiki navigation and 21 session-lifecycle checks passed.
- Real React server rendering with the actual I18nProvider and badge components displayed all 4 Vietnamese status labels and 5 type labels.
- Deployed `/knowledge` and `/wiki` returned HTTP 200. Compiled runtime assets contain the new status translation key, Vietnamese label, graph legend and read-only permission hint.
- Live browser navigation reached the Chat SSO login page. No credentials or permissions were changed. Authenticated upload/edit acceptance was not completed in that expired browser session; passing unit/build checks are not represented as full upload E2E acceptance.

## Deployment

Frontend image: `cahy-wiki-frontend:labels-vi-261023-cf4171a`.

Image ID: `sha256:924fd9139155af810f59b3444bc0d092d678037590fd3e8957484e8fb83f7ff2`.

Previous frontend: `cahy-wiki-frontend:label-261023-2b178fb-r2`, image ID `sha256:fdee5fe78485cde8e3978734274f9f71f74bdf29ef48c88975dd35933d3b5e6b`.

Appended `deploy/compose.wiki-labels-vi.json` to the three existing Compose files; deployment arguments are saved in `deploy/wiki-labels-vi-compose-args.json`. Only the frontend was recreated. Wiki API and both workers remain on `cahy-wiki-backend:label-261023-2b178fb`, and Chat keeps its current deployed image. No release merge was performed.
