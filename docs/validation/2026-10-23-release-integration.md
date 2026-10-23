# Release integration — 23/10/2026

The user requested push and merge into `release/cahy`. The fetched release tip `dcbc793` is an ancestor of feature source `eafde0b`; integration preserves all 28 feature commits, including the two deployed custom-model fixes.

Pre-merge verification against this source:

- 48 selected Python modules: **652 passed, 4 skipped, 2 warnings**. Skips require an isolated PostgreSQL test URL (3) or `xlwt` (1); warnings are existing AsyncMock/session.add substitutes. No running database was used by this suite.
- Frontend Node tests: **34 passed**.
- Production Docker frontend build: **passed**, image `cahy-wiki-frontend:merge-261023-eafde0b`, image ID `sha256:7f056669119a42042adb467f3c287c6c0a630b25a0dfbcecebcf4e96386b8ea3`. Uses the repository Dockerfile with frozen dependency lockfile; build stages reused identical cached inputs.
- Local Windows builds encounter the cross-drive dependency junction: Turbopack rejects dependency resolution outside the workspace; Webpack also cannot resolve that cross-drive Next path. The clean Docker build avoids this environment limitation without source changes.

This is source integration, not an assertion that the previously recorded live router timeout, model-to-export acceptance or source-recovery jobs have completed. Those limits remain in the acceptance reports. No production API, worker or frontend was restarted for this merge. Original dirty checkouts remain untouched.
