from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import pytest


def source(**kw):
    return SimpleNamespace(**{**dict(metadata_={}, attempt_id=None, chunk_attempt_id=None,
                           wiki_attempt_id=None, chunk_status="ready", wiki_status="ready"), **kw})


def quality_result(src):
    result = MagicMock()
    result.one_or_none.return_value = src
    return result


def test_legacy_ready_has_unknown_coverage():
    from app.services.source_quality import public_source_quality
    report = public_source_quality(source())
    assert report["source_index"] == {"status": "unknown", "expected": None, "indexed": None}
    assert report["wiki"]["status"] == "unknown"
    assert report["extraction"]["total_pages"] is None


def test_partial_extraction_counts_empty_and_ocr_and_page_limit():
    from app.services.source_quality import record_extraction, public_source_quality
    src = source()
    record_extraction(src, [{"content": "Native", "is_ocr": False, "total_doc_pages": 4},
                            {"content": "", "is_ocr": False, "total_doc_pages": 4},
                            {"content": "OCR", "is_ocr": True, "total_doc_pages": 4}])
    report = public_source_quality(src)
    assert report["extraction"] == {"status": "partial", "total_pages": 4,
                                     "text_pages": 2, "empty_pages": 1, "ocr_pages": 1}
    assert {w["code"] for w in report["warnings"]} >= {"empty_pages", "unprocessed_pages"}


def test_retry_does_not_reuse_old_branch_counters():
    from app.services.source_quality import record_quality, public_source_quality
    src = source()
    record_quality(src, "wiki", {"status": "complete", "expected": 3, "published": 3, "failed": 0})
    src.wiki_attempt_id = uuid.uuid4()
    assert public_source_quality(src)["wiki"]["published"] is None


def test_inconsistent_measured_complete_is_partial():
    from app.services.source_quality import record_quality, public_source_quality
    src = source()
    record_quality(src, "source_index", {"status": "complete", "expected": 4, "indexed": 2})
    assert public_source_quality(src)["source_index"]["status"] == "partial"


def test_unknown_counters_never_mean_complete():
    from app.services.source_quality import record_quality, public_source_quality
    src = source()
    record_quality(src, "wiki", {"status": "complete", "expected": None, "published": 1, "failed": None})
    assert public_source_quality(src)["wiki"]["status"] == "unknown"
    record_quality(src, "extraction", {"status": "complete", "total_pages": 1,
                                      "text_pages": 1, "empty_pages": 0, "ocr_pages": None})
    assert public_source_quality(src)["extraction"]["status"] == "unknown"


def test_measured_index_failure_remains_visible_before_branch_finalization():
    from app.services.source_quality import record_quality, public_source_quality
    src = source(chunk_status="embedding")
    record_quality(src, "source_index", {"status": "error", "expected": 2, "indexed": 0})
    assert public_source_quality(src)["source_index"]["status"] == "error"


@pytest.mark.asyncio
async def test_expired_approval_keeps_database_and_original():
    from app.worker import cleanup_orphan_awaiting_approval_cron
    src = source(id=uuid.uuid4(), minio_key="original.pdf", wiki_status="awaiting_approval")
    db = AsyncMock()
    rows = MagicMock()
    rows.scalars.return_value.all.return_value = [src]
    db.execute.return_value = rows
    factory = MagicMock()
    factory.return_value.__aenter__.return_value = db
    with patch("app.database.async_session_factory", factory), patch(
        "app.services.storage_service.storage_service.delete_object"
    ) as delete_object:
        assert await cleanup_orphan_awaiting_approval_cron({}) == 0
    db.delete.assert_not_awaited()
    delete_object.assert_not_called()
    assert src.metadata_["processing_quality"]["review_expired"] is True
    assert src.wiki_status == "awaiting_approval"


def test_expiry_warning_disappears_after_approval_resumes_processing():
    from app.services.source_quality import public_source_quality
    src = source(wiki_status="awaiting_approval", status="awaiting_approval",
                 metadata_={"processing_quality": {"review_expired": True}})
    assert any(w["code"] == "review_expired" for w in public_source_quality(src)["warnings"])
    src.wiki_status = "processing"
    src.status = "processing"
    assert not any(w["code"] == "review_expired" for w in public_source_quality(src)["warnings"])


