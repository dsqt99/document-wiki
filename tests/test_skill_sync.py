"""POST /internal/skill-sync: danh sách kỹ năng toàn hệ thống (kèm thân SKILL.md) cho chatbot nạp vào menu kỹ năng.

Hồi quy: org_sync từng import ``_read_skill_files``/``_split_skill_md`` không còn tồn tại trong app.routers.skills
-> ImportError -> HTTP 500 mỗi lần chatbot đồng bộ.
"""

import hashlib
import time
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import jwt
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.database import get_db
from app.routers import org_sync, skills
from app.routers.org_sync import SKILL_SYNC_AUDIENCE, SYNC_AUDIENCE
from app.routers.sso import CHATBOT_TICKET_ISSUER

SECRET = "x" * 40
SKILL_MD = (
    '---\nname: tom_tat\ndescription: "Tóm tắt văn bản hành chính"\n---\n\n'
    "# KN2 - Tóm tắt văn bản (`tom_tat`)\n\nQuy trình tóm tắt...\n"
)
UPDATED = datetime(2026, 10, 18, 8, 30, tzinfo=timezone.utc)


def _skill(slug, text=SKILL_MD, storage_path="skills/x/", **kw):
    base = dict(
        id=uuid.uuid4(), slug=slug, name=slug, storage_path=storage_path, is_system=False,
        current_version=2, updated_at=UPDATED, status="active", scope_type="global", _text=text,
    )
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.fixture
def fake_storage(monkeypatch):
    """Thay phần đọc MinIO: trả SKILL.md gắn sẵn trên kỹ năng giả; ``_text`` là Exception thì ném ra."""

    async def _read_skill_md(skill):
        if isinstance(skill._text, Exception):
            raise skill._text
        return ("SKILL.md" if skill._text else None), skill._text, []

    monkeypatch.setattr(skills, "_read_skill_md", _read_skill_md)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class FakeDB:
    def __init__(self, rows):
        self.rows = rows

    async def execute(self, _stmt):
        return _Result(self.rows)


def _token(body: bytes, audience=SKILL_SYNC_AUDIENCE, secret=SECRET) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "iss": CHATBOT_TICKET_ISSUER,
            "aud": audience,
            "iat": now,
            "exp": now + 60,
            "jti": uuid.uuid4().hex,
            "body_sha256": hashlib.sha256(body).hexdigest(),
        },
        secret,
        algorithm="HS256",
    )


async def _post(rows, token):
    app = FastAPI()
    app.include_router(org_sync.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: FakeDB(rows)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        return await ac.post(
            "/api/internal/skill-sync",
            content=b"{}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )


# ---------------------------------------------------------------- helper


async def test_items_strip_frontmatter_and_keep_chatbot_fields(fake_storage):
    items = await org_sync._skill_sync_items([_skill("tom_tat", is_system=True)])
    assert items == [
        {
            "slug": "tom_tat",
            "name": "tom_tat",
            "description": "Tóm tắt văn bản hành chính",
            "content": "# KN2 - Tóm tắt văn bản (`tom_tat`)\n\nQuy trình tóm tắt...",
            "is_system": True,
            "version": 2,
            "updated_at": "2026-10-18T08:30:00+00:00",
        }
    ]


async def test_items_without_frontmatter_keep_whole_body(fake_storage):
    items = await org_sync._skill_sync_items([_skill("tra_cuu", text="# Tra cứu\n\nNội dung.\n")])
    assert items[0]["description"] == ""
    assert items[0]["content"] == "# Tra cứu\n\nNội dung."


async def test_items_skip_broken_skills_but_keep_the_rest(fake_storage):
    rows = [
        _skill("chua_co_noi_dung", storage_path=None),
        _skill("kho_loi", text=RuntimeError("minio down")),
        _skill("thieu_skill_md", text=""),
        _skill("chi_frontmatter", text="---\nname: a\n---\n"),
        _skill("ok"),
    ]
    items = await org_sync._skill_sync_items(rows)
    assert [i["slug"] for i in items] == ["ok"]
    # Chatbot chỉ nhận mục có slug và content: mọi mục trả về đều qua được bộ lọc đó.
    assert all(i.get("slug") and i.get("content") for i in items)


# ---------------------------------------------------------------- endpoint


@pytest.fixture
def sync_secret(monkeypatch):
    monkeypatch.setattr(org_sync, "settings", SimpleNamespace(chatbot_wiki_sso_secret=SECRET))


async def test_endpoint_returns_global_skills(fake_storage, sync_secret):
    resp = await _post([_skill("tom_tat"), _skill("soan_thao", text="# Soạn thảo\n\nMẫu.\n")], _token(b"{}"))
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert [i["slug"] for i in data["items"]] == ["tom_tat", "soan_thao"]
    assert data["items"][0]["content"].startswith("# KN2 - Tóm tắt văn bản")
    assert data["items"][1] == {
        "slug": "soan_thao", "name": "soan_thao", "description": "", "content": "# Soạn thảo\n\nMẫu.",
        "is_system": False, "version": 2, "updated_at": "2026-10-18T08:30:00+00:00",
    }


async def test_endpoint_rejects_org_sync_audience(fake_storage, sync_secret):
    resp = await _post([_skill("tom_tat")], _token(b"{}", audience=SYNC_AUDIENCE))
    assert resp.status_code == 401


async def test_endpoint_rejects_body_mismatch(fake_storage, sync_secret):
    resp = await _post([_skill("tom_tat")], _token(b'{"other": 1}'))
    assert resp.status_code == 401
