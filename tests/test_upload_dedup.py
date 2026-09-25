import io
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException, UploadFile

from app.routers.sources import upload_source


@pytest.mark.asyncio
async def test_upload_source_detects_duplicate_content_hash():
    """Verify that uploading a file with an already existing content_hash returns HTTP 409."""
    file_content = b"PDF dummy content for hash test"
    file_mock = UploadFile(filename="test.pdf", file=io.BytesIO(file_content))

    mock_user = MagicMock()
    mock_user.id = uuid.uuid4()
    mock_user.role = "admin"
    mock_user.department_ids = []

    mock_db = AsyncMock()
    mock_existing_source = MagicMock()
    mock_existing_source.id = uuid.uuid4()
    mock_existing_source.title = "Tài liệu gốc"

    # Simulate existing source found with same hash
    mock_scalars = MagicMock()
    mock_scalars.first.return_value = mock_existing_source
    mock_exec = MagicMock()
    mock_exec.scalars.return_value = mock_scalars
    mock_db.execute.return_value = mock_exec

    with pytest.raises(HTTPException) as exc_info:
        await upload_source(
            file=file_mock,
            title="Tài liệu trùng",
            knowledge_type_id=None,
            department_ids=None,
            scope_type="global",
            scope_id=None,
            preserve_verbatim=False,
            db=mock_db,
            user=mock_user,
        )

    assert exc_info.value.status_code == 409
    assert "đã tồn tại trên hệ thống" in exc_info.value.detail
