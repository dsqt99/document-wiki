"""
Verbatim source indexing.

A preserve_verbatim Source skips the LLM wiki pipeline (MRP). Instead its raw
full_text is split into page-aligned chunks and embedded as-is into the
source_chunk_embeddings_<dim> tables, so it is discoverable in the same semantic
search pool as wiki pages — but never rewritten.

Chunking is page-based: every chunk carries the exact 1-based page_number it came
from (clean "trang N" citations) and char offsets into full_text so a clean
preview can be sliced back out. Long pages are sub-split into overlapping windows.
"""

import re
from dataclasses import dataclass
from typing import Optional

from loguru import logger
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embedding_catalog import get_spec
from app.ai.registry import ProviderRegistry
from app.database.models import Source, get_source_chunk_embedding_model_for_dim
from app.services.embedding_storage import (
    chunk_content_hash,
    upsert_chunk_embedding,
)
from app.services.source_outline import PAGE_JOIN_SEPARATOR

# Retrieval-sized chunks (much smaller than the MAP chunker's 20k) for precision.
CHUNK_TARGET_CHARS = 2_000
CHUNK_OVERLAP_CHARS = 200
MIN_CHUNK_CHARS = 50

_HEADING_PATTERN = re.compile(
    r"^(#{1,6}\s+[^\n\r]+|(?:Chương|Điều|Phần|Mục)\s+[0-9IVXLCDM]+[^\n\r]*)",
    re.MULTILINE | re.IGNORECASE,
)


@dataclass
class SourceChunk:
    index: int
    page_number: int  # 1-based
    start_char: int   # absolute offset in full_text
    end_char: int
    text: str
    heading_path: str = ""


# Backward compatibility alias
VerbatimChunk = SourceChunk


def _find_headings(full_text: str) -> list[tuple[int, int, str]]:
    """Scan full_text for headings and return [(start_char, level, heading_text), ...]."""
    headings: list[tuple[int, int, str]] = []
    for m in _HEADING_PATTERN.finditer(full_text):
        raw_heading = m.group(0).strip()
        start = m.start()
        # Determine depth level
        if raw_heading.startswith("#"):
            hashes = len(raw_heading) - len(raw_heading.lstrip("#"))
            level = hashes
            title = raw_heading.lstrip("#").strip()
        elif raw_heading.lower().startswith("phần"):
            level = 1
            title = raw_heading
        elif raw_heading.lower().startswith("chương"):
            level = 2
            title = raw_heading
        elif raw_heading.lower().startswith("mục"):
            level = 3
            title = raw_heading
        elif raw_heading.lower().startswith("điều"):
            level = 4
            title = raw_heading
        else:
            level = 2
            title = raw_heading
        headings.append((start, level, title))
    return headings


def _resolve_heading_path(headings: list[tuple[int, int, str]], char_offset: int, end_offset: int = -1) -> str:
    """Build breadcrumb hierarchy (e.g. 'Chương I > Điều 3') active at char_offset or within [char_offset, end_offset)."""
    if not headings:
        return ""
    target = end_offset if end_offset > char_offset else char_offset
    # Collect all headings up to target
    stack: list[tuple[int, str]] = []  # (level, title)
    for start, level, title in headings:
        if start > target:
            break
        # Pop any deeper or equal level headings
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))
    return " > ".join(t for _, t in stack)


def _adjust_chunk_boundary(full_text: str, start: int, target_end: int, page_end: int) -> int:
    """Snap target_end to natural boundaries (newline, end of table row, sentence)

    to avoid breaking markdown tables or sentences in half.
    """
    if target_end >= page_end:
        return page_end

    slice_text = full_text[start:target_end]
    # Check if target_end falls inside a table row (starts with |)
    last_nl = full_text.rfind("\n", start, target_end)
    if last_nl != -1 and target_end - last_nl < 150:
        line_after_nl = full_text[last_nl:target_end]
        if line_after_nl.strip().startswith("|"):
            # Check if next newline closes the row
            next_nl = full_text.find("\n", target_end, min(target_end + 300, page_end))
            if next_nl != -1:
                return next_nl

    # Try snapping to paragraph or newline boundary in the last 200 chars
    search_start = max(start + MIN_CHUNK_CHARS, target_end - 200)
    best_nl = full_text.rfind("\n\n", search_start, target_end)
    if best_nl != -1:
        return best_nl + 2

    best_single_nl = full_text.rfind("\n", search_start, target_end)
    if best_single_nl != -1:
        return best_single_nl + 1

    return target_end


