import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
import pymupdf as fitz
from app.main import app
from app.database import get_db

async def mock_get_db():
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result
    yield mock_db

@pytest.fixture(autouse=True)
def override_db():
    app.dependency_overrides[get_db] = mock_get_db
    yield
    app.dependency_overrides.pop(get_db, None)

def _make_pdf_bytes():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Hello PDF Test Page")
    b = doc.tobytes()
    doc.close()
    return b

@pytest.mark.asyncio
async def test_test_ocr_connection_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with patch("app.services.ocr_service.ocr_service.test_connection", new_callable=AsyncMock) as mock_test:
            mock_test.return_value = (True, "Connection OK", 120)
            resp = await ac.post("/api/settings/test-ocr-connection", json={
                "base_url": "https://ocr.example.com/v1",
                "api_key": "test-key",
                "model": "ocr-model"
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert data["message"] == "Connection OK"
            assert data["latency_ms"] == 120

@pytest.mark.asyncio
async def test_test_ocr_endpoint_with_image():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with patch("app.services.ocr_service.ocr_service.ocr_image", new_callable=AsyncMock) as mock_ocr:
            mock_ocr.return_value = "Extracted OCR text"
            files = {"file": ("test.png", b"fake-png-bytes", "image/png")}
            resp = await ac.post("/api/settings/test-ocr", files=files)
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert data["text"] == "Extracted OCR text"
            assert data["chars_count"] == len("Extracted OCR text")

@pytest.mark.asyncio
async def test_test_extraction_endpoint_with_pdf():
    pdf_bytes = _make_pdf_bytes()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        files = {"file": ("sample.pdf", pdf_bytes, "application/pdf")}
        resp = await ac.post("/api/settings/test-extraction", files=files, data={"max_pages": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["file_name"] == "sample.pdf"
        assert len(data["pages"]) == 1
        assert "stats" in data
        assert data["stats"]["total_pages"] >= 1
