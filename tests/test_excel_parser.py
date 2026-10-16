import io
import pytest
import openpyxl
from pathlib import Path

from app.services.parsers.excel_parser import ExcelParser


@pytest.fixture
def sample_excel_file(tmp_path: Path) -> Path:
    """Create a sample Excel workbook with 2 sheets for testing."""
    wb = openpyxl.Workbook()
    
    # Sheet 1: Danh sach can bo
    ws1 = wb.active
    ws1.title = "Cán bộ PCCC"
    ws1.append(["STT", "Họ và tên", "Cấp bậc", "Chức vụ", "Đơn vị"])
    ws1.append([1, "Nguyễn Văn A", "Đại úy", "Đội trưởng", "Đội PCCC số 1"])
    ws1.append([2, "Trần Thị B", "Thượng úy", "Cán bộ", "Đội PCCC số 1"])
    ws1.append([3, "Lê Văn C", "Trung úy", "Cán bộ", "Đội PCCC số 2"])

    # Sheet 2: Thiet bi PCCC
    ws2 = wb.create_sheet(title="Phương tiện PCCC")
    ws2.append(["Mã", "Tên phương tiện", "Số lượng", "Tình trạng"])
    ws2.append(["XE-01", "Xe chữa cháy Kamaz", 2, "Hoạt động tốt"])
    ws2.append(["XE-02", "Xe thang 32m", 1, "Bảo dưỡng định kỳ"])

    file_path = tmp_path / "test_pccc_data.xlsx"
    wb.save(file_path)
    return file_path


def test_excel_parser_extracts_metadata_and_structure(sample_excel_file: Path):
    """Verify Excel parser extracts sheet names, column headers, and row counts."""
    parser = ExcelParser()
    result = parser.parse_file(sample_excel_file)

    assert result["sheet_count"] == 2
    assert "Cán bộ PCCC" in result["sheet_names"]
    assert "Phương tiện PCCC" in result["sheet_names"]

    sheet1_info = result["sheets"]["Cán bộ PCCC"]
    assert sheet1_info["columns"] == ["STT", "Họ và tên", "Cấp bậc", "Chức vụ", "Đơn vị"]
    assert sheet1_info["row_count"] == 3


def test_excel_parser_row_wise_chunking(sample_excel_file: Path):
    """Verify row-wise structured chunking preserves column context."""
    parser = ExcelParser()
    result = parser.parse_file(sample_excel_file)

    chunks = result["chunks"]
    assert len(chunks) == 5  # 3 rows from sheet1 + 2 rows from sheet2

    first_chunk = chunks[0]
    assert "Cán bộ PCCC" in first_chunk["sheet_name"]
    assert "Nguyễn Văn A" in first_chunk["text"]
    assert "Đội trưởng" in first_chunk["text"]
    assert "Đội PCCC số 1" in first_chunk["text"]
    assert first_chunk["row_index"] == 1


def test_excel_parser_markdown_table_conversion(sample_excel_file: Path):
    """Verify generation of clean markdown tables for document full_text."""
    parser = ExcelParser()
    result = parser.parse_file(sample_excel_file)

    md = result["markdown"]
    assert "## Bảng tính: Cán bộ PCCC" in md
    assert "| STT | Họ và tên | Cấp bậc | Chức vụ | Đơn vị |" in md
    assert "| 1 | Nguyễn Văn A | Đại úy | Đội trưởng | Đội PCCC số 1 |" in md
    assert "## Bảng tính: Phương tiện PCCC" in md
    assert "Xe chữa cháy Kamaz" in md
