"""Branch A: split a source's full text into verbatim chunks and embed them."""

from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass
from typing import Any, Optional

from loguru import logger

from app.core.legal_headings import is_bare_article_continuation, is_legal_structure_candidate, legal_heading_level
from app.services import chunk_budget as _cb
from app.services.source_outline import PAGE_JOIN_SEPARATOR
from app.services.legal_endmatter import find_end_sections

MIN_CHUNK_CHARS = 50
EMBED_BATCH_SIZE = 16


@dataclass
class SourceChunk:
    index: int
    page_number: int
    start_char: int
    end_char: int
    text: str
    heading_path: str = ""


VerbatimChunk = SourceChunk

_MD_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
_LEGAL_HEADING = re.compile(
    r"^(phần|chương|mục|điều)\s+(\d+|[ivxlcdm]+)\b",
    re.IGNORECASE,
)
_LEGAL_LEVELS = {"phần": 1, "chương": 2, "mục": 3, "điều": 4}
_SEPARATOR_ROW = re.compile(r"^[\s|:\-]*$")


# ---------------------------------------------------------------------------
# Headings
# ---------------------------------------------------------------------------


def _heading_display_text(line: str, *, legal_article: bool = False) -> str:
    from app.services.legal_hierarchy_parser import strip_markup

    if legal_article:
        # Legal article footnotes do not belong to the heading identifier.
        line = re.sub(r"<sup\b[^>]*>.*?</sup>", "", line, flags=re.I | re.S)
    else:
        # Generic technical headings can use superscripts as visible units.
        # Remove their tags first so strip_markup retains the exponent text.
        line = re.sub(r"</?sup\b[^>]*>", "", line, flags=re.I)
    return strip_markup(line)


def _find_headings(text: str, *, isolate_end_sections: bool = False) -> list[tuple[int, int, str]]:
    """Return structural headings without promoting wrapped legal citations."""
    out: list[tuple[int, int, str]] = []
    end_sections = find_end_sections(text) if isolate_end_sections else []
    body_end = end_sections[0].start if end_sections else len(text)
    # The same quote/context rules must own article splits and article paths.
    article_positions = {position for position, _title in _article_boundaries(text, isolate_end_sections=isolate_end_sections)}
    pos = 0
    for line in text.split("\n"):
        if pos >= body_end:
            break
        stripped = line.strip()
        if stripped:
            markdown = _MD_HEADING.match(stripped)
            title = _heading_display_text(markdown.group(2) if markdown else stripped)
            level = legal_heading_level(stripped)
            candidate = is_legal_structure_candidate(stripped)
            article = re.match(r'^Điều\s+\d+[a-z]?(?!\w)', title.lstrip('“”" \t'), re.I)
            if article:
                if pos in article_positions:
                    title = _heading_display_text(markdown.group(2) if markdown else stripped, legal_article=True)
                    out.append((pos, 4, title))
            elif candidate:
                if level:
                    out.append((pos, level, title))
            elif markdown and title:
                out.append((pos, len(markdown.group(1)), title))
        pos += len(line) + 1
    out.extend((section.start, 1, section.title) for section in end_sections)
    return out


def _heading_path(headings: list[tuple[int, int, str]], start: int, end: int) -> str:
    limit = end if end > start else start
    stack: list[tuple[int, str]] = []
    for hpos, level, title in headings:
        if hpos >= limit:
            break
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))
    return " > ".join(t for _, t in stack)


# ---------------------------------------------------------------------------
# Pages and tables
# ---------------------------------------------------------------------------


def _pages(full_text: str, page_offsets: Optional[list[int]]) -> list[tuple[int, int, int]]:
    """(page_number, start, end) spans following the page offsets."""
    n = len(full_text)
    if not full_text:
        return []
    offsets = [int(o) for o in (page_offsets or [])]
    if not offsets:
        return [(1, 0, n)]
    spans: list[tuple[int, int, int]] = []
    for i, start in enumerate(offsets):
        if i + 1 < len(offsets):
            end = offsets[i + 1] - len(PAGE_JOIN_SEPARATOR)
        else:
            end = n
        start = max(0, min(start, n))
        end = max(start, min(end, n))
        spans.append((i + 1, start, end))
    return spans


def _lines(text: str, start: int, end: int) -> list[tuple[int, int]]:
    """(line_start, line_end_without_newline) for each line in text[start:end]."""
    out: list[tuple[int, int]] = []
    pos = start
    while pos < end:
        nl = text.find("\n", pos, end)
        if nl == -1:
            out.append((pos, end))
            break
        out.append((pos, nl))
        pos = nl + 1
    return out


def _find_large_tables(text: str, start: int, end: int) -> list[list[tuple[int, int]]]:
    """Return a list of large tables, each being its list of line spans."""
    target = _cb.CHUNK_TARGET_TOKENS
    lines = _lines(text, start, end)
    tables = []
    i = 0
    while i < len(lines):
        if not text[lines[i][0] : lines[i][1]].startswith("|"):
            i += 1
            continue
        j = i
        while j < len(lines) and text[lines[j][0] : lines[j][1]].startswith("|"):
            j += 1
        run = lines[i:j]
        if len(run) >= 3:
            sep = text[run[1][0] : run[1][1]]
            if _SEPARATOR_ROW.match(sep) and "-" in sep:
                tstart, tend = run[0][0], run[-1][1]
                if _cb.estimate_tokens(text[tstart:tend]) > target:
                    tables.append(run)
        i = j
    return tables


