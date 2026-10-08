"""
Table Query Service — In-memory analytical SQL querying over spreadsheets via DuckDB.

Provides safe, sandboxed, read-only SQL execution for Excel and CSV sources.
Enforces keyword blocklists to prevent destructive or unauthorized operations.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional, Union

import duckdb
import pandas as pd
from loguru import logger

from app.core.vi_tokenizer import strip_accents

FORBIDDEN_SQL_PATTERNS = [
    r"\bDROP\b",
    r"\bDELETE\b",
    r"\bINSERT\b",
    r"\bUPDATE\b",
    r"\bALTER\b",
    r"\bTRUNCATE\b",
    r"\bCOPY\b",
    r"\bATTACH\b",
    r"\bDETACH\b",
    r"\bEXPORT\b",
    r"\bIMPORT\b",
    r"\bPRAGMA\b",
    r"\bINSTALL\b",
    r"\bLOAD\b",
    r"\bCALL\b",
    r"\bCREATE\b",
]

FORBIDDEN_RE = re.compile("|".join(FORBIDDEN_SQL_PATTERNS), re.IGNORECASE)


class TableQueryService:
    """Read-only SQL query runner for tabular files using DuckDB."""

    def __init__(self, default_max_rows: int = 100) -> None:
        self.default_max_rows = default_max_rows

    def validate_sql(self, sql_query: str) -> None:
        """Ensure SQL query is strictly read-only and free of destructive statements."""
        clean_sql = sql_query.strip()
        if not clean_sql:
            raise ValueError("Câu truy vấn SQL không được để trống.")

        # Must start with SELECT or WITH
        if not re.match(r"^(SELECT|WITH)\b", clean_sql, re.IGNORECASE):
            raise ValueError("Chỉ cho phép truy vấn đọc dữ liệu (SELECT hoặc WITH).")

        # Check for forbidden keywords
        match = FORBIDDEN_RE.search(clean_sql)
        if match:
            raise ValueError(
                f"Lệnh SQL '{match.group(0).upper()}' bị chặn vì lý do an toàn. "
                "Chỉ cho phép truy vấn đọc dữ liệu."
            )

    def query_excel_bytes(
        self,
        file_bytes: bytes,
        file_name: str,
        sql_query: str,
        max_rows: Optional[int] = None,
    ) -> dict[str, Any]:
        """Execute safe SQL query across sheets of an in-memory Excel or CSV file."""
        import tempfile

        ext = Path(file_name).suffix.lower() or ".xlsx"
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = Path(tmp.name)

        try:
            return self.query_excel(file_path=tmp_path, sql_query=sql_query, max_rows=max_rows)
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass

    def query_excel(
        self,
        file_path: Union[str, Path],
        sql_query: str,
        max_rows: Optional[int] = None,
    ) -> dict[str, Any]:
        """Execute safe SQL query across sheets of an Excel file."""
        file_path = Path(file_path)
        if not file_path.exists():
            return {
                "success": False,
                "error": f"Không tìm thấy file: {file_path}",
                "columns": [],
                "rows": [],
                "row_count": 0,
            }

        limit = max_rows or self.default_max_rows

        try:
            self.validate_sql(sql_query)
        except ValueError as e:
            return {
                "success": False,
                "error": str(e),
                "columns": [],
                "rows": [],
                "row_count": 0,
            }

        conn = duckdb.connect(database=":memory:", read_only=False)

        try:
            # Read all sheets into pandas
            excel_data = pd.read_excel(file_path, sheet_name=None)

            # Register each sheet in DuckDB
            for sheet_name, df in excel_data.items():
                # Clean column names in dataframe
                df.columns = [
                    re.sub(r"[^\w\s]", "", str(c)).strip().replace(" ", "_")
                    for c in df.columns
                ]

                # Register exact sheet name (if identifier-compatible)
                safe_name = re.sub(r"[^\w]", "_", sheet_name).strip("_")
                unaccented = strip_accents(safe_name).lower()
                unaccented = re.sub(r"[^\w]", "_", unaccented).strip("_")

                conn.register(sheet_name, df)
                if safe_name != sheet_name:
                    conn.register(safe_name, df)
                if unaccented not in (sheet_name, safe_name):
                    conn.register(unaccented, df)

            # Enforce row limit
            limited_query = sql_query.strip().rstrip(";")
            if not re.search(r"\bLIMIT\s+\d+", limited_query, re.IGNORECASE):
                limited_query = f"{limited_query} LIMIT {limit}"

            cursor = conn.execute(limited_query)
            col_names = [desc[0] for desc in cursor.description]
            fetched_rows = cursor.fetchall()

            rows = []
            for row in fetched_rows:
                row_dict = {}
                for idx, col in enumerate(col_names):
                    val = row[idx]
                    # Convert timestamps or non-serializables
                    if hasattr(val, "isoformat"):
                        val = val.isoformat()
                    row_dict[col] = val
                rows.append(row_dict)

            return {
                "success": True,
                "columns": col_names,
                "rows": rows,
                "row_count": len(rows),
                "query": limited_query,
            }

        except Exception as e:
            logger.warning(f"DuckDB table query failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "columns": [],
                "rows": [],
                "row_count": 0,
            }
        finally:
            conn.close()
