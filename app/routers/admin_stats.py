"""Statistics dashboard endpoints over ``stats_daily_rollup`` (06 §8)."""

from __future__ import annotations

import csv
import io
import json
import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import StatsDailyRollup as R
from app.services.auth_service import require_permission

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/stats", tags=["admin-stats"])

MAX_RANGE_DAYS = 366
DEFAULT_RANGE_DAYS = 30

SECTION_METRICS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "content": (
        ("wiki.pages.total", "wiki.pages.created", "wiki.pages.updated", "wiki.pages.stale_30d",
         "wiki.pages.orphan", "wiki.revisions.daily"),
        ("wiki.pages.by_type", "wiki.top_pages"),
    ),
    "contribution": (
        ("draft.created", "draft.approved", "draft.rejected", "draft.pending",
         "draft.time_to_review_avg_seconds", "compile_plan.pending_review"),
        ("draft.top_contributors", "draft.top_reviewers", "draft.created.by_source"),
    ),
    "usage": (
        ("mcp.queries.total", "mcp.queries.zero_result", "mcp.queries.error", "mcp.queries.denied",
         "mcp.active_users", "mcp.weekly_active_users", "mcp.latency_ms_avg"),
        ("mcp.queries.by_tool", "mcp.top_employees"),
    ),
    "gaps": ((), ("mcp.gaps.zero_result",)),
}
OVERVIEW_KPIS = (
    "wiki.pages.total", "wiki.pages.stale_30d", "wiki.pages.orphan", "wiki.pages.updated",
    "draft.pending", "draft.time_to_review_avg_seconds", "compile_plan.pending_review",
    "mcp.active_users", "mcp.weekly_active_users", "mcp.queries.total", "mcp.queries.zero_result",
    "audit.denied",
)
# Metrics kept in ``series`` (and CSV export) but not summarised in latest/latest_lists.
SERIES_ONLY: dict[str, frozenset[str]] = {
    "content": frozenset({"wiki.pages.by_type"}),
    "contribution": frozenset({"draft.time_to_review_avg_seconds", "draft.created.by_source"}),
}
# Breakdown metrics stored as one row per dimension value.
DIMENSION_COUNT_KEY = "count"


class SectionResponse(BaseModel):
    from_date: date
    to_date: date
    series: dict[str, list[dict]]
    latest: dict[str, float]
    latest_lists: dict[str, Any]


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _range(from_date: Optional[date], to_date: Optional[date]) -> tuple[date, date]:
    to_date = to_date or (_today() - timedelta(days=1))
    from_date = from_date or (to_date - timedelta(days=DEFAULT_RANGE_DAYS - 1))
    if from_date > to_date:
        raise HTTPException(status_code=400, detail="from must be <= to")
    if (to_date - from_date).days + 1 > MAX_RANGE_DAYS:
        raise HTTPException(status_code=400, detail="range cannot exceed 366 days")
    return from_date, to_date


def _dt(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=timezone.utc)


async def _rows(db, metrics, from_date: date, to_date: date) -> list:
    if not metrics:
        return []
    stmt = (
        select(R).where(R.metric_key.in_(list(metrics)), R.date >= _dt(from_date),
                        R.date < _dt(to_date) + timedelta(days=1))
        .order_by(R.date, R.metric_key)
    )
    return list((await db.execute(stmt)).scalars().all())


def _day(row) -> str:
    d = row.date
    return (d.date() if isinstance(d, datetime) else d).isoformat()


def _items(row) -> Optional[list]:
    vj = row.value_json
    return vj.get("items") if isinstance(vj, dict) else None


def _latest_list(rows: list) -> list:
    """Items of the newest day: value_json.items, or the per-dimension rows of that day."""
    if not rows:
        return []
    last = max(r.date for r in rows)
    day_rows = [r for r in rows if r.date == last]
    for r in day_rows:
        items = _items(r)
        if items is not None:
            return items
    out = [{**(r.dimensions or {}), DIMENSION_COUNT_KEY: r.value_numeric} for r in day_rows if r.dimensions]
    return sorted(out, key=lambda x: -(x.get(DIMENSION_COUNT_KEY) or 0))


async def _section(db, section: str, from_date: date, to_date: date) -> SectionResponse:
    scalars, lists = SECTION_METRICS[section]
    rows = await _rows(db, scalars + lists, from_date, to_date)
    series: dict[str, list[dict]] = {m: [] for m in scalars + lists}
    latest: dict[str, float] = {}
    by_metric: dict[str, list] = {}
    for r in rows:
        series.setdefault(r.metric_key, []).append({
            "date": _day(r), "value": r.value_numeric, "dimensions": r.dimensions, "items": _items(r),
        })
        by_metric.setdefault(r.metric_key, []).append(r)
    hidden = SERIES_ONLY.get(section, frozenset())
    for m in scalars:
        if m in hidden:
            continue
        mrows = [r for r in by_metric.get(m, []) if not r.dimensions]
        if mrows:
            latest[m] = float(mrows[-1].value_numeric or 0)
    latest_lists = {m: _latest_list(by_metric.get(m, [])) for m in lists if m not in hidden}
    return SectionResponse(from_date=from_date, to_date=to_date, series=series, latest=latest,
                           latest_lists=latest_lists)


