# Document extraction review — 2026-10-20

Scope: the 50 stored sources with extracted text in the local Wiki instance, parser code, and the reported source `b1372cdc-5cc5-423b-8a1b-1c965ba58889`.

## Findings and fixes

1. **Wrapped references became headings.** The PDF formatter classified any line starting with Điều/Chương as a heading. Inline references such as “Điều 85 của Luật…” entered the table of contents; a false chapter boundary could also discard the remainder of the current article. Shared conservative classification now distinguishes references, including uppercase document references and bare article numbers continuing citation lists. Genuine amended chapter/article suffixes remain valid. The readable UI also normalizes legacy heading markup without changing stored source words.
2. **Superscript footnotes changed article identifiers.** Native PDF glyphs merged Điều 46 + footnote 33 into Điều 4633, and similarly 48 + 35. The rich PDF parser preserves elevated, smaller numeric glyphs on article headings as superscripts. Hierarchy/outline/TOC labels exclude footnotes, while the displayed source retains them. This uses actual glyph geometry; ambiguous plain OCR text is not split by guessing.
3. **Tables could remove adjacent text.** The old full-width vertical bands omitted native text beside narrow tables. Text is now filtered against actual cells of successfully rendered tables and merged with tables in reading order. Failed or empty table conversion retains native text. Irregular table bounding boxes no longer remove paragraphs in their unoccupied corners.
   A separate boxed-prose issue suppressed Articles 44, 44a, 45, 49 and 50. A single-column region now stays native prose only when its first nonempty row is a titled article and a later row contains a substantial numbered clause. Single-column reference lists and real multi-column tables remain tables.
4. **Sparse image pages could skip OCR.** Pages with 15–49 native characters fell between the low-text and image-coverage checks. The image-coverage check now covers that interval, while short native pages without images remain native.
5. **Word lost list labels and nested content.** DOCX extraction now reads OOXML numbering definitions, inheritance, starts/overrides and multilevel labels. Empty numbered paragraphs advance numbering; image-only paragraphs retain labels and image placeholders. Nested tables and cell images survive; merged-cell aliases are emitted once without collapsing distinct cells with equal text. Heading levels and explicit page breaks are handled.
6. **Consolidated-document metadata invented the publisher.** All VBHN files previously defaulted to Văn phòng Quốc hội. Formal source codes/certification now determine the publisher; unknown publishers stay unknown. The sample identifies `22/VBHN-BXD`, Bộ Xây dựng. Blank consolidation dates stay unknown instead of using the underlying decree date. Markdown table syntax and amendment recitals no longer pollute the title; legitimate wrapped amendment titles remain intact.
7. **Search chunks repeated false headings.** Chunk paths and article boundaries now use the same reference/quote classification. Citation lists do not create extra articles. Source text and offsets remain intact; generic technical headings retain their exponent digits.

## Evidence and limits

- Inventory: **30 PDFs + 20 DOCX files** with stored full text. The initial narrow false-reference scan identified examples in six files; this is not an exhaustive count of all extraction defects.
- PDF inventory: **1,483 pages**; **968 pages** met the scan/low-text heuristic. That is a routing estimate, not 968 verified OCR errors; blank pages can qualify.
- The reported PDF has **65 pages and a native text layer**. Its highlighted “Điều 85…” is an inline reference, not an article heading. The rendered original was compared directly.
- All **20 actual DOCX files** completed a dry extraction. Eighteen retained all unique old words. The two image-bearing files need pipeline image resolution before a meaningful complete-content comparison; old image UUIDs and fresh relationship placeholders differ.
- A real legacy `.doc` round trip through the container's LibreOffice retained the tested Vietnamese heading/body/table text. This is a compatibility smoke test, not a complete legacy Word corpus audit.
- The initial streaming OCR probe timed out and returned no usable output. After switching dedicated OCR to `stream=False`, the same page returned **3,026 characters in 35.2 seconds** with a 45-second client timeout and retries disabled. The output includes Điều 4a and the Điều 85 reference, but still contains recognition errors (e.g. “Thị hành” for “Thi hành” and a corrupted “hướng dẫn thi hành” phrase). **The transport fix does not establish text accuracy across scan files.** Parser/unit tests cannot establish the upstream model's accuracy.
- DOCX text boxes, header/footer semantics, unusual list formats, complex layouts, quoted legal headings, and OCR-only superscript ambiguity still need sample-based checks. No claim of perfect extraction across every file.

## Data handling

Dry runs did not overwrite Word files, regenerate Wiki pages, or enqueue a bulk reprocessing run. Original files remain unchanged. Hand-edited Wiki pages must be preserved when any subsequent reprocessing is performed. The reported source's legacy Wiki pages still reflect the previous split; corrected extraction and regenerated Wiki are separate stages.

The reported source alone was repaired after a guarded snapshot: full text, page offsets, outline, token count, and automatic document metadata/title. The complete source-character sequence matched the old extraction after removing presentation syntax (heading markers, table wrappers, emphasis, superscript tags, whitespace). Its legal hierarchy contains **63 articles: 1–59 plus 4a, 44a, 44b, 56a**. The readable TOC contains 76 entries, including chapters/sections and a quoted heading; the TOC count is not the article count. Quoted headings in the readable TOC remain a known limitation.

The source search index was regenerated successfully: **69 stored chunks**, with text and offsets exactly matching fresh chunk generation. The Wiki branch's old error and its 69 existing Wiki pages were retained; this review did not silently mark that branch complete or overwrite edited Wiki content.

## Final verification

- **241 backend tests passed**, with four pre-existing SQLAlchemy array deprecation warnings.
- Both frontend heading/anchor checks passed; full TypeScript checking and scoped ESLint passed.
- The final 65-page parse retained the same article set and source characters after the reference-table guard was tightened.
- API and main worker restarted; API health and the frontend development server returned HTTP 200.
- Original snapshot: `source-before-repair.json`; applied repair result: `sample-verification.json`; final dry verification: `final-dry-verification.json`; visual proof: `extracted-fixed.png` in the evidence directory below.
- OCR follow-up: switched the request and response parsing to non-streaming, retaining `finish_reason == "length"` rejection. **112 related OCR/PDF tests passed**; API and both workers restarted and API health returned HTTP 200. Real probe evidence: `ocr-nonstream-result.json` and `ocr-nonstream.md`. The probe output was not substituted for the accurate native-text extraction.

Evidence files are stored locally in `C:/Users/DEV/.codex/visualizations/2026/10/20/extraction-review/`.
