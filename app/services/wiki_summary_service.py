"""Rebuild wiki summaries from current page content, without re-ingesting sources."""

from __future__ import annotations

import json
import re
import time
import uuid
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import select

from app.database.models import WikiPage
from app.services import wiki_service

JOB_TTL = 86_400
LOCK_TTL = 7_200
ACTIVE = ("queued", "running")


def build_summary(page) -> str:
    from app.services.legal_hierarchy_parser import strip_markup
    from app.services.legal_service import refresh_article_summary

    copy = SimpleNamespace(slug=page.slug, title=page.title, content_md=page.content_md, summary=None)
    refresh_article_summary(copy)
    if copy.summary is not None:
        return copy.summary
    parts = []
    fenced = False
    frontmatter = False
    for i, line in enumerate((page.content_md or "").splitlines()):
        raw = line.strip()
        if i == 0 and raw == "---":
            frontmatter = True
            continue
        if frontmatter:
            if raw == "---":
                frontmatter = False
            continue
        if raw.startswith(("```", "~~~")):
            fenced = not fenced
            continue
        if fenced:
            continue
        if not raw:
            if parts:
                break
            continue
        if raw.startswith(("#", ">", "|", "![")) or raw == "---":
            if parts:
                break
            continue
        # Generated legal overviews start with an attributes list, not prose.
        if re.match(r"^[-*]\s+\*\*[^*]+\*\*\s*:", raw):
            continue
        if parts and re.match(r"^(?:\d+\.|[a-zđ]\)|[-+•–])\s+", raw):
            break
        raw = re.sub(r"\[\[[^]|]+\|([^]]+)\]\]", r"\1", raw)
        raw = re.sub(r"\[\[([^]]+)\]\]", r"\1", raw)
        raw = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", raw)
        text = re.sub(r"^[-+•–]\s+", "", strip_markup(raw))
        if text:
            parts.append(text)
    return " ".join(" ".join(parts).split())


def needs_summary_refresh(current, computed: str) -> bool:
    old = " ".join((current or "").split())
    computed = " ".join((computed or "").split())
    if not computed or old == computed:
        return False
    if not old:
        return True
    if old.endswith(("…", "...")):
        return True
    return len(current or "") in (180, 280, 300, 400) and len(computed) > len(old) and computed.startswith(old)


def needs_llm_summary(page):
    current = (page.summary or "").strip()
    return not current or current.endswith(("...", "…")) or needs_summary_refresh(current, build_summary(page))


async def candidate_pages(db, read_filter=None, *, only_missing=True, engine="extract", page_ids=None):
    stmt = select(WikiPage).where(
        WikiPage.slug.notin_(wiki_service.RESERVED_SLUGS),
        WikiPage.content_md.isnot(None), WikiPage.content_md != "",
    )
    if read_filter is not None:
        stmt = stmt.where(read_filter)
    if page_ids is not None:
        stmt = stmt.where(WikiPage.id.in_(page_ids))
    pages = (await db.execute(stmt.order_by(WikiPage.id))).scalars().all()
    return [p for p in pages if (p.content_md or "").strip()
            and (not only_missing or (needs_llm_summary(p) if engine == "llm" else needs_summary_refresh(p.summary, build_summary(p))))]


def _job_key(job_id):
    return f"wiki:summaries:job:{job_id}"


def _active_key(owner_id):
    return f"wiki:summaries:active:{owner_id}"


def _decode(raw):
    return raw.decode() if isinstance(raw, bytes) else raw


async def _save(redis, job):
    job["updated_at"] = time.time()
    await redis.set(_job_key(job["job_id"]), json.dumps(job, ensure_ascii=False), ex=JOB_TTL)


async def _release(redis, owner_id, job_id):
    # Never delete another job's lock if this worker finishes after its lease expires.
    await redis.eval(
        "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",
        1, _active_key(owner_id), job_id,
    )


