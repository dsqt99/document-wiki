"""
arq Worker — async Redis queue for document ingestion.

The worker now compiles each source into the LLM Wiki (markdown pages stored
in PostgreSQL) instead of producing chunk embeddings. See app/ai/wiki_compiler.py.

Start with:
    arq app.worker.WorkerSettings
"""

import asyncio
import time
import uuid
import zipfile
from typing import Optional

from arq import cron
from arq import func as arq_func
from arq.connections import ArqRedis, RedisSettings, create_pool
from loguru import logger
from sqlalchemy import select

from app.config import settings


def _get_redis_settings() -> RedisSettings:
    return RedisSettings(
        host=settings.redis_host,
        port=settings.redis_port,
        database=settings.redis_db,
        password=settings.redis_password or None,
    )


# arq Redis pool (lazy init)
_arq_pool: Optional[ArqRedis] = None


async def get_arq_pool() -> ArqRedis:
    """Lazy-init arq Redis connection pool."""
    global _arq_pool
    if _arq_pool is None:
        _arq_pool = await create_pool(_get_redis_settings())
    return _arq_pool


# ---------------------------------------------------------------------------
# Progress helper (re-exported from utils for backward compatibility)
# ---------------------------------------------------------------------------

from app.utils.progress import ProgressTracker  # noqa: E402

# ---------------------------------------------------------------------------
# Ingestion tasks
# ---------------------------------------------------------------------------

async def check_task_attempt_validity(
    session, source_id: uuid.UUID, attempt_id_str: Optional[str], branch: Optional[str] = None,
) -> bool:
    """Validate whether the task's attempt_id matches the current attempt in DB.

    If attempt_id_str is None, it defaults to valid (backward compatibility).
    branch=None checks source.attempt_id (whole-source jobs). branch="wiki"
    checks source.wiki_attempt_id, falling back to source.attempt_id while no
    wiki attempt was started, so retrying branch B invalidates only old
    branch-B jobs. A mismatch means a stale job from an older attempt.
    """
    if not attempt_id_str:
        return True
    try:
        expected = uuid.UUID(attempt_id_str)
    except ValueError:
        return False
    from app.database.models import Source

    row = (await session.execute(
        select(Source.attempt_id, Source.wiki_attempt_id).where(Source.id == source_id)
    )).one_or_none()
    if row is None:
        return True
    curr_attempt = row.attempt_id
    if branch == "wiki" and row.wiki_attempt_id is not None:
        curr_attempt = row.wiki_attempt_id
    return curr_attempt is None or curr_attempt == expected


async def _chain_to_mrp(source_id: str, attempt_id_str: Optional[str] = None) -> Optional[str]:
    """Chain execution to ingest_map_reduce_task and update source state."""
    from app.database import async_session_factory
    from app.database.models import Source

    pool = await get_arq_pool()
    args = [source_id]
    if attempt_id_str:
        args.append(attempt_id_str)
    job = await pool.enqueue_job("ingest_map_reduce_task", *args)
    if job:
        try:
            sid = uuid.UUID(source_id)
            async with async_session_factory() as session:
                source = await session.get(Source, sid)
                if source:
                    source.job_id = job.job_id
                    source.progress_message = "Extraction queued..."
                    await session.commit()
        except Exception as e:
            logger.warning(f"_chain_to_mrp: failed to update source {source_id} state: {e}")
        logger.info(f"Successfully chained to ingest_map_reduce_task for {source_id}")
        return job.job_id
    logger.error(f"_chain_to_mrp: failed to enqueue ingest_map_reduce_task for {source_id}")
    return None


async def enqueue_post_extraction_pipeline(source_id: str, has_images: bool, attempt_id_str: Optional[str] = None) -> Optional[str]:
    """Enqueue caption_images_task (if images) or ingest_map_reduce_task directly.

    Shared by ingest_file_task auto-proceed and the approve-extraction API.
    Returns the enqueued job_id, or None if enqueue failed.
    """
    if not has_images:
        return await _chain_to_mrp(source_id, attempt_id_str=attempt_id_str)

    pool = await get_arq_pool()
    args = [source_id]
    if attempt_id_str:
        args.append(attempt_id_str)
    job = await pool.enqueue_job("caption_images_task", *args)
    return job.job_id if job else None


from app.services.source_status import (  # noqa: E402  (re-exported for callers/tests)
    compute_source_dual_status,
    reset_branches,
    set_branch_state,
    start_wiki_attempt,
    update_source_dual_status,
    wiki_attempt_of,
)


async def finalize_verbatim_source(session, source, tracker) -> dict:
    """Verbatim path run synchronously (e.g. dept-change re-ingest via MRP task).

    Verbatim sources have no wiki branch, so indexing raw chunks (branch A) is the
    whole pipeline. Burns no LLM tokens, so even long legal documents go straight
    to ready without the awaiting_approval gate.
    """
    from app.services.verbatim_service import index_source_chunks

    await tracker.update(60, "Indexing verbatim document (no wiki)...")
    source.wiki_status = "skipped"
    source.wiki_progress = 100
    source.wiki_progress_message = "Skipped (verbatim source)"
    await set_branch_state(
        source.id, "chunk", status="processing", progress=60,
        message="Indexing verbatim chunks...", session=session,
    )

    n_chunks = await index_source_chunks(session, source)
    source.auto_recover_count = 0
    await set_branch_state(
        source.id, "chunk", status="ready", progress=100,
        message=(
            f"Verbatim: indexed {n_chunks} chunks, no wiki" if n_chunks
            else "Verbatim: stored, no embedding model (keyword search only)"
        ),
        session=session,
    )
    logger.info(f"Source {source.id} finalized as verbatim ({n_chunks} chunks indexed)")
    return {"status": "ready", "verbatim_chunks": n_chunks}


async def commit_and_enqueue_chunk_branch(session, source, attempt_id_str: Optional[str] = None) -> Optional[str]:
    """Start branch A: new chunk_attempt_id, status queued, commit, then enqueue.

    Committing BEFORE enqueueing guarantees the task sees full_text and the new
    chunk_attempt_id, and that this session never writes stale chunk_* fields
    after the task has already finished.
    """
    source.chunk_attempt_id = uuid.uuid4()
    source.chunk_status = "queued"
    source.chunk_progress = 5
    source.chunk_progress_message = "Queued: chunk & embed raw text"
    source.chunk_error_message = None
    await update_source_dual_status(session, source)
    await session.commit()
    pool = await get_arq_pool()
    job = await pool.enqueue_job(
        "ingest_source_chunks_task",
        str(source.id),
        attempt_id_str or (str(source.attempt_id) if source.attempt_id else None),
        str(source.chunk_attempt_id),
    )
    if job:
        logger.info(f"Branch A enqueued for source {source.id}: job={job.job_id}")
    return job.job_id if job else None


async def ingest_source_chunks_task(
    ctx: dict,
    source_id: str,
    attempt_id_str: Optional[str] = None,
    chunk_attempt_id_str: Optional[str] = None,
):
    """arq task, branch A: chunk & embed full_text into source_chunk_embeddings_<dim>.

    Runs concurrently with branch B (MRP / legal). Writes only chunk_* fields and
    recomputes the aggregate status under a row lock.
    """
    from app.ai.tracing import flush_langfuse, trace_context
    from app.database import async_session_factory
    from app.database.models import Source
    from app.models.task_failure import record_stage_timing, record_task_failure
    from app.services.verbatim_service import index_source_chunks

    sid = uuid.UUID(source_id)
    async with trace_context(
        "ingest_source_chunks_task",
        trace_id=f"src_chunk_{source_id}",
        tags=["dual_pipeline", "chunking"],
        metadata={"source_id": source_id},
    ):
        try:
            async with async_session_factory() as session:
                source = await session.get(Source, sid)
                if not source:
                    logger.warning(f"ingest_source_chunks_task: source {source_id} not found")
                    return {"status": "not_found"}
                if not await check_task_attempt_validity(session, sid, attempt_id_str):
                    logger.warning(f"ingest_source_chunks_task: source {source_id} attempt {attempt_id_str} is stale, skipping.")
                    return {"status": "stale"}
                if chunk_attempt_id_str and str(source.chunk_attempt_id or "") != chunk_attempt_id_str:
                    logger.warning(f"ingest_source_chunks_task: source {source_id} chunk attempt {chunk_attempt_id_str} superseded, skipping.")
                    return {"status": "stale"}
                if not source.full_text:
                    await set_branch_state(
                        sid, "chunk", status="error", progress=0,
                        message="No extracted text to chunk", error="No full_text",
                        session=session,
                    )
                    return {"status": "no_text"}

                await set_branch_state(
                    sid, "chunk", status="embedding", progress=20,
                    message="Building chunks with heading hierarchy & embedding...",
                    session=session,
                )

                t0 = time.perf_counter()
                n_chunks = await index_source_chunks(session, source)
                await record_stage_timing(
                    session, sid, "source_chunks",
                    int((time.perf_counter() - t0) * 1000), {"chunks": n_chunks},
                )

                agg = await set_branch_state(
                    sid, "chunk", status="ready", progress=100,
                    message=(
                        f"Indexed {n_chunks} raw chunks" if n_chunks
                        else "No embedding model: keyword search only"
                    ),
                    session=session,
                )
                logger.info(f"ingest_source_chunks_task: source {source_id} indexed {n_chunks} chunks (aggregate={agg})")
                return {"status": "ready", "chunks": n_chunks}
        except BaseException as e:
            logger.error(f"ingest_source_chunks_task failed for {source_id}: {e}")
            err_msg = (str(e).strip() or type(e).__name__)[:500]

            async def _mark_chunk_error(exc: BaseException = e) -> None:
                # `e` is unbound once the except block exits; shield() may outlive it.
                await set_branch_state(
                    sid, "chunk", status="error", progress=0,
                    message=f"Chunking error: {err_msg[:200]}", error=err_msg,
                )
                async with async_session_factory() as err_session:
                    await record_task_failure(
                        session=err_session,
                        task_name="ingest_source_chunks_task",
                        error=exc,
                        source_id=sid,
                        attempt_id=attempt_id_str,
                    )

            try:
                await asyncio.shield(_mark_chunk_error())
            except Exception:
                pass
            raise
        finally:
            flush_langfuse()


