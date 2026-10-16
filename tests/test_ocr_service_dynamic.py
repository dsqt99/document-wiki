import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.ocr_service import OCRService

@pytest.mark.asyncio
async def test_ocr_service_test_connection_success():
    svc = OCRService()
    
    with patch("openai.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_model = MagicMock()
        mock_model.id = "test-ocr-model"
        mock_client.models.list.return_value = [mock_model]
        mock_openai_cls.return_value = mock_client
        
        ok, msg, latency = await svc.test_connection(
            base_url="https://mock-ocr.example.com/v1",
            api_key="mock-key",
            model="test-ocr-model"
        )
        assert ok is True
        assert "thành công" in msg.lower() or "connected" in msg.lower() or "ok" in msg.lower()
        assert latency >= 0

@pytest.mark.asyncio
async def test_ocr_service_test_connection_failure():
    svc = OCRService()
    
    with patch("openai.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_client.models.list.side_effect = Exception("Connection refused")
        mock_client.chat.completions.create.side_effect = Exception("Connection refused")
        mock_openai_cls.return_value = mock_client
        
        ok, msg, latency = await svc.test_connection(
            base_url="https://bad-ocr.example.com/v1",
            api_key="mock-key",
            model="test-ocr-model"
        )
        assert ok is False
        assert "Connection refused" in msg

@pytest.mark.asyncio
async def test_ocr_service_override_params():
    svc = OCRService()
    
    with patch.object(svc, "_call_ocr_stream_sync", return_value="# Output text") as mock_sync:
        res = await svc.ocr_image(
            image_bytes=b"fake-image-bytes",
            mime_type="image/jpeg",
            prompt="Custom test prompt",
            base_url="https://custom-url/v1",
            api_key="custom-key",
            model="custom-model",
        )
        assert res == "# Output text"
        assert mock_sync.called
