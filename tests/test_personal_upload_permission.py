import io
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, UploadFile

from app.routers.sources import upload_source

READER = {"doc:read:own_dept", "wiki:read:own_dept", "skill:read:own_dept"}


def _reader():
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = "employee"
    user.department_ids = []
    user.clearance_level = "INTERNAL"
    return user


def _dup_db():
    db = AsyncMock()
    existing = MagicMock(id=uuid.uuid4(), title="x")
    result = MagicMock()
    result.scalars.return_value.first.return_value = existing
    db.execute.return_value = result
    return db


async def _upload(scope):
    return await upload_source(
        file=UploadFile(filename="a.pdf", file=io.BytesIO(b"%PDF-1.4 x")),
        title=None, knowledge_type_id=None, department_ids=None, managing_department_id=None,
        scope_type=scope, scope_id=None, preserve_verbatim=False, processing_mode=None,
        security_label=None, review_before_processing=False, db=_dup_db(), user=_reader(),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["department", "global", None])
async def test_reader_cannot_upload_shared_scope(scope):
    with patch("app.routers.sources._get_user_permissions", return_value=READER):
        with pytest.raises(HTTPException) as exc:
            await _upload(scope)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_reader_passes_gate_for_personal_scope():
    # Reaching the duplicate check (409) proves the doc:create gate was skipped.
    with patch("app.routers.sources._get_user_permissions", return_value=READER):
        with pytest.raises(HTTPException) as exc:
            await _upload("personal")
    assert exc.value.status_code == 409
