"""MRP orchestration, auto-approval and COMMIT phase (05a §5.4, §5.8, §5.9)."""

from __future__ import annotations

from datetime import datetime, timezone
from copy import copy
from types import SimpleNamespace
from typing import Any, Optional

from loguru import logger
from sqlalchemy import select, text

from app.ai.mrp.merger import append_fallback, merge_page_content
from app.services import source_quality, source_status, wiki_chunk_service, wiki_service
from app.services.wiki_service import resolve_wiki_scopes as _resolve_wiki_scopes
from app.services.wiki_write_guard import is_failure_stub

MERGE_MIN_EXISTING_CHARS = 100
SKIPPED_SLUGS_SHOWN = 5


async def _progress(tracker, p: int, msg: str) -> None:
    if tracker is None:
        return
    try:
        await tracker.update(p, msg)
    except Exception as e:
        logger.debug(f"progress update failed: {e}")


async def _lock(session, key: str) -> None:
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": key})


async def _merge_llm(session):
    import app.ai.registry as registry_mod

    try:
        return await registry_mod.ProviderRegistry(session).get_llm()
    except Exception as e:
        logger.info(f"commit: no merge LLM available ({e})")
        return None


async def run_commit_phase(session, source, page_results, plan, embedding_provider, embedding_spec,
                           kt_slug, tracker, *, expected_fingerprint: Optional[str] = None) -> dict:
    from app.database.models import Source

    wiki_scopes = await _resolve_wiki_scopes(session, source)
    # VERIFY annotates factual blockers; COMMIT also enforces them when resumed.
    from app.ai.mrp.verifier import factual_publication_blockers
    full_text = getattr(source, "full_text", None)
    for r in page_results:
        if isinstance(full_text, str) and not is_failure_stub(r.content_md):
            r.publication_blockers = factual_publication_blockers(r.content_md, full_text)
    failed_slugs = sorted(r.slug for r in page_results if is_failure_stub(r.content_md) or getattr(r, "publication_blockers", []))
    failure_reasons = {r.slug: r.publication_blockers for r in page_results
                       if getattr(r, "publication_blockers", [])}
    validation_detail = ", ".join(sorted({reason for reasons in failure_reasons.values() for reason in reasons}))
    # Keep safe diagnostics for generation failures as well as factual blockers;
    # raw provider exception text may contain endpoint/credential details.
    from app.services.source_retry import is_ai_outage_text
    for r in page_results:
        if is_failure_stub(r.content_md):
            reasons = ["generation_failed"]
            if is_ai_outage_text(r.content_md):
                reasons.append("ai_unavailable")
            if any(token in r.content_md.lower() for token in ("timeout", "timed out", "error code: 524")):
                reasons.append("ai_timeout")
            failure_reasons[r.slug] = reasons
    good = [r for r in page_results if r.slug not in failed_slugs]
    planned = (getattr(plan, "plan_json", None) or {}).get("pages") if plan is not None else None
    expected = max(len(planned or []), len(page_results)) * len(wiki_scopes or [("global", None)])
    index_failures = []
    merge_llm = await _merge_llm(session)

    await _progress(tracker, 95, f"Saving {len(good)} wiki page(s)...")
    if expected_fingerprint is not None:
        from app.ai.mrp.writer import checkpoint_fingerprint
        from app.database.models import SourceCompilationPlan

        # ProgressTracker uses a separate Source session: finish it before
        # taking this lock. Hold source + plan locks through publication and
        # the final commit, including the all-reused checkpoint path.
        if plan is None or not await source_quality.lock_current_attempt(session, source, "wiki"):
            await session.rollback()
            return {"status": "stale"}
        current = (await session.execute(
            select(Source.full_text, Source.outline_json, Source.attempt_id)
            .where(Source.id == source.id).execution_options(autoflush=False)
        )).one_or_none()
        latest_plan = (await session.execute(
            select(SourceCompilationPlan.plan_json).where(SourceCompilationPlan.id == plan.id)
            .with_for_update().execution_options(autoflush=False)
        )).scalar_one_or_none()
        snapshot = SimpleNamespace(id=source.id, attempt_id=current.attempt_id,
                                   outline_json=current.outline_json) if current is not None else None
        if (snapshot is None or not isinstance(latest_plan, dict)
                or checkpoint_fingerprint(snapshot, plan, current.full_text, kt_slug,
                                          plan_json=latest_plan) != expected_fingerprint):
            await session.rollback()
            return {"status": "stale"}
    created = 0
    updated = 0
    kt_list = [kt_slug] if kt_slug else []

    for scope_type, scope_id in wiki_scopes or [("global", None)]:
        scope_created = 0
        scope_updated = 0
        from app.services.wiki_origin_service import resolve_target_slug, remap_links
        mapping = {r.slug: await resolve_target_slug(session, r.slug, "generated", scope_type, scope_id, source.id) for r in good}
        scoped_results = []
        for original in good:
            result = copy(original)
            result.slug = mapping[original.slug]
            result.content_md = remap_links(original.content_md, mapping)
            scoped_results.append(result)
        for r in scoped_results:
            status = getattr(r, "status", None) or "seed"
            try:
                await _lock(session, f"{r.slug}:{scope_type}:{scope_id}")
                action = (r.action or "CREATE").upper()
                page = None
                write_kind = None
                expected_content = r.content_md
                if action == "CREATE":
                    existing = await wiki_service.get_page_by_slug(
                        session, r.slug, scope_type=scope_type, scope_id=scope_id
                    )
                    if existing is not None:
                        action = "UPDATE"
                    else:
                        page = await wiki_service.apply_create(
                            session, slug=r.slug, title=r.title, page_type=r.page_type,
                            content_md=r.content_md, summary=r.summary, knowledge_type_slugs=kt_list,
                            source_ids=[source.id], scope_type=scope_type, scope_id=scope_id, status=status,
                            origin_tag="generated",
                        )
                        write_kind = "create"
                if action == "UPDATE":
                    existing = await wiki_service.get_page_by_slug(
                        session, r.slug, scope_type=scope_type, scope_id=scope_id
                    )
                    content = r.content_md
                    old = getattr(existing, "content_md", None) if existing is not None else None
                    if existing is not None:
                        from app.services.wiki_origin_service import require_compatible
                        require_compatible(existing, "generated", source.id)
                    if old and old.strip() != content.strip():
                        if merge_llm is not None and len(old.strip()) > MERGE_MIN_EXISTING_CHARS:
                            content = await merge_page_content(merge_llm, old, r.content_md, r.slug)
                        else:
                            content = append_fallback(old, r.content_md)
                    # Merging may introduce a broken footnote. Old pages may
                    # cite other sources, so check only structural integrity here.
                    broken = [b for b in factual_publication_blockers(content, full_text or "")
                              if b in ("empty_page", "undefined_footnote", "empty_footnote")]
                    if broken:
                        raise ValueError(f"Broken merged evidence: {', '.join(broken)}")
                    expected_content = content
                    page = await wiki_service.apply_update(
                        session, slug=r.slug, new_content_md=content, summary=r.summary, title=r.title,
                        add_knowledge_type_slug=kt_slug, add_source_id=source.id,
                        scope_type=scope_type, scope_id=scope_id, status=status,
                        origin_tag="generated",
                    )
                    if page is None:
                        page = await wiki_service.apply_create(
                            session, slug=r.slug, title=r.title, page_type=r.page_type,
                            content_md=content, summary=r.summary, knowledge_type_slugs=kt_list,
                            source_ids=[source.id], scope_type=scope_type, scope_id=scope_id, status=status,
                            origin_tag="generated",
                        )
                        write_kind = "create"
                    else:
                        write_kind = "update"
                if page is None or write_kind is None:
                    raise ValueError(f"No Wiki page written for action {action}")
                actual_content = getattr(page, "content_md", None)
                if isinstance(actual_content, str) and actual_content != expected_content:
                    raise ValueError("Wiki write guard declined the generated content")
                await session.flush()
                if write_kind == "create":
                    scope_created += 1
                else:
                    scope_updated += 1
                if embedding_spec is not None and page is not None:
                    try:
                        await wiki_chunk_service.index_wiki_page_chunks(
                            session, page, spec_id=getattr(embedding_spec, "id", None)
                        )
                    except Exception as e:
                        index_failures.append(r.slug)
                        logger.warning(f"commit[{r.slug}]: chunk indexing failed: {e}")
            except Exception as e:
                if r.slug not in failed_slugs:
                    failed_slugs.append(r.slug)
                failure_reasons.setdefault(r.slug, []).append("commit_failed")
                logger.error(f"commit[{r.slug}] in {scope_type}:{scope_id} failed: {type(e).__name__}: {e}")

        created += scope_created
        updated += scope_updated
        try:
            await wiki_service.regenerate_index(session, scope_type=scope_type, scope_id=scope_id)
            name = getattr(source, "title", None) or getattr(source, "file_name", None) or str(source.id)
            await wiki_service.append_log(
                session,
                f"MRP: ingested '{name}': +{scope_created} created, ~{scope_updated} updated",
                scope_type=scope_type, scope_id=scope_id,
            )
        except Exception as e:
            logger.warning(f"commit: index/log update failed for {scope_type}:{scope_id}: {e}")

    if plan is not None:
        plan.status = "done"

    src = await session.get(Source, source.id)
    if src is None:
        src = source
    published = created + updated
    failed = max(0, expected - published)
    warnings = []
    if failed:
        warnings.append({"code": "wiki_pages_skipped", "message": f"{failed}/{expected} planned Wiki page(s) were not published: {', '.join(failed_slugs[:SKIPPED_SLUGS_SHOWN])}"})
    if validation_detail:
        warnings.append({"code": "wiki_factual_validation", "message": f"Wiki evidence validation failed: {validation_detail}"})
    if index_failures:
        warnings.append({"code": "wiki_index_failed", "message": f"Wiki vector indexing failed for {len(index_failures)} page(s). Keyword search remains available."})
    saved = await source_quality.save_quality(session, source, "wiki", {
        "status": "error" if not published else "partial" if failed or index_failures else "complete",
        "expected": expected, "published": published, "failed": failed,
        "skipped_slugs": failed_slugs, "failure_reasons": failure_reasons,
        "index_failed_slugs": index_failures, "warnings": warnings,
    })
    if not saved:
        await session.rollback()
        return {"status": "stale"}
    if src is not source:
        src.metadata_ = source.metadata_
    if not published:
        # Nothing was written (typically every page call timed out): report an error so the
        # retry/cron paths pick the source up again, resuming at REFINE.
        from app.ai.upstream import AI_UNAVAILABLE_MARKER
        from app.services.source_retry import is_ai_outage_text

        shown = ", ".join(failed_slugs[:SKIPPED_SLUGS_SHOWN])
        msg = f"All {len(failed_slugs)} page(s) failed to generate: {shown}"
        if validation_detail:
            msg += f"; evidence validation: {validation_detail}"
        # The per-page reasons live only in the stubs; keep the marker so the outage cron resumes it.
        if any(is_ai_outage_text(r.content_md) for r in page_results if is_failure_stub(r.content_md)):
            msg = f"{AI_UNAVAILABLE_MARKER} {msg}"
        src.pipeline_phase = "refine"
        src.wiki_status = "error"
        src.wiki_progress = 0
        src.wiki_progress_message = f"Wiki error: {msg[:200]}"
        src.wiki_error_message = msg
        await source_status.update_source_dual_status(session, src)
        await session.commit()
        return {"pages_created": 0, "pages_updated": 0, "pages_skipped": failed_slugs, "status": "error"}
    src.pipeline_phase = "commit"
    src.wiki_status = "error" if failed or index_failures else "ready"
    src.wiki_progress = 100
    if failed_slugs:
        shown = ", ".join(failed_slugs[:SKIPPED_SLUGS_SHOWN])
        src.wiki_progress_message = (
            f"Done ({len(failed_slugs)} page(s) skipped — generation failed: {shown})"
        )
    else:
        src.wiki_progress_message = "Done"
    src.wiki_error_message = f"Wiki incomplete: {failed} page(s) skipped; {len(index_failures)} index failure(s)" if failed or index_failures else None
    if src.wiki_error_message and validation_detail:
        src.wiki_error_message += f"; evidence validation: {validation_detail}"
    src.auto_recover_count = 0
    await source_status.update_source_dual_status(session, src)
    await session.commit()
    return {"pages_created": created, "pages_updated": updated, "pages_skipped": failed_slugs}


