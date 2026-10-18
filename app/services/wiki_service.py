"""Wiki core service: pages, links, scopes, index/log/hot pages, drafts and revisions.

Search functions (``search_pages_semantic``, ``search_pages_hybrid``,
``search_source_chunks_hybrid``, ``_lexical_plan``) live in ``_wiki_search`` and
are re-exported at the bottom of this module so callers and tests can address
them as ``wiki_service.<name>``.

Functions inside this module call each other through module globals (never via
captured references) so ``monkeypatch.setattr(wiki_service, ...)`` takes effect.
"""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from loguru import logger
from sqlalchemy import and_, any_, delete, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database.models import (
    Source,
    SourceDepartment,
    WikiLink,
    WikiPage,
    WikiPageDraft,
    WikiPageRevision,
)
from app.services import wiki_write_guard

INDEX_SLUG = "_index"
LOG_SLUG = "_log"
HOT_SLUG = "_hot"
RESERVED_SLUGS = frozenset({INDEX_SLUG, LOG_SLUG, HOT_SLUG})
PAGE_TYPES = frozenset({"entity", "concept", "source", "topic", "index", "log", "hot"})

INDEX_TITLE = "Wiki Index"
INDEX_SUMMARY = "Catalog of all wiki pages"
LOG_TITLE = "Wiki Log"
LOG_SUMMARY = "Chronological record of wiki changes"
HOT_TITLE = "Bản tin tri thức nóng"
HOT_SUMMARY = "Tổng hợp nhanh các trang cần chú ý"

_EMPTY_INDEX_NOTE = "_Chưa có trang wiki nào._"
_EMPTY_LOG_NOTE = "_Chưa có mục nhật ký nào._"
_CONTRADICTION_MARKER = "[!contradiction]"

_WIKILINK_RE = re.compile(r"\[\[([^\[\]|]+?)(?:\|([^\[\]]*))?\]\]")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class DraftConflictError(Exception):
    def __init__(self, current_version: int, base_version: int):
        self.current_version = current_version
        self.base_version = base_version
        super().__init__(
            f"Draft was based on v{base_version} but the page is now at v{current_version}; "
            "re-base the draft on the latest version before approving."
        )


class CreateDraftSlugConflict(Exception):
    def __init__(self, slug: str, scope_type: str, scope_id: Any = None):
        self.slug = slug
        self.scope_type = scope_type
        self.scope_id = scope_id
        where = scope_type if scope_id is None else f"{scope_type}:{scope_id}"
        super().__init__(
            f"Slug '{slug}' already exists in {where}. Choose a different final_slug "
            "or edit the existing page instead."
        )


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_uuid(value: Any) -> Optional[uuid.UUID]:
    if value is None or value == "":
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def is_reserved_slug(slug: Optional[str]) -> bool:
    return (slug or "") in RESERVED_SLUGS


async def _advisory_lock(session, key: str) -> None:
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": key})


def _page_type_of(page: Any) -> str:
    pt = getattr(page, "page_type", None)
    if isinstance(pt, str) and pt:
        return pt
    return "concept"


# ---------------------------------------------------------------------------
# Wikilinks
# ---------------------------------------------------------------------------


