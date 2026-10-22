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

    async def execute(self, _query):
        # File-token resolution now eager-loads department memberships before policy checks.
        return SimpleNamespace(scalar_one_or_none=lambda: self.employee)


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


def test_session_wiki_deadline_is_capped_by_parent():
    import time

    deadline = int(time.time()) + 300
    token = auth_service.create_access_token(
        str(uuid.uuid4()), "employee", "A", auth_source="chatbot",
        parent={"proof": "opaque-parent-proof", "sub": "chatbot-user", "exp": deadline},
    )
    claims = auth_service.decode_access_token(token)
    assert claims["exp"] == deadline
    assert claims["session_version"] == 2
    assert claims["auth_source"] == "chatbot"
    assert claims["parent"]["proof"] == "opaque-parent-proof"


def test_session_legacy_unbound_token_is_rejected(monkeypatch):
    import time
    import jwt
    from app.config import settings

    person = _employee()

    async def fake_load(db, employee_id):
        return person

    monkeypatch.setattr(auth_service, "_load_employee", fake_load)
    legacy = jwt.encode({"sub": str(person.id), "exp": int(time.time()) + 600}, settings.secret_key, algorithm="HS256")
    with pytest.raises(HTTPException) as exc:
        _run(auth_service.employee_from_bearer(_FakeDb(), legacy))
    assert exc.value.status_code == 401


@pytest.mark.parametrize("parent", [None, {}, {"proof": "opaque", "sub": "p", "exp": 1}, {"sub": "p", "exp": 9999999999}])
def test_session_invalid_parent_never_mints_unbound_sso_token(parent):
    with pytest.raises(ValueError):
        auth_service.create_access_token(str(uuid.uuid4()), "employee", "A", auth_source="chatbot", parent=parent)


@pytest.mark.parametrize("status,body,expected", [
    (200, {"active": False}, 401),
    (200, {"active": True, "user_id": "someone-else", "expires_at": 9999999999}, 401),
    (401, {}, 401),
    (503, {}, 503),
    (200, {"active": "true"}, 503),
])
def test_session_parent_verification_denies_revoked_mismatch_or_unavailable(monkeypatch, status, body, expected):
    import time
    import httpx
    from app.services import sso_session_service as sessions
    from app.config import settings

    monkeypatch.setattr(settings, "chatbot_internal_url", "http://chatbot.internal:8080")
    deadline = int(time.time()) + 300
    claims = {"session_version": 2, "auth_source": "chatbot", "exp": deadline,
              "parent": {"proof": "opaque", "sub": "parent-user", "exp": deadline}}
    original = httpx.AsyncClient

    def handler(request):
        assert str(request.url) == "http://chatbot.internal:8080/api/v1/arkon/sso/session"
        assert request.method == "POST"
        assert json.loads(request.content) == {"proof": "opaque"}
        return httpx.Response(status, json=body)

    monkeypatch.setattr(sessions.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    with pytest.raises(HTTPException) as exc:
        _run(sessions.validate_session_claims(claims))
    assert exc.value.status_code == expected


def test_session_valid_parent_checked_on_each_api_request_and_file_capability(monkeypatch):
    import time
    import httpx
    from app.services import sso_session_service as sessions
    from app.config import settings

    monkeypatch.setattr(settings, "chatbot_internal_url", "http://chatbot.internal:8080")
    person, source_id = _employee(), uuid.uuid4()
    deadline = int(time.time()) + 300
    requests = []
    alive = [True]
    original = httpx.AsyncClient

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"active": alive[0], "user_id": "parent-user", "expires_at": deadline})

    monkeypatch.setattr(sessions.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))

    async def fake_load(db, employee_id):
        return person

    monkeypatch.setattr(auth_service, "_load_employee", fake_load)
    token = auth_service.create_access_token(str(person.id), "employee", "A", auth_source="chatbot",
                                           parent={"proof": "opaque", "sub": "parent-user", "exp": deadline})
    for _ in range(2):
        assert _run(auth_service.employee_from_bearer(_FakeDb(), token)) is person
    assert len(requests) == 2  # No success cache can preserve access after a revocation.
    file_token = auth_service.create_source_file_token(str(person.id), str(source_id), session_claims=person._wiki_session_claims)
    file_claims = auth_service.decode_source_file_claims(file_token, str(source_id))
    assert file_claims["exp"] <= deadline
    alive[0] = False
    for invoke in (
        lambda: auth_service.employee_from_bearer(_FakeDb(), token),
        lambda: sources._authenticate_request_user(file_token, None, _FakeDb(person), source_id),
    ):
        with pytest.raises(HTTPException) as exc:
            _run(invoke())
        assert exc.value.status_code == 401