async def get_job(redis, job_id, owner_id):
    raw = await redis.get(_job_key(job_id))
    if not raw:
        return None
    job = json.loads(_decode(raw))
    if job.get("owner_id") != str(owner_id):
        return None
    if job["status"] in ACTIVE and time.time() - job["updated_at"] > LOCK_TTL:
        job["status"] = "failed"
        job["message"] = "Tác vụ đã gián đoạn. Bạn có thể chạy lại."
        await _save(redis, job)
        await _release(redis, owner_id, job_id)
    return {k: v for k, v in job.items() if k != "owner_id"}


async def active_job(redis, owner_id):
    job_id = _decode(await redis.get(_active_key(owner_id)))
    return await get_job(redis, job_id, owner_id) if job_id else None


async def recent_job(redis, owner_id):
    job_id = _decode(await redis.get(f"wiki:summaries:recent:{owner_id}"))
    return await get_job(redis, job_id, owner_id) if job_id else None


async def job_items(redis, job_id, owner_id, *, offset=0, limit=50, status=None, q=None):
    from app.services import summary_job_details

    job = await get_job(redis, job_id, owner_id)
    if job is None:
        return None
    return await summary_job_details.read(redis, job, offset=offset, limit=limit, status=status, q=q)


async def start_rebuild(db, redis, read_filter, owner_id, *, only_missing=True, engine="extract", page_ids=None):
    from app.services import summary_job_details as details
    from app.database.models import Source
    owner_id = str(owner_id)
    job_id = str(uuid.uuid4())
    if not await redis.set(_active_key(owner_id), job_id, nx=True, ex=LOCK_TTL):
        existing = await active_job(redis, owner_id)
        if existing and existing["status"] in ACTIVE:
            return existing
        raise HTTPException(409, "Một tác vụ tóm tắt đang được khởi tạo. Vui lòng thử lại sau.")
    try:
        pages = await candidate_pages(db, read_filter, only_missing=only_missing, engine=engine, page_ids=page_ids)
        if page_ids is not None and not pages:
            raise HTTPException(404, "Không có trang Wiki phù hợp trong phạm vi bạn được phép xem.")
        ids = [str(p.id) for p in pages]
        items = [details.item_for(page, index) for index, page in enumerate(pages)]
        source_ids = {sid for page in pages for sid in (getattr(page, "source_ids", None) or [])}
        if source_ids:
            sources = (await db.execute(select(Source.id, Source.title, Source.file_name).where(Source.id.in_(source_ids)))).all()
            names = {sid: title or file_name or str(sid) for sid, title, file_name in sources}
            for page, item in zip(pages, items):
                item["source_titles"] = [names[sid] for sid in (page.source_ids or []) if sid in names]
        job = dict(job_id=job_id, owner_id=owner_id, status="queued" if ids else "completed",
                   only_missing=only_missing, engine=engine, total=len(ids), processed=0, updated=0, failed=0,
                   index_failed=0, unchanged=0, skipped=0, current=None, details_available=True,
                   errors=[], message="Đã xếp hàng cập nhật tóm tắt." if ids else "Không có tóm tắt cần cập nhật.")
        await details.seed(redis, job_id, items)
        await _save(redis, job)
        await redis.set(f"wiki:summaries:recent:{owner_id}", job_id, ex=JOB_TTL)
        if ids:
            queued = await redis.enqueue_job("rebuild_wiki_summaries_task", job_id, ids,
                                             _job_id=f"wiki-summaries:{job_id}")
            if queued is None:
                raise RuntimeError("Không tạo được tác vụ trong hàng đợi")
        else:
            await _release(redis, owner_id, job_id)
        return {k: v for k, v in job.items() if k != "owner_id"}
    except BaseException:
        raw = await redis.get(_job_key(job_id))
        if raw:
            failed = json.loads(_decode(raw))
            failed.update(status="failed", message="Không khởi tạo được tác vụ. Vui lòng chạy lại.")
            await _save(redis, failed)
        await _release(redis, owner_id, job_id)
        raise


