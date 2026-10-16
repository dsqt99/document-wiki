"""REST API nhận access token Keycloak do proxy chatbot chuyển tiếp; URL tệp không mang token phiên."""

import asyncio
import base64
import json
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.routers import sources, sso
from app.services import auth_service


def _fake_rs256_token() -> str:
    def part(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()

    return f"{part({'alg': 'RS256', 'typ': 'JWT', 'kid': 'k1'})}.{part({'sub': 'kc-1'})}.c2ln"


class _FakeDb:
    def __init__(self, employee=None):
        self.commits = 0
        self.rollbacks = 0
        self.employee = employee

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def get(self, _model, employee_id):
        if self.employee is not None and self.employee.id == employee_id:
            return self.employee
        return None


def _employee(**kw):
    return SimpleNamespace(id=kw.get("id", uuid.uuid4()), is_active=kw.get("is_active", True), global_role="viewer")


def _run(coro):
    return asyncio.run(coro)


def test_keycloak_tokens_are_told_apart_from_wiki_tokens():
    assert auth_service.is_keycloak_token(_fake_rs256_token())
    assert not auth_service.is_keycloak_token(auth_service.create_access_token(str(uuid.uuid4()), "employee", "A"))
    assert not auth_service.is_keycloak_token("not-a-jwt")


def test_keycloak_token_resolves_the_real_employee(monkeypatch):
    person = _employee()
    seen = {}

    async def fake_from_access_token(db, token):
        seen["token"] = token
        return person

    async def fake_load(db, employee_id):
        return person if employee_id == person.id else None

    monkeypatch.setattr(sso, "employee_from_access_token", fake_from_access_token)
    monkeypatch.setattr(auth_service, "_load_employee", fake_load)
    db = _FakeDb()
    token = _fake_rs256_token()

    assert _run(auth_service.employee_from_bearer(db, token)) is person
    assert seen["token"] == token
    # Tài khoản/vai trò/đơn vị vừa đồng bộ được lưu ngay.
    assert db.commits == 1


def test_rejected_keycloak_token_is_401_and_rolled_back(monkeypatch):
    async def reject(db, token):
        return "sso_client_not_allowed"

    monkeypatch.setattr(sso, "employee_from_access_token", reject)
    db = _FakeDb()
    with pytest.raises(HTTPException) as exc:
        _run(auth_service.employee_from_bearer(db, _fake_rs256_token()))
    assert exc.value.status_code == 401
    assert "sso_client_not_allowed" in exc.value.detail
    assert db.commits == 0 and db.rollbacks == 1


def test_garbage_token_never_reaches_keycloak_verification(monkeypatch):
    async def must_not_run(db, token):
        raise AssertionError("called")

    monkeypatch.setattr(sso, "employee_from_access_token", must_not_run)
    for token in ("abc", "a.b.c"):
        with pytest.raises(HTTPException) as exc:
            _run(auth_service.employee_from_bearer(_FakeDb(), token))
        assert exc.value.status_code == 401


def test_wiki_session_token_still_works_and_inactive_is_refused(monkeypatch):
    person = _employee()
    locked = _employee(is_active=False)
    people = {person.id: person, locked.id: locked}

    async def fake_load(db, employee_id):
        return people.get(employee_id)

    monkeypatch.setattr(auth_service, "_load_employee", fake_load)
    ok = auth_service.create_access_token(str(person.id), "employee", "A")
    assert _run(auth_service.employee_from_bearer(_FakeDb(), ok)) is person

    for token in (
        auth_service.create_access_token(str(locked.id), "employee", "B"),
        auth_service.create_access_token("not-a-uuid", "employee", "C"),
    ):
        with pytest.raises(HTTPException) as exc:
            _run(auth_service.employee_from_bearer(_FakeDb(), token))
        assert exc.value.status_code == 401


def test_file_url_token_opens_only_that_source_and_is_not_a_session():
    person, source_id = str(uuid.uuid4()), str(uuid.uuid4())
    token = auth_service.create_source_file_token(person, source_id)

    assert auth_service.decode_source_file_token(token, source_id) == person
    assert auth_service.decode_source_file_token(token, str(uuid.uuid4())) is None
    # Lộ URL (log proxy, lịch sử trình duyệt) không lộ phiên đăng nhập.
    assert auth_service.decode_access_token(token) is None


def test_file_endpoint_query_token_rules(monkeypatch):
    person = _employee()
    source_id = uuid.uuid4()
    db = _FakeDb(person)

    good = auth_service.create_source_file_token(str(person.id), str(source_id))
    assert _run(sources._authenticate_request_user(good, None, db, source_id)) is person

    other_source = auth_service.create_source_file_token(str(person.id), str(uuid.uuid4()))
    session = auth_service.create_access_token(str(person.id), "employee", "A")
    for token in (other_source, session):
        with pytest.raises(HTTPException) as exc:
            _run(sources._authenticate_request_user(token, None, db, source_id))
        assert exc.value.status_code == 401


def test_file_endpoint_header_uses_the_shared_bearer_check(monkeypatch):
    person = _employee()

    async def fake_bearer(db, token):
        assert token == "kc-access-token"
        return person

    monkeypatch.setattr(auth_service, "employee_from_bearer", fake_bearer)
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="kc-access-token")
    assert _run(sources._authenticate_request_user(None, creds, _FakeDb(), uuid.uuid4())) is person
