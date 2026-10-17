"""MAP phase: split the source into chunks and extract knowledge per chunk (05a §5.2)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.utils.text import parse_json_loose, strip_code_fence

CHUNK_TARGET_CHARS = 20_000
OVERLAP_CHARS = 1_000
MAX_PARALLEL_CALLS = 6
LLM_TIMEOUT_S = 300
SINGLE_PASS_MAX = 30_000
STANDARD_MAX = 200_000
TAIL_MIN_CHARS = 100
ERROR_MAX_LEN = 500
OVERLAP_MARKER = "[--- ngữ cảnh từ phần trước ---]"

EXTRACTION_SYSTEM_PROMPT = (
    "You extract structured knowledge from one passage of a document for an internal wiki. "
    "Return JSON only."
)

EXTRACTION_PROMPT_TEMPLATE = """Read the passage below (part of the document "{source_title}", section: {section_path}).
Return one JSON object with these keys:
- "entities": always an empty list.
- "concepts": list of {{"term", "definition_excerpt", "local_offset"}} for the terms the passage defines or explains.
- "claims": list of {{"statement", "subject", "local_offset", "evidence_length", "confidence"}} where confidence is high, medium or low.
- "relations": list of {{"from", "to", "predicate", "evidence"}} between concepts. "predicate" must be one of:
  la_mot (is a kind of), thuoc (belongs to / is part of), quy_dinh (regulates / governs),
  ap_dung_cho (applies to), lien_quan (generally related). "evidence" is a short quote from the passage.
- "topics": list of short topic names.
local_offset is the character position inside the passage where the item is stated.
Write values in the language of the passage. Output JSON only.