async def backfill_source_chunks_task(ctx: dict, limit: int = 500) -> dict:
    """arq task: start branch A for sources that have text but no raw chunks.

    Covers sources ingested before the dual pipeline (migration 044 leaves them
    with chunk_status='pending') and sources whose chunk branch failed. A source
    whose wiki is ready stays 'ready' while its chunks are being indexed.
    """
    from app.database import async_session_factory
    from app.database.models import Source

    async with async_session_factory() as session:
        ids = (
            await session.execute(
                select(Source.id)
                .where(
                    Source.chunk_status.in_(("pending", "error")),
                    Source.status.in_(("ready", "partial")),
                    Source.full_text.is_not(None),
                )
                .order_by(Source.created_at)
                .limit(limit)
            )
        ).scalars().all()

    enqueued = 0
    for sid in ids:
        async with async_session_factory() as session:
            source = await session.get(Source, sid)
            if not source or not (source.full_text or "").strip():
                continue
            try:
                await commit_and_enqueue_chunk_branch(session, source)
                enqueued += 1
            except Exception as e:
                logger.warning(f"backfill_source_chunks_task: source {sid} failed to enqueue: {e}")
    logger.info(f"backfill_source_chunks_task: enqueued branch A for {enqueued}/{len(ids)} sources")
    return {"candidates": len(ids), "enqueued": enqueued}


async def mark_wiki_error(source_id: uuid.UUID, error_msg: str) -> None:
    """Branch B failed: record it without discarding a healthy branch A."""
    await set_branch_state(
        source_id, "wiki", status="error", progress=0,
        message=f"Wiki error: {error_msg[:200]}", error=error_msg,
    )


async def dispatch_dual_pipeline(
    session,
    source,
    tracker,
    token_count: int,
    n_images: int = 0,
    attempt_id_str: Optional[str] = None,
) -> dict:
    """After extraction: start branch A (raw chunks) and branch B (wiki) in parallel.

    Branch A never waits for branch B's approval gate, so raw chunks become
    searchable as soon as they are embedded.
    """
    from app.services.legal_service import finalize_legal_source, is_legal_source

    source_id = str(source.id)
    attempt = attempt_id_str or (str(source.attempt_id) if source.attempt_id else None)

    # Branch B state first, so the aggregate computed when A is queued is right.
    if source.preserve_verbatim:
        source.wiki_status = "skipped"
        source.wiki_progress = 100
        source.wiki_progress_message = "Skipped (verbatim source)"
    else:
        source.wiki_status = "queued"
        source.wiki_progress = 50
        source.wiki_progress_message = "Waiting to compile wiki..."
        # New branch-B run; committed together with branch A's state below.
        start_wiki_attempt(source)
    wiki_attempt = wiki_attempt_of(source)

    # Branch A: commit, then enqueue.
    await commit_and_enqueue_chunk_branch(session, source, attempt)

    # Document metadata (số hiệu, hiệu lực, lĩnh vực...) for the legal wiki UI.
    # Legal sources that compile get it inside finalize_legal_source, where the
    # article count and overview slug are known.
    is_legal = await is_legal_source(session, source)
    if source.preserve_verbatim or not is_legal:
        try:
            from app.services.doc_metadata_service import store_document_metadata
            await store_document_metadata(session, source)
            await session.commit()
        except Exception as e:
            logger.warning(f"Document metadata extraction failed for {source_id}: {e}")

    if source.preserve_verbatim:
        logger.info(f"Source {source_id} is verbatim: branch B skipped")
        return {"status": source.status, "branch_a": "queued", "branch_b": "skipped"}

    # Branch B: legal documents compile into Điều-level pages without MRP.
    if is_legal:
        await set_branch_state(
            source.id, "wiki", status="processing", progress=50,
            message="Parsing legal document articles...", session=session,
        )
        try:
            return await finalize_legal_source(session, source, tracker)
        except BaseException as e:
            logger.error(f"Legal compilation failed for {source_id}: {e}")
            await asyncio.shield(mark_wiki_error(source.id, (str(e) or type(e).__name__)[:500]))
            raise

    # Branch B: gate large documents behind human approval (A keeps running).
    threshold = settings.auto_approve_extraction_threshold_tokens
    if token_count > threshold:
        agg = await set_branch_state(
            source.id, "wiki", status="awaiting_approval", progress=55,
            message=f"Awaiting approval for wiki compilation: {token_count:,} tokens > {threshold:,} threshold",
            session=session,
        )
        logger.info(f"Source {source_id} branch B gated at awaiting_approval ({token_count} tokens); branch A continues")
        return {"status": agg, "token_count": token_count, "images": n_images}

    # Commit branch B's state BEFORE enqueueing, so a fast-failing MRP task's
    # wiki error is never overwritten by this 'processing' write.
    agg = await set_branch_state(
        source.id, "wiki", status="processing", progress=55,
        message=f"Captioning {n_images} images before extraction..." if n_images else "Extraction queued...",
        session=session,
    )
    job_id = await enqueue_post_extraction_pipeline(source_id, has_images=bool(n_images), attempt_id_str=wiki_attempt)
    if job_id:
        source.job_id = job_id
        await session.commit()
    logger.info(f"Source {source_id} dual pipeline running: A=chunks, B={'caption→MRP' if n_images else 'MRP'}")
    return {"status": agg, "token_count": token_count, "images": n_images}


