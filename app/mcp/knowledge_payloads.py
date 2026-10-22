"""Permission-filtered metadata and compatible text/structured MCP knowledge results."""
from __future__ import annotations

import json
import re
import hashlib
from urllib.parse import quote, urlencode

from fastmcp.tools import ToolResult
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.database.models import Source, SourceDepartment, WikiPage
from app.services import mcp_auth_service
from app.services._wiki_search import _page_conditions
from app.services.source_quality import public_source_quality

DOC_FIELDS = (
    "doc_number", "doc_type", "issuing_authority", "official_title", "issued_date",
    "effective_date", "expiry_date", "field", "article_count", "doc_slug", "method", "extracted_at",
)

READ_DEFAULT_CHARS = 20_000
READ_MAX_CHARS = 50_000
READ_MAX_PAGES = 20


def _bounded_int(value, minimum, maximum, default):
    try:
        return max(minimum, min(maximum, int(value)))
    except (TypeError, ValueError, OverflowError):
        return default


def text_window(text, *, offset=0, max_chars=READ_DEFAULT_CHARS):
    """A lossless character window with an explicit, reusable continuation."""
    text = text or ''
    offset = _bounded_int(offset, 0, len(text), 0)
    max_chars = _bounded_int(max_chars, 1, READ_MAX_CHARS, READ_DEFAULT_CHARS)
    end = min(len(text), offset + max_chars)
    return {'content': text[offset:end], 'offset': offset, 'max_chars': max_chars,
            'content_offset': offset, 'content_length': len(text),
            'content_version': hashlib.sha256(text.encode('utf-8')).hexdigest(),
            'content_empty': not text.strip(),
            'total_chars': len(text), 'truncated': offset > 0 or end < len(text),
            'has_more': end < len(text), 'next_offset': end if end < len(text) else None}


def source_page_window(full_text, page_offsets, pages, *, offset=0, char_offset=0,
                       max_chars=READ_DEFAULT_CHARS, limit=READ_MAX_PAGES):
    """Page and character bounded verbatim reads, including empty pages.

    Intersect intervals with the actual page count before expanding a request;
    even ``1-999999999`` cannot allocate an unbounded integer range.
    ``offset`` indexes the requested existing pages; ``char_offset`` continues
    inside that page. Both values must be replayed with the same page request.
    """
    from app.services.source_outline import _page_bounds

    full_text, page_offsets = full_text or '', list(page_offsets or [])
    intervals = []
    for part in str(pages or '').split(','):
        match = re.fullmatch(r'\s*(\d+)\s*(?:-\s*(\d+)\s*)?', part)
        if match:
            lo = int(match[1])
            hi = int(match[2] or match[1])
            if 1 <= lo <= hi:
                intervals.append((lo, min(hi, len(page_offsets))))
    requested = sorted({p for lo, hi in intervals for p in range(lo, hi + 1)})
    offset = _bounded_int(offset, 0, len(requested), 0)
    char_offset = _bounded_int(char_offset, 0, len(full_text), 0)
    max_chars = _bounded_int(max_chars, 1, READ_MAX_CHARS, READ_DEFAULT_CHARS)
    limit = _bounded_int(limit, 1, READ_MAX_PAGES, READ_MAX_PAGES)
    slices, remaining, cursor = [], max_chars, offset
    while cursor < len(requested) and len(slices) < limit and remaining > 0:
        page = requested[cursor]
        start, end = _page_bounds(full_text, page_offsets, page - 1)
        page_length = end - start
        at = min(char_offset, page_length) if cursor == offset else 0
        stop = min(page_length, at + remaining)
        content = full_text[start + at:start + stop]
        slices.append({'page': page, 'content': content, 'content_offset': at,
                       'content_length': page_length, 'total_chars': page_length,
                       'content_version': hashlib.sha256(full_text[start:end].encode('utf-8')).hexdigest(),
                       'content_empty': not full_text[start:end].strip(),
                       'content_truncated': at > 0 or stop < page_length})
        remaining -= len(content)
        if stop < page_length:
            char_offset = stop
            break
        cursor += 1
        char_offset = 0
    more = cursor < len(requested)
    return {'pages': slices, 'truncated': offset > 0 or more or any(p['content_truncated'] for p in slices),
            'valid_range': bool(intervals),
            'pagination': {'offset': offset, 'limit': limit, 'max_chars': max_chars,
                           'total_pages': len(requested), 'has_more': more,
                           'next_offset': cursor if more else None,
                           'next_char_offset': char_offset if more else None}}


