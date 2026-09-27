"""
Excel Parser — Structured spreadsheet extraction and row-wise relational chunking.

Extracts data from Excel files (.xlsx, .xls) into:
1. Markdown table previews for full-text viewing.
2. Structured row-wise chunks with column context, enabling precise semantic
   retrieval on tabular records without losing column definitions.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional, Union

import openpyxl
from loguru import logger

from app.services.parsers.base import BaseParser


class ExcelParser(BaseParser):
    """Specialized parser for Excel workbooks."""

    async def parse(
        self,
        file_data: bytes,
        file_name: str,
        *,
        vision_provider: Optional[Any] = None,
        tracker: Optional[Any] = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Parse Excel binary data into page-like sheet markdown records."""
        import io
        from app.core.text_normalizer import normalize_text

        wb = openpyxl.load_workbook(io.BytesIO(file_data), data_only=True)
        pages: list[dict[str, Any]] = []

        for idx, sheet_name in enumerate(wb.sheetnames, start=1):
            ws = wb[sheet_name]
            rows = list(ws.iter_rows(values_only=True))
            if not rows:
                continue

            # First non-empty row as header
            header_idx = 0
            header_row = None
            for r_i, r in enumerate(rows):
                if any(cell is not None and str(cell).strip() != "" for cell in r):
                    header_row = [str(c).strip() if c is not None else f"Cột_{i+1}" for i, c in enumerate(r)]
                    header_idx = r_i
                    break

            if not header_row:
                continue

            columns = [c if c else f"Cột_{i+1}" for i, c in enumerate(header_row)]
            data_rows = rows[header_idx + 1:]

            md_lines = [f"## Bảng tính: {sheet_name}\n"]
            md_lines.append("| " + " | ".join(columns) + " |")
            md_lines.append("| " + " | ".join(["---"] * len(columns)) + " |")

            for row in data_rows:
                row_vals = [
                    str(val).replace("\n", " ").replace("|", "\\|").strip() if val is not None else ""
                    for val in row[:len(columns)]
                ]
                while len(row_vals) < len(columns):
                    row_vals.append("")
                md_lines.append("| " + " | ".join(row_vals) + " |")

            content = normalize_text("\n".join(md_lines))
            pages.append({
                "page_number": idx,
                "sheet_name": sheet_name,
                "content": content,
            })

        wb.close()
        if not pages:
            pages = [{"page_number": 1, "content": ""}]
        return pages

    def parse_file(
        self,
        file_path: Union[str, Path],
        max_rows_per_sheet_preview: int = 100,
    ) -> dict[str, Any]:
        """Parse an Excel file and return metadata, markdown tables, and row-wise chunks."""
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Excel file not found: {file_path}")

        wb = openpyxl.load_workbook(file_path, data_only=True)
        sheet_names = wb.sheetnames

        sheets_meta: dict[str, Any] = {}
        all_chunks: list[dict[str, Any]] = []
        md_sections: list[str] = [f"# Tài liệu bảng tính: {file_path.name}\n"]

        for sheet_name in sheet_names:
            ws = wb[sheet_name]
            rows = list(ws.iter_rows(values_only=True))

            if not rows:
                continue

            # First non-empty row as header
            header_idx = 0
            header_row = None
            for idx, r in enumerate(rows):
                if any(cell is not None and str(cell).strip() != "" for cell in r):
                    header_row = [str(c).strip() if c is not None else f"Cột_{i+1}" for i, c in enumerate(r)]
                    header_idx = idx
                    break

            if not header_row:
                continue

            # Clean header column names
            columns = [c if c else f"Cột_{i+1}" for i, c in enumerate(header_row)]
            data_rows = rows[header_idx + 1:]

            sheets_meta[sheet_name] = {
                "columns": columns,
                "row_count": len(data_rows),
            }

            # 1. Build Markdown Table Preview
            md_sections.append(f"## Bảng tính: {sheet_name}\n")
            md_sections.append("| " + " | ".join(columns) + " |")
            md_sections.append("| " + " | ".join(["---"] * len(columns)) + " |")

            preview_rows = data_rows[:max_rows_per_sheet_preview]
            for row in preview_rows:
                row_vals = [
                    str(val).replace("\n", " ").replace("|", "\\|").strip() if val is not None else ""
                    for val in row[:len(columns)]
                ]
                # Pad if shorter
                while len(row_vals) < len(columns):
                    row_vals.append("")
                md_sections.append("| " + " | ".join(row_vals) + " |")

            if len(data_rows) > max_rows_per_sheet_preview:
                md_sections.append(f"\n*(Hiển thị {max_rows_per_sheet_preview}/{len(data_rows)} dòng. Dùng truy vấn bảng để tra cứu toàn bộ)*\n")
            else:
                md_sections.append("")

            # 2. Build Row-Wise Structured Chunks
            for r_idx, row in enumerate(data_rows, start=1):
                cell_pairs = []
                for c_idx, val in enumerate(row[:len(columns)]):
                    if val is not None and str(val).strip() != "":
                        clean_v = str(val).strip()
                        cell_pairs.append(f"{columns[c_idx]}: {clean_v}")

                if cell_pairs:
                    chunk_text = f"[Bảng: {sheet_name} | Dòng {r_idx}]: " + " | ".join(cell_pairs)
                    all_chunks.append({
                        "sheet_name": sheet_name,
                        "row_index": r_idx,
                        "text": chunk_text,
                    })

        wb.close()

        full_markdown = "\n".join(md_sections)

        return {
            "file_name": file_path.name,
            "sheet_count": len(sheet_names),
            "sheet_names": sheet_names,
            "sheets": sheets_meta,
            "chunks": all_chunks,
            "markdown": full_markdown,
            "full_text": full_markdown,
        }
