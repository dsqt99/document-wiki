"""Behaviour fixes found by black-box comparison (2026-10-17).

Covers: list caps accepting what the shipped UI sends, department ordering,
admin wiki scopes, stats overview/section shapes, legal-docs knowledge types
and the vision catalog ``protocol`` field.
"""

import re
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select

from app.database import get_db
from app.database.models import WikiPage
from app.main import app
from app.routers import wiki
from app.services.auth_service import get_current_user


def _admin():
    return SimpleNamespace(role="admin", global_role="admin", id="u-admin", departments=[],
                           department_id=None, clearance_level=None)


def _result(rows=None, scalars=None, scalar=None):
    res = MagicMock()
    res.all.return_value = rows or []
    res.scalars.return_value.all.return_value = scalars or []
    res.scalar.return_value = scalar
    return res


# ---------------------------------------------------------------- 1. list caps

# (path, query param, value the frontend sends)
FRONTEND_LIST_QUERIES = [
    ("/api/skills", "limit", 2000),
    ("/api/skills", "limit", 1),
    ("/api/prompts", "limit", 500),
    ("/api/employees", "page_size", 500),
    ("/api/employees", "page_size", 200),
    ("/api/employees", "page_size", 20),
    ("/api/sources", "page_size", 1000),
    ("/api/sources", "page_size", 100),
    ("/api/audit/log", "page_size", 20),
    ("/api/notifications", "limit", 50),
    ("/api/admin/stats/gaps", "limit", 50),
    ("/api/wiki/pages", "limit", 1000),
    ("/api/wiki/graph", "limit", 10),
    ("/api/settings/embeddings/backfill-source-chunks", "limit", 500),
]


def _param_schema(path: str, name: str) -> dict:
    spec = app.openapi()["paths"][path]
    for op in spec.values():
        for p in op.get("parameters", []):
            if p["name"] == name:
                return p["schema"]
    raise AssertionError(f"{path} has no query param {name}")


@pytest.mark.parametrize("path,name,value", FRONTEND_LIST_QUERIES)
def test_list_caps_accept_frontend_values(path, name, value):
    schema = _param_schema(path, name)
    maximum = schema.get("maximum")
    if maximum is None:
        for alt in schema.get("anyOf", []):
            maximum = alt.get("maximum", maximum)
    assert maximum is None or value <= maximum, f"{path}?{name}={value} exceeds cap {maximum}"


async def test_skills_limit_2000_is_accepted():
    db = AsyncMock()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = _admin
    try:
        with patch("app.routers.skills.permission_engine.build_skill_filter", return_value=(False, None)), \
             patch("app.routers.skills.skill_service.list_skills", new=AsyncMock(return_value=([], 0))), \
             patch("app.routers.skills.department_names", new=AsyncMock(return_value={})):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get("/api/skills", params={"limit": 2000})
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"items": [], "total": 0}
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------- 2. departments order

async def test_departments_ordered_by_created_at_ascending():
    from app.routers.rbac import list_departments

    db = AsyncMock()
    db.get.return_value = None  # standalone deployment, no shared directory yet
    db.execute.return_value = _result(rows=[])
    await list_departments(include_inactive=False, user=_admin(), db=db)
    sql = str(db.execute.call_args.args[0]).lower()
    assert "order by departments.created_at asc" in sql


# ---------------------------------------------------------------- 3. my-scopes

async def test_my_scopes_admin_sees_every_department():
    from app.routers.wiki import get_my_scopes

    rows = [(f"d{i}", f"Dept {i}") for i in range(6)]
    db = AsyncMock()
    db.execute.return_value = _result(rows=rows)
    scopes = await get_my_scopes(db=db, user=_admin())
    assert len(scopes) == 7
    assert scopes[0].scope_type == "global" and scopes[0].name == "Global"
    assert [s.scope_id for s in scopes[1:]] == [r[0] for r in rows]
    sql = str(db.execute.call_args.args[0]).lower()
    assert " in " not in sql  # no membership filter for admins


