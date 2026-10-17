"""Legacy policy facade kept for compatibility; decisions come from permission_engine."""

from dataclasses import dataclass

from app.services import permission_engine


@dataclass
class PolicyDecision:
    allowed: bool
    reason: str


class PolicyEngine:
    def __init__(self, db):
        self.db = db

    async def check_document_access(self, user, source, action: str = "read") -> PolicyDecision:
        allowed = await permission_engine.can_access_document(self.db, user, source, action)
        return PolicyDecision(allowed=allowed, reason="Allowed" if allowed else "Access denied")

    async def check_workspace_access(self, *args, **kwargs) -> PolicyDecision:
        # Workspaces no longer exist; always deny.
        return PolicyDecision(allowed=False, reason="Access denied")
