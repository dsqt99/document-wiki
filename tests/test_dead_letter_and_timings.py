"""Tests for TaskFailure dead-letter tracking, stage timings, and admin endpoints."""

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.task_failure import (
    TaskFailure,
    SourceStageTiming,
    record_task_failure,
    record_stage_timing,
)
from app.routers.admin_failures import (
    list_task_failures,
    retry_task_failure,
    get_source_stage_timings,
)


@pytest.mark.asyncio
async def test_record_task_failure():
    """Verify recording a dead-letter task failure."""
    mock_session = AsyncMock()
    src_id = uuid.uuid4()

    failure = await record_task_failure(
        session=mock_session,
        task_name="process_source_task",
        error=ValueError("Vision provider timeout"),
        source_id=src_id,
        attempt_id="job-12345",
        payload={"source_id": str(src_id)},
        tb="Traceback (most recent call last)...",
    )

    assert failure.task_name == "process_source_task"
    assert failure.error_type == "ValueError"
    assert "Vision provider timeout" in failure.error_message
    assert failure.source_id == src_id
    assert failure.status == "pending"
    assert failure.attempt_id == "job-12345"

    mock_session.add.assert_called_once_with(failure)
    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_record_stage_timing():
    """Verify recording stage execution timing."""
    mock_session = AsyncMock()
    src_id = uuid.uuid4()

    timing = await record_stage_timing(
        session=mock_session,
        source_id=src_id,
        stage_name="map_reduce",
        duration_ms=4250,
        metadata={"chunks_count": 12, "pages_compiled": 3},
    )

    assert timing.source_id == src_id
    assert timing.stage_name == "map_reduce"
    assert timing.duration_ms == 4250
    assert timing.metadata_json["chunks_count"] == 12

    mock_session.add.assert_called_once_with(timing)
    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_admin_list_failures():
    """Verify admin endpoint lists dead-letter task failures."""
    mock_session = AsyncMock()
    mock_count = MagicMock()
    mock_count.scalar.return_value = 1

    sample_failure = TaskFailure(
        id=uuid.uuid4(),
        task_name="caption_images_task",
        error_type="RuntimeError",
        error_message="CUDA out of memory",
        status="pending",
        retry_count=0,
    )
    mock_rows = MagicMock()
    mock_rows.scalars.return_value.all.return_value = [sample_failure]

    mock_session.execute.side_effect = [mock_count, mock_rows]

    mock_admin = MagicMock(role="admin")

    res = await list_task_failures(
        task_name=None,
        status="pending",
        limit=50,
        offset=0,
        db=mock_session,
        user=mock_admin,
    )

    assert res["total"] == 1
    assert len(res["items"]) == 1
    assert res["items"][0]["task_name"] == "caption_images_task"
    assert res["items"][0]["error_message"] == "CUDA out of memory"


@pytest.mark.asyncio
async def test_admin_retry_failure():
    """Verify admin endpoint redispatches a task failure."""
    mock_session = AsyncMock()
    fail_id = uuid.uuid4()
    src_id = uuid.uuid4()

    failure = TaskFailure(
        id=fail_id,
        source_id=src_id,
        task_name="generate_questions_task",
        error_type="TimeoutError",
        error_message="Redis disconnected",
        payload_json={"source_id": str(src_id)},
        status="pending",
        retry_count=0,
    )

    mock_get = MagicMock()
    mock_get.scalar_one_or_none.return_value = failure
    mock_session.execute.return_value = mock_get

    mock_admin = MagicMock(role="admin")

    with patch("app.worker.get_arq_pool", new_callable=AsyncMock) as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        res = await retry_task_failure(
            failure_id=fail_id,
            db=mock_session,
            user=mock_admin,
        )

        assert res["ok"] is True
        assert res["status"] == "retried"
        assert failure.status == "retried"
        assert failure.retry_count == 1
        mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_admin_get_source_timings():
    """Verify admin endpoint returns stage execution timings for a source."""
    mock_session = AsyncMock()
    src_id = uuid.uuid4()

    t1 = SourceStageTiming(
        id=uuid.uuid4(),
        source_id=src_id,
        stage_name="parse",
        duration_ms=850,
        metadata_json={"parser": "PDFParser"},
    )
    t2 = SourceStageTiming(
        id=uuid.uuid4(),
        source_id=src_id,
        stage_name="map_reduce",
        duration_ms=3100,
        metadata_json={"pages": 2},
    )

    mock_rows = MagicMock()
    mock_rows.scalars.return_value.all.return_value = [t1, t2]
    mock_session.execute.return_value = mock_rows

    mock_admin = MagicMock(role="admin")

    res = await get_source_stage_timings(
        source_id=src_id,
        db=mock_session,
        user=mock_admin,
    )

    assert res["source_id"] == str(src_id)
    assert len(res["timings"]) == 2
    assert res["total_duration_ms"] == 3950
    assert res["timings"][0]["stage_name"] == "parse"


@pytest.mark.asyncio
async def test_worker_task_failure_recording_integration():
    """Verify worker task failure is recorded to dead-letter on exception."""
    from app.worker import ingest_file_task
    import uuid

    sid = uuid.uuid4()
    mock_session = AsyncMock()

    mock_source = MagicMock()
    mock_source.id = sid
    mock_source.minio_key = "test/path.pdf"
    mock_source.file_name = "test.pdf"
    mock_source.attempt_id = uuid.uuid4()
    mock_session.get.return_value = mock_source

    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_session
    mock_session_factory.return_value.__aexit__.return_value = None

    with patch("app.database.async_session_factory", mock_session_factory), \
         patch("app.worker.check_task_attempt_validity", new_callable=AsyncMock, return_value=True), \
         patch("app.models.task_failure.record_task_failure", new_callable=AsyncMock) as mock_record_fail, \
         patch("app.services.storage_service.storage_service.download_file", side_effect=RuntimeError("MinIO connection failed")):

        with pytest.raises(RuntimeError, match="MinIO connection failed"):
            await ingest_file_task({}, str(sid), None)

        mock_record_fail.assert_awaited_once()
        call_kwargs = mock_record_fail.await_args.kwargs
        assert call_kwargs["task_name"] == "ingest_file_task"
        assert call_kwargs["source_id"] == sid
        assert isinstance(call_kwargs["error"], RuntimeError)