async def run_rebuild(ctx, job_id, page_ids):
    from app.database import async_session_factory
    from app.services.wiki_chunk_service import index_wiki_page_chunks
    from app.services import summary_job_details as details

    redis = ctx["redis"]
    raw = await redis.get(_job_key(job_id))
    if not raw:
        raise RuntimeError("Thông tin tác vụ tóm tắt đã hết hạn")
    job = json.loads(_decode(raw))
    if job["status"] not in ACTIVE:
        return job
    if job.get("engine") == "llm":
        return await _run_llm(ctx, job, page_ids)
    job.update(status="running", message="Đang cập nhật tóm tắt từ nội dung wiki mới nhất.")
    await _save(redis, job)
    try:
        # Restarted ARQ attempts revisit pages safely; progress reflects this attempt.
        job.update(processed=0, updated=0, failed=0, index_failed=0, unchanged=0, skipped=0, errors=[])
        stored_items = await details.read(redis, job, limit=max(len(page_ids), 1))
        records = {item["page_id"]: item for item in stored_items["items"]}
        for position, page_id in enumerate(page_ids):
            item = records.get(str(page_id), dict(page_id=str(page_id), position=position, title=str(page_id),
                                               slug="", scope_type="global", scope_id=None, source_titles=[]))
            await details.save(redis, job, item, "running", "reading", "Đang đọc nội dung Wiki mới nhất")
            await _save(redis, job)
            try:
                async with async_session_factory() as db:
                    page = (await db.execute(select(WikiPage).where(
                        WikiPage.id == uuid.UUID(str(page_id)),
                    ).with_for_update())).scalar_one_or_none()
                    if page is not None:
                        item.update(title=page.title, slug=page.slug)
                    if page is not None and page.slug not in wiki_service.RESERVED_SLUGS and (page.content_md or "").strip():
                        await details.save(redis, job, item, "running", "summary", "Đang tạo tóm tắt từ nội dung Wiki")
                        await _save(redis, job)
                        text = build_summary(page)
                        if not text.strip():
                            job["skipped"] += 1
                            await details.save(redis, job, item, "skipped", "summary", "Không có đoạn văn phù hợp để tạo tóm tắt; cần kiểm tra nội dung trích xuất")
                        elif " ".join(text.split()) == " ".join((page.summary or "").split()):
                            job["unchanged"] += 1
                            message = "Tóm tắt đã khớp nội dung Wiki, không cần ghi lại"
                            if text.rstrip().endswith(("...", "…")):
                                message += "; dấu ... đã nằm trong nội dung Wiki hiện tại, không phải bị cắt khi tạo tóm tắt"
                            await details.save(redis, job, item, "unchanged", "completed", message)
                        elif job["only_missing"] and not needs_summary_refresh(page.summary, text):
                            job["skipped"] += 1
                            await details.save(redis, job, item, "skipped", "completed", "Giữ tóm tắt riêng: trang hiện không thuộc nhóm thiếu hoặc bị cắt")
                        else:
                            page.summary = text
                            await db.commit()
                            job["updated"] += 1
                            await details.save(redis, job, item, "running", "indexing", "Đã lưu tóm tắt; đang cập nhật chỉ mục tìm kiếm")
                            await _save(redis, job)
                            try:
                                # Reload after committing so concurrent edits are indexed from their latest content.
                                await db.refresh(page)
                                await index_wiki_page_chunks(db, page)
                                await db.commit()
                                await details.save(redis, job, item, "updated", "completed", "Đã cập nhật tóm tắt và chỉ mục tìm kiếm")
                            except Exception as exc:
                                await db.rollback()
                                job["index_failed"] += 1
                                await details.save(redis, job, item, "index_failed", "indexing", f"Tóm tắt đã lưu, chỉ mục bị lỗi: {type(exc).__name__}: {str(exc).splitlines()[0][:240] if str(exc) else 'Không có chi tiết'}")
                    else:
                        job["skipped"] += 1
                        await details.save(redis, job, item, "skipped", "reading", "Trang đã bị xóa, là trang hệ thống hoặc không có nội dung Wiki")
            except Exception as exc:
                job["failed"] += 1
                await details.save(redis, job, item, "failed", item.get("stage", "reading"), f"Không cập nhật được: {type(exc).__name__}: {str(exc).splitlines()[0][:240] if str(exc) else 'Không có chi tiết'}")
                if len(job["errors"]) < 5:
                    job["errors"].append(f"{page_id}: {type(exc).__name__}")
            job["processed"] += 1
            await _save(redis, job)
            # Renew only our lease; don't steal a newer run's active pointer.
            await redis.eval(
                "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('expire', KEYS[1], ARGV[2]) else return 0 end",
                1, _active_key(job["owner_id"]), job_id, LOCK_TTL,
            )
        message = f"Hoàn tất {job['processed']}/{job['total']} trang: cập nhật {job['updated']}, đã khớp {job['unchanged']}, bỏ qua {job['skipped']}"
        if job["failed"] or job["index_failed"]:
            message += f", lỗi {job['failed']}, lỗi chỉ mục {job['index_failed']}"
        job.update(status="completed", current=None, message=message + ".")
        await _save(redis, job)
        return {k: v for k, v in job.items() if k != "owner_id"}
    except BaseException:
        job.update(status="failed", message="Tác vụ đã gián đoạn. Bạn có thể chạy lại.")
        await _save(redis, job)
        raise
    finally:
        await _release(redis, job["owner_id"], job_id)


