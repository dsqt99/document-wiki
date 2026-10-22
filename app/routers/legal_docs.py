"""Legal document browsing: fields, list, metadata backfill and detail (05b §8.3)."""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.database.models import Employee, KnowledgeType, Source, SourceDepartment, WikiPage
from app.routers.wiki import _build_wiki_scope_filter
from app.services import doc_metadata_service, legal_service, wiki_service
from app.services.audit_service import log_audit
from app.services.auth_service import create_source_file_token, get_current_user, require_permission

logger = logging.getLogger(__name__)

router = APIRouter()


def _iso(v) -> Optional[str]:
    return v.isoformat() if v is not None and hasattr(v, "isoformat") else None


def _with_relations(stmt):
    return stmt.options(
        selectinload(Source.knowledge_type),
        selectinload(Source.departments).selectinload(SourceDepartment.department),
        selectinload(Source.contributor),
    )


def _meta(source) -> dict:
    try:
        return dict(doc_metadata_service.get_doc_meta(source) or {})
    except Exception:  # noqa: BLE001
        return {}


def _doc_slug(source, meta: dict) -> str:
    return meta.get("doc_slug") or f"doc-{source.id.hex[:8]}"


def _item(source, lifecycles: dict) -> dict:
    meta = _meta(source)
    life = doc_metadata_service.lifecycle_for(lifecycles, meta.get("doc_number")) if meta else {}
    kt = getattr(source, "knowledge_type", None)
    depts = []
    for link in getattr(source, "departments", None) or []:
        dep = getattr(link, "department", None)
        if dep is not None:
            depts.append({"id": str(dep.id), "name": dep.name})
    depts.sort(key=lambda d: d["name"] or "")
    return {
        "id": str(source.id),
        "title": source.title or source.file_name or "",
        "file_name": source.file_name,
        "knowledge_type": (
            {"id": str(kt.id), "name": kt.name, "slug": kt.slug, "color": kt.color} if kt is not None else None
        ),
        "scope_type": source.scope_type or "global",
        "departments": depts,
        "status": source.status,
        "has_file": bool(source.minio_key),
        "url": source.url,
        "doc_slug": _doc_slug(source, meta),
        "meta": meta or None,
        "validity": doc_metadata_service.compute_validity(meta, life) if meta else None,
        "replaced_by": list(life.get("replaced_by") or []),
        "repealed_by": list(life.get("repealed_by") or []),
        "created_at": _iso(source.created_at),
        "updated_at": _iso(source.updated_at),
    }


@router.get("/wiki/legal-doc-fields")
async def legal_doc_fields(user: Employee = Depends(get_current_user)):
    return {"fields": doc_metadata_service.FIELDS}


