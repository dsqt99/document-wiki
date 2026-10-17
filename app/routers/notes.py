"""Free-form notes (/api/notes)."""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import Employee, Note
from app.services.auth_service import get_current_user, require_permission

router = APIRouter()

# The spec names legacy permissions kb.create / kb.delete; they map onto doc:*.
PERM_CREATE = "doc:create"
PERM_DELETE = "doc:delete"


class NoteIn(BaseModel):
    title: Optional[str] = None
    content: str
    note_type: str = "human"


def _iso(value) -> Optional[str]:
    return value.isoformat() if isinstance(value, datetime) else None


def _dto(note: Note) -> dict:
    return {
        "id": str(note.id),
        "title": note.title,
        "content": note.content,
        "note_type": note.note_type,
        "created_at": _iso(note.created_at),
        "updated_at": _iso(note.updated_at),
    }


@router.get("/notes")
async def list_notes(db: AsyncSession = Depends(get_db), user: Employee = Depends(get_current_user)):
    rows = (await db.execute(select(Note).order_by(Note.created_at.desc()))).scalars().all()
    return [_dto(n) for n in rows]


@router.post("/notes")
async def create_note(
    body: NoteIn,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission(PERM_CREATE),
):
    note = Note(title=body.title, content=body.content, note_type=body.note_type or "human")
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return _dto(note)


@router.delete("/notes/{note_id}")
async def delete_note(
    note_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission(PERM_DELETE),
):
    note = await db.get(Note, note_id)
    if note is None:
        raise HTTPException(404, "Note not found")
    await db.delete(note)
    await db.commit()
    return {"deleted": True}
