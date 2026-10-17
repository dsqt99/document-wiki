"""arq worker: background tasks, cron jobs and worker settings.

Ingestion tasks (03) live directly in this module. Tasks owned by other domains live in
``app/tasks/<domain>_tasks.py`` and are exposed here through thin lazy-import wrappers so
that arq can register them by name.
"""

import logging
import os
import time
from pathlib import Path

from arq import cron
from arq.connections import RedisSettings

from app.config import settings

logger = logging.getLogger(__name__)

TEMP_UPLOAD_DIR = Path(__file__).resolve().parent.parent / "temp_uploads"
TEMP_UPLOAD_MAX_AGE_SECONDS = 3600
SKILLS_QUEUE = "skills_queue"


def redis_settings() -> RedisSettings:
    return RedisSettings(
        host=settings.redis_host,
        port=settings.redis_port,
        database=settings.redis_db,
        password=settings.redis_password or None,
    )


async def get_arq_pool():
    from arq import create_pool

    return await create_pool(redis_settings())


async def on_startup(ctx) -> None:
    logger.info("Document Wiki worker starting")


async def on_shutdown(ctx) -> None:
    logger.info("Document Wiki worker stopping")


async def cleanup_temp_uploads_cron(ctx) -> None:
    if not TEMP_UPLOAD_DIR.is_dir():
        return
    now = time.time()
    removed = 0
    for entry in TEMP_UPLOAD_DIR.iterdir():
        try:
            if entry.is_file() and now - entry.stat().st_mtime > TEMP_UPLOAD_MAX_AGE_SECONDS:
                os.remove(entry)
                removed += 1
        except Exception as e:
            logger.warning("Could not remove temp upload %s: %s", entry, e)
    logger.info("cleanup_temp_uploads_cron removed %d file(s)", removed)


# ---------------------------------------------------------------------------
# Ingestion tasks (03) -- implemented in this module.
# ---------------------------------------------------------------------------
# INGESTION-SECTION-BEGIN

import asyncio
import inspect
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone

from app.services import source_status as _source_status
from app.services.source_status import (  # noqa: F401 - re-exported for callers and tests
    compute_source_dual_status,
    reset_branches,
    set_branch_state,
    start_wiki_attempt,
    update_source_dual_status,
    wiki_attempt_of,
)

CAPTION_CONCURRENCY = 4
CAPTION_TIMEOUT_SECONDS = 120
CAPTION_PROMPT = (
    "Mô tả ngắn gọn (1–3 câu) nội dung của hình ảnh này bằng tiếng Việt. "
    "Nếu là sơ đồ, biểu đồ hoặc quy trình, nêu rõ loại hình, các nhãn, số liệu và các bước chính. "
    "Không mở đầu bằng những câu như 'Đây là hình ảnh'. Chỉ trả về văn bản thuần, không định dạng."
)


def _self():
    """This module, so patched attributes (tests) are honoured at call time."""
    return sys.modules[__name__]


def _as_uuid(value) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


async def _pool():
    return await _maybe_await(_self().get_arq_pool())


