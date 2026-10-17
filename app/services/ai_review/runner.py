"""AI pre-review runner: result format, sync (L1+L2) and async (L1-L4) runs (05b §3.1, §3.6)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from loguru import logger

RESULTS_VERSION = 1

AiReviewResults = dict


_CORE_KEYS = ("id", "layer", "severity", "status", "message")


@dataclass
class CheckResult:
    """One finding produced by a review layer (L1..L4).

    ``extra`` carries layer-specific keys; they are merged into the serialised
    form but never override the core keys.
    """

    status: str
    severity: str
    layer: str
    id: str
    extra: dict = field(default_factory=dict)
    matches: list = field(default_factory=list)
    message: Optional[str] = None

    def to_dict(self) -> dict:
        payload = {key: getattr(self, key) for key in _CORE_KEYS}
        payload["matches"] = [*(self.matches or ())]
        payload.update((k, v) for k, v in (self.extra or {}).items() if k not in payload)
        return payload


def _as_dict(check: Any) -> dict:
    return check.to_dict() if isinstance(check, CheckResult) else dict(check)


def _summary(checks: list[dict]) -> dict:
    s = {"pass": 0, "warn": 0, "fail": 0, "skipped": 0}
    for c in checks:
        st = c.get("status")
        if st in s:
            s[st] += 1
    return s


def build_results(checks: list) -> AiReviewResults:
    items = [_as_dict(c) for c in checks]
    return {"version": RESULTS_VERSION, "summary": _summary(items), "checks": items}


def merge_results(base: Optional[dict], extra_checks: list) -> AiReviewResults:
    current = list((base or {}).get("checks") or [])
    index = {c.get("id"): i for i, c in enumerate(current)}
    for chk in extra_checks or []:
        d = _as_dict(chk)
        if d.get("id") in index:
            current[index[d["id"]]] = d
        else:
            index[d.get("id")] = len(current)
            current.append(d)
    return {"version": RESULTS_VERSION, "summary": _summary(current), "checks": current}


async def run_sync_checks(db, content_md: str, self_slug: Optional[str] = None, self_page_id=None,
                          scope_type: str = "global", scope_id=None) -> AiReviewResults:
    from app.services.ai_review import regex_checks, structural_checks

    checks: list = list(regex_checks.run(content_md))
    checks.extend(await structural_checks.run(db, content_md, self_slug=self_slug, scope_type=scope_type,
                                              scope_id=scope_id))
    return build_results(checks)


def _overall_status(results: dict) -> str:
    s = results.get("summary") or {}
    if s.get("fail"):
        return "failed"
    if s.get("warn"):
        return "warned"
    return "passed"


async def run_async_checks(draft_id, expected_round: Optional[int] = None) -> Optional[AiReviewResults]:
    from app import database
    from app.database.models import WikiPageDraft
    from app.services.ai_review import llm_checks, semantic_checks

    try:
        did = draft_id if isinstance(draft_id, uuid.UUID) else uuid.UUID(str(draft_id))
    except (ValueError, TypeError):
        logger.warning(f"ai_review: invalid draft id {draft_id!r}")
        return None

    async with database.async_session_factory() as db:
        draft = await db.get(WikiPageDraft, did)
        if draft is None or draft.status != "pending":
            return None
        draft.ai_check_status = "running"
        await db.commit()

        page = draft.page
        meta = draft.suggested_metadata or {}
        if page is not None:
            slug, scope_type, scope_id = page.slug, page.scope_type or "global", page.scope_id
            title, page_type, page_id = page.title, getattr(page, "page_type", "concept"), page.id
        else:
            slug, scope_type, scope_id = meta.get("slug"), meta.get("scope_type") or "global", None
            title, page_type, page_id = meta.get("title"), meta.get("page_type") or "concept", None
        content = draft.content_md or ""
        kind = draft.draft_kind or "edit"

        try:
            results = await run_sync_checks(db, content, self_slug=slug, self_page_id=page_id,
                                            scope_type=scope_type, scope_id=scope_id)
        except Exception as e:
            logger.warning(f"ai_review[{did}]: L1/L2 failed: {e}")
            results = build_results([CheckResult(id="runner.l12_error", layer="L2", severity="warn",
                                                 status="skipped", message=str(e))])
        extra: list = []
        try:
            extra.extend(await semantic_checks.run(db, content, page_id, scope_type, scope_id, kind))
            extra.extend(await llm_checks.run(db, content, title or slug or "", page_type))
        except Exception as e:
            logger.warning(f"ai_review[{did}]: L3/L4 failed: {e}")
            extra.append(CheckResult(id="runner.error", layer="L4", severity="warn", status="skipped",
                                     message=str(e)))
        results = merge_results(results, extra)

        if expected_round is not None:
            await db.refresh(draft, attribute_names=["revision_round", "status"])
            if (draft.revision_round or 0) != int(expected_round) or draft.status != "pending":
                logger.info(f"ai_review[{did}]: draft moved on (round/status changed); discarding results")
                return None

        draft.ai_check_results = results
        draft.ai_check_status = _overall_status(results)
        draft.ai_checked_at = datetime.now(timezone.utc)
        await db.commit()
        return results
