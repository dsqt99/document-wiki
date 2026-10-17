"""Background jobs for the retrieval layer (run by arq through app.worker wrappers).

- reembed_all_pages_task: migrate every wiki page / source chunk to a new
  embedding spec, then flip the active spec atomically.
- backfill_source_chunks_task: queue raw-chunk indexing for sources that
  never got it (or all of them with force=True).
- generate_questions_task: generated search questions per legal provision.

All imports are lazy so the worker module stays cheap to import and tests can
patch the symbols at their home modules.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from loguru import logger

REEMBED_BATCH_SIZE = 50
_SKIP_SLUGS = ("_index", "_log")
QUESTIONS_PER_PROVISION = 3


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_uuid(value: Any) -> Optional[uuid.UUID]:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Re-embed migration
# ---------------------------------------------------------------------------

async def _mark_job(job_id: uuid.UUID, **fields) -> None:
    from app.database import async_session_factory
    from app.database.models import EmbeddingJob

    async with async_session_factory() as session:
        job = await session.get(EmbeddingJob, job_id)
        if job is None:
            return
        for k, v in fields.items():
            setattr(job, k, v)
        await session.commit()


async def _job_status(job_id: uuid.UUID) -> Optional[str]:
    from sqlalchemy import select

    from app.database import async_session_factory
    from app.database.models import EmbeddingJob

    async with async_session_factory() as session:
        res = await session.execute(select(EmbeddingJob.status).where(EmbeddingJob.id == job_id))
        return res.scalar_one_or_none()


async def reembed_all_pages_task(ctx, job_id) -> dict:
    from sqlalchemy import func, or_, and_, select

    from app.ai.embedding_catalog import get_spec
    from app.ai.registry import ProviderRegistry
    from app.database import async_session_factory
    from app.database.models import EmbeddingJob, Source, WikiPage
    from app.services import embedding_storage
    from app.services.config_service import ACTIVE_EMBEDDING_MODEL_KEY, ConfigService

    jid = _as_uuid(job_id)
    if jid is None:
        return {"status": "invalid_job_id", "job_id": str(job_id)}

    # 1-3. Load job, validate spec/provider, count pages, mark running.
    async with async_session_factory() as session:
        job = await session.get(EmbeddingJob, jid)
        if job is None:
            return {"status": "not_found", "job_id": str(jid)}
        if job.status not in ("pending", "running"):
            return {"status": "skipped", "job_id": str(jid), "job_status": job.status}
        try:
            spec = get_spec(job.model_spec_id)
        except KeyError:
            job.status = "failed"
            job.error_message = f"Unknown embedding model: {job.model_spec_id}"
            job.finished_at = _now()
            await session.commit()
            return {"status": "failed", "job_id": str(jid), "error": job.error_message}
        try:
            await ProviderRegistry(session).get_embedding(task="document", spec_id=spec.id)
        except Exception as exc:
            job.status = "failed"
            job.error_message = f"Embedding provider init failed: {exc}"[:2000]
            job.finished_at = _now()
            await session.commit()
            return {"status": "failed", "job_id": str(jid), "error": job.error_message}

        total = (
            await session.execute(
                select(func.count()).select_from(WikiPage).where(WikiPage.slug.notin_(_SKIP_SLUGS))
            )
        ).scalar_one()
        job.total_pages = int(total or 0)
        job.done_pages = 0
        job.status = "running"
        job.started_at = _now()
        job.error_message = None
        await session.commit()

    from app.services.wiki_chunk_service import index_wiki_page_chunks

    # 4. Pages in batches, each batch in its own session.
    done = 0
    offset = 0
    while True:
        if await _job_status(jid) == "cancelled":
            logger.info(f"reembed job {jid} cancelled after {done} pages")
            return {"status": "cancelled", "job_id": str(jid), "done_pages": done}
        async with async_session_factory() as session:
            res = await session.execute(
                select(WikiPage)
                .where(WikiPage.slug.notin_(_SKIP_SLUGS))
                .order_by(WikiPage.created_at, WikiPage.id)
                .offset(offset)
                .limit(REEMBED_BATCH_SIZE)
            )
            pages = list(res.scalars().all())
            if not pages:
                break
            try:
                for page in pages:
                    await index_wiki_page_chunks(session, page, spec_id=spec.id)
                await session.commit()
            except Exception as exc:
                await session.rollback()
                msg = f"Embedding API failed: {exc}"[:2000]
                logger.error(f"reembed job {jid}: {msg}")
                await _mark_job(jid, status="failed", error_message=msg, finished_at=_now())
                return {"status": "failed", "job_id": str(jid), "error": msg}
        done += len(pages)
        offset += len(pages)
        await _mark_job(jid, done_pages=done)

    # 5. Raw source chunks.
    from app.services import verbatim_service

    async with async_session_factory() as session:
        res = await session.execute(
            select(Source.id).where(
                or_(
                    Source.chunk_status == "ready",
                    and_(Source.preserve_verbatim.is_(True), Source.status == "ready"),
                )
            ).order_by(Source.created_at)
        )
        source_ids = [row[0] for row in res.all()]
    reindexed = 0
    for sid in source_ids:
        if await _job_status(jid) == "cancelled":
            return {"status": "cancelled", "job_id": str(jid), "done_pages": done}
        async with async_session_factory() as session:
            try:
                src = await session.get(Source, sid)
                if src is None:
                    continue
                await verbatim_service.index_source_chunks(session, src, spec.id)
                await session.commit()
                reindexed += 1
            except Exception as exc:
                await session.rollback()
                logger.warning(f"reembed job {jid}: source {sid} re-index failed: {exc}")

    # 6. Final cancel check, then atomic flip + cleanup.
    if await _job_status(jid) == "cancelled":
        return {"status": "cancelled", "job_id": str(jid), "done_pages": done}
    async with async_session_factory() as session:
        job = await session.get(EmbeddingJob, jid)
        if job is None:
            return {"status": "not_found", "job_id": str(jid)}
        if job.status == "cancelled":
            return {"status": "cancelled", "job_id": str(jid), "done_pages": done}
        await ConfigService(session).set(ACTIVE_EMBEDDING_MODEL_KEY, spec.id)
        removed_pages = await embedding_storage.cleanup_stale_embeddings(session, spec.id)
        removed_src = await embedding_storage.cleanup_stale_source_chunk_embeddings(session, spec.id)
        removed_wiki = await embedding_storage.cleanup_stale_wiki_chunk_embeddings(session, spec.id)
        job.status = "completed"
        job.done_pages = done
        job.finished_at = _now()
        await session.commit()

    logger.info(
        f"reembed job {jid} completed: {done} pages, {reindexed} sources; "
        f"pruned {removed_pages}/{removed_src}/{removed_wiki} stale rows"
    )
    return {
        "status": "completed",
        "job_id": str(jid),
        "done_pages": done,
        "sources_reindexed": reindexed,
    }


# ---------------------------------------------------------------------------
# Raw-chunk backfill
# ---------------------------------------------------------------------------

async def backfill_source_chunks_task(ctx, limit: int = 500, force: bool = False) -> dict:
    from sqlalchemy import select

    import app.worker as worker
    from app.database import async_session_factory
    from app.database.models import Source

    async with async_session_factory() as session:
        stmt = select(Source).where(
            Source.status.in_(("ready", "partial")),
            Source.full_text.isnot(None),
            Source.full_text != "",
        )
        if not force:
            stmt = stmt.where(Source.chunk_status.in_(("pending", "error")))
        stmt = stmt.order_by(Source.created_at).limit(max(int(limit or 0), 0))
        sources = list((await session.execute(stmt)).scalars().all())

        enqueue = getattr(worker, "commit_and_enqueue_chunk_branch", None)
        enqueued = 0
        if enqueue is None:
            logger.error("backfill_source_chunks_task: app.worker.commit_and_enqueue_chunk_branch missing")
        else:
            for src in sources:
                try:
                    job = await enqueue(session, src)
                    if job:
                        enqueued += 1
                except Exception as exc:
                    logger.warning(f"backfill: could not enqueue source {src.id}: {exc}")
    return {"candidates": len(sources), "enqueued": enqueued}


# ---------------------------------------------------------------------------
# Generated questions
# ---------------------------------------------------------------------------

def _unit_title(unit) -> str:
    kind = (str(getattr(unit, "unit_type", "") or "")).strip()
    kind = getattr(getattr(unit, "unit_type", None), "value", None) or kind
    number = getattr(unit, "unit_number", None) or ""
    name = getattr(unit, "title", None) or ""
    return f"{str(kind).capitalize()} {number}: {name}".strip()


def _verbatim_chunker():
    from app.services import verbatim_service

    return getattr(verbatim_service, "build_verbatim_chunks", None) or verbatim_service.build_source_chunks


async def generate_questions_task(
    ctx, source_id, attempt_id_str: Optional[str] = None, max_provisions: int = 15
) -> dict:
    from sqlalchemy import select

    import app.worker as worker
    from app.ai.registry import ProviderRegistry
    from app.database import async_session_factory
    from app.database.models import LegalUnit, Source
    from app.services import question_generator as qg

    sid_str = str(source_id)
    sid = _as_uuid(source_id)
    if sid is None:
        return {"status": "not_found", "source_id": sid_str}

    async with async_session_factory() as session:
        check = getattr(worker, "check_task_attempt_validity", None)
        if check is not None and not await check(session, sid, attempt_id_str):
            return {"status": "stale", "source_id": sid_str}

        source = await session.get(Source, sid)
        if source is None:
            return {"status": "not_found", "source_id": sid_str}

        llm = await ProviderRegistry(session).get_llm()
        generator = qg.QuestionGenerator(llm_provider=llm)

        res = await session.execute(
            select(LegalUnit)
            .where(LegalUnit.source_id == source.id)
            .order_by(LegalUnit.created_at, LegalUnit.id)
            .limit(max_provisions)
        )
        units = list(res.scalars().all())

        chunks: list[dict] = []
        questions_total = 0
        if units:
            for idx, unit in enumerate(units):
                questions = await generator.generate_questions_for_chunk(
                    text=unit.content or "",
                    title=_unit_title(unit),
                    max_questions=QUESTIONS_PER_PROVISION,
                )
                if not questions:
                    continue
                questions_total += len(questions)
                chunks.extend(
                    qg.build_question_chunks(
                        source.id, idx, questions, page_number=1, context_preview=unit.content or ""
                    )
                )
        else:
            raw_chunks = _verbatim_chunker()(source.full_text or "", source.page_offsets or [])
            for chunk in list(raw_chunks)[:max_provisions]:
                questions = await generator.generate_questions_for_chunk(
                    text=chunk.text,
                    title=source.title,
                    max_questions=QUESTIONS_PER_PROVISION,
                )
                if not questions:
                    continue
                questions_total += len(questions)
                chunks.extend(
                    qg.build_question_chunks(
                        source.id,
                        chunk.index,
                        questions,
                        page_number=getattr(chunk, "page_number", 1) or 1,
                        context_preview=chunk.text,
                    )
                )

        indexed = 0
        if chunks:
            indexed = await qg.index_question_chunks(session, source.id, chunks)
            await session.commit()

    return {
        "status": "success",
        "source_id": sid_str,
        "questions_generated": questions_total,
        "chunks_indexed": indexed,
    }
