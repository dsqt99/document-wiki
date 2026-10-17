"""Skill contribution endpoints (06 §3.3-3.4, deviations 9-11 of §12)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.database.models import Skill, SkillContribution
from app.services import contribution_service as cs
from app.services import permission_engine
from app.services import skill_contribution_service as contrib
from app.services.auth_service import get_current_user, require_permission
from app.services.storage_service import storage_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["skill-contributions"])

REVIEW_PERMISSION = "skill:contribution:review"
ADAPTER = cs.skill_contribution_adapter
TEXT_EXTENSIONS = {
    ".py", ".md", ".txt", ".json", ".yaml", ".yml", ".sh", ".js", ".ts", ".tsx", ".html", ".css", ".sql",
    ".env", ".cfg", ".ini", ".xml", ".csv", ".bat", ".ps1",
}


class SkillContributionCreate(BaseModel):
    skill_id: Optional[uuid.UUID] = None
    base_version: Optional[int] = None
    title: str
    scope_type: str = "global"
    scope_ids: Optional[list[uuid.UUID]] = None


class SkillContributionResponse(BaseModel):
    id: uuid.UUID
    skill_id: Optional[uuid.UUID] = None
    contributor_id: Optional[uuid.UUID] = None
    base_version: Optional[int] = None
    status: str
    title: Optional[str] = None
    storage_path: Optional[str] = None
    scope_type: Optional[str] = "global"
    scope_ids: Optional[list[Any]] = None
    contributor_name: str = "Unknown"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class PutFileRequest(BaseModel):
    path: str
    content: str


class SkillContributionApprove(BaseModel):
    final_scope_type: Optional[str] = None
    final_scope_ids: Optional[list[uuid.UUID]] = None


class RequestChangesSkillRequest(BaseModel):
    reviewer_note: str


# ---------------------------------------------------------------- helpers


def _is_admin(user) -> bool:
    return getattr(user, "role", None) == "admin"


def _is_reviewer(user) -> bool:
    return _is_admin(user) or REVIEW_PERMISSION in permission_engine._get_user_permissions(user)


def _is_owner(user, c) -> bool:
    return c.contributor_id is not None and str(c.contributor_id) == str(getattr(user, "id", None))


def _to_response(c: SkillContribution) -> SkillContributionResponse:
    contributor = getattr(c, "contributor", None)
    return SkillContributionResponse(
        id=c.id, skill_id=c.skill_id, contributor_id=c.contributor_id, base_version=c.base_version,
        status=c.status, title=c.title, storage_path=c.storage_path, scope_type=c.scope_type,
        scope_ids=c.scope_ids, contributor_name=(getattr(contributor, "name", None) or "Unknown"),
        created_at=c.created_at, updated_at=c.updated_at,
    )


async def _viewable(db, user, contribution_id) -> SkillContribution:
    c = await contrib.require_contribution(db, contribution_id)
    if not (_is_admin(user) or _is_owner(user, c) or _is_reviewer(user)):
        raise HTTPException(status_code=403, detail="Access denied")
    return c


async def _editable(db, user, contribution_id) -> SkillContribution:
    c = await contrib.require_contribution(db, contribution_id)
    if not (_is_admin(user) or _is_owner(user, c)):
        raise HTTPException(status_code=403, detail="Access denied")
    if c.status not in contrib.EDITABLE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot edit contribution while status='{c.status}'. Withdraw it (or ask a reviewer to "
                   f"request changes) before editing.",
        )
    return c


def _prefix(c) -> str:
    return c.storage_path or contrib.contribution_prefix(c.id)


def _is_text(path: str) -> bool:
    from pathlib import PurePosixPath

    p = PurePosixPath(path or "")
    return p.suffix.lower() in TEXT_EXTENSIONS or p.name.lower() in TEXT_EXTENSIONS


async def _commit_touch(db, c) -> None:
    from datetime import timezone

    c.updated_at = datetime.now(timezone.utc)
    await db.commit()


async def _write_file(db, c, path: str, data: bytes, content_type: str) -> str:
    root = await contrib.contribution_root(db, c)
    rel = contrib.under_root(root, path)
    if not contrib.is_safe_member(rel):
        raise HTTPException(status_code=400, detail="Invalid file path.")
    try:
        await contrib.run(storage_service.upload_file, _prefix(c) + rel, data, content_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MinIO upload failed: {e}")
    await _commit_touch(db, c)
    return rel


# ---------------------------------------------------------------- collection routes


@router.get("/skill-contributions/check", response_model=Optional[SkillContributionResponse])
async def check_draft(title: Optional[str] = None, skill_id: Optional[uuid.UUID] = None,
                      db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    stmt = (select(SkillContribution).options(selectinload(SkillContribution.contributor))
            .where(SkillContribution.contributor_id == user.id, SkillContribution.status == "draft"))
    if skill_id:
        stmt = stmt.where(SkillContribution.skill_id == skill_id)
    elif title:
        stmt = stmt.where(SkillContribution.title == title)
    else:
        return None
    c = (await db.execute(stmt.order_by(SkillContribution.updated_at.desc()).limit(1))).scalars().first()
    return _to_response(c) if c else None


@router.post("/skill-contributions", response_model=SkillContributionResponse)
async def create_contribution(body: SkillContributionCreate, db: AsyncSession = Depends(get_db),
                              user=Depends(get_current_user)):
    if not _is_admin(user):
        perms = permission_engine._get_user_permissions(user)
        if "skill:create:all" not in perms and "skill:create:own_dept" not in perms:
            raise HTTPException(status_code=403, detail="Permission required: skill:create")
    if not (body.title or "").strip():
        raise HTTPException(status_code=400, detail="title is required")
    if body.skill_id is not None:
        skill = await db.get(Skill, body.skill_id)
        if skill is None:
            raise HTTPException(status_code=404, detail="Skill not found")
        if skill.is_system:
            raise HTTPException(status_code=403, detail="System skills cannot be modified via contributions")
    c = await contrib.create_contribution(
        db, body.skill_id, body.base_version, user.id, body.title.strip()[:200], body.scope_type or "global",
        body.scope_ids,
    )
    return _to_response(c)


@router.get("/admin/skill-contributions", response_model=list[SkillContributionResponse])
async def list_pending(skill_id: Optional[uuid.UUID] = None, db: AsyncSession = Depends(get_db),
                       user=require_permission(REVIEW_PERMISSION)):
    stmt = (select(SkillContribution).options(selectinload(SkillContribution.contributor))
            .where(SkillContribution.status == "pending"))
    if skill_id:
        stmt = stmt.where(SkillContribution.skill_id == skill_id)
    rows = (await db.execute(stmt.order_by(SkillContribution.created_at.desc()))).scalars().all()
    return [_to_response(c) for c in rows]


@router.get("/skill-contributions", response_model=list[SkillContributionResponse])
async def list_mine(status: Optional[str] = None, db: AsyncSession = Depends(get_db),
                    user=Depends(get_current_user)):
    stmt = (select(SkillContribution).options(selectinload(SkillContribution.contributor))
            .where(SkillContribution.contributor_id == user.id))
    if status:
        stmt = stmt.where(SkillContribution.status == status)
    rows = (await db.execute(stmt.order_by(SkillContribution.created_at.desc()))).scalars().all()
    return [_to_response(c) for c in rows]


# ---------------------------------------------------------------- single contribution


@router.get("/skill-contributions/{contribution_id}", response_model=SkillContributionResponse)
async def get_contribution(contribution_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                           user=Depends(get_current_user)):
    return _to_response(await _viewable(db, user, contribution_id))


@router.delete("/skill-contributions/{contribution_id}")
async def delete_contribution(contribution_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                              user=Depends(get_current_user)):
    c = await contrib.require_contribution(db, contribution_id)
    if not (_is_admin(user) or _is_owner(user, c)):
        raise HTTPException(status_code=403, detail="Access denied")
    if not _is_admin(user) and c.status == "approved":
        raise HTTPException(status_code=400, detail="Cannot delete an approved contribution")
    try:
        await contrib.run(storage_service.delete_prefix, _prefix(c))
    except Exception as e:
        logger.warning("could not delete storage of contribution %s: %s", c.id, e)
    await db.delete(c)
    await db.commit()
    return {"status": "ok"}


@router.get("/skill-contributions/{contribution_id}/files")
async def list_files(contribution_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                     user=Depends(get_current_user)):
    c = await _viewable(db, user, contribution_id)
    if c.status == "approved":
        raise HTTPException(status_code=400, detail="Cannot access contribution files in status: approved")
    if not c.storage_path:
        return []
    return [{"path": rel, "size": getattr(o, "size", 0) or 0, "is_text": _is_text(rel)}
            for rel, o in await contrib.list_rel(c.storage_path)]


@router.get("/skill-contributions/{contribution_id}/files/content")
async def read_file(contribution_id: uuid.UUID, path: str, db: AsyncSession = Depends(get_db),
                    user=Depends(get_current_user)):
    c = await _viewable(db, user, contribution_id)
    try:
        data = await contrib.run(storage_service.download_file, _prefix(c) + path.strip().lstrip("/"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {e}")
    return {"content": data.decode("utf-8", errors="ignore")}


@router.post("/skill-contributions/{contribution_id}/rename")
async def rename_path(contribution_id: uuid.UUID, old_path: str, new_path: str,
                      db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    c = await _editable(db, user, contribution_id)
    old = old_path.strip().strip("/")
    new = new_path.strip().strip("/")
    if "/" not in old or "/" not in new:
        raise HTTPException(status_code=400, detail="Cannot rename the root folder.")
    if old.lower().endswith("skill.md") and old.rsplit("/", 1)[-1].lower() == "skill.md":
        raise HTTPException(status_code=400, detail="Cannot rename SKILL.md.")
    if not contrib.is_safe_member(new):
        raise HTTPException(status_code=400, detail="Invalid file path.")
    prefix = _prefix(c)
    rels = {rel: o for rel, o in await contrib.list_rel(prefix)}
    if old in rels:
        await contrib.run(storage_service.copy_object, prefix + old, prefix + new)
        await contrib.run(storage_service.delete_object, prefix + old)
    else:
        await contrib.run(storage_service.move_prefix, prefix + old + "/", prefix + new + "/")
    await _commit_touch(db, c)
    return {"status": "ok", "old_path": old, "new_path": new, "contribution_status": c.status}


@router.delete("/skill-contributions/{contribution_id}/files")
async def delete_path(contribution_id: uuid.UUID, path: str, db: AsyncSession = Depends(get_db),
                      user=Depends(get_current_user)):
    c = await _editable(db, user, contribution_id)
    rel = path.strip().strip("/")
    prefix = _prefix(c)
    rels = {r for r, _ in await contrib.list_rel(prefix)}
    if rel in rels:
        await contrib.run(storage_service.delete_object, prefix + rel)
    await contrib.run(storage_service.delete_prefix, prefix + rel + "/")
    await _commit_touch(db, c)
    return {"status": "ok", "path": rel, "contribution_status": c.status}


@router.post("/skill-contributions/{contribution_id}/upload")
async def upload_file(contribution_id: uuid.UUID, path: Optional[str] = None, file: UploadFile = File(...),
                      db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    c = await _editable(db, user, contribution_id)
    data = await file.read()
    rel = await _write_file(db, c, path or file.filename or "file", data,
                            file.content_type or "application/octet-stream")
    return {"status": "ok", "path": rel, "contribution_status": c.status}


@router.put("/skill-contributions/{contribution_id}/files")
async def put_file(contribution_id: uuid.UUID, body: PutFileRequest, db: AsyncSession = Depends(get_db),
                   user=Depends(get_current_user)):
    c = await _editable(db, user, contribution_id)
    rel = await _write_file(db, c, body.path, body.content.encode("utf-8"), "text/plain")
    return {"status": "ok", "path": rel, "contribution_status": c.status}


# ---------------------------------------------------------------- review flow


@router.post("/skill-contributions/{contribution_id}/submit")
async def submit(contribution_id: uuid.UUID, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    c = await contrib.require_contribution(db, contribution_id)
    if not (_is_admin(user) or _is_owner(user, c)):
        raise HTTPException(status_code=403, detail="Access denied")
    if c.status not in ("draft", "needs_revision"):
        raise HTTPException(status_code=400, detail=f"Cannot submit contribution in status: {c.status}")
    c = await contrib.submit_contribution(db, c.id)
    await cs.notify_submitted(db, ADAPTER, c, user)
    await db.commit()
    return {"status": c.status}


@router.post("/skill-contributions/{contribution_id}/approve")
async def approve(contribution_id: uuid.UUID, body: Optional[SkillContributionApprove] = Body(None),
                  db: AsyncSession = Depends(get_db), user=require_permission(REVIEW_PERMISSION)):
    body = body or SkillContributionApprove()
    c = await contrib.get_contribution(db, contribution_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Contribution not found")
    if c.status in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="Contribution already approved")
    if not _is_admin(user):
        scope_type = body.final_scope_type or c.scope_type or "global"
        targets = body.final_scope_ids if body.final_scope_ids is not None else c.scope_ids
        if scope_type == "department":
            mine = permission_engine._as_uuid_set(permission_engine._user_department_ids(user))
            if not (permission_engine._as_uuid_set(targets) & mine):
                raise HTTPException(
                    status_code=403,
                    detail="You do not have permission to approve contributions for these departments. "
                           "Reviewer must belong to one of the target departments.",
                )
    skill = await contrib.approve_contribution(db, c.id, user.id, body.final_scope_type, body.final_scope_ids)
    c = await contrib.require_contribution(db, c.id)
    await cs.notify_approved(db, ADAPTER, c, user, version_label=f"v{skill.current_version}")
    await db.commit()
    return {"status": "approved", "skill_id": str(skill.id), "skill_slug": skill.slug,
            "version": skill.current_version}


@router.post("/skill-contributions/{contribution_id}/reject")
async def reject(contribution_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                 user=require_permission(REVIEW_PERMISSION)):
    c = await contrib.require_contribution(db, contribution_id)
    if c.status in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="Contribution already approved")
    c = await contrib.reject_contribution(db, c.id)
    await cs.notify_rejected(db, ADAPTER, c, user)
    await db.commit()
    return {"status": c.status}


@router.post("/skill-contributions/{contribution_id}/request-changes")
async def request_changes(contribution_id: uuid.UUID, body: RequestChangesSkillRequest,
                          db: AsyncSession = Depends(get_db), user=require_permission(REVIEW_PERMISSION)):
    c = await contrib.require_contribution(db, contribution_id)
    try:
        await cs.request_changes(db, ADAPTER, c, user, body.reviewer_note)
    except cs.InvalidTransition as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return {"status": c.status, "revision_round": c.revision_round or 0}


@router.post("/skill-contributions/{contribution_id}/resubmit")
async def resubmit(contribution_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                   user=Depends(get_current_user)):
    c = await contrib.require_contribution(db, contribution_id)
    try:
        await cs.resubmit_skill_contribution(db, c, user)
    except cs.InvalidTransition as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return {"status": c.status, "revision_round": c.revision_round or 0}


@router.post("/skill-contributions/{contribution_id}/withdraw")
async def withdraw(contribution_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                   user=Depends(get_current_user)):
    c = await contrib.require_contribution(db, contribution_id)
    try:
        await cs.withdraw(db, ADAPTER, c, user)
    except cs.InvalidTransition as e:
        raise HTTPException(status_code=403, detail=str(e))
    await db.commit()
    return {"status": c.status}


@router.get("/skill-contributions/{contribution_id}/diff-status")
async def diff_status(contribution_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                      user=Depends(get_current_user)):
    c = await _viewable(db, user, contribution_id)
    return await contrib.diff_status(db, c)
