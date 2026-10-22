from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import pytest

from app.ai.mrp import pipeline, writer, verifier
from app.services.wiki_write_guard import make_failure_stub


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["verify", "commit"])
@pytest.mark.parametrize("draft", [
    make_failure_stub("Page", "APIConnectionError"),
    "# Page\n\nBroken citation[^missing]",
    "",
])
async def test_resuming_checkpoint_regenerates_failed_drafts(phase, draft):
    source = SimpleNamespace(id=uuid.uuid4(), pipeline_phase=phase)
    row = writer.PageWriteResult("page", "Page", "concept", "CREATE", draft, "")
    plan = SimpleNamespace(status="done", plan_json={"pages": [{"slug": "page"}],
                                                   "_page_drafts": [row.to_dict()]})
    db = AsyncMock()
    db.execute.return_value = MagicMock()
    db.execute.return_value.scalars.return_value.all.return_value = []
    registry = AsyncMock()
    registry.get_active_embedding_spec_id.return_value = None
    regenerated = writer.PageWriteResult("page", "Page", "concept", "CREATE", "Valid source text.", "")
    with patch.object(pipeline, "_load_plan", AsyncMock(return_value=plan)), \
         patch.object(writer, "run_refine_phase", AsyncMock(return_value=[regenerated])) as refine, \
         patch.object(verifier, "run_verify_phase", AsyncMock(side_effect=lambda *a: a[2])) as verify, \
         patch.object(pipeline, "run_commit_phase", AsyncMock(return_value={"status": "ready"})):
        await pipeline.run_refine_pipeline(db, source, "Valid source text.", None, registry, None, None, None)
    refine.assert_awaited_once()
    assert verify.await_args.args[2] == [regenerated]


@pytest.mark.asyncio
async def test_good_checkpoint_does_not_call_writer_again():
    source = SimpleNamespace(id=uuid.uuid4(), pipeline_phase="commit")
    row = writer.PageWriteResult("page", "Page", "concept", "CREATE", "Valid source text.", "")
    plan = SimpleNamespace(status="done", plan_json={"pages": [{"slug": "page"}],
                                                   "_page_drafts": [row.to_dict()]})
    db = AsyncMock()
    db.execute.return_value = MagicMock()
    db.execute.return_value.scalars.return_value.all.return_value = []
    registry = AsyncMock()
    registry.get_active_embedding_spec_id.return_value = None
    with patch.object(pipeline, "_load_plan", AsyncMock(return_value=plan)), \
         patch.object(writer, "run_refine_phase", AsyncMock()) as refine, \
         patch.object(verifier, "run_verify_phase", AsyncMock(side_effect=lambda *a: a[2])), \
         patch.object(pipeline, "run_commit_phase", AsyncMock(return_value={"status": "ready"})):
        await pipeline.run_refine_pipeline(db, source, "Valid source text.", None, registry, None, None, None)
    refine.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_checkpoint_page_is_regenerated():
    source = SimpleNamespace(id=uuid.uuid4(), pipeline_phase="commit")
    row = writer.PageWriteResult("page", "Page", "concept", "CREATE", "Valid source text.", "")
    plan = SimpleNamespace(status="done", plan_json={"pages": [{"slug": "page"}, {"slug": "missing"}],
                                                   "_page_drafts": [row.to_dict()]})
    db = AsyncMock()
    db.execute.return_value = MagicMock()
    db.execute.return_value.scalars.return_value.all.return_value = []
    registry = AsyncMock()
    registry.get_active_embedding_spec_id.return_value = None
    with patch.object(pipeline, "_load_plan", AsyncMock(return_value=plan)), \
         patch.object(writer, "run_refine_phase", AsyncMock(return_value=[row])) as refine, \
         patch.object(verifier, "run_verify_phase", AsyncMock(side_effect=lambda *a: a[2])), \
         patch.object(pipeline, "run_commit_phase", AsyncMock(return_value={"status": "ready"})):
        await pipeline.run_refine_pipeline(db, source, "Valid source text.", None, registry, None, None, None)
    refine.assert_awaited_once()
