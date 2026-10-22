"""Wiki draft endpoints: propose, list, review, revise, withdraw, bulk approve (05b §6)."""

from __future__ import annotations

import logging
import uuid
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import AfterValidator, BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import (
    Department,
    Employee,
    WikiBranch,
    WikiDraftRound,
    WikiPage,
    WikiPageDraft,
    WikiPageRevision,
)
from app.routers import wiki as wiki_router
from app.services import contribution_service, wiki_chunk_service, wiki_service
from app.services.audit_service import log_audit
from app.services.auth_service import get_current_user, require_permission
from app.services.wiki_draft_publish import publish_draft

logger = logging.getLogger(__name__)

router = APIRouter()

# Revision change types that count as an editorial review action.
REVIEW_CHANGE_TYPES = tuple("editor_edit draft_approved draft_approved_create rollback".split())


# ---------------------------------------------------------------------------
# Request models (§6.1)
# ---------------------------------------------------------------------------


class _Validated:
    """Annotated field types that delegate to the shared wiki validators.

    The lambdas resolve ``wiki_router`` at call time so the validators stay the
    single source of truth (and remain patchable in tests).
    """

    Content = Annotated[str, AfterValidator(lambda v: wiki_router._validate_content(v))]
    Slug = Annotated[str, AfterValidator(lambda v: wiki_router._validate_slug(v))]
    PageType = Annotated[str, AfterValidator(lambda v: wiki_router._validate_page_type(v))]
    ScopeType = Annotated[str, AfterValidator(lambda v: wiki_router._validate_scope_type(v))]


def _required_note(action: str):
    def check(value: str) -> str:
        if value is None or not value.strip():
            raise ValueError(f"reviewer_note is required when {action}")
        return value

    return AfterValidator(check)


class ProposeDraftRequest(BaseModel):
    content_md: _Validated.Content
    branch_id: Optional[uuid.UUID] = None
    base_version: Optional[int] = None
    note: Optional[str] = None
    scope_id: Optional[uuid.UUID] = None
    scope_type: Optional[str] = None


class ProposeCreateRequest(BaseModel):
    title: str
    slug: _Validated.Slug
    content_md: _Validated.Content
    summary: str = ""
    note: Optional[str] = None
    page_type: _Validated.PageType = "concept"
    scope_type: _Validated.ScopeType = "global"
    scope_id: Optional[uuid.UUID] = None
    branch_id: Optional[uuid.UUID] = None
    knowledge_type_slugs: list[str] = Field(default_factory=list)


class ApproveDraftRequest(BaseModel):
    allow_conflict: bool = False
    reviewer_note: Optional[str] = None
    edited_content_md: Optional[str] = None
    final_title: Optional[str] = None
    final_slug: Optional[str] = None
    final_knowledge_type_slugs: Optional[list[str]] = None
    final_page_type: Optional[str] = None


class RejectDraftRequest(BaseModel):
    reviewer_note: Annotated[str, _required_note("rejecting")]


class RequestChangesRequest(BaseModel):
    reviewer_note: Annotated[str, _required_note("requesting changes")]


class ResubmitDraftRequest(BaseModel):
    note: Optional[str] = None
    content_md: _Validated.Content


class BulkApproveRequest(BaseModel):
    draft_ids: list[str] = Field(default_factory=list)
    allow_conflict: bool = False
    reviewer_note: Optional[str] = None


# ---------------------------------------------------------------------------
# Response models (§6.2)
# ---------------------------------------------------------------------------


class AuthorStats(BaseModel):
    approved: int = 0
    rejected: int = 0
    needs_revision: int = 0
    total_reviewed: int = 0
    accuracy: float = 0.0


class SuggestedReviewer(BaseModel):
    id: str
    name: Optional[str] = None
    email: Optional[str] = None
    score: int = 0


class DraftResponse(BaseModel):
    id: str
    page_id: Optional[str] = None
    page_slug: Optional[str] = None
    page_title: Optional[str] = None
    page_scope_type: str = "global"
    page_scope_id: Optional[str] = None
    page_scope_name: Optional[str] = None
    page_version: int = 1
    base_version: Optional[int] = None
    has_conflict: bool = False
    draft_kind: str = "edit"
    suggested_metadata: Optional[dict] = None
    author_id: Optional[str] = None
    author_name: Optional[str] = None
    author_stats: Optional[AuthorStats] = None
    suggested_reviewers: list[SuggestedReviewer] = Field(default_factory=list)
    content_md: str = ""
    note: Optional[str] = None
    status: str = "pending"
    revision_round: int = 0
    last_returned_note: Optional[str] = None
    ai_check_status: str = "pending"
    ai_check_results: Optional[Any] = None
    ai_checked_at: Optional[str] = None
    source: Optional[str] = None
    reviewed_by_name: Optional[str] = None
    reviewed_at: Optional[str] = None
    reviewer_note: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""


