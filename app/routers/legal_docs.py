"""
Document library ("Wiki Pháp luật") router.

Endpoints:
  GET  /api/wiki/legal-docs            — every readable document with its metadata
                                         (số hiệu, ngày ban hành/hiệu lực, lĩnh vực)
                                         and derived validity; facets are computed
                                         client-side.
  GET  /api/wiki/legal-docs/{key}      — one document (key = doc_slug or source id):
                                         metadata, preamble + articles, relations,
                                         linked wiki pages, file URLs.
  POST /api/wiki/legal-docs/backfill   — extract metadata for sources ingested
                                         before it existed.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only, selectinload

from app.database import get_db
from app.database.models import Employee, KnowledgeType, Source, WikiPage
from app.routers.sources import source_read_filter
from app.routers.wiki import _build_wiki_scope_filter
from app.services import wiki_service
from app.services.audit_service import log_audit
from app.services.auth_service import get_current_user, require_permission
from app.services.doc_metadata_service import (
    compute_validity,
    get_doc_meta,
    lifecycle_for,
    load_doc_relations,
    load_lifecycle,
)

router = APIRouter()

_LIST_COLUMNS = (
    Source.id, Source.title, Source.file_name, Source.knowledge_type_id, Source.scope_type,
    Source.scope_id, Source.status, Source.minio_key, Source.url, Source.metadata_,
    Source.created_at, Source.updated_at,
)


def _kt_out(kt: Optional[KnowledgeType]) -> Optional[dict]:
    if not kt:
        return None
    return {"id": str(kt.id), "name": kt.name, "slug": kt.slug, "color": kt.color}


def _doc_out(source: Source, lifecycle: dict) -> dict:
    meta = get_doc_meta(source)
    return {
        "id": str(source.id),
        "title": source.title or source.file_name or "",
        "file_name": source.file_name,
        "knowledge_type": _kt_out(source.knowledge_type),
        "scope_type": source.scope_type or "global",
        "status": source.status,
        "has_file": bool(source.minio_key),
        "url": source.url,
        "doc_slug": meta.get("doc_slug"),
        "meta": meta,
        "validity": compute_validity(meta, lifecycle) if meta else None,
        "replaced_by": lifecycle.get("replaced_by", []),
        "repealed_by": lifecycle.get("repealed_by", []),
        "created_at": source.created_at.isoformat() if source.created_at else None,
        "updated_at": source.updated_at.isoformat() if source.updated_at else None,
    }


@router.get("/wiki/legal-doc-fields")
async def list_legal_doc_fields(_user: Employee = Depends(get_current_user)):
    """Allowed values for the 'lĩnh vực' metadata field."""
    from app.services.doc_metadata_service import FIELDS

    return {"fields": FIELDS}


@router.get("/wiki/legal-docs")
async def list_legal_docs(
    content_q: Optional[str] = Query(None, description="Full-text (nội dung) search"),
    db: AsyncSession = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    allowed, dept_filter = source_read_filter(user)
    kts = (await db.execute(
        select(KnowledgeType).order_by(KnowledgeType.sort_order, KnowledgeType.name)
    )).scalars().all()
    kt_list = [_kt_out(k) for k in kts]
    if not allowed:
        return {"items": [], "knowledge_types": kt_list}

    stmt = (
        select(Source)
        .options(load_only(*_LIST_COLUMNS), selectinload(Source.knowledge_type))
        .where(Source.status == "ready")
        .order_by(Source.created_at.desc())
    )
    if dept_filter is not None:
        stmt = stmt.where(dept_filter)
    if content_q and content_q.strip():
        stmt = stmt.where(Source.full_text.ilike(f"%{content_q.strip()}%"))
    sources = (await db.execute(stmt)).scalars().all()

    lifecycles = await load_lifecycle(
        db, [n for s in sources if (n := get_doc_meta(s).get("doc_number"))]
    )
    items = [
        _doc_out(s, lifecycle_for(lifecycles, get_doc_meta(s).get("doc_number")))
        for s in sources
    ]
    return {"items": items, "knowledge_types": kt_list}


@router.post("/wiki/legal-docs/backfill")
async def backfill_legal_docs(
    only_missing: bool = True,
    use_llm: bool = True,
    limit: int = Query(1000, ge=1, le=20000),
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:settings:manage"),
):
    """Enqueue metadata extraction for existing sources (and refresh legal relations)."""
    from app.worker import get_arq_pool

    await log_audit(
        db, _user, "backfill_doc_metadata", "settings", "global",
        reason=f"Backfill document metadata (only_missing={only_missing}, use_llm={use_llm}, limit={limit})",
    )
    await db.commit()
    pool = await get_arq_pool()
    job = await pool.enqueue_job("backfill_doc_metadata_task", only_missing, use_llm, limit)
    return {"job_id": job.job_id if job else None}


async def _resolve_source(db: AsyncSession, key: str) -> Optional[Source]:
    opts = (selectinload(Source.knowledge_type),)
    try:
        sid = uuid.UUID(key)
    except ValueError:
        sid = None
    if sid:
        return (await db.execute(select(Source).options(*opts).where(Source.id == sid))).scalar_one_or_none()
    return (await db.execute(
        select(Source).options(*opts)
        .where(Source.metadata_["doc"]["doc_slug"].astext == key)
        .order_by(Source.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()


@router.get("/wiki/legal-docs/{key}")
async def get_legal_doc(
    key: str,
    db: AsyncSession = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    from app.services.legal_service import split_legal_text_by_articles
    from app.services.permission_engine import can_access_document

    source = await _resolve_source(db, key)
    if not source:
        raise HTTPException(404, "Document not found")
    if not await can_access_document(db, user, source, "read"):
        raise HTTPException(403, "Access denied")

    meta = get_doc_meta(source)
    doc_number = meta.get("doc_number")
    lifecycles = await load_lifecycle(db, [doc_number] if doc_number else [])
    doc = _doc_out(source, lifecycle_for(lifecycles, doc_number))

    # Structure is re-parsed from full_text so it works for every document,
    # including ones never sent through the legal pipeline. Article slugs are
    # deterministic given doc_slug, so they match the per-Điều wiki pages.
    parsed = split_legal_text_by_articles(
        source.full_text or "", doc["title"], doc_slug=meta.get("doc_slug") or f"doc-{source.id.hex[:8]}",
    )

    # Wiki pages of this source the user can see (overview, per-Điều, summaries).
    page_stmt = select(
        WikiPage.slug, WikiPage.title, WikiPage.page_type, WikiPage.summary,
    ).where(
        WikiPage.source_ids.contains([source.id]),
        WikiPage.slug.notin_([wiki_service.INDEX_SLUG, wiki_service.LOG_SLUG, wiki_service.HOT_SLUG]),
    )
    wiki_filter = _build_wiki_scope_filter(user)
    if wiki_filter is not None:
        page_stmt = page_stmt.where(wiki_filter)
    pages: dict[str, dict] = {}
    for slug, title, page_type, summary in (await db.execute(page_stmt)).all():
        pages.setdefault(slug, {"slug": slug, "title": title, "page_type": page_type, "summary": summary or ""})

    articles = [
        {
            "num": a["num"],
            "heading": a["heading"],
            "title": a["title"],
            "content_md": a["content_md"],
            "chapter_num": a.get("chapter_num"),
            "chapter_title": a.get("chapter_title"),
            "wiki_slug": a["slug"] if a["slug"] in pages else None,
        }
        for a in parsed["articles"]
    ]

    download_url = file_url = None
    if source.minio_key:
        try:
            from app.services.auth_service import create_access_token
            token = create_access_token(str(user.id), user.role, user.name)
            download_url = f"/api/sources/{source.id}/file?download=1&token={token}"
            file_url = f"/api/sources/{source.id}/file?token={token}"
        except Exception as e:
            logger.warning(f"Failed to generate URLs for source {source.id}: {e}")

    overview = pages.get(meta.get("doc_slug") or "")
    summary_page = next((p for p in pages.values() if p["page_type"] == "summary"), None)
    return {
        **doc,
        "preamble": parsed["preamble"],
        "articles": articles,
        "relations": await load_doc_relations(db, source.id, doc_number),
        "wiki_pages": sorted(pages.values(), key=lambda p: p["slug"]),
        "overview_slug": overview["slug"] if overview else None,
        "summary": (summary_page or overview or {}).get("summary") or meta.get("official_title") or "",
        "download_url": download_url,
        "file_url": file_url,
    }
