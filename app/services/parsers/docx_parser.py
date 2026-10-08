"""DOCX Parser converting Word documents to Markdown with table and merged-cell support."""

import io
from typing import Any, Dict, List, Optional
from loguru import logger

try:
    import docx
    from docx.document import Document as _DocumentType
    from docx.oxml.text.paragraph import CT_P
    from docx.oxml.table import CT_Tbl
    from docx.table import Table, _Cell
    from docx.text.paragraph import Paragraph
except ImportError:
    docx = None

from app.core.text_normalizer import normalize_text
from app.services.parsers.base import BaseParser
from app.services.parsers.pdf_parser import enhance_vietnamese_headings


def _table_to_markdown(table: Any) -> str:
    """Convert a python-docx Table to a clean Markdown table string."""
    if not table.rows:
        return ""

    rows_data: List[List[str]] = []
    max_cols = 0

    for row in table.rows:
        row_cells: List[str] = []
        for cell in row.cells:
            # Replace internal line breaks with <br> so markdown table does not break
            cell_txt = cell.text.replace("\r\n", "\n").replace("\n", "<br>").strip()
            # Escape pipe character
            cell_txt = cell_txt.replace("|", "\\|")
            row_cells.append(cell_txt)
        
        # Deduplicate consecutive identical cells caused by merged cells in python-docx
        cleaned_cells: List[str] = []
        for i, val in enumerate(row_cells):
            # python-docx points merged cells to the same object, so cell.text is repeated
            # For header and data rows, keep structure aligned
            cleaned_cells.append(val)

        if len(cleaned_cells) > max_cols:
            max_cols = len(cleaned_cells)
        rows_data.append(cleaned_cells)

    if not rows_data or max_cols == 0:
        return ""

    # Pad all rows to max_cols to ensure well-formed markdown table
    for r in rows_data:
        while len(r) < max_cols:
            r.append("")

    lines: List[str] = []
    header_row = rows_data[0]
    lines.append("| " + " | ".join(header_row) + " |")
    lines.append("| " + " | ".join(["---"] * max_cols) + " |")

    for body_row in rows_data[1:]:
        lines.append("| " + " | ".join(body_row) + " |")

    return "\n".join(lines)


def _has_page_break(paragraph_element: Any) -> bool:
    """Check if a paragraph element contains a page break."""
    xml_str = paragraph_element.xml
    return 'w:type="page"' in xml_str or "w:lastRenderedPageBreak" in xml_str


class DocxParser(BaseParser):
    """Parser for DOCX files preserving paragraph hierarchy, tables, and logical pages."""

    async def parse(
        self,
        file_data: bytes,
        file_name: str,
        *,
        vision_provider: Optional[Any] = None,
        tracker: Optional[Any] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Parse DOCX binary content into Markdown pages."""
        if docx is None:
            raise RuntimeError("python-docx is not installed in the environment")

        try:
            doc = docx.Document(io.BytesIO(file_data))
        except Exception as e:
            logger.warning(f"DocxParser: python-docx failed to open '{file_name}': {e}. Falling back to mammoth.")
            return await self._fallback_mammoth(file_data, file_name)

        pages: List[str] = []
        current_page_lines: List[str] = []

        # Iterate through document body in exact order
        for child in doc.element.body:
            if isinstance(child, CT_P):
                p = Paragraph(child, doc)
                text = p.text.strip()
                if not text:
                    if _has_page_break(child):
                        if current_page_lines:
                            pages.append("\n\n".join(current_page_lines))
                            current_page_lines = []
                    continue

                # Heading detection via paragraph style
                style_name = p.style.name.lower() if p.style and p.style.name else ""
                if "heading 1" in style_name:
                    text = f"# {text}"
                elif "heading 2" in style_name:
                    text = f"## {text}"
                elif "heading 3" in style_name:
                    text = f"### {text}"
                elif "title" in style_name:
                    text = f"# {text}"

                current_page_lines.append(text)

                if _has_page_break(child):
                    pages.append("\n\n".join(current_page_lines))
                    current_page_lines = []

            elif isinstance(child, CT_Tbl):
                tbl = Table(child, doc)
                tbl_md = _table_to_markdown(tbl)
                if tbl_md:
                    current_page_lines.append(tbl_md)

        if current_page_lines:
            pages.append("\n\n".join(current_page_lines))

        if not pages:
            pages = [""]

        # Post-process each page with Vietnamese legal headings and NFC normalizer
        final_pages: List[Dict[str, Any]] = []
        for idx, page_content in enumerate(pages):
            enhanced = enhance_vietnamese_headings(page_content)
            normalized = normalize_text(enhanced)
            final_pages.append({
                "content": normalized,
                "page_number": idx + 1,
            })

        return final_pages

    async def _fallback_mammoth(self, file_data: bytes, file_name: str) -> List[Dict[str, Any]]:
        """Fallback to mammoth markdown conversion if python-docx fails."""
        try:
            import mammoth
            result = mammoth.convert_to_markdown(io.BytesIO(file_data))
            text = normalize_text(enhance_vietnamese_headings(result.value or ""))
            return [{"content": text, "page_number": 1}]
        except Exception as err:
            logger.error(f"DocxParser: mammoth fallback also failed for '{file_name}': {err}")
            return [{"content": "", "page_number": 1}]