@pytest.mark.asyncio
async def test_verify_marks_broken_citation_as_publication_blocker():
    from app.ai.mrp.verifier import run_verify_phase
    from app.ai.mrp.writer import PageWriteResult
    row = PageWriteResult("test", "Test", "concept", "CREATE", "Quy định này phải áp dụng [^s1].", "")
    await run_verify_phase(AsyncMock(), source(), [row], [], "Quy định này phải áp dụng.", None, None, None)
    assert "undefined_footnote" in row.publication_blockers


def test_gate_allows_short_uncited_supported_page_but_blocks_empty_source():
    from app.ai.mrp.verifier import factual_publication_blockers
    assert factual_publication_blockers("Nội dung ngắn.", "Nội dung ngắn.") == []
    assert "empty_source" in factual_publication_blockers("Nội dung ngắn.", "")
    assert "missing_source_reference" in factual_publication_blockers(
        "Theo Điều 99, phải đóng phí.", "Điều 1. Phạm vi áp dụng.")


def test_source_vector_failure_returns_false():
    from app.services.milvus_service import upsert_source_chunk_vector_to_milvus
    with patch("app.services.milvus_service.get_milvus_client", return_value=None):
        assert upsert_source_chunk_vector_to_milvus(uuid.uuid4(), 0, "test", 3, [0, 0, 1]) is False


@pytest.mark.asyncio
async def test_commit_never_publishes_factually_blocked_page():
    from app.ai.mrp import pipeline
    from app.ai.mrp.writer import PageWriteResult
    src = source(id=uuid.uuid4())
    row = PageWriteResult("blocked", "Blocked", "concept", "CREATE", "Text [^missing].", "")
    row.publication_blockers = ["undefined_footnote"]
    db = AsyncMock()
    db.get.return_value = src
    db.execute.return_value = quality_result(src)
    with patch.object(pipeline, "_resolve_wiki_scopes", AsyncMock(return_value=[("global", None)])), \
         patch.object(pipeline, "_merge_llm", AsyncMock(return_value=None)), \
         patch.object(pipeline.wiki_service, "apply_create", AsyncMock()) as create, \
         patch.object(pipeline.wiki_service, "regenerate_index", AsyncMock()), \
         patch.object(pipeline.wiki_service, "append_log", AsyncMock()), \
         patch.object(pipeline.source_status, "update_source_dual_status", AsyncMock()):
        result = await pipeline.run_commit_phase(db, src, [row], None, None, None, None, None)
    create.assert_not_awaited()
    assert result["status"] == "error"
    assert src.metadata_["processing_quality"]["wiki"]["failed"] == 1
    assert src.wiki_status == "error"
    assert "undefined_footnote" in src.wiki_error_message
    assert src.metadata_["processing_quality"]["wiki"]["failure_reasons"] == {"blocked": ["undefined_footnote"]}


@pytest.mark.asyncio
async def test_indexing_records_only_confirmed_vector_writes():
    from app.services import verbatim_service as service
    from app.services.source_quality import public_source_quality
    src = source(id=uuid.uuid4(), full_text="Long source text. " * 50, page_offsets=[], title="Test")
    db = AsyncMock()
    db.execute.return_value = quality_result(src)
    registry = MagicMock()
    registry.get_active_embedding_spec_id = AsyncMock(return_value="spec")
    provider = SimpleNamespace(embed_batch=AsyncMock(return_value=[[0.1, 0.2, 0.3]]))
    registry.get_embedding = AsyncMock(return_value=provider)
    with patch("app.ai.registry.ProviderRegistry", return_value=registry), \
         patch("app.services.legal_service.is_legal_source", AsyncMock(return_value=False)), \
         patch("app.ai.embedding_catalog.get_spec", return_value=SimpleNamespace(id="spec", dimension=768)), \
         patch("app.services.embedding_storage.upsert_chunk_embedding", AsyncMock(return_value=False)):
        n = await service.index_source_chunks(db, src)
    assert n == 0
    report = public_source_quality(src)
    assert report["source_index"]["status"] == "error"
    assert report["source_index"]["expected"] > 0
    assert any(w["code"] == "source_index_incomplete" for w in report["warnings"])


