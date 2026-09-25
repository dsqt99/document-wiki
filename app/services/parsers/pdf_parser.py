"""PDF Parser using PyMuPDF4LLM with Vietnamese heading heuristics,

repeated header/footer stripping, and scanned page OCR fallback.
"""

import asyncio
import re
from typing import Any, Dict, List, Optional, Tuple
from loguru import logger

try:
    import pymupdf as fitz
except ImportError:
    import fitz

try:
    import pymupdf4llm
except ImportError:
    pymupdf4llm = None

from app.core.text_normalizer import normalize_text
from app.services.parsers.base import BaseParser


# ---------------------------------------------------------------------------
# Heuristic Helpers
# ---------------------------------------------------------------------------

VIETNAMESE_HEADING_PATTERNS = [
    (re.compile(r"^(PHẦN THỨ\s+[A-ZÀ-Ỹ0-9]+.*)$", re.IGNORECASE), "# "),
    (re.compile(r"^(CHƯƠNG\s+[IVXLCDM0-9]+.*)$", re.IGNORECASE), "## "),
    (re.compile(r"^(MỤC\s+\d+.*)$", re.IGNORECASE), "### "),
    (re.compile(r"^(TIỂU MỤC\s+\d+.*)$", re.IGNORECASE), "### "),
    (re.compile(r"^(Điều\s+\d+\.?.*)$"), "### "),
    (re.compile(r"^(PHỤ LỤC(?:\s+[A-Z0-9IVX]+)?.*)$", re.IGNORECASE), "## "),
]

PAGE_NUMBER_PATTERN = re.compile(
    r"^(?:trang\s*)?-?\s*\d+\s*(?:/\s*\d+)?\s*-?$", re.IGNORECASE
)


def enhance_vietnamese_headings(markdown_text: str) -> str:
    """Enhance Vietnamese legal headings with markdown hierarchy prefixes if not present."""
    if not markdown_text:
        return ""

    lines = markdown_text.split("\n")
    enhanced_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            enhanced_lines.append(line)
            continue

        # If already a markdown heading, skip modification
        if stripped.startswith("#"):
            enhanced_lines.append(line)
            continue

        matched = False
        for pattern, prefix in VIETNAMESE_HEADING_PATTERNS:
            if pattern.match(stripped):
                enhanced_lines.append(f"{prefix}{stripped}")
                matched = True
                break

        if not matched:
            enhanced_lines.append(line)

    return "\n".join(enhanced_lines)


def strip_repeated_headers_and_footers(
    pages: List[str], threshold: float = 0.5
) -> List[str]:
    """Strip recurring top/bottom lines (e.g. state motto, page numbers) occurring across >50% of pages."""
    num_pages = len(pages)
    if num_pages <= 1:
        return pages

    # Extract first 2 lines and last 2 lines of each page
    top_candidates: Dict[str, int] = {}
    bottom_candidates: Dict[str, int] = {}

    for page_text in pages:
        lines = [ln.strip() for ln in page_text.split("\n") if ln.strip()]
        if not lines:
            continue

        # Top 2 lines
        for top_line in lines[:2]:
            if len(top_line) > 3:
                top_candidates[top_line] = top_candidates.get(top_line, 0) + 1

        # Bottom 2 lines
        for bottom_line in lines[-2:]:
            if len(bottom_line) > 1:
                bottom_candidates[bottom_line] = (
                    bottom_candidates.get(bottom_line, 0) + 1
                )

    min_occurrences = max(2, int(num_pages * threshold))
    repeated_headers = {
        line for line, cnt in top_candidates.items() if cnt >= min_occurrences
    }
    repeated_footers = {
        line for line, cnt in bottom_candidates.items() if cnt >= min_occurrences
    }

    cleaned_pages: List[str] = []
    for page_text in pages:
        lines = page_text.split("\n")
        # Filter top lines
        start_idx = 0
        while start_idx < len(lines) and start_idx < 3:
            raw_stripped = lines[start_idx].strip()
            if raw_stripped in repeated_headers:
                start_idx += 1
            else:
                break

        # Filter bottom lines
        end_idx = len(lines)
        while end_idx > start_idx and (len(lines) - end_idx) < 3:
            raw_stripped = lines[end_idx - 1].strip()
            if raw_stripped in repeated_footers or PAGE_NUMBER_PATTERN.match(
                raw_stripped
            ):
                end_idx -= 1
            else:
                break

        cleaned_pages.append("\n".join(lines[start_idx:end_idx]).strip())

    return cleaned_pages


def is_scanned_page(page: Any, text: str) -> bool:
    """Detect if a PDF page is a scanned image with minimal/no extractable text."""
    clean_text = (text or "").strip()
    if len(clean_text) >= 50:
        return False

    if len(clean_text) < 15:
        # Check image coverage area
        rect = getattr(page, "rect", None)
        if not rect:
            return False

        page_area = rect.width * rect.height
        if page_area <= 0:
            return False

        img_rects = []
        if hasattr(page, "get_image_rects"):
            img_rects = page.get_image_rects()
        elif hasattr(page, "get_images"):
            # Fallback when get_image_rects is not present
            for img in page.get_images():
                xref = img[0]
                img_rects.extend(page.get_image_rects(xref))

        total_img_area = sum(r.width * r.height for r in img_rects)
        if (total_img_area / page_area) > 0.5:
            return True

    return False


# ---------------------------------------------------------------------------
# PDF Parser Implementation
# ---------------------------------------------------------------------------

