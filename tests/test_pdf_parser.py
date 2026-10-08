import pytest
import fitz
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.parsers.pdf_parser import (
    PDFParser,
    strip_repeated_headers_and_footers,
    enhance_vietnamese_headings,
    is_scanned_page,
)


def test_strip_repeated_headers_and_footers():
    """Verify that repeated headers (e.g. motto) and footers (page numbers) across pages are stripped."""
    pages = [
        "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\nĐộc lập - Tự do - Hạnh phúc\nNội dung trang 1\nTrang 1 / 3",
        "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\nĐộc lập - Tự do - Hạnh phúc\nNội dung trang 2\nTrang 2 / 3",
        "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\nĐộc lập - Tự do - Hạnh phúc\nNội dung trang 3\nTrang 3 / 3",
    ]

    cleaned = strip_repeated_headers_and_footers(pages)
    assert len(cleaned) == 3
    # Header should be removed from all pages
    for page_text in cleaned:
        assert "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM" not in page_text
        assert "Độc lập - Tự do - Hạnh phúc" not in page_text
    
    # Body text must remain
    assert "Nội dung trang 1" in cleaned[0]
    assert "Nội dung trang 2" in cleaned[1]
    assert "Nội dung trang 3" in cleaned[2]


def test_enhance_vietnamese_headings():
    """Verify that Vietnamese legal structure keywords without markdown headings get enhanced."""
    raw = (
        "CHƯƠNG I\n"
        "QUY ĐỊNH CHUNG\n\n"
        "Điều 1. Phạm vi điều chỉnh\n"
        "Nghị định này quy định về...\n\n"
        "Điều 2. Đối tượng áp dụng\n"
        "Cơ quan, tổ chức, cá nhân...\n\n"
        "# Điều 3. Đã có heading\n"
        "Không được thêm hashtag vào dòng này."
    )

    enhanced = enhance_vietnamese_headings(raw)

    assert "## CHƯƠNG I" in enhanced
    assert "### Điều 1. Phạm vi điều chỉnh" in enhanced
    assert "### Điều 2. Đối tượng áp dụng" in enhanced
    # Already heading line should NOT be double-tagged
    assert "## # Điều 3" not in enhanced
    assert "# Điều 3. Đã có heading" in enhanced


def test_is_scanned_page_detection():
    """Verify scanned page heuristic: image area > 50% of page and text length < 15 chars."""
    mock_page = MagicMock()
    mock_page.rect.width = 600
    mock_page.rect.height = 800

    # Case 1: Page has a large image (covers 70% area) and almost no text (3 chars)
    mock_img_rect = fitz.Rect(50, 50, 550, 650)  # Area: 500 * 600 = 300,000 / 480,000 = 62.5%
    mock_page.get_image_rects.return_value = [mock_img_rect]
    assert is_scanned_page(mock_page, text="abc") is True

    # Case 2: Page has plenty of text (> 50 chars) even if it has an image
    assert is_scanned_page(mock_page, text="Đây là văn bản hoàn chỉnh có độ dài lớn hơn 50 ký tự được trích xuất bằng bộ parser.") is False

    # Case 3: Page has tiny icon/logo (5% area) and 5 chars
    mock_tiny_rect = fitz.Rect(10, 10, 30, 30)  # Area: 400
    mock_page.get_image_rects.return_value = [mock_tiny_rect]
    assert is_scanned_page(mock_page, text="12345") is False


@pytest.mark.asyncio
async def test_pdf_parser_generates_markdown():
    """Verify PDFParser converts a synthetic PDF to structured markdown."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "CHAPTER I: GENERAL PROVISIONS\nArticle 1. Scope of regulation\nTesting document content here.")
    pdf_bytes = doc.tobytes()
    doc.close()

    parser = PDFParser()
    pages_data = await parser.parse(pdf_bytes, "test_doc.pdf")

    assert len(pages_data) == 1
    assert pages_data[0]["page_number"] == 1
    content = pages_data[0]["content"]
    assert "Article 1" in content


@pytest.mark.asyncio
async def test_pdf_parser_preserves_tables_and_vietnamese_headings():
    """Verify PDFParser enhances Vietnamese headings and keeps table formatting intact."""
    mock_chunks = [
        {
            "text": "Điều 1. Phạm vi điều chỉnh\n\n| STT | Tên | Số lượng |\n| --- | --- | --- |\n| 1 | Máy tính | 10 |",
            "metadata": {"page": 1},
        }
    ]
    with patch("pymupdf4llm.to_markdown", return_value=mock_chunks):
        doc = fitz.open()
        doc.new_page()
        pdf_bytes = doc.tobytes()
        doc.close()

        parser = PDFParser()
        pages = await parser.parse(pdf_bytes, "mock_table.pdf")
        assert len(pages) == 1
        assert "### Điều 1. Phạm vi điều chỉnh" in pages[0]["content"]
        assert "| STT | Tên | Số lượng |" in pages[0]["content"]