@router.get("/wiki/legal-docs")
async def list_legal_docs(
    content_q: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    from app.routers import sources as sources_router

    kts = (await db.execute(
        select(KnowledgeType).order_by(KnowledgeType.sort_order, KnowledgeType.name)
    )).scalars().all()
    knowledge_types = [
        {"id": str(k.id), "slug": k.slug, "name": k.name, "color": k.color}
        for k in kts
    ]
    try:
        allowed, clause = sources_router.source_read_filter(user)
    except HTTPException:
        allowed, clause = False, None
    if not allowed:
        return {"items": [], "knowledge_types": knowledge_types}

    stmt = _with_relations(select(Source).where(Source.status == "ready")).order_by(Source.created_at.desc())
    if clause is not None:
        stmt = stmt.where(clause)
    if content_q and content_q.strip():
        stmt = stmt.where(Source.full_text.ilike(f"%{content_q.strip()}%"))
    sources = list((await db.execute(stmt)).scalars().all())
    numbers = [m.get("doc_number") for m in (_meta(s) for s in sources) if m.get("doc_number")]
    lifecycles = await doc_metadata_service.load_lifecycle(db, numbers) if numbers else {}
    return {"items": [_item(s, lifecycles) for s in sources], "knowledge_types": knowledge_types}


@router.post("/wiki/legal-docs/backfill")
async def backfill_legal_docs(
    only_missing: bool = True,
    use_llm: bool = True,
    limit: int = Query(1000, ge=1, le=20000),
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("org:settings:manage"),
):
    from app.routers import sources as sources_router

    await log_audit(db, user, "backfill_doc_metadata", "settings", "global",
                    reason=f"only_missing={only_missing} use_llm={use_llm} limit={limit}")
    await db.commit()
    job_id = None
    try:
        pool = await sources_router.get_arq_pool()
        job = await pool.enqueue_job("backfill_doc_metadata_task", only_missing, use_llm, limit)
        job_id = str(job.job_id) if job is not None and getattr(job, "job_id", None) else None
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not enqueue backfill_doc_metadata_task: %s", e)
    return {"job_id": job_id}


async def _find_source(db, key: str) -> Optional[Source]:
    try:
        sid = uuid.UUID(key)
    except (ValueError, TypeError):
        sid = None
    if sid is not None:
        src = (await db.execute(_with_relations(select(Source).where(Source.id == sid)))).scalar_one_or_none()
        if src is not None:
            return src
    doc_key = doc_metadata_service.METADATA_KEY
    stmt = _with_relations(
        select(Source).where(Source.metadata_[doc_key]["doc_slug"].astext == key)
    ).order_by(Source.created_at.desc()).limit(1)
    src = (await db.execute(stmt)).scalars().first()
    if src is None and key.startswith("doc-") and len(key) == 12:
        prefix = key[4:]
        stmt = _with_relations(
            select(Source).where(func.replace(func.cast(Source.id, _text_type()), "-", "").like(f"{prefix}%"))
        ).order_by(Source.created_at.desc()).limit(1)
        src = (await db.execute(stmt)).scalars().first()
    return src


VERBATIM_ARTICLE_MARKER = "> **Căn cứ pháp lý**"
PREAMBLE_HEADING = "## Căn cứ ban hành & Phần mở đầu"
TOC_HEADING = "\n## Danh mục các Điều"


def _article_body(page, edited: bool) -> Optional[str]:
    """Article text kept on its wiki page (citation blockquote stripped), so OCR fixes show in "Toàn văn"."""
    content = (getattr(page, "content_md", None) or "").replace("\r\n", "\n").strip()
    if content.startswith(VERBATIM_ARTICLE_MARKER):
        lines = content.split("\n")
        i = 0
        while i < len(lines) and lines[i].startswith(">"):
            i += 1
        return "\n".join(lines[i:]).strip()
    return content if edited and content else None


def _end_section_body(page, edited: bool) -> Optional[str]:
    content = (getattr(page, "content_md", None) or "").replace("\r\n", "\n").strip()
    marker = re.match(r"<!--\s*cahy:legal-endmatter kind=(?:appendix|notes)\s*-->", content)
    if not marker:
        return content if edited and content else None
    lines = content[marker.end():].lstrip().split("\n")
    if lines and lines[0].startswith("> **Toàn văn văn bản**:"):
        lines = lines[1:]
    return "\n".join(lines).strip()


def _end_section_page(by_slug, slug, source_id):
    from app.services.wiki_origin_service import compatible
    for suffix in ("", "-extracted", f"-extracted-{str(source_id)[:8]}"):
        page = by_slug.get((slug or "")[:300 - len(suffix)] + suffix)
        if page is not None and compatible(page, "extracted", source_id):
            return page
    return None


def _fulltext_article_parts(content: Optional[str], heading: Optional[str]) -> tuple[str, str]:
    """Render the current article heading once, preserving corrections and all body text."""
    from app.services.legal_hierarchy_parser import _match_article, strip_markup

    text = (content or "").strip()
    first, _, rest = text.partition("\n")
    current_heading = strip_markup(first)
    current = _match_article(current_heading)
    expected = _match_article(strip_markup(heading or ""))
    if current and expected and current.group(1).lower() == expected.group(1).lower():
        return current_heading, rest.strip()
    return heading or "", text


def _overview_preamble(page) -> Optional[str]:
    content = (getattr(page, "content_md", None) or "").replace("\r\n", "\n")
    start = content.find(PREAMBLE_HEADING)
    if start < 0:
        return None
    body = content[start + len(PREAMBLE_HEADING):]
    ends = [pos for heading in (TOC_HEADING, "\n## Phụ lục & Chú thích") if (pos := body.find(heading)) >= 0]
    return (body[:min(ends)] if ends else body).strip()


class _NoProgress:
    async def update(self, progress: int, message: str) -> None:
        return None


def _text_type():
    from sqlalchemy import Text

    return Text


def _file_token(user, source) -> Optional[str]:
    try:
        return create_source_file_token(str(user.id), str(source.id), session_claims=getattr(user, "_wiki_session_claims", None))
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not create file token for %s: %s", source.id, e)
        return None


@router.get("/wiki/legal-docs/{key}")
async def get_legal_doc(key: str, db: AsyncSession = Depends(get_db), user: Employee = Depends(get_current_user)):
    from app.services import permission_engine

    source = await _find_source(db, key)
    if source is None:
        raise HTTPException(404, "Document not found")
    if not await permission_engine.can_access_document(db, user, source, "read"):
        raise HTTPException(403, "Access denied")

    meta = _meta(source)
    numbers = [meta["doc_number"]] if meta.get("doc_number") else []
    lifecycles = await doc_metadata_service.load_lifecycle(db, numbers) if numbers else {}
    item = _item(source, lifecycles)
    doc_slug = item["doc_slug"]

    # Visible wiki pages built from this source.
    stmt = select(WikiPage).where(
        WikiPage.source_ids.any(source.id), WikiPage.slug.notin_(list(wiki_service.RESERVED_SLUGS))
    )
    scope_filter = _build_wiki_scope_filter(user)
    if scope_filter is not None:
        stmt = stmt.where(scope_filter)
    pages = list((await db.execute(stmt.order_by(WikiPage.slug))).scalars().all())
    seen: set[str] = set()
    wiki_pages: list[dict] = []
    by_slug: dict[str, Any] = {}
    for p in pages:
        if p.slug in seen:
            continue
        seen.add(p.slug)
        by_slug[p.slug] = p
        wiki_pages.append({"slug": p.slug, "title": p.title, "page_type": wiki_service._page_type_of(p),
                           "summary": p.summary or ""})

    try:
        parsed = legal_service.split_legal_text_by_articles(source.full_text or "", source.title or "", doc_slug)
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not split legal text for %s: %s", source.id, e)
        parsed = {"preamble": "", "articles": []}
    edited_ids = await wiki_service.human_edited_page_ids(db, [p.id for p in by_slug.values()])
    articles = []
    parsed_articles = parsed.get("articles") or []
    for index, a in enumerate(parsed_articles):
        slug = a.get("slug")
        page = by_slug.get(slug) if slug else None
        edited = page is not None and page.id in edited_ids
        body = _article_body(page, edited) if page is not None else None
        if body and not edited and parsed.get("end_sections") and index == len(parsed_articles) - 1:
            from app.services.legal_endmatter import find_end_sections
            legacy_tails = find_end_sections(body)
            if any(tail.title.casefold() == parsed["end_sections"][0]["title"].casefold() for tail in legacy_tails):
                # An old generated last-article page may still include the tail.
                # Fresh source parsing retains inline notes without guessing from
                # this isolated page, which lacks following-article context.
                body = a.get("content_md")
        heading, content = _fulltext_article_parts(
            body if body is not None else a.get("content_md"), a.get("heading"),
        )
        articles.append({
            "num": a.get("num"),
            "heading": heading,
            "title": a.get("title"),
            "content_md": content,
            "chapter_num": a.get("chapter_num"),
            "chapter_title": a.get("chapter_title"),
            "wiki_slug": slug if page is not None else None,
            "edited": edited,
        })

    end_sections = []
    for section in parsed.get("end_sections") or []:
        page = _end_section_page(by_slug, section.get("slug"), source.id)
        edited = page is not None and page.id in edited_ids
        body = _end_section_body(page, edited) if page is not None else None
        content = body if body is not None else section.get("content_md") or ""
        title = section.get("title") or ""
        from app.services.legal_hierarchy_parser import strip_markup
        first, _, rest = content.strip().partition("\n")
        if strip_markup(first).casefold() == title.casefold():
            content = rest.strip()
        end_sections.append({
            "kind": section.get("kind"), "number": section.get("number"),
            "title": title, "content_md": content,
            "wiki_slug": page.slug if page is not None else None, "edited": edited,
        })

    try:
        relations = await doc_metadata_service.load_doc_relations(db, source.id, meta.get("doc_number"))
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not load relations for %s: %s", source.id, e)
        relations = {"outgoing": [], "incoming": []}

    overview = by_slug.get(doc_slug)
    preamble = _overview_preamble(overview) if overview is not None else None
    if preamble is None:
        preamble = parsed.get("preamble") or ""
    summary_page = next((p for p in by_slug.values() if wiki_service._page_type_of(p) == "summary"), None)
    summary = (
        (summary_page.summary if summary_page is not None and summary_page.summary else None)
        or (overview.summary if overview is not None and overview.summary else None)
        or meta.get("official_title")
        or ""
    )

    download_url = preview_url = file_url = None
    if source.minio_key:
        token = _file_token(user, source)
        if token:
            base = f"/api/sources/{source.id}"
            download_url = f"{base}/file?download=true&token={token}"
            preview_url = f"{base}/preview?token={token}"
            file_url = f"{base}/file?token={token}"

    contributor = getattr(source, "contributor", None)
    item.update({
        "preamble": preamble,
        "preamble_edited": overview is not None and overview.id in edited_ids,
        "articles": articles,
        "end_sections": end_sections,
        "relations": relations,
        "wiki_pages": wiki_pages,
        "overview_slug": doc_slug if overview is not None else None,
        "summary": summary,
        "download_url": download_url,
        "preview_url": preview_url,
        "file_url": file_url,
        "file_size": source.file_size,
        "source_type": source.source_type or ("url" if source.url else "file"),
        "contributed_by_name": getattr(contributor, "name", None) if contributor is not None else None,
    })
    return item


@router.post("/wiki/legal-docs/{key}/pages")
async def create_legal_doc_pages(
    key: str, db: AsyncSession = Depends(get_db), user: Employee = Depends(get_current_user)
):
    """Split the document into an overview page and one verbatim page per Điều so each can be corrected
    by hand (OCR fixes). Pages someone already edited are kept; the wiki status is left unchanged."""
    from app.routers.wiki import _has_wiki_write_all
    from app.services import permission_engine
    from app.utils.progress import WIKI_ACTIVE

    if not _has_wiki_write_all(user):
        raise HTTPException(403, "Requires wiki:write:all permission")
    source = await _find_source(db, key)
    if source is None:
        raise HTTPException(404, "Document not found")
    if not await permission_engine.can_access_document(db, user, source, "read"):
        raise HTTPException(403, "Access denied")
    if (source.wiki_status or "pending") in WIKI_ACTIVE:
        raise HTTPException(409, "Văn bản đang được xử lý, thử lại sau khi xử lý xong")
    if not (source.full_text or "").strip():
        raise HTTPException(400, "Văn bản chưa có nội dung trích xuất")

    result = await legal_service.finalize_legal_source(
        db, source, _NoProgress(), final=False, refresh_metadata=False
    )
    await log_audit(db, user, "create", "wiki_page", source.id, reason="legal doc pages for manual correction")
    await db.commit()
    doc_slug = _doc_slug(source, _meta(source))
    parsed = legal_service.split_legal_text_by_articles(source.full_text or "", source.title or "", doc_slug)
    return {
        "doc_slug": doc_slug,
        "overview_slug": result.get("overview_slug", doc_slug),
        "article_slugs": result.get("article_slugs", [a.get("slug") for a in parsed.get("articles") or []]),
        "end_section_slugs": result.get("end_section_slugs", [s.get("slug") for s in parsed.get("end_sections") or []]),
        "articles": result.get("articles", 0),
    }
