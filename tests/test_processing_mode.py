import uuid
from types import SimpleNamespace
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
        ("articles", False, False, (False, True, False)),
        ("verbatim_page", False, True, (True, True, False)),
        ("verbatim_page", True, True, (True, True, False)),
        ("verbatim", True, False, (False, True, False)),
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
async def test_dispatch_legacy_personal_mode_also_runs_llm_and_embedding():
    from app import worker

    src = MagicMock()
    src.id = uuid.uuid4()
    src.preserve_verbatim = True
    src.scope_type = "personal"
    src.metadata_ = {processing_mode.KEY: "verbatim_page"}
    w = MagicMock()
    w.commit_and_enqueue_chunk_branch = AsyncMock()
    w.set_branch_state = AsyncMock(return_value="processing")
    w.enqueue_post_extraction_pipeline = AsyncMock()
    with patch.object(worker, "_self", return_value=w), \
         patch("app.services.doc_metadata_service.store_document_metadata", new_callable=AsyncMock), \
         patch("app.services.legal_service.is_legal_source", new_callable=AsyncMock, return_value=False), \
         patch("app.services.verbatim_page_service.finalize_verbatim_pages", new_callable=AsyncMock,
               return_value={"status": "ready"}) as fin:
        res = await worker.dispatch_dual_pipeline(AsyncMock(), src, AsyncMock(), token_count=10)
    fin.assert_not_awaited()
    w.commit_and_enqueue_chunk_branch.assert_awaited_once()
    w.enqueue_post_extraction_pipeline.assert_awaited_once()
    assert src.preserve_verbatim is False


@pytest.mark.asyncio
async def test_managing_department_validation_is_independent_of_visibility():
    from app.routers import sources
    dept, owner = uuid.uuid4(), uuid.uuid4()
    user = SimpleNamespace(id=owner,role="viewer",department_ids=[dept])
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(id=dept,name="PC08")
    with patch.object(sources,"_has_all",return_value=False):
        assert await sources._checked_managing_department(db,user,dept,"create") == dept
        with pytest.raises(Exception) as error:
            await sources._checked_managing_department(db,user,uuid.uuid4(),"create")
    assert getattr(error.value,"status_code",None) == 403


def test_processing_mode_is_auto_even_for_legacy_private_source():
    source = _src("verbatim", preserve=True)
    assert processing_mode.mode_of(source) == "auto"
    processing_mode.set_mode(source,"auto")
    assert source.preserve_verbatim is False


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
async def test_relink_leaves_duplicate_target_units_unresolved():
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
    assert out["linked_count"] == 0
    assert out["unresolved_count"] == 1
    assert out["ambiguous_count"] == 1
    assert rel.target_unit_id is None
    session.commit.assert_not_awaited()


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


# Upload metadata review and resumption regressions.
@pytest.mark.asyncio
@pytest.mark.parametrize("metadata_fails", [False, True])
async def test_legacy_review_flag_does_not_pause_automatic_processing(metadata_fails):
    from app import worker

    source = SimpleNamespace(id=uuid.uuid4(), attempt_id=uuid.uuid4(),
                             preserve_verbatim=False, metadata_={"upload_review": "pending"})
    session = AsyncMock()
    w = MagicMock()
    w.commit_and_enqueue_chunk_branch = AsyncMock()
    w.set_branch_state = AsyncMock(return_value="processing")
    w.enqueue_post_extraction_pipeline = AsyncMock(return_value="job")
    with patch.object(worker, "_self", return_value=w), \
         patch("app.services.legal_service.is_legal_source", new_callable=AsyncMock, return_value=False), \
         patch("app.services.doc_metadata_service.store_document_metadata", new_callable=AsyncMock,
               side_effect=RuntimeError("provider unavailable") if metadata_fails else None) as extract:
        result = await worker.dispatch_dual_pipeline(session, source, AsyncMock(), 120)
    assert result["status"] == "processing"
    assert "upload_review" not in source.metadata_
    extract.assert_awaited_once_with(session, source)
    w.commit_and_enqueue_chunk_branch.assert_awaited_once()
    w.enqueue_post_extraction_pipeline.assert_awaited_once()


def test_review_state_has_no_effect_on_old_uploads_and_retains_other_metadata():
    from app.services.upload_review_service import review_status, mark_reviewed

    source = SimpleNamespace(metadata_={"processing_mode": "articles", "doc": {"doc_number": "88/2025/QH15"}})
    assert review_status(source) is None
    source.metadata_["upload_review"] = "awaiting"
    mark_reviewed(source)
    assert review_status(source) == "approved"
    assert source.metadata_["doc"]["doc_number"] == "88/2025/QH15"
    assert source.metadata_["processing_mode"] == "articles"
    assert "doc_number" in source.metadata_["doc"]["manual_fields"]