=== PASSAGE ===
{chunk_text}
"""


@dataclass
class DocumentChunk:
    index: int
    start_char: int
    end_char: int
    section_path: Optional[str]
    text: str
    overlap_prefix_len: int = 0


def classify_strategy(full_text: str) -> str:
    n = len(full_text or "")
    if n < SINGLE_PASS_MAX:
        return "single_pass"
    if n <= STANDARD_MAX:
        return "standard"
    return "hierarchical"


def _outline_nodes(nodes: Any, level: int = 1, path: tuple = ()) -> list[tuple[int, int, str]]:
    out: list[tuple[int, int, str]] = []
    if not isinstance(nodes, list):
        return out
    for n in nodes:
        if not isinstance(n, dict):
            continue
        lvl = n.get("level") if isinstance(n.get("level"), int) else level
        title = str(n.get("title") or "")
        p = path + (title,)
        s, e = n.get("char_start"), n.get("char_end")
        kids = n.get("children") or []
        if lvl <= 2 and isinstance(s, int) and isinstance(e, int) and e > s:
            if lvl < 2 and kids:
                deeper = _outline_nodes(kids, lvl + 1, p)
                if deeper:
                    out.extend(deeper)
                    continue
            out.append((s, e, " > ".join(x for x in p if x)))
        elif kids:
            out.extend(_outline_nodes(kids, lvl + 1, p))
    return out


def _with_overlap(text: str, spans: list[tuple[int, int, Optional[str]]]) -> list[DocumentChunk]:
    chunks: list[DocumentChunk] = []
    for i, (s, e, path) in enumerate(spans):
        body = text[s:e]
        prefix = ""
        if i > 0:
            prev = text[max(0, s - OVERLAP_CHARS):s]
            if prev:
                prefix = f"{OVERLAP_MARKER}\n{prev}\n{OVERLAP_MARKER}\n\n"
        chunks.append(DocumentChunk(i, s, e, path, prefix + body, len(prefix)))
    return chunks


def build_chunks(full_text: str, outline_json: Any = None) -> list[DocumentChunk]:
    text = full_text or ""
    if not text:
        return []
    nodes = sorted(_outline_nodes(outline_json), key=lambda x: x[0])
    spans: list[tuple[int, int, Optional[str]]] = []
    if nodes:
        cur_s: Optional[int] = None
        cur_e = 0
        cur_path: Optional[str] = None
        for s, e, path in nodes:
            e = min(e, len(text))
            if s < cur_e:
                s = cur_e
            if e <= s:
                continue
            if cur_s is None:
                cur_s, cur_e, cur_path = s, e, path
                continue
            if e - cur_s > CHUNK_TARGET_CHARS:
                spans.append((cur_s, s, cur_path))
                cur_s, cur_e, cur_path = s, e, path
            else:
                cur_e = e
        if cur_s is not None:
            spans.append((cur_s, len(text), cur_path))
        if spans and spans[0][0] > TAIL_MIN_CHARS:
            spans.insert(0, (0, spans[0][0], None))
        elif spans and spans[0][0] > 0:
            spans[0] = (0, spans[0][1], spans[0][2])
        # Ensure contiguous coverage between spans.
        fixed: list[tuple[int, int, Optional[str]]] = []
        for i, (s, e, p) in enumerate(spans):
            nxt = spans[i + 1][0] if i + 1 < len(spans) else len(text)
            fixed.append((s, max(e, nxt) if i + 1 < len(spans) else len(text), p))
        spans = fixed
        covered = spans[-1][1] if spans else 0
        if len(text) - covered > TAIL_MIN_CHARS:
            spans.append((covered, len(text), None))
    if not spans:
        start = 0
        while start < len(text):
            end = min(len(text), start + CHUNK_TARGET_CHARS)
            spans.append((start, end, None))
            start = end
    return _with_overlap(text, spans)


def _normalize_extract(data: Any, chunk: DocumentChunk) -> dict:
    if not isinstance(data, dict):
        data = {}
    out: dict = {"entities": [], "concepts": [], "claims": [], "relations": [], "topics": []}

    def _abs(item: dict) -> int:
        try:
            local = int(item.get("local_offset") or 0)
        except (TypeError, ValueError):
            local = 0
        return chunk.start_char + max(0, local)

    for c in data.get("concepts") or []:
        if isinstance(c, dict) and (c.get("term") or "").strip():
            item = dict(c)
            item["absolute_offset"] = _abs(c)
            out["concepts"].append(item)
    for c in data.get("claims") or []:
        if isinstance(c, dict) and (c.get("statement") or "").strip():
            item = dict(c)
            item["absolute_offset"] = _abs(c)
            out["claims"].append(item)
    for r in data.get("relations") or []:
        if isinstance(r, dict) and r.get("from") and r.get("to"):
            out["relations"].append(dict(r))
    out["topics"] = [t for t in (data.get("topics") or []) if isinstance(t, str) and t.strip()]
    return out


async def extract_chunk(llm, chunk: DocumentChunk, source_title: str = "") -> dict:
    prompt = EXTRACTION_PROMPT_TEMPLATE.format(
        source_title=source_title or "",
        section_path=chunk.section_path or "-",
        chunk_text=chunk.text,
    )
    raw = await asyncio.wait_for(
        llm.generate(prompt, system=EXTRACTION_SYSTEM_PROMPT, temperature=0.1), timeout=LLM_TIMEOUT_S
    )
    data = parse_json_loose(strip_code_fence(raw or ""))
    return _normalize_extract(data, chunk)


async def _upsert_row(session, source_id, chunk: DocumentChunk, status: str, extract: Optional[dict],
                      error: Optional[str]) -> None:
    from app.database.models import SourceChunkExtract

    values = {
        "source_id": source_id,
        "chunk_index": chunk.index,
        "start_char": chunk.start_char,
        "end_char": chunk.end_char,
        "section_path": chunk.section_path,
        "extract_json": extract,
        "status": status,
        "error_message": (error or "")[:ERROR_MAX_LEN] or None,
    }
    stmt = pg_insert(SourceChunkExtract).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["source_id", "chunk_index"],
        set_={k: stmt.excluded[k] for k in ("start_char", "end_char", "section_path", "extract_json",
                                             "status", "error_message")},
    )
    await session.execute(stmt)


async def run_map_phase(session, source_id, full_text: str, outline_json, tracker, llm,
                        source_title: str = "") -> tuple[str, list]:
    from app.database.models import SourceChunkExtract

    strategy = classify_strategy(full_text)
    chunks = build_chunks(full_text, outline_json)
    existing = (await session.execute(
        select(SourceChunkExtract).where(SourceChunkExtract.source_id == source_id)
    )).scalars().all()
    done_idx = {r.chunk_index for r in existing if r.status == "done"}
    todo = [c for c in chunks if c.index not in done_idx]
    total = max(1, len(chunks))
    completed = len(chunks) - len(todo)
    if tracker is not None:
        await tracker.update(10, f"Extracting knowledge from {len(chunks)} chunk(s)...")

    sem = asyncio.Semaphore(MAX_PARALLEL_CALLS)
    lock = asyncio.Lock()
    results: dict[int, tuple[str, Optional[dict], Optional[str]]] = {}

    async def _run(chunk: DocumentChunk) -> None:
        nonlocal completed
        async with sem:
            try:
                data = await extract_chunk(llm, chunk, source_title)
                results[chunk.index] = ("done", data, None)
            except Exception as e:
                results[chunk.index] = ("error", None, f"{type(e).__name__}: {e}")
        async with lock:
            completed += 1
            if tracker is not None:
                try:
                    await tracker.update(int(10 + 40 * completed / total),
                                         f"Extracted {completed}/{len(chunks)} chunk(s)")
                except Exception:
                    pass

    await asyncio.gather(*[_run(c) for c in todo])

    # Retry failed chunks once, sequentially.
    for chunk in todo:
        if results.get(chunk.index, ("error",))[0] != "error":
            continue
        try:
            data = await extract_chunk(llm, chunk, source_title)
            results[chunk.index] = ("done", data, None)
        except Exception as e:
            results[chunk.index] = ("error", None, f"{type(e).__name__}: {e}")
            logger.warning(f"map[{source_id}] chunk {chunk.index} failed: {e}")

    for chunk in todo:
        status, data, err = results[chunk.index]
        await _upsert_row(session, source_id, chunk, status, data, err)
    await session.commit()

    rows = (await session.execute(
        select(SourceChunkExtract)
        .where(SourceChunkExtract.source_id == source_id, SourceChunkExtract.status == "done")
        .order_by(SourceChunkExtract.chunk_index)
    )).scalars().all()
    return strategy, list(rows)
