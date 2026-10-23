"""Real multipart/form validation with isolated auth, storage and repository boundaries."""
import inspect
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import sources as src


@pytest.mark.parametrize('label,scope,permissions,expected', [
    (None, 'personal', ['doc:create:all'], 200),
    ('', 'personal', ['doc:create:all'], 200),
    ('  ', 'personal', ['doc:create:all'], 200),
    ('PUBLIC', 'personal', ['doc:create:all'], 200),
    ('INTERNAL', 'personal', ['doc:create:all'], 403),
    ('RESTRICTED', 'personal', ['doc:create:all'], 403),
    ('CONFIDENTIAL', 'personal', ['doc:create:all'], 403),
    ('PUBLIC', 'global', ['doc:create:own_dept'], 403),
    ('PUBLIC', 'personal', ['doc:create:own_dept'], 200),
    ('PUBLIC', 'department', ['doc:create:all'], 400),
])
def test_public_multipart_upload_keeps_label_and_actor_at_repository_boundary(monkeypatch, label, scope, permissions, expected):
    actor = SimpleNamespace(id=uuid.uuid4(), role='employee', clearance_level='PUBLIC',
                            permissions=permissions, department_ids=[])
    monkeypatch.setattr(src, '_get_user_permissions', lambda user: set(user.permissions))
    db = AsyncMock()
    duplicate = MagicMock()
    duplicate.scalars.return_value.first.return_value = None
    db.execute.return_value = duplicate
    saved = []

    async def create(source):
        source.id = uuid.uuid4()
        saved.append(source)
        return source

    repository = SimpleNamespace(create=AsyncMock(side_effect=create))
    storage = AsyncMock()
    monkeypatch.setattr(src, 'Repository', lambda _: repository)
    monkeypatch.setattr(src, 'log_audit', AsyncMock())
    monkeypatch.setattr(src, '_enqueue', AsyncMock(return_value=SimpleNamespace(job_id='isolated-job')))
    monkeypatch.setattr(src, '_reload', AsyncMock(side_effect=lambda *_: saved[0]))
    monkeypatch.setattr(src, '_to_response', lambda source: {'security_label': source.security_label, 'scope_id': str(source.scope_id)})
    monkeypatch.setattr('app.services.storage_service.storage_service.upload_stream_async', storage)
    app = FastAPI()
    app.post('/sources/upload')(src.upload_source)
    dependency = inspect.signature(src.upload_source).parameters['user'].default.dependency
    app.dependency_overrides[dependency] = lambda: actor
    app.dependency_overrides[src.get_db] = lambda: db
    data = {'scope_type': scope}
    if label is not None:
        data['security_label'] = label
    response = TestClient(app).post('/sources/upload', data=data,
                                    files={'file': ('label-check.txt', b'Synthetic non-sensitive test content', 'text/plain')})
    if expected != 200:
        assert response.status_code == expected
        assert not saved
        storage.assert_not_awaited()
    else:
        assert response.status_code == 200
        assert response.json() == {'security_label': 'PUBLIC', 'scope_id': str(actor.id)}
        assert saved[0].security_label == 'PUBLIC'
        assert saved[0].contributed_by_employee_id == actor.id
        storage.assert_awaited_once()


@pytest.mark.parametrize('scope,status', [('global', 403), ('department', 400)])
def test_url_creation_enforces_the_same_scope_guards(monkeypatch, scope, status):
    actor = SimpleNamespace(id=uuid.uuid4(), role='employee', clearance_level='PUBLIC',
                            permissions=['doc:create:own_dept'], department_ids=[])
    monkeypatch.setattr(src, '_get_user_permissions', lambda user: set(user.permissions))
    repository = MagicMock()
    monkeypatch.setattr(src, 'Repository', repository)
    app = FastAPI()
    app.post('/sources/url')(src.create_url_source)
    dependency = inspect.signature(src.create_url_source).parameters['user'].default.dependency
    app.dependency_overrides[dependency] = lambda: actor
    app.dependency_overrides[src.get_db] = lambda: AsyncMock()
    response = TestClient(app).post('/sources/url', json={
        'url': 'https://example.test/synthetic', 'scope_type': scope, 'security_label': 'PUBLIC'
    })
    assert response.status_code == status
    repository.assert_not_called()