async def ingest_file_task(ctx: dict, source_id: str, attempt_id_str: Optional[str] = None):
    """
    arq task: full file ingestion → wiki compilation.
    Steps: download from MinIO → extract text → outline → enqueue MRP + caption_images_task.
    Image captioning is offloaded to caption_images_task so this job is not blocked by image count.
    File must already be uploaded to MinIO before this task is enqueued.
    """
    from app.ai.tracing import flush_langfuse, trace_context
    from app.database import async_session_factory
    from app.database.models import Source, SourceImage
    from app.services.image_service import extract_images
    from app.services.kb_service import (
        _extract_text_from_file,
        _inline_image_markers,
    )
    from app.services.source_outline import assemble_full_text, build_outline
    from app.services.storage_service import storage_service
    from app.utils.tokens import count_tokens

    sid = uuid.UUID(source_id)
    tracker = ProgressTracker(sid)

    async with trace_context("ingest_file_task", trace_id=f"src_{source_id}", tags=["ingestion", "file"], metadata={"source_id": source_id}):
        try:
            async with async_session_factory() as session:
                source = await session.get(Source, sid)
                if not source:
                    logger.warning(f"Source {source_id} not found, it may have been deleted.")
                    return
                if not await check_task_attempt_validity(session, sid, attempt_id_str):
                    logger.warning(f"ingest_file_task: source {source_id} attempt {attempt_id_str} is stale, skipping.")
                    return
                if not source.minio_key:
                    raise ValueError(f"Source {source_id} has no file in storage")

                file_name = source.file_name or source.minio_key.split("/")[-1]

                try:
                    reset_branches(source, wiki_skipped=bool(source.preserve_verbatim))
                    source.status = "processing"
                    source.progress = 0
                    source.progress_message = "Starting processing..."
                    await session.commit()

                    from app.models.task_failure import record_stage_timing

                    # --- Step 1: Download from MinIO (10%) ---
                    await tracker.update(5, "Loading file...")
                    t_dl = time.perf_counter()
                    file_data = storage_service.download_file(source.minio_key)
                    dl_ms = int((time.perf_counter() - t_dl) * 1000)
                    await record_stage_timing(session, sid, "download", dl_ms, {"size_bytes": len(file_data) if file_data else 0})
                    await tracker.update(10, "File loaded")

                    # --- Step 2: Extract text per page (25%) ---
                    await tracker.update(15, "Extracting text (per page)...")
                    # Resolve vision provider for OCR fallback on image-only PDFs
                    vision_provider = None
                    try:
                        from app.ai.registry import ProviderRegistry
                        registry = ProviderRegistry(session)
                        vision_provider = await registry.get_vision()
                    except Exception:
                        pass  # OCR fallback unavailable — continue without it
                    t_parse = time.perf_counter()
                    pages_data = await _extract_text_from_file(file_data, file_name, vision_provider=vision_provider, tracker=tracker)
                    parse_ms = int((time.perf_counter() - t_parse) * 1000)
                    await record_stage_timing(session, sid, "parse", parse_ms, {"pages_count": len(pages_data) if pages_data else 0})

                    if not pages_data or not any((p.get("content") or "").strip() for p in pages_data):
                        source.status = "error"
                        source.error_message = "Unable to extract text content"
                        source.progress = 0
                        await session.commit()
                        return {"status": "error", "message": "No text content"}

                    await tracker.update(25, "Text extraction complete")

                    # --- Step 3: Extract images (40%) ---
                    # Captioning is offloaded to caption_images_task (enqueued below) so
                    # this job is not blocked by the number of images in the document.
                    await tracker.update(30, "Extracting images...")
                    t_img = time.perf_counter()
                    images = extract_images(file_data, file_name, source_id)

                    # Persist images so wiki content_md can reference them by uuid.
                    for img in images:
                        row = SourceImage(
                            source_id=uuid.UUID(source_id),
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

                    # Inline image markers into per-page text so the compiler sees them.
                    _inline_image_markers(pages_data, images)
                    img_ms = int((time.perf_counter() - t_img) * 1000)
                    await record_stage_timing(session, sid, "extract_images", img_ms, {"images_count": len(images)})
                    await tracker.update(40, f"Analyzed {len(images)} images")

                    # --- Step 4: Build outline + assemble full_text (50%) ---
                    await tracker.update(45, "Building document outline...")
                    t_out = time.perf_counter()
                    source.outline_json = build_outline(pages_data)
                    full_text, page_offsets = assemble_full_text(pages_data)
                    source.full_text = full_text
                    source.page_offsets = page_offsets

                    # --- Step 5: Token count (drives auto-approve vs gate) ---
                    token_count = count_tokens(full_text)
                    source.extracted_token_count = token_count
                    await session.commit()
                    out_ms = int((time.perf_counter() - t_out) * 1000)
                    await record_stage_timing(session, sid, "outline", out_ms, {"token_count": token_count})
                    await tracker.update(50, f"Outline: {len(source.outline_json or [])} top-level sections, ~{token_count} tokens")

                    return await dispatch_dual_pipeline(
                        session, source, tracker, token_count,
                        n_images=len(images), attempt_id_str=attempt_id_str,
                    )

                except BaseException as e:
                    logger.error(f"Pre-processing failed for {source_id}: {e}")
                    err_type = type(e).__name__
                    err_msg = str(e).strip() or err_type
                    error_msg = f"{err_type}: {err_msg}" if err_msg != err_type else err_type
                    progress_msg = f"Error: {error_msg[:200]}"

                    async def _mark_error_file(exc: BaseException = e) -> None:
                        # `e` is unbound once the except block exits; shield() may outlive it.
                        from app.database import async_session_factory as _sf
                        from app.database.models import Source as _Source
                        from app.models.task_failure import record_task_failure
                        async with _sf() as err_session:
                            src = await err_session.get(_Source, sid)
                            if src and src.chunk_status not in (None, "pending"):
                                await mark_wiki_error(sid, error_msg)
                            elif src:
                                src.status = "error"
                                src.error_message = error_msg
                                src.progress = 0
                                src.progress_message = progress_msg
                                await err_session.commit()
                            await record_task_failure(
                                session=err_session,
                                task_name="ingest_file_task",
                                error=exc,
                                source_id=sid,
                                attempt_id=attempt_id_str,
                                payload={"file_name": file_name} if "file_name" in locals() else None,
                            )

                    try:
                        await asyncio.shield(_mark_error_file())
                    except Exception:
                        pass
                    raise
        finally:
            flush_langfuse()


async def ingest_url_task(ctx: dict, source_id: str, attempt_id_str: Optional[str] = None):
    """arq task: URL ingestion → wiki compilation."""
    from app.ai.tracing import flush_langfuse, trace_context
    from app.database import async_session_factory
    from app.database.models import Source
    from app.services.kb_service import _extract_text_from_url
    from app.services.source_outline import assemble_full_text, build_outline
    from app.utils.tokens import count_tokens

    sid = uuid.UUID(source_id)
    tracker = ProgressTracker(sid)

    async with trace_context("ingest_url_task", trace_id=f"src_{source_id}", tags=["ingestion", "url"], metadata={"source_id": source_id}):
        try:
            async with async_session_factory() as session:
                source = await session.get(Source, sid)
                if not source:
                    logger.warning(f"Source {source_id} not found, it may have been deleted.")
                    return
                if not await check_task_attempt_validity(session, sid, attempt_id_str):
                    logger.warning(f"ingest_url_task: source {source_id} attempt {attempt_id_str} is stale, skipping.")
                    return

                try:
                    reset_branches(source, wiki_skipped=bool(source.preserve_verbatim))
                    source.status = "processing"
                    source.progress = 0
                    await session.commit()

                    await tracker.update(15, "Fetching content from URL...")
                    if not source.url:
                        source.status = "error"
                        source.error_message = "Source has no URL"
                        await session.commit()
                        return {"status": "error"}
                    from app.models.task_failure import record_stage_timing
                    t_url = time.perf_counter()
                    pages_data = await _extract_text_from_url(source.url)
                    url_ms = int((time.perf_counter() - t_url) * 1000)
                    await record_stage_timing(session, sid, "fetch_url", url_ms, {"pages_count": len(pages_data) if pages_data else 0})

                    if not pages_data or not any((p.get("content") or "").strip() for p in pages_data):
                        source.status = "error"
                        source.error_message = "Unable to fetch content from URL"
                        await session.commit()
                        return {"status": "error"}

                    await tracker.update(40, "Building outline...")
                    t_out = time.perf_counter()
                    source.outline_json = build_outline(pages_data)
                    full_text, page_offsets = assemble_full_text(pages_data)
                    source.full_text = full_text
                    source.page_offsets = page_offsets
                    token_count = count_tokens(full_text)
                    source.extracted_token_count = token_count
                    await session.commit()
                    out_ms = int((time.perf_counter() - t_out) * 1000)
                    await record_stage_timing(session, sid, "outline", out_ms, {"token_count": token_count})

                    return await dispatch_dual_pipeline(
                        session, source, tracker, token_count,
                        n_images=0, attempt_id_str=attempt_id_str,
                    )

                except BaseException as e:
                    logger.error(f"URL ingestion failed for {source_id}: {e}")
                    error_msg = str(e)[:500]

                    async def _mark_error_url(exc: BaseException = e) -> None:
                        # `e` is unbound once the except block exits; shield() may outlive it.
                        from app.database import async_session_factory as _sf
                        from app.database.models import Source as _Source
                        from app.models.task_failure import record_task_failure
                        async with _sf() as err_session:
                            src = await err_session.get(_Source, sid)
                            if src and src.chunk_status not in (None, "pending"):
                                await mark_wiki_error(sid, error_msg)
                            elif src:
                                src.status = "error"
                                src.error_message = error_msg
                                src.progress = 0
                                await err_session.commit()
                            await record_task_failure(
                                session=err_session,
                                task_name="ingest_url_task",
                                error=exc,
                                source_id=sid,
                                attempt_id=attempt_id_str,
                            )

                    try:
                        await asyncio.shield(_mark_error_url())
                    except Exception:
                        pass
                    raise
        finally:
            flush_langfuse()


# ---------------------------------------------------------------------------
# Worker configuration
# ---------------------------------------------------------------------------


async def ingest_skill_task(ctx: dict, skill_id: str, version_id: str, file_path: str, file_name: str):
    """
    arq task: unzip skill package from disk buffer, store in MinIO, and extract metadata.
    """
    import os

    from app.database import async_session_factory
    from app.database.models import Skill, SkillVersion
    from app.services.storage_service import storage_service

    sid = uuid.UUID(skill_id)
    vid = uuid.UUID(version_id)
    skill_name = file_name.rsplit(".", 1)[0]
    
    logger.info(f"Starting ingestion for skill: {skill_name} ({skill_id})")

    async with async_session_factory() as session:
        skill = await session.get(Skill, sid)
        version = await session.get(SkillVersion, vid)
        
        if not skill or not version:
            logger.error(f"Skill {skill_id} or Version {version_id} not found in DB")
            return

        try:
            skill.status = "processing"
            await session.commit()

            if not os.path.exists(file_path):
                logger.error(f"Disk buffer file not found: {file_path}")
                skill.status = "error"
                await session.commit()
                return

            import asyncio

            from app.services.kb_service import _guess_content_type

            # 1. Unzip with streaming, security checks, and concurrent uploads
            MAX_UNCOMPRESSED_SIZE = 10 * 1024 * 1024  # 10 MB
            MAX_FILE_COUNT = 100

            total_size = 0
            file_count = 0

            upload_tasks = []
            semaphore = asyncio.Semaphore(10)

            async def _upload_worker(zf_path, member_name, obj_name, file_size):
                async with semaphore:
                    # Open a fresh ZipFile instance in the thread to avoid GIL lock contention
                    with zipfile.ZipFile(zf_path) as local_zf:
                        with local_zf.open(member_name) as f_stream:
                            await storage_service.upload_stream_async(
                                obj_name, f_stream, file_size, _guess_content_type(member_name)
                            )

            with zipfile.ZipFile(file_path) as zf:
                for member in zf.infolist():
                    if member.is_dir():
                        continue
                    
                    filename = member.filename
                    
                    # [Security] Zip Slip check
                    if filename.startswith("/") or filename.startswith("\\") or "../" in filename or "..\\" in filename:
                        raise ValueError(f"Security risk: Zip Slip detected in {filename}")
                        
                    # [Security] File count check
                    file_count += 1
                    if file_count > MAX_FILE_COUNT:
                        raise ValueError(f"Too many files (exceeds {MAX_FILE_COUNT})")
                        
                    # [Security] Zip Bomb check
                    total_size += member.file_size
                    if total_size > MAX_UNCOMPRESSED_SIZE:
                        raise ValueError("Uncompressed size too large (exceeds 10MB)")

                    object_name = f"skills/{skill_id}/versions/{version.version_number}/content/{filename}"
                    target_readme = f"{skill_name}/SKILL.md".lower()

                    if filename.lower() == target_readme or filename.lower().endswith("/skill.md"):
                        with zf.open(member) as f:
                            content = f.read()
                        
                        storage_service.upload_file(
                            object_name=object_name,
                            data=content,
                            content_type=_guess_content_type(filename)
                        )
                    else:
                        upload_tasks.append(
                            _upload_worker(file_path, filename, object_name, member.file_size)
                        )

            if upload_tasks:
                await asyncio.gather(*upload_tasks)

            # 3. Calculate content-based hash (consistent with contribution workflow)
            storage_path = f"skills/{skill_id}/versions/{version.version_number}/content/"
            file_hash = storage_service.calculate_prefix_hash(storage_path)

            # 4. Update DB with extracted metadata

            skill.version_hash = file_hash
            skill.current_version = version.version_number
            skill.storage_path = storage_path
            skill.status = "active"
            
            version.version_hash = file_hash
            version.storage_path = storage_path
            
            await session.commit()
            logger.success(f"Skill {skill_name} version {version.version_number} processed successfully")

        except Exception as e:
            logger.exception(f"Failed to process skill {skill_name}: {e}")
            skill.status = "error"
            await session.commit()
        finally:
            # Clean up disk buffer
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.debug(f"Cleaned up disk buffer: {file_path}")
                except Exception as e:
                    logger.warning(f"Failed to delete temp file {file_path}: {e}")


async def delete_skill_task(ctx: dict, skill_id: str):
    """
    arq task: delete skill files from MinIO and remove from DB.
    """
    from app.database import async_session_factory
    from app.database.models import Skill
    from app.services.storage_service import storage_service

    sid = uuid.UUID(skill_id)
    
    logger.info(f"Starting deletion task for skill: {skill_id}")

    async with async_session_factory() as session:
        skill = await session.get(Skill, sid)
        if not skill:
            logger.warning(f"Skill {skill_id} already deleted or not found")
            return

        try:
            from sqlalchemy.orm import selectinload
            # 1. Fetch skill with contributions to get their storage paths
            stmt = select(Skill).where(Skill.id == sid).options(selectinload(Skill.contributions))
            res = await session.execute(stmt)
            skill = res.scalars().first()
            if not skill:
                return

            # 2. Delete files from MinIO for the skill itself
            prefix = f"skills/{skill_id}/"
            storage_service.delete_prefix(prefix)
            
            # 3. Delete files for all associated contributions
            for contrib in skill.contributions:
                if contrib.storage_path:
                    logger.info(f"Deleting storage for contribution {contrib.id}: {contrib.storage_path}")
                    storage_service.delete_prefix(contrib.storage_path)

            # 4. Delete skill from DB (cascades to SkillVersion and SkillContribution DB rows)
            await session.delete(skill)
            await session.commit()
            
            logger.success(f"Skill {skill_id} and all related assets (versions, contributions) deleted successfully")

        except Exception as e:
            logger.exception(f"Failed to delete skill {skill_id}: {e}")
            raise


async def cleanup_temp_uploads_cron(ctx: dict):
    """
    Cronjob: Quét và dọn các file rác trong temp_uploads do server crash để lại (cũ hơn 1 giờ).
    """
    import os
    import time
    
    temp_dir = "temp_uploads"
    if not os.path.exists(temp_dir):
        return
        
    cutoff_time = time.time() - 3600  # 1 hour ago
    
    for filename in os.listdir(temp_dir):
        file_path = os.path.join(temp_dir, filename)
        if os.path.isfile(file_path):
            if os.path.getmtime(file_path) < cutoff_time:
                try:
                    os.remove(file_path)
                    logger.info(f"Cronjob: Cleaned up orphaned temp file {filename}")
                except Exception as e:
                    logger.debug(f"Cronjob: Failed to clean {filename}: {e}")


# ---------------------------------------------------------------------------
# Embedding migration: re-embed every wiki page with a new model
# ---------------------------------------------------------------------------

async def reembed_all_pages_task(ctx: dict, job_id: str) -> None:
    """
    Re-embed every wiki page using the model spec referenced by the job.

    On success, atomically flips `app_config.active_embedding_model_spec_id`
    to the new spec — search keeps using the OLD model until that flip lands,
    so there is no zero-result window during the migration.
    """
    from datetime import datetime, timezone

    from sqlalchemy import select

    from app.ai.embedding_catalog import get_spec
    from app.ai.registry import ProviderRegistry
    from app.database import async_session_factory
    from app.database.models import EmbeddingJob, Source, WikiPage
    from app.services.config_service import (
        ACTIVE_EMBEDDING_MODEL_KEY,
        ConfigService,
    )
    from app.services.embedding_storage import (
        cleanup_stale_embeddings,
        cleanup_stale_source_chunk_embeddings,
        cleanup_stale_wiki_chunk_embeddings,
    )
    from app.services.wiki_chunk_service import index_wiki_page_chunks

    job_uuid = uuid.UUID(job_id)
    BATCH = 50

    async with async_session_factory() as session:
        job = await session.get(EmbeddingJob, job_uuid)
        if job is None:
            logger.error(f"reembed: job {job_id} not found")
            return
        if job.status not in ("pending", "running"):
            logger.info(f"reembed: job {job_id} status={job.status}, skipping")
            return

        try:
            spec = get_spec(job.model_spec_id)
        except Exception as e:
            job.status = "failed"
            job.error_message = f"Unknown model spec: {e}"
            job.finished_at = datetime.now(timezone.utc)
            await session.commit()
            return

        # Provision a provider bound to the NEW spec (not the active one).
        registry = ProviderRegistry(session)
        try:
            provider = await registry.get_embedding(
                task="document", spec_id=spec.id
            )
        except Exception as e:
            job.status = "failed"
            job.error_message = f"Provider init failed: {e}"
            job.finished_at = datetime.now(timezone.utc)
            await session.commit()
            return

        # Count work and mark running.
        total = (
            await session.execute(
                select(WikiPage.id).where(
                    WikiPage.slug.notin_(["_index", "_log"])
                )
            )
        ).scalars().all()
        job.total_pages = len(total)
        job.done_pages = 0
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        await session.commit()

    logger.info(
        f"reembed: starting job {job_id} model={spec.id} dim={spec.dimension} "
        f"total={len(total)}"
    )

    # Process batches in independent sessions so progress is visible to UI poll.
    for offset in range(0, len(total), BATCH):
        batch_ids = total[offset : offset + BATCH]
        async with async_session_factory() as session:
            # Re-check cancellation flag.
            job = await session.get(EmbeddingJob, job_uuid)
            if job is None or job.status == "cancelled":
                logger.info(f"reembed: job {job_id} cancelled at offset={offset}")
                return

            pages = (
                await session.execute(
                    select(WikiPage).where(WikiPage.id.in_(batch_ids))
                )
            ).scalars().all()
            try:
                for page in pages:
                    await index_wiki_page_chunks(session, page, spec_id=spec.id)
            except Exception as e:
                job.status = "failed"
                job.error_message = f"Embedding API failed: {e}"
                job.finished_at = datetime.now(timezone.utc)
                await session.commit()
                logger.exception(f"reembed: job {job_id} failed at offset={offset}")
                return

            job.done_pages = min(offset + len(pages), job.total_pages)
            await session.commit()

    # Re-embed raw source chunks (branch A: verbatim and regular sources) against
    # the NEW spec too, so the unified search pool stays consistent after the flip.
    # Each source re-indexes against spec.id explicitly (active spec is still the
    # OLD one until the flip below).
    async with async_session_factory() as session:
        from sqlalchemy import or_

        from app.services.verbatim_service import index_source_chunks

        chunk_sources = (
            await session.execute(
                select(Source).where(
                    or_(
                        Source.chunk_status == "ready",
                        (Source.preserve_verbatim.is_(True)) & (Source.status == "ready"),
                    )
                )
            )
        ).scalars().all()
        for cs in chunk_sources:
            try:
                await index_source_chunks(session, cs, spec_id=spec.id)
            except Exception as e:
                logger.warning(f"reembed: source {cs.id} chunk re-index failed: {e}")
        if chunk_sources:
            logger.info(f"reembed: re-indexed raw chunks of {len(chunk_sources)} sources")

    # Atomic flip + cleanup of old model's vectors.
    async with async_session_factory() as session:
        job = await session.get(EmbeddingJob, job_uuid)
        if job is None or job.status == "cancelled":
            return
        svc = ConfigService(session)
        await svc.set(ACTIVE_EMBEDDING_MODEL_KEY, spec.id)
        deleted = await cleanup_stale_embeddings(session, keep_spec_id=spec.id)
        deleted += await cleanup_stale_source_chunk_embeddings(session, keep_spec_id=spec.id)
        deleted += await cleanup_stale_wiki_chunk_embeddings(session, keep_spec_id=spec.id)
        job.status = "completed"
        job.finished_at = datetime.now(timezone.utc)
        await session.commit()
        logger.info(
            f"reembed: job {job_id} complete — flipped to {spec.id}, "
            f"cleaned up {deleted} stale embedding rows"
        )


# ---------------------------------------------------------------------------
# MRP arq tasks
# ---------------------------------------------------------------------------

async def ingest_map_reduce_task(ctx: dict, source_id: str, attempt_id_str: Optional[str] = None):
    """
    arq task: Phase 0-2 of MRP pipeline (Triage + MAP + REDUCE).

    Reads source.full_text and outline_json (set by ingest_file_task / ingest_url_task),
    runs parallel chunk extraction, entity deduplication, KB reconciliation, and
    produces a Compilation Plan saved to source_compilation_plans.

    If mrp_auto_approve_plan=True → immediately enqueues ingest_refine_task.
    Otherwise → sets source.status='plan_ready' and waits for human approval via API.
    """
    from app.ai.mrp.pipeline import run_mrp_pipeline
    from app.ai.registry import ProviderRegistry
    from app.ai.tracing import flush_langfuse, trace_context
    from app.database import async_session_factory
    from app.database.models import KnowledgeType, Source

    sid = uuid.UUID(source_id)
    tracker = ProgressTracker(sid)

    async with trace_context("ingest_map_reduce_task", trace_id=f"src_{source_id}", tags=["mrp", "map_reduce"], metadata={"source_id": source_id}):
        try:
            async with async_session_factory() as session:
                source = await session.get(Source, sid)
                if not source:
                    logger.warning(f"Source {source_id} not found, it may have been deleted.")
                    return
                if not await check_task_attempt_validity(session, sid, attempt_id_str, branch="wiki"):
                    logger.warning(f"ingest_map_reduce_task: source {source_id} attempt {attempt_id_str} is stale, skipping.")
                    return
                if not source.full_text:
                    raise ValueError(f"Source {source_id} has no full_text — run pre-processing first")

                # Legal documents parse directly into Điều-level WikiPages without MRP
                from app.services.legal_service import is_legal_source, finalize_legal_source
                if await is_legal_source(session, source):
                    try:
                        return await finalize_legal_source(session, source, tracker)
                    except BaseException as e:
                        logger.error(f"Legal indexing failed for {source_id}: {e}")
                        await asyncio.shield(mark_wiki_error(sid, (str(e) or type(e).__name__)[:500]))
                        raise

                # Verbatim sources never run MRP, regardless of which task enqueued them
                # (e.g. a dept-change re-ingest). Index raw chunks and finish.
                if source.preserve_verbatim:
                    try:
                        return await finalize_verbatim_source(session, source, tracker)
                    except BaseException as e:
                        logger.error(f"Verbatim indexing failed for {source_id}: {e}")
                        await asyncio.shield(set_branch_state(
                            sid, "chunk", status="error", progress=0,
                            message="Verbatim indexing failed", error=(str(e) or type(e).__name__)[:500],
                        ))
                        raise

                try:
                    await set_branch_state(
                        sid, "wiki", status="mapping", progress=56,
                        message="Extracting knowledge from document...", session=session,
                    )

                    registry = ProviderRegistry(session)

                    kt_slug = kt_name = kt_desc = None
                    if source.knowledge_type_id:
                        kt = await session.get(KnowledgeType, source.knowledge_type_id)
                        if kt:
                            kt_slug, kt_name, kt_desc = kt.slug, kt.name, kt.description

                    from app.models.task_failure import record_stage_timing
                    t_mrp = time.perf_counter()
                    result = await run_mrp_pipeline(
                        session=session,
                        source=source,
                        attempt_id_str=attempt_id_str,
                        full_text=source.full_text,
                        tracker=tracker,
                        registry=registry,
                        kt_slug=kt_slug,
                        kt_name=kt_name,
                        kt_desc=kt_desc,
                    )
                    mrp_ms = int((time.perf_counter() - t_mrp) * 1000)
                    await record_stage_timing(
                        session, sid, "map_reduce", mrp_ms,
                        {"status": result.get("status") if isinstance(result, dict) else None}
                    )

                    if result.get("status") == "plan_ready":
                        src = await session.get(Source, sid)
                        if src:
                            src.auto_recover_count = 0
                            await set_branch_state(
                                sid, "wiki", status="plan_ready", progress=80,
                                message="Compilation plan ready — awaiting review", session=session,
                            )
                        logger.info(f"Source {source_id} plan ready: {result.get('plan_id')}")
                    elif result.get("status") == "plan_auto_approved":
                        logger.info(f"Source {source_id} plan auto-approved, refine task enqueued")
                    else:
                        logger.info(f"Source {source_id} map-reduce result: {result}")

                    return result

                except BaseException as e:
                    logger.error(f"MAP-REDUCE failed for {source_id}: {e}")
                    error_msg = str(e)[:500]
                    progress_msg = f"Error: {str(e)[:200]}"

                    async def _mark_error_mr(exc: BaseException = e) -> None:
                        # `e` is unbound once the except block exits; shield() may outlive it.
                        from app.database import async_session_factory as _sf
                        from app.models.task_failure import record_task_failure
                        await mark_wiki_error(sid, error_msg)
                        async with _sf() as err_session:
                            await record_task_failure(
                                session=err_session,
                                task_name="ingest_map_reduce_task",
                                error=exc,
                                source_id=sid,
                                attempt_id=attempt_id_str,
                            )

                    try:
                        await asyncio.shield(_mark_error_mr())
                    except Exception:
                        pass
                    raise
        finally:
            flush_langfuse()


async def ingest_refine_task(ctx: dict, source_id: str, attempt_id_str: Optional[str] = None):
    """
    arq task: Phase 3-5 of MRP pipeline (REFINE + VERIFY + COMMIT).

    Enqueued by either:
    - Plan approval API endpoint (POST /sources/{id}/plan/approve)
    - Auto-approve from ingest_map_reduce_task when mrp_auto_approve_plan=True
    """
    from app.ai.mrp.pipeline import run_refine_pipeline
    from app.ai.registry import ProviderRegistry
    from app.ai.tracing import flush_langfuse, trace_context
    from app.database import async_session_factory
    from app.database.models import KnowledgeType, Source

    sid = uuid.UUID(source_id)
    tracker = ProgressTracker(sid)

    async with trace_context("ingest_refine_task", trace_id=f"src_{source_id}", tags=["mrp", "refine"], metadata={"source_id": source_id}):
        try:
            async with async_session_factory() as session:
                source = await session.get(Source, sid)
                if not source:
                    logger.warning(f"Source {source_id} not found, it may have been deleted.")
                    return
                if not await check_task_attempt_validity(session, sid, attempt_id_str, branch="wiki"):
                    logger.warning(f"ingest_refine_task: source {source_id} attempt {attempt_id_str} is stale, skipping.")
                    return
                if not source.full_text:
                    raise ValueError(f"Source {source_id} has no full_text")

                try:
                    await set_branch_state(
                        sid, "wiki", status="refining", progress=78,
                        message="Writing wiki pages...", session=session,
                    )

                    registry = ProviderRegistry(session)

                    kt_slug = kt_name = kt_desc = None
                    if source.knowledge_type_id:
                        kt = await session.get(KnowledgeType, source.knowledge_type_id)
                        if kt:
                            kt_slug, kt_name, kt_desc = kt.slug, kt.name, kt.description

                    from app.models.task_failure import record_stage_timing
                    t_refine = time.perf_counter()
                    result = await run_refine_pipeline(
                        session=session,
                        source=source,
                        full_text=source.full_text,
                        tracker=tracker,
                        registry=registry,
                        kt_slug=kt_slug,
                        kt_name=kt_name,
                        kt_desc=kt_desc,
                    )
                    refine_ms = int((time.perf_counter() - t_refine) * 1000)
                    await record_stage_timing(
                        session, sid, "refine", refine_ms,
                        {
                            "pages_created": result.get("pages_created", 0) if isinstance(result, dict) else 0,
                            "pages_updated": result.get("pages_updated", 0) if isinstance(result, dict) else 0,
                        }
                    )

                    logger.success(
                        f"Source {source_id} MRP complete: "
                        f"+{result.get('pages_created', 0)} created, "
                        f"~{result.get('pages_updated', 0)} updated"
                    )
                    return result

                except BaseException as e:
                    logger.error(f"REFINE failed for {source_id}: {e}")
                    error_msg = str(e)[:500]
                    progress_msg = f"Error: {str(e)[:200]}"

                    async def _mark_error_refine(exc: BaseException = e) -> None:
                        # `e` is unbound once the except block exits; shield() may outlive it.
                        from app.database import async_session_factory as _sf
                        from app.models.task_failure import record_task_failure
                        await mark_wiki_error(sid, error_msg)
                        async with _sf() as err_session:
                            await record_task_failure(
                                session=err_session,
                                task_name="ingest_refine_task",
                                error=exc,
                                source_id=sid,
                                attempt_id=attempt_id_str,
                            )

                    try:
                        await asyncio.shield(_mark_error_refine())
                    except Exception:
                        pass
                    raise
        finally:
            flush_langfuse()


async def regenerate_plan_task(ctx: dict, source_id: str, user_note: str):
    """
    arq task: re-run KB reconciliation + planning call with reviewer feedback.

    Toggles plan.status: pending_review/rejected → regenerating → pending_review.
    Frontend polls GET /sources/{id}/plan to observe completion.
    """
    from app.ai.mrp.reducer import reconcile_with_kb, run_planning_call
    from app.ai.registry import ProviderRegistry
    from app.database import async_session_factory
    from app.database.models import Source, SourceCompilationPlan

    sid = uuid.UUID(source_id)

    async with async_session_factory() as session:
        from sqlalchemy.orm import selectinload
        source = (await session.execute(
            select(Source)
            .options(selectinload(Source.knowledge_type))
            .where(Source.id == sid)
        )).scalar_one_or_none()
        if not source:
            logger.warning(f"regenerate_plan_task: source {source_id} not found")
            return

        plan = (await session.execute(
            select(SourceCompilationPlan).where(SourceCompilationPlan.source_id == sid)
        )).scalar_one_or_none()
        if not plan:
            logger.warning(f"regenerate_plan_task: no plan for source {source_id}")
            return

        plan_json = plan.plan_json or {}
        canonical_entities = plan_json.get("_entities", [])
        canonical_concepts = plan_json.get("_concepts", [])

        try:
            registry = ProviderRegistry(session)
            llm = await registry.get_llm()
            embedding_provider = None
            try:
                embedding_provider = await registry.get_embedding(task="document")
            except Exception:
                pass

            reconciliation: dict = {}
            if embedding_provider and (canonical_entities or canonical_concepts):
                try:
                    reconciliation = await reconcile_with_kb(
                        session, canonical_entities, canonical_concepts, embedding_provider, source, llm=llm,
                    )
                except Exception as exc:
                    logger.warning(f"regenerate_plan_task: KB reconcile failed: {exc}")

            kt_name = source.knowledge_type.name if source.knowledge_type else None
            kt_desc = source.knowledge_type.description if source.knowledge_type else None
            strategy = source.pipeline_strategy or "standard"

            new_plan_dict = await run_planning_call(
                llm=llm,
                source=source,
                strategy=strategy,
                canonical_entities=canonical_entities,
                canonical_concepts=canonical_concepts,
                reconciliation=reconciliation,
                kt_name=kt_name,
                kt_desc=kt_desc,
                user_note=user_note,
            )

            internal_keys = {
                k: plan_json[k] for k in ("_claims", "_entities", "_concepts") if k in plan_json
            }
            new_plan_dict.update(internal_keys)

            plan.plan_json = new_plan_dict
            plan.status = "pending_review"
            plan.reviewed_by = None
            plan.review_note = None
            plan.reviewed_at = None
            await session.commit()
            logger.success(f"regenerate_plan_task: plan refreshed for source {source_id}")
        except Exception as exc:
            logger.exception(f"regenerate_plan_task failed for {source_id}: {exc}")
            # Restore plan to pending_review so user isn't stuck on 'regenerating'
            plan2 = await session.get(SourceCompilationPlan, plan.id)
            if plan2 and plan2.status == "regenerating":
                plan2.status = "pending_review"
                plan2.review_note = f"Regeneration failed: {str(exc)[:200]}"
                await session.commit()


async def sweep_stuck_ai_review_cron(ctx: dict):
    """Periodic safety net: flip any draft stuck in ai_check_status='running'
    for longer than the worker job_timeout back to 'skipped'.

    A draft can get stuck if the worker process is SIGKILL/OOM-killed AFTER
    committing status='running' but BEFORE finishing the checks — the
    try/except in the runner only catches Python exceptions, not process
    death. Without this sweep the UI shows a perpetual "running" spinner.
    """
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import or_, select, update

    from app.database import async_session_factory
    from app.database.models import WikiPageDraft

    # Anything still "running" beyond 2x the job timeout (or 30 min, whichever
    # is larger) is almost certainly a dead worker. Use updated_at since the
    # runner doesn't bump ai_checked_at until it writes the final verdict.
    timeout_sec = max(int(settings.worker_job_timeout) * 2, 1800)
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=timeout_sec)

    async with async_session_factory() as session:
        stmt = (
            update(WikiPageDraft)
            .where(
                WikiPageDraft.ai_check_status == "running",
                or_(
                    WikiPageDraft.updated_at < cutoff,
                    WikiPageDraft.updated_at.is_(None),
                ),
            )
            .values(ai_check_status="skipped")
        )
        result = await session.execute(stmt)
        await session.commit()
        n = result.rowcount or 0
        if n:
            logger.warning(
                f"sweep_stuck_ai_review_cron: reset {n} draft(s) stuck in "
                f"'running' for >{timeout_sec}s"
            )


