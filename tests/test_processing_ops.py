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


def _summary_page(**changes):
    from types import SimpleNamespace
    values = dict(id=uuid.uuid4(), slug="dieu-2-luat-a", title="Điều 2: Nguyên tắc - Luật A",
                  summary="Cũ…", content_md="> **Căn cứ pháp lý**: Điều 2 — Luật A\n\n"
                  "### Điều 2. Nguyên tắc\n\n1. " + "Nội dung đã sửa cần giữ đầy đủ " * 25 + ".\n\n2. Khoản hai.")
    return SimpleNamespace(**(values | changes))


def test_summary_rebuild_uses_current_legal_content_without_mutating_page():
    from app.services import wiki_summary_service as svc
    page = _summary_page()
    text = svc.build_summary(page)
    assert text.startswith("Điều 2: Nguyên tắc — 1. Nội dung đã sửa")
    assert len(text) > 400 and "Khoản hai" not in text and "Căn cứ pháp lý" not in text
    assert page.summary == "Cũ…"


def test_summary_rebuild_generic_keeps_complete_first_paragraph():
    from app.services import wiki_summary_service as svc
    body = "Thông tin mới " * 40 + "hết đoạn."
    page = _summary_page(slug="thu-tuc", content_md="# Thủ tục\n\n" + body + "\n\nĐoạn khác.")
    assert svc.build_summary(page) == body


@pytest.mark.parametrize("old, expected", [
    ("", True), ("Nội dung…", True), ("Nội dung...", True),
    ("Tóm tắt do người biên tập viết.", False),
])
def test_summary_rebuild_missing_mode_preserves_custom_summary(old, expected):
    from app.services import wiki_summary_service as svc
    assert svc.needs_summary_refresh(old, "Nội dung hiện tại đầy đủ.") is expected


def test_summary_rebuild_recognizes_old_hard_cut_only_when_prefix_matches():
    from app.services import wiki_summary_service as svc
    complete = "Nội dung " * 60 + "hoàn chỉnh."
    assert svc.needs_summary_refresh(complete[:180], complete)
    assert not svc.needs_summary_refresh("Khác " * 36, complete)


@pytest.mark.parametrize("text", [
    "Điều 19 — Nội dung gốc cũng kết thúc bằng...",
    "Điều 1 — Địa chỉ: ...............",
    "Điều 3 — Nơi nhận: ... (7)....",
])
def test_summary_source_dots_are_not_permanent_missing_candidates(text):
    from app.services import wiki_summary_service as svc
    assert not svc.needs_summary_refresh(text, text)
    assert not svc.needs_summary_refresh(text, "  " + text + "\n")


def test_summary_unavailable_text_is_not_queued_as_repairable():
    from app.services import wiki_summary_service as svc
    assert not svc.needs_summary_refresh("", "")
    assert not svc.needs_summary_refresh("Ancien...", "")


