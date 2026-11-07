"""Wiki images are served same-origin through the API, never as MinIO presigned links."""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def _image():
    source = SimpleNamespace(id=uuid.uuid4())
    return SimpleNamespace(id=uuid.uuid4(), source=source, source_id=source.id,
                           minio_key="sources/x/images/docx_0.png", content_type="image/png")


def _db(result):
    db = AsyncMock()
    rows = MagicMock()
    rows.scalars.return_value.all.return_value = result
    rows.scalar_one_or_none.return_value = result
    db.execute.return_value = rows
    return db


@pytest.mark.asyncio
async def test_resolve_returns_same_origin_url():
    from app.routers import wiki_images
    image = _image()
    user = SimpleNamespace(id=uuid.uuid4())
    with patch.object(wiki_images, "can_access_document", AsyncMock(return_value=True)), \
         patch.object(wiki_images, "create_source_file_token", return_value="tok"):
        out = await wiki_images.resolve_wiki_images(wiki_images.ResolveRequest(ids=[image.id]), _db([image]), user)
    assert out["resolved"][str(image.id)] == f"/api/wiki/images/{image.id}?token=tok"


@pytest.mark.asyncio
async def test_get_image_streams_bytes_and_enforces_access():
    from app.routers import wiki_images
    from app.services import storage_service
    image = _image()
    storage = SimpleNamespace(download_file=lambda key: b"PNG")
    with patch("app.routers.sources._authenticate_request_user", AsyncMock(return_value=object())), \
         patch.object(storage_service, "storage_service", storage), \
         patch.object(wiki_images, "can_access_document", AsyncMock(return_value=True)):
        resp = await wiki_images.get_wiki_image(image.id, "tok", None, _db(image))
    assert resp.body == b"PNG" and resp.media_type == "image/png"
    with patch("app.routers.sources._authenticate_request_user", AsyncMock(return_value=object())), \
         patch.object(wiki_images, "can_access_document", AsyncMock(return_value=False)):
        with pytest.raises(HTTPException) as err:
            await wiki_images.get_wiki_image(image.id, "tok", None, _db(image))
    assert err.value.status_code == 403