def _split_table(text: str, run: list[tuple[int, int]]) -> list[tuple[int, int, str]]:
    """Row-wise groups of a large table: (start, end, chunk_text)."""
    target = _cb.CHUNK_TARGET_TOKENS
    header_end = run[1][1] + 1 if run[1][1] < len(text) else run[1][1]
    header = text[run[0][0] : header_end]
    if not header.endswith("\n"):
        header += "\n"
    header_tokens = _cb.estimate_tokens(header)
    rows = run[2:]
    groups: list[tuple[int, int, str]] = []
    g_start: Optional[int] = None
    g_end = 0
    g_tokens = 0
    for idx, (ls, le) in enumerate(rows):
        is_last = idx == len(rows) - 1
        # Each row owns its trailing newline except the table's final row.
        row_end = le if is_last or le >= len(text) else le + 1
        row_tokens = _cb.estimate_tokens(text[ls:le])
        if g_start is not None and header_tokens + g_tokens + row_tokens + 1 > target:
            groups.append((g_start, g_end, header + text[g_start:g_end]))
            g_start, g_tokens = None, 0
        if g_start is None:
            g_start = ls
        g_end = row_end
        g_tokens += row_tokens
    if g_start is not None:
        groups.append((g_start, g_end, header + text[g_start:g_end]))
    return groups


# ---------------------------------------------------------------------------
# Sliding window
# ---------------------------------------------------------------------------


def _adjust_cut(text: str, pos: int, raw: int, seg_end: int) -> int:
    if raw >= seg_end:
        return seg_end
    nl = text.rfind("\n", pos, raw)
    if nl != -1 and raw - nl <= 150 and text.startswith("|", nl + 1):
        nxt = text.find("\n", raw, min(seg_end, raw + 300))
        if nxt != -1:
            return min(seg_end, nxt + 1)
    lo = max(raw - 200, pos + 50)
    if lo < raw:
        para = text.rfind("\n\n", lo, raw)
        if para != -1:
            return para + 2
        single = text.rfind("\n", lo, raw)
        if single != -1:
            return single + 1
    return raw


def _window(text: str, seg_start: int, seg_end: int) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    pos = seg_start
    while pos < seg_end:
        raw = _cb.end_for_tokens(text, pos, seg_end)
        end = _adjust_cut(text, pos, raw, seg_end)
        if end <= pos:
            end = max(raw, pos + 1)
        spans.append((pos, end))
        if end >= seg_end:
            break
        nxt = end - _cb.overlap_chars(end - pos)
        if nxt <= seg_start or nxt <= pos:
            nxt = end
        pos = nxt
    return spans


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _article_boundaries(text, *, isolate_end_sections=True):
    from app.services.legal_hierarchy_parser import _match_article, _article_seq
    end_sections = find_end_sections(text) if isolate_end_sections else []
    body_end = end_sections[0].start if end_sections else len(text)
    lines = text[:body_end].splitlines(keepends=True)
    matches = []
    previous_nonempty = ""
    for line in lines:
        plain = _heading_display_text(line, legal_article=True)
        bare_reference = is_bare_article_continuation(line, previous_nonempty)
        matches.append(None if bare_reference else _match_article(plain))
        if plain:
            previous_nonempty = f"### {plain}" if legal_heading_level(plain) and not bare_reference else plain
    seqs = [_article_seq(match.group(1)) if match and not any(q in line for q in ('"','“','”')) else None for line, match in zip(lines,matches)]
    boundaries, position, quoted, last_seq = [], 0, False, None
    for index, line in enumerate(lines):
        seq = seqs[index]
        # Same recovery as the legal parser for a closing quote lost by OCR.
        if quoted and seq is not None and seq == (last_seq or 0) + 1 and seq not in seqs[index + 1:]:
            quoted = False
        if sum(line.count(mark) for mark in ('"','“','”')) % 2:
            quoted = not quoted
        if matches[index] and not quoted:
            boundaries.append((position, _heading_display_text(line, legal_article=True)))
            last_seq = _article_seq(matches[index].group(1))
        position += len(line)
    return boundaries


