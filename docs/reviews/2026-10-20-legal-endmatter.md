# Legal end matter — implementation and verification

User-confirmed scope: both search chunks and separate Wiki pages for terminal notes/appendices. Their internal Điều/Chương labels remain content.

## Resulting behavior

- The main body retains article-aligned chunk boundaries.
- Each explicit appendix/notes heading opens a separate opaque section. Long sections are split by the existing token budget, with table row protection in source chunks. Internal article/chapter labels do not become additional main-law pages or search breadcrumbs.
- Extracted tail pages use distinct, collision-safe slugs, overview links and source identity. Their Wiki search chunks preserve internal headings and short sections.
- The legal fulltext API and reader include tail sections after the articles, with edit links and correction badges. Old generated final-article pages cannot reintroduce an already-separated source tail into the reader. Edited content and opening blockquotes remain preserved.
- Detection works on raw source text before indentation-erasing normalization. It retains raw offsets and excludes tables, blockquotes, code fences, indented code, inline references, and opening appendix inventories. Notes before the next sequential main article remain in the main body. Existing OCR quote-recovery rules are mirrored.

## Verification

Regression cases cover both raw and styled headings, CRLF/NFD source offsets, multiple appendices, appendix-only documents, long windows, cross-page continuation, code/table/reference exclusions, mid-article notes, missing closing OCR quotes, slug collisions, short Wiki notes, manual corrections, and fulltext API preservation.

A read-only corpus audit inspected 50 stored extracted texts. Twelve contained recognized terminal labels (including a general Word guide; actual legal chunk behavior is selected only for legal sources). The audit caught an OCR-created appendix inventory at the start of Nghị định 136; an explicit regression now keeps its later main articles in the main body.

Live sample: source `b95c9a51-b22d-47ec-8226-8682cca4c70d`, Thông tư 154/2025/TT-BTC. The raw extraction and existing Wiki page contents were saved before regeneration. It now has separate `phu-luc-1-154-2025-tt-btc` and `chu-thich-1-154-2025-tt-btc` extracted pages and five source chunks. Each tail page has one opaque Wiki chunk. The raw extraction was not changed. Existing unrelated and edited Wiki pages are retained.

The legacy final article's tail was moved only after verifying that its complete previous body equals the new article plus all persisted original tail bodies (Unicode normalization/whitespace folding only). The move preserves revisions and refuses edited pages, scope/source mismatches, missing tail material or other changes. The sample's final article is now version 3 and excludes the moved tail.

Final checks: **272 backend tests passed**, full TypeScript and scoped ESLint passed, frontend heading checks passed, and API/worker processes reloaded with healthy API HTTP 200. Existing SQLAlchemy deprecation/AsyncMock fixture warnings remain. Direct database checks confirm both tail pages are extracted pages with opaque chunk paths. Visual browser verification could not complete because the browser-control connection repeatedly timed out; no screenshot is claimed.

Evidence is stored under `C:/Users/DEV/.codex/visualizations/2026/10/20/extraction-review/` in `endmatter-audit-final.json`, `endmatter-sample-before.json`, `endmatter-sample-result.json`, and `endmatter-sample-final.json`. Existing files beyond the live sample were inspected without bulk rewriting their Wiki pages; future re-extraction uses the new section rules.
