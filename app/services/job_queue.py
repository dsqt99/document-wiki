"""What the arq worker is doing right now: running and queued jobs with readable labels and progress.

Source-bound jobs report progress through the Source row (``progress`` / ``progress_message``).
Jobs without a source report it with :func:`report_progress`, stored in Redis next to the arq job.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from loguru import logger
from sqlalchemy import select

IN_PROGRESS_PREFIX = "arq:in-progress:"
PROGRESS_PREFIX = "cahy:job-progress:"
PROGRESS_TTL_S = 6 * 3600

JOB_LABELS = {
    "ingest_file_task": "Xử lý tài liệu",
    "ingest_url_task": "Xử lý tài liệu từ URL",
    "resume_upload_review_task": "Tiếp tục xử lý tài liệu",
    "ingest_source_chunks_task": "Tạo chỉ mục văn bản gốc",
    "backfill_source_chunks_task": "Bổ sung chỉ mục văn bản gốc",
    "caption_images_task": "Mô tả hình ảnh",
    "ingest_map_reduce_task": "Biên soạn Wiki",
    "ingest_refine_task": "Biên soạn Wiki",
    "regenerate_plan_task": "Lập lại kế hoạch biên soạn",
    "reembed_all_pages_task": "Tạo lại chỉ mục toàn bộ trang",
    "reembed_missing_pages_task": "Bổ sung chỉ mục trang Wiki",
    "ai_pre_review_draft_task": "AI duyệt sơ bộ bản nháp",
    "reassign_source_scope_task": "Đổi phạm vi tài liệu",
    "detach_source_wiki_task": "Gỡ tài liệu khỏi Wiki",
    "relink_legal_relations_task": "Liên kết lại quan hệ văn bản",
    "backfill_doc_metadata_task": "Trích xuất thông tin văn bản",
    "rebuild_wiki_summaries_task": "Tạo lại tóm tắt trang",
    "generate_questions_task": "Sinh câu hỏi gợi ý",
    "rewrite_pages_after_source_delete_task": "Viết lại trang sau khi xoá tài liệu",
    "ingest_skill_task": "Nạp kỹ năng AI",
    "delete_skill_task": "Xoá kỹ năng AI",
}


async def report_progress(ctx, done: int, total: int, message: str = "") -> None:
    """Record progress for the running arq job (no-op outside the worker)."""
    redis, job_id = (ctx or {}).get("redis"), (ctx or {}).get("job_id")
    if redis is None or not job_id:
        return
    pct = int(done * 100 / total) if total else 0
    try:
        await redis.set(PROGRESS_PREFIX + str(job_id),
                        json.dumps({"progress": pct, "message": message}, ensure_ascii=False), ex=PROGRESS_TTL_S)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"job progress update failed for {job_id}: {e}")


def _short(title: Optional[str], limit: int = 100) -> str:
    line = (title or "").strip().split("\n", 1)[0].strip()
    return line if len(line) <= limit else line[: limit - 1].rstrip() + "…"


def _uuid(value) -> Optional[uuid.UUID]:
    if isinstance(value, uuid.UUID):
        return value
    if isinstance(value, str):
        try:
            return uuid.UUID(value)
        except ValueError:
            return None
    return None


def _detail(function: str, args: tuple) -> Optional[str]:
    if function == "rewrite_pages_after_source_delete_task" and len(args) >= 2:
        n = len(args[0] or []) if isinstance(args[0], (list, tuple)) else 0
        return f"Sau khi xoá «{_short(str(args[1]), 80)}» · {n} trang"
    return None


async def list_jobs(db, pool, source_clause=None, *, include_unbound=False) -> dict[str, Any]:
    """Running jobs first, then queued ones in queue order."""
    from app.database.models import Source

    from app.utils.progress import WIKI_ACTIVE

    from app.worker import SKILLS_QUEUE

    # Cron runs are housekeeping; they queue up behind long jobs but mean nothing to users.
    defs = []
    for queue in (None, SKILLS_QUEUE):
        found = await (pool.queued_jobs() if queue is None else pool.queued_jobs(queue_name=queue))
        defs += [j for j in found if j is not None and not str(j.function).startswith("cron:")]
    defs.sort(key=lambda j: (j.score or 0))
    running_flags = []
    if defs:
        pipe = pool.pipeline()
        for j in defs:
            pipe.exists(IN_PROGRESS_PREFIX + str(j.job_id))
        running_flags = await pipe.execute()

    source_of: dict[str, uuid.UUID] = {}
    for j in defs:
        sid = next((u for u in (_uuid(a) for a in (j.args or ())) if u), None)
        if sid and j.function in JOB_LABELS and j.function != "rewrite_pages_after_source_delete_task":
            source_of[str(j.job_id)] = sid
    sources: dict[uuid.UUID, Source] = {}
    if source_of:
        stmt = select(Source).where(Source.id.in_(set(source_of.values())))
        if source_clause is not None:
            stmt = stmt.where(source_clause)
        sources = {s.id: s for s in (await db.execute(stmt)).scalars().all()}

    running_ids = [str(j.job_id) for j, r in zip(defs, running_flags) if r]
    stored: dict[str, dict] = {}
    if running_ids:
        values = await pool.mget([PROGRESS_PREFIX + jid for jid in running_ids])
        for jid, raw in zip(running_ids, values):
            if raw:
                try:
                    stored[jid] = json.loads(raw)
                except ValueError:
                    pass

    jobs = []
    for j, running in zip(defs, running_flags):
        jid = str(j.job_id)
        src = sources.get(source_of.get(jid)) if jid in source_of else None
        # A filtered/deleted source is not proof that its Redis metadata is
        # public. Only administrators can inspect jobs without a readable source.
        if jid in source_of and src is None:
            continue
        if jid not in source_of and not include_unbound:
            continue
        progress, message = None, None
        if running and src is not None:
            if (src.wiki_status or "") in WIKI_ACTIVE:
                progress, message = src.wiki_progress, src.wiki_progress_message
            else:
                progress, message = src.progress, src.progress_message
        elif running and jid in stored:
            progress, message = stored[jid].get("progress"), stored[jid].get("message")
        jobs.append({
            "id": jid,
            "function": j.function,
            "label": JOB_LABELS.get(j.function, j.function),
            "detail": _detail(j.function, tuple(j.args or ())),
            "source_id": str(src.id) if src is not None else None,
            "source_title": _short(src.title or src.file_name) if src is not None else None,
            "state": "running" if running else "queued",
            "progress": progress,
            "message": message,
            "enqueued_at": j.enqueue_time.isoformat() if j.enqueue_time else None,
        })
    jobs.sort(key=lambda x: x["state"] != "running")
    return {
        "running": sum(1 for x in jobs if x["state"] == "running"),
        "queued": sum(1 for x in jobs if x["state"] == "queued"),
        "jobs": jobs,
    }
