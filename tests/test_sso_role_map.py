"""Ánh xạ realm role Keycloak → global_role wiki (không bao giờ ra admin)."""

from app.services.sso_roles import derived_global_role, parse_role_map, reconcile_global_role

MAP = parse_role_map("qt-dl:knowledge_manager,qt-nd:viewer,qt-ai:viewer,qt-ht:viewer")


def test_parse_pairs_and_json():
    assert MAP == {"qt-dl": "knowledge_manager", "qt-nd": "viewer", "qt-ai": "viewer", "qt-ht": "viewer"}
    assert parse_role_map('{"qt-dl": "contributor"}') == {"qt-dl": "contributor"}
    assert parse_role_map("") == {}
    assert parse_role_map("{không phải json") == {}


def test_map_never_grants_admin_or_unknown_roles():
    assert parse_role_map("qt-nd:admin,qt-dl:superuser,qt-ai:viewer") == {"qt-ai": "viewer"}


def test_derived_takes_highest_mapped_role():
    assert derived_global_role(["user", "qt-nd", "qt-dl"], MAP) == "knowledge_manager"
    assert derived_global_role(["qt-ht"], MAP) == "viewer"
    assert derived_global_role(["user"], MAP) is None
    assert derived_global_role([], MAP) is None


def _sso(current, roles, role_map=MAP):
    return reconcile_global_role(current, "sso", roles, role_map, "viewer")


def _manual(current, roles, role_map=MAP):
    return reconcile_global_role(current, "manual", roles, role_map, "viewer")


def test_qt_dl_is_raised_to_knowledge_manager():
    assert _sso("viewer", ["qt-dl"]) == ("knowledge_manager", "sso")
    assert _manual("viewer", ["qt-dl"]) == ("knowledge_manager", "sso")


def test_losing_qt_dl_demotes_knowledge_manager():
    assert _sso("knowledge_manager", ["user"]) == ("viewer", "sso")
    assert _sso("knowledge_manager", []) == ("viewer", "sso")
    assert _sso("knowledge_manager", ["qt-nd"]) == ("viewer", "sso")


def test_lowering_or_deleting_a_role_demotes_its_holders():
    # Lỗi cũ: mức không còn trong bảng ánh xạ bị coi là cấp tay nên không bị hạ.
    before = {"tmp-role": "contributor", "qt-nd": "viewer"}
    assert _sso("viewer", ["tmp-role"], before) == ("contributor", "sso")
    assert _sso("contributor", ["tmp-role"], {"tmp-role": "viewer", "qt-nd": "viewer"}) == ("viewer", "sso")
    assert _sso("contributor", ["tmp-role"], {"qt-nd": "viewer"}) == ("viewer", "sso")
    assert _sso("knowledge_manager", [], {"qt-nd": "viewer"}) == ("viewer", "sso")


def test_manual_grant_is_kept_until_keycloak_raises_it():
    assert _manual("contributor", ["user"]) == ("contributor", "manual")
    assert _manual("contributor", ["qt-nd"]) == ("contributor", "manual")
    assert _manual("knowledge_manager", []) == ("knowledge_manager", "manual")
    # Keycloak nâng thì từ đó Keycloak quản lý: mất vai trò là hạ.
    assert _manual("contributor", ["qt-dl"]) == ("knowledge_manager", "sso")
    assert _sso("knowledge_manager", ["user"]) == ("viewer", "sso")


def test_admin_and_unknown_values_are_untouched():
    assert _sso("admin", ["user"]) == ("admin", "sso")
    assert _manual("custom_x", ["qt-dl"]) == ("custom_x", "manual")
    assert _sso(None, ["qt-dl"]) == ("knowledge_manager", "sso")
    assert _sso(None, []) == ("viewer", "sso")


# ── Bảng ánh xạ do Trợ lý ảo AI đẩy sang (org-sync) ──────────────────────────
import asyncio

import pytest
from fastapi import HTTPException

from app.database.models import AppConfig
from app.routers import org_sync
from app.services import audit_chain
from app.services.sso_roles import ROLE_MAP_CONFIG_KEY, load_role_map


class _FakeDb:
    def __init__(self, value=None):
        self.rows = {} if value is None else {ROLE_MAP_CONFIG_KEY: AppConfig(key=ROLE_MAP_CONFIG_KEY, value=value)}

    async def get(self, _model, key):
        return self.rows.get(key)

    def add(self, row):
        self.rows[row.key] = row

    async def flush(self):
        pass


@pytest.fixture
def audits(monkeypatch):
    calls = []

    async def record(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(audit_chain, "record", record)
    return calls


def test_env_map_is_used_until_chatbot_pushes_one(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "sso_role_global_map", "qt-dl:knowledge_manager")
    assert asyncio.run(load_role_map(_FakeDb())) == {"qt-dl": "knowledge_manager"}
    assert asyncio.run(load_role_map(_FakeDb('{"pho-phong": "contributor"}'))) == {"pho-phong": "contributor"}
    # Bảng rỗng đã đẩy sang là quyết định có chủ đích, không quay về .env.
    assert asyncio.run(load_role_map(_FakeDb("{}"))) == {}


def test_org_sync_stores_role_map_and_audits_before_after(monkeypatch, audits):
    from app.config import settings

    monkeypatch.setattr(settings, "sso_role_global_map", "qt-dl:knowledge_manager")
    db = _FakeDb()
    wanted = {"qt-dl": "knowledge_manager", "can-bo-nghiep-vu": "contributor"}
    assert asyncio.run(org_sync._apply_role_map(db, wanted)) is True
    assert asyncio.run(load_role_map(db)) == wanted
    assert audits[0]["action"] == "SSO_ROLE_MAP_UPDATE"
    assert audits[0]["metadata"] == {"before": {"qt-dl": "knowledge_manager"}, "after": wanted}

    # Gửi lại y hệt: không ghi, không thêm nhật ký.
    assert asyncio.run(org_sync._apply_role_map(db, dict(wanted))) is False
    assert len(audits) == 1


def test_org_sync_role_map_never_grants_admin(audits):
    db = _FakeDb()
    for bad in ({"qt-dl": "admin"}, {"qt-dl": "superuser"}, {"admin": "viewer"}, {" ": "viewer"}):
        with pytest.raises(HTTPException) as e:
            asyncio.run(org_sync._apply_role_map(db, bad))
        assert e.value.status_code == 422
    assert db.rows == {} and audits == []
