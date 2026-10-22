# Wiki origin tags and merge boundaries

**Goal:** Show single-word tags Extracted / Generated and permit automated updates only within the same origin and exact source visibility scope.

- Persist nullable `origin_tag` with a database check and migration. Backfill known article/verbatim pages as extracted and MRP planned pages as generated, prioritizing extraction evidence. Leave system/manual/uncertain pages unclassified; do not guess by title alone.
- Populate tags in legal, verbatim and MRP writers. Preserve origin on human edits. Validate origin in machine updates; extracted pages also keep their source identity.
- Reconcile MRP concepts only against generated pages in source-derived scopes. Recheck at commit. Resolve conflicting slugs using deterministic tag/source suffixes, and remap sibling links in that scope; never replace a different tag or unrelated extracted source.
- Expose the tag in Wiki API, library column/filter and page badge. No user control to relabel extracted content as generated.
- Test mismatch refusal, same-tag updates, source identity, scoped semantic candidates and deterministic collision handling before implementation. Apply migration only after checking queue state, then verify classification totals, frontend build and UI. Do not rerun source compilation on the whole library.

Verified: 138 focused backend tests pass; TypeScript, changed-component ESLint and frontend Docker build pass. Migration 052 is applied: 1,579 extracted pages, 131 generated pages, 12 unclassified (11 reserved/system pages and one library page). Real database checks exercised cross-tag refusal, exact department scope updates and collision suffixes inside a transaction rolled back in full. Browser verified both tags, Generated filter (131 results), and the visible Tag column. API/frontend/worker are updated; the pre-existing 1,711-page LLM summary job was handed over at its 290-page checkpoint and visibly continued beyond 309 pages with its counters preserved.

Origin describes the page body, not how its summary was produced. Human edits and AI summary regeneration preserve origin. New personal-source pages retain their personal owner scope; legacy pages whose scope conflicts with a private source remain unclassified and excluded from automated merging.
