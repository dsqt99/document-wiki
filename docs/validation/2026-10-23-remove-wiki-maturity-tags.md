# Remove unreliable Wiki maturity tags

The user requested removal because the maturity labels were not assigned reliably and did not help readers assess documents.

Implementation: `6c5a671` on `feature/optimize-261022`.

- Removed maturity badges from page details, the Wiki library and orphan-page diagnostics, including the matching diagnostics table header.
- Removed the manual maturity update menu and its PATCH request from the page UI.
- Removed maturity graph coloring, counts, legend and mode controls. Scope coloring and relation filters remain available.
- Replaced maturity-colored page-tree dots with neutral decorative dots.
- Removed the unused badge component, facet constants and translations.
- Preserved security labels, visibility scopes, origin/type badges, document processing statuses and existing backend/API status fields. No data migration or backend restart is required.

Checks completed before building:

- Targeted ESLint: passed for all seven remaining changed source files, including the deleted component's consumers.
- Security-label and select-search regressions: 6 passed.
- Session lifecycle regression checks: 21 passed.
- Source workflow and Wiki navigation checks: passed.
- `git diff --check`: passed.
- Source scan: no maturity badge, facet, graph-mode or translation references remain in the frontend UI.

Production verification:

- Clean Docker production build passed, including TypeScript and generation of all 20 static pages.
- Deployed frontend image: `cahy-wiki-frontend:no-maturity-261023-6c5a671`, revision label `6c5a671`.
- HTTP checks for `/wiki`, `/knowledge` and `/wiki/graph`: all returned 200.
- Scanned all 61 deployed JavaScript assets: no removed maturity label translation keys or associated Vietnamese quality labels/menu text remained.
- API and both workers retained `cahy-wiki-backend:label-261023-2b178fb` with unchanged uptime; API remained healthy.
- Authenticated browser acceptance was not repeated: the previously observed SSO session had expired. HTTP checks confirm page delivery, rather than authenticated rendering of document content.

Rollback frontend image: `cahy-wiki-frontend:labels-vi-261023-cf4171a`.
