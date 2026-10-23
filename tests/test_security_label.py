"""Nhãn bảo mật tài liệu và ACL khi truy xuất."""

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.services import security_label as sl


def _sql(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


@pytest.mark.parametrize(
    "clearance,expected",
    [
        ("PUBLIC", ["PUBLIC"]),
        ("INTERNAL", ["PUBLIC", "INTERNAL"]),
        ("restricted", ["PUBLIC", "INTERNAL", "RESTRICTED"]),
        ("CONFIDENTIAL", ["PUBLIC", "INTERNAL", "RESTRICTED", "CONFIDENTIAL"]),
        (None, ["PUBLIC", "INTERNAL"]),
        ("", ["PUBLIC", "INTERNAL"]),
        ("TOP_SECRET", ["PUBLIC", "INTERNAL"]),
    ],
)
def test_allowed_labels_never_exceeds_clearance(clearance, expected):
    assert sl.allowed_labels(clearance) == expected


def test_describe_records_condition_and_level():
    text = sl.describe("RESTRICTED")
    assert "PUBLIC, INTERNAL, RESTRICTED" in text
    assert "CONFIDENTIAL" not in text
    assert "clearance=RESTRICTED" in text


def test_source_clause_is_in_list_of_allowed_labels():
    from app.database.models import Source

    sql = _sql(select(Source.id).where(sl.source_label_clause("INTERNAL")))
    assert "sources.security_label IN ('PUBLIC', 'INTERNAL')" in sql
    assert "CONFIDENTIAL" not in sql


def test_page_clause_hides_pages_built_from_any_higher_source():
    from app.database.models import WikiPage

    sql = _sql(select(WikiPage.id).where(sl.page_label_clause("INTERNAL")))
    assert "NOT (EXISTS" in sql
    assert "ANY (wiki_pages.source_ids)" in sql
    assert "sources.security_label NOT IN ('PUBLIC', 'INTERNAL')" in sql


def _identity(clearance, **kwargs):
    from app.services.mcp_auth_service import ResolvedIdentity

    return ResolvedIdentity(
        employee_id=uuid.uuid4(), employee_name="t", clearance_level=clearance, **kwargs
    )


@pytest.mark.parametrize("scoped", [False, True])
def test_apply_scope_filter_always_applies_label(scoped):
    from app.database.models import Source
    from app.services.mcp_auth_service import apply_scope_filter

    kwargs = {"allowed_knowledge_types": ["van-ban"]} if scoped else {}
    sql = _sql(apply_scope_filter(select(Source.id), _identity("PUBLIC", **kwargs)))
    assert "sources.security_label IN ('PUBLIC')" in sql


def test_identity_without_clearance_is_internal():
    assert _identity("INTERNAL").allowed_labels == ["PUBLIC", "INTERNAL"]


def test_source_read_filter_non_admin_gets_label_but_admin_does_not(monkeypatch):
    from app.routers import sources as src

    def user(role, clearance):
        return SimpleNamespace(
            role=role, clearance_level=clearance, department_ids=[], permissions=["doc:read:all"]
        )

    monkeypatch.setattr(src, "_get_user_permissions", lambda u: {"doc:read:all"})
    allowed, clause = src.source_read_filter(user("employee", "INTERNAL"))
    assert allowed and "sources.security_label IN ('PUBLIC', 'INTERNAL')" in _sql(
        select(src.Source.id).where(clause)
    )
    allowed, clause = src.source_read_filter(user("admin", "INTERNAL"))
    assert allowed and clause is None


def test_checked_label_blocks_labelling_above_own_clearance():
    from fastapi import HTTPException

    from app.routers.sources import _checked_label

    staff = SimpleNamespace(role="employee", clearance_level="INTERNAL")
    assert _checked_label(staff, None) == "INTERNAL"
    assert _checked_label(staff, "public") == "PUBLIC"
    with pytest.raises(HTTPException) as high:
        _checked_label(staff, "CONFIDENTIAL")
    assert high.value.status_code == 403
    with pytest.raises(HTTPException) as bad:
        _checked_label(staff, "SECRET")
    assert bad.value.status_code == 400
    assert _checked_label(SimpleNamespace(role="admin", clearance_level="INTERNAL"), "CONFIDENTIAL") == "CONFIDENTIAL"


@pytest.mark.parametrize("value", [None, "", "  "])
def test_public_upload_default_label_stays_within_clearance(value):
    from app.routers.sources import _checked_label

    assert _checked_label(SimpleNamespace(role="employee", clearance_level="PUBLIC"), value) == "PUBLIC"


@pytest.mark.parametrize("value", ["INTERNAL", "RESTRICTED", "CONFIDENTIAL"])
def test_public_upload_cannot_choose_a_higher_label(value):
    from fastapi import HTTPException
    from app.routers.sources import _checked_label

    with pytest.raises(HTTPException) as error:
        _checked_label(SimpleNamespace(role="employee", clearance_level="PUBLIC"), value)
    assert error.value.status_code == 403


def test_apply_clearances_sets_matched_and_resets_others_to_internal():
    from app.routers.org_sync import SyncClearance, _apply_clearances

    matched = SimpleNamespace(id=1, external_id="kc-1", email="a@x.vn", clearance_level="INTERNAL")
    stale = SimpleNamespace(id=2, external_id="kc-2", email="b@x.vn", clearance_level="CONFIDENTIAL")
    by_email = SimpleNamespace(id=3, external_id=None, email="C@x.vn", clearance_level="INTERNAL")
    result = MagicMock()
    result.scalars.return_value.all.return_value = [matched, stale, by_email]
    db = AsyncMock()
    db.execute.return_value = result

    changed = asyncio.run(_apply_clearances(
        db,
        [
            SyncClearance(keycloak_id="kc-1", clearance_level="RESTRICTED"),
            SyncClearance(keycloak_id="unknown", email="c@x.vn", clearance_level="confidential"),
        ],
    ))

    assert matched.clearance_level == "RESTRICTED"
    assert stale.clearance_level == "INTERNAL"  # không còn trong danh sách → hạ về mặc định
    assert by_email.clearance_level == "CONFIDENTIAL"
    assert changed == 3
