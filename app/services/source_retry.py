"""Re-queue a failed source; shared by the retry endpoint, bulk retry and the AI-outage resume cron."""

import uuid
from typing import Awaitable, Callable, Optional

from sqlalchemy import or_, select

RETRYABLE = ("error", "partial", "plan_ready")
REFINE_PHASES = ("refine", "verify", "commit")

Enqueue = Callable[..., Awaitable[object]]


class NotRetryable(ValueError):
    pass


def pick_branch(source, branch: Optional[str] = None) -> str:
    from app.services.upload_review_service import review_status

    review = review_status(source)
    if review == "awaiting" or (review == "pending" and branch in ("chunk", "wiki", "both")):
        raise NotRetryable("Hãy duyệt thông tin trích xuất trước khi tạo Wiki hoặc chỉ mục")
    has_text = bool((source.full_text or "").strip())
    chunk_status = source.chunk_status or "pending"
    wiki_status = source.wiki_status or "pending"
    chunk_failed = chunk_status == "error"
    wiki_failed = wiki_status == "error" or source.status == "plan_ready"
    legacy = chunk_status == "pending" and wiki_status == "pending"

    if not branch:
        if not has_text or legacy or not (chunk_failed or wiki_failed):
            branch = "all"
        elif chunk_failed and wiki_failed:
            branch = "both"
        elif chunk_failed:
            branch = "chunk"
        else:
            branch = "wiki"
    if branch in ("chunk", "wiki", "both") and not has_text:
        raise NotRetryable("Source has no extracted text; retry with branch=all")
    return branch


def job_id_of(job) -> Optional[str]:
    jid = getattr(job, "job_id", None) if job is not None else None
    return str(jid) if jid else None


async def has_uncaptioned_images(db, source_id) -> bool:
    from app.database.models import SourceImage

    stmt = (
        select(SourceImage.id)
        .where(SourceImage.source_id == source_id, or_(SourceImage.caption.is_(None), SourceImage.caption == ""))
        .limit(1)
    )
    return (await db.execute(stmt)).first() is not None


async def requeue_source(db, source, enqueue: Enqueue, branch: Optional[str] = None) -> Optional[str]:
    """Reset the failed branch(es) of ``source``, commit, enqueue their first task and return its job id."""
    from app.services.processing_mode import set_mode
    set_mode(source, "auto")
    chosen = pick_branch(source, branch)
    source.error_message = None
    job_id = None

    if chosen == "all":
        source.attempt_id = uuid.uuid4()
        source.status = "pending"
        source.progress = 0
        source.progress_message = "Queued for retry..."
        await db.flush()
        task = "ingest_url_task" if source.source_type == "url" else "ingest_file_task"
        await db.commit()
        job_id = job_id_of(await enqueue(task, str(source.id), str(source.attempt_id)))
    else:
        if chosen in ("chunk", "both"):
            from app import worker

            attempt = str(source.attempt_id) if source.attempt_id else None
            job_id = await worker.commit_and_enqueue_chunk_branch(db, source, attempt)
        if chosen in ("wiki", "both"):
            from app.services import source_status

            if source.pipeline_phase in REFINE_PHASES:
                task = "ingest_refine_task"
            elif await has_uncaptioned_images(db, source.id):
                # A caption run cut short by an outage; it skips captioned images and chains to MAP.
                task = "caption_images_task"
            else:
                task = "ingest_map_reduce_task"
            source.wiki_status = "queued"
            source.wiki_progress = 0
            source.wiki_progress_message = "Queued for retry..."
            source.wiki_error_message = None
            wiki_attempt = source_status.start_wiki_attempt(source)
            await source_status.update_source_dual_status(db, source)
            await db.commit()
            job_id = job_id_of(await enqueue(task, str(source.id), wiki_attempt)) or job_id

    if isinstance(job_id, str) and job_id:
        source.job_id = job_id
    await db.commit()
    return job_id if isinstance(job_id, str) else None


# ---------------------------------------------------------------------------
# Bulk retry (CLI and resume_ai_unavailable_cron)
# ---------------------------------------------------------------------------

PROBE_TIMEOUT_S = 45


def _failure_text(source) -> str:
    return " ".join(
        str(m) for m in (source.error_message, source.wiki_error_message, source.chunk_error_message) if m
    )


# A single transport failure fails the task before the circuit breaker opens, so the stored
# message has no marker; these are how such failures read (see worker._error_text).
TRANSIENT_SIGNATURES = (
    "APIConnectionError", "TimeoutError", "InternalServerError",
    "Error code: 502", "Error code: 503", "Error code: 504", "Error code: 524",
)


def is_ai_outage_text(text: Optional[str]) -> bool:
    from app.ai.upstream import AI_UNAVAILABLE_MARKER

    text = text or ""
    return AI_UNAVAILABLE_MARKER in text or any(sig in text for sig in TRANSIENT_SIGNATURES)


def failed_by_ai_outage(source, plan_json: Optional[dict] = None) -> bool:
    from app.services.wiki_write_guard import is_failure_stub

    if is_ai_outage_text(_failure_text(source)):
        return True
    # Older COMMIT errors retained only slugs, losing the underlying transport
    # error. Recover that evidence from actual failed drafts, not document prose.
    return any(
        isinstance(draft, dict) and is_failure_stub(draft.get("content_md"))
        and is_ai_outage_text(draft.get("content_md"))
        for draft in (plan_json or {}).get("_page_drafts") or []
    )


