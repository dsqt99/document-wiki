"""Thin compatibility wrapper that writes audit events through the hash chain."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def log_audit(
    db,
    user,
    action: str,
    resource_type: str,
    resource_id,
    decision: str = "ALLOW",
    reason: Optional[str] = None,
) -> None:
    """Record one audit event. ``db`` is accepted for signature compatibility only:
    the chain opens and commits its own transaction. Failures are logged, never raised."""
    try:
        from app.services import audit_chain

        await audit_chain.record(
            principal_id=getattr(user, "id", None),
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else "",
            decision=decision,
            reason=reason,
        )
    except Exception as e:  # pragma: no cover - defensive
        logger.error("Failed to write audit event %s on %s/%s: %s", action, resource_type, resource_id, e)
