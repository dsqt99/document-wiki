"""Retries preserve proven drafts without trusting stale source/plan checkpoints."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio
import uuid

import pytest

from app.ai.mrp import pipeline, writer
from app.services.wiki_write_guard import make_failure_stub


def source_and_plan(count=3):
    source = SimpleNamespace(id=uuid.uuid4(), attempt_id=uuid.uuid4(), outline_json=None,
                             full_text="Valid source text.", pipeline_phase="refine")
    plan = SimpleNamespace(id=uuid.uuid4(), status="in_progress", plan_json={
        "pages": [{"slug": f"page-{i}", "title": f"Page {i}"} for i in range(count)]})
    return source, plan


async def run_writer(source, plan, *, generate=None, current_attempt=True,
                     stored_text=None, stored_plan=None, attempt_check=None):
    db = AsyncMock()
    def current_plan(*args, **kwargs):
        result = MagicMock()
        result.scalar_one_or_none.return_value = deepcopy(stored_plan if stored_plan is not None else plan.plan_json)
        result.one_or_none.return_value = SimpleNamespace(
            full_text=source.full_text if stored_text is None else stored_text,
            outline_json=source.outline_json)
        return result
    db.execute.side_effect = current_plan
    factory = MagicMock()
    factory.return_value.__aenter__.return_value = db
    generate = generate or AsyncMock(return_value=("Valid source text.", "Summary"))
    with patch("app.database.async_session_factory", factory), \
         patch("app.services.wiki_service.resolve_wiki_scopes", AsyncMock(return_value=[("global", None)])), \
         patch("app.services.wiki_service.get_page_by_slug", AsyncMock(return_value=None)), \
         patch("app.services.wiki_origin_service.resolve_target_slug", AsyncMock(
             side_effect=lambda session, slug, *a: slug + "-generated")), \
         patch("app.services.source_quality.lock_current_attempt",
               attempt_check or AsyncMock(return_value=current_attempt)), \
         patch.object(writer, "write_simple", generate):
        results = await writer.run_refine_phase(db, source, plan, [], source.full_text,
                                                SimpleNamespace(), None, "general", None)
    return results, [call.args[1]["slug"] for call in generate.await_args_list]


@pytest.mark.asyncio
async def test_retry_69_failed_pages_preserves_ten_valid_drafts():
    source, plan = source_and_plan(79)
    initial, _ = await run_writer(source, plan)
    for draft in plan.plan_json["_page_drafts"][10:]:
        draft["content_md"] = make_failure_stub(draft["title"], "UpstreamUnavailable: [ai_unavailable]")
    # A branch retry does not change the original extraction attempt.
    source.wiki_attempt_id = uuid.uuid4()
    results, generated = await run_writer(source, plan)
    assert generated == [f"page-{i}-generated" for i in range(10, 79)]
    assert [r.to_dict() for r in results[:10]] == [r.to_dict() for r in initial[:10]]
    assert len(results) == 79 and all(not writer.is_failure_stub(r.content_md) for r in results)


@pytest.mark.asyncio
async def test_interrupted_writer_retains_completed_versioned_draft_for_retry():
    source, plan = source_and_plan()
    async def interrupted(*args):
        if args[1]["slug"] == "page-1-generated":
            raise asyncio.CancelledError()
        return "Valid source text.", "Summary"
    with pytest.raises(asyncio.CancelledError):
        await run_writer(source, plan, generate=AsyncMock(side_effect=interrupted))
    assert plan.plan_json.get("_page_drafts_checkpoint", {}).get("fingerprint")
    saved = {d["slug"] for d in plan.plan_json.get("_page_drafts", [])}
    assert "page-0-generated" in saved
    assert "page-1-generated" not in saved
    _, generated = await run_writer(source, plan)
    assert "page-0-generated" not in generated and "page-1-generated" in generated


@pytest.mark.asyncio
async def test_superseded_attempt_cannot_save_new_draft_checkpoint():
    source, plan = source_and_plan()
    before = deepcopy(plan.plan_json)
    with pytest.raises(RuntimeError, match="[Ss]tale"):
        await run_writer(source, plan, current_attempt=False)
    assert plan.plan_json == before


@pytest.mark.asyncio
async def test_changed_original_cannot_save_checkpoint_even_without_attempt_change():
    source, plan = source_and_plan()
    before = deepcopy(plan.plan_json)
    with pytest.raises(RuntimeError, match="[Ss]tale"):
        await run_writer(source, plan, stored_text="Concurrently corrected original.")
    assert plan.plan_json == before


@pytest.mark.asyncio
async def test_changed_plan_cannot_be_overwritten_by_page_checkpoint():
    source, plan = source_and_plan()
    before = deepcopy(plan.plan_json)
    changed = deepcopy(before)
    changed["pages"][0]["entity_names"] = ["Changed while generating"]
    with pytest.raises(RuntimeError, match="[Ss]tale"):
        await run_writer(source, plan, stored_plan=changed)
    assert plan.plan_json == before


@pytest.mark.asyncio
async def test_parallel_page_completions_serialize_parent_session_checkpoints():
    source, plan = source_and_plan(5)
    active, peak = 0, 0
    async def attempt_check(*args):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(.001)
        active -= 1
        return True
    checker = AsyncMock(side_effect=attempt_check)
    await run_writer(source, plan, attempt_check=checker)
    assert checker.await_count == 5 and peak == 1
    assert len(plan.plan_json["_page_drafts"]) == 5


@pytest.mark.asyncio
async def test_retry_regenerates_only_missing_or_currently_blocked_drafts():
    source, plan = source_and_plan()
    await run_writer(source, plan)
    plan.plan_json["_page_drafts"][1]["content_md"] = "Điều 99. Unsupported reference."
    plan.plan_json["_page_drafts"].pop()
    results, generated = await run_writer(source, plan)
    assert generated == ["page-1-generated", "page-2-generated"]
    assert len(results) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["text", "source", "attempt", "plan", "plan_inputs", "outline", "legacy"])
async def test_stale_or_unversioned_checkpoint_cannot_reuse_drafts(change):
    source, plan = source_and_plan()
    await run_writer(source, plan)
    if change == "text":
        source.full_text += " Revised original."
    elif change == "source":
        source.id = uuid.uuid4()
    elif change == "attempt":
        source.attempt_id = uuid.uuid4()
    elif change == "plan":
        plan.id = uuid.uuid4()
    elif change == "plan_inputs":
        plan.plan_json["pages"][0]["entity_names"] = ["Revised entity"]
    elif change == "outline":
        source.outline_json = [{"title": "Revised section"}]
    else:
        plan.plan_json.pop("_page_drafts_checkpoint", None)
    _, generated = await run_writer(source, plan)
    assert generated == [f"page-{i}-generated" for i in range(3)]


@pytest.mark.asyncio
async def test_checkpoint_with_wrong_or_duplicate_slug_regenerates_that_item():
    source, plan = source_and_plan()
    await run_writer(source, plan)
    plan.plan_json["_page_drafts"][0]["slug"] = "unplanned-page"
    plan.plan_json["_page_drafts"].append(deepcopy(plan.plan_json["_page_drafts"][1]))
    _, generated = await run_writer(source, plan)
    assert generated == ["page-0-generated", "page-1-generated"]


@pytest.mark.asyncio
@pytest.mark.parametrize("error,expected", [
    ("InternalServerError: Error code: 524 - timeout https://secret.invalid/?token=secret",
     ["generation_failed", "ai_unavailable", "ai_timeout"]),
    ("UpstreamUnavailable: [ai_unavailable]", ["generation_failed", "ai_unavailable"]),
    ("APIConnectionError: secret", ["generation_failed", "ai_unavailable"]),
])
async def test_commit_records_safe_reason_codes_for_failed_ai_stubs(error, expected):
    source, plan = source_and_plan(2)
    stub = writer.PageWriteResult("bad", "Bad", "concept", "CREATE",
        make_failure_stub("Bad", error), "")
    good = writer.PageWriteResult("good", "Good", "concept", "CREATE", source.full_text, "")
    db = AsyncMock()
    db.get.return_value = source
    page = SimpleNamespace(content_md=source.full_text)
    save = AsyncMock(return_value=True)
    with patch.object(pipeline, "_resolve_wiki_scopes", AsyncMock(return_value=[("global", None)])), \
         patch.object(pipeline, "_merge_llm", AsyncMock(return_value=None)), \
         patch.object(pipeline, "_lock", AsyncMock()), \
         patch("app.services.wiki_origin_service.resolve_target_slug", AsyncMock(side_effect=lambda s, slug, *a: slug)), \
         patch.object(pipeline.wiki_service, "get_page_by_slug", AsyncMock(return_value=None)), \
         patch.object(pipeline.wiki_service, "apply_create", AsyncMock(return_value=page)) as create, \
         patch.object(pipeline.wiki_service, "regenerate_index", AsyncMock()), \
         patch.object(pipeline.wiki_service, "append_log", AsyncMock()), \
         patch.object(pipeline.source_quality, "save_quality", save), \
         patch.object(pipeline.source_status, "update_source_dual_status", AsyncMock()):
        await pipeline.run_commit_phase(db, source, [good, stub], plan, None, None, None, None)
    reasons = save.await_args.args[3]["failure_reasons"]
    assert reasons == {"bad": expected}
    assert "secret" not in str(reasons)
    assert create.await_count == 1 and create.await_args.kwargs["slug"] == "good"
    assert source.wiki_status == "error"
