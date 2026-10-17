import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import processing_mode
from app.services.verbatim_page_service import split_parts


def _src(mode=None, preserve=False, attempt=None):
    s = MagicMock()
    s.id = uuid.uuid4()
    s.preserve_verbatim = preserve
    s.metadata_ = {processing_mode.KEY: mode} if mode else None
    s.wiki_attempt_id = attempt
    return s


def test_normalize_rejects_unknown_mode():
    assert processing_mode.normalize(None) is None
    assert processing_mode.normalize(" Verbatim_Page ") == "verbatim_page"
    with pytest.raises(ValueError):
        processing_mode.normalize("magic")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode,preserve,legal,expected",
    [
        (None, False, True, (True, True, False)),
        (None, False, False, (False, True, False)),
        ("articles", False, False, (True, False, False)),
        ("verbatim_page", False, True, (False, False, True)),
        ("verbatim_page", True, True, (False, False, False)),
    ],
)
async def test_plan_for(mode, preserve, legal, expected):
    with patch("app.services.legal_service.is_legal_source", new_callable=AsyncMock, return_value=legal):
        plan = await processing_mode.plan_for(MagicMock(), _src(mode, preserve))
    assert tuple(plan) == expected


def test_articles_done_tracks_wiki_attempt():
    attempt = uuid.uuid4()
    s = _src(attempt=attempt)
    processing_mode.mark_articles_done(s)
    assert processing_mode.articles_done(s, str(attempt))
    assert not processing_mode.articles_done(s, str(uuid.uuid4()))


def test_split_parts_keeps_images_and_prefers_headings():
    img = "![Sơ đồ](image://0b8f2c3e-1111-2222-3333-444455556666)"
    blocks = [f"## Mục {i}\n\n" + ("Nội dung đoạn văn dài. " * 20) + f"\n\n{img}" for i in range(1, 9)]
    text = "\n\n".join(blocks)
    parts = split_parts(text, 1500)
    assert len(parts) > 1
    assert all(len(p) <= 1500 for p in parts)
    assert "\n\n".join(parts).count(img) == 8
    assert all(p.startswith("## Mục") for p in parts)


def test_split_parts_single_page_when_short():
    assert split_parts("Ngắn gọn.\n\n![a](image://x)", 40000) == ["Ngắn gọn.\n\n![a](image://x)"]


@pytest.mark.asyncio
async def test_dispatch_auto_legal_runs_articles_then_llm():
    from app import worker

    src = MagicMock()
    src.id = uuid.uuid4()
    src.preserve_verbatim = False
    src.metadata_ = None
    w = MagicMock()
    w.commit_and_enqueue_chunk_branch = AsyncMock()
    w.set_branch_state = AsyncMock(return_value="processing")
    w.enqueue_post_extraction_pipeline = AsyncMock(return_value="job-1")
    with patch.object(worker, "_self", return_value=w), \
         patch("app.services.legal_service.is_legal_source", new_callable=AsyncMock, return_value=True), \
         patch("app.services.legal_service.finalize_legal_source", new_callable=AsyncMock) as fin:
        await worker.dispatch_dual_pipeline(AsyncMock(), src, AsyncMock(), token_count=10)
    assert fin.await_args.kwargs["final"] is False
    w.enqueue_post_extraction_pipeline.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_verbatim_page_skips_llm():
    from app import worker

    src = MagicMock()
    src.id = uuid.uuid4()
    src.preserve_verbatim = False
    src.metadata_ = {processing_mode.KEY: "verbatim_page"}
    w = MagicMock()
    w.commit_and_enqueue_chunk_branch = AsyncMock()
    w.set_branch_state = AsyncMock(return_value="processing")
    w.enqueue_post_extraction_pipeline = AsyncMock()
    with patch.object(worker, "_self", return_value=w), \
         patch("app.services.doc_metadata_service.store_document_metadata", new_callable=AsyncMock), \
         patch("app.services.verbatim_page_service.finalize_verbatim_pages", new_callable=AsyncMock,
               return_value={"status": "ready"}) as fin:
        res = await worker.dispatch_dual_pipeline(AsyncMock(), src, AsyncMock(), token_count=10)
    assert res == {"status": "ready"}
    fin.assert_awaited_once()
    w.enqueue_post_extraction_pipeline.assert_not_awaited()


def test_part_label_skips_broken_lowercase_heading():
    from app.services.verbatim_page_service import _first_heading

    assert _first_heading("## tiện\n\nabc\n\n## Mục 7\n\nxyz") == "Mục 7"
    assert _first_heading("không có tiêu đề") is None