def _id(value):
    return str(value) if value is not None else None


def _iso(value):
    return value.isoformat() if value is not None else None


def _base_url():
    from app.config import settings
    return (settings.portal_base_url or "").rstrip("/")


def page_url(page):
    url = f"{_base_url()}/wiki/{quote(page.slug, safe='/')}"
    scope_type = getattr(page, "scope_type", None) or "global"
    if scope_type != "global":
        url += "?" + urlencode({"scopeType": scope_type, "scopeId": _id(getattr(page, "scope_id", None)) or ""})
    return url


def source_metadata(source):
    """Only public document attributes; never serialize the opaque metadata blob."""
    doc = (getattr(source, "metadata_", None) or {}).get("doc") or {}
    kt = getattr(source, "knowledge_type", None)
    manager = getattr(source, "managing_department", None)
    contributor = getattr(source, "contributor", None)
    depts = getattr(source, "departments", None) or []
    offsets = getattr(source, "page_offsets", None) or []
    return {
        "id": str(source.id), "title": source.title or source.file_name or str(source.id),
        "source_type": getattr(source, "source_type", None),
        "file_name": getattr(source, "file_name", None), "file_size": getattr(source, "file_size", None),
        "original_url": getattr(source, "url", None), "url": f"{_base_url()}/wiki/source/{source.id}",
        "status": getattr(source, "status", None), "progress": getattr(source, "progress", None),
        "wiki_status": getattr(source, "wiki_status", None), "chunk_status": getattr(source, "chunk_status", None),
        "wiki_progress": getattr(source, "wiki_progress", None), "chunk_progress": getattr(source, "chunk_progress", None),
        "processing_quality": public_source_quality(source),
        "page_count": len(offsets) if offsets else (1 if getattr(source, "full_text", None) else 0),
        "extracted_token_count": getattr(source, "extracted_token_count", None),
        "knowledge_type_id": _id(getattr(source, "knowledge_type_id", None)),
        "knowledge_type_name": getattr(kt, "name", None), "knowledge_type_slug": getattr(kt, "slug", None),
        "scope_type": getattr(source, "scope_type", None) or "global", "scope_id": _id(getattr(source, "scope_id", None)),
        "security_label": getattr(source, "security_label", None),
        "department_ids": [str(d.department_id) for d in depts],
        "department_names": [getattr(getattr(d, "department", None), "name", None) for d in depts],
        "managing_department_id": _id(getattr(source, "managing_department_id", None)),
        "managing_department_name": getattr(manager, "name", None),
        "contributed_by_employee_id": _id(getattr(source, "contributed_by_employee_id", None)),
        "contributed_by_name": getattr(contributor, "name", None),
        "doc_meta": {key: doc.get(key) for key in DOC_FIELDS},
        "created_at": _iso(getattr(source, "created_at", None)), "updated_at": _iso(getattr(source, "updated_at", None)),
    }


def page_metadata(page, sources, *, full_summary=True):
    summary = getattr(page, "summary", None) or ""
    return {
        "id": str(page.id), "slug": page.slug, "title": page.title or page.slug,
        "page_type": getattr(page, "page_type", None), "status": getattr(page, "status", None),
        "origin_tag": getattr(page, "origin_tag", None), "orphaned": bool(getattr(page, "orphaned", False)),
        "summary": summary if full_summary else summary[:300],
        "summary_truncated": not full_summary and len(summary) > 300, "summary_length": len(summary),
        "scope_type": getattr(page, "scope_type", None) or "global", "scope_id": _id(getattr(page, "scope_id", None)),
        "knowledge_type_slugs": list(getattr(page, "knowledge_type_slugs", None) or []),
        "source_ids": [str(s) for s in (getattr(page, "source_ids", None) or [])], "sources": sources,
        "version": getattr(page, "version", None), "created_at": _iso(getattr(page, "created_at", None)),
        "updated_at": _iso(getattr(page, "updated_at", None)), "url": page_url(page),
    }


def page_citation(meta, snippet):
    return {"id": meta["id"], "kind": "wiki", "title": meta["title"], "url": meta["url"],
            "snippet": snippet[:2400], "wiki_slug": meta["slug"], "origin_tag": meta["origin_tag"],
            "scope_type": meta["scope_type"], "scope_id": meta["scope_id"], "source_ids": meta["source_ids"]}