class DraftRoundResponse(BaseModel):
    id: str
    round_no: int
    content_md: Optional[str] = None
    author_note: Optional[str] = None
    reviewer_return_note: Optional[str] = None
    ai_check_results: Optional[Any] = None
    submitted_at: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _iso(v) -> Optional[str]:
    return v.isoformat() if v is not None and hasattr(v, "isoformat") else None


def _sid(v) -> Optional[str]:
    return str(v) if v is not None else None


def _as_uuid(v) -> Optional[uuid.UUID]:
    if v is None or v == "":
        return None
    try:
        return v if isinstance(v, uuid.UUID) else uuid.UUID(str(v))
    except (ValueError, TypeError):
        return None


def _draft_scope(draft) -> tuple[str, Optional[uuid.UUID]]:
    page = draft.page
    if page is not None:
        return page.scope_type or "global", page.scope_id
    meta = draft.suggested_metadata or {}
    return meta.get("scope_type") or "global", _as_uuid(meta.get("scope_id"))


def _draft_slug(draft) -> Optional[str]:
    if draft.page is not None:
        return draft.page.slug
    return (draft.suggested_metadata or {}).get("slug")


async def _author_stats(db, author_id) -> Optional[AuthorStats]:
    if author_id is None:
        return None
    rows = (await db.execute(
        select(WikiPageDraft.status, func.count(WikiPageDraft.id))
        .where(WikiPageDraft.author_id == author_id,
               WikiPageDraft.status.in_(("approved", "rejected", "needs_revision")))
        .group_by(WikiPageDraft.status)
    )).all()
    counts = {s: int(n) for s, n in rows}
    approved, rejected = counts.get("approved", 0), counts.get("rejected", 0)
    total = approved + rejected
    return AuthorStats(
        approved=approved, rejected=rejected, needs_revision=counts.get("needs_revision", 0),
        total_reviewed=total, accuracy=round(approved / total, 3) if total else 0.0,
    )


async def _suggested_reviewers(db, draft) -> list[SuggestedReviewer]:
    if draft.status not in ("pending", "needs_revision"):
        return []
    if draft.page is not None:
        kts = list(draft.page.knowledge_type_slugs or [])
    else:
        kts = list((draft.suggested_metadata or {}).get("knowledge_type_slugs") or [])
    scope_type, scope_id = _draft_scope(draft)
    scope_match = (
        and_(WikiPage.scope_type == "global", WikiPage.scope_id.is_(None))
        if scope_type == "global"
        else and_(WikiPage.scope_type == scope_type, WikiPage.scope_id == scope_id)
    )
    cond = scope_match
    if kts:
        cond = or_(WikiPage.knowledge_type_slugs.overlap(kts), scope_match)
    stmt = (
        select(Employee.id, Employee.name, Employee.email, func.count(WikiPageRevision.id).label("score"))
        .join(WikiPageRevision, WikiPageRevision.changed_by_id == Employee.id)
        .join(WikiPage, WikiPage.id == WikiPageRevision.page_id)
        .where(WikiPageRevision.change_type.in_(REVIEW_CHANGE_TYPES), cond)
        .group_by(Employee.id, Employee.name, Employee.email)
        .order_by(func.count(WikiPageRevision.id).desc())
        .limit(4)
    )
    if draft.author_id is not None:
        stmt = stmt.where(Employee.id != draft.author_id)
    rows = (await db.execute(stmt)).all()
    return [SuggestedReviewer(id=str(r.id), name=r.name, email=r.email, score=int(r.score)) for r in rows][:3]


async def _scope_name(db, scope_type, scope_id) -> Optional[str]:
    if scope_type != "department" or scope_id is None:
        return None
    dept = await db.get(Department, scope_id)
    return dept.name if dept is not None else None


