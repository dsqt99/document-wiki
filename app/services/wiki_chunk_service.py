"""Wiki page chunking + indexing for hybrid search.

A wiki page's `content_md` is split into section-aligned, retrieval-sized chunks
(one chunk per markdown heading section, long sections sub-split into overlapping
windows) and embedded per-chunk into wiki_page_chunk_embeddings_<dim>. This
replaces the old one-vector-per-page approach: long pages no longer lose their
tail to an 8000-char truncation, and each chunk carries a `heading_path`
breadcrumb for citation context.

Mirrors app/services/verbatim_service.py (which does the same for verbatim
Source.full_text). The GIN full-text index on the chunk `text` column (migration
037) lets the same rows serve the lexical half of hybrid search.
"""

import re
from dataclasses import dataclass
from typing import Optional

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embedding_catalog import get_spec
from app.ai.registry import ProviderRegistry
from app.database.models import WikiPage
from app.services.embedding_storage import (
    delete_wiki_page_chunk_embeddings,
    embedding_input_text,
    upsert_page_embedding,
    upsert_wiki_chunk_embedding,
    wiki_chunk_content_hash,
)

from app.services.chunk_budget import CHUNK_TARGET_TOKENS, end_for_tokens, estimate_tokens, overlap_chars

# Retrieval-sized chunks (match the verbatim chunker for a consistent pool).
MIN_CHUNK_CHARS = 50

# ATX markdown headings, H1–H3 (deeper headings stay inside their parent section).
_HEADING_RE = re.compile(r"^(#{1,3})\s+(.*)$")
_ENDMATTER_MARKER_RE = re.compile(r"\A<!-- cahy:legal-endmatter kind=(appendix|notes) -->\r?\n")


@dataclass
class WikiChunk:
    index: int
    heading_path: str  # breadcrumb "H1 > H2 > H3" for the section this came from
    text: str


@dataclass
class _Section:
    heading_path: str
    text: str


def _split_sections(content_md: str) -> list[_Section]:
    """Split markdown into sections by H1–H3 headings, tracking the heading path.

    Text before the first heading (page preamble) becomes a section with an empty
    heading_path. Each heading opens a new section whose breadcrumb reflects the
    current H1 > H2 > H3 nesting.
    """
    lines = (content_md or "").splitlines()
    sections: list[_Section] = []
    # Current heading stack: index 0 = H1, 1 = H2, 2 = H3.
    stack: list[Optional[str]] = [None, None, None]
    buf: list[str] = []
    cur_path = ""

    def _flush():
        text = "\n".join(buf).strip()
        if text:
            sections.append(_Section(heading_path=cur_path, text=text))
        buf.clear()

    for line in lines:
        m = _HEADING_RE.match(line)
        if m:
            _flush()
            level = len(m.group(1))  # 1..3
            title = m.group(2).strip()
            stack[level - 1] = title
            for i in range(level, 3):
                stack[i] = None
            cur_path = " > ".join(h for h in stack[:level] if h)
        else:
            buf.append(line)
    _flush()
    return sections


def _window(text: str) -> list[str]:
    """Sub-split a long section into overlapping windows (mirror verbatim logic)."""
    if estimate_tokens(text) <= CHUNK_TARGET_TOKENS:
        return [text]
    out: list[str] = []
    pos = 0
    n = len(text)
    while pos < n:
        end = end_for_tokens(text, pos, n)
        out.append(text[pos:end])
        if end >= n:
            break
        step_back = overlap_chars(end - pos)
        pos = end - step_back if step_back and end - step_back > pos else end
    return out


def build_wiki_chunks(content_md: str, *, page: Optional[WikiPage] = None) -> list[WikiChunk]:
    """Split a wiki page's markdown into section-aligned, retrieval-sized chunks.

    Each chunk belongs to one heading section and carries its heading breadcrumb.
    Sections longer than CHUNK_TARGET_TOKENS are sub-split into overlapping windows.
    """
    marker = _ENDMATTER_MARKER_RE.match(content_md or "")
    if (
        marker and page is not None
        and getattr(page, "origin_tag", None) == "extracted"
        and getattr(page, "source_ids", None)
        and (page.slug or "").startswith("phu-luc-" if marker.group(1) == "appendix" else "chu-thich-")
    ):
        # Retain headings and even very short tails: they belong to one opaque unit.
        body = content_md[marker.end():]
        return [
            WikiChunk(index=index, heading_path=page.title or "", text=window)
            for index, window in enumerate(_window(body)) if window.strip()
        ]
    chunks: list[WikiChunk] = []
    idx = 0
    for section in _split_sections(content_md):
        for window_text in _window(section.text):
            if len(window_text.strip()) < MIN_CHUNK_CHARS:
                continue
            chunks.append(WikiChunk(
                index=idx,
                heading_path=section.heading_path,
                text=window_text,
            ))
            idx += 1
    return chunks


