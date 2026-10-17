"""Audit log browsing and hash-chain verification (06 §10.1)."""

from __future__ import annotations

import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import AuditLog, Employee
from app.services.auth_service import require_permission

router = APIRouter(prefix="/audit", tags=["audit"])


_PageNo = Annotated[int, Query(ge=1)]
_PageSize = Annotated[int, Query(ge=1, le=200)]
_Session = Annotated[AsyncSession, Depends(get_db)]


def _audit_filters(
    principal_id: Optional[str], action: Optional[str], decision: Optional[str], resource_type: Optional[str]
) -> list:
    """Translate the optional query parameters into SQL predicates."""
    predicates: list = []
    if principal_id:
        try:
            wanted = uuid.UUID(principal_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid principal_id")
        predicates.append(AuditLog.principal_id == wanted)
    exact = ((AuditLog.action, action), (AuditLog.resource_type, resource_type))
    predicates.extend(column == value for column, value in exact if value)
    if decision:
        predicates.append(func.lower(AuditLog.decision) == decision.lower())
    return predicates


@router.get("/log")
async def list_audit_log(
    db: _Session,
    page: _PageNo = 1,
    page_size: _PageSize = 50,
    resource_type: Optional[str] = None,
    decision: Optional[str] = None,
    action: Optional[str] = None,
    principal_id: Optional[str] = None,
    user=require_permission("audit.read"),
):
    conds = _audit_filters(principal_id, action, decision, resource_type)

    total = (await db.execute(select(func.count()).select_from(AuditLog).where(*conds))).scalar() or 0
    stmt = (
        select(AuditLog, Employee.name, Employee.email)
        .outerjoin(Employee, Employee.id == AuditLog.principal_id)
        .where(*conds)
        .order_by(AuditLog.seq.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = []
    for row, name, email in (await db.execute(stmt)).all():
        items.append({
            "id": str(row.id),
            "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            "principal_id": str(row.principal_id) if row.principal_id else None,
            "principal_type": row.principal_type,
            "principal_name": name,
            "principal_email": email,
            "action": row.action,
            "resource_type": row.resource_type,
            "resource_id": row.resource_id,
            "decision": row.decision,
            "reason": row.reason,
            "seq": row.seq,
            "trace_id": row.trace_id,
            "event_hash": row.event_hash,
        })
    return {"items": items, "total": int(total), "page": page, "page_size": page_size}


@router.post("/verify")
async def verify_audit_chain(db: AsyncSession = Depends(get_db), user=require_permission("audit.read")):
    from app.services import audit_chain

    return await audit_chain.verify_chain(db)