class PDFParser(BaseParser):
    """High-fidelity PDF parser using PyMuPDF4LLM with OCR fallback."""

    OCR_PROMPT = (
        "Trích xuất TOÀN BỘ văn bản từ hình ảnh trang tài liệu này một cách chính xác tuyệt đối.\n"
        "Yêu cầu nghiêm ngặt:\n"
        "1. Giữ nguyên số hiệu văn bản, tiêu đề, dấu câu, ngày tháng, các cụm từ viết tắt ngành (CAND, CSGT, PCCC, ANTT, QĐ, NĐ, TT...).\n"
        "2. Tái tạo chính xác cấu trúc bảng biểu dạng Markdown Table (| Cột 1 | Cột 2 |).\n"
        "3. Tái tạo cấu trúc thứ bậc đề mục: Phần, Chương, Mục, Điều, Khoản, Điểm.\n"
        "4. Tuyệt đối không thêm lời bình, không tóm tắt hay tự ý suy diễn từ ngữ."
    )

    async def parse(
        self,
        file_data: bytes,
        file_name: str,
        *,
        vision_provider: Optional[Any] = None,
        tracker: Optional[Any] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Parse PDF binary data into structured Markdown page records."""
        doc = fitz.open(stream=file_data, filetype="pdf")
        num_pages = len(doc)
        raw_pages: List[str] = []

        # Step 1: Extract with pymupdf4llm if available, otherwise native fitz get_text()
        extracted_via_llm = False
        if pymupdf4llm is not None:
            try:
                chunks = pymupdf4llm.to_markdown(
                    doc, page_chunks=True, table_strategy="lines_strict"
                )
                if chunks and isinstance(chunks, list):
                    raw_pages = [chunk.get("text", "") for chunk in chunks]
                    extracted_via_llm = True
                    logger.debug(
                        f"PDFParser: pymupdf4llm extracted {len(raw_pages)} pages for '{file_name}'"
                    )
            except Exception as e:
                logger.warning(
                    f"PDFParser: pymupdf4llm failed for '{file_name}', falling back to fitz: {e}"
                )

        if not extracted_via_llm or len(raw_pages) != num_pages:
            raw_pages = [(page.get_text() or "") for page in doc]

        # Step 2: Identify scanned / empty pages that need OCR
        scanned_indices: List[int] = []
        for idx, page in enumerate(doc):
            page_text = raw_pages[idx] if idx < len(raw_pages) else ""
            if not page_text.strip() or is_scanned_page(page, page_text):
                scanned_indices.append(idx)

        # Step 3: Trigger OCR for scanned/empty pages if providers available
        from app.services.ocr_service import ocr_service

        if scanned_indices and (ocr_service.is_configured or vision_provider):
            total_ocr = len(scanned_indices)
            logger.info(
                f"PDFParser: {total_ocr}/{num_pages} scanned/empty pages detected in '{file_name}'. Running OCR..."
            )

            page_images: List[Tuple[int, bytes]] = []
            for idx in scanned_indices:
                try:
                    page = doc[idx]
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                    img_bytes = pix.tobytes("jpg", jpg_quality=85)
                    page_images.append((idx, img_bytes))
                except Exception as render_err:
                    logger.warning(
                        f"PDFParser: render page {idx+1} failed for '{file_name}': {render_err}"
                    )

            sem = asyncio.Semaphore(5)
            progress_lock = asyncio.Lock()
            completed = 0

            async def _run_ocr_one(idx: int, img_bytes: bytes) -> None:
                nonlocal completed
                async with sem:
                    ocr_res = None
                    if ocr_service.is_configured:
                        try:
                            ocr_res = await ocr_service.ocr_image(
                                img_bytes,
                                mime_type="image/jpeg",
                                prompt=self.OCR_PROMPT,
                            )
                        except Exception as e:
                            logger.warning(
                                f"PDFParser: GLM-OCR failed on page {idx+1}: {e}"
                            )

                    if (not ocr_res or not ocr_res.strip()) and vision_provider:
                        try:
                            ocr_res = await vision_provider.analyze_image(
                                img_bytes,
                                mime_type="image/jpeg",
                                prompt=self.OCR_PROMPT,
                            )
                        except Exception as e:
                            logger.warning(
                                f"PDFParser: Vision OCR failed on page {idx+1}: {e}"
                            )

                    if ocr_res and ocr_res.strip():
                        raw_pages[idx] = ocr_res.strip()

                    async with progress_lock:
                        completed += 1
                        if tracker:
                            try:
                                prog = 15 + int(10 * completed / total_ocr)
                                await tracker.update(
                                    prog,
                                    f"OCR xử lý: {completed}/{total_ocr} trang scan...",
                                )
                            except Exception:
                                pass

            await asyncio.gather(
                *[_run_ocr_one(idx, img_b) for idx, img_b in page_images],
                return_exceptions=True,
            )

        doc.close()

        # Step 4: Post-processing pipeline:
        # A. Strip recurring headers and footers
        cleaned_pages = strip_repeated_headers_and_footers(raw_pages)

        # B. Enhance headings & normalize Unicode NFC
        final_pages: List[Dict[str, Any]] = []
        for i, page_text in enumerate(cleaned_pages):
            enhanced = enhance_vietnamese_headings(page_text)
            normalized = normalize_text(enhanced)
            final_pages.append(
                {
                    "content": normalized,
                    "page_number": i + 1,
                }
            )

        return final_pages
