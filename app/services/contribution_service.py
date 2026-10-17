"""Shared review state machine for wiki drafts and skill contributions (05b §2, 06 §3.2)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from loguru import logger
from sqlalchemy import select

from app.services.audit_service import log_audit


class InvalidTransition(Exception):
    """Raised when an action is not allowed from the object's current status."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_admin(user) -> bool:
    return getattr(user, "role", None) == "admin" or getattr(user, "global_role", None) == "admin"


def _draft_display(d) -> str:
    page = getattr(d, "page", None)
    if page is not None:
        return f"{page.title or page.slug} ({page.slug})"
    meta = getattr(d, "suggested_metadata", None) or {}
    if meta.get("slug"):
        return f"{meta.get('title') or meta['slug']} ({meta['slug']})"
    return f"draft {d.id}"


def _contribution_display(c) -> str:
    return getattr(c, "title", None) or f"contribution {c.id}"


async def _draft_reviewers(db, d) -> list:
    from app.services import notification_service as ns

    page = getattr(d, "page", None)
    if page is not None:
        return list(await ns.get_reviewers_for_scope(db, page.scope_type or "global", page.scope_id))
    return list(await ns.get_global_reviewers(db))


async def _contribution_reviewers(db, c) -> list:
    from app.services import notification_service as ns

    return list(await ns.get_global_reviewers(db))


@dataclass(frozen=True)
class Adapter:
    artifact_type: str
    label: str
    target_type: str
    author_attr: str
    display: Callable[[Any], str]
    reviewers: Callable[[Any, Any], Any]

    def author_id(self, obj):
        return getattr(obj, self.author_attr, None)


wiki_draft_adapter = Adapter(
    artifact_type="wiki_draft",
    label="draft",
    target_type="wiki_draft",
    author_attr="author_id",
    display=_draft_display,
    reviewers=_draft_reviewers,
)

skill_contribution_adapter = Adapter(
    artifact_type="skill_contribution",
    label="contribution",
    target_type="skill_contribution",
    author_attr="contributor_id",
    display=_contribution_display,
    reviewers=_contribution_reviewers,
)


def _require(adapter: Adapter, obj, allowed: tuple[str, ...]) -> None:
    status = getattr(obj, "status", None)
    if status not in allowed:
        raise InvalidTransition(
            f"Cannot perform this action while {adapter.label} is in status '{status}'. "
            f"Allowed: {', '.join(allowed)}"
        )


async def _notify_one(db, recipient_id, type_: str, subject: str, adapter: Adapter, obj, body: str = "",
                      actor=None) -> None:
    if recipient_id is None:
        return
    actor_id = getattr(actor, "id", None)
    if actor_id is not None and str(actor_id) == str(recipient_id):
        return
    try:
        from app.services import notification_service as ns

        await ns.notify(db, recipient_id, type_, subject, adapter.target_type, str(obj.id), body=body,
                        actor_id=actor_id)
    except Exception as e:
        logger.warning(f"notification '{type_}' failed: {e}")


async def _notify_reviewers(db, adapter: Adapter, obj, type_: str, subject: str, body: str = "",
                            actor=None) -> None:
    try:
        from app.services import notification_service as ns

        recipients = await adapter.reviewers(db, obj)
        await ns.notify_many(db, recipients, type_, subject, adapter.target_type, str(obj.id), body=body,
                             actor_id=getattr(actor, "id", None), exclude_actor=True)
    except Exception as e:
        logger.warning(f"reviewer notification '{type_}' failed: {e}")


async def _audit(db, user, action: str, adapter: Adapter, obj, reason: Optional[str] = None) -> None:
    try:
        await log_audit(db, user, action, adapter.artifact_type, str(obj.id), reason=reason)
    except Exception as e:
        logger.warning(f"audit '{action}' failed: {e}")


# ---------------------------------------------------------------------------
# AI pre-review queueing
# ---------------------------------------------------------------------------


async def _enqueue_ai_review(db, draft) -> None:
    """Queue the AI pre-review for a draft. Never raises."""
    try:
        enabled = None
        try:
            from app.services.config_service import ConfigService

            enabled = await ConfigService(db).get("ai_pre_review_enabled")
        except Exception as e:
            logger.debug(f"ai_pre_review_enabled lookup failed: {e}")
        if str(enabled).strip().lower() == "false":
            draft.ai_check_status = "skipped"
            return
        draft.ai_check_status = "queued"
        draft.ai_check_results = None
        draft.ai_checked_at = None
        try:
            from app.ai.mrp.pipeline import get_pool

            pool = await get_pool()
            await pool.enqueue_job("ai_pre_review_draft_task", str(draft.id), draft.revision_round or 0)
        except Exception as e:
            logger.warning(f"AI pre-review enqueue failed for draft {draft.id}: {e}")
            draft.ai_check_status = "skipped"
    except Exception as e:  # pragma: no cover - last-resort guard
        logger.warning(f"_enqueue_ai_review failed: {e}")


# ---------------------------------------------------------------------------
# Transitions
# ---------------------------------------------------------------------------


