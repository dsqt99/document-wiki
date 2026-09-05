"""
Helpers for writing/reading wiki page embeddings across the
per-dimension `wiki_page_embeddings_<dim>` tables.

Use these instead of touching the embedding tables directly so callers don't
have to care which dimension corresponds to the active model.
"""

import hashlib
import uuid
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embedding_catalog import EmbeddingModelSpec, get_spec
from app.database.models import (
    EmbeddingJob,
    get_embedding_model_for_dim,
    get_source_chunk_embedding_model_for_dim,
    get_wiki_page_chunk_embedding_model_for_dim,
)


def compute_content_hash(title: str, summary: str, content_md: str) -> str:
    """Stable hash of the text we feed into the embedding model."""
    blob = f"{title}\n\n{summary or ''}\n\n{content_md or ''}".encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def embedding_input_text(title: str, summary: str, content_md: str) -> str:
    """The exact text that gets embedded — kept in one place so hash matches."""
    return f"{title}\n\n{summary or ''}\n\n{content_md or ''}"[:8000]


async def upsert_page_embedding(
    session: AsyncSession,
    page_id: uuid.UUID,
    spec: EmbeddingModelSpec,
    vector: list[float],
    content_hash: str,
    *,
    title: Optional[str] = None,
    summary: Optional[str] = None,
    content_md: Optional[str] = None,
) -> None:
    """Upsert one (page, model_spec_id) row into wiki_page_embeddings_<dim>."""
    from app.services.milvus_service import upsert_page_vector_to_milvus

    Model = get_embedding_model_for_dim(spec.dimension)
    stmt = pg_insert(Model).values(
        page_id=page_id,
        model_spec_id=spec.id,
        content_hash=content_hash,
        embedding=vector,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["page_id", "model_spec_id"],
        set_={
            "embedding": stmt.excluded.embedding,
            "content_hash": stmt.excluded.content_hash,
            "embedded_at": stmt.excluded.embedded_at,
        },
    )
    await session.execute(stmt)

    # Sync to Milvus with content and title
    upsert_page_vector_to_milvus(
        page_id,
        spec.id,
        spec.dimension,
        vector,
        content_hash,
        title=title,
        summary=summary,
        content=content_md,
    )


async def get_existing_hash(
    session: AsyncSession, page_id: uuid.UUID, spec_id: str, dimension: int
) -> Optional[str]:
    Model = get_embedding_model_for_dim(dimension)
    row = (
        await session.execute(
            select(Model.content_hash).where(
                Model.page_id == page_id, Model.model_spec_id == spec_id
            )
        )
    ).scalar_one_or_none()
    return row


async def cleanup_stale_embeddings(
    session: AsyncSession, keep_spec_id: str
) -> int:
    """
    Delete rows in every wiki_page_embeddings_<dim> table whose model_spec_id
    is NOT `keep_spec_id`. Returns total deleted rows.

    Called after an atomic flip so the inactive model's vectors don't waste
    disk + index memory.
    """
    from app.database.models import (
        WikiPageEmbedding768,
        WikiPageEmbedding1024,
        WikiPageEmbedding1536,
        WikiPageEmbedding3072,
    )
    total = 0
    for Model in (
        WikiPageEmbedding768,
        WikiPageEmbedding1024,
        WikiPageEmbedding1536,
        WikiPageEmbedding3072,
    ):
        result = await session.execute(
            delete(Model).where(Model.model_spec_id != keep_spec_id)
        )
        total += result.rowcount or 0  # type: ignore[union-attr]
    return total


def get_spec_for_job(job: EmbeddingJob) -> EmbeddingModelSpec:
    return get_spec(job.model_spec_id)


async def cleanup_stale_source_chunk_embeddings(
    session: AsyncSession, keep_spec_id: str
) -> int:
    """Delete source chunk embedding rows whose model_spec_id != keep_spec_id,
    across every dimension table. Mirrors cleanup_stale_embeddings for the
    verbatim source pool; called after the atomic embedding-model flip."""
    from app.database.models import (
        SourceChunkEmbedding768,
        SourceChunkEmbedding1024,
        SourceChunkEmbedding1536,
        SourceChunkEmbedding3072,
    )
    total = 0
    for Model in (
        SourceChunkEmbedding768,
        SourceChunkEmbedding1024,
        SourceChunkEmbedding1536,
        SourceChunkEmbedding3072,
    ):
        result = await session.execute(
            delete(Model).where(Model.model_spec_id != keep_spec_id)
        )
        total += result.rowcount or 0  # type: ignore[union-attr]
    return total


# ---------------------------------------------------------------------------
# Verbatim source chunk embeddings
# ---------------------------------------------------------------------------