@pytest.mark.asyncio
async def test_wiki_index_failure_is_not_swallowed():
    from app.services import wiki_chunk_service as service
    page = SimpleNamespace(id=uuid.uuid4(), slug="page", title="Page", summary="", content_md="Source text. " * 100)
    registry = MagicMock()
    registry.get_embedding = AsyncMock(return_value=SimpleNamespace(embed_batch=AsyncMock(return_value=[[0.1]] * 2)))
    with patch.object(service, "ProviderRegistry", return_value=registry), \
         patch.object(service, "get_spec", return_value=SimpleNamespace(id="spec", dimension=768)), \
         patch.object(service, "delete_wiki_page_chunk_embeddings", AsyncMock()), \
         patch.object(service, "upsert_page_embedding", AsyncMock(return_value=False)):
        with pytest.raises(RuntimeError, match="index"):
            await service.index_wiki_page_chunks(AsyncMock(), page, "spec")


@pytest.mark.asyncio
async def test_quality_merge_keeps_other_branch_measurements():
    from app.services.source_quality import save_quality
    src = source(id=uuid.uuid4())
    db = AsyncMock()
    result = MagicMock()
    result.one_or_none.return_value = source(metadata_={"processing_quality": {"wiki": {"published": 3}}, "other": "keep"})
    db.execute.return_value = result
    await save_quality(db, src, "source_index", {"expected": 2, "indexed": 1, "status": "partial"})
    assert src.metadata_["processing_quality"]["wiki"]["published"] == 3
    assert src.metadata_["other"] == "keep"


@pytest.mark.asyncio
async def test_guard_refused_wiki_update_does_not_count_as_published():
    from app.ai.mrp import pipeline
    from app.ai.mrp.writer import PageWriteResult
    src = source(id=uuid.uuid4())
    old = SimpleNamespace(id=uuid.uuid4(), origin_tag="generated", source_ids=[src.id], content_md="Old page text.")
    row = PageWriteResult("page", "Page", "concept", "UPDATE", "New page text.", "")
    db = AsyncMock()
    db.get.return_value = src
    db.execute.return_value = quality_result(src)
    with patch.object(pipeline, "_resolve_wiki_scopes", AsyncMock(return_value=[("global", None)])), \
         patch.object(pipeline, "_merge_llm", AsyncMock(return_value=None)), \
         patch.object(pipeline.wiki_service, "get_page_by_slug", AsyncMock(return_value=old)), \
         patch.object(pipeline.wiki_service, "apply_update", AsyncMock(return_value=old)), \
         patch.object(pipeline.wiki_service, "regenerate_index", AsyncMock()), \
         patch.object(pipeline.wiki_service, "append_log", AsyncMock()), \
         patch.object(pipeline.source_status, "update_source_dual_status", AsyncMock()):
        result = await pipeline.run_commit_phase(db, src, [row], None, None, None, None, None)
    assert result.get("status") == "error"
    assert src.metadata_["processing_quality"]["wiki"]["published"] == 0


@pytest.mark.asyncio
async def test_stale_quality_writer_cannot_overwrite_new_attempt():
    from app.services.source_quality import save_quality
    old = source(id=uuid.uuid4(), chunk_attempt_id=uuid.uuid4())
    current = source(chunk_attempt_id=uuid.uuid4(), metadata_={"processing_quality": {"source_index": {"indexed": 8}}})
    db = AsyncMock()
    db.execute.return_value = quality_result(current)
    assert await save_quality(db, old, "source_index", {"status": "complete", "expected": 2, "indexed": 2}) is False
    assert current.metadata_["processing_quality"]["source_index"]["indexed"] == 8
    assert old.metadata_ == {}


def test_legal_identifier_formatting_and_ratios_are_not_factual_failures():
    from app.ai.mrp.verifier import factual_publication_blockers
    assert factual_publication_blockers("Theo ĐIỀU 5A Nghị định 12/2020/NĐ–CP.", "Điều 5a Nghị định 12/2020/NĐ-CP.") == []
    assert factual_publication_blockers("Tỷ lệ 1/2.", "Tỷ lệ một phần hai.") == []
    assert factual_publication_blockers("Xem thêm [[dieu-99|Điều 99]].", "Điều 1.") == []


def test_unsuccessful_required_ocr_is_partial_even_with_native_text():
    from app.services.source_quality import record_extraction, public_source_quality
    src = source()
    record_extraction(src, [{"content": "Sparse native signature", "is_ocr": False, "ocr_required": True, "total_doc_pages": 1}])
    report = public_source_quality(src)
    assert report["extraction"]["status"] == "partial"
    assert any(w["code"] == "ocr_incomplete" for w in report["warnings"])


