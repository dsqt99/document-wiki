"""In-app notifications and their outbound dispatch queue (06 §9.2).

``notify*`` add rows to the caller's session (the caller commits). Every new row is
also queued for outbound delivery (email / webhook): inside an HTTP request the
queue lives in a request-scoped ContextVar and the main.py middleware calls
``dispatch_pending()`` after the response; outside a request it is kept per session
and the caller runs ``dispatch_pending(db)`` after committing.
"""

from __future__ import annotations

import logging
import uuid
import weakref
from contextvars import ContextVar
from typing import Any, Iterable, Optional

from sqlalchemy import or_, select

logger = logging.getLogger(__name__)

_SUFFIXES = ("submitted", "resubmitted", "approved", "rejected", "changes_requested", "withdrawn")


class NotificationType:
    WIKI_DRAFT_SUBMITTED = "wiki_draft.submitted"
    WIKI_DRAFT_RESUBMITTED = "wiki_draft.resubmitted"
    WIKI_DRAFT_APPROVED = "wiki_draft.approved"
    WIKI_DRAFT_REJECTED = "wiki_draft.rejected"
    WIKI_DRAFT_CHANGES_REQUESTED = "wiki_draft.changes_requested"
    WIKI_DRAFT_WITHDRAWN = "wiki_draft.withdrawn"
    SKILL_CONTRIBUTION_SUBMITTED = "skill_contribution.submitted"
    SKILL_CONTRIBUTION_RESUBMITTED = "skill_contribution.resubmitted"
    SKILL_CONTRIBUTION_APPROVED = "skill_contribution.approved"
    SKILL_CONTRIBUTION_REJECTED = "skill_contribution.rejected"
    SKILL_CONTRIBUTION_CHANGES_REQUESTED = "skill_contribution.changes_requested"
    SKILL_CONTRIBUTION_WITHDRAWN = "skill_contribution.withdrawn"

    ALL = tuple(f"{p}.{s}" for p in ("wiki_draft", "skill_contribution") for s in _SUFFIXES)


REVIEWER_GLOBAL_ROLES = ("admin", "knowledge_manager")

# Request-scoped queue (None = no request scope active).
_request_queue: ContextVar[Optional[list]] = ContextVar("arkon_notification_queue", default=None)
# Fallback queue per session object, used outside a request.
_session_queues: "weakref.WeakKeyDictionary[Any, list]" = weakref.WeakKeyDictionary()


def init_request_dispatch_scope() -> None:
    """Start a fresh per-request dispatch queue (called by the HTTP middleware)."""
    _request_queue.set([])


def _queue_for(db) -> list:
    q = _request_queue.get()
    if q is not None:
        return q
    if db is None:
        return []
    try:
        return _session_queues.setdefault(db, [])
    except TypeError:
        return []


def _enqueue(db, notification) -> None:
    _queue_for(db).append(notification)


def take_pending_dispatch(db=None) -> list[dict]:
    """Pop the queued notifications (request queue first, then the session's)."""
    items: list = []
    q = _request_queue.get()
    if q:
        items.extend(q)
        q.clear()
    if db is not None:
        try:
            sq = _session_queues.pop(db, None)
        except TypeError:
            sq = None
        if sq:
            items.extend(sq)
    return [_snapshot(n) for n in items]


def _snapshot(n) -> dict:
    created = getattr(n, "created_at", None)
    return {
        "id": str(n.id) if getattr(n, "id", None) else None,
        "type": n.type,
        "subject": n.subject,
        "body": n.body or "",
        "target_type": n.target_type,
        "target_id": n.target_id,
        "recipient_id": str(n.recipient_id) if n.recipient_id else None,
        "actor_id": str(n.actor_id) if getattr(n, "actor_id", None) else None,
        "created_at": created.isoformat() if created else None,
    }


async def dispatch_pending(db=None) -> None:
    """Deliver queued notifications through the external channels, in a fresh session."""
    items = take_pending_dispatch(db)
    if not items:
        return
    try:
        from app import database
        from app.services import notification_dispatch

        async with database.async_session_factory() as session:
            await notification_dispatch.dispatch(session, items)
    except Exception as e:  # never fail the caller
        logger.warning("notification dispatch failed: %s", e)


def _as_uuid(value) -> Optional[uuid.UUID]:
    if value is None or isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


async def notify(
    db,
    recipient_id,
    type: str,
    subject: str,
    target_type: str,
    target_id,
    body: str = "",
    actor_id=None,
):
    from app.database.models import Notification

    n = Notification(
        id=uuid.uuid4(),
        recipient_id=_as_uuid(recipient_id),
        type=str(type)[:80],
        subject=(subject or "")[:200],
        body=body or "",
        target_type=(target_type or None) and str(target_type)[:40],
        target_id=None if target_id is None else str(target_id)[:100],
        actor_id=_as_uuid(actor_id),
    )
    db.add(n)
    _enqueue(db, n)
    return n


async def notify_each(
    db,
    items: Iterable[dict],
    type: str,
    target_type: str,
    actor_id=None,
    exclude_actor: bool = True,
) -> list:
    out = []
    actor = _as_uuid(actor_id)
    for item in items or []:
        rid = _as_uuid(item.get("recipient_id"))
        if rid is None or (exclude_actor and actor is not None and rid == actor):
            continue
        out.append(
            await notify(
                db, rid, type, item.get("subject") or "", target_type, item.get("target_id"),
                body=item.get("body") or "", actor_id=actor,
            )
        )
    return out


async def notify_many(
    db,
    recipient_ids: Iterable,
    type: str,
    subject: str,
    target_type: str,
    target_id,
    body: str = "",
    actor_id=None,
    exclude_actor: bool = True,
) -> list:
    actor = _as_uuid(actor_id)
    seen: set = set()
    out = []
    for raw in recipient_ids or []:
        rid = _as_uuid(raw)
        if rid is None or rid in seen:
            continue
        seen.add(rid)
        if exclude_actor and actor is not None and rid == actor:
            continue
        out.append(await notify(db, rid, type, subject, target_type, target_id, body=body, actor_id=actor))
    return out


async def get_reviewers_for_scope(db, scope_type: Optional[str] = None, scope_id=None) -> list[uuid.UUID]:
    """Employees allowed to review: role admin, or global_role admin / knowledge_manager."""
    from app.database.models import Employee

    res = await db.execute(
        select(Employee.id).where(
            Employee.is_active.is_(True),
            or_(Employee.role == "admin", Employee.global_role.in_(REVIEWER_GLOBAL_ROLES)),
        )
    )
    return list(res.scalars().all())


async def get_global_reviewers(db) -> list[uuid.UUID]:
    return await get_reviewers_for_scope(db, "global", None)
