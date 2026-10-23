"""Disposable-PostgreSQL gate for the built Wiki image; no production access.

Only LLM output and unrelated page lookup are stubbed. Source/plan reads,
attempt fences, transactions, commits, and retry reloads use real PostgreSQL.
DATABASE_URL must point to the isolated QA container.
"""
import asyncio
import json
import uuid
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import select, text

from app import database
from app.ai.mrp import pipeline, writer
from app.database.models import Base, Source, SourceCompilationPlan, WikiPage
from app.services.wiki_write_guard import make_failure_stub


async def main():
    async with database.engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)

    async def seed(count=3):
        async with database.async_session_factory() as db:
            source = Source(id=uuid.uuid4(), full_text="Valid source text.",
                            attempt_id=uuid.uuid4(), wiki_attempt_id=uuid.uuid4())
            plan = SourceCompilationPlan(id=uuid.uuid4(), source_id=source.id,
                status="in_progress", plan_json={"pages": [
                    {"slug": f"page-{i}", "title": f"Page {i}"} for i in range(count)]})
            db.add_all([source, plan])
            await db.commit()
            return source.id, plan.id

    async def run(sid, pid, generate=None):
        async with database.async_session_factory() as db:
            source = await db.get(Source, sid)
            plan = await db.get(SourceCompilationPlan, pid)
            generate = generate or AsyncMock(return_value=(source.full_text, "Summary"))
            with patch("app.services.wiki_service.resolve_wiki_scopes", AsyncMock(return_value=[("global", None)])), \
                 patch("app.services.wiki_service.get_page_by_slug", AsyncMock(return_value=None)), \
                 patch("app.services.wiki_origin_service.resolve_target_slug", AsyncMock(side_effect=lambda s, slug, *a: slug)), \
                 patch.object(writer, "write_simple", generate):
                result = await writer.run_refine_phase(db, source, plan, [], source.full_text,
                    SimpleNamespace(), None, "general", None)
            return result, generate.await_count

    sid, pid = await seed()
    result, count = await run(sid, pid)
    assert len(result) == 3 and count == 3
    async with database.async_session_factory() as db:
        source = await db.get(Source, sid)
        plan = await db.get(SourceCompilationPlan, pid)
        saved = deepcopy(plan.plan_json)
        saved["_page_drafts"][1]["content_md"] = make_failure_stub("Page 1", "UpstreamUnavailable")
        plan.plan_json = saved
        source.wiki_attempt_id = uuid.uuid4()
        await db.commit()
    result, count = await run(sid, pid)
    assert len(result) == 3 and count == 1, count
    print(json.dumps({"check": "real_commit_reload_selective_retry", "passed": True,
                      "initial_generated": 3, "retry_generated": count}), flush=True)

    for change in ("source_text", "source_outline", "plan", "attempt"):
        sid, pid = await seed(1)
        async def concurrent_edit(*args, **kwargs):
            async with database.async_session_factory() as other:
                if change == "plan":
                    plan = await other.get(SourceCompilationPlan, pid)
                    plan.plan_json = {"pages": [{"slug": "changed", "title": "Changed"}]}
                else:
                    source = await other.get(Source, sid)
                    if change == "source_text":
                        source.full_text = "Concurrently changed original."
                    elif change == "source_outline":
                        source.outline_json = [{"title": "Changed"}]
                    else:
                        source.wiki_attempt_id = uuid.uuid4()
                await other.commit()
            return "Valid source text.", "Summary"
        try:
            await run(sid, pid, AsyncMock(side_effect=concurrent_edit))
        except RuntimeError as exc:
            assert "Stale Wiki" in str(exc), type(exc).__name__
        else:
            raise AssertionError(f"Concurrent {change} was not fenced")
        async with database.async_session_factory() as db:
            saved = (await db.execute(select(SourceCompilationPlan.plan_json).where(
                SourceCompilationPlan.id == pid))).scalar_one()
            assert not saved.get("_page_drafts")
        print(json.dumps({"check": "real_concurrent_" + change + "_fenced", "passed": True}), flush=True)
    for change in ("source_text", "source_outline", "plan", "attempt", None):
        sid, pid = await seed(1)
        await run(sid, pid)
        async with database.async_session_factory() as db:
            source = await db.get(Source, sid)
            plan = await db.get(SourceCompilationPlan, pid)
            fingerprint = writer.checkpoint_fingerprint(source, plan, source.full_text, "general")
            cached = list(writer.reusable_checkpoint_results(source, plan, source.full_text, "general").values())
            assert len(cached) == 1
            if change:
                async with database.async_session_factory() as other:
                    if change == "plan":
                        current = await other.get(SourceCompilationPlan, pid)
                        current.plan_json = {"pages": [{"slug": "changed", "title": "Changed"}]}
                    else:
                        current = await other.get(Source, sid)
                        if change == "source_text":
                            current.full_text = "Concurrently corrected original."
                        elif change == "source_outline":
                            current.outline_json = [{"title": "Changed"}]
                        else:
                            current.wiki_attempt_id = uuid.uuid4()
                    await other.commit()
            with patch.object(pipeline, "_resolve_wiki_scopes", AsyncMock(return_value=[("global", None)])), \
                 patch.object(pipeline, "_merge_llm", AsyncMock(return_value=None)):
                result = await pipeline.run_commit_phase(db, source, cached, plan, None, None,
                    "general", None, expected_fingerprint=fingerprint)
            if change:
                assert result == {"status": "stale"}, result
            else:
                assert result.get("pages_created", 0) + result.get("pages_updated", 0) == 1, result
        async with database.async_session_factory() as check:
            pages = (await check.execute(select(WikiPage))).scalars().all()
            owned = [page for page in pages if sid in (page.source_ids or [])]
            current = await check.get(Source, sid)
            assert len(owned) == (0 if change else 1)
            assert (current.wiki_status == "ready") == (change is None)
        print(json.dumps({"check": "real_cached_publication_" + (change or "unchanged"),
                          "passed": True}), flush=True)
    # A complete checkpoint in VERIFY must still detect a new slug collision.
    sid, pid = await seed(3)
    prefix = "qa-" + str(sid)[:8]
    a, b, c = [prefix + "-" + suffix for suffix in "abc"]
    async with database.async_session_factory() as db:
        plan = await db.get(SourceCompilationPlan, pid)
        plan.plan_json = {"pages": [{"slug": slug, "title": slug} for slug in (a, b, c)]}
        await db.commit()
    async def initial(*args):
        return ("Valid source text. " + (f"[B](/wiki/{b}#detail)" if args[1]["slug"] == a else ""), "Summary")
    await run(sid, pid, AsyncMock(side_effect=initial))
    async with database.async_session_factory() as db:
        source = await db.get(Source, sid)
        source.pipeline_phase = "verify"
        db.add(WikiPage(id=uuid.uuid4(), slug=b, title="Unrelated original", content_md="Unrelated.",
                       scope_type="global", source_ids=[], origin_tag="extracted"))
        await db.commit()
    async def regenerate(*args):
        return ("Valid source text. " + (f"[B](/wiki/{b}-generated#detail)" if args[1]["slug"] == a else ""), "Summary")
    generate = AsyncMock(side_effect=regenerate)
    registry = SimpleNamespace(get_llm=AsyncMock(return_value=SimpleNamespace()),
        get_embedding=AsyncMock(return_value=None), get_active_embedding_spec_id=AsyncMock(return_value=None))
    async with database.async_session_factory() as db:
        source = await db.get(Source, sid)
        with patch.object(writer, "write_simple", generate), \
             patch.object(pipeline, "_merge_llm", AsyncMock(return_value=None)):
            result = await pipeline.run_refine_pipeline(db, source, source.full_text, None,
                registry, "general", "General", "General")
        assert result.get("pages_created") == 3, result
        assert generate.await_count == 2, generate.await_count
    async with database.async_session_factory() as db:
        page = (await db.execute(select(WikiPage).where(WikiPage.slug == a))).scalar_one()
        assert f"/wiki/{b}-generated#detail" in page.content_md
        assert f"/wiki/{b}#detail" not in page.content_md
    print(json.dumps({"check": "real_pipeline_complete_cache_collision_links", "passed": True,
                      "regenerated": 2, "reused": 1}), flush=True)
    await database.engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
