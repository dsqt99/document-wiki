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


@pytest.mark.asyncio
async def test_upload_source_streams_file_to_minio():
    """The upload body is streamed to MinIO from the spooled file, not buffered."""
    file_content = b"%PDF-1.4 " + b"x" * 200_000
    file_mock = UploadFile(filename="big.pdf", file=io.BytesIO(file_content))

    mock_user = MagicMock()
    mock_user.id = uuid.uuid4()
    mock_user.role = "admin"
    mock_user.department_ids = []

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    no_dup = MagicMock()
    no_dup.scalars.return_value.first.return_value = None
    loaded = MagicMock()
    mock_db.execute.side_effect = [no_dup, loaded]

    uploaded = {}

    async def _fake_upload(object_name, stream, length, content_type):
        uploaded.update(key=object_name, data=stream.read(), length=length, ct=content_type)
        return object_name

    async def _create(src):
        src.id = uuid.uuid4()
        return src

    pool = AsyncMock()
    pool.enqueue_job.return_value = MagicMock(job_id="job-1")
    with patch("app.routers.sources.Repository") as repo_cls, \
         patch("app.routers.sources.log_audit", AsyncMock()), \
         patch("app.routers.sources.get_arq_pool", AsyncMock(return_value=pool)), \
         patch("app.routers.sources._to_response", side_effect=lambda s: s), \
         patch("app.services.storage_service.storage_service.upload_stream_async", side_effect=_fake_upload):
        repo_cls.return_value.create = AsyncMock(side_effect=_create)
        await upload_source(
            file=file_mock,
            title=None,
            knowledge_type_id=None,
            department_ids=None,
            scope_type="global",
            scope_id=None,
            preserve_verbatim=False,
            db=mock_db,
            user=mock_user,
        )

    assert uploaded["data"] == file_content
    assert uploaded["length"] == len(file_content)
    assert uploaded["key"].endswith("/original/big.pdf")
    created = repo_cls.return_value.create.await_args.args[0]
    assert created.file_size == len(file_content)
    pool.enqueue_job.assert_awaited_once()
