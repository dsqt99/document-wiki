"""Task Failure Dead-Letter model and Stage Execution Timing tracking."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from loguru import logger
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models import Base


class TaskFailure(Base):
    """Dead-letter queue table for unrecoverable background task failures."""
    __tablename__ = "task_failures"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    attempt_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    task_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    error_type: Mapped[str] = mapped_column(String(255), nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    traceback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payload_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True
    )  # pending | resolved | retried
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_task_failures_status_created", "status", "created_at"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "source_id": str(self.source_id) if self.source_id else None,
            "attempt_id": self.attempt_id,
            "task_name": self.task_name,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "traceback": self.traceback,
            "payload_json": self.payload_json,
            "status": self.status,
            "retry_count": self.retry_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class SourceStageTiming(Base):
    """Detailed stage execution duration metrics per source."""
    __tablename__ = "source_stage_timings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    stage_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_source_stage_timings_source_stage", "source_id", "stage_name"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "source_id": str(self.source_id),
            "stage_name": self.stage_name,
            "duration_ms": self.duration_ms,
            "metadata_json": self.metadata_json,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


async def record_task_failure(
    session,
    task_name: str,
    error: BaseException,
    source_id: Optional[uuid.UUID] = None,
    attempt_id: Optional[str] = None,
    payload: Optional[dict] = None,
    tb: Optional[str] = None,
) -> TaskFailure:
    """Record an unrecoverable worker task failure to task_failures table."""
    import traceback as tb_module

    tb_str = tb or "".join(tb_module.format_exception(type(error), error, error.__traceback__))
    failure = TaskFailure(
        source_id=source_id,
        attempt_id=attempt_id,
        task_name=task_name,
        error_type=type(error).__name__,
        error_message=str(error),
        traceback=tb_str,
        payload_json=payload,
        status="pending",
        retry_count=0,
    )
    session.add(failure)
    try:
        await session.commit()
        logger.error(
            f"record_task_failure: Recorded failure for task '{task_name}' (source={source_id}): {error}"
        )
    except Exception as e:
        logger.critical(f"Failed to record task failure to database: {e}")
    return failure


async def record_stage_timing(
    session,
    source_id: uuid.UUID,
    stage_name: str,
    duration_ms: int,
    metadata: Optional[dict] = None,
) -> SourceStageTiming:
    """Record execution duration of a processing stage."""
    timing = SourceStageTiming(
        source_id=source_id,
        stage_name=stage_name,
        duration_ms=duration_ms,
        metadata_json=metadata or {},
    )
    session.add(timing)
    try:
        await session.commit()
    except Exception as e:
        logger.warning(f"Failed to record stage timing ({stage_name}) for source {source_id}: {e}")
    return timing
