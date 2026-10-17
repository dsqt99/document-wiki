"""Persistence of embedding rows (PostgreSQL bookkeeping + Milvus vectors).

PostgreSQL keeps one row per (object, model spec) with the content hash and
timestamp; the vector column is left NULL because the vectors themselves are
stored in Milvus. None of these functions commit: the caller owns the
transaction.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any, Optional

from loguru import logger
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embedding_catalog import get_spec
from app.database.models import (
    EMBEDDING_TABLE_DIMENSIONS,
    get_embedding_model_for_dim,
    get_source_chunk_embedding_model_for_dim,
    get_wiki_page_chunk_embedding_model_for_dim,
)
from app.services import milvus_service

MAX_EMBED_INPUT_CHARS = 8000


# ---------------------------------------------------------------------------
# Hashing / input text
# ---------------------------------------------------------------------------

def _join_fields(title: Optional[str], summary: Optional[str], content_md: Optional[str]) -> str:
    return "\n\n".join([title or "", summary or "", content_md or ""])


def compute_content_hash(title: Optional[str], summary: Optional[str], content_md: Optional[str]) -> str:
    return hashlib.sha256(_join_fields(title, summary, content_md).encode("utf-8")).hexdigest()


def embedding_input_text(title: Optional[str], summary: Optional[str], content_md: Optional[str]) -> str:
    return _join_fields(title, summary, content_md)[:MAX_EMBED_INPUT_CHARS]


def chunk_content_hash(text: Optional[str]) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def wiki_chunk_content_hash(heading_path: Optional[str], text: Optional[str]) -> str:
    payload = f"{heading_path or ''}\n\n{text or ''}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_spec_for_job(job: Any):
    return get_spec(job.model_spec_id)


def _rowcount(result: Any) -> int:
    count = getattr(result, "rowcount", 0)
    try:
        return max(int(count or 0), 0)
    except (TypeError, ValueError):
        return 0


def _milvus_call(fn, *args, **kwargs) -> None:
    """Milvus sync is best effort: PG bookkeeping must not fail because of it."""
    try:
        fn(*args, **kwargs)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(f"Milvus sync failed in {getattr(fn, '__name__', fn)}: {exc}")


def _milvus_delete_other_specs(collection_prefix: str, keep_spec_id: str) -> None:
    client = milvus_service.get_milvus_client()
    if not client:
        return
    safe = str(keep_spec_id).replace('"', '\\"')
    for dim in EMBEDDING_TABLE_DIMENSIONS:
        name = f"{collection_prefix}_{dim}"
        try:
            if client.has_collection(name):
                client.delete(collection_name=name, filter=f'model_spec_id != "{safe}"')
        except Exception as exc:
            logger.debug(f"Milvus stale cleanup failed for {name}: {exc}")


# ---------------------------------------------------------------------------
# Wiki page embeddings
# ---------------------------------------------------------------------------

async def upsert_page_embedding(
    session: AsyncSession,
    page_id: uuid.UUID,
    spec,
    vector: list[float],
    content_hash: str,
    *,
    title: Optional[str] = None,
    summary: Optional[str] = None,
    content_md: Optional[str] = None,
) -> None:
    model = get_embedding_model_for_dim(spec.dimension)
    stmt = pg_insert(model.__table__).values(
        page_id=page_id,
        model_spec_id=spec.id,
        content_hash=content_hash,
        embedding=None,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["page_id", "model_spec_id"],
        set_={"content_hash": stmt.excluded.content_hash, "embedded_at": func.now()},
    )
    await session.execute(stmt)
    _milvus_call(
        milvus_service.upsert_page_vector_to_milvus,
        page_id,
        spec.id,
        spec.dimension,
        list(vector),
        content_hash,
        title=title,
        summary=summary,
        content=content_md,
    )


async def get_existing_hash(
    session: AsyncSession, page_id: uuid.UUID, spec_id: str, dimension: int
) -> Optional[str]:
    model = get_embedding_model_for_dim(dimension)
    result = await session.execute(
        select(model.content_hash).where(model.page_id == page_id, model.model_spec_id == spec_id)
    )
    return result.scalar_one_or_none()


async def cleanup_stale_embeddings(session: AsyncSession, keep_spec_id: str) -> int:
    total = 0
    for dim in EMBEDDING_TABLE_DIMENSIONS:
        model = get_embedding_model_for_dim(dim)
        res = await session.execute(delete(model).where(model.model_spec_id != keep_spec_id))
        total += _rowcount(res)
    _milvus_delete_other_specs("arkon_wiki_pages", keep_spec_id)
    return total


async def cleanup_stale_source_chunk_embeddings(session: AsyncSession, keep_spec_id: str) -> int:
    total = 0
    for dim in EMBEDDING_TABLE_DIMENSIONS:
        model = get_source_chunk_embedding_model_for_dim(dim)
        res = await session.execute(delete(model).where(model.model_spec_id != keep_spec_id))
        total += _rowcount(res)
    _milvus_delete_other_specs("arkon_source_chunks", keep_spec_id)
    return total


async def cleanup_stale_wiki_chunk_embeddings(session: AsyncSession, keep_spec_id: str) -> int:
    total = 0
    for dim in EMBEDDING_TABLE_DIMENSIONS:
        model = get_wiki_page_chunk_embedding_model_for_dim(dim)
        res = await session.execute(delete(model).where(model.model_spec_id != keep_spec_id))
        total += _rowcount(res)
    _milvus_delete_other_specs("arkon_wiki_chunks", keep_spec_id)
    return total


async def delete_wiki_page_embeddings(session: AsyncSession, page_id: uuid.UUID) -> int:
    total = 0
    for dim in EMBEDDING_TABLE_DIMENSIONS:
        model = get_embedding_model_for_dim(dim)
        res = await session.execute(delete(model).where(model.page_id == page_id))
        total += _rowcount(res)
        _milvus_call(milvus_service.delete_page_vectors_from_milvus, page_id, dim)
    return total


# ---------------------------------------------------------------------------
# Source (verbatim) chunk embeddings
# ---------------------------------------------------------------------------

async def upsert_chunk_embedding(
    session: AsyncSession,
    source_id: uuid.UUID,
    chunk_index: int,
    spec,
    vector: list[float],
    *,
    text: str,
    start_char: Optional[int],
    end_char: Optional[int],
    page_number: Optional[int],
    content_hash: str,
) -> None:
    model = get_source_chunk_embedding_model_for_dim(spec.dimension)
    page_no = page_number if page_number is not None else 1
    stmt = pg_insert(model.__table__).values(
        source_id=source_id,
        chunk_index=chunk_index,
        model_spec_id=spec.id,
        start_char=start_char,
        end_char=end_char,
        page_number=page_no,
        text=text,
        content_hash=content_hash,
        embedding=None,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["source_id", "chunk_index", "model_spec_id"],
        set_={
            "content_hash": stmt.excluded.content_hash,
            "text": stmt.excluded.text,
            "start_char": stmt.excluded.start_char,
            "end_char": stmt.excluded.end_char,
            "page_number": stmt.excluded.page_number,
            "embedded_at": func.now(),
        },
    )
    await session.execute(stmt)
    _milvus_call(
        milvus_service.upsert_source_chunk_vector_to_milvus,
        source_id,
        chunk_index,
        spec.id,
        spec.dimension,
        list(vector),
        text=text or "",
        start_char=start_char or 0,
        end_char=end_char or 0,
        page_number=page_no,
        content_hash=content_hash or "",
    )


async def delete_source_chunk_embeddings(session: AsyncSession, source_id: uuid.UUID) -> int:
    total = 0
    for dim in EMBEDDING_TABLE_DIMENSIONS:
        model = get_source_chunk_embedding_model_for_dim(dim)
        res = await session.execute(delete(model).where(model.source_id == source_id))
        total += _rowcount(res)
        _milvus_call(milvus_service.delete_source_chunk_vectors_from_milvus, source_id, dim)
    return total


# ---------------------------------------------------------------------------
# Wiki page chunk embeddings
# ---------------------------------------------------------------------------

async def upsert_wiki_chunk_embedding(
    session: AsyncSession,
    page_id: uuid.UUID,
    chunk_index: int,
    spec,
    vector: list[float],
    *,
    text: str,
    heading_path: Optional[str],
    content_hash: str,
) -> None:
    model = get_wiki_page_chunk_embedding_model_for_dim(spec.dimension)
    stmt = pg_insert(model.__table__).values(
        page_id=page_id,
        chunk_index=chunk_index,
        model_spec_id=spec.id,
        heading_path=heading_path or "",
        text=text,
        content_hash=content_hash,
        embedding=None,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["page_id", "chunk_index", "model_spec_id"],
        set_={
            "content_hash": stmt.excluded.content_hash,
            "text": stmt.excluded.text,
            "heading_path": stmt.excluded.heading_path,
            "embedded_at": func.now(),
        },
    )
    await session.execute(stmt)
    _milvus_call(
        milvus_service.upsert_wiki_chunk_vector_to_milvus,
        page_id,
        chunk_index,
        spec.id,
        spec.dimension,
        list(vector),
        text=text or "",
        heading_path=heading_path or "",
        content_hash=content_hash or "",
    )


async def delete_wiki_page_chunk_embeddings(
    session: AsyncSession, page_id: uuid.UUID, spec_id: Optional[str] = None
) -> int:
    total = 0
    for dim in EMBEDDING_TABLE_DIMENSIONS:
        model = get_wiki_page_chunk_embedding_model_for_dim(dim)
        stmt = delete(model).where(model.page_id == page_id)
        if spec_id:
            stmt = stmt.where(model.model_spec_id == spec_id)
        res = await session.execute(stmt)
        total += _rowcount(res)
        _milvus_call(milvus_service.delete_wiki_chunk_vectors_from_milvus, page_id, dim, spec_id)
    return total