async def _to_response(db, draft, *, with_extras: bool = True) -> DraftResponse:
    page = draft.page
    meta = draft.suggested_metadata or {}
    scope_type, scope_id = _draft_scope(draft)
    current = (page.version if page is not None else None) or 1
    has_conflict = bool(
        draft.status == "pending" and page is not None and draft.base_version is not None
        and draft.base_version < (page.version or 1)
    )
    author = draft.author
    reviewer = draft.reviewer
    return DraftResponse(
        id=str(draft.id),
        page_id=_sid(draft.page_id),
        page_slug=page.slug if page is not None else meta.get("slug"),
        page_title=page.title if page is not None else meta.get("title"),
        page_scope_type=scope_type or "global",
        page_scope_id=_sid(scope_id),
        page_scope_name=await _scope_name(db, scope_type, scope_id),
        page_version=current,
        base_version=draft.base_version,
        has_conflict=has_conflict,
        draft_kind=draft.draft_kind or "edit",
        suggested_metadata=draft.suggested_metadata,
        author_id=_sid(draft.author_id),
        author_name=getattr(author, "name", None) if author is not None else None,
        author_stats=await _author_stats(db, draft.author_id) if with_extras else None,
        suggested_reviewers=await _suggested_reviewers(db, draft) if with_extras else [],
        content_md=draft.content_md or "",
        note=draft.note,
        status=draft.status or "pending",
        revision_round=draft.revision_round or 0,
        last_returned_note=draft.last_returned_note,
        ai_check_status=draft.ai_check_status or "pending",
        ai_check_results=draft.ai_check_results,
        ai_checked_at=_iso(draft.ai_checked_at),
        source=draft.source,
        reviewed_by_name=getattr(reviewer, "name", None) if reviewer is not None else None,
        reviewed_at=_iso(draft.reviewed_at),
        reviewer_note=draft.reviewer_note,
        created_at=_iso(draft.created_at) or "",
        updated_at=_iso(draft.updated_at) or "",
    )


async def _load_draft(db, draft_id: str) -> WikiPageDraft:
    try:
        did = uuid.UUID(str(draft_id))
    except (ValueError, TypeError):
        raise HTTPException(400, "Invalid draft ID format")
    draft = await db.get(WikiPageDraft, did)
    if draft is None:
        raise HTTPException(404, f"Draft {draft_id} not found")
    return draft


def _is_author(user, draft) -> bool:
    return draft.author_id is not None and draft.author_id == getattr(user, "id", None)


def _conflict_vi(e: wiki_service.DraftConflictError) -> HTTPException:
    return HTTPException(
        409, f"Trang đã được cập nhật lên v{e.current_version} sau khi bạn mở. Tải lại trang rồi sửa lại."
    )


async def _index_chunks(db, page) -> None:
    try:
        await wiki_chunk_service.index_wiki_page_chunks(db, page)
    except Exception as e:  # noqa: BLE001
        logger.warning("Chunk indexing failed for %s: %s", getattr(page, "slug", "?"), e)


async def _publish(db, draft, user):
    try:
        return await publish_draft(db, draft, user)
    except wiki_service.DraftConflictError as e:
        await db.rollback()
        raise _conflict_vi(e)
    except wiki_service.CreateDraftSlugConflict as e:
        await db.rollback()
        raise HTTPException(409, f"Slug '{e.slug}' đã tồn tại.")
    except ValueError as e:
        await db.rollback()
        raise HTTPException(400, str(e))


# ---------------------------------------------------------------------------
# Endpoint plumbing
# ---------------------------------------------------------------------------

_Session = Annotated[AsyncSession, Depends(get_db)]
_CurrentUser = Annotated[Employee, Depends(get_current_user)]

# ApproveDraftRequest fields that may override a "create" draft's suggested metadata.
_CREATE_OVERRIDE_FIELDS = frozenset(
    {"final_slug", "final_title", "final_page_type", "final_knowledge_type_slugs"}
)


async def _find_page_for_user(db, user, slug: str, scope_type: Optional[str], scope_id) -> WikiPage:
    """Resolve ``slug`` within what ``user`` may read, or raise 404."""
    visible = wiki_router.page_source_read_clause(user)
    if not scope_type:
        page = await wiki_service.get_page_by_slug_any_scope(db, slug, page_filter=visible)
    else:
        page = await wiki_service.get_page_by_slug(
            db, slug, page_filter=visible, scope_type=scope_type, scope_id=scope_id
        )
    if page is None:
        raise HTTPException(404, f"Wiki page not found: {slug}")
    return page