def build_source_chunks(full_text: str, page_offsets: Optional[list[int]] = None, doc_title: str = "", *, is_legal=False) -> list[SourceChunk]:
    text = full_text or ""
    headings = _find_headings(text, isolate_end_sections=is_legal)
    raw_chunks: list[tuple[int, int, int, str]] = []  # (page, start, end, text)
    spans = _pages(text, page_offsets)
    if is_legal:
        article_heads = _article_boundaries(text)
        end_sections = find_end_sections(text)
        if article_heads or end_sections:
            headings = sorted({*headings, *((pos,4,title) for pos,title in article_heads)})
            starts = sorted({0, *(pos for pos,_title in article_heads), *(section.start for section in end_sections)})
            offsets = sorted(page_offsets or [0])
            spans = [(max(1,bisect_right(offsets,start)),start,starts[i+1] if i+1 < len(starts) else len(text)) for i,start in enumerate(starts)]

    for page_no, p_start, p_end in spans:
        cursor = p_start
        for run in _find_large_tables(text, p_start, p_end):
            t_start = run[0][0]
            for s, e in _window(text, cursor, t_start):
                raw_chunks.append((page_no, s, e, text[s:e]))
            for s, e, body in _split_table(text, run):
                raw_chunks.append((page_no, s, e, body))
            cursor = run[-1][1]
        for s, e in _window(text, cursor, p_end):
            raw_chunks.append((page_no, s, e, text[s:e]))

    chunks: list[SourceChunk] = []
    for page_no, s, e, body in raw_chunks:
        if not body.strip() or not is_legal and len(body.strip()) < MIN_CHUNK_CHARS:
            continue
        chunks.append(
            SourceChunk(
                index=len(chunks),
                page_number=page_no,
                start_char=s,
                end_char=e,
                text=body,
                heading_path=_heading_path(headings, s, e),
            )
        )
    return chunks


build_verbatim_chunks = build_source_chunks


def _embed_input(title: str, heading_path: str, body: str) -> str:
    title = (title or "").strip()
    heading_path = (heading_path or "").strip()
    if title and heading_path:
        return f"[{title} — {heading_path}]\n\n{body}"
    if title or heading_path:
        return f"[{title or heading_path}]\n\n{body}"
    return body


async def index_source_chunks(session: Any, source: Any, spec_id: Optional[str] = None) -> int:
    from app.services.source_quality import save_quality

    full_text = getattr(source, "full_text", None) or ""
    if not full_text.strip():
        await save_quality(session, source, "source_index", {"status": "error", "expected": 0, "indexed": 0})
        await session.commit()
        return 0

    from sqlalchemy import delete

    from app.ai.embedding_catalog import get_spec
    from app.ai.registry import ProviderRegistry
    from app.database.models import get_source_chunk_embedding_model_for_dim
    from app.services import embedding_storage

    registry = ProviderRegistry(session)
    title = getattr(source, "title", "") or ""
    from app.services.legal_service import is_legal_source
    legal = await is_legal_source(session, source)
    chunks = build_source_chunks(full_text, getattr(source, "page_offsets", None) or [], doc_title=title, is_legal=legal)
    expected = len(chunks)
    if not await save_quality(session, source, "source_index", {"status": "processing", "expected": expected, "indexed": 0}):
        await session.rollback()
        return 0
    await session.commit()
    if spec_id is None:
        spec_id = await registry.get_active_embedding_spec_id()
    if not spec_id:
        logger.warning(
            f"index_source_chunks: no active embedding model; source {getattr(source, 'id', None)} "
            "will only be reachable through keyword search"
        )
        await save_quality(session, source, "source_index", {
            "status": "partial", "expected": expected, "indexed": 0,
            "warnings": [{"code": "embedding_unavailable", "message": "No embedding model configured; keyword search only."}],
        })
        await session.commit()
        return 0
    spec = get_spec(spec_id)

    model = get_source_chunk_embedding_model_for_dim(spec.dimension)
    await session.execute(
        delete(model).where(model.source_id == source.id, model.model_spec_id == spec.id)
    )

    if not chunks:
        await save_quality(session, source, "source_index", {"status": "partial", "expected": 0, "indexed": 0,
            "warnings": [{"code": "no_source_chunks", "message": "Extracted text produced no indexable chunks."}]})
        await session.commit()
        return 0

    provider = await registry.get_embedding(task="document", spec_id=spec_id)
    indexed = 0
    for b in range(0, len(chunks), EMBED_BATCH_SIZE):
        batch = chunks[b : b + EMBED_BATCH_SIZE]
        vectors = await provider.embed_batch([_embed_input(title, c.heading_path, c.text) for c in batch])
        for chunk, vector in zip(batch, vectors):
            success = await embedding_storage.upsert_chunk_embedding(
                session,
                source.id,
                chunk.index,
                spec,
                vector,
                text=chunk.text,
                start_char=chunk.start_char,
                end_char=chunk.end_char,
                page_number=chunk.page_number,
                content_hash=embedding_storage.chunk_content_hash(chunk.text),
            )
            if success is True:
                indexed += 1
        # Keep confirmed, durable progress visible if a later batch fails.
        if not await save_quality(session, source, "source_index", {"status": "processing", "expected": expected, "indexed": indexed}):
            await session.rollback()
            return indexed
        await session.commit()
    await save_quality(session, source, "source_index", {
        "status": "complete" if indexed == expected else "partial" if indexed else "error",
        "expected": expected, "indexed": indexed,
        "warnings": [] if indexed == expected else [{"code": "source_index_incomplete", "message": f"Only {indexed}/{expected} source chunks reached the vector index."}],
    })
    await session.commit()
    return indexed


index_verbatim_source = index_source_chunks
