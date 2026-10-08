"""Dual-pipeline aggregate status and dispatch routing."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.database.models import Source
from app.services.source_status import compute_source_dual_status, reset_branches


def _src(**kw) -> Source:
    kw.setdefault("preserve_verbatim", False)
    return Source(id=uuid.uuid4(), **kw)


def test_chunk_error_wiki_ready_is_partial():
    st, prog, msg = compute_source_dual_status(
        _src(chunk_status="error", chunk_error_message="embed 500", wiki_status="ready")
    )
    assert st == "partial"
    assert prog == 100
    assert "embed 500" in msg


def test_both_error_is_error():
    st, _, msg = compute_source_dual_status(
        _src(chunk_status="error", chunk_error_message="a", wiki_status="error", wiki_error_message="b")
    )
    assert st == "error"
    assert "a" in msg and "b" in msg


def test_one_branch_failed_other_running_is_processing():
    st, _, _ = compute_source_dual_status(
        _src(chunk_status="error", wiki_status="mapping", wiki_progress=60)
    )
    assert st == "processing"
    st, _, _ = compute_source_dual_status(
        _src(chunk_status="embedding", wiki_status="error")
    )
    assert st == "processing"


def test_wiki_ready_while_chunks_reindex_stays_ready():
    """Backfill of raw chunks must not take a ready source out of 'ready'."""
    st, _, _ = compute_source_dual_status(_src(chunk_status="embedding", wiki_status="ready"))
    assert st == "ready"


def test_legacy_source_chunk_pending_follows_wiki():
    """Sources from before migration 044: chunk 'pending', wiki 'ready'."""
    st, _, _ = compute_source_dual_status(_src(chunk_status="pending", wiki_status="ready"))
    assert st == "ready"
    st, _, _ = compute_source_dual_status(_src(chunk_status="pending", wiki_status="error"))
    assert st == "error"


def test_plan_ready_gate_keeps_status():
    st, _, msg = compute_source_dual_status(_src(chunk_status="ready", wiki_status="plan_ready"))
    assert st == "plan_ready"
    assert "Raw chunks already searchable" in msg


def test_verbatim_chunk_error_is_error():
    st, _, _ = compute_source_dual_status(
        _src(preserve_verbatim=True, chunk_status="error", wiki_status="skipped")
    )
    assert st == "error"


def test_reset_branches():
    src = _src(chunk_status="ready", wiki_status="error", wiki_error_message="x")
    reset_branches(src, wiki_skipped=True)
    assert src.chunk_status == "pending"
    assert src.wiki_status == "skipped"
    assert src.wiki_error_message is None


# ---------------------------------------------------------------------------
# dispatch_dual_pipeline routing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dispatch_verbatim_skips_wiki():
    from app import worker

    src = _src(preserve_verbatim=True, attempt_id=uuid.uuid4())
    with patch.object(worker, "commit_and_enqueue_chunk_branch", AsyncMock()) as enq, \
         patch("app.services.legal_service.is_legal_source", AsyncMock(return_value=False)), \
         patch.object(worker, "enqueue_post_extraction_pipeline", AsyncMock()) as mrp:
        res = await worker.dispatch_dual_pipeline(MagicMock(), src, MagicMock(), token_count=10)
    enq.assert_awaited_once()
    mrp.assert_not_awaited()
    assert src.wiki_status == "skipped"
    assert res["branch_b"] == "skipped"


@pytest.mark.asyncio
async def test_dispatch_large_doc_gates_wiki_only():
    from app import worker

    src = _src(attempt_id=uuid.uuid4())
    with patch.object(worker, "commit_and_enqueue_chunk_branch", AsyncMock()) as enq, \
         patch("app.services.legal_service.is_legal_source", AsyncMock(return_value=False)), \
         patch.object(worker, "set_branch_state", AsyncMock(return_value="awaiting_approval")) as sbs, \
         patch.object(worker, "enqueue_post_extraction_pipeline", AsyncMock()) as mrp, \
         patch.object(worker.settings, "auto_approve_extraction_threshold_tokens", 100):
        res = await worker.dispatch_dual_pipeline(MagicMock(), src, MagicMock(), token_count=1000)
    enq.assert_awaited_once()  # branch A still runs
    mrp.assert_not_awaited()
    assert sbs.await_args.kwargs["status"] == "awaiting_approval"
    assert res["status"] == "awaiting_approval"


@pytest.mark.asyncio
async def test_dispatch_small_doc_sets_wiki_state_before_enqueue():
    from app import worker

    calls = []
    src = _src(attempt_id=uuid.uuid4())
    session = MagicMock()
    session.commit = AsyncMock()

    async def _sbs(*a, **kw):
        calls.append(("state", kw.get("status")))
        return "processing"

    async def _mrp(*a, **kw):
        calls.append(("enqueue", None))
        # Branch B carries its own attempt, distinct from branch A's.
        assert kw["attempt_id_str"] == str(src.wiki_attempt_id)
        assert src.wiki_attempt_id != src.attempt_id
        return "job-1"

    with patch.object(worker, "commit_and_enqueue_chunk_branch", AsyncMock()), \
         patch("app.services.legal_service.is_legal_source", AsyncMock(return_value=False)), \
         patch.object(worker, "set_branch_state", side_effect=_sbs), \
         patch.object(worker, "enqueue_post_extraction_pipeline", side_effect=_mrp), \
         patch.object(worker.settings, "auto_approve_extraction_threshold_tokens", 100_000):
        await worker.dispatch_dual_pipeline(session, src, MagicMock(), token_count=10)
    assert calls == [("state", "processing"), ("enqueue", None)]
    assert src.job_id == "job-1"
