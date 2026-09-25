import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.worker import check_task_attempt_validity, ingest_file_task


@pytest.mark.asyncio
async def test_check_task_attempt_validity_drops_stale_attempt():
    """Verify that a stale attempt_id is detected and returns False."""
    sid = uuid.uuid4()
    current_attempt = uuid.uuid4()
    old_attempt = uuid.uuid4()

    mock_session = AsyncMock()
    mock_exec = MagicMock()
    mock_exec.scalar_one_or_none.return_value = current_attempt
    mock_session.execute.return_value = mock_exec

    is_valid = await check_task_attempt_validity(mock_session, sid, str(old_attempt))
    assert is_valid is False


@pytest.mark.asyncio
async def test_check_task_attempt_validity_allows_matching_attempt():
    """Verify that a matching attempt_id returns True."""
    sid = uuid.uuid4()
    current_attempt = uuid.uuid4()

    mock_session = AsyncMock()
    mock_exec = MagicMock()
    mock_exec.scalar_one_or_none.return_value = current_attempt
    mock_session.execute.return_value = mock_exec

    is_valid = await check_task_attempt_validity(mock_session, sid, str(current_attempt))
    assert is_valid is True


@pytest.mark.asyncio
async def test_ingest_file_task_early_returns_on_stale_attempt():
    """Verify that ingest_file_task aborts immediately without downloading or modifying state when attempt is stale."""
    sid = uuid.uuid4()
    stale_attempt = uuid.uuid4()
    current_attempt = uuid.uuid4()

    fake_source = MagicMock()
    fake_source.id = sid
    fake_source.attempt_id = current_attempt
    fake_source.minio_key = "test/path.pdf"

    mock_session = AsyncMock()
    mock_session.get.return_value = fake_source

    mock_exec = MagicMock()
    mock_exec.scalar_one_or_none.return_value = current_attempt
    mock_session.execute.return_value = mock_exec

    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_session

    with patch("app.database.async_session_factory", mock_session_factory), \
         patch("app.ai.tracing.trace_context") as mock_trace, \
         patch("app.services.storage_service.storage_service.download_file") as mock_download:
        mock_trace.return_value.__aenter__.return_value = None

        await ingest_file_task({}, str(sid), attempt_id_str=str(stale_attempt))

        # download_file should NEVER be called because task dropped early
        mock_download.assert_not_called()