async def sweep_stuck_processing_cron(ctx: dict):
    """Periodic safety net: flip any Source stuck in status='processing' for
    longer than 2x the worker job_timeout back to 'error'.

    A source gets stuck when the worker process dies AFTER writing
    status='processing' but BEFORE finishing the pipeline — OOM, SIGKILL,
    container restart, hung LLM call. The in-worker try/except can't catch
    process death so the source row stays at 'processing' indefinitely with
    no recovery path (the retry endpoint only accepts 'error' / 'plan_ready').

    This sweep does NOT auto-enqueue a retry — it only marks the row 'error'
    so the user sees the Retry button. Auto-retrying here would loop forever
    if the failure is deterministic (bad provider key, malformed file).
    Source.auto_recover_count tracks consecutive sweeps; the retry API blocks
    once it crosses settings.max_auto_recover_attempts so even manual retries
    are gated against token-burning loops.

    Uses updated_at (bumped by ProgressTracker on every progress update) so
    legitimately slow MAP-phase LLM calls don't get swept while still
    producing progress.
    """
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import or_, select

    from app.database import async_session_factory
    from app.database.models import Source

    timeout_sec = max(int(settings.worker_job_timeout) * 2, 1800)
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=timeout_sec)

    async with async_session_factory() as session:
        rows = (await session.execute(
            select(Source).where(
                Source.status == "processing",
                or_(Source.updated_at < cutoff, Source.updated_at.is_(None)),
            )
        )).scalars().all()

        if not rows:
            return

        from app.services.source_status import CHUNK_ACTIVE
        from app.utils.progress import WIKI_ACTIVE

        for src in rows:
            src.auto_recover_count = (src.auto_recover_count or 0) + 1
            attempts = src.auto_recover_count
            cap = settings.max_auto_recover_attempts
            if attempts >= cap:
                src.error_message = (
                    f"Worker died with no progress for >{timeout_sec // 60} min "
                    f"on {attempts} consecutive attempts (cap={cap}). Retry is "
                    f"blocked — check LLM provider config and source file, then "
                    f"ask an admin to reset auto_recover_count."
                )
            else:
                src.error_message = (
                    f"Worker died with no progress for >{timeout_sec // 60} min. "
                    f"Press Retry to try again ({attempts}/{cap} auto-recoveries used)."
                )
            stuck_chunk = (src.chunk_status or "pending") in CHUNK_ACTIVE
            stuck_wiki = (src.wiki_status or "pending") in WIKI_ACTIVE
            if stuck_chunk or stuck_wiki:
                if stuck_chunk:
                    src.chunk_status = "error"
                    src.chunk_error_message = src.error_message
                if stuck_wiki:
                    src.wiki_status = "error"
                    src.wiki_error_message = src.error_message
                src.status, src.progress, src.progress_message = compute_source_dual_status(src)
            else:
                src.status = "error"
                src.progress_message = src.error_message

            from app.models.task_failure import record_task_failure
            await record_task_failure(
                session=session,
                task_name=src.job_id or "pipeline_stuck_sweep",
                error=TimeoutError(src.error_message),
                source_id=src.id,
                attempt_id=str(src.attempt_id) if src.attempt_id else None,
                payload={"auto_recover_count": attempts, "cap": cap},
            )

        await session.commit()
        logger.warning(
            f"sweep_stuck_processing_cron: flipped {len(rows)} source(s) "
            f"from 'processing' → 'error' (stuck >{timeout_sec}s)"
        )


