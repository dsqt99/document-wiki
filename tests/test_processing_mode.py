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


def test_to_openai_tools_wraps_neutral_and_keeps_wrapped():
    from app.ai.agent_protocol import to_openai_tools

    neutral = {"name": "finish", "description": "d", "parameters": {"type": "object", "properties": {}}}
    wrapped = {"type": "function", "function": {"name": "x", "parameters": {}}}
    out = to_openai_tools([neutral, wrapped])
    assert out[0] == {"type": "function", "function": neutral}
    assert out[1] is wrapped


def test_verbatim_legal_page_detection():
    from app.ai.mrp.writer import is_verbatim_legal_page

    assert is_verbatim_legal_page("> **Căn cứ pháp lý**: Điều 1 — Luật 107/2025/QH15\n\nĐiều 1. ...")
    assert not is_verbatim_legal_page("# Cung cấp thông tin lý lịch tư pháp")
    assert not is_verbatim_legal_page(None)


@pytest.mark.asyncio
async def test_relink_tolerates_duplicate_target_units():
    from app.services.legal_relation_extractor import relink_legal_relations

    rel = MagicMock(target_doc_number="90/VBHN-VPQH", target_article_number="5",
                    target_clause_number="2", target_unit_id=None)
    art, clause, dup = MagicMock(id=uuid.uuid4()), MagicMock(id=uuid.uuid4()), MagicMock(id=uuid.uuid4())

    def _res(rows):
        r = MagicMock()
        r.scalars.return_value.all.return_value = rows
        r.scalars.return_value.first.return_value = rows[0] if rows else None
        r.scalar_one_or_none.side_effect = AssertionError("must tolerate duplicates")
        return r

    session = MagicMock()
    session.execute = AsyncMock(side_effect=[_res([rel]), _res([art, dup]), _res([clause, dup])])
    session.commit = AsyncMock()
    out = await relink_legal_relations(session)
    assert out == {"linked_count": 1, "unresolved_count": 0}
    assert rel.target_unit_id == clause.id


@pytest.mark.asyncio
async def test_vision_calls_share_one_process_limit():
    import asyncio
    from app.ai.providers import openai_provider

    openai_provider._vision_slots = None
    with patch.object(openai_provider, "settings", create=True), \
         patch("app.config.settings.vision_max_concurrency", 2):
        sem = openai_provider._vision_semaphore()
    assert sem is openai_provider._vision_semaphore()
    peak = cur = 0

    async def _call():
        nonlocal peak, cur
        async with openai_provider._vision_semaphore():
            cur += 1
            peak = max(peak, cur)
            await asyncio.sleep(0.01)
            cur -= 1

    await asyncio.gather(*(_call() for _ in range(8)))
    assert peak == 2
    openai_provider._vision_slots = None