def _range_params(
    from_date: Optional[date] = Query(None, alias="from"),
    to_date: Optional[date] = Query(None, alias="to"),
) -> tuple[date, date]:
    return _range(from_date, to_date)


@router.get("/overview")
async def overview(db: AsyncSession = Depends(get_db), user=require_permission("org:settings:manage")):
    from app.services import stats_aggregator

    today = _today()
    start = today - timedelta(days=29)
    keys = OVERVIEW_KPIS + ("mcp.gaps.zero_result", "draft.top_contributors")
    rows = await _rows(db, keys, start, today)
    if not rows:
        await stats_aggregator.run_daily_rollup(today)
        rows = await _rows(db, keys, start, today)

    newest: dict[str, Any] = {}
    for r in rows:  # ordered by date: later rows overwrite
        if not r.dimensions:
            newest[r.metric_key] = r
    kpis: dict[str, Optional[float]] = {"draft.time_to_review_avg_seconds": None}
    for k in OVERVIEW_KPIS:
        if k in newest and newest[k].value_numeric is not None:
            kpis[k] = float(newest[k].value_numeric)
    if "wiki.pages.total" not in kpis:
        from app.database.models import WikiPage

        try:
            n = (await db.execute(
                select(func.count()).select_from(WikiPage).where(
                    WikiPage.slug.not_in(stats_aggregator.SPECIAL_SLUGS))
            )).scalar()
            kpis["wiki.pages.total"] = float(n or 0)
        except Exception as e:
            logger.warning("fallback page count failed: %s", e)

    def _first(metric):
        row = newest.get(metric)
        items = _items(row) if row is not None else None
        return items[0] if items else None

    return {
        "as_of": today.isoformat(),
        "kpis": kpis,
        "top_gap_topic": _first("mcp.gaps.zero_result"),
        "top_contributor": _first("draft.top_contributors"),
    }


@router.get("/content", response_model=SectionResponse)
async def content(rng=Depends(_range_params), db: AsyncSession = Depends(get_db),
                  user=require_permission("org:settings:manage")):
    return await _section(db, "content", *rng)


@router.get("/contribution", response_model=SectionResponse)
async def contribution(rng=Depends(_range_params), db: AsyncSession = Depends(get_db),
                       user=require_permission("org:settings:manage")):
    return await _section(db, "contribution", *rng)


@router.get("/usage", response_model=SectionResponse)
async def usage(rng=Depends(_range_params), db: AsyncSession = Depends(get_db),
                user=require_permission("org:settings:manage")):
    return await _section(db, "usage", *rng)


@router.get("/gaps")
async def gaps(
    rng=Depends(_range_params),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    user=require_permission("org:settings:manage"),
):
    from_date, to_date = rng
    merged: dict[str, dict] = {}
    for r in await _rows(db, ("mcp.gaps.zero_result",), from_date, to_date):
        for it in _items(r) or []:
            key = it.get("normalized")
            if not key:
                continue
            g = merged.setdefault(key, {"normalized": key, "count": 0, "samples": [], "requester_ids": set()})
            g["count"] += int(it.get("count") or 0)
            for s in it.get("samples") or []:
                if s not in g["samples"] and len(g["samples"]) < 5:
                    g["samples"].append(s)
            g["requester_ids"].update(it.get("requester_ids") or [])
    ranked = sorted(merged.values(), key=lambda g: (-g["count"], g["normalized"]))[:limit]
    return {
        "from_date": from_date,
        "to_date": to_date,
        "items": [{**g, "requester_ids": sorted(g["requester_ids"])} for g in ranked],
    }


@router.get("/export/{section}.csv")
async def export_csv(section: str, rng=Depends(_range_params), db: AsyncSession = Depends(get_db),
                     user=require_permission("org:settings:manage")):
    if section not in SECTION_METRICS:
        raise HTTPException(status_code=404, detail=f"unknown section: {section}")
    from_date, to_date = rng
    scalars, lists = SECTION_METRICS[section]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["date", "metric_key", "dimensions_json", "value_numeric", "value_json"])
    for r in await _rows(db, scalars + lists, from_date, to_date):
        w.writerow([
            _day(r), r.metric_key,
            json.dumps(r.dimensions, ensure_ascii=False, sort_keys=True) if r.dimensions else "",
            "" if r.value_numeric is None else r.value_numeric,
            json.dumps(r.value_json, ensure_ascii=False) if r.value_json is not None else "",
        ])
    filename = f"stats_{section}_{from_date.isoformat()}_{to_date.isoformat()}.csv"
    return Response(
        content=buf.getvalue(), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/rollup")
async def rollup(target: Optional[str] = None, user=require_permission("org:settings:manage")):
    from app.services import stats_aggregator

    if target:
        try:
            target_date = date.fromisoformat(target)
        except ValueError:
            raise HTTPException(status_code=400, detail="target must be ISO date YYYY-MM-DD")
    else:
        target_date = _today() - timedelta(days=1)
    written = await stats_aggregator.run_daily_rollup(target_date)
    return {"target_date": target_date.isoformat(), "sections_written": written}
