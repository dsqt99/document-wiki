"""Wiki pages, search, index/log/hot, graph and lint endpoints (05b §4, §5)."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, any_, exists, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.database import get_db
from app.database.models import (
    Department,
    Employee,
    LegalRelation,
    LegalUnit,
    Source,
    WikiLink,
    WikiPage,
    WikiPageRevision,
)
from app.services import permission_engine, wiki_chunk_service, wiki_service
from app.services.audit_service import log_audit
from app.services.auth_service import get_current_user, require_permission

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_CONTENT_CHARS = 50_000
PAGE_STATUSES = ("seed", "growing", "mature", "evergreen")
HOT_PLACEHOLDER = (
    "*Bản tin nóng chưa được khởi tạo cho phạm vi này. "
    "Nội dung sẽ được tự động tạo sau lần nạp tài liệu tiếp theo.*"
)


# ---------------------------------------------------------------------------
# Permission helpers (§4)
# ---------------------------------------------------------------------------


def _is_admin(user) -> bool:
    return getattr(user, "role", None) == "admin" or getattr(user, "global_role", None) == "admin"


def _perms(user) -> set:
    return set(permission_engine._get_user_permissions(user))


def _dept_ids(user) -> list:
    return list(permission_engine._user_department_ids(user))


def _dept_str_set(user) -> set[str]:
    return {str(d) for d in _dept_ids(user)}


def _has_wiki_write_all(user) -> bool:
    return _is_admin(user) or "wiki:write:all" in _perms(user)


def _has_wiki_read_all(user) -> bool:
    return _is_admin(user) or "wiki:read:all" in _perms(user)


def _build_wiki_scope_filter(user):
    if _is_admin(user):
        return None
    level = permission_engine.get_scope_level(_perms(user), "wiki", "read")
    if level == "all":
        return None
    if level == "own_dept":
        depts = _dept_ids(user)
        if depts:
            return or_(
                WikiPage.scope_type == "global",
                and_(WikiPage.scope_type == "department", WikiPage.scope_id.in_(depts)),
            )
        return WikiPage.scope_type == "global"
    return false()


def page_source_read_clause(user):
    """Hide pages built from any source document the user cannot read."""
    if _is_admin(user):
        return None
    try:
        from app.routers import sources as sources_router

        _allowed, clause = sources_router.source_read_filter(user)
    except HTTPException:
        return func.coalesce(func.cardinality(WikiPage.source_ids), 0) == 0
    if clause is None:
        return None
    return ~exists(select(1).where(Source.id == any_(WikiPage.source_ids), ~clause))


def _page_read_filter(user):
    if _is_admin(user):
        return None
    clauses = [c for c in (_build_wiki_scope_filter(user), page_source_read_clause(user)) if c is not None]
    if not clauses:
        return None
    return clauses[0] if len(clauses) == 1 else and_(*clauses)


def _can_propose(user, page) -> bool:
    if _is_admin(user):
        return True
    perms = _perms(user)
    scope_type = getattr(page, "scope_type", None) or "global"
    scope_id = getattr(page, "scope_id", None)
    if scope_type == "department" and scope_id is not None:
        if "wiki:write:all" in perms:
            return True
        return "wiki:write:own_dept" in perms and str(scope_id) in _dept_str_set(user)
    return permission_engine.has_permission(perms, "wiki", "write", "any")


def _can_propose_scope(user, scope_type: Optional[str], scope_id) -> bool:
    class _Scope:
        pass

    s = _Scope()
    s.scope_type = scope_type or "global"
    s.scope_id = scope_id
    return _can_propose(user, s)


def _can_review(user) -> bool:
    return _has_wiki_write_all(user)


async def _page_readable(db, user, page_id) -> bool:
    clause = page_source_read_clause(user)
    if clause is None:
        return True
    row = (await db.execute(select(WikiPage.id).where(WikiPage.id == page_id, clause).limit(1))).first()
    return row is not None


async def _can_review_draft(db, user, draft) -> bool:
    if (getattr(draft, "draft_kind", None) or "edit") == "create":
        return _can_review(user)
    page_id = getattr(draft, "page_id", None)
    if page_id is None:
        return _is_admin(user)
    page = await db.get(WikiPage, page_id)
    if page is None:
        return _is_admin(user)
    if not await _page_readable(db, user, page_id):
        return False
    return _can_review(user)


async def _lookup_page(db, user, slug: str, scope_type: Optional[str] = None, scope_id=None):
    """Standard slug lookup used by the page endpoints."""
    pf = page_source_read_clause(user)
    if scope_type:
        page = await wiki_service.get_page_by_slug(db, slug, scope_type=scope_type, scope_id=scope_id,
                                                   page_filter=pf)
    else:
        page = await wiki_service.get_page_by_slug(db, slug, scope_type="global", page_filter=pf)
        if page is None:
            page = await wiki_service.get_page_by_slug_any_scope(db, slug, page_filter=pf)
    if page is None:
        raise HTTPException(404, f"Wiki page not found: {slug}")
    return page


def _check_department_access(user, scope_type: Optional[str], scope_id, message: str) -> None:
    if (scope_type or "global") != "department" or scope_id is None:
        return
    if _has_wiki_read_all(user):
        return
    if str(scope_id) not in _dept_str_set(user):
        raise HTTPException(403, message)


def _user_label(user) -> str:
    return getattr(user, "name", None) or getattr(user, "email", None) or str(getattr(user, "id", ""))


# ---------------------------------------------------------------------------
# Models (§5.1)
# ---------------------------------------------------------------------------


def _validate_slug(v: str) -> str:
    v = (v or "").strip()
    if not v or wiki_service.is_reserved_slug(v):
        raise ValueError("slug must be non-empty and not reserved")
    if any(ch.isspace() for ch in v):
        raise ValueError("slug must not contain whitespace")
    return v


def _validate_page_type(v: str) -> str:
    v = v or "concept"
    if v not in wiki_service.PAGE_TYPES:
        raise ValueError(f"page_type must be one of {sorted(wiki_service.PAGE_TYPES)}")
    return v


def _validate_scope_type(v: str) -> str:
    v = v or "global"
    if v not in ("global", "department"):
        raise ValueError("scope_type must be global or department")
    return v


def _validate_content(v: str) -> str:
    if v is None or not v.strip():
        raise ValueError("content_md must not be empty")
    if len(v) > MAX_CONTENT_CHARS:
        raise ValueError("content_md exceeds 50,000 character limit")
    return v


class WikiPageSummary(BaseModel):
    slug: str
    title: Optional[str] = None
    page_type: str = "concept"
    status: str = "seed"
    summary: str = ""
    knowledge_type_slugs: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    scope_type: str = "global"
    scope_id: Optional[str] = None
    scope_name: Optional[str] = None
    version: int = 1
    updated_at: str = ""


class WikiPageDetail(WikiPageSummary):
    content_md: str = ""
    backlinks: list[str] = Field(default_factory=list)
    outlinks: list[str] = Field(default_factory=list)
    orphaned: bool = False


class WikiScope(BaseModel):
    scope_type: str
    scope_id: Optional[str] = None
    name: str


class WikiDirectEditRequest(BaseModel):
    content_md: str
    change_note: Optional[str] = None

    @field_validator("content_md")
    @classmethod
    def _content(cls, v):
        if v is None or not v.strip():
            raise ValueError("content_md must not be empty")
        return v


class WikiDirectCreateRequest(BaseModel):
    slug: str
    title: str
    page_type: str = "concept"
    knowledge_type_slugs: list[str] = Field(default_factory=list)
    scope_type: str = "global"
    scope_id: Optional[uuid.UUID] = None
    content_md: str
    summary: str = ""

    _slug = field_validator("slug")(classmethod(lambda cls, v: _validate_slug(v)))
    _page_type = field_validator("page_type")(classmethod(lambda cls, v: _validate_page_type(v)))
    _scope_type = field_validator("scope_type")(classmethod(lambda cls, v: _validate_scope_type(v)))
    _content = field_validator("content_md")(classmethod(lambda cls, v: _validate_content(v)))


class WikiRevisionSummary(BaseModel):
    id: str
    version: int
    change_type: Optional[str] = None
    changed_by_name: Optional[str] = None
    change_note: Optional[str] = None
    created_at: str = ""


class StatusUpdate(BaseModel):
    status: str


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


def _iso(value) -> str:
    return value.isoformat() if value is not None and hasattr(value, "isoformat") else ""


async def _scope_names(db, pages) -> dict[str, str]:
    ids = {p.scope_id for p in pages if getattr(p, "scope_id", None) is not None}
    if not ids:
        return {}
    rows = (await db.execute(select(Department.id, Department.name).where(Department.id.in_(list(ids))))).all()
    return {str(i): n for i, n in rows}


def _summary(page, scope_names: Optional[dict] = None) -> WikiPageSummary:
    sid = getattr(page, "scope_id", None)
    return WikiPageSummary(
        slug=page.slug,
        title=page.title,
        page_type=wiki_service._page_type_of(page),
        status=page.status or "seed",
        summary=page.summary or "",
        knowledge_type_slugs=list(page.knowledge_type_slugs or []),
        source_ids=[str(s) for s in (page.source_ids or [])],
        scope_type=page.scope_type or "global",
        scope_id=str(sid) if sid is not None else None,
        scope_name=(scope_names or {}).get(str(sid)) if sid is not None else None,
        version=page.version or 1,
        updated_at=_iso(page.updated_at),
    )


async def _detail(db, page) -> WikiPageDetail:
    names = await _scope_names(db, [page])
    base = _summary(page, names).model_dump()
    scope_type = page.scope_type or "global"
    backlinks = await wiki_service.get_backlinks(db, page.slug, scope_type=scope_type, scope_id=page.scope_id)
    outlinks = await wiki_service.get_outlinks(db, page.slug, scope_type=scope_type, scope_id=page.scope_id)
    return WikiPageDetail(
        **base,
        content_md=page.content_md or "",
        backlinks=sorted(set(backlinks or [])),
        outlinks=sorted(set(outlinks or [])),
        orphaned=bool(page.orphaned),
    )


async def _index_chunks(db, page) -> None:
    try:
        await wiki_chunk_service.index_wiki_page_chunks(db, page)
    except Exception as e:  # noqa: BLE001
        logger.warning("Chunk indexing failed for %s: %s", getattr(page, "slug", "?"), e)


def _scope_clause(scope_type: Optional[str], scope_id):
    st = scope_type or "global"
    if st == "global":
        return and_(WikiPage.scope_type == "global", WikiPage.scope_id.is_(None))
    return and_(WikiPage.scope_type == st, WikiPage.scope_id == scope_id)


# ---------------------------------------------------------------------------
# Listing and search
# ---------------------------------------------------------------------------


@router.get("/wiki/pages", response_model=list[WikiPageSummary])
async def list_wiki_pages(
    page_type: Optional[str] = None,
    knowledge_type_slug: Optional[str] = None,
    source_id: Optional[uuid.UUID] = None,
    scope_type: Optional[str] = None,
    scope_id: Optional[uuid.UUID] = None,
    limit: int = Query(5000, ge=1, le=50000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("wiki:read"),
):
    stmt = select(WikiPage).where(WikiPage.slug.notin_(list(wiki_service.RESERVED_SLUGS)))
    rf = _page_read_filter(user)
    if rf is not None:
        stmt = stmt.where(rf)
    if scope_type:
        stmt = stmt.where(_scope_clause(scope_type, scope_id))
    if page_type:
        stmt = stmt.where(WikiPage.page_type == page_type)
    if knowledge_type_slug:
        stmt = stmt.where(WikiPage.knowledge_type_slugs.any(knowledge_type_slug))
    if source_id:
        stmt = stmt.where(WikiPage.source_ids.any(source_id))
    stmt = stmt.order_by(WikiPage.updated_at.desc()).offset(offset).limit(limit)
    pages = list((await db.execute(stmt)).scalars().all())
    names = await _scope_names(db, pages)
    return [_summary(p, names) for p in pages]


@router.get("/wiki/search", response_model=list[WikiPageSummary])
async def search_wiki(
    q: str = Query(..., min_length=1, max_length=500),
    limit: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("wiki:read"),
):
    try:
        import app.ai.registry as registry_mod

        registry = registry_mod.ProviderRegistry(db)
        emb = await registry.get_embedding(task="search_query")
        vec = await emb.embed(q[:4000])
    except Exception as e:  # noqa: BLE001
        logger.warning("wiki search embedding failed: %s", e)
        raise HTTPException(503, "Embedding model is not available")

    scope_filter = _build_wiki_scope_filter(user)
    hits = await wiki_service.search_pages_hybrid(
        db, vec, q, top_k=3 * limit,
        all_scopes=scope_filter is None,
        department_ids=_dept_ids(user),
        clearance=None if _is_admin(user) else getattr(user, "clearance_level", None),
        page_filter=page_source_read_clause(user),
    )
    slugs: list[str] = []
    ids: list = []
    for h in hits or []:
        page = h.get("page") if isinstance(h, dict) else (h[0] if isinstance(h, (tuple, list)) else h)
        pid = getattr(page, "id", None) if page is not None else (h.get("page_id") if isinstance(h, dict) else None)
        if pid is not None and pid not in ids:
            ids.append(pid)
        elif page is None and isinstance(h, dict) and h.get("slug") and h["slug"] not in slugs:
            slugs.append(h["slug"])
    if not ids and not slugs:
        return []
    stmt = select(WikiPage).where(or_(WikiPage.id.in_(ids) if ids else false(),
                                      WikiPage.slug.in_(slugs) if slugs else false()))
    rf = _page_read_filter(user)
    if rf is not None:
        stmt = stmt.where(rf)
    pages = list((await db.execute(stmt)).scalars().all())
    by_id = {p.id: p for p in pages}
    by_slug: dict[str, Any] = {}
    for p in pages:
        by_slug.setdefault(p.slug, p)
    ordered = [by_id[i] for i in ids if i in by_id] + [by_slug[s] for s in slugs if s in by_slug]
    ordered = ordered[:limit]
    names = await _scope_names(db, ordered)
    return [_summary(p, names) for p in ordered]


# ---------------------------------------------------------------------------
# Index, scopes, log
# ---------------------------------------------------------------------------


@router.get("/wiki/index")
async def get_wiki_index(
    scope_type: str = "global",
    scope_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("wiki:read"),
):
    _check_department_access(user, scope_type, scope_id, "Access denied — this belongs to another department")
    src = page_source_read_clause(user)
    if src is not None:
        content = await wiki_service.render_scoped_index(
            db, all_scopes=True,
            page_filter=and_(wiki_service._scope_filter(scope_type, scope_id), src),
        )
        return {"content_md": content}
    page = await wiki_service.get_page_by_slug(db, wiki_service.INDEX_SLUG, scope_type=scope_type,
                                               scope_id=scope_id)
    return {"content_md": (page.content_md or "") if page is not None else ""}


@router.get("/wiki/my-scopes", response_model=list[WikiScope])
async def get_my_scopes(db: AsyncSession = Depends(get_db), user: Employee = Depends(get_current_user)):
    scopes = [WikiScope(scope_type="global", scope_id=None, name="Global")]
    query = select(Department.id, Department.name).order_by(Department.name)
    rows = []
    if _is_admin(user):
        # System admins can browse every department scope, not only their own.
        rows = (await db.execute(query)).all()
    else:
        ids = _dept_ids(user)
        if ids:
            rows = (await db.execute(query.where(Department.id.in_(ids)))).all()
    if rows:
        scopes.extend(WikiScope(scope_type="department", scope_id=str(i), name=n) for i, n in rows)
    return scopes


@router.get("/wiki/log")
async def get_wiki_log(db: AsyncSession = Depends(get_db), user: Employee = require_permission("wiki:read")):
    page = await wiki_service.get_page_by_slug(db, wiki_service.LOG_SLUG, scope_type="global")
    return {"content_md": (page.content_md or "") if page is not None else ""}


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@router.post("/wiki/pages", response_model=WikiPageDetail, status_code=201)
async def create_wiki_page(
    body: WikiDirectCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    if not _has_wiki_write_all(user):
        raise HTTPException(403, "Requires wiki:write:all permission to create global/department wiki pages")
    existing = await wiki_service.get_page_by_slug(db, body.slug, scope_type=body.scope_type,
                                                   scope_id=body.scope_id)
    if existing is not None:
        raise HTTPException(
            409, f"Slug '{body.slug}' already exists in {body.scope_type}. Edit the existing page instead."
        )
    page = await wiki_service.apply_create(
        db, body.slug, body.title, body.page_type, body.content_md, body.summary,
        body.knowledge_type_slugs, [], scope_type=body.scope_type, scope_id=body.scope_id,
    )
    await log_audit(db, user, "create", "wiki_page", page.id, reason=f"direct create: {page.slug}")
    await wiki_service.regenerate_index(db, scope_type=body.scope_type, scope_id=body.scope_id)
    await wiki_service.append_log(db, f"Created page: {page.title} ({page.slug}) by {_user_label(user)}",
                                  scope_type=body.scope_type, scope_id=body.scope_id)
    await _index_chunks(db, page)
    await db.commit()
    return await _detail(db, page)


# ---------------------------------------------------------------------------
# Suffix routes (registered before the generic /wiki/pages/{slug:path})
# ---------------------------------------------------------------------------


@router.patch("/wiki/pages/{slug:path}/status")
async def update_wiki_page_status(
    slug: str,
    body: StatusUpdate,
    scope_type: Optional[str] = None,
    scope_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    if body.status not in PAGE_STATUSES:
        raise HTTPException(400, f"Invalid status. Must be one of: {', '.join(PAGE_STATUSES)}")
    if wiki_service.is_reserved_slug(slug):
        raise HTTPException(400, "Cannot update status of reserved pages")
    page = await _lookup_page(db, user, slug, scope_type, scope_id)
    if not _has_wiki_write_all(user):
        raise HTTPException(403, "Requires wiki:write:all permission")
    page.status = body.status
    await db.commit()
    return {"slug": page.slug, "status": page.status}


@router.get("/wiki/pages/{slug:path}/revisions", response_model=list[WikiRevisionSummary])
async def list_wiki_revisions(
    slug: str,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("wiki:read"),
):
    page = await wiki_service.get_page_by_slug_any_scope(db, slug, page_filter=_page_read_filter(user))
    if page is None:
        raise HTTPException(404, f"Wiki page not found: {slug}")
    rows = (await db.execute(
        select(WikiPageRevision, Employee.name)
        .outerjoin(Employee, Employee.id == WikiPageRevision.changed_by_id)
        .where(WikiPageRevision.page_id == page.id)
        .order_by(WikiPageRevision.version.desc())
        .limit(limit)
    )).all()
    return [
        WikiRevisionSummary(
            id=str(r.id), version=r.version, change_type=r.change_type, changed_by_name=name,
            change_note=r.change_note, created_at=_iso(r.created_at),
        )
        for r, name in rows
    ]


@router.post("/wiki/pages/{slug:path}/revisions/{version}/rollback", response_model=WikiPageDetail)
async def rollback_wiki_page(
    slug: str,
    version: int,
    db: AsyncSession = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    if not _is_admin(user):
        raise HTTPException(403, "Only admins can rollback wiki pages")
    page = await wiki_service.get_page_by_slug_any_scope(db, slug)
    if page is None:
        raise HTTPException(404, f"Wiki page not found: {slug}")
    try:
        page = await wiki_service.rollback_to_revision(db, page, version, user.id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    await log_audit(db, user, "update", "wiki_page", page.id, reason=f"rollback to v{version}: {slug}")
    await _index_chunks(db, page)
    await db.commit()
    return await _detail(db, page)


# ---------------------------------------------------------------------------
# Generic page routes
# ---------------------------------------------------------------------------


@router.get("/wiki/pages/{slug:path}", response_model=WikiPageDetail)
async def get_wiki_page(
    slug: str,
    scope_type: Optional[str] = None,
    scope_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("wiki:read"),
):
    page = await _lookup_page(db, user, slug, scope_type, scope_id)
    if not _is_admin(user) and page.slug not in wiki_service.RESERVED_SLUGS:
        from app.services.security_label import page_label_clause

        ok = (await db.execute(
            select(WikiPage.id).where(
                WikiPage.id == page.id, page_label_clause(getattr(user, "clearance_level", None))
            ).limit(1)
        )).first()
        if ok is None:
            raise HTTPException(404, f"Wiki page not found: {slug}")
    _check_department_access(user, page.scope_type, page.scope_id,
                             "Access denied — this page belongs to another department")
    return await _detail(db, page)


@router.put("/wiki/pages/{slug:path}", response_model=WikiPageDetail)
async def direct_edit_wiki_page(
    slug: str,
    body: WikiDirectEditRequest,
    scope_type: Optional[str] = None,
    scope_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    if wiki_service.is_reserved_slug(slug):
        raise HTTPException(400, "Cannot directly edit reserved pages")
    page = await _lookup_page(db, user, slug, scope_type, scope_id)
    if not _has_wiki_write_all(user):
        raise HTTPException(403, "Requires wiki:write:all permission to directly edit global/department wiki pages")
    page = await wiki_service.direct_edit_page(db, page, user.id, body.content_md, change_note=body.change_note)
    await log_audit(db, user, "update", "wiki_page", page.id, reason=f"direct edit: {page.slug}")
    st, sid = page.scope_type or "global", page.scope_id
    await wiki_service.regenerate_index(db, scope_type=st, scope_id=sid)
    await wiki_service.append_log(
        db, f"Edited page: {page.title} ({page.slug}) → v{page.version} by {_user_label(user)}",
        scope_type=st, scope_id=sid,
    )
    await _index_chunks(db, page)
    await db.commit()
    return await _detail(db, page)


@router.delete("/wiki/pages/{slug:path}")
async def delete_wiki_page(
    slug: str,
    scope_type: Optional[str] = None,
    scope_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("wiki:delete"),
):
    if wiki_service.is_reserved_slug(slug):
        raise HTTPException(400, "Cannot delete reserved pages")
    page = await _lookup_page(db, user, slug, scope_type, scope_id)
    roles = {getattr(user, "role", None), getattr(user, "global_role", None)}
    if not roles & {"admin", "super_admin"}:
        raise HTTPException(403, "Only admins can delete wiki pages")
    st, sid, title = page.scope_type or "global", page.scope_id, page.title
    await log_audit(db, user, "delete", "wiki_page", page.id, reason=f"delete: {slug}")
    await wiki_service.delete_page_cascade(db, page)
    await wiki_service.regenerate_index(db, scope_type=st, scope_id=sid)
    await wiki_service.append_log(db, f"Deleted page: {title} ({slug})", scope_type="global")
    await db.commit()
    return {"ok": True, "deleted_slug": slug}


@router.get("/wiki/orphaned", response_model=list[WikiPageSummary])
async def list_orphaned_pages(db: AsyncSession = Depends(get_db), user: Employee = Depends(get_current_user)):
    if not _is_admin(user):
        raise HTTPException(403, "Only admins can view orphaned pages")
    pages = list((await db.execute(
        select(WikiPage).where(WikiPage.orphaned.is_(True)).order_by(WikiPage.slug)
    )).scalars().all())
    names = await _scope_names(db, pages)
    return [_summary(p, names) for p in pages]


# ---------------------------------------------------------------------------
# Graph (§5.3)
# ---------------------------------------------------------------------------


def _enum_value(v) -> str:
    return getattr(v, "value", v)


def _edge(frm, to, type_, predicate, weight, evidence, **extra) -> dict:
    d = {"from": frm, "to": to, "type": type_, "label": predicate, "predicate": predicate,
         "weight": weight, "evidence": evidence}
    d.update(extra)
    return d


@router.get("/wiki/graph")
async def get_wiki_graph(
    slug: Optional[str] = None,
    depth: int = Query(1, ge=1, le=3),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    edge_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("wiki:read"),
):
    rf = None if _is_admin(user) else _page_read_filter(user)
    visible: Optional[set[str]] = None
    if rf is not None:
        visible = set((await db.execute(select(WikiPage.slug).where(rf))).scalars().all())

    if slug:
        if visible is not None and slug not in visible:
            raise HTTPException(404, f"Wiki page not found: {slug}")
        hood = await wiki_service.get_neighborhood(db, slug, depth=depth)
        nodes = list(hood.get("nodes") or [])
        edges = [
            _edge(e["from"], e["to"], "wikilink", "wikilink", 1.0, None)
            for e in (hood.get("edges") or [])
        ]
        if visible is not None:
            nodes = [n for n in nodes if n.get("slug") in visible]
            edges = [e for e in edges if e["from"] in visible and e["to"] in visible]
        return {"nodes": nodes, "edges": edges}

    base = [WikiPage.slug.notin_(list(wiki_service.RESERVED_SLUGS))]
    if rf is not None:
        base.append(rf)

    total = (await db.execute(select(func.count(WikiPage.id)).where(*base))).scalar() or 0
    node_rows = (await db.execute(
        select(
            WikiPage.slug, WikiPage.title, WikiPage.page_type, WikiPage.status, WikiPage.scope_type,
            WikiPage.scope_id, Department.name.label("scope_name"),
        )
        .outerjoin(Department, and_(WikiPage.scope_type == "department", Department.id == WikiPage.scope_id))
        .where(*base)
        .order_by(WikiPage.slug)
        .offset(offset)
        .limit(limit)
    )).all()
    nodes = [
        {
            "slug": r.slug, "title": r.title, "page_type": r.page_type, "status": r.status,
            "scope_type": r.scope_type or "global",
            "scope_id": str(r.scope_id) if r.scope_id is not None else None,
            "scope_name": r.scope_name,
        }
        for r in node_rows
    ]

    edges: list[dict] = []
    if offset == 0:
        kind = edge_type or "all"
        if kind in ("all", "wikilink"):
            rows = (await db.execute(
                select(WikiPage.slug.label("from_slug"), WikiLink.to_slug.label("to_slug"))
                .join(WikiLink, WikiLink.from_page_id == WikiPage.id)
                .where(*base)
            )).all()
            edges.extend(_edge(r.from_slug, r.to_slug, "wikilink", "wikilink", 1.0, None) for r in rows)
        if kind in ("all", "concept"):
            from app.models.concept_relation import ConceptRelation

            sp, tp = aliased(WikiPage), aliased(WikiPage)
            rows = (await db.execute(
                select(
                    sp.slug.label("from_slug"), tp.slug.label("to_slug"), ConceptRelation.predicate,
                    ConceptRelation.evidence, ConceptRelation.weight, ConceptRelation.source_concept,
                    ConceptRelation.target_concept,
                )
                .join(sp, sp.id == ConceptRelation.source_page_id)
                .join(tp, tp.id == ConceptRelation.target_page_id)
            )).all()
            edges.extend(
                _edge(r.from_slug, r.to_slug, "concept", r.predicate,
                      float(r.weight if r.weight is not None else 1.0), r.evidence,
                      source_concept=r.source_concept, target_concept=r.target_concept)
                for r in rows
            )
        if kind in ("all", "legal"):
            su, tu = aliased(LegalUnit), aliased(LegalUnit)
            sp, tp = aliased(WikiPage), aliased(WikiPage)
            rows = (await db.execute(
                select(
                    sp.slug.label("from_slug"), tp.slug.label("to_slug"), LegalRelation.relation_type,
                    LegalRelation.quote_context, LegalRelation.is_effective, LegalRelation.target_doc_number,
                )
                .join(su, su.id == LegalRelation.source_unit_id)
                .join(tu, tu.id == LegalRelation.target_unit_id)
                .join(sp, sp.id == su.wiki_page_id)
                .join(tp, tp.id == tu.wiki_page_id)
                .where(LegalRelation.is_effective.is_(True))
            )).all()
            for r in rows:
                if r.is_effective is False:
                    continue
                rt = _enum_value(r.relation_type)
                edges.append(_edge(r.from_slug, r.to_slug, "legal", rt, 1.2, r.quote_context,
                                   target_doc_number=r.target_doc_number))

    if visible is not None:
        edges = [e for e in edges if e["from"] in visible and e["to"] in visible]
    return {"nodes": nodes, "edges": edges, "total": total, "offset": offset,
            "has_more": offset + limit < total}


# ---------------------------------------------------------------------------
# Lint and hot cache
# ---------------------------------------------------------------------------


@router.get("/wiki/lint")
async def lint_wiki(
    scope_type: str = "global",
    scope_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("wiki:read"),
):
    _check_department_access(user, scope_type, scope_id, "Access denied — this belongs to another department")
    return await wiki_service.lint_wiki(db, scope_type=scope_type, scope_id=scope_id)


@router.get("/wiki/hot")
async def get_wiki_hot(
    scope_type: str = "global",
    scope_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("wiki:read"),
):
    _check_department_access(user, scope_type, scope_id, "Access denied — this belongs to another department")
    page = await wiki_service.get_page_by_slug(db, wiki_service.HOT_SLUG, scope_type=scope_type,
                                               scope_id=scope_id)
    if page is None or not (page.content_md or "").strip():
        return {"content_md": HOT_PLACEHOLDER}
    return {"content_md": page.content_md}


@router.post("/wiki/hot/rebuild")
async def rebuild_wiki_hot(
    scope_type: str = "global",
    scope_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    if not _has_wiki_write_all(user):
        raise HTTPException(403, "Requires wiki:write:all permission to edit global/department wiki pages")
    page = await wiki_service.regenerate_hot_cache(db, scope_type=scope_type, scope_id=scope_id)
    await db.commit()
    return {"ok": True, "content_md": (page.content_md or "") if page is not None else ""}