async def outage_source_ids(db, sources) -> set:
    """Classify failed sources, including legacy plans missing a top-level marker."""
    from app.database.models import SourceCompilationPlan

    found = {s.id for s in sources if failed_by_ai_outage(s)}
    remaining = {s.id: s for s in sources if s.id not in found}
    if remaining:
        plans = (await db.execute(
            select(SourceCompilationPlan.source_id, SourceCompilationPlan.plan_json)
            .where(SourceCompilationPlan.source_id.in_(remaining))
        )).all()
        found.update(sid for sid, plan in plans if failed_by_ai_outage(remaining[sid], plan))
    return found


async def ai_ready(db, need_ocr: bool = False) -> tuple[bool, str]:
    """Send one tiny real request to the LLM (and the OCR model): the gateway lists models even when backends are down."""
    import asyncio

    from app.ai import registry, upstream
    from app.config import settings

    try:
        llm = await registry.ProviderRegistry(db).get_llm()
        upstream.record_success(llm.config.model_id)  # let the probe through an open breaker
        await asyncio.wait_for(llm.generate("Reply with OK.", max_tokens=5, temperature=0), PROBE_TIMEOUT_S)
    except Exception as e:  # noqa: BLE001
        return False, f"LLM: {type(e).__name__}: {str(e)[:200]}"
    if need_ocr:
        from app.services.config_service import ConfigService
        from app.services.ocr_service import OCR_UPSTREAM_KEY, ocr_service

        cfg = ConfigService(db)
        url, key, model = [await cfg.get(k) for k in ("ocr_base_url", "ocr_api_key", "ocr_model")]
        model = model or settings.ocr_model
        if ocr_service.is_configured(base_url=url, api_key=key):
            try:
                client = ocr_service._get_client(base_url=url, api_key=key)
                await asyncio.wait_for(asyncio.to_thread(
                    client.chat.completions.create, model=model, max_tokens=1,
                    messages=[{"role": "user", "content": "ping"}],
                ), PROBE_TIMEOUT_S)
                upstream.record_success(OCR_UPSTREAM_KEY)
            except Exception as e:  # noqa: BLE001
                return False, f"OCR: {type(e).__name__}: {str(e)[:200]}"
    return True, "ok"


async def retry_failed_sources(enqueue: Enqueue, busy: set, *, only_ai_outage: bool = False,
                               reset_recover: bool = False, limit: Optional[int] = None,
                               where=None, probe: bool = True) -> dict:
    """Re-queue failed sources (status error/partial). ``busy`` holds source ids that still have a queued job.

    ``where`` narrows the candidates (e.g. to what a user may read); ``probe=False`` skips the AI health check.
    """
    import app.database as _db
    from app.config import settings
    from app.database.models import Source

    cap = int(settings.max_auto_recover_attempts)
    out = {"requeued": [], "skipped_busy": 0, "skipped_cap": 0, "skipped_other": [], "probe": None}
    async with _db.async_session_factory() as db:
        rows = (await db.execute(
            select(Source).where(Source.status.in_(("error", "partial")), *([where] if where is not None else []))
            .order_by(Source.created_at)
        )).scalars().all()
        if only_ai_outage:
            outage_ids = await outage_source_ids(db, rows)
            rows = [s for s in rows if s.id in outage_ids]
        if not rows:
            return out
        if probe:
            ok, detail = await ai_ready(db, need_ocr=any("'ocr'" in _failure_text(s) for s in rows))
            out["probe"] = detail
            if not ok:
                return out
        for source in rows:
            if limit is not None and len(out["requeued"]) >= limit:
                break
            if source.id in busy:
                out["skipped_busy"] += 1
                continue
            if int(source.auto_recover_count or 0) >= cap:
                if not reset_recover:
                    out["skipped_cap"] += 1
                    continue
                source.auto_recover_count = 0
            if not (source.url if source.source_type == "url" else source.minio_key):
                out["skipped_other"].append((str(source.id), "no file/url"))
                continue
            try:
                await requeue_source(db, source, enqueue)
                out["requeued"].append(str(source.id))
            except NotRetryable as e:
                await db.rollback()
                out["skipped_other"].append((str(source.id), str(e)))
    return out


async def _main(argv=None) -> None:
    import argparse
    import asyncio

    p = argparse.ArgumentParser(description="Re-queue every failed source (status error/partial).")
    p.add_argument("--only-ai-outage", action="store_true", help="only sources that failed with [ai_unavailable]")
    p.add_argument("--reset-recover", action="store_true", help="also retry sources past max_auto_recover_attempts")
    p.add_argument("--wait", action="store_true", help="keep probing every --interval s until the AI gateway answers")
    p.add_argument("--interval", type=int, default=120)
    p.add_argument("--limit", type=int, default=None)
    args = p.parse_args(argv)

    from app import worker

    redis = await worker.get_arq_pool()
    try:
        while True:
            busy = await worker._source_ids_with_pending_jobs(redis)
            res = await retry_failed_sources(
                lambda task, *a: redis.enqueue_job(task, *a), busy, only_ai_outage=args.only_ai_outage,
                reset_recover=args.reset_recover, limit=args.limit,
            )
            print(f"probe={res['probe']} requeued={len(res['requeued'])} busy={res['skipped_busy']} "
                  f"cap={res['skipped_cap']} other={res['skipped_other']}", flush=True)
            if res["requeued"] or res["probe"] in (None, "ok") or not args.wait:
                return
            await asyncio.sleep(args.interval)
    finally:
        await redis.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(_main())