async def cleanup_orphan_awaiting_approval_cron(ctx: dict):
    """Delete sources stuck in status='awaiting_approval' longer than the TTL.

    A source enters this state after extraction when token count exceeds the
    auto-approve threshold. If a human never approves or cancels, the MinIO
    object + DB row become orphans. This sweep deletes them along with
    associated MinIO data.
    """
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from app.database import async_session_factory
    from app.database.models import Source
    from app.services.storage_service import storage_service

    ttl_hours = max(1, int(settings.extraction_approval_ttl_hours))
    cutoff = datetime.now(timezone.utc) - timedelta(hours=ttl_hours)

    async with async_session_factory() as session:
        rows = (await session.execute(
            select(Source).where(
                Source.status == "awaiting_approval",
                Source.updated_at < cutoff,
            )
        )).scalars().all()

        for src in rows:
            try:
                if src.minio_key:
                    try:
                        storage_service.delete_object(src.minio_key)
                    except Exception as exc:
                        logger.warning(f"cleanup_orphan: minio delete failed for {src.id}: {exc}")
                await session.delete(src)
            except Exception as exc:
                logger.warning(f"cleanup_orphan: delete failed for {src.id}: {exc}")

        if rows:
            await session.commit()
            logger.info(
                f"cleanup_orphan_awaiting_approval_cron: deleted {len(rows)} "
                f"source(s) older than {ttl_hours}h"
            )