async def notify_submitted(db, adapter: Adapter, obj, actor) -> None:
    if adapter is wiki_draft_adapter:
        await _enqueue_ai_review(db, obj)
    await _notify_reviewers(db, adapter, obj, f"{adapter.artifact_type}_submitted",
                            f"New {adapter.label}: {adapter.display(obj)}", actor=actor)


async def request_changes(db, adapter: Adapter, obj, reviewer, note: Optional[str]) -> None:
    if not (note or "").strip():
        raise InvalidTransition("reviewer_note is required when requesting changes.")
    _require(adapter, obj, ("pending",))
    obj.status = "needs_revision"
    obj.last_returned_note = note.strip()
    if hasattr(obj, "reviewed_by_id"):
        obj.reviewed_by_id = getattr(reviewer, "id", None)
        obj.reviewed_at = _now()
    await _audit(db, reviewer, "request_changes", adapter, obj, reason=note.strip())
    await _notify_one(db, adapter.author_id(obj), "changes_requested",
                      f"Changes requested: {adapter.display(obj)}", adapter, obj, body=note.strip(),
                      actor=reviewer)


async def resubmit_wiki_draft(db, draft, author, new_content_md: str, author_note: Optional[str] = None) -> None:
    from app.database.models import WikiDraftRound

    adapter = wiki_draft_adapter
    _require(adapter, draft, ("needs_revision",))
    if str(draft.author_id) != str(getattr(author, "id", None)):
        raise InvalidTransition("Only the original author can resubmit this draft.")
    current_round = draft.revision_round or 0
    db.add(WikiDraftRound(
        draft_id=draft.id,
        round_no=current_round,
        content_md=draft.content_md,
        author_note=draft.note,
        reviewer_return_note=draft.last_returned_note,
        ai_check_results=draft.ai_check_results,
    ))
    draft.content_md = new_content_md
    if author_note is not None:
        draft.note = author_note
    draft.last_returned_note = None
    draft.ai_check_status = "pending"
    draft.ai_check_results = None
    draft.ai_checked_at = None
    draft.revision_round = current_round + 1
    draft.status = "pending"
    await _enqueue_ai_review(db, draft)
    await _audit(db, author, "resubmit", adapter, draft, reason=f"round {draft.revision_round}")
    await _notify_reviewers(db, adapter, draft, "wiki_draft_resubmitted",
                            f"Resubmitted: {adapter.display(draft)} (round {draft.revision_round})",
                            actor=author)


async def resubmit_skill_contribution(db, contribution, user) -> None:
    adapter = skill_contribution_adapter
    _require(adapter, contribution, ("needs_revision",))
    if str(contribution.contributor_id) != str(getattr(user, "id", None)):
        raise InvalidTransition("Only the original author can resubmit this contribution.")
    contribution.status = "pending"
    contribution.revision_round = (contribution.revision_round or 0) + 1
    await _audit(db, user, "resubmit", adapter, contribution, reason=f"round {contribution.revision_round}")
    await _notify_reviewers(
        db, adapter, contribution, "skill_contribution_resubmitted",
        f"Resubmitted: {adapter.display(contribution)} (round {contribution.revision_round})", actor=user,
    )


async def withdraw(db, adapter: Adapter, obj, author) -> None:
    _require(adapter, obj, ("pending", "needs_revision"))
    if str(adapter.author_id(obj)) != str(getattr(author, "id", None)) and not _is_admin(author):
        raise InvalidTransition("Only the original author can withdraw this contribution.")
    obj.status = "withdrawn"
    await _audit(db, author, "withdraw", adapter, obj)
    await _notify_reviewers(db, adapter, obj, f"{adapter.artifact_type}_withdrawn",
                            f"Withdrawn: {adapter.display(obj)}", actor=author)


async def notify_approved(db, adapter: Adapter, obj, reviewer, version_label: Optional[str] = None) -> None:
    suffix = f" ({version_label})" if version_label else ""
    await _notify_one(db, adapter.author_id(obj), f"{adapter.artifact_type}_approved",
                      f"Approved: {adapter.display(obj)}{suffix}", adapter, obj, actor=reviewer)
    if adapter is not wiki_draft_adapter or getattr(obj, "page_id", None) is None:
        return
    try:
        from app.database.models import WikiPageDraft

        rows = (await db.execute(
            select(WikiPageDraft.author_id).where(
                WikiPageDraft.page_id == obj.page_id,
                WikiPageDraft.status == "pending",
                WikiPageDraft.id != obj.id,
            )
        )).scalars().all()
        seen: set[str] = {str(obj.author_id)} if obj.author_id else set()
        for author_id in rows:
            if author_id is None or str(author_id) in seen:
                continue
            seen.add(str(author_id))
            await _notify_one(db, author_id, "wiki_page_advanced",
                              f"Page updated{suffix}: {adapter.display(obj)} — your pending draft may need a rebase",
                              adapter, obj, actor=reviewer)
    except Exception as e:
        logger.warning(f"notify_approved: sibling draft notification failed: {e}")


async def notify_rejected(db, adapter: Adapter, obj, reviewer, reason: Optional[str] = None) -> None:
    await _notify_one(db, adapter.author_id(obj), f"{adapter.artifact_type}_rejected",
                      f"Rejected: {adapter.display(obj)}", adapter, obj, body=reason or "", actor=reviewer)
