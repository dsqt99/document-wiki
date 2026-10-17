"""Semantic indexing of wiki pages built without the LLM pipeline (article and verbatim pages)."""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.ai.embedding_catalog import get_spec
from app.ai.registry import ProviderRegistry
from app.services.embedding_storage import upsert_page_embedding, wiki_chunk_content_hash
from app.services.wiki_chunk_service import index_wiki_page_chunks


async def embed_and_index_pages(session, pages: list, tracker: Any, source_id: Any = None) -> None:
    """Page-level embeddings, then section chunks. Progress moves from 70% to 95%."""
    total_pages = len(pages)
    await tracker.update(70, f"Đang tạo vector embeddings cho {total_pages} trang Wiki...")

    registry = ProviderRegistry(session)
    spec_id = await registry.get_active_embedding_spec_id()
    embedding_spec = get_spec(spec_id) if spec_id else None
    embedding_provider = None
    if embedding_spec:
        try:
            embedding_provider = await registry.get_embedding(task="document", spec_id=embedding_spec.id)
        except Exception as e:
            logger.warning(f"Failed to get embedding provider for {embedding_spec.id}: {e}")

    if not (embedding_provider and embedding_spec) or not total_pages:
        logger.info("No active embedding model configured — skipping semantic vector index.")
        return

    # Stop calling the embedding service after this many consecutive failures
    # (outage): pages stay readable/keyword-searchable and can be re-embedded later.
    max_consecutive_failures = 3
    consecutive_failures = 0
    # A. Page-level embedding in batches
    batch_size = 16
    for b_start in range(0, total_pages, batch_size):
        if consecutive_failures >= max_consecutive_failures:
            break
        b_pages = pages[b_start : b_start + batch_size]
        texts_to_embed = [f"{p.title}\n\n{p.summary}\n\n{(p.content_md or '')[:4000]}" for p in b_pages]
        try:
            vectors = await embedding_provider.embed_batch(texts_to_embed)
            for p, vec in zip(b_pages, vectors):
                chash = wiki_chunk_content_hash("", p.content_md or "")
                await upsert_page_embedding(
                    session,
                    page_id=p.id,
                    spec=embedding_spec,
                    vector=list(vec),
                    content_hash=chash,
                    title=p.title,
                    summary=p.summary,
                    content_md=p.content_md,
                )
            consecutive_failures = 0
        except Exception as e:
            consecutive_failures += 1
            logger.warning(f"Batch page embedding failed for pages {b_start}-{b_start+len(b_pages)}: {e}")

        pct = 70 + int((b_start + len(b_pages)) / total_pages * 15)
        await tracker.update(pct, f"Đã tính embedding trang ({b_start + len(b_pages)}/{total_pages})...")

    # B. Section-level chunk embeddings
    for idx, p in enumerate(pages):
        if consecutive_failures >= max_consecutive_failures:
            logger.warning(
                f"Embedding service unavailable — skipped semantic indexing for "
                f"{total_pages - idx} page(s) of source {source_id}; re-embed them later."
            )
            break
        try:
            await index_wiki_page_chunks(session, p, spec_id=embedding_spec.id)
            consecutive_failures = 0
        except Exception as e:
            consecutive_failures += 1
            logger.warning(f"Chunk embedding failed for page '{p.slug}': {e}")

        if idx % 10 == 0 or idx == total_pages - 1:
            pct = 85 + int((idx + 1) / total_pages * 10)
            await tracker.update(pct, f"Đã đánh chỉ mục chunk ({idx + 1}/{total_pages})...")