async def daily_stats_rollup_cron(ctx: dict):
    """
    Cronjob: recompute admin Statistics rollups for yesterday (UTC).

    Idempotent — re-running overwrites previous rows via the unique constraint on
    (date, metric_key, dimensions_hash). Failures in one section don't stop the others.
    """
    from datetime import datetime, timedelta, timezone

    from app.services.stats_aggregator import run_daily_rollup

    target = (datetime.now(timezone.utc) - timedelta(days=1)).date()
    result = await run_daily_rollup(target)
    logger.info(f"daily_stats_rollup_cron: {target} -> {result}")


async def caption_images_task(ctx: dict, source_id: str, attempt_id_str: Optional[str] = None):
    """
    arq task: vision-caption all SourceImage rows for a source.

    Runs independently from the MRP pipeline — enqueued by ingest_file_task
    immediately after images are persisted to DB. Updates each row's caption
    field as soon as the vision call returns, so captions are available by the
    time ingest_refine_task writes wiki pages.

    Each image opens its own DB session for the UPDATE so concurrent coroutines
    never share session state.
    """
    from sqlalchemy import update as sa_update

    from app.ai.registry import ProviderRegistry
    from app.ai.tracing import flush_langfuse, trace_context
    from app.database import async_session_factory
    from app.database.models import Source, SourceImage
    from app.services.storage_service import storage_service

    sid = uuid.UUID(source_id)

    async with trace_context("caption_images_task", trace_id=f"src_{source_id}", tags=["vision", "caption"], metadata={"source_id": source_id}):
        try:
            # Load vision provider and image rows in a short-lived session, then close it.
            async with async_session_factory() as session:
                source = await session.get(Source, sid)
                if not source:
                    logger.warning(f"caption_images_task: source {source_id} not found")
                    return
                if not await check_task_attempt_validity(session, sid, attempt_id_str, branch="wiki"):
                    logger.warning(f"caption_images_task: source {source_id} attempt {attempt_id_str} is stale, skipping.")
                    return

                registry = ProviderRegistry(session)
                vision_provider = await registry.get_vision()
                if not vision_provider:
                    logger.info(f"caption_images_task: no vision provider configured, skipping to MRP for {source_id}")
                    if attempt_id_str:
                        await _chain_to_mrp(source_id, attempt_id_str=attempt_id_str)
                    else:
                        await _chain_to_mrp(source_id)
                    return

                rows = (await session.execute(
                    select(SourceImage).where(SourceImage.source_id == sid)
                )).scalars().all()

                # Snapshot only the fields we need — session closes after this block.
                image_records = [(row.id, row.minio_key, row.content_type) for row in rows]

            if not image_records:
                logger.info(f"caption_images_task: no image records for {source_id}, skipping to MRP")
                await _chain_to_mrp(source_id)
                return

            logger.info(f"caption_images_task: captioning {len(image_records)} images for {source_id}")

            MAX_CONCURRENCY = 4
            PER_IMAGE_TIMEOUT = 120
            sem = asyncio.Semaphore(MAX_CONCURRENCY)
            total = len(image_records)

            async def _caption_one(image_id, minio_key: str, content_type: str, idx: int) -> None:
                async with sem:
                    try:
                        img_bytes = storage_service.download_file(minio_key)
                        vision_prompt = (
                            "Describe this image concisely in 1-3 sentences. "
                            "Focus on what is shown (diagrams, charts, photos, illustrations) "
                            "and what information it conveys. Be specific — mention key elements, "
                            "labels, numbers, or steps visible in the image. Do not start with "
                            "'Based on the image' or similar filler phrases."
                        )
                        caption = await asyncio.wait_for(
                            vision_provider.analyze_image(img_bytes, content_type, prompt=vision_prompt),
                            timeout=PER_IMAGE_TIMEOUT,
                        )
                        # Each image gets its own session — no concurrent session access.
                        async with async_session_factory() as upd_session:
                            await upd_session.execute(
                                sa_update(SourceImage).where(SourceImage.id == image_id).values(caption=caption)
                            )
                            await upd_session.commit()
                        logger.info(f"caption_images_task: image {idx}/{total} done for {source_id}")
                    except Exception as e:
                        logger.warning(f"caption_images_task: failed {minio_key}: {type(e).__name__}: {e}")

            await asyncio.gather(*[
                _caption_one(img_id, mkey, ctype, idx)
                for idx, (img_id, mkey, ctype) in enumerate(image_records, 1)
            ])
            logger.success(f"caption_images_task: {total} images processed for {source_id}")

            # Bake captions into source.full_text so MAP-phase LLM sees ![<caption>](image://uuid)
            # instead of the empty ![](image://uuid) marker, then chain into MRP.
            import re

            async with async_session_factory() as session:
                source = await session.get(Source, sid)
                if not source:
                    return
                rows = (await session.execute(
                    select(SourceImage).where(SourceImage.source_id == sid)
                )).scalars().all()
                caption_by_id = {str(r.id): (r.caption or "").replace("\n", " ").strip() for r in rows}

                if source.full_text and caption_by_id:
                    def _sub(match: re.Match) -> str:
                        uid = match.group(1)
                        cap = caption_by_id.get(uid, "")
                        return f"![{cap}](image://{uid})"
                    # Replace any marker (empty or already-captioned) so re-runs are idempotent.
                    new_text = re.sub(r"!\[[^\]]*\]\(image://([0-9a-fA-F-]+)\)", _sub, source.full_text)
                    if new_text != source.full_text:
                        source.full_text = new_text
                        await session.commit()
                        logger.info(f"caption_images_task: refreshed full_text with {len(caption_by_id)} captions for {source_id}")

                # Index visual image chunks into source_chunk_embeddings
                try:
                    from app.services.image_service import index_image_chunks
                    image_chunks = []
                    for r in rows:
                        if r.caption:
                            image_chunks.append({
                                "chunk_type": "image_caption",
                                "text": f"[image_caption | Trang {r.page_number or 1}]: {r.caption.strip()}",
                                "page_number": r.page_number or 1,
                                "image_id": str(r.id),
                                "minio_key": r.minio_key,
                            })
                    if image_chunks:
                        await index_image_chunks(session, sid, image_chunks)
                except Exception as img_chunk_err:
                    logger.warning(f"caption_images_task: failed to index image chunks for {source_id}: {img_chunk_err}")

            # Chain into MAP-REDUCE (only now that captions are baked in).
            if attempt_id_str:
                await _chain_to_mrp(source_id, attempt_id_str=attempt_id_str)
            else:
                await _chain_to_mrp(source_id)
        except Exception as exc:
            # If an error happens while captioning, ensure pipeline doesn't hang forever
            logger.error(f"caption_images_task: unhandled error for {source_id}: {exc}")
            if attempt_id_str:
                await _chain_to_mrp(source_id, attempt_id_str=attempt_id_str)
            else:
                await _chain_to_mrp(source_id)
            raise
        finally:
            flush_langfuse()


