"""Resolve wiki image references to short-lived same-origin URLs (/api/wiki/images/resolve)."""

import asyncio
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.database.models import Employee, Source, SourceImage
from app.services.auth_service import create_source_file_token, get_current_user
from app.services.permission_engine import can_access_document

logger = logging.getLogger(__name__)

router = APIRouter()
_optional_bearer = HTTPBearer(auto_error=False)

MAX_IDS_PER_REQUEST = 100


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

    decisions: dict = {}
    tickets: dict = {}
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
            if key not in tickets:
                tickets[key] = create_source_file_token(
                    str(user.id), str(key), session_claims=getattr(user, "_wiki_session_claims", None)
                )
            # Same-origin URL: MinIO presigned links point at an internal host the browser cannot reach.
            resolved[str(image.id)] = f"/api/wiki/images/{image.id}?token={tickets[key]}"
        except Exception as e:  # noqa: BLE001
            logger.warning("image ticket failed for %s: %s", image.id, e)
    return {"resolved": resolved, "denied": denied}


@router.get("/wiki/images/{image_id}")
async def get_wiki_image(
    image_id: uuid.UUID,
    token: Optional[str] = Query(None),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_bearer),
    db: AsyncSession = Depends(get_db),
):
    from app.routers.sources import _authenticate_request_user
    from app.services import storage_service as storage_module

    image = (
        await db.execute(
            select(SourceImage)
            .where(SourceImage.id == image_id)
            .options(selectinload(SourceImage.source).selectinload(Source.departments))
        )
    ).scalar_one_or_none()
    if image is None or image.source is None:
        raise HTTPException(404, "Image not found")
    user = await _authenticate_request_user(token, credentials, db, image.source_id)
    if not await can_access_document(db, user, image.source, "read"):
        raise HTTPException(403, "Access denied")
    try:
        data = await asyncio.to_thread(storage_module.storage_service.download_file, image.minio_key)
    except Exception as e:  # noqa: BLE001
        logger.error("download image %s failed: %s", image.id, e)
        raise HTTPException(500, "Failed to retrieve image from storage")
    return Response(content=data, media_type=image.content_type or "application/octet-stream",
                    headers={"Cache-Control": "private, max-age=600"})