def _page_bounds(full_text: str, page_offsets: list[int]) -> list[tuple[int, int, int]]:
    """Return [(page_number, start_char, end_char), ...] for each page (1-based)."""
    if not page_offsets:
        return [(1, 0, len(full_text))] if full_text else []
    total = len(page_offsets)
    out: list[tuple[int, int, int]] = []
    for idx in range(total):
        start = page_offsets[idx]
        if idx + 1 < total:
            end = page_offsets[idx + 1] - len(PAGE_JOIN_SEPARATOR)
        else:
            end = len(full_text)
        out.append((idx + 1, start, max(start, end)))
    return out


_TABLE_SEPARATOR = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")


def _find_large_tables(full_text: str, start: int, end: int) -> list[tuple[int, int, list[tuple[int, int]]]]:
    """Markdown tables in [start, end) too long for one chunk.

    Returns [(table_start, rows_start, [(row_start, row_end), ...]), ...] where
    full_text[table_start:rows_start] is the header + separator lines.
    """
    lines: list[tuple[int, int]] = []  # (line_start, line_end without newline)
    pos = start
    while pos < end:
        nl = full_text.find("\n", pos, end)
        line_end = end if nl == -1 else nl
        lines.append((pos, line_end))
        pos = line_end + 1

    tables = []
    i = 0
    while i < len(lines):
        j = i
        while j < len(lines) and full_text[lines[j][0]:lines[j][1]].strip().startswith("|"):
            j += 1
        run = lines[i:j]
        if (
            len(run) >= 3
            and _TABLE_SEPARATOR.match(full_text[run[1][0]:run[1][1]].strip())
            and run[-1][1] - run[0][0] > CHUNK_TARGET_CHARS
        ):
            tables.append((run[0][0], run[2][0], run[2:]))
        i = max(j, i + 1)
    return tables


def _table_row_chunks(full_text: str, table_start: int, rows_start: int, rows: list[tuple[int, int]]):
    """Group table rows into chunks, repeating the header so every chunk keeps
    its column names (row-wise chunks for spreadsheets / long tables)."""
    header = full_text[table_start:rows_start]
    group_start = group_end = None
    for row_start, row_end in rows:
        if group_start is not None and len(header) + (row_end - group_start) > CHUNK_TARGET_CHARS:
            yield group_start, group_end, header + full_text[group_start:group_end]
            group_start = None
        if group_start is None:
            group_start = row_start
        group_end = row_end
    if group_start is not None:
        yield group_start, group_end, header + full_text[group_start:group_end]


def build_source_chunks(
    full_text: str,
    page_offsets: list[int],
    doc_title: str = "",
) -> list[SourceChunk]:
    """Split full_text into page-aligned, retrieval-sized chunks with heading hierarchy.

    Each chunk belongs to exactly one page. Pages longer than CHUNK_TARGET_CHARS
    are sub-split into overlapping windows with boundary snapping (preventing
    breaks inside markdown tables). `text` is the clean verbatim slice of full_text,
    and heading_path captures the structural breadcrumb.

    Markdown tables longer than one chunk (Excel sheets, CSV, long DOCX/PDF
    tables) are split on row boundaries instead, and each chunk's `text` is the
    table header followed by its rows; start/end_char cover only those rows.
    """
    headings = _find_headings(full_text)
    chunks: list[SourceChunk] = []

    def _add(page_number: int, start: int, end: int, text: str) -> None:
        if len(text.strip()) >= MIN_CHUNK_CHARS:
            chunks.append(SourceChunk(
                index=len(chunks),
                page_number=page_number,
                start_char=start,
                end_char=end,
                text=text,
                heading_path=_resolve_heading_path(headings, start, end),
            ))

    def _add_windows(page_number: int, seg_start: int, seg_end: int) -> None:
        pos = seg_start
        while pos < seg_end:
            raw_end = min(pos + CHUNK_TARGET_CHARS, seg_end)
            end = _adjust_chunk_boundary(full_text, pos, raw_end, seg_end)
            _add(page_number, pos, end, full_text[pos:end])
            if end >= seg_end:
                break
            pos = end - CHUNK_OVERLAP_CHARS  # overlap window
            if pos <= seg_start and end < seg_end:
                pos = end  # degenerate guard (tiny target vs overlap)

    for page_number, p_start, p_end in _page_bounds(full_text, page_offsets):
        cursor = p_start
        for table_start, rows_start, rows in _find_large_tables(full_text, p_start, p_end):
            if cursor < table_start:
                _add_windows(page_number, cursor, table_start)
            for start, end, text in _table_row_chunks(full_text, table_start, rows_start, rows):
                _add(page_number, start, end, text)
            cursor = rows[-1][1]
        if cursor < p_end:
            _add_windows(page_number, cursor, p_end)
    return chunks


