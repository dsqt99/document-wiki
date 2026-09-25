import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.routers.sources import retry_source


@pytest.mark.asyncio
async def test_retry_source_routes_to_map_reduce_when_prev_status_was_plan_ready():
    """Verify that retrying a source with status 'plan_ready' routes to ingest_map_reduce_task, not ingest_file_task."""
    source_id = uuid.uuid4()
    mock_source = MagicMock()
    mock_source.id = source_id
    mock_source.status = "plan_ready"
    mock_source.pipeline_phase = None  # No phase set, relies on status
    mock_source.source_type = "file"
    mock_source.minio_key = "test_key.pdf"
    mock_source.auto_recover_count = 0

    mock_db = AsyncMock()
    mock_db.get.return_value = mock_source
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()
    
    scalar_mock = MagicMock()
    scalar_mock.scalar_one_or_none.return_value = mock_source
    scalar_mock.scalar_one.return_value = mock_source
    mock_db.execute.return_value = scalar_mock

    mock_user = MagicMock()
    mock_user.role = "admin"

    with patch("app.routers.sources.get_arq_pool") as mock_get_pool, \
         patch("app.routers.sources._to_response") as mock_resp:
        
        mock_pool = AsyncMock()
        mock_job = MagicMock()
        mock_job.job_id = "job_retry_123"
        mock_pool.enqueue_job.return_value = mock_job
        mock_get_pool.return_value = mock_pool

        await retry_source(source_id=source_id, db=mock_db, _user=mock_user)

        # Before fix: called with ingest_file_task because source.status was overwritten to "pending"
        # After fix: called with ingest_map_reduce_task
        mock_pool.enqueue_job.assert_called_once_with("ingest_map_reduce_task", str(source_id))