# ---------------------------------------------------------------------------
# Plan approval
# ---------------------------------------------------------------------------


async def _load_plan(session, source_id):
    from app.database.models import SourceCompilationPlan

    return (await session.execute(
        select(SourceCompilationPlan).where(SourceCompilationPlan.source_id == source_id)
    )).scalar_one_or_none()


async def get_pool():
    """Shared arq pool (cached in the sources router, falling back to app.worker)."""
    try:
        from app.routers import sources as sources_router

        getter = getattr(sources_router, "get_arq_pool", None)
        if getter is not None:
            return await getter()
    except ImportError:
        pass
    import app.worker as worker_mod

    return await worker_mod.get_arq_pool()


async def enqueue_refine(source) -> Optional[str]:
    attempt = source_status.wiki_attempt_of(source)
    pool = await get_pool()
    args = [str(source.id)] + ([attempt] if attempt else [])
    job = await pool.enqueue_job("ingest_refine_task", *args)
    return getattr(job, "job_id", None)


async def auto_approve_plan(session, source, plan) -> dict:
    if plan.status == "pending_review":
        plan.status = "approved"
        plan.review_note = "Auto-approved"
        plan.reviewed_at = datetime.now(timezone.utc)
    source.wiki_status = "refining"
    source.wiki_progress_message = "Plan approved — compiling wiki pages..."
    await source_status.update_source_dual_status(session, source)
    await session.commit()
    job_id = await enqueue_refine(source)
    return {"status": "plan_auto_approved", "job_id": job_id}


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


