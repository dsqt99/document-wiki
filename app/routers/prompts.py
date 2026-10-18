"""Prompt library (06 §4)."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, cast, func, or_, select
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import Department, Employee, PromptTemplate
from app.services import permission_engine
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/prompts", tags=["prompts"])

SCOPES = ("personal", "department", "global")
COMMAND_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,99}$")
MAX_TAGS = 20
MAX_TAG_LEN = 50
NOT_FOUND = "Không tìm thấy prompt"
COMMAND_ERROR = "Lệnh chỉ gồm chữ thường không dấu, số, '-' hoặc '_' (ví dụ: tom-tat-van-ban)"


class PromptIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    command: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=2000)
    content: str = Field(..., min_length=1, max_length=50000)
    tags: list[str] = Field(default_factory=list)
    scope_type: str = "personal"
    department_ids: list[uuid.UUID] = Field(default_factory=list)
    source: Optional[str] = Field(None, max_length=20)
    external_ref: Optional[str] = Field(None, max_length=200)


class PromptPatch(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    command: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=2000)
    content: Optional[str] = Field(None, min_length=1, max_length=50000)
    tags: Optional[list[str]] = None
    scope_type: Optional[str] = None
    department_ids: Optional[list[uuid.UUID]] = None


class PromptOut(BaseModel):
    id: uuid.UUID
    title: str
    command: Optional[str] = None
    description: Optional[str] = None
    content: str
    tags: list[str] = []
    scope_type: str
    department_ids: list[uuid.UUID] = []
    department_names: list[str] = []
    owner_id: Optional[uuid.UUID] = None
    owner_name: Optional[str] = None
    source: Optional[str] = None
    external_ref: Optional[str] = None
    can_edit: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


def normalize_command(raw: str) -> str:
    cmd = (raw or "").strip().lstrip("/").lower()
    if not COMMAND_RE.match(cmd):
        raise HTTPException(status_code=400, detail=COMMAND_ERROR)
    return cmd


def normalize_tags(tags) -> list[str]:
    out: list[str] = []
    for t in tags or []:
        t = str(t).strip()[:MAX_TAG_LEN].strip()
        if t and t not in out:
            out.append(t)
        if len(out) >= MAX_TAGS:
            break
    return out


def _clean_description(value: Optional[str]) -> Optional[str]:
    value = (value or "").strip()
    return value or None


def _perms(user) -> set:
    return permission_engine._get_user_permissions(user)


def _is_admin(user) -> bool:
    return getattr(user, "role", None) == "admin"


def _sees_all(user) -> bool:
    return _is_admin(user) or "skill:read:all" in _perms(user)


def _user_depts(user) -> set:
    return permission_engine._as_uuid_set(permission_engine._user_department_ids(user))


def can_view(user, p: PromptTemplate) -> bool:
    if _sees_all(user) or p.scope_type == "global" or p.owner_id == user.id:
        return True
    if p.scope_type == "department":
        return bool(permission_engine._as_uuid_set(p.department_ids) & _user_depts(user))
    return False


def can_modify(user, p: PromptTemplate, action: str = "edit") -> bool:
    return _is_admin(user) or p.owner_id == user.id or f"skill:{action}:all" in _perms(user)


def check_scope(user, scope_type: str, dept_ids) -> None:
    if scope_type not in SCOPES:
        raise HTTPException(status_code=400, detail="scope_type phải là personal, department hoặc global")
    if _is_admin(user):
        return
    create_all = "skill:create:all" in _perms(user)
    if scope_type == "global" and not create_all:
        raise HTTPException(status_code=403, detail="Bạn không có quyền tạo prompt toàn hệ thống")
    if scope_type == "department":
        wanted = permission_engine._as_uuid_set(dept_ids)
        if not wanted:
            raise HTTPException(status_code=400, detail="Chọn ít nhất một phòng ban")
        if not create_all and not wanted <= _user_depts(user):
            raise HTTPException(status_code=403, detail="Chỉ gán được cho phòng ban của bạn")


def _visibility_clause(user):
    clauses = [PromptTemplate.scope_type == "global", PromptTemplate.owner_id == user.id]
    depts = list(_user_depts(user))
    if depts:
        clauses.append(
            and_(PromptTemplate.scope_type == "department", PromptTemplate.department_ids.op("&&")(cast(depts, ARRAY(UUID(as_uuid=True)))))
        )
    return or_(*clauses)


async def _to_out(db, user, items: list) -> list[PromptOut]:
    dept_ids = {d for p in items for d in (p.department_ids or [])}
    owner_ids = {p.owner_id for p in items if p.owner_id}
    dept_names: dict = {}
    owner_names: dict = {}
    if dept_ids:
        rows = await db.execute(select(Department.id, Department.name).where(Department.id.in_(dept_ids)))
        dept_names = dict(rows.all())
    if owner_ids:
        rows = await db.execute(select(Employee.id, Employee.name).where(Employee.id.in_(owner_ids)))
        owner_names = dict(rows.all())
    out = []
    for p in items:
        ids = list(p.department_ids or [])
        out.append(PromptOut(
            id=p.id, title=p.title, command=p.command, description=p.description, content=p.content,
            tags=list(p.tags or []), scope_type=p.scope_type or "personal", department_ids=ids,
            department_names=[dept_names[d] for d in ids if d in dept_names],
            owner_id=p.owner_id, owner_name=owner_names.get(p.owner_id),
            source=p.source, external_ref=p.external_ref, can_edit=can_modify(user, p, "edit"),
            created_at=p.created_at, updated_at=p.updated_at,
        ))
    return out


async def _get_visible(db, user, prompt_id: uuid.UUID) -> PromptTemplate:
    p = await db.get(PromptTemplate, prompt_id)
    if p is None or not can_view(user, p):
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return p


@router.get("")
async def list_prompts(
    q: Optional[str] = None,
    scope_type: Optional[str] = None,
    department_id: Optional[uuid.UUID] = None,
    tag: Optional[str] = None,
    mine: bool = False,
    external_ref: Optional[str] = None,
    limit: int = Query(200, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    conds = []
    if not _sees_all(user):
        conds.append(_visibility_clause(user))
    if q and q.strip():
        like = f"%{q.strip()}%"
        conds.append(or_(
            PromptTemplate.title.ilike(like), PromptTemplate.command.ilike(like),
            PromptTemplate.description.ilike(like), PromptTemplate.content.ilike(like),
        ))
    if scope_type:
        conds.append(PromptTemplate.scope_type == scope_type)
    if department_id:
        conds.append(PromptTemplate.department_ids.any(department_id))
    if tag:
        conds.append(PromptTemplate.tags.any(tag))
    if mine:
        conds.append(PromptTemplate.owner_id == user.id)
    if external_ref:
        conds.append(PromptTemplate.external_ref == external_ref)

    total = (await db.execute(select(func.count()).select_from(PromptTemplate).where(*conds))).scalar() or 0
    rows = (
        await db.execute(
            select(PromptTemplate).where(*conds)
            .order_by(PromptTemplate.updated_at.desc(), PromptTemplate.id.desc()).limit(limit)
        )
    ).scalars().all()
    return {"items": await _to_out(db, user, list(rows)), "total": int(total)}


@router.get("/{prompt_id}", response_model=PromptOut)
async def get_prompt(prompt_id: uuid.UUID, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    p = await _get_visible(db, user, prompt_id)
    return (await _to_out(db, user, [p]))[0]


@router.post("", response_model=PromptOut)
async def create_prompt(body: PromptIn, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    dept_ids = list(dict.fromkeys(body.department_ids)) if body.scope_type == "department" else []
    check_scope(user, body.scope_type, dept_ids)
    command = normalize_command(body.command)

    existing = None
    if body.external_ref:
        existing = (
            await db.execute(
                select(PromptTemplate).where(
                    PromptTemplate.owner_id == user.id, PromptTemplate.external_ref == body.external_ref
                ).limit(1)
            )
        ).scalars().first()
    p = existing or PromptTemplate(
        id=uuid.uuid4(), owner_id=user.id, external_ref=body.external_ref,
        source=(body.source or "wiki")[:20],
    )
    p.title = body.title.strip()
    p.command = command
    p.description = _clean_description(body.description)
    p.content = body.content
    p.tags = normalize_tags(body.tags)
    p.scope_type = body.scope_type
    p.department_ids = dept_ids
    if existing is None:
        db.add(p)
    await db.commit()
    await db.refresh(p)
    return (await _to_out(db, user, [p]))[0]


@router.patch("/{prompt_id}", response_model=PromptOut)
async def update_prompt(
    prompt_id: uuid.UUID, body: PromptPatch, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)
):
    p = await _get_visible(db, user, prompt_id)
    if not can_modify(user, p, "edit"):
        raise HTTPException(status_code=403, detail="Bạn không có quyền sửa prompt này")
    if body.scope_type is not None or body.department_ids is not None:
        scope = body.scope_type if body.scope_type is not None else p.scope_type
        depts = body.department_ids if body.department_ids is not None else list(p.department_ids or [])
        depts = list(dict.fromkeys(depts)) if scope == "department" else []
        check_scope(user, scope, depts)
        p.scope_type = scope
        p.department_ids = depts
    if body.title is not None:
        p.title = body.title.strip()
    if body.command is not None:
        p.command = normalize_command(body.command)
    if body.description is not None:
        p.description = _clean_description(body.description)
    if body.content is not None:
        p.content = body.content
    if body.tags is not None:
        p.tags = normalize_tags(body.tags)
    await db.commit()
    await db.refresh(p)
    return (await _to_out(db, user, [p]))[0]


@router.delete("/{prompt_id}")
async def delete_prompt(prompt_id: uuid.UUID, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    p = await _get_visible(db, user, prompt_id)
    if not can_modify(user, p, "delete"):
        raise HTTPException(status_code=403, detail="Bạn không có quyền xóa prompt này")
    await db.delete(p)
    await db.commit()
    return {"message": "Đã xóa prompt"}
