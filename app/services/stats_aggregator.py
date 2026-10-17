"""Daily statistics rollup into ``stats_daily_rollup`` (06 §8.3).

Each section computes its metrics for one UTC day and upserts them in its own
transaction; a failing section reports -1 without stopping the others.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import string
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

logger = logging.getLogger(__name__)

SEARCH_TOOLS = ("search_wiki", "list_wiki_pages", "list_sources", "get_knowledge_type_docs")
SPECIAL_SLUGS = ("_index", "_log", "_hot")
TOP_N = 10
GAP_TOP_N = 100
GAP_SAMPLES = 5
GAP_MAX_LEN = 200

EN_STOPWORDS = frozenset(
    "the a an of for to in on at and or is are was were be been what how why where when who do does did "
    "i we you it this that these those about with".split()
)
VI_STOPWORDS = frozenset(
    "la lam co khong nao the nay do thi va hoac cua trong voi cho den ai gi sao minh ban ta ho duoc phai "
    "se da dang".split()
)
_STOPWORDS = EN_STOPWORDS | VI_STOPWORDS
_PUNCT_RE = re.compile("[" + re.escape(string.punctuation) + "]")


# ---------------------------------------------------------------- helpers


def day_window(target: date) -> tuple[datetime, datetime]:
    start = datetime.combine(target, time.min, tzinfo=timezone.utc)
    return start, start + timedelta(days=1)


def dimensions_hash(dimensions: Optional[dict]) -> str:
    if not dimensions:
        return ""
    canon = json.dumps(dimensions, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.md5(canon.encode("utf-8")).hexdigest()


def normalize_query(text: Optional[str]) -> str:
    if not text:
        return ""
    cleaned = _PUNCT_RE.sub(" ", text.lower())
    words = [w for w in cleaned.split() if w not in _STOPWORDS]
    return " ".join(words)[:GAP_MAX_LEN].strip()


class _Rows:
    """Collects rollup rows for one section."""

    def __init__(self, day_start: datetime):
        self.day = day_start
        self.rows: list[dict] = []

    def add(self, metric: str, value: Optional[float] = None, dimensions: Optional[dict] = None,
            items: Optional[list] = None, extra: Optional[dict] = None) -> None:
        value_json: Any = None
        if items is not None or extra:
            value_json = dict(extra or {})
            if items is not None:
                value_json["items"] = items
        self.rows.append({
            "date": self.day,
            "metric_key": metric,
            "dimensions": dimensions or None,
            "dimensions_hash": dimensions_hash(dimensions),
            "value_numeric": None if value is None else float(value),
            "value_json": value_json,
        })


async def _upsert(session, rows: list[dict]) -> int:
    from app.database.models import StatsDailyRollup

    if not rows:
        return 0
    now = datetime.now(timezone.utc)
    for r in rows:
        stmt = pg_insert(StatsDailyRollup).values(computed_at=now, **r)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_stats_rollup_keys",
            set_={
                "value_numeric": stmt.excluded.value_numeric,
                "value_json": stmt.excluded.value_json,
                "dimensions": stmt.excluded.dimensions,
                "computed_at": now,
            },
        )
        await session.execute(stmt)
    return len(rows)


async def _scalar(session, stmt) -> Any:
    return (await session.execute(stmt)).scalar()


async def _names(session, ids) -> dict:
    from app.database.models import Employee

    ids = [i for i in ids if i]
    if not ids:
        return {}
    rows = await session.execute(select(Employee.id, Employee.name).where(Employee.id.in_(ids)))
    return dict(rows.all())


# ---------------------------------------------------------------- sections


async def _content(session, start: datetime, end: datetime) -> list[dict]:
    from app.database.models import WikiLink, WikiPage, WikiPageRevision

    out = _Rows(start)
    count = select(func.count()).select_from(WikiPage)
    out.add("wiki.pages.total", await _scalar(session, count) or 0)
    out.add("wiki.pages.created", await _scalar(
        session, count.where(WikiPage.created_at >= start, WikiPage.created_at < end)) or 0)
    out.add("wiki.pages.updated", await _scalar(
        session, count.where(WikiPage.updated_at >= start, WikiPage.updated_at < end)) or 0)
    out.add("wiki.pages.stale_30d", await _scalar(
        session, count.where(WikiPage.updated_at < end - timedelta(days=30))) or 0)
    linked = select(WikiLink.to_slug).distinct()
    out.add("wiki.pages.orphan", await _scalar(session, count.where(WikiPage.slug.not_in(linked))) or 0)
    out.add("wiki.revisions.daily", await _scalar(
        session,
        select(func.count()).select_from(WikiPageRevision).where(
            WikiPageRevision.created_at >= start, WikiPageRevision.created_at < end),
    ) or 0)

    ptype = WikiPage.page_type
    by_type = (await session.execute(select(ptype, func.count()).group_by(ptype))).all()
    for page_type, n in by_type:
        out.add("wiki.pages.by_type", n, dimensions={"page_type": page_type or "unknown"})

    rev_count = func.count(WikiPageRevision.id)
    top = (await session.execute(
        select(WikiPage.slug, WikiPage.title, rev_count)
        .join(WikiPageRevision, WikiPageRevision.page_id == WikiPage.id)
        .where(WikiPageRevision.created_at >= start, WikiPageRevision.created_at < end)
        .group_by(WikiPage.id, WikiPage.slug, WikiPage.title)
        .order_by(rev_count.desc(), WikiPage.slug)
        .limit(TOP_N)
    )).all()
    out.add("wiki.top_pages", len(top), items=[{"slug": s, "title": t, "revisions": int(n)} for s, t, n in top])
    return out.rows


async def _contribution(session, start: datetime, end: datetime) -> list[dict]:
    from app.database.models import SourceCompilationPlan, WikiPageDraft as D

    out = _Rows(start)
    count = select(func.count()).select_from(D)
    in_window = and_(D.created_at >= start, D.created_at < end)
    reviewed = and_(D.reviewed_at >= start, D.reviewed_at < end)
    out.add("draft.created", await _scalar(session, count.where(in_window)) or 0)
    out.add("draft.approved", await _scalar(session, count.where(reviewed, D.status == "approved")) or 0)
    out.add("draft.rejected", await _scalar(session, count.where(reviewed, D.status == "rejected")) or 0)
    out.add("draft.pending", await _scalar(session, count.where(D.status == "pending")) or 0)
    avg = await _scalar(
        session,
        select(func.avg(func.extract("epoch", D.reviewed_at - D.created_at))).where(reviewed),
    )
    out.add("draft.time_to_review_avg_seconds", float(avg) if avg is not None else 0.0)

    for src, n in (await session.execute(
        select(D.source, func.count()).where(in_window).group_by(D.source)
    )).all():
        out.add("draft.created.by_source", n, dimensions={"source": src or "unknown"})

    authors = (await session.execute(
        select(D.author_id, func.count()).where(in_window).group_by(D.author_id)
        .order_by(func.count().desc()).limit(TOP_N)
    )).all()
    reviewers = (await session.execute(
        select(D.reviewed_by_id, func.count()).where(reviewed, D.reviewed_by_id.is_not(None))
        .group_by(D.reviewed_by_id).order_by(func.count().desc()).limit(TOP_N)
    )).all()
    names = await _names(session, [a for a, _ in authors] + [r for r, _ in reviewers])
    out.add("draft.top_contributors", len(authors), items=[
        {"author_id": str(a) if a else None, "name": names.get(a) or "(unknown)", "count": int(n)}
        for a, n in authors
    ])
    out.add("draft.top_reviewers", len(reviewers), items=[
        {"reviewer_id": str(r), "name": names.get(r) or "(unknown)", "count": int(n)} for r, n in reviewers
    ])
    out.add("compile_plan.pending_review", await _scalar(
        session,
        select(func.count()).select_from(SourceCompilationPlan)
        .where(SourceCompilationPlan.status == "pending_review"),
    ) or 0)
    return out.rows


async def _usage(session, start: datetime, end: datetime) -> list[dict]:
    from app.database.models import MCPQueryLog as Q

    out = _Rows(start)
    win = and_(Q.created_at >= start, Q.created_at < end)
    count = select(func.count()).select_from(Q).where(win)
    out.add("mcp.queries.total", await _scalar(session, count) or 0)
    out.add("mcp.queries.zero_result", await _scalar(
        session, count.where(Q.tool_name.in_(SEARCH_TOOLS), Q.result_count == 0)) or 0)
    out.add("mcp.queries.error", await _scalar(session, count.where(Q.status == "error")) or 0)
    out.add("mcp.queries.denied", await _scalar(session, count.where(Q.status == "denied")) or 0)
    out.add("mcp.active_users", await _scalar(
        session, select(func.count(func.distinct(Q.employee_id))).where(win)) or 0)
    out.add("mcp.weekly_active_users", await _scalar(
        session,
        select(func.count(func.distinct(Q.employee_id))).where(
            Q.created_at >= end - timedelta(days=7), Q.created_at < end),
    ) or 0)
    avg = await _scalar(session, select(func.avg(Q.latency_ms)).where(win))
    out.add("mcp.latency_ms_avg", float(avg) if avg is not None else 0.0)

    by_tool = (await session.execute(
        select(Q.tool_name, func.count()).where(win).group_by(Q.tool_name).order_by(func.count().desc())
    )).all()
    out.add("mcp.queries.by_tool", len(by_tool),
            items=[{"tool_name": t, "count": int(n)} for t, n in by_tool])
    top = (await session.execute(
        select(Q.employee_id, func.count()).where(win, Q.employee_id.is_not(None))
        .group_by(Q.employee_id).order_by(func.count().desc()).limit(TOP_N)
    )).all()
    names = await _names(session, [e for e, _ in top])
    out.add("mcp.top_employees", len(top), items=[
        {"employee_id": str(e), "name": names.get(e) or "(unknown)", "count": int(n)} for e, n in top
    ])
    return out.rows


async def _gaps(session, start: datetime, end: datetime) -> list[dict]:
    from app.database.models import MCPQueryLog as Q

    rows = (await session.execute(
        select(Q.query_text, Q.employee_id).where(
            Q.created_at >= start, Q.created_at < end,
            Q.tool_name.in_(SEARCH_TOOLS), Q.result_count == 0,
            Q.query_text.is_not(None),
        )
    )).all()
    groups: dict[str, dict] = {}
    for text, emp in rows:
        key = normalize_query(text)
        if not key:
            continue
        g = groups.setdefault(key, {"normalized": key, "count": 0, "samples": [], "requester_ids": set()})
        g["count"] += 1
        if text not in g["samples"] and len(g["samples"]) < GAP_SAMPLES:
            g["samples"].append(text)
        if emp:
            g["requester_ids"].add(str(emp))
    ranked = sorted(groups.values(), key=lambda g: (-g["count"], g["normalized"]))[:GAP_TOP_N]
    items = [{**g, "requester_ids": sorted(g["requester_ids"])} for g in ranked]
    out = _Rows(start)
    out.add("mcp.gaps.zero_result", len(items), items=items)
    return out.rows


async def _audit(session, start: datetime, end: datetime) -> list[dict]:
    from app.database.models import AuditLog as A

    out = _Rows(start)
    denied = and_(A.timestamp >= start, A.timestamp < end, func.lower(A.decision) == "deny")
    out.add("audit.denied", await _scalar(session, select(func.count()).select_from(A).where(denied)) or 0)
    by_res = (await session.execute(
        select(A.resource_type, func.count()).where(denied).group_by(A.resource_type)
        .order_by(func.count().desc())
    )).all()
    out.add("audit.denied.by_resource", len(by_res),
            items=[{"resource_type": r, "count": int(n)} for r, n in by_res])
    return out.rows


SECTIONS = (
    ("content", _content),
    ("contribution", _contribution),
    ("usage", _usage),
    ("gaps", _gaps),
    ("audit", _audit),
)


async def run_daily_rollup(target_date: date) -> dict[str, int]:
    from app import database

    if isinstance(target_date, datetime):
        target_date = target_date.date()
    start, end = day_window(target_date)
    written: dict[str, int] = {}
    for name, fn in SECTIONS:
        try:
            async with database.async_session_factory() as session:
                rows = await fn(session, start, end)
                written[name] = await _upsert(session, rows)
                await session.commit()
        except Exception as e:
            logger.exception("stats rollup section %s failed for %s: %s", name, target_date, e)
            written[name] = -1
    return written


def yesterday_utc() -> date:
    return datetime.now(timezone.utc).date() - timedelta(days=1)
