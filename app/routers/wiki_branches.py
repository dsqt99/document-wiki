"""Contribution branches: group drafts and merge them in one review (05b §7)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import Employee, WikiBranch, WikiPage, WikiPageDraft
from app.routers import wiki as wiki_router
from app.routers.wiki_drafts import DraftResponse, _to_response
from app.services import contribution_service, wiki_service
from app.services.audit_service import log_audit
from app.services.auth_service import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


class BranchCreate(BaseModel):
    name: str
    description: Optional[str] = None
    scope_type: str = "global"
    scope_id: Optional[uuid.UUID] = None

    @field_validator("name")
    @classmethod
    def _name(cls, v):
        v = (v or "").strip()
        if not v:
            raise ValueError("Tên nhánh không được để trống")
        if len(v) > 100:
            raise ValueError("Tên nhánh không được vượt quá 100 ký tự")
        return v

    @field_validator("scope_type")
    @classmethod
    def _scope_type(cls, v):
        v = v or "global"
        if v not in ("global", "department"):
            raise ValueError("scope_type phải là global hoặc department")
        return v


class BranchResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    scope_type: str = "global"
    scope_id: Optional[str] = None
    author_id: Optional[str] = None
    author_name: Optional[str] = None
    status: str = "draft"
    has_conflict: bool = False
    reviewer_id: Optional[str] = None
    reviewer_name: Optional[str] = None
    reviewed_at: Optional[str] = None
    reviewer_note: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""
    draft_count: int = 0


class BranchDetailResponse(BranchResponse):
    drafts: list[DraftResponse] = Field(default_factory=list)


class MergeRequest(BaseModel):
    reviewer_note: Optional[str] = None


class RebaseRequest(BaseModel):
    resolved_content_md: str


def _iso(v) -> Optional[str]:
    return v.isoformat() if v is not None and hasattr(v, "isoformat") else None


def _sid(v) -> Optional[str]:
    return str(v) if v is not None else None


async def _name_of(db, emp_id) -> Optional[str]:
    if emp_id is None:
        return None
    emp = await db.get(Employee, emp_id)
    return emp.name if emp is not None else None


async def _branch_drafts(db, branch_id) -> list[WikiPageDraft]:
    return list((await db.execute(
        select(WikiPageDraft).where(WikiPageDraft.branch_id == branch_id).order_by(WikiPageDraft.created_at.desc())
    )).scalars().all())


async def _to_branch(db, b: WikiBranch, draft_count: Optional[int] = None) -> BranchResponse:
    if draft_count is None:
        draft_count = int((await db.execute(
            select(func.count(WikiPageDraft.id)).where(WikiPageDraft.branch_id == b.id)
        )).scalar() or 0)
    return BranchResponse(
        id=str(b.id), name=b.name, description=b.description, scope_type=b.scope_type or "global",
        scope_id=_sid(b.scope_id), author_id=_sid(b.author_id), author_name=await _name_of(db, b.author_id),
        status=b.status or "draft", has_conflict=bool(b.has_conflict), reviewer_id=_sid(b.reviewer_id),
        reviewer_name=await _name_of(db, b.reviewer_id), reviewed_at=_iso(b.reviewed_at),
        reviewer_note=b.reviewer_note, created_at=_iso(b.created_at) or "", updated_at=_iso(b.updated_at) or "",
        draft_count=draft_count,
    )


async def _detail(db, b: WikiBranch) -> BranchDetailResponse:
    drafts = await _branch_drafts(db, b.id)
    base = await _to_branch(db, b, draft_count=len(drafts))
    return BranchDetailResponse(**base.model_dump(), drafts=[await _to_response(db, d) for d in drafts])


async def _load_branch(db, branch_id, message: str) -> WikiBranch:
    try:
        bid = uuid.UUID(str(branch_id))
    except (ValueError, TypeError):
        raise HTTPException(404, message)
    b = await db.get(WikiBranch, bid)
    if b is None:
        raise HTTPException(404, message)
    return b


def _is_branch_author(user, b) -> bool:
    return b.author_id is not None and b.author_id == getattr(user, "id", None)


def _can_merge(user) -> bool:
    return wiki_router._can_review(user)


async def _conflicting_drafts(db, b) -> list[tuple[WikiPageDraft, WikiPage]]:
    out = []
    for d in await _branch_drafts(db, b.id):
        if (d.draft_kind or "edit") != "edit" or d.page_id is None:
            continue
        if d.status not in ("pending", "needs_revision"):
            continue
        page = await db.get(WikiPage, d.page_id)
        if page is None:
            continue
        if d.base_version is not None and page.version is not None and d.base_version < page.version:
            out.append((d, page))
    return out


@router.post("/wiki/branches", response_model=BranchResponse, status_code=201)
async def create_branch(body: BranchCreate, db: AsyncSession = Depends(get_db),
                        user: Employee = Depends(get_current_user)):
    if not wiki_router._can_propose_scope(user, body.scope_type, body.scope_id):
        raise HTTPException(403, "Bạn không có quyền đóng góp trong phạm vi này")
    b = WikiBranch(name=body.name, description=body.description, scope_type=body.scope_type,
                   scope_id=body.scope_id, author_id=user.id, status="draft", has_conflict=False)
    db.add(b)
    await db.commit()
    await log_audit(db, user, "create_branch", "wiki_branch", b.id, reason=b.name)
    await db.refresh(b)
    return await _to_branch(db, b, draft_count=0)


@router.get("/wiki/branches", response_model=list[BranchResponse])
async def list_branches(
    status: Optional[str] = None,
    scope_type: Optional[str] = None,
    scope_id: Optional[uuid.UUID] = None,
    mine: bool = False,
    db: AsyncSession = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    stmt = select(WikiBranch)
    if status:
        stmt = stmt.where(WikiBranch.status == status)
    if scope_type:
        stmt = stmt.where(WikiBranch.scope_type == scope_type)
    if scope_id is not None:
        stmt = stmt.where(WikiBranch.scope_id == scope_id)
    if mine:
        stmt = stmt.where(WikiBranch.author_id == user.id)
    stmt = stmt.order_by(WikiBranch.updated_at.desc())
    branches = list((await db.execute(stmt)).scalars().all())
    return [await _to_branch(db, b) for b in branches]


@router.get("/wiki/branches/{branch_id}", response_model=BranchDetailResponse)
async def get_branch(branch_id: str, db: AsyncSession = Depends(get_db),
                     user: Employee = Depends(get_current_user)):
    b = await _load_branch(db, branch_id, "Không tìm thấy nhánh đóng góp này")
    return await _detail(db, b)


@router.post("/wiki/branches/{branch_id}/submit", response_model=BranchDetailResponse)
async def submit_branch(branch_id: str, db: AsyncSession = Depends(get_db),
                        user: Employee = Depends(get_current_user)):
    b = await _load_branch(db, branch_id, "Không tìm thấy nhánh đóng góp")
    if not _is_branch_author(user, b) and not wiki_router._is_admin(user):
        raise HTTPException(403, "Chỉ có tác giả của nhánh mới có quyền gửi yêu cầu")
    if b.status != "draft":
        raise HTTPException(400, f"Không thể gửi yêu cầu hợp nhất khi nhánh đang ở trạng thái '{b.status}'")
    drafts = await _branch_drafts(db, b.id)
    if not drafts:
        raise HTTPException(400, "Nhánh đóng góp của bạn đang trống. Vui lòng thêm nháp trang trước khi gửi.")
    for d in drafts:
        d.status = "pending"
        await contribution_service.notify_submitted(db, contribution_service.wiki_draft_adapter, d, user)
    b.status = "pending_merge"
    await db.commit()
    await log_audit(db, user, "submit_branch", "wiki_branch", b.id, reason=b.name)
    return await _detail(db, b)


@router.post("/wiki/branches/{branch_id}/close", response_model=BranchDetailResponse)
async def close_branch(branch_id: str, db: AsyncSession = Depends(get_db),
                       user: Employee = Depends(get_current_user)):
    b = await _load_branch(db, branch_id, "Không tìm thấy nhánh đóng góp")
    if not (_is_branch_author(user, b) or wiki_router._is_admin(user) or _can_merge(user)):
        raise HTTPException(403, "Bạn không có quyền đóng hoặc hủy nhánh này")
    if b.status in ("merged", "closed"):
        raise HTTPException(400, "Nhánh đã đóng hoặc đã được hợp nhất")
    for d in await _branch_drafts(db, b.id):
        if d.status in ("pending", "needs_revision"):
            d.status = "withdrawn"
    b.status = "closed"
    await db.commit()
    await log_audit(db, user, "close_branch", "wiki_branch", b.id, reason=b.name)
    return await _detail(db, b)


@router.post("/wiki/branches/{branch_id}/merge", response_model=BranchDetailResponse)
async def merge_branch(branch_id: str, body: MergeRequest = MergeRequest(), db: AsyncSession = Depends(get_db),
                       user: Employee = Depends(get_current_user)):
    b = await _load_branch(db, branch_id, "Không tìm thấy nhánh đóng góp")
    if not _can_merge(user):
        raise HTTPException(403, "Bạn không có quyền hợp nhất tài liệu trong phạm vi này")
    if b.status != "pending_merge":
        raise HTTPException(400, "Chỉ có thể hợp nhất nhánh khi đang ở trạng thái 'pending_merge'")

    conflicts = await _conflicting_drafts(db, b)
    if conflicts:
        b.has_conflict = True
        await db.commit()
        parts = [
            f"'{p.title}' ({p.slug}): trang hiện ở v{p.version}, bản nháp dựa trên v{d.base_version}"
            for d, p in conflicts
        ]
        raise HTTPException(
            409,
            "Nhánh có xung đột phiên bản: " + "; ".join(parts)
            + ". Tác giả cần rebase các bản nháp này trước khi hợp nhất.",
        )

    try:
        async with db.begin_nested():
            for d in await _branch_drafts(db, b.id):
                if d.status != "pending":
                    continue
                page = await wiki_service.approve_draft(db, d, user.id, reviewer_note=body.reviewer_note)
                d.page = page
                await contribution_service.notify_approved(db, contribution_service.wiki_draft_adapter, d, user,
                                                           version_label=f"v{page.version}")
            b.status = "merged"
            b.reviewer_id = user.id
            b.reviewed_at = datetime.now(timezone.utc)
            b.reviewer_note = body.reviewer_note
            b.has_conflict = False
        await db.commit()
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        await db.rollback()
        raise HTTPException(400, f"Lỗi hợp nhất nhánh: {e}")
    await log_audit(db, user, "merge_branch", "wiki_branch", b.id, reason=b.name)
    return await _detail(db, b)


@router.post("/wiki/branches/{branch_id}/rebase/{draft_id}", response_model=DraftResponse)
async def rebase_draft(branch_id: str, draft_id: str, body: RebaseRequest, db: AsyncSession = Depends(get_db),
                       user: Employee = Depends(get_current_user)):
    b = await _load_branch(db, branch_id, "Không tìm thấy nhánh đóng góp")
    if not _is_branch_author(user, b) and not wiki_router._is_admin(user):
        raise HTTPException(403, "Chỉ có tác giả nhánh mới có quyền xử lý xung đột")
    try:
        did = uuid.UUID(str(draft_id))
    except (ValueError, TypeError):
        did = None
    d = await db.get(WikiPageDraft, did) if did is not None else None
    if d is None or d.branch_id != b.id:
        raise HTTPException(404, "Không tìm thấy bản nháp cần xử lý trong nhánh này")
    if (d.draft_kind or "edit") == "create":
        raise HTTPException(400, "Bản nháp trang tạo mới không cần xử lý rebase")
    page = await db.get(WikiPage, d.page_id) if d.page_id is not None else None
    if page is None:
        raise HTTPException(404, "Không tìm thấy trang gốc trên wiki")
    d.content_md = body.resolved_content_md
    d.base_version = page.version
    d.status = "pending"
    await contribution_service._enqueue_ai_review(db, d)
    b.has_conflict = bool(await _conflicting_drafts(db, b))
    await db.commit()
    await log_audit(db, user, "rebase_draft", "wiki_draft", d.id, reason=f"branch {b.id}")
    await db.refresh(d)
    return await _to_response(db, d)
