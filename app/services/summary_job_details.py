"""Per-page summary job records, separate from the lightweight progress snapshot."""
import json
import time

TTL = 86_400


def key(job_id):
    return f"wiki:summaries:items:{job_id}"


def item_for(page, position=0):
    return {
        "page_id": str(page.id), "position": position,
        "slug": page.slug, "title": page.title,
        "scope_type": getattr(page, "scope_type", None) or "global",
        "scope_id": str(page.scope_id) if getattr(page, "scope_id", None) else None,
        "source_titles": [], "status": "queued", "stage": "queued",
        "message": "Đang chờ xử lý", "updated_at": time.time(),
    }


async def seed(redis, job_id, items):
    if items:
        await redis.hset(key(job_id), mapping={item["page_id"]: json.dumps(item, ensure_ascii=False) for item in items})
        await redis.expire(key(job_id), TTL)


async def save(redis, job, item, status, stage, message):
    item.update(status=status, stage=stage, message=message, updated_at=time.time())
    await seed(redis, job["job_id"], [item])
    job["current"] = {field: item[field] for field in ("page_id", "title", "slug", "scope_type", "scope_id", "status", "stage", "message")}


async def read(redis, job, *, offset=0, limit=50, status=None, q=None):
    rows = await redis.hgetall(key(job["job_id"]))
    items = [json.loads(value.decode() if isinstance(value, bytes) else value) for value in rows.values()]
    counts = {}
    for item in items:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    needle = (q or "").strip().casefold()
    selected = [item for item in items if (not status or item["status"] == status)
                and (not needle or needle in " ".join([item["title"], item["slug"], *item.get("source_titles", [])]).casefold())]
    selected.sort(key=lambda item: item["position"])
    return {"items": selected[offset:offset + limit], "total": len(selected), "offset": offset,
            "limit": limit, "counts": counts, "details_available": bool(job.get("details_available"))}