def extract_wikilinks(content_md: Optional[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for m in _WIKILINK_RE.finditer(content_md or ""):
        slug = m.group(1).strip()
        if slug and slug not in seen:
            seen.add(slug)
            out.append(slug)
    return out


async def refresh_links(session, from_page_id, from_slug: Optional[str], content_md: Optional[str]) -> None:
    await session.execute(delete(WikiLink).where(WikiLink.from_page_id == from_page_id))
    targets = [s for s in extract_wikilinks(content_md) if s != from_slug]
    if not targets:
        return
    stmt = pg_insert(WikiLink).values(
        [{"from_page_id": from_page_id, "to_slug": s} for s in targets]
    ).on_conflict_do_nothing()
    await session.execute(stmt)


async def get_backlinks(session, slug: str, scope_type: Optional[str] = None, scope_id=None) -> list[str]:
    stmt = (
        select(WikiPage.slug)
        .join(WikiLink, WikiLink.from_page_id == WikiPage.id)
        .where(WikiLink.to_slug == slug)
        .distinct()
    )
    if scope_type is not None:
        stmt = stmt.where(or_(_scope_filter(scope_type, scope_id), WikiPage.scope_type == "global"))
    rows = await session.execute(stmt)
    return list(rows.scalars().all())


async def get_outlinks(session, slug: str, scope_type: str = "global", scope_id=None) -> list[str]:
    stmt = (
        select(WikiLink.to_slug)
        .join(WikiPage, WikiLink.from_page_id == WikiPage.id)
        .where(WikiPage.slug == slug, _scope_filter(scope_type, scope_id))
    )
    rows = await session.execute(stmt)
    return list(rows.scalars().all())


async def get_neighborhood(session, slug: str, depth: int = 1) -> dict:
    depth = max(1, min(3, int(depth or 1)))
    visited: set[str] = {slug}
    frontier: set[str] = {slug}
    edges: set[tuple[str, str]] = set()
    for _ in range(depth):
        if not frontier:
            break
        out_rows = await session.execute(
            select(WikiPage.slug, WikiLink.to_slug)
            .join(WikiLink, WikiLink.from_page_id == WikiPage.id)
            .where(WikiPage.slug.in_(frontier))
        )
        in_rows = await session.execute(
            select(WikiPage.slug, WikiLink.to_slug)
            .join(WikiLink, WikiLink.from_page_id == WikiPage.id)
            .where(WikiLink.to_slug.in_(frontier))
        )
        nxt: set[str] = set()
        for a, b in list(out_rows.all()) + list(in_rows.all()):
            if a == b:
                continue
            edges.add((a, b))
            for s in (a, b):
                if s not in visited:
                    nxt.add(s)
        visited |= nxt
        frontier = nxt

    page_rows = await session.execute(
        select(WikiPage.slug, WikiPage.title, WikiPage.page_type).where(WikiPage.slug.in_(visited))
    )
    nodes: dict[str, dict] = {}
    for s, title, pt in page_rows.all():
        if s not in nodes:
            nodes[s] = {"slug": s, "title": title, "page_type": pt}
    return {
        "nodes": list(nodes.values()),
        "edges": [{"from": a, "to": b} for a, b in sorted(edges) if a in nodes and b in nodes],
    }


# ---------------------------------------------------------------------------
# Scope filters
# ---------------------------------------------------------------------------


def _scope_filter(scope_type: Optional[str] = "global", scope_id=None):
    st = scope_type or "global"
    sid = _as_uuid(scope_id)
    if sid is None:
        return and_(WikiPage.scope_type == st, WikiPage.scope_id.is_(None))
    return and_(WikiPage.scope_type == st, WikiPage.scope_id == sid)


def _identity_scope_filter(department_ids: Optional[Iterable] = None, project_ids: Optional[Iterable] = None):
    clauses = [WikiPage.scope_type == "global"]
    dept = [d for d in (_as_uuid(x) for x in (department_ids or [])) if d]
    proj = [p for p in (_as_uuid(x) for x in (project_ids or [])) if p]
    if dept:
        clauses.append(and_(WikiPage.scope_type == "department", WikiPage.scope_id.in_(dept)))
    if proj:
        clauses.append(and_(WikiPage.scope_type == "project", WikiPage.scope_id.in_(proj)))
    return or_(*clauses)


def inverse_scope(department_ids: Optional[Iterable] = None, project_ids: Optional[Iterable] = None):
    dept = [d for d in (_as_uuid(x) for x in (department_ids or [])) if d]
    proj = [p for p in (_as_uuid(x) for x in (project_ids or [])) if p]
    dept_clause = WikiPage.scope_type == "department"
    if dept:
        dept_clause = and_(dept_clause, or_(WikiPage.scope_id.is_(None), WikiPage.scope_id.notin_(dept)))
    proj_clause = WikiPage.scope_type == "project"
    if proj:
        proj_clause = and_(proj_clause, or_(WikiPage.scope_id.is_(None), WikiPage.scope_id.notin_(proj)))
    return or_(dept_clause, proj_clause)


async def resolve_wiki_scopes(session, source) -> list[tuple[str, Optional[uuid.UUID]]]:
    current = source
    try:
        sid = getattr(source, "id", None)
        if sid is not None:
            fresh = await session.get(Source, sid)
            if fresh is not None:
                current = fresh
    except Exception as e:  # pragma: no cover - defensive
        logger.debug(f"resolve_wiki_scopes: reload failed ({e}); using given object")

    scope_type = getattr(current, "scope_type", None) or "global"
    scope_id = getattr(current, "scope_id", None)
    if scope_type == "project" and scope_id is not None:
        return [("project", scope_id)]

    dept_ids: list = []
    try:
        rows = await session.execute(
            select(SourceDepartment.department_id).where(SourceDepartment.source_id == current.id)
        )
        dept_ids = list(rows.scalars().all())
    except Exception as e:
        logger.debug(f"resolve_wiki_scopes: department lookup failed ({e})")
    if dept_ids:
        return [("department", d) for d in dept_ids]
    if scope_type == "department" and scope_id is not None:
        return [("department", scope_id)]
    return [("global", None)]


# ---------------------------------------------------------------------------
# Reading pages
# ---------------------------------------------------------------------------


def _kt_ok(page, allowed_kt_slugs) -> bool:
    if allowed_kt_slugs is None:
        return True
    kts = list(getattr(page, "knowledge_type_slugs", None) or [])
    if not kts:
        return True
    return bool(set(kts) & set(allowed_kt_slugs))


def _apply_read_filters(stmt, slug: str, clearance, page_filter):
    if slug not in RESERVED_SLUGS:
        if clearance is not None:
            from app.services.security_label import page_label_clause

            stmt = stmt.where(page_label_clause(clearance))
        if page_filter is not None:
            stmt = stmt.where(page_filter)
    return stmt


async def get_page_by_slug(
    session,
    slug: str,
    allowed_kt_slugs: Optional[list[str]] = None,
    scope_type: str = "global",
    scope_id=None,
    clearance: Optional[str] = None,
    page_filter=None,
) -> Optional[WikiPage]:
    stmt = select(WikiPage).where(WikiPage.slug == slug, _scope_filter(scope_type, scope_id))
    stmt = _apply_read_filters(stmt, slug, clearance, page_filter).limit(1)
    page = (await session.execute(stmt)).scalars().first()
    if page is None or not _kt_ok(page, allowed_kt_slugs):
        return None
    return page


async def get_page_by_slug_any_scope(session, slug: str, clearance: Optional[str] = None, page_filter=None):
    stmt = select(WikiPage).where(WikiPage.slug == slug)
    stmt = _apply_read_filters(stmt, slug, clearance, page_filter)
    stmt = stmt.order_by((WikiPage.scope_type != "global"), WikiPage.created_at).limit(1)
    return (await session.execute(stmt)).scalars().first()


async def list_pages(
    session,
    page_type: Optional[str] = None,
    knowledge_type_slug: Optional[str] = None,
    allowed_kt_slugs: Optional[list[str]] = None,
    query: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    scope_type: str = "global",
    scope_id=None,
    department_ids: Optional[list] = None,
    project_ids: Optional[list] = None,
    all_scopes: bool = False,
    clearance: Optional[str] = None,
    page_filter=None,
) -> list[WikiPage]:
    stmt = select(WikiPage).where(WikiPage.slug.notin_(list(RESERVED_SLUGS)))
    if all_scopes:
        pass
    elif department_ids or project_ids:
        stmt = stmt.where(_identity_scope_filter(department_ids, project_ids))
    else:
        stmt = stmt.where(_scope_filter(scope_type, scope_id))
    if page_type:
        stmt = stmt.where(WikiPage.page_type == page_type)
    if knowledge_type_slug:
        stmt = stmt.where(WikiPage.knowledge_type_slugs.any(knowledge_type_slug))
    if allowed_kt_slugs is not None:
        stmt = stmt.where(
            or_(
                WikiPage.knowledge_type_slugs.overlap(list(allowed_kt_slugs)),
                func.coalesce(func.cardinality(WikiPage.knowledge_type_slugs), 0) == 0,
            )
        )
    if query:
        pat = f"%{query}%"
        stmt = stmt.where(
            or_(WikiPage.title.ilike(pat), WikiPage.slug.ilike(pat), WikiPage.content_md.ilike(pat))
        )
    if clearance is not None:
        from app.services.security_label import page_label_clause

        stmt = stmt.where(page_label_clause(clearance))
    if page_filter is not None:
        stmt = stmt.where(page_filter)
    stmt = stmt.order_by(WikiPage.updated_at.desc()).offset(max(0, offset)).limit(max(1, limit))
    return list((await session.execute(stmt)).scalars().all())


# ---------------------------------------------------------------------------
# Writing pages
# ---------------------------------------------------------------------------


def _revision(page_id, version: int, content_md: Optional[str], change_type: str,
              draft_id=None, changed_by_id=None, change_note: Optional[str] = None) -> WikiPageRevision:
    return WikiPageRevision(
        page_id=page_id,
        version=version,
        content_md=content_md,
        change_type=change_type,
        draft_id=draft_id,
        changed_by_id=changed_by_id,
        change_note=change_note,
    )


async def apply_create(
    session,
    slug: str,
    title: Optional[str],
    page_type: Optional[str],
    content_md: Optional[str],
    summary: Optional[str],
    knowledge_type_slugs: Optional[list[str]],
    source_ids: Optional[list],
    embedding=None,
    scope_type: str = "global",
    scope_id=None,
    status: str = "seed",
) -> WikiPage:
    # page_type is derived from the slug on the model; the argument is accepted
    # for API compatibility with callers that pass it.
    page = WikiPage(
        id=uuid.uuid4(),
        slug=slug,
        title=title,
        content_md=content_md or "",
        summary=summary,
        knowledge_type_slugs=list(knowledge_type_slugs or []),
        source_ids=list(source_ids or []),
        scope_type=scope_type or "global",
        scope_id=_as_uuid(scope_id),
        status=status or "seed",
        version=1,
    )
    session.add(page)
    await session.flush()
    await refresh_links(session, page.id, slug, page.content_md)
    session.add(_revision(page.id, 1, page.content_md, "agent_compile"))
    return page


async def apply_update(
    session,
    slug: str,
    new_content_md: str,
    summary: Optional[str] = None,
    title: Optional[str] = None,
    add_knowledge_type_slug: Optional[str] = None,
    add_source_id=None,
    embedding=None,
    scope_type: str = "global",
    scope_id=None,
    status: Optional[str] = None,
    guard: bool = True,
) -> Optional[WikiPage]:
    page = await get_page_by_slug(session, slug, scope_type=scope_type, scope_id=scope_id)
    if page is None:
        return None
    if guard:
        reason = wiki_write_guard.check_machine_rewrite(page.content_md or "", new_content_md or "")
        if reason:
            logger.warning(f"apply_update: refused machine rewrite of '{slug}': {reason}")
            return page

    page.content_md = new_content_md
    if title is not None:
        page.title = title
    if summary is not None:
        page.summary = summary
    if status is not None:
        page.status = status
    if add_knowledge_type_slug:
        kts = list(page.knowledge_type_slugs or [])
        if add_knowledge_type_slug not in kts:
            kts.append(add_knowledge_type_slug)
            page.knowledge_type_slugs = kts
    if add_source_id is not None:
        sids = list(page.source_ids or [])
        if add_source_id not in sids:
            sids.append(add_source_id)
            page.source_ids = sids
    page.version = int(page.version or 1) + 1
    await session.flush()
    await refresh_links(session, page.id, slug, new_content_md)
    session.add(_revision(page.id, page.version, new_content_md, "agent_compile"))
    return page


async def upsert_page(
    session,
    slug: str,
    title: Optional[str],
    page_type: Optional[str],
    content_md: Optional[str],
    summary: Optional[str],
    knowledge_type_slugs: Optional[list[str]],
    source_ids: Optional[list],
    scope_type: str = "global",
    scope_id=None,
    status: Optional[str] = None,
) -> WikiPage:
    await _advisory_lock(session, slug)
    existing = await get_page_by_slug(session, slug, scope_type=scope_type, scope_id=scope_id)
    if existing is None:
        return await apply_create(
            session, slug=slug, title=title, page_type=page_type, content_md=content_md,
            summary=summary, knowledge_type_slugs=knowledge_type_slugs, source_ids=source_ids,
            scope_type=scope_type, scope_id=scope_id, status=status or "seed",
        )
    kts = list(knowledge_type_slugs or [])
    sids = list(source_ids or [])
    updated = await apply_update(
        session, slug=slug, new_content_md=content_md or "", summary=summary, title=title,
        add_knowledge_type_slug=kts[0] if kts else None,
        add_source_id=sids[0] if sids else None,
        scope_type=scope_type, scope_id=scope_id, status=status,
    )
    return updated if updated is not None else existing


async def _upsert_reserved(session, slug: str, title: str, summary: str, content_md: str,
                           scope_type: str, scope_id, status: str = "evergreen") -> WikiPage:
    page = await get_page_by_slug(session, slug, scope_type=scope_type, scope_id=scope_id)
    if page is None:
        page = WikiPage(
            id=uuid.uuid4(), slug=slug, title=title, summary=summary, content_md=content_md,
            scope_type=scope_type or "global", scope_id=_as_uuid(scope_id), status=status,
            knowledge_type_slugs=[], source_ids=[], version=1,
        )
        session.add(page)
    else:
        page.content_md = content_md
        page.title = page.title or title
        if not page.summary:
            page.summary = summary
        page.version = int(page.version or 1) + 1
    await session.flush()
    return page


# ---------------------------------------------------------------------------
# Index / log / hot
# ---------------------------------------------------------------------------


def _render_index_md(pages: list, max_pages: Optional[int] = None) -> str:
    truncated = max_pages is not None and len(pages) > max_pages
    if truncated:
        pages = pages[:max_pages]
    lines = [f"# {INDEX_TITLE}", ""]
    if not pages:
        lines.append(_EMPTY_INDEX_NOTE)
        return "\n".join(lines) + "\n"
    groups: dict[str, list] = defaultdict(list)
    for p in pages:
        groups[_page_type_of(p)].append(p)
    for pt in sorted(groups):
        lines.append(f"## {pt.capitalize()}")
        lines.append("")
        for p in sorted(groups[pt], key=lambda x: ((x.title or x.slug or "").lower(), x.slug or "")):
            entry = f"- [[{p.slug}|{p.title or p.slug}]]"
            if getattr(p, "summary", None):
                entry += f" — {p.summary}"
            lines.append(entry)
        lines.append("")
    if truncated:
        lines.append(
            f"_Danh sách đã bị cắt ở {max_pages} trang. Dùng công cụ `list_wiki_pages` "
            "hoặc `search_wiki` để xem thêm._"
        )
    return "\n".join(lines).rstrip() + "\n"


async def render_scoped_index(
    session,
    *,
    allowed_kt_slugs: Optional[list[str]] = None,
    department_ids: Optional[list] = None,
    all_scopes: bool = False,
    max_pages: int = 2000,
    clearance: Optional[str] = None,
    page_filter=None,
) -> str:
    pages = await list_pages(
        session,
        allowed_kt_slugs=allowed_kt_slugs,
        department_ids=department_ids,
        all_scopes=all_scopes,
        clearance=clearance,
        page_filter=page_filter,
        limit=max_pages + 1,
    )
    return _render_index_md(list(pages), max_pages=max_pages)


async def regenerate_index(session, scope_type: str = "global", scope_id=None) -> WikiPage:
    stmt = (
        select(WikiPage)
        .where(WikiPage.slug.notin_(list(RESERVED_SLUGS)), _scope_filter(scope_type, scope_id))
        .order_by(WikiPage.title)
    )
    pages = list((await session.execute(stmt)).scalars().all())
    content = _render_index_md(pages)
    return await _upsert_reserved(session, INDEX_SLUG, INDEX_TITLE, INDEX_SUMMARY, content,
                                  scope_type or "global", scope_id)


async def append_log(session, entry: str, scope_type: str = "global", scope_id=None) -> WikiPage:
    stamp = _now().strftime("%Y-%m-%d %H:%M UTC")
    block = f"## [{stamp}] {entry}"
    page = await get_page_by_slug(session, LOG_SLUG, scope_type=scope_type, scope_id=scope_id)
    if page is None:
        content = f"# {LOG_TITLE}\n\n{block}\n"
        return await _upsert_reserved(session, LOG_SLUG, LOG_TITLE, LOG_SUMMARY, content,
                                      scope_type or "global", scope_id)
    current = page.content_md or f"# {LOG_TITLE}\n"
    if _EMPTY_LOG_NOTE in current:
        current = current.replace(_EMPTY_LOG_NOTE, block, 1)
        new_content = current if current.endswith("\n") else current + "\n"
    else:
        new_content = current.rstrip() + "\n\n" + block + "\n"
    page.content_md = new_content
    page.version = int(page.version or 1) + 1
    await session.flush()
    return page


async def regenerate_hot_cache(session, scope_type: str = "global", scope_id=None) -> WikiPage:
    base = select(WikiPage).where(
        WikiPage.slug.notin_(list(RESERVED_SLUGS)), _scope_filter(scope_type, scope_id)
    )
    contradictions = list((await session.execute(
        base.where(WikiPage.content_md.contains(_CONTRADICTION_MARKER)).order_by(WikiPage.updated_at.desc())
    )).scalars().all())
    recent = list((await session.execute(base.order_by(WikiPage.updated_at.desc()).limit(10))).scalars().all())
    seeds = list((await session.execute(
        base.where(WikiPage.status == "seed").order_by(WikiPage.updated_at.desc()).limit(20)
    )).scalars().all())

    def _section(heading: str, pages: list, empty: str) -> list[str]:
        out = [f"## {heading}", ""]
        if not pages:
            out.append(empty)
        for p in pages:
            out.append(f"- [[{p.slug}|{p.title or p.slug}]]")
        out.append("")
        return out

    lines = [f"# {HOT_TITLE}", ""]
    lines += _section("Trang có mâu thuẫn cần xử lý", contradictions, "_Không có mâu thuẫn nào._")
    lines += _section("Cập nhật gần đây", recent, "_Chưa có cập nhật._")
    lines += _section("Trang cần phát triển thêm", seeds, "_Không có trang nào ở trạng thái seed._")
    content = "\n".join(lines).rstrip() + "\n"
    return await _upsert_reserved(session, HOT_SLUG, HOT_TITLE, HOT_SUMMARY, content,
                                  scope_type or "global", scope_id, status="evergreen")


# ---------------------------------------------------------------------------
# Deletion / detaching sources
# ---------------------------------------------------------------------------


def _strip_links_to(content_md: str, slug: str) -> str:
    def _sub(m: re.Match) -> str:
        if m.group(1).strip() != slug:
            return m.group(0)
        label = m.group(2)
        if label is not None and label.strip():
            return label
        return slug.rsplit("/", 1)[-1]

    return _WIKILINK_RE.sub(_sub, content_md or "")


async def delete_page_cascade(session, page: WikiPage) -> None:
    slug = page.slug
    is_global = (page.scope_type or "global") == "global"
    if is_global:
        link_stmt = delete(WikiLink).where(WikiLink.to_slug == slug)
        ref_stmt = select(WikiPage).join(WikiLink, WikiLink.from_page_id == WikiPage.id).where(
            WikiLink.to_slug == slug, WikiPage.id != page.id
        )
    else:
        same_scope_ids = select(WikiPage.id).where(_scope_filter(page.scope_type, page.scope_id))
        link_stmt = delete(WikiLink).where(
            WikiLink.to_slug == slug, WikiLink.from_page_id.in_(same_scope_ids)
        )
        ref_stmt = select(WikiPage).join(WikiLink, WikiLink.from_page_id == WikiPage.id).where(
            WikiLink.to_slug == slug, WikiPage.id != page.id,
            _scope_filter(page.scope_type, page.scope_id),
        )
    referrers = list((await session.execute(ref_stmt.distinct())).scalars().all())
    await session.execute(link_stmt)
    for ref in referrers:
        new_md = _strip_links_to(ref.content_md or "", slug)
        if new_md != (ref.content_md or ""):
            ref.content_md = new_md

    try:
        from app.services.embedding_storage import (
            delete_wiki_page_chunk_embeddings,
            delete_wiki_page_embeddings,
        )

        await delete_wiki_page_embeddings(session, page.id)
        await delete_wiki_page_chunk_embeddings(session, page.id)
    except Exception as e:
        logger.warning(f"delete_page_cascade: embedding cleanup failed for {slug}: {e}")
    await session.delete(page)
    await session.flush()


async def detach_source_from_wiki(session, source_id) -> int:
    sid = _as_uuid(source_id)
    if sid is None:
        return 0
    pages = list((await session.execute(
        select(WikiPage).where(sid == any_(WikiPage.source_ids))
    )).scalars().all())
    deleted = 0
    for page in pages:
        remaining = [s for s in (page.source_ids or []) if s != sid]
        if remaining:
            page.source_ids = remaining
        else:
            await delete_page_cascade(session, page)
            deleted += 1
    await session.flush()
    return deleted


# ---------------------------------------------------------------------------
# Lint
# ---------------------------------------------------------------------------


async def lint_wiki(session, scope_type: str = "global", scope_id=None) -> dict:
    scope = _scope_filter(scope_type, scope_id)
    pages = list((await session.execute(
        select(WikiPage).where(WikiPage.slug.notin_(list(RESERVED_SLUGS)), scope)
    )).scalars().all())
    in_scope_slugs = {p.slug for p in pages}
    alive = set(in_scope_slugs) | set(RESERVED_SLUGS)
    if (scope_type or "global") != "global":
        g = await session.execute(select(WikiPage.slug).where(_scope_filter("global", None)))
        alive |= set(g.scalars().all())

    link_rows = await session.execute(
        select(WikiPage.slug, WikiPage.title, WikiLink.to_slug)
        .join(WikiLink, WikiLink.from_page_id == WikiPage.id)
        .where(scope, WikiPage.slug.notin_(list(RESERVED_SLUGS)))
    )
    dead_links: list[dict] = []
    linked: set[str] = set()
    for from_slug, from_title, to_slug in link_rows.all():
        linked.add(to_slug)
        if to_slug not in alive:
            dead_links.append({"from_slug": from_slug, "from_title": from_title, "to_slug": to_slug})

    orphans = [
        {"slug": p.slug, "title": p.title, "status": p.status}
        for p in sorted(pages, key=lambda x: x.slug)
        if p.slug not in linked
    ]
    contradictions = [
        {"slug": p.slug, "title": p.title}
        for p in sorted(pages, key=lambda x: x.slug)
        if _CONTRADICTION_MARKER in (p.content_md or "")
    ]
    return {"dead_links": dead_links, "orphans": orphans, "contradictions": contradictions}


# ---------------------------------------------------------------------------
# Drafts and revisions (05b §1)
# ---------------------------------------------------------------------------


async def create_draft(
    session,
    page_id,
    author_id,
    content_md: str,
    note: Optional[str] = None,
    source: str = "web_ui",
    source_metadata: Optional[dict] = None,
    base_version: Optional[int] = None,
    draft_kind: str = "edit",
    suggested_metadata: Optional[dict] = None,
) -> WikiPageDraft:
    draft = WikiPageDraft(
        id=uuid.uuid4(),
        page_id=page_id,
        author_id=author_id,
        content_md=content_md,
        note=note,
        source=source,
        source_metadata=source_metadata,
        base_version=base_version,
        draft_kind=draft_kind or "edit",
        suggested_metadata=suggested_metadata,
        status="pending",
        revision_round=0,
        ai_check_status="pending",
    )
    session.add(draft)
    await session.flush()
    return draft


def _meta_pick(overrides: dict, suggested: dict, override_key: str, suggested_key: str):
    val = overrides.get(override_key)
    if val is None or (isinstance(val, str) and not val.strip()):
        val = suggested.get(suggested_key)
    return val


async def approve_draft(
    session,
    draft: WikiPageDraft,
    reviewer_id,
    reviewer_note: Optional[str] = None,
    edited_content_md: Optional[str] = None,
    allow_conflict: bool = False,
    metadata_overrides: Optional[dict] = None,
) -> WikiPage:
    final_content = edited_content_md.strip() if edited_content_md is not None else draft.content_md

    if (draft.draft_kind or "edit") == "create":
        overrides = dict(metadata_overrides or {})
        suggested = dict(draft.suggested_metadata or {})
        slug = (_meta_pick(overrides, suggested, "final_slug", "slug") or "").strip()
        title = (_meta_pick(overrides, suggested, "final_title", "title") or "").strip()
        page_type = _meta_pick(overrides, suggested, "final_page_type", "page_type") or "concept"
        kts = overrides.get("final_knowledge_type_slugs")
        if kts is None:
            kts = suggested.get("knowledge_type_slugs") or []
        scope_type = suggested.get("scope_type") or "global"
        scope_id = _as_uuid(suggested.get("scope_id"))
        if not slug or slug in RESERVED_SLUGS:
            raise ValueError(f"Invalid slug for new page: '{slug}'")
        if not title:
            raise ValueError("Title is required to materialise a new page")
        await _advisory_lock(session, slug)
        existing = await get_page_by_slug(session, slug, scope_type=scope_type, scope_id=scope_id)
        if existing is not None:
            raise CreateDraftSlugConflict(slug, scope_type, scope_id)
        page = await apply_create(
            session, slug=slug, title=title, page_type=page_type, content_md=final_content,
            summary="", knowledge_type_slugs=list(kts), source_ids=[],
            scope_type=scope_type, scope_id=scope_id,
        )
        session.add(_revision(page.id, page.version, page.content_md, "draft_approved_create",
                              draft_id=draft.id, changed_by_id=reviewer_id, change_note=reviewer_note))
        draft.page_id = page.id
    else:
        page = getattr(draft, "page", None)
        if page is None and draft.page_id is not None:
            page = await session.get(WikiPage, draft.page_id)
        if page is None:
            raise ValueError(f"Wiki page {draft.page_id} not found")
        await _advisory_lock(session, page.slug)
        try:
            await session.refresh(page)
        except Exception:
            fresh = await session.get(WikiPage, page.id)
            if fresh is not None:
                page = fresh
        if (
            not allow_conflict
            and edited_content_md is None
            and draft.base_version is not None
            and page.version is not None
            and draft.base_version < page.version
        ):
            raise DraftConflictError(page.version, draft.base_version)
        page.content_md = final_content
        page.version = int(page.version or 1) + 1
        await session.flush()
        await refresh_links(session, page.id, page.slug, final_content)
        session.add(_revision(page.id, page.version, final_content, "draft_approved",
                              draft_id=draft.id, changed_by_id=reviewer_id, change_note=reviewer_note))

    draft.status = "approved"
    draft.reviewed_by_id = reviewer_id
    draft.reviewed_at = _now()
    draft.reviewer_note = reviewer_note
    await session.flush()
    return page


async def reject_draft(session, draft: WikiPageDraft, reviewer_id, reviewer_note: Optional[str]) -> WikiPageDraft:
    draft.status = "rejected"
    draft.reviewed_by_id = reviewer_id
    draft.reviewed_at = _now()
    draft.reviewer_note = reviewer_note
    await session.flush()
    return draft


HUMAN_REVISION_TYPES = ("editor_edit", "rollback", "draft_approved")


async def human_edited_page_ids(session, page_ids) -> set:
    """Pages whose content a person has changed (direct edit, rollback or approved draft)."""
    ids = [i for i in page_ids if i is not None]
    if not ids:
        return set()
    rows = await session.execute(
        select(WikiPageRevision.page_id).where(
            WikiPageRevision.page_id.in_(ids), WikiPageRevision.change_type.in_(HUMAN_REVISION_TYPES)
        ).distinct()
    )
    return set(rows.scalars().all())


async def direct_edit_page(session, page: WikiPage, editor_id, content_md: str,
                           change_note: Optional[str] = None) -> WikiPage:
    page.content_md = content_md
    page.version = int(page.version or 1) + 1
    await session.flush()
    await refresh_links(session, page.id, page.slug, content_md)
    session.add(_revision(page.id, page.version, content_md, "editor_edit",
                          changed_by_id=editor_id, change_note=change_note))
    await session.flush()
    return page


async def rollback_to_revision(session, page: WikiPage, target_version: int, actor_id) -> WikiPage:
    rev = (await session.execute(
        select(WikiPageRevision).where(
            WikiPageRevision.page_id == page.id, WikiPageRevision.version == target_version
        ).limit(1)
    )).scalars().first()
    if rev is None:
        raise ValueError(f"Revision v{target_version} not found for page {page.slug}")
    page.content_md = rev.content_md
    page.version = int(page.version or 1) + 1
    await session.flush()
    await refresh_links(session, page.id, page.slug, rev.content_md)
    session.add(_revision(page.id, page.version, rev.content_md, "rollback",
                          changed_by_id=actor_id, change_note=f"rollback to v{target_version}"))
    await session.flush()
    return page


# ---------------------------------------------------------------------------
# Search re-exports (implemented in _wiki_search, spec 04 §8)
# ---------------------------------------------------------------------------

try:
    from app.services._wiki_search import (  # noqa: E402,F401
        _lexical_plan,
        search_pages_hybrid,
        search_pages_semantic,
        search_source_chunks_hybrid,
    )
except ImportError as _search_import_error:  # pragma: no cover - fallback when search module missing
    logger.warning(f"wiki_service: search module unavailable ({_search_import_error})")

    def _lexical_plan(query_text):  # type: ignore[no-redef]
        return [], []

    async def search_pages_semantic(*args, **kwargs):  # type: ignore[no-redef]
        return []

    async def search_pages_hybrid(*args, **kwargs):  # type: ignore[no-redef]
        return []

    async def search_source_chunks_hybrid(*args, **kwargs):  # type: ignore[no-redef]
        return []