async def _refresh_scope(db, page, log_line: str) -> None:
    """Rebuild the scope's index page and append ``log_line`` to its log."""
    where = {"scope_type": page.scope_type or "global", "scope_id": page.scope_id}
    await wiki_service.regenerate_index(db, **where)
    await wiki_service.append_log(db, log_line, **where)


async def _ensure_pending_and_reviewable(db, user, draft, verb: str) -> None:
    if draft.status != "pending":
        raise HTTPException(400, f"Draft is already {draft.status}")
    if not await wiki_router._can_review_draft(db, user, draft):
        raise HTTPException(403, f"Insufficient permission to {verb} this draft")


async def _finish_transition(db, draft, pending_call, *, denied_status: int = 400) -> DraftResponse:
    """Await a contribution-service transition, mapping invalid ones to HTTP errors."""
    try:
        await pending_call
    except contribution_service.InvalidTransition as exc:
        raise HTTPException(denied_status, str(exc))
    await db.commit()
    return await _to_response(db, draft)


# ---------------------------------------------------------------------------
# Propose edit (published immediately)
# ---------------------------------------------------------------------------


@router.post("/wiki/pages/{slug:path}/drafts", response_model=DraftResponse, status_code=201)
async def propose_draft(slug: str, body: ProposeDraftRequest, db: _Session, user: _CurrentUser):
    reserved = wiki_service.is_reserved_slug(slug) or slug in {wiki_service.INDEX_SLUG, wiki_service.LOG_SLUG}
    if reserved:
        raise HTTPException(400, "Cannot propose drafts for reserved pages")
    page = await _find_page_for_user(db, user, slug, body.scope_type, body.scope_id)
    if not wiki_router._can_propose(user, page):
        raise HTTPException(403, "Insufficient permission to propose a draft for this page")
    await _validate_shared_branch_attachment(db, user, body.branch_id, page.scope_type, page.scope_id)

    live_version = page.version or 1
    base_version = live_version if body.base_version is None else body.base_version
    if base_version > live_version:
        raise HTTPException(400, f"base_version {base_version} is ahead of current page v{live_version}")

    draft = await wiki_service.create_draft(
        db, page.id, user.id, body.content_md, base_version=base_version, source="web_ui", note=body.note,
    )
    draft.page = page
    if body.branch_id is not None:
        draft.branch_id = body.branch_id
    await log_audit(db, user, "update", "wiki_draft", draft.id, reason=f"published edit: {page.slug}")
    await _publish(db, draft, user)
    await db.commit()
    return await _to_response(db, draft)


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


@router.get("/wiki/drafts", response_model=list[DraftResponse])
async def list_drafts(
    db: _Session,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    mine: bool = False,
    status: Optional[str] = "pending",
    user: Employee = require_permission("wiki:read"),
):
    stmt = select(WikiPageDraft).outerjoin(WikiPage, WikiPage.id == WikiPageDraft.page_id)
    conditions: list = [WikiPageDraft.status == status] if status else []
    if mine:
        conditions.append(WikiPageDraft.author_id == user.id)
    elif not wiki_router._can_review(user):
        return []
    else:
        stmt = stmt.outerjoin(WikiBranch, WikiBranch.id == WikiPageDraft.branch_id)
        conditions.append(or_(WikiPageDraft.branch_id.is_(None), WikiBranch.status == "pending_merge"))
        readable = wiki_router.page_source_read_clause(user)
        if readable is not None:
            conditions.append(or_(WikiPageDraft.page_id.is_(None), readable))
        if getattr(user, '_central_permissions', None) is not None and not wiki_router._is_admin(user):
            metadata = WikiPageDraft.suggested_metadata
            create_scope = or_(
                metadata['scope_type'].as_string() == 'global',
                and_(metadata['scope_type'].as_string() == 'department',
                     metadata['scope_id'].as_string().in_(wiki_router._dept_str_set(user))),
                and_(metadata['scope_type'].as_string() == 'personal',
                     metadata['scope_id'].as_string() == str(user.id)),
            )
            conditions.append(or_(
                and_(WikiPageDraft.draft_kind == 'create', create_scope),
                and_(WikiPageDraft.draft_kind != 'create', wiki_router._build_wiki_scope_filter(user)),
            ))
    if conditions:
        stmt = stmt.where(*conditions)
    stmt = stmt.order_by(WikiPageDraft.created_at.desc()).offset(offset).limit(limit)
    found = (await db.execute(stmt)).scalars().unique().all()
    return [await _to_response(db, d) for d in found]


