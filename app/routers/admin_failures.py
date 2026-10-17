"""Admin views over the dead-letter table and per-source stage timings."""

import inspect
import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import Employee
from app.models.task_failure import SourceStageTiming, TaskFailure
from app.services.auth_service import require_admin

router = APIRouter()

_FAILURE_STATUSES = ("pending", "resolved", "retried")
_STATUS_PATTERN = "^(" + "|".join(_FAILURE_STATUSES) + ")$"


@router.get("/admin/failures")
async def list_task_failures(
    user: Annotated[Employee, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    status: Annotated[Optional[str], Query(pattern=_STATUS_PATTERN)] = None,
    task_name: Annotated[Optional[str], Query()] = None,
):
    criteria = ((TaskFailure.task_name, task_name), (TaskFailure.status, status))
    filters = [column == wanted for column, wanted in criteria if wanted]

    total = (await db.execute(select(func.count()).select_from(TaskFailure).where(*filters))).scalar() or 0
    rows = (
        await db.execute(
            select(TaskFailure)
            .where(*filters)
            .order_by(TaskFailure.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()
    return {"total": total, "items": [r.to_dict() for r in rows], "offset": offset, "limit": limit}


@router.post("/admin/failures/{failure_id}/retry")
async def retry_task_failure(
    failure_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = Depends(require_admin),
):
    failure = (await db.execute(select(TaskFailure).where(TaskFailure.id == failure_id))).scalar_one_or_none()
    if failure is None:
        raise HTTPException(status_code=404, detail="Task failure record not found")

    from app import worker

    try:
        pool = worker.get_arq_pool()
        if inspect.isawaitable(pool):
            pool = await pool
        await pool.enqueue_job(failure.task_name, **(failure.payload_json or {}))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Failed to enqueue task: {e}") from e

    failure.status = "retried"
    failure.retry_count = int(failure.retry_count or 0) + 1
    await db.commit()
    return {
        "ok": True,
        "id": str(failure.id),
        "task_name": failure.task_name,
        "status": failure.status,
        "retry_count": failure.retry_count,
    }


@router.get("/admin/timings/{source_id}")
async def get_source_stage_timings(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = Depends(require_admin),
):
    rows = (
        await db.execute(
            select(SourceStageTiming)
            .where(SourceStageTiming.source_id == source_id)
            .order_by(SourceStageTiming.created_at.asc())
        )
    ).scalars().all()
    return {
        "source_id": str(source_id),
        "timings": [r.to_dict() for r in rows],
        "total_duration_ms": sum(int(r.duration_ms or 0) for r in rows),
    }
