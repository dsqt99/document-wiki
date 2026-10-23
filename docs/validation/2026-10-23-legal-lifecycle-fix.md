# Legal lifecycle linking and provenance ACL — 2026-10-23

Task 3 implementation against feature source `51fd35e`, using the approved Wiki flow fix plan. No production database writes, ingestion/retries, deployment, or service restarts were performed.

## Behavior

- Ingestion adds a `document` LegalUnit root (the existing column is a String; no schema migration). Articles belong to that root. Relinking considers both outgoing relations and existing incoming relations targeting the ingested document.
- Exact document identifiers normalize whitespace, fullwidth slash and common Unicode hyphens. Whole-document changes resolve to a root. Legacy roots can be created without changing article/source/page text. Multiple matching source/article/clause/root targets remain unresolved and are counted as ambiguous. Missing clauses remain unresolved instead of being attributed to their entire article.
- Warnings inherit document/article ancestors and filter both the readable target and modifier provenance by allowed source IDs. MCP always supplies the caller's allow-list. No warning number/quote is read from an inaccessible modifier in the regression fixtures.
- `get_document_relations` keeps readable text and adds schema-version-1 structured data: `doc_number`, `article_number`, `checked_sources` (`source_id`, canonical `doc_number`), `source_ids`, `verification_status`, `relations`, `unresolved_count`, and `truncated`. Exact scoped identity is required. `not_found`/`ambiguous` return no checked sources. An unresolved or truncated graph reports `verification_status=unresolved`. `validity_known=false` always: local edges do not certify externally current law. No source version is invented.

## Verification

Python: `D:/code/dsqt/conganhungyen/chatbot_cahy/final_ban_giao/cahy_wiki/.venv/Scripts/python.exe`.

Initial disposable SQLite run: **7 failures** reproducing missing roots/linking/incoming resolution, unsafe duplicate choice, missing scoped warning parameters, and identifier normalization. After adding structured lookup/replacement/implicit-target regressions: **5 expected failures, 8 passed**. Both runs preceded their respective production fixes.

Focused legal/MCP suite: **70 passed** before replacing an invalid async `session.add` mock. The wider regression run identified one old test that explicitly required choosing the first duplicate target; it was updated to require unresolved ambiguity, unchanged target ID and no commit, as required by the approved design.

Final wider suite: **497 passed, 4 skipped, 2 warnings in 18.37s**, exit 0. This is the same 41 modules listed in `2026-10-23-wiki-flow-review.md`, plus `tests/test_legal_lifecycle_repair.py` (16 new tests). It is not the complete repository suite. Three PostgreSQL tests require an absent `ARKON_IT_DATABASE_URL`; one XLS test lacks `xlwt`. The two warnings are existing synchronous `session.add` calls mocked with AsyncMock in `test_dead_letter_and_timings.py`. The new lifecycle tests use an actual in-memory SQLite database and invoke the real ingest/link/warning functions and MCP tool functions.

`git diff --check` passed. Maintenance `--help` exited 0 without connecting to a database. Disposable fixtures verify dry-run leaves relation IDs/unit counts unchanged, apply creates only the missing root/link, a second apply is a no-op, and original content remains unchanged.

## Bounded repair command

Run from the Wiki project root, in the intended environment:

```text
python -m app.scripts.relink_legal_relations --limit 100
python -m app.scripts.relink_legal_relations --limit 100 --apply
python -m app.scripts.relink_legal_relations --limit 100 --after-id RETURNED_UUID
```

The default is dry-run. `--apply` changes one batch only; limit is restricted to 1–1000. Optional `--source-id UUID` selects outgoing and incoming relations for that source. Continue with `next_after_id` until a batch scans zero rows. Restart without a cursor to revisit earlier unresolved targets after new ingestion. Output includes scanned/linked/unresolved/ambiguous counts and planned/created roots. It repairs only unresolved edges, preserving already linked edges and source/page content. Production repair and PostgreSQL/concurrent-writer acceptance remain for the root task's controlled run; SQLite success is not presented as production acceptance.