def test_session_verifier_network_failure_denies_access_without_false_logout(monkeypatch):
    import time
    import httpx
    from app.services import sso_session_service as sessions
    from app.config import settings

    monkeypatch.setattr(settings, "chatbot_internal_url", "http://chatbot.internal:8080")
    deadline = int(time.time()) + 300
    claims = {"session_version": 2, "auth_source": "chatbot", "exp": deadline,
              "parent": {"proof": "opaque", "sub": "parent-user", "exp": deadline}}
    original = httpx.AsyncClient

    def handler(request):
        raise httpx.ConnectError("offline", request=request)

    monkeypatch.setattr(sessions.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    with pytest.raises(HTTPException) as exc:
        _run(sessions.validate_session_claims(claims))
    assert exc.value.status_code == 503


@pytest.mark.parametrize("status,body,expected", [
    (200, {"active": True}, None),
    (200, {"active": False}, 401),
    (200, {"active": True, "sub": "other-user"}, 401),
    (401, {"error": "invalid_client"}, 503),
    (503, {}, 503),
])
def test_session_oidc_parent_is_encrypted_capped_and_introspected(monkeypatch, status, body, expected):
    import time
    import httpx
    from app.services import sso_session_service as sessions
    from app.config import settings

    deadline = int(time.time()) + 300
    monkeypatch.setattr(settings, "sso_client_id", "wiki-client")
    monkeypatch.setattr(settings, "sso_client_secret", "test-client-secret")
    parent = sessions.oidc_parent("private-oidc-access-token", {"sub": "oidc-user", "exp": deadline})
    assert "private-oidc-access-token" not in parent["proof"]
    token = auth_service.create_access_token(str(uuid.uuid4()), "employee", "A", auth_source="oidc", parent=parent)
    claims = auth_service.decode_access_token(token)
    assert claims["exp"] == deadline
    original = httpx.AsyncClient
    calls = []

    async def endpoints():
        return SimpleNamespace(introspection="https://idp.internal/introspect")

    def handler(request):
        calls.append(request)
        assert str(request.url) == "https://idp.internal/introspect"
        assert request.content == b"token=private-oidc-access-token"
        assert request.headers["authorization"].startswith("Basic ")
        return httpx.Response(status, json={"sub": "oidc-user", "exp": deadline, **body})

    monkeypatch.setattr(sso, "_endpoints", endpoints)
    monkeypatch.setattr(sessions.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    if expected is None:
        _run(sessions.validate_session_claims(claims))
        _run(sessions.validate_session_claims(claims))
        assert len(calls) == 2
    else:
        with pytest.raises(HTTPException) as exc:
            _run(sessions.validate_session_claims(claims))
        assert exc.value.status_code == expected


def test_session_oidc_bad_discovery_is_unavailable_not_logout(monkeypatch):
    import time
    from app.services import sso_session_service as sessions
    from app.config import settings

    monkeypatch.setattr(settings, "sso_client_secret", "test-client-secret")
    deadline = int(time.time()) + 300
    parent = sessions.oidc_parent("private-access-token", {"sub": "oidc-user", "exp": deadline})

    async def endpoints():
        raise KeyError("introspection_endpoint")

    monkeypatch.setattr(sso, "_endpoints", endpoints)
    with pytest.raises(HTTPException) as exc:
        _run(sessions.validate_session_claims({"session_version": 2, "auth_source": "oidc", "exp": deadline, "parent": parent}))
    assert exc.value.status_code == 503


@pytest.mark.parametrize("deadline", [True, "9999999999", 9999999999.5, float("inf"), 1])
def test_session_invalid_deadline_never_mints_sso_token(deadline):
    with pytest.raises(ValueError):
        auth_service.create_access_token(str(uuid.uuid4()), "employee", "A", auth_source="chatbot",
                                        parent={"proof": "opaque", "sub": "p", "exp": deadline})


@pytest.mark.parametrize("bound", [False, True])
def test_session_chatbot_callback_requires_binding_and_preserves_parent_deadline(monkeypatch, bound):
    import time
    import jwt
    from urllib.parse import parse_qs, urlsplit
    from starlette.requests import Request
    from app.config import settings

    monkeypatch.setattr(settings, "chatbot_url", "https://chatbot.test")
    monkeypatch.setattr(settings, "chatbot_wiki_sso_secret", "shared-test-secret-that-is-over-32-characters")
    monkeypatch.setattr(settings, "portal_base_url", "https://wiki.test")
    monkeypatch.setattr(sso, "_read_tx", lambda request: {"st": "test-state", "src": "chatbot", "nx": "/wiki"})
    person = SimpleNamespace(id=uuid.uuid4(), role="employee", name="A")
    provisioned = []

    async def provision(*args, **kwargs):
        provisioned.append(True)
        return person

    monkeypatch.setattr(sso, "_provision", provision)
    now = int(time.time())
    claims = {"iss": sso.CHATBOT_TICKET_ISSUER, "aud": sso.CHATBOT_TICKET_AUDIENCE,
              "sub": "chatbot-user", "st": "test-state", "iat": now, "exp": now + 60}
    if bound:
        claims.update(session_proof="opaque-proof", session_expires_at=now + 120)
    ticket = jwt.encode(claims, settings.chatbot_wiki_sso_secret, algorithm="HS256")
    response = _run(sso.chatbot_callback(Request({"type": "http", "scheme": "https", "server": ("wiki.test", 443),
                                                 "headers": [], "path": "/api/auth/sso/chatbot/callback"}),
                                       ticket=ticket, error=None, db=_FakeDb()))
    location = urlsplit(response.headers["location"])
    if bound:
        token = parse_qs(location.fragment)["token"][0]
        result = auth_service.decode_access_token(token)
        assert result["auth_source"] == "chatbot"
        assert result["exp"] == now + 120
        assert result["parent"] == {"proof": "opaque-proof", "sub": "chatbot-user", "exp": now + 120}
        assert provisioned == [True]
    else:
        assert parse_qs(location.query)["error"] == ["sso_token"]
        assert provisioned == []