@pytest.mark.asyncio
@pytest.mark.parametrize("legal,legal_fails", [(False, False), (True, False), (True, True)])
async def test_metadata_preparation_finishes_before_chunk_job_can_write_quality(legal, legal_fails):
    from app import worker
    events = []
    src = source(id=uuid.uuid4(), preserve_verbatim=False)
    w = MagicMock()
    async def chunks(*a, **kw):
        events.append("chunk")
    async def metadata(*a, **kw):
        events.append("metadata")
    async def articles(*a, **kw):
        events.append("legal")
        if legal_fails:
            raise ValueError("legal failed")
    w.commit_and_enqueue_chunk_branch = AsyncMock(side_effect=chunks)
    w.set_branch_state = AsyncMock(return_value="processing")
    w.mark_wiki_error = AsyncMock()
    w.enqueue_post_extraction_pipeline = AsyncMock(return_value="job")
    with patch.object(worker, "_self", return_value=w), \
         patch("app.services.legal_service.is_legal_source", AsyncMock(return_value=legal)), \
         patch("app.services.legal_service.finalize_legal_source", AsyncMock(side_effect=articles)), \
         patch("app.services.doc_metadata_service.store_document_metadata", AsyncMock(side_effect=metadata)):
        if legal_fails:
            with pytest.raises(ValueError, match="legal failed"):
                await worker.dispatch_dual_pipeline(AsyncMock(), src, AsyncMock(), 10)
        else:
            await worker.dispatch_dual_pipeline(AsyncMock(), src, AsyncMock(), 10)
    assert events == ["legal" if legal else "metadata", "chunk"]


@pytest.mark.asyncio
async def test_raw_worker_does_not_finalize_a_retried_attempt():
    from app import worker
    src = source(id=uuid.uuid4(), full_text="Text", chunk_attempt_id=uuid.uuid4())
    current = source(chunk_attempt_id=uuid.uuid4())
    db = AsyncMock()
    db.get.return_value = src
    db.execute.return_value = quality_result(current)
    factory = MagicMock()
    factory.return_value.__aenter__.return_value = db
    with patch("app.database.async_session_factory", factory), \
         patch.object(worker, "check_task_attempt_validity", AsyncMock(return_value=True)), \
         patch.object(worker, "set_branch_state", AsyncMock()) as state, \
         patch.object(worker, "_timing", AsyncMock()), \
         patch("app.services.verbatim_service.index_source_chunks", AsyncMock(return_value=1)):
        assert await worker.ingest_source_chunks_task({}, str(src.id)) == {"status": "stale"}
    assert not any(call.kwargs.get("status") == "ready" for call in state.await_args_list)


@pytest.mark.asyncio
async def test_metadata_refresh_preserves_new_quality_and_latest_manual_edits():
    from app.services import doc_metadata_service as service
    src = source(id=uuid.uuid4(), metadata_={"doc": {"official_title": "Old"}})
    latest = {"processing_quality": {"source_index": {"indexed": 9}},
              "doc": {"official_title": "Corrected", "manual_fields": ["official_title"], "doc_slug": "keep"}}
    db = AsyncMock()
    row = MagicMock()
    row.scalar_one_or_none.return_value = latest
    db.execute.return_value = row
    with patch.object(service, "extract_document_metadata", AsyncMock(return_value={"official_title": "Generated"})):
        meta = await service.store_document_metadata(db, src)
    assert meta["official_title"] == "Corrected"
    assert meta["doc_slug"] == "keep"
    assert src.metadata_["processing_quality"]["source_index"]["indexed"] == 9
    query = db.execute.await_args.args[0]
    assert query.get_execution_options()["autoflush"] is False
    assert "FOR UPDATE" in str(query)


@pytest.mark.asyncio
async def test_manual_metadata_storage_preserves_new_quality():
    from app.services.doc_metadata_service import store_manual_doc_meta
    src = source(id=uuid.uuid4(), metadata_={"doc": {"field": "Old"}})
    db = AsyncMock()
    row = MagicMock()
    row.scalar_one_or_none.return_value = {"processing_quality": {"wiki": {"published": 5}}, "doc": {"doc_slug": "keep"}}
    db.execute.return_value = row
    meta = await store_manual_doc_meta(db, src, {"official_title": "Manual title"})
    assert meta["official_title"] == "Manual title"
    assert meta["doc_slug"] == "keep"
    assert src.metadata_["processing_quality"]["wiki"]["published"] == 5
