"""Kênh `accounts` của /internal/org-sync: khóa, mở khóa và đổi vai trò có hiệu lực ngay trên wiki."""

import asyncio
import uuid
from types import SimpleNamespace

import pytest

from app.config import settings
from app.routers import org_sync
from app.routers.org_sync import SyncAccount, SyncPayload
from app.services import audit_chain

MAP = {"qt-dl": "knowledge_manager", "qt-nd": "viewer"}


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class FakeDB:
    def __init__(self, employees):
        self.employees = employees
        self.flushed = 0

    async def execute(self, _stmt):
        return _Result(self.employees)

    async def flush(self):
        self.flushed += 1


def _emp(external_id, **kw):
    base = dict(
        id=uuid.uuid4(), email=f"{external_id}@x.vn", external_id=external_id, is_active=True, role="employee",
        global_role="contributor", global_role_source="sso",
        mcp_token="t", mcp_token_hash="h", mcp_token_prefix="p",
    )
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.fixture
def audit(monkeypatch):
    events = []

    async def record(**kw):
        events.append(kw)

    monkeypatch.setattr(audit_chain, "record", record)

    async def role_map(_db):
        return MAP

    monkeypatch.setattr(org_sync, "load_role_map", role_map)
    return events


def run(coro):
    return asyncio.run(coro)


def test_disable_deactivates_and_revokes_mcp_token(audit):
    emp = _emp("kc-1")
    out = run(org_sync._apply_accounts(FakeDB([emp]), [SyncAccount(keycloak_id="kc-1", enabled=False)], "Khóa tài khoản"))
    assert out == {"deactivated": 1, "reactivated": 0, "roles_changed": 0}
    assert emp.is_active is False
    assert (emp.mcp_token, emp.mcp_token_hash, emp.mcp_token_prefix) == (None, None, None)
    assert [e["action"] for e in audit] == ["SSO_ACCOUNT_DEACTIVATED"]
    assert audit[0]["reason"] == "Khóa tài khoản"


def test_disable_matches_chatbot_prefix_id(audit):
    emp = _emp("chatbot:abc")
    run(org_sync._apply_accounts(FakeDB([emp]), [SyncAccount(keycloak_id="kc-x", chatbot_id="abc", enabled=False)], None))
    assert emp.is_active is False


def test_unknown_account_is_ignored_and_never_matched_by_email(audit):
    local = _emp(None, email="admin@local.vn")
    out = run(org_sync._apply_accounts(FakeDB([]), [SyncAccount(keycloak_id="kc-9", enabled=False)], None))
    assert out["deactivated"] == 0 and local.is_active is True and audit == []


def test_already_inactive_is_not_audited_again_but_token_still_cleared(audit):
    emp = _emp("kc-1", is_active=False)
    out = run(org_sync._apply_accounts(FakeDB([emp]), [SyncAccount(keycloak_id="kc-1", enabled=False)], None))
    assert out["deactivated"] == 0 and audit == [] and emp.mcp_token is None


def test_periodic_sync_never_reactivates_but_portal_unlock_does(audit):
    periodic = _emp("kc-1", is_active=False)
    run(org_sync._apply_accounts(FakeDB([periodic]), [SyncAccount(keycloak_id="kc-1", enabled=True)], None))
    assert periodic.is_active is False

    unlocked = _emp("kc-2", is_active=False)
    out = run(org_sync._apply_accounts(
        FakeDB([unlocked]), [SyncAccount(keycloak_id="kc-2", enabled=True, reactivate=True)], "Mở khóa"))
    assert unlocked.is_active is True and out["reactivated"] == 1
    assert audit[0]["action"] == "SSO_ACCOUNT_REACTIVATED"


def test_role_change_lowers_global_role_immediately(audit):
    emp = _emp("kc-1", global_role="knowledge_manager")
    out = run(org_sync._apply_accounts(FakeDB([emp]), [SyncAccount(keycloak_id="kc-1", enabled=True, roles=["qt-nd"])], "Đổi vai trò"))
    assert emp.global_role == "viewer" and out["roles_changed"] == 1
    assert audit[0]["action"] == "SSO_GLOBAL_ROLE_SYNC"
    assert audit[0]["metadata"]["before"]["global_role"] == "knowledge_manager"


def test_roles_none_leaves_global_role_alone(audit):
    emp = _emp("kc-1", global_role="knowledge_manager")
    run(org_sync._apply_accounts(FakeDB([emp]), [SyncAccount(keycloak_id="kc-1", enabled=True)], None))
    assert emp.global_role == "knowledge_manager" and audit == []


def test_losing_admin_role_demotes_wiki_admin(audit):
    emp = _emp("kc-1", role="admin", global_role="admin")
    run(org_sync._apply_accounts(FakeDB([emp]), [SyncAccount(keycloak_id="kc-1", enabled=True, roles=["user"])], None))
    assert emp.role == "employee" and emp.global_role != "admin"


def test_admin_role_grants_wiki_admin(audit):
    admin_role = next(iter(settings.sso_admin_role_set))
    emp = _emp("kc-1")
    run(org_sync._apply_accounts(FakeDB([emp]), [SyncAccount(keycloak_id="kc-1", enabled=True, roles=[admin_role])], None))
    assert emp.role == "admin" and emp.global_role == "admin"


def test_accounts_only_payload_skips_the_empty_unit_tree_guard(audit):
    emp = _emp("kc-1")
    out = run(org_sync.apply_org_sync(FakeDB([emp]), SyncPayload(accounts=[SyncAccount(keycloak_id="kc-1", enabled=False)])))
    assert out["accounts_deactivated"] == 1 and emp.is_active is False
