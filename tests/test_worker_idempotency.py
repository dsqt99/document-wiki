import uuid
from types import SimpleNamespace

import pytest
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
    mock_exec.one_or_none.return_value = SimpleNamespace(attempt_id=current_attempt, wiki_attempt_id=None)
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
    mock_exec.one_or_none.return_value = SimpleNamespace(attempt_id=current_attempt, wiki_attempt_id=None)
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
    mock_exec.one_or_none.return_value = SimpleNamespace(attempt_id=current_attempt, wiki_attempt_id=None)
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



def _session_with(attempt_id, wiki_attempt_id):
    session = AsyncMock()
    exec_result = MagicMock()
    exec_result.one_or_none.return_value = SimpleNamespace(
        attempt_id=attempt_id, wiki_attempt_id=wiki_attempt_id,
    )
    session.execute.return_value = exec_result
    return session


@pytest.mark.asyncio
async def test_wiki_attempt_invalidates_only_old_wiki_jobs():
    """Retrying branch B rotates wiki_attempt_id: old wiki jobs drop, whole-source jobs don't."""
    sid = uuid.uuid4()
    attempt, old_wiki, new_wiki = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    session = _session_with(attempt, new_wiki)

    assert await check_task_attempt_validity(session, sid, str(new_wiki), branch="wiki") is True
    assert await check_task_attempt_validity(session, sid, str(old_wiki), branch="wiki") is False
    # A wiki job still carrying the global attempt is stale once a wiki attempt exists.
    assert await check_task_attempt_validity(session, sid, str(attempt), branch="wiki") is False
    # Branch A / whole-source jobs keep validating against attempt_id.
    assert await check_task_attempt_validity(session, sid, str(attempt)) is True


@pytest.mark.asyncio
async def test_wiki_attempt_falls_back_to_global_attempt():
    """Wiki jobs queued before wiki_attempt_id existed carry the global attempt."""
    sid = uuid.uuid4()
    attempt = uuid.uuid4()
    session = _session_with(attempt, None)

    assert await check_task_attempt_validity(session, sid, str(attempt), branch="wiki") is True
    assert await check_task_attempt_validity(session, sid, str(uuid.uuid4()), branch="wiki") is False
