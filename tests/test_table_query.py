import openpyxl
import pytest
from pathlib import Path

from app.services.table_query_service import TableQueryService


@pytest.fixture
def excel_pccc_file(tmp_path: Path) -> Path:
    """Create sample Excel file for DuckDB SQL querying."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "can_bo"
    ws.append(["id", "name", "rank", "position", "unit"])
    ws.append([1, "Nguyễn Văn A", "Đại úy", "Đội trưởng", "Đội 1"])
    ws.append([2, "Trần Thị B", "Thượng úy", "Cán bộ", "Đội 1"])
    ws.append([3, "Lê Văn C", "Trung úy", "Cán bộ", "Đội 2"])

    file_path = tmp_path / "can_bo_pccc.xlsx"
    wb.save(file_path)
    return file_path


def test_table_query_select_success(excel_pccc_file: Path):
    """Verify executing safe SELECT query on Excel table using DuckDB."""
    service = TableQueryService()
    result = service.query_excel(
        file_path=excel_pccc_file,
        sql_query="SELECT name, rank, position FROM can_bo WHERE unit = 'Đội 1' ORDER BY id ASC",
    )

    assert result["success"] is True
    assert result["row_count"] == 2
    assert result["columns"] == ["name", "rank", "position"]
    assert result["rows"][0]["name"] == "Nguyễn Văn A"
    assert result["rows"][1]["name"] == "Trần Thị B"


def test_table_query_blocks_harmful_sql(excel_pccc_file: Path):
    """Verify destructive SQL statements are blocked immediately."""
    service = TableQueryService()
    
    harmful_queries = [
        "DROP TABLE can_bo",
        "DELETE FROM can_bo WHERE id = 1",
        "UPDATE can_bo SET rank = 'Đại tá'",
        "INSERT INTO can_bo VALUES (4, 'X', 'Y', 'Z', 'W')",
        "COPY can_bo TO 'secret.csv'",
        "ATTACH 'db.duckdb' AS remote",
    ]

    for sql in harmful_queries:
        result = service.query_excel(file_path=excel_pccc_file, sql_query=sql)
        assert result["success"] is False
        assert "Chỉ cho phép truy vấn đọc dữ liệu" in result["error"] or "blocked" in result["error"].lower()


def test_table_query_row_limit(excel_pccc_file: Path):
    """Verify query result respects max_rows constraint."""
    service = TableQueryService()
    result = service.query_excel(
        file_path=excel_pccc_file,
        sql_query="SELECT * FROM can_bo",
        max_rows=1,
    )

    assert result["success"] is True
    assert result["row_count"] == 1
    assert len(result["rows"]) == 1


def test_table_query_bytes_success(excel_pccc_file: Path):
    """Verify executing SQL query on in-memory Excel bytes."""
    service = TableQueryService()
    bytes_data = excel_pccc_file.read_bytes()

    result = service.query_excel_bytes(
        file_bytes=bytes_data,
        file_name="can_bo.xlsx",
        sql_query="SELECT name FROM can_bo WHERE id = 1",
    )

    assert result["success"] is True
    assert result["row_count"] == 1
    assert result["rows"][0]["name"] == "Nguyễn Văn A"


@pytest.mark.asyncio
async def test_mcp_query_table_tool(excel_pccc_file: Path):
    """Verify MCP query_table tool execution."""
    import uuid
    from unittest.mock import AsyncMock, patch, MagicMock
    from app.database.models import Source
    from app.mcp.tools import register_tools
    from fastmcp import FastMCP

    mcp = FastMCP("test-kb")
    register_tools(mcp)

    # Find the registered tool
    query_table_tool = None
    for tool in await mcp.list_tools():
        if tool.name == "query_table":
            query_table_tool = tool
            break

    assert query_table_tool is not None

    source_id = uuid.uuid4()
    mock_source = Source(
        id=source_id,
        file_name="can_bo_pccc.xlsx",
        minio_key="sources/can_bo_pccc.xlsx",
    )

    mock_identity = MagicMock()
    mock_identity.is_admin = True
    mock_identity.allowed_knowledge_types = []
    mock_identity.department_ids = []

    bytes_data = excel_pccc_file.read_bytes()

    with patch("app.mcp.tools._get_identity", new_callable=AsyncMock) as mock_get_id, \
         patch("app.services.storage_service.storage_service.download_file") as mock_dl, \
         patch("app.database.async_session_factory") as mock_session_factory:

        mock_get_id.return_value = (mock_identity, None)
        mock_dl.return_value = bytes_data

        mock_session = AsyncMock()
        mock_session.get.return_value = mock_source
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        # Call tool via FastMCP
        result_str = await mcp.call_tool(
            "query_table",
            {"source_id": str(source_id), "sql_query": "SELECT name, rank FROM can_bo WHERE id = 1"},
        )
        output_text = result_str[0].text if isinstance(result_str, list) else str(result_str)

        assert "Nguyễn Văn A" in output_text
        assert "Đại úy" in output_text

