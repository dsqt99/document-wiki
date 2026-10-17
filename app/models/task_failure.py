"""Persistent records of worker task failures and per-stage pipeline timings."""

import logging
import traceback as _traceback
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models import Base

logger = logging.getLogger(__name__)


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


class TaskFailure(Base):
    __tablename__ = "task_failures"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="SET NULL"), nullable=True, index=True
    )
    attempt_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    task_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    error_type: Mapped[str] = mapped_column(String(255), nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    traceback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payload_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default="pending")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("ix_task_failures_status_created", "status", "created_at"),)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id) if self.id is not None else None,
            "source_id": str(self.source_id) if self.source_id is not None else None,
            "attempt_id": self.attempt_id,
            "task_name": self.task_name,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "traceback": self.traceback,
            "payload_json": self.payload_json,
            "status": self.status,
            "retry_count": self.retry_count,
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
        }


class SourceStageTiming(Base):
    __tablename__ = "source_stage_timings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    metadata_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_source_stage_timings_source_stage", "source_id", "stage_name"),)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id) if self.id is not None else None,
            "source_id": str(self.source_id) if self.source_id is not None else None,
            "stage_name": self.stage_name,
            "duration_ms": self.duration_ms,
            "metadata_json": self.metadata_json,
            "created_at": _iso(self.created_at),
        }


def _format_tb(error: BaseException) -> str:
    return "".join(_traceback.format_exception(type(error), error, error.__traceback__))


async def record_task_failure(
    session,
    task_name: str,
    error: BaseException,
    source_id=None,
    attempt_id=None,
    payload=None,
    tb: Optional[str] = None,
) -> TaskFailure:
    failure = TaskFailure(
        id=uuid.uuid4(),
        source_id=source_id,
        attempt_id=str(attempt_id) if attempt_id is not None else None,
        task_name=task_name,
        error_type=type(error).__name__,
        error_message=str(error),
        traceback=tb if tb else _format_tb(error),
        payload_json=payload,
        status="pending",
        retry_count=0,
    )
    session.add(failure)
    try:
        await session.commit()
    except Exception:
        logger.exception("Failed to persist task failure for %s", task_name)
    return failure


async def record_stage_timing(
    session,
    source_id,
    stage_name: str,
    duration_ms: int,
    metadata: Optional[dict] = None,
) -> SourceStageTiming:
    timing = SourceStageTiming(
        id=uuid.uuid4(),
        source_id=source_id,
        stage_name=stage_name,
        duration_ms=int(duration_ms),
        metadata_json=metadata or {},
    )
    session.add(timing)
    try:
        await session.commit()
    except Exception:
        logger.exception("Failed to persist stage timing %s", stage_name)
    return timing