@router.get("/wiki/pages/{slug:path}/drafts", response_model=list[DraftResponse])
async def list_page_drafts(
    slug: str,
    db: _Session,
    user: _CurrentUser,
    status: Optional[str] = None,
    scope_type: Optional[str] = None,
    scope_id: Optional[uuid.UUID] = None,
):
    page = await _find_page_for_user(db, user, slug, scope_type, scope_id)
    stmt = select(WikiPageDraft).where(WikiPageDraft.page_id == page.id)
    if status:
        stmt = stmt.where(WikiPageDraft.status == status)
    if not wiki_router._can_review(user):
        stmt = stmt.where(WikiPageDraft.author_id == user.id)
    found = (await db.execute(stmt.order_by(WikiPageDraft.created_at.desc()))).scalars().all()
    return [await _to_response(db, d) for d in found]


# ---------------------------------------------------------------------------
# Create proposal (published immediately)
# ---------------------------------------------------------------------------


def _check_create_permission(user, body: ProposeCreateRequest) -> None:
    if wiki_router._is_admin(user):
        return
    perms = wiki_router._perms(user)
    if body.scope_type == "department" and body.scope_id is not None:
        in_own_dept = str(body.scope_id) in wiki_router._dept_str_set(user)
        if "wiki:write:all" not in perms and not ("wiki:write:own_dept" in perms and in_own_dept):
            raise HTTPException(403, "Insufficient permission to propose pages in this department")
    elif not any(p.startswith("wiki:write") for p in perms):
        raise HTTPException(403, "Insufficient permission to propose new pages")


async def _validate_shared_branch_attachment(db, user, branch_id, scope_type, scope_id):
    if branch_id is None or getattr(user, '_central_permissions', None) is None or wiki_router._is_admin(user):
        return
    branch = await db.get(WikiBranch, branch_id)
    if branch is None:
        raise HTTPException(404, 'Không tìm thấy nhánh đóng góp')
    if branch.author_id != user.id or branch.status in ('closed', 'merged'):
        raise HTTPException(403, 'Không được gắn bản nháp vào nhánh này')
    if (branch.scope_type or 'global') != (scope_type or 'global') or str(branch.scope_id or '') != str(scope_id or ''):
        raise HTTPException(403, 'Bản nháp phải cùng phạm vi với nhánh đóng góp')


@router.post("/wiki/drafts/create", response_model=DraftResponse, status_code=201)
async def propose_create(body: ProposeCreateRequest, db: _Session, user: _CurrentUser):
    _check_create_permission(user, body)
    await _validate_shared_branch_attachment(db, user, body.branch_id, body.scope_type, body.scope_id)
    clash = await wiki_service.get_page_by_slug(db, body.slug, scope_type=body.scope_type, scope_id=body.scope_id)
    if clash is not None:
        raise HTTPException(
            409,
            f"Slug '{body.slug}' already exists in {body.scope_type}. Use edit_wiki_page to edit the existing page.",
        )
    suggested = dict(
        slug=body.slug,
        title=body.title,
        page_type=body.page_type,
        knowledge_type_slugs=list(body.knowledge_type_slugs or []),
        scope_type=body.scope_type,
        scope_id=_sid(body.scope_id),
    )
    draft = await wiki_service.create_draft(
        db, None, user.id, body.content_md,
        draft_kind="create", suggested_metadata=suggested, note=body.note, source="web_ui",
    )
    if body.branch_id is not None:
        draft.branch_id = body.branch_id
    await log_audit(db, user, "create", "wiki_draft", draft.id, reason=f"published new page: {body.slug}")
    await _publish(db, draft, user)
    await db.commit()
    return await _to_response(db, draft)


# ---------------------------------------------------------------------------
# Bulk approve (registered before /wiki/drafts/{id} routes)
# ---------------------------------------------------------------------------


def _bulk_row(draft_id, status: str, message: Optional[str] = None, page_version=None) -> dict:
    return {"draft_id": str(draft_id), "status": status, "message": message, "page_version": page_version}


def _bulk_skip_reason(user, draft, is_admin: bool, can_review: bool) -> Optional[str]:
    if draft.status != "pending":
        return f"Draft is already {draft.status}"
    if not can_review:
        return "Insufficient permission"
    if _is_author(user, draft) and not is_admin:
        return "Cannot approve your own draft"
    return None


