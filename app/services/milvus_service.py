"""
Milvus Vector Database Integration for Arkon.

Provides high-performance vector storage and similarity search for:
1. Wiki page embeddings (arkon_wiki_pages_<dim>)
2. Wiki chunk embeddings (arkon_wiki_chunks_<dim>)
3. Source verbatim chunk embeddings (arkon_source_chunks_<dim>)
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from loguru import logger

from app.config import settings

_milvus_client: Optional[Any] = None
_milvus_initialized: bool = False


def get_milvus_client() -> Optional[Any]:
    """Get or initialize the MilvusClient singleton."""
    global _milvus_client, _milvus_initialized

    if not settings.milvus_enabled:
        return None

    if not _milvus_initialized:
        _milvus_initialized = True
        host = settings.milvus_host or "milvus"
        port = settings.milvus_port or 19530
        uri = f"http://{host}:{port}"

        try:
            from pymilvus import MilvusClient

            _milvus_client = MilvusClient(
                uri=uri,
                user=settings.milvus_user or "",
                password=settings.milvus_password or "",
                db_name=settings.milvus_database or "default",
            )
            logger.info(f"Milvus client connected successfully to {uri}")
        except Exception as e:
            logger.warning(f"Failed to connect to Milvus at {uri}: {e}")
            _milvus_client = None

    return _milvus_client


def _ensure_collection(client: Any, collection_name: str, dimension: int, collection_type: str) -> None:
    """Ensure a collection exists with correct schema and index."""
    try:
        if client.has_collection(collection_name):
            return

        logger.info(f"Creating Milvus collection '{collection_name}' with dimension={dimension}")
        client.create_collection(
            collection_name=collection_name,
            dimension=dimension,
            primary_field_name="id",
            id_type="string",
            max_length=128,
            vector_field_name="vector",
            metric_type="COSINE",
            auto_id=False,
            enable_dynamic_field=True,
        )
    except Exception as e:
        logger.debug(f"Milvus ensure_collection error for '{collection_name}': {e}")


# ---------------------------------------------------------------------------
# Wiki Page Embeddings
# ---------------------------------------------------------------------------

def upsert_page_vector_to_milvus(
    page_id: uuid.UUID,
    spec_id: str,
    dimension: int,
    vector: list[float],
    content_hash: str,
    *,
    title: Optional[str] = None,
    summary: Optional[str] = None,
    content: Optional[str] = None,
) -> None:
    """Upsert a wiki page embedding vector into Milvus."""
    client = get_milvus_client()
    if not client:
        return

    collection_name = f"arkon_wiki_pages_{dimension}"
    try:
        _ensure_collection(client, collection_name, dimension, "page")
        record_id = f"{page_id}_{spec_id}"
        # Truncate content in dynamic field so dynamic field JSON never exceeds Milvus 64KB limit
        safe_content = (content or "")[:12000]
        data = [
            {
                "id": record_id,
                "page_id": str(page_id),
                "model_spec_id": spec_id,
                "title": (title or "")[:500],
                "summary": (summary or "")[:2000],
                "content": safe_content,
                "text": safe_content,
                "content_hash": content_hash,
                "vector": vector,
            }
        ]
        client.upsert(collection_name=collection_name, data=data)
    except Exception as e:
        logger.debug(f"Milvus upsert_page_vector error: {e}")


def delete_page_vectors_from_milvus(page_id: uuid.UUID, dimension: int) -> None:
    """Delete all vectors for a wiki page across a dimension collection in Milvus."""
    client = get_milvus_client()
    if not client:
        return

    collection_name = f"arkon_wiki_pages_{dimension}"
    try:
        if client.has_collection(collection_name):
            client.delete(
                collection_name=collection_name,
                filter=f'page_id == "{str(page_id)}"',
            )
    except Exception as e:
        logger.debug(f"Milvus delete_page_vectors error: {e}")


# ---------------------------------------------------------------------------
# Wiki Chunk Embeddings
# ---------------------------------------------------------------------------

def upsert_wiki_chunk_vector_to_milvus(
    page_id: uuid.UUID,
    chunk_index: int,
    spec_id: str,
    dimension: int,
    vector: list[float],
    *,
    text: str,
    heading_path: str,
    content_hash: str,
) -> None:
    """Upsert a wiki chunk embedding vector into Milvus."""
    client = get_milvus_client()
    if not client:
        return

    collection_name = f"arkon_wiki_chunks_{dimension}"
    try:
        _ensure_collection(client, collection_name, dimension, "wiki_chunk")
        record_id = f"{page_id}_{chunk_index}_{spec_id}"
        data = [
            {
                "id": record_id,
                "page_id": str(page_id),
                "chunk_index": chunk_index,
                "model_spec_id": spec_id,
                "heading_path": heading_path[:500] if heading_path else "",
                "content": text or "",
                "text": text or "",
                "content_hash": content_hash,
                "vector": vector,
            }
        ]
        client.upsert(collection_name=collection_name, data=data)
    except Exception as e:
        logger.debug(f"Milvus upsert_wiki_chunk_vector error: {e}")


def delete_wiki_chunk_vectors_from_milvus(
    page_id: uuid.UUID, dimension: int, spec_id: Optional[str] = None
) -> None:
    """Delete chunk vectors for a wiki page in Milvus."""
    client = get_milvus_client()
    if not client:
        return

    collection_name = f"arkon_wiki_chunks_{dimension}"
    try:
        if client.has_collection(collection_name):
            filt = f'page_id == "{str(page_id)}"'
            if spec_id:
                filt += f' and model_spec_id == "{spec_id}"'
            client.delete(collection_name=collection_name, filter=filt)
    except Exception as e:
        logger.debug(f"Milvus delete_wiki_chunk_vectors error: {e}")


# ---------------------------------------------------------------------------
# Source Chunk Embeddings (Verbatim)
# ---------------------------------------------------------------------------

def upsert_source_chunk_vector_to_milvus(
    source_id: uuid.UUID,
    chunk_index: int,
    spec_id: str,
    dimension: int,
    vector: list[float],
    *,
    text: str = "",
    start_char: int = 0,
    end_char: int = 0,
    page_number: int = 1,
    content_hash: str = "",
) -> None:
    """Upsert a verbatim source chunk vector into Milvus."""
    client = get_milvus_client()
    if not client:
        return

    collection_name = f"arkon_source_chunks_{dimension}"
    try:
        _ensure_collection(client, collection_name, dimension, "source_chunk")
        record_id = f"{source_id}_{chunk_index}_{spec_id}"
        data = [
            {
                "id": record_id,
                "source_id": str(source_id),
                "chunk_index": chunk_index,
                "model_spec_id": spec_id,
                "content": text or "",
                "text": text or "",
                "start_char": start_char,
                "end_char": end_char,
                "page_number": page_number,
                "content_hash": content_hash,
                "vector": vector,
            }
        ]
        client.upsert(collection_name=collection_name, data=data)
    except Exception as e:
        logger.debug(f"Milvus upsert_source_chunk_vector error: {e}")


def delete_source_chunk_vectors_from_milvus(source_id: uuid.UUID, dimension: int) -> None:
    """Delete all chunk vectors for a verbatim source in Milvus."""
    client = get_milvus_client()
    if not client:
        return

    collection_name = f"arkon_source_chunks_{dimension}"
    try:
        if client.has_collection(collection_name):
            client.delete(
                collection_name=collection_name,
                filter=f'source_id == "{str(source_id)}"',
            )
    except Exception as e:
        logger.debug(f"Milvus delete_source_chunk_vectors error: {e}")


# ---------------------------------------------------------------------------
# Similarity Search via Milvus
# ---------------------------------------------------------------------------

def search_milvus_vectors(
    collection_name: str,
    query_vector: list[float],
    limit: int = 10,
    filter_expr: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Search similar vectors in a Milvus collection."""
    client = get_milvus_client()
    if not client:
        return []

    try:
        if not client.has_collection(collection_name):
            return []

        search_params = {"metric_type": "COSINE", "params": {"nprobe": 10}}
        results = client.search(
            collection_name=collection_name,
            data=[query_vector],
            limit=limit,
            filter=filter_expr or "",
            output_fields=["*"],
            search_params=search_params,
            consistency_level="Strong",
        )

        flat_results = []
        if results and len(results) > 0:
            for hit in results[0]:
                entity = hit.get("entity", {})
                entity["score"] = hit.get("distance", 0.0)
                flat_results.append(entity)
        return flat_results
    except Exception as e:
        logger.debug(f"Milvus search error in '{collection_name}': {e}")
        return []


def test_milvus_connection() -> tuple[bool, str]:
    """Test connection to Milvus."""
    try:
        client = get_milvus_client()
        if not client:
            return False, "Milvus client could not be initialized (disabled or connection failure)"
        collections = client.list_collections()
        return True, f"OK — connected to Milvus at {settings.milvus_host}:{settings.milvus_port}, collections={collections}"
    except Exception as e:
        return False, f"Milvus connection error: {e}"