def test_retry_cannot_bypass_pending_upload_review():
    from app.services.source_retry import pick_branch, NotRetryable

    source = SimpleNamespace(metadata_={"upload_review": "awaiting"})
    with pytest.raises(NotRetryable):
        pick_branch(source, "chunk")


@pytest.mark.asyncio
async def test_deferred_upload_review_is_not_deleted_by_cleanup():
    from app import worker

    source = SimpleNamespace(metadata_={"upload_review": "awaiting"})
    session = AsyncMock()
    session.execute.return_value = MagicMock()
    session.execute.return_value.scalars.return_value.all.return_value = [source]
    factory = MagicMock()
    factory.return_value.__aenter__.return_value = session
    with patch("app.database.async_session_factory", factory):
        removed = await worker.cleanup_orphan_awaiting_approval_cron({})
    assert removed == 0
    session.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_approve_upload_queues_resume_without_reextracting():
    from app.routers import sources

    source = SimpleNamespace(id=uuid.uuid4(), metadata_={"upload_review": "awaiting"},
                             status="awaiting_approval", attempt_id=uuid.uuid4(), title="Luật 88")
    session = AsyncMock()
    session.get.return_value = source
    with patch.object(sources, "can_access_document", new_callable=AsyncMock, return_value=True), \
         patch.object(sources, "_foreign_personal", return_value=False), \
         patch.object(sources, "_enqueue", new_callable=AsyncMock, return_value="job") as enqueue, \
         patch.object(sources, "log_audit", new_callable=AsyncMock):
        result = await sources.approve_upload_review(source.id, session, MagicMock())
    assert result["queued"] is True
    assert source.metadata_["upload_review"] == "approved"
    enqueue.assert_awaited_once_with("resume_upload_review_task", str(source.id), str(source.attempt_id))


@pytest.mark.asyncio
async def test_approve_upload_refuses_inaccessible_document():
    from fastapi import HTTPException
    from app.routers import sources

    session = AsyncMock()
    session.get.return_value = SimpleNamespace(id=uuid.uuid4())
    with patch.object(sources, "_foreign_personal", return_value=False), \
         patch.object(sources, "can_access_document", new_callable=AsyncMock, return_value=False), \
         patch.object(sources, "_enqueue", new_callable=AsyncMock) as enqueue:
        with pytest.raises(HTTPException) as error:
            await sources.approve_upload_review(uuid.uuid4(), session, MagicMock())
    assert error.value.status_code == 403
    enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_queue_failure_returns_document_to_review():
    from fastapi import HTTPException
    from app.routers import sources

    source = SimpleNamespace(id=uuid.uuid4(), metadata_={"upload_review": "awaiting"},
                             status="awaiting_approval", attempt_id=uuid.uuid4(), title="Luật 88")
    session = AsyncMock()
    session.get.return_value = source
    with patch.object(sources, "can_access_document", new_callable=AsyncMock, return_value=True), \
         patch.object(sources, "_foreign_personal", return_value=False), \
         patch.object(sources, "_enqueue", new_callable=AsyncMock, side_effect=RuntimeError("queue down")), \
         patch.object(sources, "log_audit", new_callable=AsyncMock):
        with pytest.raises(HTTPException) as error:
            await sources.approve_upload_review(source.id, session, MagicMock())
    assert error.value.status_code == 503
    assert source.metadata_["upload_review"] == "awaiting"
    assert source.status == "awaiting_approval"


@pytest.mark.asyncio
async def test_resume_uses_existing_text_and_rejects_stale_attempt():
    from app import worker

    source = SimpleNamespace(id=uuid.uuid4(), metadata_={"upload_review": "approved"}, extracted_token_count=123)
    session = AsyncMock()
    session.get.return_value = source
    session.execute.return_value = MagicMock()
    session.execute.return_value.scalar_one.return_value = 2
    factory = MagicMock()
    factory.return_value.__aenter__.return_value = session
    w = MagicMock()
    w.check_task_attempt_validity = AsyncMock(return_value=True)
    w.dispatch_dual_pipeline = AsyncMock(return_value={"status": "processing"})
    with patch("app.database.async_session_factory", factory), patch.object(worker, "_self", return_value=w):
        result = await worker.resume_upload_review_task({}, str(source.id), "attempt")
        assert result["status"] == "processing"
        assert w.dispatch_dual_pipeline.await_args.args[3] == 123
        assert w.dispatch_dual_pipeline.await_args.kwargs["n_images"] == 2
        w.dispatch_dual_pipeline.reset_mock()
        w.check_task_attempt_validity.return_value = False
        assert await worker.resume_upload_review_task({}, str(source.id), "old-attempt") is None
        w.dispatch_dual_pipeline.assert_not_awaited()