def _ms_since(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


async def _timing(session, source_id, stage: str, t0: float, metadata: dict | None = None) -> None:
    try:
        from app.models import task_failure

        await task_failure.record_stage_timing(session, source_id, stage, _ms_since(t0), metadata or {})
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not record stage timing %s for %s: %s", stage, source_id, e)


def _flush_langfuse() -> None:
    try:
        from app.ai import tracing

        tracing.flush_langfuse()
    except Exception as e:  # noqa: BLE001
        logger.debug("flush_langfuse failed: %s", e)


def _error_text(exc: BaseException) -> str:
    kind = type(exc).__name__
    message = str(exc).strip() or kind
    return kind if message == kind else f"{kind}: {message}"


def _job_id(job):
    return getattr(job, "job_id", None) if job is not None else None


# ---------------------------------------------------------------------------
# Idempotency and chaining
# ---------------------------------------------------------------------------


async def check_task_attempt_validity(session, source_id, attempt_id_str, branch=None) -> bool:
    if not attempt_id_str:
        return True
    try:
        attempt = uuid.UUID(str(attempt_id_str))
    except (ValueError, TypeError, AttributeError):
        return False
    from sqlalchemy import select

    from app.database.models import Source

    row = (
        await session.execute(
            select(Source.attempt_id, Source.wiki_attempt_id).where(Source.id == _as_uuid(source_id))
        )
    ).one_or_none()
    if row is None:
        return True
    wiki_attempt = getattr(row, "wiki_attempt_id", None)
    current = wiki_attempt if branch == "wiki" and wiki_attempt is not None else getattr(row, "attempt_id", None)
    if current is None:
        return True
    try:
        return _as_uuid(current) == attempt
    except (ValueError, TypeError):
        return False


async def _chain_to_mrp(source_id, attempt_id_str=None):
    args = [source_id] + ([attempt_id_str] if attempt_id_str else [])
    try:
        pool = await _pool()
        job = await pool.enqueue_job("ingest_map_reduce_task", *args)
    except Exception as e:  # noqa: BLE001
        logger.error("Could not enqueue ingest_map_reduce_task for %s: %s", source_id, e)
        return None
    job_id = _job_id(job)
    try:
        import app.database as _db
        from app.database.models import Source

        async with _db.async_session_factory() as session:
            source = await session.get(Source, _as_uuid(source_id))
            if source is not None:
                source.job_id = job_id
                source.progress_message = "Extraction queued..."
                await session.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not store MRP job id for %s: %s", source_id, e)
    return job_id


async def enqueue_post_extraction_pipeline(source_id, has_images, attempt_id_str=None):
    w = _self()
    if not has_images:
        if attempt_id_str:
            return await w._chain_to_mrp(source_id, attempt_id_str)
        return await w._chain_to_mrp(source_id)
    args = [source_id] + ([attempt_id_str] if attempt_id_str else [])
    try:
        pool = await _pool()
        job = await pool.enqueue_job("caption_images_task", *args)
    except Exception as e:  # noqa: BLE001
        logger.error("Could not enqueue caption_images_task for %s: %s", source_id, e)
        return None
    return _job_id(job)


async def mark_wiki_error(source_id, msg) -> None:
    text_msg = str(msg or "")
    await _self().set_branch_state(
        _as_uuid(source_id),
        "wiki",
        status="error",
        progress=0,
        message=f"Wiki error: {text_msg[:200]}",
        error=text_msg,
    )


# ---------------------------------------------------------------------------
# Branch A
# ---------------------------------------------------------------------------


async def commit_and_enqueue_chunk_branch(session, source, attempt_id_str=None):
    source.chunk_attempt_id = uuid.uuid4()
    source.chunk_status = "queued"
    source.chunk_progress = 5
    source.chunk_progress_message = "Queued: chunk & embed raw text"
    source.chunk_error_message = None
    await _source_status.update_source_dual_status(session, source)
    await session.commit()
    attempt = attempt_id_str or (str(source.attempt_id) if source.attempt_id else None)
    pool = await _pool()
    job = await pool.enqueue_job(
        "ingest_source_chunks_task", str(source.id), attempt, str(source.chunk_attempt_id)
    )
    return _job_id(job)


async def ingest_source_chunks_task(ctx, source_id, attempt_id_str=None, chunk_attempt_id_str=None):
    import app.database as _db
    from app.ai import tracing
    from app.database.models import Source

    w = _self()
    sid = _as_uuid(source_id)
    try:
        async with tracing.trace_context("ingest_source_chunks_task", metadata={"source_id": str(sid)}):
            async with _db.async_session_factory() as session:
                try:
                    source = await session.get(Source, sid)
                    if source is None:
                        return {"status": "not_found"}
                    if not await w.check_task_attempt_validity(session, sid, attempt_id_str):
                        return {"status": "stale"}
                    if chunk_attempt_id_str and str(source.chunk_attempt_id) != str(chunk_attempt_id_str):
                        return {"status": "stale"}
                    if not (source.full_text or "").strip():
                        await w.set_branch_state(
                            sid, "chunk", status="error", progress=0,
                            message="No extracted text to chunk", error="No full_text", session=session,
                        )
                        return {"status": "no_text"}
                    await w.set_branch_state(
                        sid, "chunk", status="embedding", progress=20,
                        message="Building chunks with heading hierarchy & embedding...", session=session,
                    )
                    from app.services import verbatim_service

                    t0 = time.perf_counter()
                    n = await verbatim_service.index_source_chunks(session, source)
                    await _timing(session, sid, "source_chunks", t0, {"chunks": n})
                    message = f"Indexed {n} raw chunks" if n > 0 else "No embedding model: keyword search only"
                    await w.set_branch_state(sid, "chunk", status="ready", progress=100, message=message, session=session)
                    return {"status": "ready", "chunks": n}
                except BaseException as exc:
                    err = str(exc) or type(exc).__name__

                    async def _fail():
                        try:
                            try:
                                await session.rollback()
                            except Exception:  # noqa: BLE001
                                pass
                            await w.set_branch_state(
                                sid, "chunk", status="error", progress=0,
                                message=f"Chunking error: {err[:200]}", error=err[:500],
                            )
                        except Exception as e:  # noqa: BLE001
                            logger.warning("Could not mark chunk branch error for %s: %s", sid, e)
                        try:
                            from app.models import task_failure

                            await task_failure.record_task_failure(
                                session=session, task_name="ingest_source_chunks_task", error=exc,
                                source_id=sid, attempt_id=attempt_id_str,
                                payload={"chunk_attempt_id": chunk_attempt_id_str},
                            )
                        except Exception as e:  # noqa: BLE001
                            logger.warning("Could not record task failure for %s: %s", sid, e)

                    try:
                        await asyncio.shield(_fail())
                    except BaseException as e:  # noqa: BLE001
                        logger.warning("Chunk failure handling interrupted for %s: %s", sid, e)
                    raise
    finally:
        _flush_langfuse()


async def finalize_verbatim_source(session, source, tracker) -> dict:
    from app.services import verbatim_service

    w = _self()
    await tracker.update(60, "Indexing verbatim document (no wiki)...")
    await w.set_branch_state(
        source.id, "wiki", status="skipped", progress=100, message="Skipped (verbatim source)", session=session
    )
    await w.set_branch_state(
        source.id, "chunk", status="processing", progress=60, message="Indexing verbatim chunks...", session=session
    )
    n = await verbatim_service.index_source_chunks(session, source)
    source.auto_recover_count = 0
    message = (
        f"Verbatim: indexed {n} chunks, no wiki"
        if n > 0
        else "Verbatim: stored, no embedding model (keyword search only)"
    )
    await w.set_branch_state(source.id, "chunk", status="ready", progress=100, message=message, session=session)
    return {"status": "ready", "verbatim_chunks": n}


# ---------------------------------------------------------------------------
# Dispatch after extraction
# ---------------------------------------------------------------------------


async def dispatch_dual_pipeline(session, source, tracker, token_count, n_images=0, attempt_id_str=None) -> dict:
    w = _self()
    attempt = attempt_id_str or (str(source.attempt_id) if source.attempt_id else None)
    verbatim = bool(getattr(source, "preserve_verbatim", False))
    if verbatim:
        source.wiki_status = "skipped"
        source.wiki_progress = 100
        source.wiki_progress_message = "Skipped (verbatim source)"
    else:
        source.wiki_status = "queued"
        source.wiki_progress = 50
        source.wiki_progress_message = "Waiting to compile wiki..."
        _source_status.start_wiki_attempt(source)
    wiki_attempt = _source_status.wiki_attempt_of(source)

    await w.commit_and_enqueue_chunk_branch(session, source, attempt)

    from app.services import legal_service, processing_mode

    plan = await processing_mode.plan_for(session, source)
    is_legal = plan.articles

    if verbatim or not is_legal:
        try:
            from app.services import doc_metadata_service

            await doc_metadata_service.store_document_metadata(session, source)
            await session.commit()
        except Exception as e:  # noqa: BLE001
            logger.warning("Document metadata extraction failed for %s: %s", source.id, e)
            try:
                await session.rollback()
            except Exception:  # noqa: BLE001
                pass

    if verbatim:
        return {"status": source.status, "branch_a": "queued", "branch_b": "skipped"}

    if plan.verbatim_page or is_legal:
        try:
            if plan.verbatim_page:
                from app.services import verbatim_page_service

                await w.set_branch_state(
                    source.id, "wiki", status="processing", progress=50,
                    message="Creating verbatim wiki page(s)...", session=session,
                )
                return await verbatim_page_service.finalize_verbatim_pages(session, source, tracker)
            await w.set_branch_state(
                source.id, "wiki", status="processing", progress=50,
                message="Parsing legal document articles...", session=session,
            )
            result = await legal_service.finalize_legal_source(session, source, tracker, final=not plan.llm)
            if not plan.llm:
                return result
        except BaseException as exc:
            try:
                await asyncio.shield(w.mark_wiki_error(source.id, _error_text(exc)))
            except BaseException as e:  # noqa: BLE001
                logger.warning("Could not mark wiki error for %s: %s", source.id, e)
            raise

    threshold = int(getattr(settings, "auto_approve_extraction_threshold_tokens", 0) or 0)
    if threshold > 0 and token_count > threshold:
        agg = await w.set_branch_state(
            source.id, "wiki", status="awaiting_approval", progress=55,
            message=f"Awaiting approval for wiki compilation: {token_count:,} tokens > {threshold:,} threshold",
            session=session,
        )
        return {"status": agg, "token_count": token_count, "images": n_images}

    message = f"Captioning {n_images} images before extraction..." if n_images > 0 else "Extraction queued..."
    agg = await w.set_branch_state(source.id, "wiki", status="processing", progress=55, message=message, session=session)
    job_id = await w.enqueue_post_extraction_pipeline(
        str(source.id), has_images=n_images > 0, attempt_id_str=wiki_attempt
    )
    if job_id:
        source.job_id = job_id
        await session.commit()
    return {"status": agg, "token_count": token_count, "images": n_images}


# ---------------------------------------------------------------------------
# Ingest entry points
# ---------------------------------------------------------------------------


async def _handle_ingest_failure(sid, exc, task_name, attempt_id_str, payload, error_msg) -> None:
    """Mark the source failed and always write exactly one dead-letter record."""
    import app.database as _db
    from app.database.models import Source

    w = _self()

    async def _record(session):
        try:
            from app.models import task_failure

            await task_failure.record_task_failure(
                session=session, task_name=task_name, error=exc,
                source_id=sid, attempt_id=attempt_id_str, payload=payload,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("Could not record dead-letter for %s: %s", sid, e)

    async def _work():
        try:
            factory_cm = _db.async_session_factory()
        except Exception as e:  # noqa: BLE001
            logger.warning("Failure handling for %s could not open a session: %s", sid, e)
            await _record(None)
            return
        recorded = False
        try:
            async with factory_cm as session:
                try:
                    source = await session.get(Source, sid)
                    if source is not None:
                        if (source.chunk_status or "pending") != "pending":
                            await w.mark_wiki_error(sid, error_msg)
                        else:
                            source.status = "error"
                            source.error_message = error_msg
                            source.progress = 0
                            source.progress_message = f"Error: {error_msg[:200]}"
                            await session.commit()
                except Exception as e:  # noqa: BLE001
                    logger.warning("Could not mark %s as failed: %s", sid, e)
                    try:
                        await session.rollback()
                    except Exception:  # noqa: BLE001
                        pass
                recorded = True
                await _record(session)
        except Exception as e:  # noqa: BLE001
            logger.warning("Failure handling for %s could not use a session: %s", sid, e)
            if not recorded:
                await _record(None)

    try:
        await asyncio.shield(_work())
    except BaseException as e:  # noqa: BLE001
        logger.warning("Failure handling for %s interrupted: %s", sid, e)


async def _vision_provider(session):
    try:
        from app.ai import registry

        return await registry.ProviderRegistry(session).get_vision()
    except Exception as e:  # noqa: BLE001
        logger.info("No vision provider available: %s", e)
        return None


async def _store_extracted_text(session, source, pages) -> int:
    from app.services import source_outline
    from app.utils.tokens import count_tokens

    source.outline_json = source_outline.build_outline(pages)
    full_text, page_offsets = source_outline.assemble_full_text(pages)
    token_count = count_tokens(full_text)
    source.full_text = full_text
    source.page_offsets = page_offsets
    source.extracted_token_count = token_count
    await session.commit()
    return token_count


async def ingest_file_task(ctx, source_id, attempt_id_str=None):
    import app.database as _db
    from app.ai import tracing
    from app.database.models import Source, SourceImage
    from app.utils.progress import ProgressTracker

    w = _self()
    sid = _as_uuid(source_id)
    tracker = ProgressTracker(sid)
    file_name = None
    try:
        async with tracing.trace_context(
            "ingest_file_task", metadata={"source_id": str(sid), "attempt_id": attempt_id_str}
        ):
            async with _db.async_session_factory() as session:
                source = await session.get(Source, sid)
                if source is None:
                    return None
                if not await w.check_task_attempt_validity(session, sid, attempt_id_str):
                    logger.info("ingest_file_task: stale attempt %s for %s, skipping", attempt_id_str, sid)
                    return None
                if not source.minio_key:
                    raise ValueError("Source has no stored file")
                file_name = source.file_name or str(source.minio_key).rsplit("/", 1)[-1]

                _source_status.reset_branches(source, wiki_skipped=bool(source.preserve_verbatim))
                source.status = "processing"
                source.progress = 0
                source.progress_message = "Starting processing..."
                await session.commit()

                from app.services import storage_service as storage_mod

                await tracker.update(5, "Loading file...")
                t0 = time.perf_counter()
                data = await asyncio.to_thread(storage_mod.storage_service.download_file, source.minio_key)
                await _timing(session, sid, "download", t0, {"size_bytes": len(data)})
                await tracker.update(10, "File loaded")

                await tracker.update(15, "Extracting text (per page)...")
                vision = await _vision_provider(session)
                from app.services import kb_service

                t0 = time.perf_counter()
                pages = await kb_service._extract_text_from_file(
                    data, file_name, vision_provider=vision, tracker=tracker
                )
                pages = list(pages or [])
                await _timing(session, sid, "parse", t0, {"pages_count": len(pages)})
                if not any((p.get("content") or "").strip() for p in pages):
                    source.status = "error"
                    source.error_message = "Unable to extract text content"
                    source.progress = 0
                    await session.commit()
                    return {"status": "error", "message": "No text content"}
                await tracker.update(25, "Text extraction complete")

                await tracker.update(30, "Extracting images...")
                from app.services import image_service

                t0 = time.perf_counter()
                images = await asyncio.to_thread(image_service.extract_images, data, file_name, str(sid))
                for img in images:
                    row = SourceImage(
                        source_id=sid,
                        minio_key=img.minio_key,
                        page_number=img.page_number,
                        image_index=img.image_index,
                        caption=img.caption,
                        content_type=img.content_type,
                        size_bytes=img.size_bytes,
                    )
                    session.add(row)
                    await session.flush()
                    img.image_id = str(row.id)
                kb_service._inline_image_markers(pages, images)
                await _timing(session, sid, "extract_images", t0, {"images_count": len(images)})
                await tracker.update(40, f"Analyzed {len(images)} images")

                await tracker.update(45, "Building document outline...")
                t0 = time.perf_counter()
                token_count = await _store_extracted_text(session, source, pages)
                await _timing(session, sid, "outline", t0, {"token_count": token_count})
                await tracker.update(50, f"Outline ready, ~{token_count} tokens")

                return await w.dispatch_dual_pipeline(
                    session, source, tracker, token_count, n_images=len(images), attempt_id_str=attempt_id_str
                )
    except BaseException as exc:
        await _handle_ingest_failure(
            sid, exc, "ingest_file_task", attempt_id_str,
            {"file_name": file_name} if file_name else None, _error_text(exc),
        )
        raise
    finally:
        _flush_langfuse()


async def ingest_url_task(ctx, source_id, attempt_id_str=None):
    import app.database as _db
    from app.ai import tracing
    from app.database.models import Source
    from app.utils.progress import ProgressTracker

    w = _self()
    sid = _as_uuid(source_id)
    tracker = ProgressTracker(sid)
    url = None
    try:
        async with tracing.trace_context(
            "ingest_url_task", metadata={"source_id": str(sid), "attempt_id": attempt_id_str}
        ):
            async with _db.async_session_factory() as session:
                source = await session.get(Source, sid)
                if source is None:
                    return None
                if not await w.check_task_attempt_validity(session, sid, attempt_id_str):
                    return None
                url = source.url
                _source_status.reset_branches(source, wiki_skipped=bool(source.preserve_verbatim))
                source.status = "processing"
                source.progress = 0
                source.progress_message = "Starting processing..."
                await session.commit()

                await tracker.update(15, "Fetching content from URL...")
                if not url:
                    raise ValueError("Source has no URL")
                from app.services import kb_service

                t0 = time.perf_counter()
                pages = list(await kb_service._extract_text_from_url(url) or [])
                await _timing(session, sid, "fetch_url", t0, {"pages_count": len(pages)})
                if not any((p.get("content") or "").strip() for p in pages):
                    source.status = "error"
                    source.error_message = "Unable to fetch content from URL"
                    source.progress = 0
                    await session.commit()
                    return {"status": "error", "message": "No content"}

                await tracker.update(40, "Building outline...")
                t0 = time.perf_counter()
                token_count = await _store_extracted_text(session, source, pages)
                await _timing(session, sid, "outline", t0, {"token_count": token_count})

                return await w.dispatch_dual_pipeline(
                    session, source, tracker, token_count, n_images=0, attempt_id_str=attempt_id_str
                )
    except BaseException as exc:
        await _handle_ingest_failure(
            sid, exc, "ingest_url_task", attempt_id_str,
            {"url": url} if url else None, (str(exc) or type(exc).__name__)[:500],
        )
        raise
    finally:
        _flush_langfuse()


# ---------------------------------------------------------------------------
# Branch B: image captions before MRP
# ---------------------------------------------------------------------------


def _clean_caption(caption: str) -> str:
    text = re.sub(r"\s*\n\s*", " ", caption or "")
    return text.replace("[", "(").replace("]", ")").strip()


async def _caption_one(vision, row):
    import app.database as _db
    from app.database.models import SourceImage
    from app.services import storage_service as storage_mod

    data = await asyncio.to_thread(storage_mod.storage_service.download_file, row.minio_key)
    caption = await asyncio.wait_for(
        vision.analyze_image(data, row.content_type or "image/png", prompt=CAPTION_PROMPT),
        timeout=CAPTION_TIMEOUT_SECONDS,
    )
    caption = (caption or "").strip() if isinstance(caption, str) else ""
    if not caption:
        return row, None
    async with _db.async_session_factory() as s:
        db_row = await s.get(SourceImage, row.id)
        if db_row is not None:
            db_row.caption = caption
            await s.commit()
    return row, caption


async def caption_images_task(ctx, source_id, attempt_id_str=None):
    import app.database as _db
    from app.ai import tracing
    from app.database.models import Source, SourceImage

    w = _self()
    sid = _as_uuid(source_id)
    state = {"chained": False}

    async def _chain():
        state["chained"] = True
        if attempt_id_str:
            return await w._chain_to_mrp(source_id, attempt_id_str)
        return await w._chain_to_mrp(source_id)

    try:
        async with tracing.trace_context("caption_images_task", metadata={"source_id": str(sid)}):
            async with _db.async_session_factory() as session:
                source = await session.get(Source, sid)
                if source is None:
                    return None
                if not await w.check_task_attempt_validity(session, sid, attempt_id_str, branch="wiki"):
                    return None

                from app.ai import registry

                vision = await registry.ProviderRegistry(session).get_vision()
                if vision is None:
                    await _chain()
                    return None

                from sqlalchemy import select

                rows = list(
                    (
                        await session.execute(
                            select(SourceImage)
                            .where(SourceImage.source_id == sid)
                            .order_by(SourceImage.image_index)
                        )
                    ).scalars().all()
                )
                if not rows:
                    await _chain()
                    return None

                sem = asyncio.Semaphore(CAPTION_CONCURRENCY)

                async def _guarded(row):
                    async with sem:
                        try:
                            return await _caption_one(vision, row)
                        except Exception as e:  # noqa: BLE001
                            logger.warning("Captioning image %s of %s failed: %s", row.id, sid, e)
                            return row, None

                results = await asyncio.gather(*(_guarded(r) for r in rows))
                captions = {str(r.id): c for r, c in results if c}

                text = source.full_text or ""
                new_text = text
                for image_id, caption in captions.items():
                    alt = _clean_caption(caption)
                    new_text = re.sub(
                        r"!\[[^\]\n]*\]\(image://" + re.escape(image_id) + r"\)",
                        lambda _m, a=alt, i=image_id: f"![{a}](image://{i})",
                        new_text,
                    )
                if new_text != text:
                    source.full_text = new_text
                    await session.commit()

                try:
                    from app.services import image_service

                    chunks = []
                    for row, caption in results:
                        if not caption:
                            continue
                        info = image_service.ImageInfo(
                            row.minio_key, row.page_number, row.image_index, row.content_type, row.size_bytes,
                            caption=caption, image_id=str(row.id),
                        )
                        chunks.append(image_service.create_image_chunk(info, "image_caption", caption))
                    if chunks:
                        await image_service.index_image_chunks(session, sid, chunks)
                        await session.commit()
                except Exception as e:  # noqa: BLE001
                    logger.warning("Indexing image captions for %s failed: %s", sid, e)

                await _chain()
                return {"status": "ok", "captioned": len(captions), "images": len(rows)}
    except BaseException:
        if not state["chained"]:
            try:
                await asyncio.shield(_chain())
            except BaseException as e:  # noqa: BLE001
                logger.warning("Could not chain %s to MRP after caption failure: %s", sid, e)
        raise
    finally:
        _flush_langfuse()


# ---------------------------------------------------------------------------
# Scope changes
# ---------------------------------------------------------------------------


def _scope_pairs(old_scopes) -> list:
    pairs = []
    for item in old_scopes or []:
        try:
            scope_type, scope_id = item[0], item[1]
        except (TypeError, IndexError, KeyError):
            continue
        scope_type = scope_type or "global"
        parsed = None
        if scope_id:
            try:
                parsed = _as_uuid(scope_id)
            except (ValueError, TypeError):
                parsed = None
        pairs.append((scope_type, parsed))
    return pairs


async def _detach_and_reindex(session, sid, old_scopes) -> None:
    from app.services import wiki_service

    await wiki_service.detach_source_from_wiki(session, sid)
    for scope_type, scope_id in _scope_pairs(old_scopes):
        try:
            await wiki_service.regenerate_index(session, scope_type=scope_type, scope_id=scope_id)
        except Exception as e:  # noqa: BLE001
            logger.warning("regenerate_index(%s, %s) failed: %s", scope_type, scope_id, e)


async def reassign_source_scope_task(ctx, source_id, old_scopes):
    import app.database as _db
    from app.database.models import Source
    from app.utils.progress import ProgressTracker

    w = _self()
    sid = _as_uuid(source_id)
    tracker = ProgressTracker(sid)
    await tracker.update(0, "Detaching from old wiki scopes...")
    async with _db.async_session_factory() as session:
        source = await session.get(Source, sid)
        if source is None:
            return {"status": "not_found"}
        await _detach_and_reindex(session, sid, old_scopes)
        await session.commit()
        await w.set_branch_state(
            sid, "wiki", status="queued", progress=5, message="Re-queued after scope change...", session=session
        )
        pool = await _pool()
        job = await pool.enqueue_job("ingest_map_reduce_task", str(sid))
        job_id = _job_id(job)
        if job_id:
            source.job_id = job_id
            await session.commit()
        return {"status": "queued", "job_id": job_id}


async def detach_source_wiki_task(ctx, source_id, old_scopes):
    import app.database as _db

    sid = _as_uuid(source_id)
    async with _db.async_session_factory() as session:
        await _detach_and_reindex(session, sid, old_scopes)
        await session.commit()
    return {"status": "detached"}


# ---------------------------------------------------------------------------
# Cron
# ---------------------------------------------------------------------------


async def sweep_stuck_processing_cron(ctx):
    import app.database as _db
    from sqlalchemy import or_, select

    from app.database.models import Source
    from app.models import task_failure
    from app.utils.progress import WIKI_ACTIVE

    threshold_s = max(2 * int(settings.worker_job_timeout), 1800)
    minutes = threshold_s // 60
    cap = int(settings.max_auto_recover_attempts)
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=threshold_s)
    swept = 0
    async with _db.async_session_factory() as session:
        rows = (
            await session.execute(
                select(Source).where(
                    Source.status == "processing",
                    or_(Source.updated_at < cutoff, Source.updated_at.is_(None)),
                )
            )
        ).scalars().all()
        for source in rows:
            n = int(source.auto_recover_count or 0) + 1
            source.auto_recover_count = n
            if n >= cap:
                msg = (
                    f"Worker died with no progress for >{minutes} min on {n} consecutive attempts (cap={cap}). "
                    "Retry is blocked — check LLM provider config and source file, then ask an admin to reset "
                    "auto_recover_count."
                )
            else:
                msg = (
                    f"Worker died with no progress for >{minutes} min. Press Retry to try again "
                    f"({n}/{cap} auto-recoveries used)."
                )
            touched = False
            if (source.chunk_status or "pending") in _source_status.CHUNK_ACTIVE:
                source.chunk_status = "error"
                source.chunk_progress = 0
                source.chunk_progress_message = msg
                source.chunk_error_message = msg
                touched = True
            if (source.wiki_status or "pending") in WIKI_ACTIVE:
                source.wiki_status = "error"
                source.wiki_progress = 0
                source.wiki_progress_message = msg
                source.wiki_error_message = msg
                touched = True
            if touched:
                source.error_message = msg
                agg = _source_status.compute_source_dual_status(source)
                if isinstance(agg, tuple) and len(agg) == 3:
                    source.status, source.progress, source.progress_message = agg
                elif isinstance(agg, str):
                    source.status = agg
            else:
                source.status = "error"
                source.error_message = msg
                source.progress_message = msg
            await task_failure.record_task_failure(
                session=session, task_name=source.job_id or "pipeline_stuck_sweep", error=TimeoutError(msg),
                source_id=source.id, attempt_id=source.attempt_id,
                payload={"auto_recover_count": n, "cap": cap},
            )
            swept += 1
        await session.commit()
    if swept:
        logger.warning("sweep_stuck_processing_cron marked %d stuck source(s) as failed", swept)
    return swept


async def cleanup_orphan_awaiting_approval_cron(ctx):
    import app.database as _db
    from sqlalchemy import select

    from app.database.models import Source
    from app.services import storage_service as storage_mod

    ttl_hours = max(1, int(settings.extraction_approval_ttl_hours))
    cutoff = datetime.now(timezone.utc) - timedelta(hours=ttl_hours)
    removed = 0
    async with _db.async_session_factory() as session:
        rows = (
            await session.execute(
                select(Source).where(Source.status == "awaiting_approval", Source.updated_at < cutoff)
            )
        ).scalars().all()
        for source in rows:
            if source.minio_key:
                try:
                    await asyncio.to_thread(storage_mod.storage_service.delete_object, source.minio_key)
                except Exception as e:  # noqa: BLE001
                    logger.warning("Could not delete object %s: %s", source.minio_key, e)
            await session.delete(source)
            removed += 1
        await session.commit()
    if removed:
        logger.info("cleanup_orphan_awaiting_approval_cron removed %d source(s)", removed)
    return removed


# INGESTION-SECTION-END


# ---------------------------------------------------------------------------
# Wrappers for tasks owned by other domains (lazy import, delegate by name).
# ---------------------------------------------------------------------------


async def reembed_all_pages_task(ctx, *args, **kwargs):
    from app.tasks import retrieval_tasks

    return await retrieval_tasks.reembed_all_pages_task(ctx, *args, **kwargs)


async def backfill_source_chunks_task(ctx, *args, **kwargs):
    from app.tasks import retrieval_tasks

    return await retrieval_tasks.backfill_source_chunks_task(ctx, *args, **kwargs)


async def generate_questions_task(ctx, *args, **kwargs):
    from app.tasks import retrieval_tasks

    return await retrieval_tasks.generate_questions_task(ctx, *args, **kwargs)


async def ingest_map_reduce_task(ctx, *args, **kwargs):
    from app.tasks import wiki_tasks

    return await wiki_tasks.ingest_map_reduce_task(ctx, *args, **kwargs)


async def ingest_refine_task(ctx, *args, **kwargs):
    from app.tasks import wiki_tasks

    return await wiki_tasks.ingest_refine_task(ctx, *args, **kwargs)


async def regenerate_plan_task(ctx, *args, **kwargs):
    from app.tasks import wiki_tasks

    return await wiki_tasks.regenerate_plan_task(ctx, *args, **kwargs)


async def ai_pre_review_draft_task(ctx, *args, **kwargs):
    from app.tasks import wiki_tasks

    return await wiki_tasks.ai_pre_review_draft_task(ctx, *args, **kwargs)


async def sweep_stuck_ai_review_cron(ctx):
    from app.tasks import wiki_tasks

    return await wiki_tasks.sweep_stuck_ai_review_cron(ctx)


async def relink_legal_relations_task(ctx, *args, **kwargs):
    from app.tasks import wiki_tasks

    return await wiki_tasks.relink_legal_relations_task(ctx, *args, **kwargs)


async def backfill_doc_metadata_task(ctx, *args, **kwargs):
    from app.tasks import wiki_tasks

    return await wiki_tasks.backfill_doc_metadata_task(ctx, *args, **kwargs)


async def ingest_skill_task(ctx, *args, **kwargs):
    from app.tasks import skill_tasks

    return await skill_tasks.ingest_skill_task(ctx, *args, **kwargs)


async def delete_skill_task(ctx, *args, **kwargs):
    from app.tasks import skill_tasks

    return await skill_tasks.delete_skill_task(ctx, *args, **kwargs)


async def daily_stats_rollup_cron(ctx):
    from app.tasks import skill_tasks

    return await skill_tasks.daily_stats_rollup_cron(ctx)


# ---------------------------------------------------------------------------
# Worker settings
# ---------------------------------------------------------------------------


def _caption_function():
    from arq.worker import func

    return func(caption_images_task, name="caption_images_task", timeout=3600)


class WorkerSettings:
    functions = [
        ingest_file_task,
        ingest_url_task,
        ingest_source_chunks_task,
        backfill_source_chunks_task,
        _caption_function(),
        ingest_map_reduce_task,
        ingest_refine_task,
        regenerate_plan_task,
        reembed_all_pages_task,
        ai_pre_review_draft_task,
        reassign_source_scope_task,
        detach_source_wiki_task,
        relink_legal_relations_task,
        backfill_doc_metadata_task,
        generate_questions_task,
    ]
    redis_settings = redis_settings()
    on_startup = on_startup
    on_shutdown = on_shutdown
    max_jobs = settings.worker_max_jobs
    job_timeout = settings.worker_job_timeout
    max_tries = 3
    retry_delay = 10
    health_check_interval = 30
    cron_jobs = [
        cron(daily_stats_rollup_cron, hour={2}, minute={0}),
        cron(sweep_stuck_ai_review_cron, minute={0, 10, 20, 30, 40, 50}),
        cron(sweep_stuck_processing_cron, minute={5, 15, 25, 35, 45, 55}),
        cron(cleanup_orphan_awaiting_approval_cron, minute={15}),
    ]


class SkillWorkerSettings:
    functions = [ingest_skill_task, delete_skill_task]
    queue_name = SKILLS_QUEUE
    redis_settings = redis_settings()
    on_startup = on_startup
    on_shutdown = on_shutdown
    max_jobs = settings.worker_max_jobs
    job_timeout = settings.worker_job_timeout
    max_tries = 3
    retry_delay = 10
    health_check_interval = 30
    cron_jobs = [cron(cleanup_temp_uploads_cron, minute={0})]
