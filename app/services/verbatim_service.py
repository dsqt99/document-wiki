"""Branch A: split a source's full text into verbatim chunks and embed them."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from loguru import logger

from app.services import chunk_budget as _cb
from app.services.source_outline import PAGE_JOIN_SEPARATOR

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


def _find_headings(text: str) -> list[tuple[int, int, str]]:
    """Return (position, level, title) for each heading line, in order."""
    out: list[tuple[int, int, str]] = []
    pos = 0
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped:
            m = _MD_HEADING.match(stripped)
            if m:
                title = m.group(2).strip()
                if title:
                    out.append((pos, len(m.group(1)), title))
            else:
                lm = _LEGAL_HEADING.match(stripped)
                if lm:
                    out.append((pos, _LEGAL_LEVELS[lm.group(1).lower()], stripped))
        pos += len(line) + 1
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


def build_source_chunks(full_text: str, page_offsets: Optional[list[int]] = None, doc_title: str = "") -> list[SourceChunk]:
    text = full_text or ""
    headings = _find_headings(text)
    raw_chunks: list[tuple[int, int, int, str]] = []  # (page, start, end, text)

    for page_no, p_start, p_end in _pages(text, page_offsets):
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
        if len(body.strip()) < MIN_CHUNK_CHARS:
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
    full_text = getattr(source, "full_text", None) or ""
    if not full_text.strip():
        return 0

    from sqlalchemy import delete

    from app.ai.embedding_catalog import get_spec
    from app.ai.registry import ProviderRegistry
    from app.database.models import get_source_chunk_embedding_model_for_dim
    from app.services import embedding_storage

    registry = ProviderRegistry(session)
    if spec_id is None:
        spec_id = await registry.get_active_embedding_spec_id()
    if not spec_id:
        logger.warning(
            f"index_source_chunks: no active embedding model; source {getattr(source, 'id', None)} "
            "will only be reachable through keyword search"
        )
        return 0
    spec = get_spec(spec_id)

    model = get_source_chunk_embedding_model_for_dim(spec.dimension)
    await session.execute(
        delete(model).where(model.source_id == source.id, model.model_spec_id == spec.id)
    )

    title = getattr(source, "title", "") or ""
    chunks = build_source_chunks(full_text, getattr(source, "page_offsets", None) or [], doc_title=title)
    if not chunks:
        await session.commit()
        return 0

    provider = await registry.get_embedding(task="document", spec_id=spec_id)
    for b in range(0, len(chunks), EMBED_BATCH_SIZE):
        batch = chunks[b : b + EMBED_BATCH_SIZE]
        vectors = await provider.embed_batch([_embed_input(title, c.heading_path, c.text) for c in batch])
        for chunk, vector in zip(batch, vectors):
            await embedding_storage.upsert_chunk_embedding(
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
    await session.commit()
    return len(chunks)


index_verbatim_source = index_source_chunks
