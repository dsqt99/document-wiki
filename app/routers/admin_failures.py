"""Admin endpoints for monitoring dead-letter task failures and stage timings."""

import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import Employee
from app.models.task_failure import SourceStageTiming, TaskFailure
from app.services.auth_service import require_admin

router = APIRouter()


@router.get("/admin/failures")
async def list_task_failures(
    task_name: Optional[str] = Query(None, description="Filter by task name"),
    status: Optional[str] = Query(None, description="pending | resolved | retried"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: Employee = Depends(require_admin),
):
    """List unrecoverable task failures from dead-letter queue."""
    query = select(TaskFailure)
    count_query = select(func.count()).select_from(TaskFailure)

    if task_name:
        query = query.where(TaskFailure.task_name == task_name)
        count_query = count_query.where(TaskFailure.task_name == task_name)
    if status:
        query = query.where(TaskFailure.status == status)
        count_query = count_query.where(TaskFailure.status == status)

    total = (await db.execute(count_query)).scalar() or 0

    query = query.order_by(TaskFailure.created_at.desc()).offset(offset).limit(limit)
    rows = (await db.execute(query)).scalars().all()

    return {
        "total": total,
        "items": [r.to_dict() for r in rows],
        "offset": offset,
        "limit": limit,
    }


@router.post("/admin/failures/{failure_id}/retry")
async def retry_task_failure(
    failure_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = Depends(require_admin),
):
    """Re-enqueue a failed task into the worker queue and mark as retried."""
    failure = (
        await db.execute(select(TaskFailure).where(TaskFailure.id == failure_id))
    ).scalar_one_or_none()

    if not failure:
        raise HTTPException(status_code=404, detail="Task failure record not found")

    from app.worker import get_arq_pool

    try:
        redis = await get_arq_pool()
        payload = failure.payload_json or {}
        # Enqueue with original payload
        await redis.enqueue_job(failure.task_name, **payload)
    except Exception as exc:
        logger.error(f"Failed to redispatch task failure {failure_id}: {exc}")
        raise HTTPException(status_code=500, detail=f"Failed to enqueue task: {exc}")

    failure.status = "retried"
    failure.retry_count = (failure.retry_count or 0) + 1
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
    """Retrieve stage execution breakdown for a source document."""
    query = (
        select(SourceStageTiming)
        .where(SourceStageTiming.source_id == source_id)
        .order_by(SourceStageTiming.created_at.asc())
    )
    rows = (await db.execute(query)).scalars().all()

    timings = [r.to_dict() for r in rows]
    total_ms = sum(r.duration_ms for r in rows)

    return {
        "source_id": str(source_id),
        "timings": timings,
        "total_duration_ms": total_ms,
    }