def _embed_input(page: WikiPage, chunk: WikiChunk) -> str:
    """Text fed to the embedding model — page title + heading path give the chunk
    global context so a bare section still embeds near its topic."""
    prefix_parts = [page.title]
    if chunk.heading_path:
        prefix_parts.append(chunk.heading_path)
    prefix = " — ".join(p for p in prefix_parts if p)
    return f"{prefix}\n\n{chunk.text}" if prefix else chunk.text


async def index_wiki_page_chunks(
    session: AsyncSession,
    page: WikiPage,
    spec_id: Optional[str] = None,
) -> int:
    """Chunk + embed a wiki page's content_md into wiki_page_chunk_embeddings_<dim>
    and page-level vector into wiki_page_embeddings_<dim> (synced to Milvus).

    Returns the number of chunks indexed. Returns 0 (and logs) if no embedding
    model is configured or for reserved pages (_index, _log, _hot).
    Does NOT commit — the caller owns the transaction so a batch of pages
    commits together.

    Args:
        spec_id: Embed against this specific spec instead of the system's active
            one. Used by the re-embed migration job (embeds with the NEW model
            while the active spec still points at the OLD one).
    """
    if page.slug in ("_index", "_log", "_hot"):
        return 0

    registry = ProviderRegistry(session)
    if spec_id is None:
        spec_id = await registry.get_active_embedding_spec_id()
    if not spec_id:
        logger.warning(
            f"index_wiki_page_chunks: no active embedding model — page {page.id} "
            f"stored but not semantically indexed (run re-embed after configuring a model)"
        )
        return 0

    spec = get_spec(spec_id)
    chunks = build_wiki_chunks(page.content_md or "", page=page)

    # Clear prior chunk rows for THIS page in THIS spec only, so a shorter re-edit
    # doesn't leave orphaned high-index chunks. Other specs stay intact until the
    # atomic flip prunes them.
    await delete_wiki_page_chunk_embeddings(session, page.id, spec_id=spec.id)

    page_text = embedding_input_text(page.title or "", page.summary or "", page.content_md or "")
    if not page_text.strip() and not chunks:
        return 0

    provider = await registry.get_embedding(task="document", spec_id=spec.id)
    chunk_inputs = [_embed_input(page, c) for c in chunks]
    all_texts = [page_text] + chunk_inputs
    vectors = await provider.embed_batch(all_texts)
    if len(vectors) != len(all_texts):
        raise RuntimeError(f"Wiki index embedding batch incomplete: {len(vectors)}/{len(all_texts)}")

    # 1. Upsert page-level embedding (PostgreSQL + Milvus)
    page_vector = list(vectors[0])
    chash = wiki_chunk_content_hash("", page.content_md or "")
    page_indexed = await upsert_page_embedding(
        session,
        page_id=page.id,
        spec=spec,
        vector=page_vector,
        content_hash=chash,
        title=page.title,
        summary=page.summary,
        content_md=page.content_md,
    )
    if page_indexed is False:
        raise RuntimeError("Wiki page vector index write failed")

    # 2. Upsert chunk-level embeddings (PostgreSQL + Milvus)
    chunk_vectors = vectors[1:]
    for chunk, vector in zip(chunks, chunk_vectors):
        chunk_indexed = await upsert_wiki_chunk_embedding(
            session,
            page_id=page.id,
            chunk_index=chunk.index,
            spec=spec,
            vector=list(vector),
            text=chunk.text,
            heading_path=chunk.heading_path,
            content_hash=wiki_chunk_content_hash(chunk.heading_path, chunk.text),
        )
        if chunk_indexed is False:
            raise RuntimeError(f"Wiki chunk vector index write failed at chunk {chunk.index}")
    return len(chunks)
