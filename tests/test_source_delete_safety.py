"""Deleting a source must not relax ACL while derived text still contains it."""
import types
import uuid
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException


@pytest.mark.asyncio
@pytest.mark.parametrize('origin', ['generated', 'extracted'])
async def test_shared_source_delete_is_rejected_before_any_side_effect(monkeypatch, origin):
    from app.routers import sources
    from app.services import embedding_storage, storage_service, wiki_service

    sid, other = uuid.uuid4(), uuid.uuid4()
    source = types.SimpleNamespace(id=sid, scope_type='global', scope_id=None, title='Restricted', file_name=None)
    linked = types.SimpleNamespace(id=uuid.uuid4(), slug='shared', title='Shared',
                                  source_ids=[sid, other], origin_tag=origin)
    db = types.SimpleNamespace(get=AsyncMock(return_value=source),
        execute=AsyncMock(return_value=types.SimpleNamespace(all=lambda: [linked])),
        delete=AsyncMock(), commit=AsyncMock())
    delete_storage = Mock()
    detach = AsyncMock()
    monkeypatch.setattr(sources, 'can_access_document', AsyncMock(return_value=True))
    monkeypatch.setattr(sources, 'log_audit', AsyncMock())
    monkeypatch.setattr(sources, '_enqueue', AsyncMock())
    monkeypatch.setattr(embedding_storage, 'delete_source_chunk_embeddings', AsyncMock())
    monkeypatch.setattr(storage_service.storage_service, 'delete_prefix', delete_storage)
    monkeypatch.setattr(wiki_service, 'detach_source_from_wiki', detach)
    monkeypatch.setattr(wiki_service, 'regenerate_index', AsyncMock())
    with pytest.raises(HTTPException) as error:
        await sources.delete_source(sid, db=db, user=types.SimpleNamespace(id=uuid.uuid4(), role='admin'))
    assert error.value.status_code == 409
    delete_storage.assert_not_called()
    detach.assert_not_awaited()
    db.delete.assert_not_awaited()
    db.commit.assert_not_awaited()