async def test_my_scopes_non_admin_limited_to_own_departments():
    from app.routers import wiki

    user = SimpleNamespace(role="user", global_role=None)
    db = AsyncMock()
    db.execute.return_value = _result(rows=[("d1", "Dept 1")])
    with patch.object(wiki, "_dept_ids", return_value=["d1"]):
        scopes = await wiki.get_my_scopes(db=db, user=user)
    assert [s.scope_type for s in scopes] == ["global", "department"]
    assert " in " in str(db.execute.call_args.args[0]).lower()

    db2 = AsyncMock()
    with patch.object(wiki, "_dept_ids", return_value=[]):
        scopes = await wiki.get_my_scopes(db=db2, user=user)
    assert [s.scope_type for s in scopes] == ["global"]
    db2.execute.assert_not_called()


# ---------------------------------------------------------------- 4/5. stats

def _row(key, day, value=None, dimensions=None, value_json=None):
    return SimpleNamespace(metric_key=key, date=datetime(2026, 10, day, tzinfo=timezone.utc),
                           value_numeric=value, dimensions=dimensions, value_json=value_json)


async def test_overview_as_of_is_today_and_review_kpi_present():
    from app.routers import admin_stats

    rows = [_row("wiki.pages.total", 15, 12), _row("draft.pending", 16, 3)]
    with patch.object(admin_stats, "_rows", new=AsyncMock(return_value=rows)):
        out = await admin_stats.overview(db=AsyncMock(), user=_admin())
    assert out["as_of"] == admin_stats._today().isoformat()
    assert len(out["as_of"]) == 10 and "T" not in out["as_of"]
    assert "draft.time_to_review_avg_seconds" in out["kpis"]
    assert out["kpis"]["draft.time_to_review_avg_seconds"] is None
    assert out["kpis"]["wiki.pages.total"] == 12.0


async def test_overview_review_kpi_keeps_value_when_present():
    from app.routers import admin_stats

    rows = [_row("wiki.pages.total", 15, 1), _row("draft.time_to_review_avg_seconds", 15, 90)]
    with patch.object(admin_stats, "_rows", new=AsyncMock(return_value=rows)):
        out = await admin_stats.overview(db=AsyncMock(), user=_admin())
    assert out["kpis"]["draft.time_to_review_avg_seconds"] == 90.0


async def test_content_section_has_no_by_type_latest_list():
    from app.routers import admin_stats

    rows = [_row("wiki.pages.total", 15, 4), _row("wiki.pages.by_type", 15, 2, {"page_type": "concept"}),
            _row("wiki.top_pages", 15, value_json={"items": [{"slug": "a", "revisions": 2}]})]
    with patch.object(admin_stats, "_rows", new=AsyncMock(return_value=rows)):
        out = await admin_stats._section(AsyncMock(), "content",
                                         datetime(2026, 10, 1).date(), datetime(2026, 10, 16).date())
    assert "wiki.pages.by_type" not in out.latest_lists
    assert out.latest_lists["wiki.top_pages"] == [{"slug": "a", "revisions": 2}]
    assert out.series["wiki.pages.by_type"][0]["dimensions"] == {"page_type": "concept"}


async def test_contribution_section_omits_review_time_and_by_source():
    from app.routers import admin_stats

    rows = [_row("draft.created", 15, 5), _row("draft.time_to_review_avg_seconds", 15, 60),
            _row("draft.created.by_source", 15, 5, {"source": "mcp"})]
    with patch.object(admin_stats, "_rows", new=AsyncMock(return_value=rows)):
        out = await admin_stats._section(AsyncMock(), "contribution",
                                         datetime(2026, 10, 1).date(), datetime(2026, 10, 16).date())
    assert "draft.time_to_review_avg_seconds" not in out.latest
    assert "draft.created.by_source" not in out.latest_lists
    assert out.latest["draft.created"] == 5.0
    assert set(out.latest_lists) == {"draft.top_contributors", "draft.top_reviewers"}


# ---------------------------------------------------------------- 6. legal-docs

async def test_legal_docs_knowledge_types_without_description_and_sort_order():
    from app.routers import legal_docs

    kt = SimpleNamespace(id="kt-1", slug="luat", name="Luật", color="#123456", description="x", sort_order=3)
    db = AsyncMock()
    db.execute.return_value = _result(scalars=[kt])
    with patch("app.routers.sources.source_read_filter", return_value=(False, None)):
        out = await legal_docs.list_legal_docs(content_q=None, db=db, user=_admin())
    assert out["knowledge_types"] == [{"id": "kt-1", "slug": "luat", "name": "Luật", "color": "#123456"}]