async def ai_pre_review_draft_task(
    ctx: dict, draft_id: str, expected_round: Optional[int] = None,
) -> None:
    """Run all four AI pre-review layers on a wiki draft.

    `expected_round` is the draft's revision_round at enqueue time — used by
    the runner to drop stale verdicts when the author resubmits mid-flight.
    Optional for backward-compat with jobs enqueued by older code.
    Permissive: never blocks the draft regardless of verdict.
    """
    from app.ai.tracing import flush_langfuse, trace_context
    from app.services.ai_review import run_async_checks
    _ = ctx
    async with trace_context("ai_pre_review_draft_task", tags=["ai_review"], metadata={"draft_id": draft_id, "expected_round": expected_round}):
        try:
            await run_async_checks(draft_id, expected_round=expected_round)
        finally:
            flush_langfuse()


async def reassign_source_scope_task(
    ctx: dict,
    source_id: str,
    old_scopes: list[list],
):
    """
    arq task: Async scope reassignment for a source that was already ready.
    1. Detach old wiki pages and cascades (including vector embeddings in pgvector/Milvus).
    2. Regenerate index for old scopes.
    3. Re-queue ingest_map_reduce_task to compile into the new scope.
    """
    from app.database import async_session_factory
    from app.database.models import Source
    from app.services import wiki_service
    from app.utils.progress import ProgressTracker

    sid = uuid.UUID(source_id)
    tracker = ProgressTracker(sid)
    await tracker.update(0, "Detaching from old wiki scopes...")

    async with async_session_factory() as session:
        source = await session.get(Source, sid)
        if not source:
            logger.warning(f"reassign_source_scope_task: Source {source_id} not found")
            return

        # Detach source from wiki pages in old scopes
        await wiki_service.detach_source_from_wiki(session, sid)

        # Regenerate index for each old scope after detach
        for item in old_scopes:
            st = item[0]
            raw_sid = item[1]
            sid_val = uuid.UUID(raw_sid) if raw_sid else None
            try:
                await wiki_service.regenerate_index(session, scope_type=st, scope_id=sid_val)
            except Exception as e:
                logger.warning(f"regenerate_index failed for scope {st}/{sid_val}: {e}")

        await set_branch_state(
            sid, "wiki", status="queued", progress=5,
            message="Re-queued after scope change...", session=session,
        )

    # Now enqueue ingest_map_reduce_task
    pool = await get_arq_pool()
    job = await pool.enqueue_job("ingest_map_reduce_task", str(sid))
    if job:
        async with async_session_factory() as session:
            source = await session.get(Source, sid)
            if source:
                source.job_id = job.job_id
                await session.commit()