def source_citation(meta, snippet="", page=None):
    return {"id": meta["id"], "kind": "source", "title": meta["title"], "url": meta["url"],
            "snippet": snippet[:2400], "page": page, "doc_meta": meta["doc_meta"]}


def knowledge_result(text, *, status="ok", **data):
    data.setdefault("sources", [])
    return ToolResult(content=text, structured_content={"schema_version": 1, "status": status, **data})


def metadata_markdown(meta):
    return "## Metadata\n```json\n" + json.dumps(meta, ensure_ascii=False, indent=2) + "\n```"


def personal_page_clause(view):
    private = WikiPage.scope_type != "personal"
    if view.employee_id is not None:
        private = or_(private, WikiPage.scope_id == view.employee_id)
    return private


def readable_pages(view):
    conditions = _page_conditions(
        allowed_kt_slugs=view.allowed_knowledge_types, department_ids=view.department_ids,
        all_scopes=view.is_admin, clearance=view.clearance_level,
        page_filter=mcp_auth_service.page_source_clause(view), personal_owner_id=view.employee_id,
    )
    # Source-less personal pages must also remain private, including for admins.
    return select(WikiPage).where(*conditions, personal_page_clause(view))


async def find_pages(db, view, *, slug=None, page_id=None, scope_type=None, scope_id=None):
    stmt = readable_pages(view)
    if page_id is not None:
        stmt = stmt.where(WikiPage.id == page_id)
    if slug:
        stmt = stmt.where(WikiPage.slug == slug)
    if scope_type:
        stmt = stmt.where(WikiPage.scope_type == scope_type)
        stmt = stmt.where(WikiPage.scope_id == scope_id) if scope_id else stmt.where(WikiPage.scope_id.is_(None))
    return list((await db.execute(stmt.order_by(WikiPage.created_at, WikiPage.id).limit(51))).scalars().all())


def source_options():
    return (
        selectinload(Source.knowledge_type), selectinload(Source.managing_department),
        selectinload(Source.contributor), selectinload(Source.departments).selectinload(SourceDepartment.department),
    )


async def load_sources(db, view, source_ids):
    if not source_ids:
        return []
    stmt = mcp_auth_service.apply_scope_filter(select(Source).where(Source.id.in_(list(source_ids))), view)
    return list((await db.execute(stmt.options(*source_options()))).scalars().all())


async def page_metadata_batch(db, view, pages, *, full_summary=False):
    ids = {sid for p in pages for sid in (getattr(p, "source_ids", None) or [])}
    sources = {str(s.id): source_metadata(s) for s in await load_sources(db, view, ids)}
    return [page_metadata(p, [sources[str(s)] for s in (p.source_ids or []) if str(s) in sources],
                          full_summary=full_summary) for p in pages]


async def search_metadata(db, view, ranked):
    pages = [hit["page"] for kind, _, hit in ranked if kind == "wiki"]
    source_ids = {sid for p in pages for sid in (p.source_ids or [])}
    source_ids.update(hit["source"].id for kind, _, hit in ranked if kind == "source")
    sources = {str(s.id): source_metadata(s) for s in await load_sources(db, view, source_ids)}
    results, citations = [], []
    for kind, score, hit in ranked:
        if kind == "wiki":
            page = hit["page"]
            meta = page_metadata(page, [sources[str(s)] for s in (page.source_ids or []) if str(s) in sources], full_summary=False)
            excerpt = hit.get("chunk_text") or meta["summary"]
            results.append({"kind": "wiki", "score": float(score), "page": meta,
                            "matched_content": excerpt[:2400], "matched_content_truncated": len(excerpt)>2400,
                            "heading_path": hit.get("heading_path")})
            citations.append(page_citation(meta, excerpt[:2400]))
        else:
            source = hit["source"]
            meta = sources.get(str(source.id))
            if meta is None:
                continue
            chunk = hit.get("chunk")
            excerpt = getattr(chunk, "text", None) or ""
            location = {key: getattr(chunk,key,None) for key in ("chunk_index","page_number","start_char","end_char")}
            location["page_end"] = getattr(chunk, "page_end", None) or location["page_number"]
            location["chunk_index_end"] = hit.get("chunk_index_end", location["chunk_index"])
            results.append({"kind": "source", "score": float(score), "source": meta, "chunk": location,
                            "matched_content": excerpt[:2400], "matched_content_truncated": len(excerpt)>2400})
            citations.append(source_citation(meta, excerpt[:2400], location["page_number"]))
    return results, citations