async def _providers(registry):
    llm = await registry.get_llm()
    try:
        emb = await registry.get_embedding(task="document")
    except Exception as e:
        logger.info(f"MRP: no embedding provider ({e})")
        emb = None
    return llm, emb


async def run_mrp_pipeline(session, source, full_text, tracker, registry, kt_slug, kt_name, kt_desc,
                           attempt_id_str: Optional[str] = None) -> dict:
    from app.ai.mrp import mapper, reducer
    from app.config import settings

    auto = bool(getattr(settings, "mrp_auto_approve_plan", False))
    phase = getattr(source, "pipeline_phase", None)
    if phase == "plan_review":
        plan = await _load_plan(session, source.id)
        if plan is not None and plan.status in ("pending_review", "approved"):
            if plan.status == "approved" or auto:
                return await auto_approve_plan(session, source, plan)
            return {"status": "plan_ready", "plan_id": str(plan.id)}
    if phase in ("refine", "verify", "commit"):
        return {"status": f"already_in_{phase}"}

    llm, emb = await _providers(registry)

    source.pipeline_phase = "map"
    strategy = mapper.classify_strategy(full_text or "")
    source.pipeline_strategy = strategy
    await session.commit()
    strategy, done_rows = await mapper.run_map_phase(
        session, source.id, full_text or "", getattr(source, "outline_json", None), tracker, llm,
        source_title=getattr(source, "title", None) or "",
    )
    if not done_rows:
        raise ValueError("MAP phase produced no successful chunk extracts")

    source.pipeline_phase = "reduce"
    source.pipeline_strategy = strategy
    await session.commit()
    plan = await reducer.run_reduce_phase(session, source, done_rows, llm, emb, kt_name, kt_desc, tracker)
    await _progress(tracker, 80, "Compilation plan ready")

    if auto:
        return await auto_approve_plan(session, source, plan)
    return {"status": "plan_ready", "plan_id": str(plan.id)}


