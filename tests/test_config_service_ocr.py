import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.config_service import (
    ALL_CONFIG_KEYS,
    _is_sensitive,
    ConfigService,
)

def test_ocr_keys_in_all_config_keys():
    expected_keys = [
        "ocr_base_url",
        "ocr_api_key",
        "ocr_model",
        "ocr_prompt",
        "ocr_mode",
        "ocr_fallback_vision",
        "pdf_parser_engine",
        "pdf_strip_headers_footers",
        "pdf_enhance_headings",
    ]
    for key in expected_keys:
        assert key in ALL_CONFIG_KEYS, f"{key} should be in ALL_CONFIG_KEYS"

def test_ocr_api_key_is_sensitive():
    assert _is_sensitive("ocr_api_key") is True
    assert _is_sensitive("ocr_base_url") is False
    assert _is_sensitive("ocr_model") is False

@pytest.mark.asyncio
async def test_config_service_defaults_and_fallbacks():
    mock_db = AsyncMock()
    # Mock no DB record found
    mock_exec_result = MagicMock()
    mock_exec_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_exec_result

    svc = ConfigService(mock_db)
    
    # Should fallback to env/settings or sensible default
    mode = await svc.get("ocr_mode")
    assert mode in ("auto", "force_ocr", "disabled")

    engine = await svc.get("pdf_parser_engine")
    assert engine in ("pymupdf4llm", "pymupdf_plain")

    prompt = await svc.get("ocr_prompt")
    assert prompt is not None and len(prompt) > 20
