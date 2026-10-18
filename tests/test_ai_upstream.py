import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai import upstream


@pytest.fixture(autouse=True)
def _reset_breaker():
    upstream.reset()
    yield
    upstream.reset()


def test_breaker_opens_after_consecutive_transient_failures():
    for _ in range(upstream.FAILURES_TO_OPEN - 1):
        upstream.record_failure("m", TimeoutError())
    assert not upstream.is_open("m")
    upstream.record_failure("m", ConnectionError())
    assert upstream.is_open("m")
    with pytest.raises(upstream.UpstreamUnavailable) as e:
        upstream.ensure_available("m")
    assert upstream.AI_UNAVAILABLE_MARKER in str(e.value)
    assert not upstream.is_open("other")


def test_breaker_ignores_request_errors_and_resets_on_success():
    for _ in range(5):
        upstream.record_failure("m", ValueError("bad prompt"))
    assert not upstream.is_open("m")
    upstream.record_failure("m", TimeoutError())
    upstream.record_failure("m", TimeoutError())
    upstream.record_success("m")
    upstream.record_failure("m", TimeoutError())
    assert not upstream.is_open("m")


def test_5xx_is_transient_4xx_is_not():
    err = Exception()
    err.status_code = 500
    assert upstream.is_transient(err)
    err.status_code = 400
    assert not upstream.is_transient(err)


def test_worker_recognises_outage_through_wrapping():
    from app.worker import _is_ai_outage

    assert _is_ai_outage(upstream.UpstreamUnavailable("ocr"))
    assert _is_ai_outage(ValueError(f"LibreOffice path failed: {upstream.UpstreamUnavailable('ocr')}"))
    assert not _is_ai_outage(ValueError("corrupt pdf"))


def _row(caption=None):
    row = MagicMock()
    row.id = uuid.uuid4()
    row.caption = caption
    row.minio_key = "k"
    row.content_type = "image/png"
    return row


@pytest.mark.asyncio
async def test_caption_task_stops_on_outage_and_keeps_existing_captions():
    from app.worker import caption_images_task

    sid = str(uuid.uuid4())
    done, todo = _row("đã có mô tả"), _row()
    source = MagicMock()
    source.full_text = f"![]({'image://' + str(done.id)}) ![](image://{todo.id})"
    session = AsyncMock()
    session.get.return_value = source
    result = MagicMock()
    result.scalars.return_value.all.return_value = [done, todo]
    session.execute.return_value = result
    factory = MagicMock()
    factory.return_value.__aenter__.return_value = session
    factory.return_value.__aexit__.return_value = False

    with patch("app.database.async_session_factory", factory), \
         patch("app.ai.registry.ProviderRegistry.get_vision", new_callable=AsyncMock, return_value=MagicMock()), \
         patch("app.worker.check_task_attempt_validity", AsyncMock(return_value=True)), \
         patch("app.worker._caption_one", AsyncMock(side_effect=upstream.UpstreamUnavailable("vl"))) as one, \
         patch("app.services.image_service.index_image_chunks", AsyncMock()), \
         patch("app.worker.mark_wiki_error", AsyncMock()) as mark, \
         patch("app.worker._chain_to_mrp", AsyncMock()) as chain:
        out = await caption_images_task({}, sid)

    assert out["reason"] == "ai_unavailable"
    one.assert_awaited_once()  # the captioned row is not sent to vision again
    assert "[đã có mô tả]" in source.full_text
    chain.assert_not_awaited()
    assert upstream.AI_UNAVAILABLE_MARKER in mark.await_args.args[1]