def chunk_content_hash(text: str) -> str:
    """Stable hash of the raw chunk text fed into the embedding model."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def wiki_chunk_content_hash(heading_path: str, text: str) -> str:
    """Stable hash of a wiki chunk (heading breadcrumb + text) fed into the model."""
    blob = f"{heading_path or ''}\n\n{text or ''}".encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


async def upsert_chunk_embedding(
    session: AsyncSession,
    source_id: uuid.UUID,
    chunk_index: int,
    spec: EmbeddingModelSpec,
    vector: list[float],
    *,
    text: str,
    start_char: int,
    end_char: int,
    page_number: int,
    content_hash: str,
) -> None:
    """Upsert one (source, chunk_index, model_spec_id) row into
    source_chunk_embeddings_<dim>."""
    from app.services.milvus_service import upsert_source_chunk_vector_to_milvus

    Model = get_source_chunk_embedding_model_for_dim(spec.dimension)
    stmt = pg_insert(Model).values(
        source_id=source_id,
        chunk_index=chunk_index,
        model_spec_id=spec.id,
        start_char=start_char,
        end_char=end_char,
        page_number=page_number,
        text=text,
        content_hash=content_hash,
        embedding=vector,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["source_id", "chunk_index", "model_spec_id"],
        set_={
            "embedding": stmt.excluded.embedding,
            "content_hash": stmt.excluded.content_hash,
            "text": stmt.excluded.text,
            "start_char": stmt.excluded.start_char,
            "end_char": stmt.excluded.end_char,
            "page_number": stmt.excluded.page_number,
            "embedded_at": stmt.excluded.embedded_at,
        },
    )
    await session.execute(stmt)

    # Sync to Milvus
    upsert_source_chunk_vector_to_milvus(
        source_id,
        chunk_index,
        spec.id,
        spec.dimension,
        vector,
        text=text,
        start_char=start_char,
        end_char=end_char,
        page_number=page_number,
        content_hash=content_hash,
    )


async def delete_source_chunk_embeddings(
    session: AsyncSession, source_id: uuid.UUID
) -> int:
    """Delete every chunk embedding row for a source across all dimension tables.

    Called before re-indexing a verbatim source (re-ingest) so stale chunks from
    a previous run don't linger.
    """
    from app.database.models import (
        SourceChunkEmbedding768,
        SourceChunkEmbedding1024,
        SourceChunkEmbedding1536,
        SourceChunkEmbedding3072,
    )
    from app.services.milvus_service import delete_source_chunk_vectors_from_milvus

    total = 0
    for Model in (
        SourceChunkEmbedding768,
        SourceChunkEmbedding1024,
        SourceChunkEmbedding1536,
        SourceChunkEmbedding3072,
    ):
        result = await session.execute(
            delete(Model).where(Model.source_id == source_id)
        )
        total += result.rowcount or 0  # type: ignore[union-attr]

    for dim in (768, 1024, 1536, 3072):
        delete_source_chunk_vectors_from_milvus(source_id, dim)

    return total


# ---------------------------------------------------------------------------
# Wiki page chunk embeddings (hybrid search)
# ---------------------------------------------------------------------------

async def upsert_wiki_chunk_embedding(
    session: AsyncSession,
    page_id: uuid.UUID,
    chunk_index: int,
    spec: EmbeddingModelSpec,
    vector: list[float],
    *,
    text: str,
    heading_path: str,
    content_hash: str,
) -> None:
    """Upsert one (page, chunk_index, model_spec_id) row into
    wiki_page_chunk_embeddings_<dim>."""
    from app.services.milvus_service import upsert_wiki_chunk_vector_to_milvus

    Model = get_wiki_page_chunk_embedding_model_for_dim(spec.dimension)
    stmt = pg_insert(Model).values(
        page_id=page_id,
        chunk_index=chunk_index,
        model_spec_id=spec.id,
        heading_path=heading_path,
        text=text,
        content_hash=content_hash,
        embedding=vector,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["page_id", "chunk_index", "model_spec_id"],
        set_={
            "embedding": stmt.excluded.embedding,
            "content_hash": stmt.excluded.content_hash,
            "text": stmt.excluded.text,
            "heading_path": stmt.excluded.heading_path,
            "embedded_at": stmt.excluded.embedded_at,
        },
    )
    await session.execute(stmt)

    # Sync to Milvus
    upsert_wiki_chunk_vector_to_milvus(
        page_id,
        chunk_index,
        spec.id,
        spec.dimension,
        vector,
        text=text,
        heading_path=heading_path,
        content_hash=content_hash,
    )


async def delete_wiki_page_chunk_embeddings(
    session: AsyncSession, page_id: uuid.UUID, spec_id: Optional[str] = None
) -> int:
    """Delete chunk embedding rows for a page across all dimension tables.

    Pass `spec_id` to only clear rows for that spec (used when re-indexing a page
    against a specific model while another spec stays live); omit to clear all.
    """
    from app.database.models import (
        WikiPageChunkEmbedding768,
        WikiPageChunkEmbedding1024,
        WikiPageChunkEmbedding1536,
        WikiPageChunkEmbedding3072,
    )
    from app.services.milvus_service import delete_wiki_chunk_vectors_from_milvus

    total = 0
    for Model in (
        WikiPageChunkEmbedding768,
        WikiPageChunkEmbedding1024,
        WikiPageChunkEmbedding1536,
        WikiPageChunkEmbedding3072,
    ):
        stmt = delete(Model).where(Model.page_id == page_id)
        if spec_id is not None:
            stmt = stmt.where(Model.model_spec_id == spec_id)
        result = await session.execute(stmt)
        total += result.rowcount or 0  # type: ignore[union-attr]

    for dim in (768, 1024, 1536, 3072):
        delete_wiki_chunk_vectors_from_milvus(page_id, dim, spec_id=spec_id)

    return total


async def cleanup_stale_wiki_chunk_embeddings(
    session: AsyncSession, keep_spec_id: str
) -> int:
    """Delete wiki chunk embedding rows whose model_spec_id != keep_spec_id,
    across every dimension table. Mirrors cleanup_stale_source_chunk_embeddings;
    called after the atomic embedding-model flip."""
    from app.database.models import (
        WikiPageChunkEmbedding768,
        WikiPageChunkEmbedding1024,
        WikiPageChunkEmbedding1536,
        WikiPageChunkEmbedding3072,
    )
    total = 0
    for Model in (
        WikiPageChunkEmbedding768,
        WikiPageChunkEmbedding1024,
        WikiPageChunkEmbedding1536,
        WikiPageChunkEmbedding3072,
    ):
        result = await session.execute(
            delete(Model).where(Model.model_spec_id != keep_spec_id)
        )
        total += result.rowcount or 0  # type: ignore[union-attr]
    return total
