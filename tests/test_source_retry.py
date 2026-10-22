import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routers.sources import retry_source
from app.services import source_retry
from app.services.wiki_write_guard import make_failure_stub


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


async def _call_retry(source, branch=None, uncaptioned=False):
    db = _mock_db(source)
    with patch("app.routers.sources.get_arq_pool") as mock_get_pool, \
         patch("app.routers.sources._to_response"), \
         patch("app.services.source_retry.has_uncaptioned_images", AsyncMock(return_value=uncaptioned)), \
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


@pytest.mark.asyncio
async def test_retry_wiki_with_uncaptioned_images_resumes_captioning():
    """A caption run stopped by an AI outage resumes at captioning, not MAP."""
    src = _mock_source(status="partial", chunk_status="ready", wiki_status="error")
    pool, chunk_enq = await _call_retry(src, uncaptioned=True)
    chunk_enq.assert_not_awaited()
    pool.enqueue_job.assert_called_once_with("caption_images_task", str(src.id), str(src.wiki_attempt_id))


@pytest.mark.parametrize("content, expected", [
    (make_failure_stub("Page", "APIConnectionError: Connection error."), True),
    (make_failure_stub("Page", "[ai_unavailable] model down"), True),
    (make_failure_stub("Page", "ValueError: invalid plan"), False),
    ("# Explaining APIConnectionError\n\nNormal document content.", False),
])
def test_legacy_outage_detected_only_in_failed_drafts(content, expected):
    src = _mock_source(error_message=None, wiki_error_message="All 1 page(s) failed to generate: page",
                       chunk_error_message=None)
    assert source_retry.failed_by_ai_outage(src, {"_page_drafts": [{"content_md": content}]}) is expected


@pytest.mark.asyncio
async def test_outage_cron_includes_legacy_failure_without_top_level_marker():
    src = _mock_source(error_message=None, wiki_error_message="All 1 page(s) failed to generate: page",
                       chunk_error_message=None)
    db = AsyncMock()
    first = MagicMock()
    first.scalars.return_value.all.return_value = [src]
    second = MagicMock()
    second.all.return_value = [(src.id, {"_page_drafts": [{
        "content_md": make_failure_stub("Page", "APIConnectionError: Connection error.")
    }]})]
    db.execute.side_effect = [first, second]
    factory = MagicMock()
    factory.return_value.__aenter__.return_value = db
    with patch("app.database.async_session_factory", factory), \
         patch.object(source_retry, "ai_ready", AsyncMock(return_value=(True, "ok"))), \
         patch.object(source_retry, "requeue_source", AsyncMock()) as requeue:
        result = await source_retry.retry_failed_sources(AsyncMock(), set(), only_ai_outage=True)
    assert result["requeued"] == [str(src.id)]
    requeue.assert_awaited_once()
