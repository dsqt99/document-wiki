import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routers import sources as sources_router
from app.services import processing_ops, source_retry


def _source(**kw):
    src = MagicMock()
    src.id = uuid.uuid4()
    src.source_type = "file"
    src.minio_key = "k.pdf"
    src.url = None
    src.auto_recover_count = 0
    src.error_message = None
    src.wiki_error_message = None
    src.chunk_error_message = None
    for k, v in kw.items():
        setattr(src, k, v)
    return src


def _factory(rows):
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    session.execute.return_value = result
    factory = MagicMock()
    factory.return_value.__aenter__.return_value = session
    factory.return_value.__aexit__.return_value = False
    return factory, session


@pytest.mark.asyncio
async def test_retry_failed_without_probe_skips_busy_cap_and_missing_file():
    ok, busy, capped, nofile = _source(), _source(), _source(auto_recover_count=99), _source(minio_key=None)
    factory, _ = _factory([ok, busy, capped, nofile])
    requeue = AsyncMock()
    with patch("app.database.async_session_factory", factory), \
         patch.object(source_retry, "ai_ready", AsyncMock()) as probe, \
         patch.object(source_retry, "requeue_source", requeue):
        out = await source_retry.retry_failed_sources(AsyncMock(), {busy.id}, probe=False, where=True)

    probe.assert_not_awaited()
    assert out["requeued"] == [str(ok.id)]
    assert out["skipped_busy"] == 1
    assert out["skipped_cap"] == 1
    assert out["skipped_other"] == [(str(nofile.id), "no file/url")]
    requeue.assert_awaited_once()


@pytest.mark.asyncio
async def test_retry_failed_admin_resets_cap():
    capped = _source(auto_recover_count=99)
    factory, _ = _factory([capped])
    with patch("app.database.async_session_factory", factory), \
         patch.object(source_retry, "requeue_source", AsyncMock()):
        out = await source_retry.retry_failed_sources(AsyncMock(), set(), reset_recover=True, probe=False)
    assert out["requeued"] == [str(capped.id)]
    assert capped.auto_recover_count == 0


@pytest.mark.asyncio
async def test_retry_failed_endpoint_scopes_to_readable_sources():
    user = MagicMock(role="manager")
    clause = object()
    db = AsyncMock()
    res = {"requeued": ["a", "b"], "skipped_busy": 1, "skipped_cap": 0, "skipped_other": [("c", "no file/url")],
           "probe": None}
    with patch.object(sources_router, "source_read_filter", return_value=(True, clause)), \
         patch.object(sources_router, "get_arq_pool", AsyncMock(return_value=MagicMock())), \
         patch("app.worker._source_ids_with_pending_jobs", AsyncMock(return_value={"busy"})), \
         patch.object(sources_router, "log_audit", AsyncMock()), \
         patch.object(source_retry, "retry_failed_sources", AsyncMock(return_value=res)) as retry:
        out = await sources_router.retry_failed(only_ai_outage=False, db=db, user=user)

    kwargs = retry.await_args.kwargs
    assert retry.await_args.args[1] == {"busy"}
    assert kwargs["where"] is clause and kwargs["probe"] is False
    assert kwargs["reset_recover"] is False  # only admins bypass the auto-recover cap
    assert out["requeued"] == 2
    assert out["skipped_other"] == [{"id": "c", "reason": "no file/url"}]
    assert "2 tài liệu" in out["message"] and "hàng đợi" in out["message"]


@pytest.mark.asyncio
async def test_reembed_missing_endpoint_enqueues_only_when_needed():
    db = AsyncMock()
    with patch.object(processing_ops, "missing_vector_page_ids", AsyncMock(return_value=[])), \
         patch.object(sources_router, "_enqueue", AsyncMock()) as enq:
        out = await sources_router.reembed_missing(db=db, user=MagicMock())
    assert out["candidates"] == 0
    enq.assert_not_awaited()

    job = MagicMock(job_id="j1")
    with patch.object(processing_ops, "missing_vector_page_ids", AsyncMock(return_value=[uuid.uuid4()] * 3)), \
         patch.object(sources_router, "log_audit", AsyncMock()), \
         patch.object(sources_router, "_enqueue", AsyncMock(return_value=job)) as enq:
        out = await sources_router.reembed_missing(db=db, user=MagicMock())
    enq.assert_awaited_once_with("reembed_missing_pages_task")
    assert out == {"job_id": "j1", "candidates": 3, "message": "Đã xếp hàng tạo vector cho 3 trang tri thức."}


@pytest.mark.asyncio
async def test_reembed_pages_keeps_going_after_a_failure():
    good, bad = uuid.uuid4(), uuid.uuid4()
    factory, session = _factory([])
    session.get.side_effect = lambda _model, pid: MagicMock(id=pid)

    async def index(_db, page):
        if page.id == bad:
            raise RuntimeError("embed down")
        return 3

    with patch("app.database.async_session_factory", factory), \
         patch("app.services.wiki_chunk_service.index_wiki_page_chunks", index):
        out = await processing_ops.reembed_pages([bad, good])
    assert out["done"] == 1
    assert out["failed"] == [(str(bad), "RuntimeError: embed down")]
    session.rollback.assert_awaited_once()


@pytest.mark.parametrize("message, expected", [
    ("[ai_unavailable] Dịch vụ AI 'llm' không phản hồi.", True),
    ("APIConnectionError: Connection error.", True),
    ("InternalServerError: Error code: 524 - origin timeout", True),
    ("TimeoutError", True),
    ("ValueError: plan has no pages", False),
])
def test_failed_by_ai_outage_counts_single_transport_failures(message, expected):
    assert source_retry.failed_by_ai_outage(_source(wiki_error_message=message)) is expected
