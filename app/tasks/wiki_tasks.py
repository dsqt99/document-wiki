"""Wiki-side worker tasks: MRP compilation, plan regeneration, AI pre-review and legal maintenance.

Registered in app.worker as thin wrappers (03 §11.7, 05a §5.9, 05b §3.6, §8.4).
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from loguru import logger
from sqlalchemy import or_, select, update

INTERNAL_PLAN_KEYS = ("_claims", "_entities", "_concepts")


def _worker():
    import app.worker as w

    return w


def _as_uuid(value) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


async def _record_failure(task_name: str, exc: BaseException, source_id, attempt_id_str=None, payload=None):
    try:
        from app import database
        from app.models import task_failure

        async with database.async_session_factory() as session:
            await task_failure.record_task_failure(
                session=session, task_name=task_name, error=exc,
                source_id=source_id, attempt_id=attempt_id_str, payload=payload or {},
            )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Could not record dead-letter for {task_name} {source_id}: {e}")


async def _fail(task_name: str, exc: BaseException, sid, attempt_id_str=None) -> None:
    w = _worker()

    async def _do():
        try:
            await w.mark_wiki_error(sid, w._error_text(exc) if hasattr(w, "_error_text") else str(exc))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Could not mark wiki error for {sid}: {e}")
        await _record_failure(task_name, exc, sid, attempt_id_str)

    try:
        await asyncio.shield(_do())
    except BaseException as e:  # noqa: BLE001
        logger.warning(f"Failure handling interrupted for {sid}: {e}")


async def _timing(session, sid, stage: str, t0: float, metadata: dict) -> None:
    try:
        from app.models import task_failure

        await task_failure.record_stage_timing(session, sid, stage, int((time.perf_counter() - t0) * 1000),
                                               metadata or {})
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Could not record stage timing {stage} for {sid}: {e}")


async def _knowledge_type(session, source) -> tuple[Optional[str], Optional[str], Optional[str]]:
    kt = getattr(source, "knowledge_type", None)
    if kt is None and getattr(source, "knowledge_type_id", None):
        from app.database.models import KnowledgeType

        kt = await session.get(KnowledgeType, source.knowledge_type_id)
    if kt is None:
        return None, None, None
    return kt.slug, kt.name, kt.description


def _registry(session):
    import app.ai.registry as registry_mod

    return registry_mod.ProviderRegistry(session)


def _flush():
    try:
        from app.ai import tracing

        tracing.flush_langfuse()
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# MAP + REDUCE
# ---------------------------------------------------------------------------


async def ingest_map_reduce_task(ctx, source_id, attempt_id_str=None, **_ignored):
    from app import database
    from app.ai.mrp import pipeline
    from app.database.models import Source
    from app.utils.progress import ProgressTracker

    w = _worker()
    sid = _as_uuid(source_id)
    try:
        async with database.async_session_factory() as session:
            try:
                if not await w.check_task_attempt_validity(session, sid, attempt_id_str, branch="wiki"):
                    return {"status": "stale"}
                source = await session.get(Source, sid)
                if source is None:
                    return {"status": "not_found"}
                full_text = source.full_text or ""
                if not full_text.strip():
                    raise ValueError(f"Source {sid} has no extracted text")
                tracker = ProgressTracker(sid)

                from app.services import legal_service, processing_mode
                processing_mode.set_mode(source, "auto")

                plan = await processing_mode.plan_for(session, source)
                if plan.verbatim_page:
                    from app.services import verbatim_page_service

                    return await verbatim_page_service.finalize_verbatim_pages(session, source, tracker)
                if plan.articles and not (plan.llm and processing_mode.articles_done(source, attempt_id_str)):
                    result = await legal_service.finalize_legal_source(
                        session, source, tracker, final=not plan.llm
                    )
                    if not plan.llm:
                        return result

                if getattr(source, "preserve_verbatim", False):
                    try:
                        return await w.finalize_verbatim_source(session, source, tracker)
                    except Exception as e:
                        try:
                            await session.rollback()
                        except Exception:  # noqa: BLE001
                            pass
                        await w.set_branch_state(sid, "chunk", status="error", progress=0,
                                                 message="Verbatim indexing failed", error=str(e)[:500])
                        raise

                await w.set_branch_state(sid, "wiki", status="mapping", progress=56,
                                         message="Extracting knowledge from document...", session=session)
                kt_slug, kt_name, kt_desc = await _knowledge_type(session, source)
                t0 = time.perf_counter()
                result = await pipeline.run_mrp_pipeline(
                    session=session, source=source, attempt_id_str=attempt_id_str, full_text=full_text,
                    tracker=tracker, registry=_registry(session), kt_slug=kt_slug, kt_name=kt_name,
                    kt_desc=kt_desc,
                )
                status = (result or {}).get("status")
                await _timing(session, sid, "map_reduce", t0, {"status": status})
                if status == "plan_ready":
                    source.auto_recover_count = 0
                    await session.commit()
                    await w.set_branch_state(sid, "wiki", status="plan_ready", progress=80,
                                             message="Compilation plan ready — awaiting review", session=session)
                return result
            except BaseException as exc:
                try:
                    await session.rollback()
                except BaseException:  # noqa: BLE001
                    pass
                await _fail("ingest_map_reduce_task", exc, sid, attempt_id_str)
                if w._is_ai_outage(exc):
                    return {"status": "error", "reason": "ai_unavailable"}
                raise
    finally:
        _flush()


# ---------------------------------------------------------------------------
# REFINE + VERIFY + COMMIT
# ---------------------------------------------------------------------------


async def ingest_refine_task(ctx, source_id, attempt_id_str=None):
    from app import database
    from app.ai.mrp import pipeline
    from app.database.models import Source
    from app.utils.progress import ProgressTracker

    w = _worker()
    sid = _as_uuid(source_id)
    try:
        async with database.async_session_factory() as session:
            try:
                if not await w.check_task_attempt_validity(session, sid, attempt_id_str, branch="wiki"):
                    return {"status": "stale"}
                source = await session.get(Source, sid)
                if source is None:
                    return {"status": "not_found"}
                await w.set_branch_state(sid, "wiki", status="refining", progress=78,
                                         message="Writing wiki pages...", session=session)
                kt_slug, kt_name, kt_desc = await _knowledge_type(session, source)
                t0 = time.perf_counter()
                result = await pipeline.run_refine_pipeline(
                    session=session, source=source, full_text=source.full_text or "",
                    tracker=ProgressTracker(sid), registry=_registry(session),
                    kt_slug=kt_slug, kt_name=kt_name, kt_desc=kt_desc,
                )
                result = result or {}
                await _timing(session, sid, "refine", t0, {
                    "pages_created": result.get("pages_created", 0),
                    "pages_updated": result.get("pages_updated", 0),
                })
                return result
            except BaseException as exc:
                try:
                    await session.rollback()
                except BaseException:  # noqa: BLE001
                    pass
                await _fail("ingest_refine_task", exc, sid, attempt_id_str)
                if w._is_ai_outage(exc):
                    return {"status": "error", "reason": "ai_unavailable"}
                raise
    finally:
        _flush()


# ---------------------------------------------------------------------------
# Plan regeneration
# ---------------------------------------------------------------------------


async def regenerate_plan_task(ctx, source_id, user_note):
    from app import database
    from app.ai.mrp import reducer
    from app.database.models import Source, SourceCompilationPlan

    sid = _as_uuid(source_id)
    async with database.async_session_factory() as session:
        try:
            source = await session.get(Source, sid)
            if source is None:
                return {"status": "not_found"}
            plan = (await session.execute(
                select(SourceCompilationPlan).where(SourceCompilationPlan.source_id == sid)
            )).scalars().first()
            if plan is None:
                return {"status": "no_plan"}
            kt_slug, kt_name, kt_desc = await _knowledge_type(session, source)
            old = dict(plan.plan_json or {})
            entities = list(old.get("_entities") or [])
            concepts = list(old.get("_concepts") or [])

            registry = _registry(session)
            llm = await registry.get_llm()
            reconciliation = {}
            try:
                emb = await registry.get_embedding(task="document")
                reconciliation = await reducer.reconcile_with_kb(session, source, entities + concepts, llm, emb)
            except Exception as e:  # noqa: BLE001
                logger.info(f"regenerate_plan[{sid}]: reconciliation skipped ({e})")
                reconciliation = {}

            new_plan = await reducer.run_planning_call(
                llm, source, getattr(source, "pipeline_strategy", None) or "standard",
                entities, concepts, reconciliation, kt_name=kt_name, kt_desc=kt_desc, user_note=user_note,
            )
            merged = dict(new_plan or {})
            for key in INTERNAL_PLAN_KEYS:
                if key in old:
                    merged[key] = old[key]
            plan.plan_json = merged
            plan.status = "pending_review"
            plan.reviewed_by = None
            plan.review_note = None
            plan.reviewed_at = None
            await session.commit()
            return {"status": "pending_review", "plan_id": str(plan.id)}
        except Exception as exc:
            logger.error(f"regenerate_plan[{sid}] failed: {exc}")
            try:
                await session.rollback()
                plan = (await session.execute(
                    select(SourceCompilationPlan).where(SourceCompilationPlan.source_id == sid)
                )).scalars().first()
                if plan is not None and plan.status == "regenerating":
                    plan.status = "pending_review"
                    plan.review_note = f"Regeneration failed: {str(exc)[:200]}"
                    await session.commit()
            except Exception as e:  # noqa: BLE001
                logger.warning(f"regenerate_plan[{sid}]: could not reset plan status: {e}")
            return {"status": "error", "error": str(exc)[:500]}


# ---------------------------------------------------------------------------
# AI pre-review
# ---------------------------------------------------------------------------


async def ai_pre_review_draft_task(ctx, draft_id, expected_round=None):
    from app.services.ai_review import runner

    results = await runner.run_async_checks(draft_id, expected_round=expected_round)
    if results is None:
        return {"status": "skipped"}
    return {"status": "done", "summary": results.get("summary")}


async def sweep_stuck_ai_review_cron(ctx):
    from app import database
    from app.config import settings
    from app.database.models import WikiPageDraft

    timeout = int(getattr(settings, "worker_job_timeout", 7200) or 7200)
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=max(2 * timeout, 1800))
    async with database.async_session_factory() as session:
        res = await session.execute(
            update(WikiPageDraft)
            .where(
                WikiPageDraft.ai_check_status == "running",
                or_(WikiPageDraft.updated_at.is_(None), WikiPageDraft.updated_at < cutoff),
            )
            .values(ai_check_status="skipped")
        )
        await session.commit()
        n = int(getattr(res, "rowcount", 0) or 0)
    if n:
        logger.info(f"sweep_stuck_ai_review_cron: reset {n} stuck draft(s) to skipped")
    return {"reset": n}


# ---------------------------------------------------------------------------
# Legal maintenance
# ---------------------------------------------------------------------------


async def relink_legal_relations_task(ctx, source_id=None):
    from app import database
    from app.services import legal_relation_extractor

    sid = _as_uuid(source_id) if source_id else None
    async with database.async_session_factory() as session:
        return await legal_relation_extractor.relink_legal_relations(session, source_id=sid)


async def backfill_doc_metadata_task(ctx, only_missing=True, use_llm=True, limit=1000):
    from app import database
    from app.services import doc_metadata_service

    async with database.async_session_factory() as session:
        return await doc_metadata_service.backfill_document_metadata(
            session, only_missing=only_missing, use_llm=use_llm, limit=limit
        )


async def rebuild_wiki_summaries_task(ctx, job_id, page_ids):
    from app.services.wiki_summary_service import run_rebuild

    return await run_rebuild(ctx, job_id, page_ids)
