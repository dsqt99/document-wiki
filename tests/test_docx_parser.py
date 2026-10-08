import io
import pytest
from docx import Document
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls

from app.services.parsers.docx_parser import DocxParser


def create_sample_docx_with_table() -> bytes:
    """Create an in-memory docx with headings, paragraphs, and a markdown table."""
    doc = Document()
    doc.add_heading("QUY CHẾ HOẠT ĐỘNG", level=1)
    doc.add_paragraph("Điều 1. Phạm vi điều chỉnh")
    doc.add_paragraph("Nội dung quy định chi tiết.")

    # Add a table 2x2
    table = doc.add_table(rows=2, cols=2)
    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = "Họ và tên"
    hdr_cells[1].text = "Chức vụ"

    row_cells = table.rows[1].cells
    row_cells[0].text = "Nguyễn Văn A"
    row_cells[1].text = "Cán bộ"

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def create_sample_docx_with_merged_cells() -> bytes:
    """Create an in-memory docx with horizontally merged cells."""
    doc = Document()
    doc.add_paragraph("Bảng thống kê")

    table = doc.add_table(rows=3, cols=3)
    # Merge row 0 cols 1 and 2
    cell_a = table.cell(0, 1)
    cell_b = table.cell(0, 2)
    cell_a.merge(cell_b)

    table.cell(0, 0).text = "STT"
    table.cell(0, 1).text = "Thông tin chung"
    
    table.cell(1, 0).text = "1"
    table.cell(1, 1).text = "Tên: Nguyễn Văn B"
    table.cell(1, 2).text = "Tuổi: 30"

    table.cell(2, 0).text = "2"
    table.cell(2, 1).text = "Tên: Trần Thị C"
    table.cell(2, 2).text = "Tuổi: 25"

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_docx_parser_extracts_headings_and_tables():
    """Verify DocxParser extracts headings and formats tables into clean Markdown."""
    docx_bytes = create_sample_docx_with_table()
    parser = DocxParser()
    pages = await parser.parse(docx_bytes, "sample.docx")

    assert len(pages) >= 1
    content = pages[0]["content"]
    assert "QUY CHẾ HOẠT ĐỘNG" in content
    assert "### Điều 1. Phạm vi điều chỉnh" in content
    # Check table format
    assert "| Họ và tên | Chức vụ |" in content
    assert "| Nguyễn Văn A | Cán bộ |" in content


@pytest.mark.asyncio
async def test_docx_parser_handles_merged_cells():
    """Verify DocxParser preserves table structure without dropping columns when cells are merged."""
    docx_bytes = create_sample_docx_with_merged_cells()
    parser = DocxParser()
    pages = await parser.parse(docx_bytes, "merged.docx")

    assert len(pages) >= 1
    content = pages[0]["content"]
    assert "| STT |" in content
    assert "Nguyễn Văn B" in content
    assert "Trần Thị C" in content