async def relink_legal_relations_task(ctx: dict, source_id: Optional[str] = None) -> dict:
    """Background task to relink unresolved legal relations across legal documents."""
    from app.database import async_session_factory
    from app.services.legal_relation_extractor import relink_legal_relations

    sid = uuid.UUID(source_id) if source_id else None
    logger.info(f"Starting relink_legal_relations_task (source_id={sid})...")
    async with async_session_factory() as session:
        result = await relink_legal_relations(session, source_id=sid)
        logger.info(f"relink_legal_relations_task finished: {result}")
        return result


async def backfill_doc_metadata_task(
    ctx: dict, only_missing: bool = True, use_llm: bool = True, limit: int = 1000,
) -> dict:
    """Backfill document metadata (số hiệu, hiệu lực, lĩnh vực) for existing sources."""
    from app.database import async_session_factory
    from app.services.doc_metadata_service import backfill_document_metadata

    logger.info(f"Starting backfill_doc_metadata_task (only_missing={only_missing}, use_llm={use_llm})...")
    async with async_session_factory() as session:
        result = await backfill_document_metadata(
            session, only_missing=only_missing, use_llm=use_llm, limit=limit,
        )
    logger.info(f"backfill_doc_metadata_task finished: {result}")
    return result


async def generate_questions_task(
    ctx: dict,
    source_id: str,
    attempt_id_str: Optional[str] = None,
    max_provisions: int = 15,
) -> dict:
    """Generate potential search queries for key legal provisions in background queue."""
    from app.database import async_session_factory
    from app.database.models import LegalUnit, Source
    from app.services.question_generator import (
        QuestionGenerator,
        build_question_chunks,
        index_question_chunks,
    )

    sid = uuid.UUID(source_id)
    async with async_session_factory() as session:
        if not await check_task_attempt_validity(session, sid, attempt_id_str):
            logger.warning(f"generate_questions_task: source {source_id} attempt is stale, skipping.")
            return {"status": "stale", "source_id": source_id}

        source = await session.get(Source, sid)
        if not source:
            logger.warning(f"generate_questions_task: source {source_id} not found.")
            return {"status": "not_found", "source_id": source_id}

        # Check provider
        from app.ai.registry import ProviderRegistry
        registry = ProviderRegistry(session)
        llm = await registry.get_llm()

        generator = QuestionGenerator(llm_provider=llm)

        legal_units = (
            await session.execute(
                select(LegalUnit)
                .where(LegalUnit.source_id == sid)
                .limit(max_provisions)
            )
        ).scalars().all()

        all_question_chunks = []
        if legal_units:
            for idx, unit in enumerate(legal_units):
                title = f"{unit.unit_type.value.capitalize()} {unit.unit_number}: {unit.title or ''}"
                questions = await generator.generate_questions_for_chunk(
                    text=unit.content or "",
                    title=title,
                    max_questions=3,
                )
                if questions:
                    chunks = build_question_chunks(
                        source_id=sid,
                        parent_chunk_index=idx,
                        questions=questions,
                        page_number=1,
                        context_preview=unit.content or "",
                    )
                    all_question_chunks.extend(chunks)
        else:
            from app.services.verbatim_service import build_verbatim_chunks
            verbatim_chunks = build_verbatim_chunks(source.full_text or "", source.page_offsets or [])[:max_provisions]
            for c in verbatim_chunks:
                questions = await generator.generate_questions_for_chunk(
                    text=c.text,
                    max_questions=3,
                )
                if questions:
                    chunks = build_question_chunks(
                        source_id=sid,
                        parent_chunk_index=c.index,
                        questions=questions,
                        page_number=c.page_number,
                        context_preview=c.text,
                    )
                    all_question_chunks.extend(chunks)

        indexed_count = 0
        if all_question_chunks:
            indexed_count = await index_question_chunks(session, sid, all_question_chunks)

        logger.info(
            f"generate_questions_task: generated {len(all_question_chunks)} question chunks, "
            f"indexed {indexed_count} for source {source_id}"
        )
        return {
            "status": "success",
            "source_id": source_id,
            "questions_generated": len(all_question_chunks),
            "chunks_indexed": indexed_count,
        }


class WorkerSettings:
    """arq worker configuration."""

    functions = [
        ingest_file_task,
        ingest_url_task,
        ingest_source_chunks_task,
        backfill_source_chunks_task,
        arq_func(caption_images_task, timeout=3600),
        ingest_map_reduce_task,
        ingest_refine_task,
        regenerate_plan_task,
        reembed_all_pages_task,
        ai_pre_review_draft_task,
        reassign_source_scope_task,
        relink_legal_relations_task,
        backfill_doc_metadata_task,
        generate_questions_task,
    ]
    redis_settings = _get_redis_settings()
    max_jobs = settings.worker_max_jobs
    job_timeout = settings.worker_job_timeout
    max_tries = 3
    retry_delay = 10
    health_check_interval = 30

    cron_jobs = [
        cron(daily_stats_rollup_cron, hour=2, minute=0),
        # Every 10 minutes — quick recovery from stuck 'running' AI reviews
        # caused by hard worker death (OOM, SIGKILL, container restart).
        cron(sweep_stuck_ai_review_cron, minute={0, 10, 20, 30, 40, 50}),
        # Every 10 minutes — recover sources stuck at 'processing' from the
        # same class of failures. Flips to 'error' only; no auto-retry.
        cron(sweep_stuck_processing_cron, minute={5, 15, 25, 35, 45, 55}),
        # Hourly: delete orphan sources stuck in awaiting_approval.
        cron(cleanup_orphan_awaiting_approval_cron, minute=15),
    ]

    @staticmethod
    async def on_startup(ctx: dict):
        # from app.ai.tracing import get_langfuse, sync_all_models_to_langfuse
        # get_langfuse()
        # try:
        #     sync_all_models_to_langfuse()
        # except Exception as e:
        #     logger.warning(f"Could not sync models to Langfuse on worker startup: {e}")
        logger.info("arq worker started — listening for ingestion jobs...")

    @staticmethod
    async def on_shutdown(ctx: dict):
        # from app.ai.tracing import shutdown_langfuse
        # shutdown_langfuse()
        logger.info("arq worker shutting down...")


class SkillWorkerSettings:
    """arq worker configuration dedicated to Skills."""

    functions = [ingest_skill_task, delete_skill_task]
    queue_name = "skills_queue"
    redis_settings = _get_redis_settings()
    max_jobs = settings.worker_max_jobs
    job_timeout = settings.worker_job_timeout
    max_tries = 3
    retry_delay = 10
    health_check_interval = 30
    
    cron_jobs = [
        cron(cleanup_temp_uploads_cron, minute=0)
    ]

    @staticmethod
    async def on_startup(ctx: dict):
        # from app.ai.tracing import get_langfuse
        # get_langfuse()
        logger.info("arq skills worker started — listening for skill jobs...")

    @staticmethod
    async def on_shutdown(ctx: dict):
        # from app.ai.tracing import shutdown_langfuse
        # shutdown_langfuse()
        logger.info("arq skills worker shutting down...")