# ---------------------------------------------------------------- 7. vision catalog

async def test_vision_catalog_specs_include_protocol():
    from app.routers import admin_models

    custom = SimpleNamespace(id="custom:my-vision", provider="custom", model_id="my-vision", label="",
                             base_url="http://vision.local/v1", protocol="openai")
    with patch.object(admin_models, "_preset_key", new=AsyncMock(return_value="")), \
         patch.object(admin_models, "_custom_key_ok", new=AsyncMock(return_value=True)), \
         patch.object(admin_models, "_active", new=AsyncMock(return_value=None)), \
         patch.object(admin_models.cm, "list_custom", new=AsyncMock(return_value=[custom])):
        out = await admin_models.get_vision_catalog(db=AsyncMock(), _user=_admin())
    dumped = [s.model_dump() for s in out.specs]
    assert dumped and all("protocol" in s for s in dumped)
    assert all(s["protocol"] is None for s in dumped if not s["custom"])
    assert dumped[-1]["protocol"] == "openai"


# ---------------------------------------------------------------- 8. document order

@pytest.fixture
def source_page_database():
    engine = create_engine("sqlite://")
    with engine.connect() as db:
        # PostgreSQL substring(text, pattern) returns the first captured group.
        # Execute the production ordering expression with that function supplied.
        db.connection.create_function("substring", 2, lambda text, pattern: (
            match.group(1) if (match := re.search(pattern, text or "")) else None
        ))
        db.exec_driver_sql("CREATE TABLE wiki_pages (id TEXT, title TEXT, slug TEXT, updated_at TEXT)")
        rows = [
            ("23", "Điều 23: Đăng ký tạm thời - Thông tư 79/2024", "dieu-23-79", "2026-10-20"),
            ("16", "Điều 16: Sang tên xe - Thông tư 79/2024", "dieu-16-79", "2026-10-19"),
            ("19", "Điều 19: Đổi chứng nhận - Thông tư 79/2024", "dieu-19-79", "2026-10-18"),
            ("39", "Điều 39: Chuyển tiếp - Thông tư 79/2024", "dieu-39-79", "2026-10-17"),
            ("10", "Điều 10. Hồ sơ đăng ký", "dieu-10-79", "2026-10-16"),
            ("2b", "Điều 2b: Bổ sung", "dieu-2b-79", "2026-10-15"),
            ("2a", "Điều 2a: Bổ sung", "dieu-2a-79", "2026-10-14"),
            ("2", "Điều 2: Nguyên tắc", "dieu-2-79", "2026-10-13"),
            ("1", "Điều 1. Phạm vi", "dieu-1-79", "2026-10-12"),
            ("overview", "Thông tư 79/2024 - Tổng quan & Căn cứ ban hành", "79-2024", "2026-10-01"),
            ("other", "Đăng ký xe - hướng dẫn chung", "huong-dan", "2026-10-21"),
            ("source", "Tài liệu nguồn", "source/79-2024", "2026-09-01"),
        ]
        db.exec_driver_sql("INSERT INTO wiki_pages VALUES (?, ?, ?, ?)", rows)
        yield db
    engine.dispose()


def test_source_articles_follow_numeric_order_with_overview_first(source_page_database):
    slugs = source_page_database.execute(select(WikiPage.slug).order_by(*wiki._source_page_order())).scalars().all()
    assert slugs == ["79-2024", "source/79-2024", "dieu-1-79", "dieu-2-79", "dieu-2a-79", "dieu-2b-79",
                     "dieu-10-79", "dieu-16-79", "dieu-19-79", "dieu-23-79", "dieu-39-79", "huong-dan"]


def test_source_article_order_applies_before_pagination(source_page_database):
    query = select(WikiPage.slug).order_by(*wiki._source_page_order()).offset(4).limit(3)
    assert source_page_database.execute(query).scalars().all() == ["dieu-2a-79", "dieu-2b-79", "dieu-10-79"]


def test_editing_an_article_does_not_move_it_ahead_of_earlier_articles(source_page_database):
    query = select(WikiPage.slug).order_by(*wiki._source_page_order())
    original = source_page_database.execute(query).scalars().all()
    source_page_database.exec_driver_sql("UPDATE wiki_pages SET updated_at = '2099-01-01' WHERE id = '39'")
    assert source_page_database.execute(query).scalars().all() == original
