import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routers.sources import retry_source


def _mock_source(**kw):
    src = MagicMock()
    src.id = uuid.uuid4()
    src.source_type = "file"
    src.minio_key = "test_key.pdf"
    src.auto_recover_count = 0
    src.full_text = "extracted text"
    src.preserve_verbatim = False
    src.pipeline_phase = None
    for k, v in kw.items():
        setattr(src, k, v)
    return src


def _mock_db(source):
    db = AsyncMock()
    db.get.return_value = source
    scalar_mock = MagicMock()
    scalar_mock.scalar_one_or_none.return_value = source
    scalar_mock.scalar_one.return_value = source
    db.execute.return_value = scalar_mock
    return db


async def _call_retry(source, branch=None):
    db = _mock_db(source)
    with patch("app.routers.sources.get_arq_pool") as mock_get_pool, \
         patch("app.routers.sources._to_response"), \
         patch("app.services.source_status.update_source_dual_status", AsyncMock()), \
         patch("app.worker.commit_and_enqueue_chunk_branch", AsyncMock()) as chunk_enq:
        pool = AsyncMock()
        job = MagicMock()
        job.job_id = "job_retry_123"
        pool.enqueue_job.return_value = job
        mock_get_pool.return_value = pool
        await retry_source(source_id=source.id, branch=branch, db=db, _user=MagicMock())
    return pool, chunk_enq


@pytest.mark.asyncio
async def test_retry_source_routes_to_map_reduce_when_prev_status_was_plan_ready():
    """plan_ready retry re-runs only branch B, starting at MAP (not a full re-ingest)."""
    old_wiki_attempt = uuid.uuid4()
    src = _mock_source(
        status="plan_ready", chunk_status="ready", wiki_status="plan_ready",
        wiki_attempt_id=old_wiki_attempt,
    )
    attempt = src.attempt_id
    pool, chunk_enq = await _call_retry(src)
    # Branch B gets a fresh wiki attempt; the global attempt (branch A) is kept.
    assert src.wiki_attempt_id != old_wiki_attempt
    assert src.attempt_id is attempt
    pool.enqueue_job.assert_called_once_with(
        "ingest_map_reduce_task", str(src.id), str(src.wiki_attempt_id)
    )
    chunk_enq.assert_not_awaited()
    assert src.wiki_status == "queued"


@pytest.mark.asyncio
async def test_retry_partial_chunk_failed_reruns_branch_a_only():
    src = _mock_source(status="partial", chunk_status="error", wiki_status="ready")
    pool, chunk_enq = await _call_retry(src)
    chunk_enq.assert_awaited_once()
    pool.enqueue_job.assert_not_called()


@pytest.mark.asyncio
async def test_retry_partial_wiki_failed_in_refine_resumes_refine():
    src = _mock_source(status="partial", chunk_status="ready", wiki_status="error", pipeline_phase="refine")
    pool, chunk_enq = await _call_retry(src)
    chunk_enq.assert_not_awaited()
    assert pool.enqueue_job.call_args.args[0] == "ingest_refine_task"


@pytest.mark.asyncio
async def test_retry_without_text_reingests_everything():
    src = _mock_source(status="error", chunk_status="pending", wiki_status="pending", full_text=None)
    pool, chunk_enq = await _call_retry(src)
    chunk_enq.assert_not_awaited()
    assert pool.enqueue_job.call_args.args[0] == "ingest_file_task"
    assert src.status == "pending"


@pytest.mark.asyncio
async def test_retry_all_starts_fresh_attempt():
    """A full re-ingest rotates attempt_id so jobs of the previous run go stale."""
    old_attempt = uuid.uuid4()
    src = _mock_source(status="error", chunk_status="error", wiki_status="error", attempt_id=old_attempt)
    pool, _ = await _call_retry(src, branch="all")
    assert src.attempt_id != old_attempt
    pool.enqueue_job.assert_called_once_with("ingest_file_task", str(src.id), str(src.attempt_id))