async def generate_llm_summary(snapshot, progress):
    from app.database import async_session_factory
    from app.ai.registry import ProviderRegistry
    from app.services.llm_summary_service import summarize_page
    # Resolve configuration in a short transaction, then release the connection.
    async with async_session_factory() as db:
        llm = await ProviderRegistry(db).get_llm()

    async def model_progress(stage, message):
        await progress(stage, f"{llm.config.model_id} · {message}")

    return await summarize_page(llm, snapshot.title or snapshot.slug, snapshot.content_md, model_progress)


def _snapshot(page):
    return SimpleNamespace(**{key: getattr(page, key, None) for key in
                            ("id", "slug", "title", "content_md", "summary", "scope_type", "scope_id", "version")})


async def _run_llm(ctx, job, page_ids):
    from app.database import async_session_factory
    from app.services import summary_job_details as details
    from app.services.wiki_chunk_service import index_wiki_page_chunks
    redis, job_id = ctx["redis"], job["job_id"]
    job.update(status="running", message="Đang tóm tắt toàn bộ nội dung từng trang bằng AI.")
    await _save(redis, job)
    stored = await details.read(redis, job, limit=max(len(page_ids), 1))
    records = {item["page_id"]: item for item in stored["items"]}
    batch_count = 0
    try:
        for position, page_id in enumerate(page_ids):
            item = records[str(page_id)]
            if position < job["processed"]:
                continue

            async def progress(stage, message):
                await details.save(redis, job, item, "running", stage, message)
                await _save(redis, job)
                await redis.eval("if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('expire', KEYS[1], ARGV[2]) else return 0 end",
                                 1, _active_key(job["owner_id"]), job_id, LOCK_TTL)

            try:
                await progress("reading", "Đang đọc toàn bộ nội dung Wiki mới nhất")
                async with async_session_factory() as db:
                    page = (await db.execute(select(WikiPage).where(WikiPage.id == uuid.UUID(str(page_id))))).scalar_one_or_none()
                    snapshot = _snapshot(page) if page else None
                if not snapshot or snapshot.slug in wiki_service.RESERVED_SLUGS or not (snapshot.content_md or "").strip():
                    job["skipped"] += 1
                    await details.save(redis, job, item, "skipped", "reading", "Trang đã bị xóa hoặc không có nội dung")
                elif (snapshot.scope_type or "global", str(snapshot.scope_id) if snapshot.scope_id else None) != (item["scope_type"], item["scope_id"]):
                    job["skipped"] += 1
                    await details.save(redis, job, item, "skipped", "reading", "Phạm vi trang đã thay đổi; hãy chọn lại trang")
                elif job["only_missing"] and not needs_llm_summary(snapshot):
                    job["skipped"] += 1
                    await details.save(redis, job, item, "skipped", "completed", "Trang đã có bản tóm tắt; giữ nguyên")
                else:
                    item.update(title=snapshot.title or snapshot.slug, slug=snapshot.slug)
                    text = await generate_llm_summary(snapshot, progress)
                    await progress("validating", "Đang kiểm tra phiên bản trang trước khi lưu tóm tắt AI")
                    async with async_session_factory() as db:
                        page = (await db.execute(select(WikiPage).where(WikiPage.id == snapshot.id).with_for_update())).scalar_one_or_none()
                        if page is None or vars(_snapshot(page)) != vars(snapshot):
                            job["skipped"] += 1
                            await details.save(redis, job, item, "skipped", "validating", "Nội dung hoặc tóm tắt đã thay đổi trong khi AI chạy; giữ bản mới, hãy chạy lại")
                        elif text == (page.summary or ""):
                            job["unchanged"] += 1
                            await details.save(redis, job, item, "unchanged", "completed", "AI đã đọc toàn bộ trang; kết quả không thay đổi")
                        else:
                            page.summary = text
                            await db.commit()
                            job["updated"] += 1
                            try:
                                await progress("indexing", "Đã lưu tóm tắt AI đầy đủ; đang cập nhật chỉ mục")
                                await db.refresh(page)
                                await index_wiki_page_chunks(db, page)
                                await db.commit()
                                await details.save(redis, job, item, "updated", "completed", f"Đã lưu tóm tắt AI ({len(text)} ký tự) và cập nhật chỉ mục")
                            except Exception as exc:
                                await db.rollback()
                                job["index_failed"] += 1
                                await details.save(redis, job, item, "index_failed", "indexing", f"Tóm tắt AI đã lưu; chỉ mục chưa cập nhật ({type(exc).__name__})")
            except Exception as exc:
                job["failed"] += 1
                message = str(exc) if isinstance(exc, ValueError) else f"Không gọi được mô hình AI ({type(exc).__name__}); kiểm tra cấu hình/kết nối rồi thử lại."
                await details.save(redis, job, item, "failed", item.get("stage", "llm"), message[:400])
                if len(job["errors"]) < 5:
                    job["errors"].append(f"{page_id}: {type(exc).__name__}")
            job["processed"] += 1
            batch_count += 1
            await _save(redis, job)
            # Yield long library runs to ARQ instead of exceeding a worker job timeout.
            if batch_count >= 5 and job["processed"] < len(page_ids):
                queued = await redis.enqueue_job("rebuild_wiki_summaries_task", job_id, page_ids,
                                                 _job_id=f"wiki-summaries:{job_id}:{job['processed']}")
                if queued is None:
                    raise RuntimeError("Không xếp hàng được phần tiếp theo")
                return {k: v for k, v in job.items() if k != "owner_id"}
        job.update(status="completed", current=None,
                   message=f"AI đã xử lý {job['processed']}/{job['total']} trang: cập nhật {job['updated']}, không đổi {job['unchanged']}, bỏ qua {job['skipped']}, lỗi {job['failed']}, lỗi chỉ mục {job['index_failed']}.")
        await _save(redis, job)
        return {k: v for k, v in job.items() if k != "owner_id"}
    except BaseException:
        job.update(status="failed", message="Tác vụ tóm tắt AI đã gián đoạn; có thể chạy lại.")
        await _save(redis, job)
        raise
    finally:
        if job["status"] not in ACTIVE:
            await _release(redis, job["owner_id"], job_id)
