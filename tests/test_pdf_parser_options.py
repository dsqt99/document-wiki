import pytest
import pymupdf as fitz
from unittest.mock import AsyncMock, patch
from app.services.parsers.pdf_parser import PDFParser

def _create_sample_pdf(num_pages: int = 3) -> bytes:
    doc = fitz.open()
    for i in range(num_pages):
        page = doc.new_page()
        page.insert_text((50, 50), f"Section {i+1}\nArticle 1. Sample content page {i+1}")
    data = doc.tobytes()
    doc.close()
    return data

@pytest.mark.asyncio
async def test_pdf_parser_max_pages_limit():
    pdf_bytes = _create_sample_pdf(num_pages=5)
    parser = PDFParser()
    
    pages = await parser.parse(pdf_bytes, "test.pdf", max_pages=2)
    assert len(pages) == 2
    assert pages[0]["page_number"] == 1
    assert pages[1]["page_number"] == 2
    assert "is_ocr" in pages[0]
    assert "char_count" in pages[0]
    assert "word_count" in pages[0]

@pytest.mark.asyncio
async def test_pdf_parser_engine_plain():
    pdf_bytes = _create_sample_pdf(num_pages=1)
    parser = PDFParser()
    
    pages = await parser.parse(pdf_bytes, "test.pdf", engine="pymupdf_plain")
    assert len(pages) == 1
    assert "Article 1" in pages[0]["content"]

@pytest.mark.asyncio
async def test_pdf_parser_ocr_mode_disabled():
    pdf_bytes = _create_sample_pdf(num_pages=2)
    parser = PDFParser()
    
    with patch("app.services.ocr_service.ocr_service.ocr_image", new_callable=AsyncMock) as mock_ocr:
        pages = await parser.parse(pdf_bytes, "test.pdf", ocr_mode="disabled")
        assert len(pages) == 2
        assert mock_ocr.call_count == 0
        assert not pages[0]["is_ocr"]

@pytest.mark.asyncio
async def test_pdf_parser_ocr_mode_force():
    pdf_bytes = _create_sample_pdf(num_pages=2)
    parser = PDFParser()
    
    with patch("app.services.ocr_service.ocr_service.is_configured", return_value=True):
        with patch("app.services.ocr_service.ocr_service.ocr_image", new_callable=AsyncMock) as mock_ocr:
            mock_ocr.side_effect = [
                "Noi dung OCR ep buoc trang 1 doc nhat\nNoi dung them",
                "Noi dung OCR ep buoc trang 2 doc nhat\nNoi dung them",
            ]
            pages = await parser.parse(pdf_bytes, "test.pdf", ocr_mode="force_ocr")
            assert len(pages) == 2
            assert mock_ocr.call_count == 2
            assert pages[0]["is_ocr"] is True
            assert pages[1]["is_ocr"] is True
            assert "Noi dung OCR ep buoc trang 1" in pages[0]["content"]
