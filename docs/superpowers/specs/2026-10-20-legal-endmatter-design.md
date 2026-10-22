# Legal end matter boundaries

User requirement: separate terminal notes and appendices from legal articles. Once such a section begins, its internal Điều/Chương lines are content, not main-document article/chapter boundaries.

## Behavior

- Recognize explicit standalone end-section headings: Phụ lục (optional identifier/title), Ghi chú, Chú thích, with ordinary Markdown/HTML emphasis supported.
- Do not match prose references such as “Phụ lục III của Nghị định này”, table cells, block quotes, or code fences.
- Each appendix and terminal note block forms an opaque section. Another explicit end-section heading can begin the next section.
- A standalone notes heading between main articles must not end the main document: a subsequent next sequential main article keeps those notes in the main body. Ambiguous text without an explicit heading is retained as body text.
- Main content retains existing article-based chunk boundaries. End sections use token-sized windows and existing table row protection, preserving text and offsets. They do not inherit the last main chapter/article breadcrumb.
- A long appendix may require several chunks for the existing token budget; it is not forced into one oversized chunk. Page transitions do not break a short end section.
- Original source text and uploaded files remain unchanged.

## Alternatives

1. Disable all legal chunking after a label and append it to the last article: insufficient isolation and misleading citations.
2. One chunk for the entire tail: simple but exceeds embedding limits on large appendices.
3. Shared explicit end-section boundaries plus opaque token windows: selected; isolates sections and retains the existing size/table rules.

## Components

- `app/services/legal_endmatter.py`: detect offsets/titles/kinds without rewriting source text or importing the hierarchy parser.
- `app/services/verbatim_service.py`: stop article/chapter discovery at the tail and create independent spans/breadcrumbs for its sections.
- Tests: explicit/raw/styled markers, multiple appendices, notes with internal legal headings, long sections, page joins, offsets, false references, fences/quotes/tables, inline notes before a later main article.

The user confirmed both search chunks and separate Wiki pages. Hierarchy parsing must retain opaque `end_sections` without interpreting their internal legal labels. Each section gets a stable extracted Wiki identity, overview link, and opaque Wiki chunk indexing; hand-edited pages remain protected. Legal full-text responses and rendering retain these sections after the articles. Existing files are not bulk regenerated without verifying affected samples.