async def _bulk_approve_one(db, user, draft, body: BulkApproveRequest) -> dict:
    async with db.begin_nested():
        page = await wiki_service.approve_draft(
            db, draft, user.id, allow_conflict=body.allow_conflict, reviewer_note=body.reviewer_note,
        )
        await log_audit(db, user, "update", "wiki_draft", draft.id, reason=f"bulk-approved: {page.slug}")
        await _refresh_scope(
            db, page,
            f"Bulk-approved draft for: {page.title} ({page.slug}) -> v{page.version} "
            f"by {wiki_router._user_label(user)}",
        )
        await contribution_service.notify_approved(
            db, contribution_service.wiki_draft_adapter, draft, user, version_label=f"v{page.version}"
        )
        await _index_chunks(db, page)
    return _bulk_row(draft.id, "approved", page_version=page.version)


def _forget(db, draft) -> None:
    try:
        db.expire(draft)
        if draft.page is not None:
            db.expire(draft.page)
    except Exception:  # noqa: BLE001
        pass


@router.post("/wiki/drafts/bulk-approve")
async def bulk_approve(body: BulkApproveRequest, db: _Session, user: _CurrentUser):
    is_admin = wiki_router._is_admin(user)
    results: list[dict] = []
    for raw_id in body.draft_ids or []:
        draft_uuid = _as_uuid(raw_id)
        draft = None if draft_uuid is None else await db.get(WikiPageDraft, draft_uuid)
        if draft is None:
            results.append(_bulk_row(raw_id, "error", "Draft not found"))
            continue
        can_review = draft.status == "pending" and await wiki_router._can_review_draft(db, user, draft)
        reason = _bulk_skip_reason(user, draft, is_admin, can_review)
        if reason is not None:
            results.append(_bulk_row(draft.id, "skipped", reason))
            continue
        try:
            results.append(await _bulk_approve_one(db, user, draft, body))
        except Exception as e:  # noqa: BLE001
            _forget(db, draft)
            results.append(_bulk_row(draft.id, "error", str(e)))
    await db.commit()
    tally = {"approved": 0, "skipped": 0, "error": 0}
    for row in results:
        tally[row["status"]] += 1
    return {"results": results, "approved": tally["approved"], "skipped": tally["skipped"], "errored": tally["error"]}


# ---------------------------------------------------------------------------
# Single draft
# ---------------------------------------------------------------------------


async def _may_view(db, user, draft) -> bool:
    if wiki_router._is_admin(user) or _is_author(user, draft):
        return True
    return await wiki_router._can_review_draft(db, user, draft)


@router.get("/wiki/drafts/{draft_id}", response_model=DraftResponse)
async def get_draft(draft_id: str, db: _Session, user: _CurrentUser):
    draft = await _load_draft(db, draft_id)
    if await _may_view(db, user, draft):
        return await _to_response(db, draft)
    raise HTTPException(403, "Insufficient permission to view this draft")


@router.post("/wiki/drafts/{draft_id}/approve", response_model=DraftResponse)
async def approve_draft(draft_id: str, body: ApproveDraftRequest, db: _Session, user: _CurrentUser):
    draft = await _load_draft(db, draft_id)
    await _ensure_pending_and_reviewable(db, user, draft, "approve")
    if _is_author(user, draft) and not wiki_router._is_admin(user):
        raise HTTPException(403, "You cannot approve your own draft. Ask another editor to review it.")

    is_create = (draft.draft_kind or "edit") == "create"
    overrides = (body.model_dump(include=_CREATE_OVERRIDE_FIELDS, exclude_none=True) or None) if is_create else None
    try:
        page = await wiki_service.approve_draft(
            db, draft, user.id,
            metadata_overrides=overrides,
            allow_conflict=body.allow_conflict,
            edited_content_md=body.edited_content_md,
            reviewer_note=body.reviewer_note,
        )
    except wiki_service.DraftConflictError as e:
        await db.rollback()
        raise HTTPException(409, detail={
            "error": "draft_conflict",
            "base_version": e.base_version,
            "current_version": e.current_version,
            "message": str(e),
            "hint": "Resubmit with allow_conflict=true to overwrite, or provide edited_content_md with a merged version.",
        })
    except wiki_service.CreateDraftSlugConflict as e:
        await db.rollback()
        raise HTTPException(409, detail={
            "error": "slug_conflict",
            "slug": e.slug,
            "scope_id": _sid(e.scope_id),
            "scope_type": e.scope_type,
            "message": str(e),
            "hint": "Choose a different final_slug, or edit the existing page instead.",
        })
    except ValueError as e:
        await db.rollback()
        raise HTTPException(400, str(e))

    audit_verb, log_verb = ("created", "Created") if is_create else ("approved", "Approved")
    await log_audit(db, user, "update", "wiki_draft", draft.id, reason=f"{audit_verb} draft for: {page.slug}")
    await _refresh_scope(
        db, page, f"{log_verb} page: {page.title} ({page.slug}) → v{page.version} by {wiki_router._user_label(user)}"
    )
    draft.page = page
    await contribution_service.notify_approved(
        db, contribution_service.wiki_draft_adapter, draft, user, version_label=f"v{page.version}"
    )
    await _index_chunks(db, page)
    await db.commit()
    return await _to_response(db, draft)


