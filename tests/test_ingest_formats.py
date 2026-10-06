"""Ingest format coverage: legacy .xls and admin document-processing config."""

import io
from unittest.mock import AsyncMock, patch

import pytest

from app.services.parsers.excel_parser import ExcelParser


def _xls_bytes() -> bytes:
    xlwt = pytest.importorskip("xlwt")
    wb = xlwt.Workbook()
    ws = wb.add_sheet("DanhSach")
    for c, h in enumerate(["STT", "Họ tên", "Đơn vị"]):
        ws.write(0, c, h)
    ws.write(1, 0, 1)
    ws.write(1, 1, "Nguyễn Văn A")
    ws.write(1, 2, "Phòng PC06")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_excel_parser_reads_legacy_xls():
    pages = await ExcelParser().parse(_xls_bytes(), "danh_sach.xls")
    assert pages[0]["sheet_name"] == "DanhSach"
    content = pages[0]["content"]
    assert "Họ tên" in content
    assert "| 1 | Nguyễn Văn A | Phòng PC06 |" in content


@pytest.mark.asyncio
async def test_extract_pdf_uses_admin_doc_processing_config():
    from app.services import kb_service

    cfg = {
        "pdf_engine": "pymupdf",
        "excel_engine": "openpyxl",
        "ocr_mode": "force",
        "ocr_fallback_vision": False,
        "strip_headers_footers": False,
        "enhance_headings": True,
    }
    with patch.object(kb_service, "_load_doc_processing_config", AsyncMock(return_value=cfg)), \
         patch("app.services.parsers.pdf_parser.PDFParser.parse", AsyncMock(return_value=[])) as parse:
        await kb_service._extract_text_from_file(b"%PDF-1.4", "a.pdf")
    kw = parse.await_args.kwargs
    assert kw["engine"] == "pymupdf"
    assert kw["ocr_mode"] == "force"
    assert kw["ocr_fallback_vision"] is False
    assert kw["strip_headers_footers"] is False
