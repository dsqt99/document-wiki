"""In-app notifications of the current user (06 §9.1)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import Notification
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationResponse(BaseModel):
    id: str
    type: str
    subject: str
    body: str = ""
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    actor_id: Optional[str] = None
    read_at: Optional[str] = None
    created_at: Optional[str] = None


def _iso(dt) -> Optional[str]:
    return dt.isoformat() if dt else None


def _out(n: Notification) -> NotificationResponse:
    return NotificationResponse(
        id=str(n.id), type=n.type, subject=n.subject, body=n.body or "",
        target_type=n.target_type, target_id=n.target_id,
        actor_id=str(n.actor_id) if n.actor_id else None,
        read_at=_iso(n.read_at), created_at=_iso(n.created_at),
    )


@router.get("", response_model=list[NotificationResponse])
async def list_notifications(
    unread: bool = False,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    stmt = select(Notification).where(Notification.recipient_id == user.id)
    if unread:
        stmt = stmt.where(Notification.read_at.is_(None))
    stmt = stmt.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit).offset(offset)
    rows = (await db.execute(stmt)).scalars().all()
    return [_out(n) for n in rows]


@router.get("/unread-count")
async def unread_count(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    count = (
        await db.execute(
            select(func.count()).select_from(Notification).where(
                Notification.recipient_id == user.id, Notification.read_at.is_(None)
            )
        )
    ).scalar()
    return {"count": int(count or 0)}


@router.post("/read-all")
async def mark_all_read(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    res = await db.execute(
        update(Notification)
        .where(Notification.recipient_id == user.id, Notification.read_at.is_(None))
        .values(read_at=datetime.now(timezone.utc))
    )
    await db.commit()
    return {"updated": int(res.rowcount or 0)}


@router.post("/{notification_id}/read", response_model=NotificationResponse)
async def mark_read(notification_id: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    try:
        nid = uuid.UUID(notification_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Notification not found")
    n = await db.get(Notification, nid)
    if n is None or n.recipient_id != user.id:
        raise HTTPException(status_code=404, detail="Notification not found")
    if n.read_at is None:
        n.read_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(n)
    return _out(n)