@pytest.mark.asyncio
async def test_summary_candidates_apply_read_scope_and_exclude_reserved_empty_pages():
    from app.services import wiki_summary_service as svc
    from app.database.models import WikiPage
    from sqlalchemy.dialects import postgresql
    rows = MagicMock()
    rows.scalars.return_value.all.return_value = [_summary_page(), _summary_page(summary="Tóm tắt riêng.")]
    db = AsyncMock(execute=AsyncMock(return_value=rows))
    pages = await svc.candidate_pages(db, WikiPage.scope_type == "department", only_missing=True)
    assert len(pages) == 1
    sql = str(db.execute.await_args.args[0].compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "department" in sql and "_index" in sql and "content_md" in sql


@pytest.mark.asyncio
async def test_wiki_library_applies_same_permissions_to_count_and_rows():
    from app.routers import wiki
    from app.database.models import WikiPage
    from sqlalchemy.dialects import postgresql
    count = MagicMock()
    count.scalar.return_value = 7
    rows = MagicMock()
    rows.scalars.return_value.all.return_value = []
    db = AsyncMock(execute=AsyncMock(side_effect=[count, rows]))
    with patch.object(wiki, "_page_read_filter", return_value=WikiPage.scope_type == "department"), \
         patch.object(wiki, "_scope_names", AsyncMock(return_value={})):
        result = await wiki.wiki_library(q="", source_id=None, page_type=None, status="mature",
                                         limit=30, offset=0, db=db, user=MagicMock())
    assert result["total"] == 7 and result["items"] == []
    for call in db.execute.await_args_list:
        sql = str(call.args[0].compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
        assert "department" in sql and "mature" in sql


class _SummaryRedis:
    def __init__(self):
        self.data = {}
        self.enqueue_job = AsyncMock(return_value=MagicMock(job_id="queued"))

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value, *, nx=False, ex=None):
        if nx and key in self.data:
            return False
        self.data[key] = value
        return True

    async def hset(self, key, *, mapping):
        self.data.setdefault(key, {}).update(mapping)

    async def hgetall(self, key):
        return self.data.get(key, {})

    async def expire(self, key, seconds):
        return True

    async def eval(self, script, key_count, key, expected, *args):
        if self.data.get(key) != expected:
            return 0
        if "'del'" in script:
            del self.data[key]
        return 1


@pytest.mark.asyncio
async def test_summary_job_deduplicates_start_and_hides_other_owners_status():
    from app.services import wiki_summary_service as svc
    redis = _SummaryRedis()
    owner = uuid.uuid4()
    clause = object()
    with patch.object(svc, "candidate_pages", AsyncMock(return_value=[_summary_page()])) as candidates:
        first = await svc.start_rebuild(AsyncMock(), redis, clause, owner)
        second = await svc.start_rebuild(AsyncMock(), redis, clause, owner)
    assert first["job_id"] == second["job_id"] and first["status"] == "queued"
    assert redis.enqueue_job.await_count == 1 and candidates.await_count == 1
    assert candidates.await_args.args[1] is clause
    assert await svc.get_job(redis, first["job_id"], uuid.uuid4()) is None
    assert "owner_id" not in first


@pytest.mark.asyncio
async def test_summary_job_empty_selection_completes_without_queueing():
    from app.services import wiki_summary_service as svc
    redis = _SummaryRedis()
    with patch.object(svc, "candidate_pages", AsyncMock(return_value=[])):
        result = await svc.start_rebuild(AsyncMock(), redis, None, "owner")
    assert result["status"] == "completed" and result["total"] == 0
    redis.enqueue_job.assert_not_awaited()
    assert await svc.active_job(redis, "owner") is None


@pytest.mark.asyncio
async def test_summary_queue_failure_releases_lock_and_reports_failure():
    from app.services import wiki_summary_service as svc
    redis = _SummaryRedis()
    redis.enqueue_job.side_effect = RuntimeError("redis queue down")
    with patch.object(svc, "candidate_pages", AsyncMock(return_value=[_summary_page()])):
        with pytest.raises(RuntimeError, match="redis queue down"):
            await svc.start_rebuild(AsyncMock(), redis, None, "owner")
    assert await svc.active_job(redis, "owner") is None
    import json
    job = next(json.loads(v) for k, v in redis.data.items() if ":job:" in k and isinstance(v, str))
    assert job["status"] == "failed"


@pytest.mark.asyncio
async def test_summary_worker_uses_current_content_and_continues_after_page_and_index_failure():
    from app.services import wiki_summary_service as svc
    redis = _SummaryRedis()
    bad, good = _summary_page(), _summary_page()
    with patch.object(svc, "candidate_pages", AsyncMock(return_value=[bad, good])):
        job = await svc.start_rebuild(AsyncMock(), redis, None, "owner")
    # The user edited the page after it was queued; worker must use the latest copy.
    good.content_md = "### Điều 2. Nguyên tắc\n\n1. Phiên bản mới nhất."
    original_content = good.content_md
    row_bad, row_good = MagicMock(), MagicMock()
    row_bad.scalar_one_or_none.return_value = bad
    row_good.scalar_one_or_none.return_value = good
    session = AsyncMock()
    session.execute.side_effect = [row_bad, row_good]
    factory = MagicMock()
    factory.return_value.__aenter__.return_value = session
    actual_build = svc.build_summary

    def build(page):
        if page is bad:
            raise ValueError("bad page")
        return actual_build(page)

    with patch("app.database.async_session_factory", factory), \
         patch.object(svc, "build_summary", side_effect=build), \
         patch("app.services.wiki_chunk_service.index_wiki_page_chunks", AsyncMock(side_effect=RuntimeError("embed down"))):
        result = await svc.run_rebuild({"redis": redis}, job["job_id"], [bad.id, good.id])
    assert result["status"] == "completed"
    assert (result["processed"], result["updated"], result["failed"], result["index_failed"]) == (2, 1, 1, 1)
    assert good.content_md == original_content and good.summary.endswith("Phiên bản mới nhất.")
    assert session.commit.await_count == 1  # summary remains saved when embedding fails
    assert await svc.active_job(redis, "owner") is None
    details = await svc.job_items(redis, job["job_id"], "owner", limit=10)
    assert [item["status"] for item in details["items"]] == ["failed", "index_failed"]
    assert "bad page" in details["items"][0]["message"]
    assert "embed down" in details["items"][1]["message"]


@pytest.mark.asyncio
async def test_summary_details_paginate_filter_and_reject_another_owner():
    from app.services import wiki_summary_service as svc
    redis = _SummaryRedis()
    pages = [_summary_page(title="Trang một"), _summary_page(title="Trang hai")]
    with patch.object(svc, "candidate_pages", AsyncMock(return_value=pages)):
        job = await svc.start_rebuild(AsyncMock(), redis, None, "owner")
    first = await svc.job_items(redis, job["job_id"], "owner", offset=0, limit=1)
    assert first["total"] == 2 and first["items"][0]["title"] == "Trang một"
    second = await svc.job_items(redis, job["job_id"], "owner", q="hai")
    assert second["total"] == 1 and second["items"][0]["status"] == "queued"
    assert await svc.job_items(redis, job["job_id"], "other") is None


@pytest.mark.asyncio
async def test_summary_details_include_document_name_and_recent_completed_job():
    from app.services import wiki_summary_service as svc
    from app.routers import wiki
    redis = _SummaryRedis()
    page, sid = _summary_page(), uuid.uuid4()
    page.source_ids = [sid]
    db = AsyncMock()
    db.execute.return_value = MagicMock()
    db.execute.return_value.all.return_value = [(sid, "Thông tư kiểm thử", "test.pdf")]
    with patch.object(svc, "candidate_pages", AsyncMock(return_value=[page])):
        job = await svc.start_rebuild(db, redis, None, "owner")
    details = await svc.job_items(redis, job["job_id"], "owner")
    assert details["items"][0]["source_titles"] == ["Thông tư kiểm thử"]
    with patch.object(wiki, "_summary_pool", AsyncMock(return_value=redis)):
        result = await wiki.wiki_summary_job_items(uuid.UUID(job["job_id"]), offset=0, limit=50, status=None, q=None, user=MagicMock(id="owner"))
    assert result["total"] == 1
    assert (await svc.recent_job(redis, "owner"))["job_id"] == job["job_id"]


@pytest.mark.asyncio
async def test_summary_same_content_reports_unchanged_instead_of_zero_success():
    from app.services import wiki_summary_service as svc
    redis = _SummaryRedis()
    page = _summary_page()
    page.summary = svc.build_summary(page)
    with patch.object(svc, "candidate_pages", AsyncMock(return_value=[page])):
        job = await svc.start_rebuild(AsyncMock(), redis, None, "owner", only_missing=False)
    session = AsyncMock()
    session.execute.return_value = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = page
    factory = MagicMock()
    factory.return_value.__aenter__.return_value = session
    with patch("app.database.async_session_factory", factory):
        result = await svc.run_rebuild({"redis": redis}, job["job_id"], [page.id])
    assert result["unchanged"] == 1 and result["updated"] == 0
    details = await svc.job_items(redis, job["job_id"], "owner")
    assert details["items"][0]["status"] == "unchanged"
    assert "khớp" in details["items"][0]["message"]


@pytest.mark.asyncio
async def test_summary_rebuild_endpoint_passes_read_scope_and_audits():
    from app.routers import wiki
    from app.services import wiki_summary_service as svc
    redis, db, user = _SummaryRedis(), AsyncMock(), MagicMock(id=uuid.uuid4())
    clause = object()
    with patch.object(wiki, "_summary_pool", AsyncMock(return_value=redis)), \
         patch.object(wiki, "_page_read_filter", return_value=clause), \
         patch.object(wiki, "log_audit", AsyncMock()) as audit, \
         patch.object(svc, "candidate_pages", AsyncMock(return_value=[_summary_page()])) as candidates:
        result = await wiki.rebuild_wiki_summaries(wiki.SummaryRebuildRequest(only_missing=False), db=db, user=user)
    assert result["status"] == "queued" and result["only_missing"] is False
    assert candidates.await_args.args[1] is clause
    audit.assert_awaited_once()


@pytest.mark.asyncio
async def test_summary_worker_is_registered():
    import app.worker as worker
    from app.tasks import wiki_tasks
    assert worker.rebuild_wiki_summaries_task in worker.WorkerSettings.functions
    with patch.object(wiki_tasks, "rebuild_wiki_summaries_task", AsyncMock(return_value={"status": "completed"})) as run:
        assert await worker.rebuild_wiki_summaries_task({}, "job", []) == {"status": "completed"}
    run.assert_awaited_once_with({}, "job", [])


@pytest.mark.asyncio
async def test_llm_summary_reads_all_clauses_and_preserves_full_output():
    import json
    from types import SimpleNamespace
    from app.services.llm_summary_service import summarize_page
    content = "# Điều 19\n\n1. Đào tạo lý thuyết...\n\n2. Học thực hành.\n\n3. Thời hạn 15 ngày."
    complete = "- Cơ sở tổ chức lý thuyết và thực hành.\n" + "- Học viên phải đăng ký đủ điều kiện.\n" * 12 + "- Thời hạn: 15 ngày."
    llm = SimpleNamespace(config=SimpleNamespace(spec=None, model_id="test"),
                          generate=AsyncMock(return_value=json.dumps({"summary": complete, "complete": True})))
    result = await summarize_page(llm, "Điều 19", content)
    assert result == complete and len(result) > 300
    assert content in llm.generate.await_args.args[0]
    assert "15 ngày" in llm.generate.await_args.args[0]


@pytest.mark.asyncio
async def test_llm_long_page_maps_every_byte_before_combining():
    import json
    from types import SimpleNamespace
    from app.services import llm_summary_service as svc
    content = "\n\n".join(f"Khoản {i}. Phải hoàn tất nghĩa vụ thứ {i}." for i in range(70))
    chunks = svc.split_content(content, 400)
    assert len(chunks) > 1 and "".join(chunks) == content
    llm = SimpleNamespace(config=SimpleNamespace(spec=None), generate=AsyncMock(
        return_value=json.dumps({"summary": "Các chủ thể phải thực hiện đầy đủ nghĩa vụ.", "complete": True})))
    with patch.object(svc, "input_budget", return_value=400):
        result = await svc.summarize_page(llm, "Quy định", content)
    prompts = [call.args[0] for call in llm.generate.await_args_list]
    assert all(any(chunk in prompt for prompt in prompts) for chunk in chunks)
    assert "nghĩa vụ" in result


@pytest.mark.asyncio
@pytest.mark.parametrize("output", ['{"summary":"Bị cắt...","complete":true}', '{"summary":"Thiếu phần kết.","complete":false}', '{"summary":"Cắt giữa câu'])
async def test_llm_summary_rejects_partial_responses(output):
    from types import SimpleNamespace
    from app.services.llm_summary_service import summarize_page
    llm = SimpleNamespace(config=SimpleNamespace(spec=None), generate=AsyncMock(return_value=output))
    with pytest.raises(ValueError, match="hoàn chỉnh"):
        await summarize_page(llm, "Điều 1", "1. Nội dung đầy đủ.\n\n2. Nghĩa vụ thứ hai.")


@pytest.mark.asyncio
async def test_llm_candidates_allow_one_page_and_include_source_dots():
    from app.services import wiki_summary_service as svc
    from sqlalchemy.dialects import postgresql
    page = _summary_page(content_md="Khoản một...\n\nKhoản hai.", summary="Khoản một...")
    rows = MagicMock()
    rows.scalars.return_value.all.return_value = [page]
    db = AsyncMock(execute=AsyncMock(return_value=rows))
    selected = await svc.candidate_pages(db, only_missing=True, engine="llm", page_ids=[page.id])
    assert selected == [page]
    sql = str(db.execute.await_args.args[0].compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert str(page.id) in sql


@pytest.mark.asyncio
async def test_llm_worker_does_not_hold_transaction_or_overwrite_concurrent_edit():
    from app.services import wiki_summary_service as svc
    redis, page = _SummaryRedis(), _summary_page()
    original = page.content_md
    with patch.object(svc, "candidate_pages", AsyncMock(return_value=[page])):
        job = await svc.start_rebuild(AsyncMock(), redis, None, "owner", only_missing=False, engine="llm")
    db = AsyncMock()
    db.execute.return_value = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = page
    factory = MagicMock()
    factory.return_value.__aenter__.return_value = db

    async def generate(*args, **kwargs):
        assert factory.return_value.__aexit__.await_count >= 1
        page.content_md = original + "\n\nNội dung vừa sửa."
        return "Bản tóm tắt AI của phiên bản cũ."

    with patch("app.database.async_session_factory", factory), \
         patch.object(svc, "generate_llm_summary", side_effect=generate):
        result = await svc.run_rebuild({"redis": redis}, job["job_id"], [str(page.id)])
    assert result["skipped"] == 1 and result["updated"] == 0
    assert page.summary == "Cũ…"
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_llm_worker_saves_full_summary_and_reports_failed_model_without_fallback():
    from app.services import wiki_summary_service as svc
    from app.services import wiki_chunk_service
    pages = [_summary_page(), _summary_page()]
    redis = _SummaryRedis()
    with patch.object(svc, "candidate_pages", AsyncMock(return_value=pages)):
        job = await svc.start_rebuild(AsyncMock(), redis, None, "owner", only_missing=False, engine="llm")
    db = AsyncMock()
    results = []
    for page in [pages[0], pages[0], pages[1]]:
        row = MagicMock()
        row.scalar_one_or_none.return_value = page
        results.append(row)
    db.execute.side_effect = results
    factory = MagicMock()
    factory.return_value.__aenter__.return_value = db
    complete = "Tóm tắt nội dung đầy đủ. " * 30
    with patch("app.database.async_session_factory", factory), \
         patch.object(svc, "generate_llm_summary", AsyncMock(side_effect=[complete, ValueError("LLM chưa hoàn chỉnh")])), \
         patch.object(wiki_chunk_service, "index_wiki_page_chunks", AsyncMock()) as index:
        result = await svc.run_rebuild({"redis": redis}, job["job_id"], [str(p.id) for p in pages])
    assert pages[0].summary == complete and pages[1].summary == "Cũ…"
    assert result["updated"] == 1 and result["failed"] == 1
    index.assert_awaited_once()


@pytest.mark.asyncio
async def test_llm_large_job_continues_without_reprocessing_finished_pages():
    from app.services import wiki_summary_service as svc
    redis = _SummaryRedis()
    pages = [_summary_page(summary="Tóm tắt không thay đổi.") for _ in range(6)]
    with patch.object(svc, "candidate_pages", AsyncMock(return_value=pages)):
        job = await svc.start_rebuild(AsyncMock(), redis, None, "owner", only_missing=False, engine="llm")
    db = AsyncMock()
    results = []
    for page in pages:
        row = MagicMock()
        row.scalar_one_or_none.return_value = page
        results.extend([row, row])
    db.execute.side_effect = results
    factory = MagicMock()
    factory.return_value.__aenter__.return_value = db
    ids = [str(p.id) for p in pages]
    with patch("app.database.async_session_factory", factory), \
         patch.object(svc, "generate_llm_summary", AsyncMock(return_value="Tóm tắt không thay đổi.")) as generate:
        first = await svc.run_rebuild({"redis": redis}, job["job_id"], ids)
        assert first["processed"] == 5 and first["status"] == "running"
        assert (await svc.active_job(redis, "owner"))["job_id"] == job["job_id"]
        second = await svc.run_rebuild({"redis": redis}, job["job_id"], ids)
    assert second["processed"] == 6 and second["unchanged"] == 6
    assert second["status"] == "completed" and generate.await_count == 6
    assert redis.enqueue_job.await_count == 2
    assert await svc.active_job(redis, "owner") is None
