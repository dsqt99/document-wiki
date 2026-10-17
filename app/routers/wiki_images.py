"""Resolve wiki image references to short-lived presigned URLs (/api/wiki/images/resolve)."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.database.models import Employee, Source, SourceImage
from app.services.auth_service import get_current_user
from app.services.permission_engine import can_access_document

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_IDS_PER_REQUEST = 100
PRESIGN_EXPIRY_HOURS = 1


class ResolveRequest(BaseModel):
    ids: list[uuid.UUID] = Field(default_factory=list)


@router.post("/wiki/images/resolve")
async def resolve_wiki_images(
    body: ResolveRequest,
    db: AsyncSession = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    ids = list(body.ids or [])
    if not ids:
        return {"resolved": {}, "denied": []}
    if len(ids) > MAX_IDS_PER_REQUEST:
        raise HTTPException(400, f"Too many ids (max {MAX_IDS_PER_REQUEST} per request)")

    unique = list(dict.fromkeys(ids))
    stmt = (
        select(SourceImage)
        .where(SourceImage.id.in_(unique))
        .options(selectinload(SourceImage.source).selectinload(Source.departments))
    )
    images = (await db.execute(stmt)).scalars().all()

    from app.services import storage_service as storage_module

    decisions: dict = {}
    resolved: dict[str, str] = {}
    denied: list[str] = []
    for image in images:
        source = image.source
        key = image.source_id
        if key not in decisions:
            decisions[key] = source is not None and await can_access_document(db, user, source, "read")
        if not decisions[key]:
            denied.append(str(image.id))
            continue
        try:
            resolved[str(image.id)] = storage_module.storage_service.get_presigned_url(
                image.minio_key, expiry_hours=PRESIGN_EXPIRY_HOURS
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("presign failed for image %s: %s", image.id, e)
    return {"resolved": resolved, "denied": denied}