# Backward compatibility alias
build_verbatim_chunks = build_source_chunks


async def index_source_chunks(
    session: AsyncSession,
    source: Source,
    spec_id: Optional[str] = None,
) -> int:
    """Chunk + embed a source's full_text into source_chunk_embeddings_<dim>.

    Works for any source (verbatim or general). Returns the number of chunks indexed.
    Computes embeddings with contextualized prefix (title + heading hierarchy)
    while storing the exact verbatim text for fidelity.
    """
    full_text = source.full_text or ""
    if not full_text.strip():
        logger.warning(f"index_source_chunks: source {source.id} has no full_text")
        return 0

    registry = ProviderRegistry(session)
    if spec_id is None:
        spec_id = await registry.get_active_embedding_spec_id()
    if not spec_id:
        logger.warning(
            f"index_source_chunks: no active embedding model configured — "
            f"source {source.id} stored but not semantically indexed "
            f"(keyword search still works; run re-embed after configuring a model)"
        )
        return 0

    spec = get_spec(spec_id)
    provider = await registry.get_embedding(task="document", spec_id=spec_id)

    doc_title = source.title or source.file_name or ""
    chunks = build_source_chunks(full_text, source.page_offsets or [], doc_title=doc_title)
    if not chunks:
        return 0

    # Clear prior rows for THIS source in THIS spec only
    Model = get_source_chunk_embedding_model_for_dim(spec.dimension)
    await session.execute(
        delete(Model).where(
            Model.source_id == source.id, Model.model_spec_id == spec.id
        )
    )

    # Build contextual embedding texts: prepend title and heading hierarchy for retrieval precision
    texts_to_embed = []
    for c in chunks:
        prefix_parts = []
        if doc_title:
            prefix_parts.append(doc_title)
        if c.heading_path:
            prefix_parts.append(c.heading_path)
        if prefix_parts:
            header = " — ".join(prefix_parts)
            texts_to_embed.append(f"[{header}]\n\n{c.text}")
        else:
            texts_to_embed.append(c.text)

    # Embed in batches to prevent API payload limits
    BATCH_SIZE = 16
    vectors = []
    for b_idx in range(0, len(texts_to_embed), BATCH_SIZE):
        batch = texts_to_embed[b_idx : b_idx + BATCH_SIZE]
        batch_vecs = await provider.embed_batch(batch)
        vectors.extend(batch_vecs)

    for chunk, vector in zip(chunks, vectors):
        await upsert_chunk_embedding(
            session,
            source_id=source.id,
            chunk_index=chunk.index,
            spec=spec,
            vector=vector,
            text=chunk.text,
            start_char=chunk.start_char,
            end_char=chunk.end_char,
            page_number=chunk.page_number,
            content_hash=chunk_content_hash(chunk.text),
        )
    await session.commit()
    logger.info(f"index_source_chunks: indexed {len(chunks)} chunks for source {source.id}")
    return len(chunks)


# Backward compatibility alias
index_verbatim_source = index_source_chunks

