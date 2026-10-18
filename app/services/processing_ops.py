"""Bulk manual-processing actions for the knowledge page: counts, retry-all-failed and re-embedding pages."""

import uuid
from types import SimpleNamespace
from typing import Optional

from sqlalchemy import and_, exists, func, or_, select

from app.database.models import Source, WikiPage

RESERVED_SLUGS = ("_index", "_log", "_hot")
FAILED = ("error", "partial")
RUNNING = ("pending", "processing")
REVIEW = ("plan_ready", "awaiting_approval")


def _chunk_missing_clause():
    return and_(
        Source.status.in_(("ready", "partial")),
        Source.full_text.isnot(None),
        Source.full_text != "",
        Source.chunk_status.in_(("pending", "error")),
    )


async def _active_spec(db):
    from app.ai.embedding_catalog import get_spec
    from app.ai.registry import ProviderRegistry

    spec_id = await ProviderRegistry(db).get_active_embedding_spec_id()
    if not spec_id:
        return None
    try:
        return get_spec(spec_id)
    except Exception:  # noqa: BLE001  (unknown/custom spec: nothing to compare against)
        return None


def _missing_vector_query(spec):
    from app.database.models import get_embedding_model_for_dim, get_wiki_page_chunk_embedding_model_for_dim

    page_model = get_embedding_model_for_dim(spec.dimension)
    chunk_model = get_wiki_page_chunk_embedding_model_for_dim(spec.dimension)
    no_page_vec = ~exists().where(page_model.page_id == WikiPage.id, page_model.model_spec_id == spec.id)
    no_chunk_vec = ~exists().where(chunk_model.page_id == WikiPage.id, chunk_model.model_spec_id == spec.id)
    return select(WikiPage.id).where(
        WikiPage.slug.notin_(RESERVED_SLUGS),
        WikiPage.content_md.isnot(None),
        WikiPage.content_md != "",
        or_(no_page_vec, no_chunk_vec),
    )


async def missing_vector_page_ids(db, limit: Optional[int] = None) -> list[uuid.UUID]:
    """Wiki pages lacking a page vector or chunk vectors for the active embedding model."""
    spec = await _active_spec(db)
    if spec is None:
        return []
    stmt = _missing_vector_query(spec).order_by(WikiPage.created_at)
    if limit is not None:
        stmt = stmt.limit(limit)
    return list((await db.execute(stmt)).scalars().all())


async def summary(db, clause=None) -> dict:
    """Counts behind the "Xử lý nội dung" menu; ``clause`` restricts sources to what the user may read."""
    from app.services.source_retry import failed_by_ai_outage

    scope = [clause] if clause is not None else []

    async def count(*where) -> int:
        return int((await db.execute(select(func.count()).select_from(Source).where(*scope, *where))).scalar() or 0)

    failed_rows = (await db.execute(
        select(Source.error_message, Source.wiki_error_message, Source.chunk_error_message)
        .where(*scope, Source.status.in_(FAILED))
    )).all()
    ai_outage = sum(
        1 for r in failed_rows
        if failed_by_ai_outage(SimpleNamespace(error_message=r[0], wiki_error_message=r[1], chunk_error_message=r[2]))
    )
    spec = await _active_spec(db)
    missing_vectors = 0
    if spec is not None:
        sub = _missing_vector_query(spec).subquery()
        missing_vectors = int((await db.execute(select(func.count()).select_from(sub))).scalar() or 0)
    return {
        "failed": len(failed_rows),
        "failed_ai_outage": ai_outage,
        "running": await count(Source.status.in_(RUNNING)),
        "review": await count(Source.status.in_(REVIEW)),
        "chunk_missing": await count(_chunk_missing_clause()),
        "pages_missing_vectors": missing_vectors,
    }


async def reembed_pages(page_ids) -> dict:
    """Re-index (page + chunk vectors) each page; one commit per page so a failure keeps the rest."""
    import app.database as _db
    from app.services.wiki_chunk_service import index_wiki_page_chunks

    out = {"done": 0, "failed": []}
    for pid in page_ids:
        async with _db.async_session_factory() as db:
            page = await db.get(WikiPage, pid)
            if page is None:
                continue
            try:
                await index_wiki_page_chunks(db, page)
                await db.commit()
                out["done"] += 1
            except Exception as e:  # noqa: BLE001
                await db.rollback()
                out["failed"].append((str(pid), f"{type(e).__name__}: {str(e)[:200]}"))
    return out
