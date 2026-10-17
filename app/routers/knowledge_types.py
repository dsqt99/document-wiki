"""Knowledge type catalogue (/api/knowledge-types)."""

import re
import uuid
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import Employee, KnowledgeType, Source
from app.services.auth_service import require_permission

router = APIRouter()

DEFAULT_COLOR = "#6366f1"
_NOT_SLUG = re.compile(r"[^a-z0-9-]")

# The spec names legacy dotted permissions (documents.create, ...); they map onto doc:*.
PERM_CREATE = "doc:create"
PERM_EDIT = "doc:edit"
PERM_DELETE = "doc:delete"


class KnowledgeTypeIn(BaseModel):
    name: str
    slug: Optional[str] = None
    color: Optional[str] = DEFAULT_COLOR
    description: Optional[str] = None


def make_slug(value: str) -> str:
    return _NOT_SLUG.sub("", (value or "").lower().replace(" ", "-"))


def _dto(kt: KnowledgeType, source_count: int = 0) -> dict:
    return {
        "id": str(kt.id),
        "slug": kt.slug,
        "name": kt.name,
        "color": kt.color or DEFAULT_COLOR,
        "description": kt.description,
        "sort_order": kt.sort_order or 0,
        "source_count": int(source_count or 0),
    }


async def _slug_taken(db: AsyncSession, slug: str, exclude_id=None) -> bool:
    stmt = select(KnowledgeType.id).where(KnowledgeType.slug == slug)
    if exclude_id is not None:
        stmt = stmt.where(KnowledgeType.id != exclude_id)
    return (await db.execute(stmt)).first() is not None


@router.get("/knowledge-types")
async def list_knowledge_types(db: AsyncSession = Depends(get_db)):
    counts = dict(
        (await db.execute(
            select(Source.knowledge_type_id, func.count())
            .where(Source.knowledge_type_id.is_not(None))
            .group_by(Source.knowledge_type_id)
        )).all()
    )
    rows = (
        await db.execute(select(KnowledgeType).order_by(KnowledgeType.sort_order, KnowledgeType.name))
    ).scalars().all()
    return [_dto(kt, counts.get(kt.id, 0)) for kt in rows]


@router.post("/knowledge-types", status_code=201)
async def create_knowledge_type(
    body: KnowledgeTypeIn,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission(PERM_CREATE),
):
    slug = make_slug(body.slug if body.slug else body.name)
    if await _slug_taken(db, slug):
        raise HTTPException(409, f"Knowledge type with slug '{slug}' already exists")
    top = (await db.execute(select(func.max(KnowledgeType.sort_order)))).scalar()
    kt = KnowledgeType(
        slug=slug,
        name=body.name,
        color=body.color or DEFAULT_COLOR,
        description=body.description,
        sort_order=(top + 1) if top is not None else 1,
    )
    db.add(kt)
    await db.commit()
    await db.refresh(kt)
    return _dto(kt, 0)


@router.patch("/knowledge-types/reorder")
async def reorder_knowledge_types(
    ids: list[uuid.UUID] = Body(...),
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission(PERM_EDIT),
):
    existing = {
        row[0]
        for row in (await db.execute(select(KnowledgeType.id).where(KnowledgeType.id.in_(ids)))).all()
    } if ids else set()
    for position, kt_id in enumerate(ids):
        if kt_id in existing:
            await db.execute(update(KnowledgeType).where(KnowledgeType.id == kt_id).values(sort_order=position))
    await db.commit()
    return {"reordered": len(ids)}


async def _get_or_404(db: AsyncSession, kt_id: uuid.UUID) -> KnowledgeType:
    kt = await db.get(KnowledgeType, kt_id)
    if kt is None:
        raise HTTPException(404, "Knowledge type not found")
    return kt


@router.put("/knowledge-types/{kt_id}")
async def update_knowledge_type(
    kt_id: uuid.UUID,
    body: KnowledgeTypeIn,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission(PERM_EDIT),
):
    kt = await _get_or_404(db, kt_id)
    kt.name = body.name
    kt.color = body.color or DEFAULT_COLOR
    kt.description = body.description
    if body.slug:
        slug = make_slug(body.slug)
        if slug != kt.slug and await _slug_taken(db, slug, exclude_id=kt.id):
            raise HTTPException(409, f"Knowledge type with slug '{slug}' already exists")
        kt.slug = slug
    await db.commit()
    await db.refresh(kt)
    count = (
        await db.execute(select(func.count()).select_from(Source).where(Source.knowledge_type_id == kt.id))
    ).scalar() or 0
    return _dto(kt, count)


@router.delete("/knowledge-types/{kt_id}")
async def delete_knowledge_type(
    kt_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission(PERM_DELETE),
):
    kt = await _get_or_404(db, kt_id)
    slug = kt.slug
    await db.execute(update(Source).where(Source.knowledge_type_id == kt.id).values(knowledge_type_id=None))
    await db.delete(kt)
    await db.commit()
    return {"deleted": True, "slug": slug}