def _draft_label(draft) -> str:
    if draft.page is not None:
        return draft.page.slug
    if (draft.draft_kind or "edit") != "create":
        return "(unknown)"
    return (draft.suggested_metadata or {}).get("slug") or "(new page)"


@router.post("/wiki/drafts/{draft_id}/reject", response_model=DraftResponse)
async def reject_draft(draft_id: str, body: RejectDraftRequest, db: _Session, user: _CurrentUser):
    draft = await _load_draft(db, draft_id)
    await _ensure_pending_and_reviewable(db, user, draft, "reject")
    note = body.reviewer_note
    await wiki_service.reject_draft(db, draft, user.id, note)
    await log_audit(db, user, "update", "wiki_draft", draft.id, reason=f"rejected draft for: {_draft_label(draft)}")
    await contribution_service.notify_rejected(
        db, contribution_service.wiki_draft_adapter, draft, user, reason=note
    )
    await db.commit()
    return await _to_response(db, draft)


@router.post("/wiki/drafts/{draft_id}/request-changes", response_model=DraftResponse)
async def request_changes(draft_id: str, body: RequestChangesRequest, db: _Session, user: _CurrentUser):
    draft = await _load_draft(db, draft_id)
    if not await wiki_router._can_review_draft(db, user, draft):
        raise HTTPException(403, "Insufficient permission to review this draft")
    adapter = contribution_service.wiki_draft_adapter
    return await _finish_transition(
        db, draft, contribution_service.request_changes(db, adapter, draft, user, body.reviewer_note)
    )


@router.patch("/wiki/drafts/{draft_id}/content", response_model=DraftResponse)
async def resubmit_draft(draft_id: str, body: ResubmitDraftRequest, db: _Session, user: _CurrentUser):
    draft = await _load_draft(db, draft_id)
    revised = body.content_md.strip()
    return await _finish_transition(
        db, draft, contribution_service.resubmit_wiki_draft(db, draft, user, revised, author_note=body.note)
    )


@router.post("/wiki/drafts/{draft_id}/withdraw", response_model=DraftResponse)
async def withdraw_draft(draft_id: str, db: _Session, user: _CurrentUser):
    draft = await _load_draft(db, draft_id)
    adapter = contribution_service.wiki_draft_adapter
    return await _finish_transition(
        db, draft, contribution_service.withdraw(db, adapter, draft, user), denied_status=403
    )


_ROUND_COPY_FIELDS = ("round_no", "content_md", "author_note", "reviewer_return_note", "ai_check_results")


def _round_to_response(round_row) -> DraftRoundResponse:
    copied = {name: getattr(round_row, name) for name in _ROUND_COPY_FIELDS}
    return DraftRoundResponse(id=str(round_row.id), submitted_at=_iso(round_row.submitted_at) or "", **copied)


@router.get("/wiki/drafts/{draft_id}/rounds", response_model=list[DraftRoundResponse])
async def list_draft_rounds(draft_id: str, db: _Session, user: _CurrentUser):
    draft = await _load_draft(db, draft_id)
    if not await _may_view(db, user, draft):
        raise HTTPException(403, "Insufficient permission to view this draft's rounds")
    by_round = select(WikiDraftRound).where(WikiDraftRound.draft_id == draft.id).order_by(
        WikiDraftRound.round_no.asc()
    )
    return [_round_to_response(r) for r in (await db.execute(by_round)).scalars().all()]