async def run_refine_pipeline(session, source, full_text, tracker, registry, kt_slug, kt_name, kt_desc) -> dict:
    from app.ai.mrp import verifier, writer
    from app.database.models import SourceChunkExtract

    plan = await _load_plan(session, source.id)
    if plan is None or plan.status not in ("approved", "in_progress", "done"):
        raise ValueError("No approved compilation plan for this source")
    expected_fingerprint = writer.checkpoint_fingerprint(source, plan, full_text, kt_slug)

    rows = (await session.execute(
        select(SourceChunkExtract)
        .where(SourceChunkExtract.source_id == source.id, SourceChunkExtract.status == "done")
        .order_by(SourceChunkExtract.chunk_index)
    )).scalars().all()

    llm = await registry.get_llm()
    try:
        emb = await registry.get_embedding(task="document")
    except Exception:
        emb = None
    embedding_spec = None
    try:
        spec_id = await registry.get_active_embedding_spec_id()
        if spec_id:
            from app.ai import embedding_catalog

            embedding_spec = embedding_catalog.get_spec(spec_id)
    except Exception as e:
        logger.info(f"refine: no active embedding spec ({e})")

    # Even a complete cache must re-resolve current target slugs and validate
    # cached link dependencies. The writer makes zero LLM calls when stable.
    source.pipeline_phase = "refine"
    plan.status = "in_progress"
    await session.commit()
    results = await writer.run_refine_phase(session, source, plan, rows, full_text, llm, emb, kt_slug, tracker)
    source.pipeline_phase = "verify"
    await session.commit()

    results = await verifier.run_verify_phase(session, source, results, rows, full_text, llm, emb, tracker)
    return await run_commit_phase(session, source, results, plan, emb, embedding_spec, kt_slug, tracker,
                                  expected_fingerprint=expected_fingerprint)
