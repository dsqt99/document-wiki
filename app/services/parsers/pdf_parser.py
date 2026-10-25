"""PDF Parser built on pypdfium2 (text layer, page rendering) and pdfplumber (ruled tables),
with Vietnamese heading heuristics, repeated header/footer stripping, and scanned page OCR fallback.
Supports customizable engine, OCR modes, and page limits.

Engines:
- ``pdfplumber``   (default) Markdown with ruled tables and font-size based headings.
- ``pdfium_plain`` plain text layer straight from PDFium, fastest.
- ``markitdown``   Microsoft MarkItDown converter.
Engine names from the previous implementation are accepted as aliases (see ENGINE_ALIASES).
"""

import asyncio
import io
import re
import statistics
from collections import Counter
from typing import Any, Dict, List, Optional, Set, Tuple

from loguru import logger

from app.core.legal_headings import is_bare_article_continuation, is_legal_structure_candidate, legal_heading_level
from app.core.text_normalizer import normalize_text
from app.services.ocr_service import VISION_OCR_PROMPT
from app.services.parsers import pdf_backend
from app.services.parsers.base import BaseParser
from app.services.parsers.pdf_backend import PdfPageView, Rect  # noqa: F401 - re-exported


# ---------------------------------------------------------------------------
# Engine names
# ---------------------------------------------------------------------------

ENGINE_RICH = "pdfplumber"
ENGINE_PLAIN = "pdfium_plain"
ENGINE_MARKITDOWN = "markitdown"
DEFAULT_PDF_ENGINE = ENGINE_RICH
SUPPORTED_PDF_ENGINES = (ENGINE_RICH, ENGINE_PLAIN, ENGINE_MARKITDOWN)

# Tên engine của bản cài cũ vẫn có thể nằm trong bảng cấu hình (`app_config`) của hệ thống đã triển khai.
ENGINE_ALIASES: Dict[str, str] = {
    "pymupdf4llm": ENGINE_RICH,
    "pymupdf": ENGINE_RICH,
    "pymupdf_plain": ENGINE_PLAIN,
    "fitz": ENGINE_PLAIN,
    "pdfium": ENGINE_PLAIN,
    "plain": ENGINE_PLAIN,
}


def normalize_pdf_engine(engine: Optional[str]) -> str:
    """Map a configured engine name (including legacy aliases) to a supported engine.

    Unknown names degrade to the plain text layer, which is what the previous
    implementation did when no engine branch matched.
    """
    name = (engine or "").strip().lower()
    if not name:
        return DEFAULT_PDF_ENGINE
    if name in SUPPORTED_PDF_ENGINES:
        return name
    return ENGINE_ALIASES.get(name, ENGINE_PLAIN)


# ---------------------------------------------------------------------------
# Heuristic Helpers
# ---------------------------------------------------------------------------

PAGE_NUMBER_PATTERN = re.compile(
    r"^(?:trang\s*)?-?\s*\d+\s*(?:/\s*\d+)?\s*-?$", re.IGNORECASE
)


def enhance_vietnamese_headings(markdown_text: str) -> str:
    """Enhance Vietnamese legal headings with markdown hierarchy prefixes if not present."""
    if not markdown_text:
        return ""

    lines = markdown_text.split("\n")
    enhanced_lines: list[str] = []
    previous_nonempty = ""

    for line in lines:
        stripped = line.strip()
        if not stripped:
            enhanced_lines.append(line)
            continue

        bare_reference = is_bare_article_continuation(stripped, previous_nonempty)
        # OCR engines can emit their own headings for wrapped inline citations.
        # Remove only that structural markup; keep every word of the source.
        if stripped.startswith("#"):
            if bare_reference or (is_legal_structure_candidate(stripped) and legal_heading_level(stripped) is None):
                enhanced_lines.append(re.sub(r"^#{1,6}\s+", "", stripped))
            else:
                enhanced_lines.append(line)
            previous_nonempty = enhanced_lines[-1].strip()
            continue

        level = None if bare_reference else legal_heading_level(stripped)
        if level:
            enhanced_lines.append(f"{'#' * level} {stripped}")
        else:
            enhanced_lines.append(line)
        previous_nonempty = enhanced_lines[-1].strip()

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
    """Detect if a PDF page is a scanned image with minimal/no extractable text.

    ``page`` only needs a ``rect`` (with ``width``/``height``) and ``get_image_rects()``
    returning rectangles with ``width``/``height``; see :class:`PdfPageView`.
    """
    clean_text = (text or "").strip()
    if len(clean_text) >= 50:
        return False

    # A short native signature/header can coexist with a full scanned page.
    # Check image coverage for all sparse text layers, including 15–49 chars.
    rect = getattr(page, "rect", None)
    if not rect:
        return False

    page_area = rect.width * rect.height
    if page_area <= 0:
        return False

    img_rects = []
    if hasattr(page, "get_image_rects"):
        img_rects = page.get_image_rects() or []

    total_img_area = sum(r.width * r.height for r in img_rects)
    if (total_img_area / page_area) > 0.5:
        return True

    return False


# ---------------------------------------------------------------------------
# Rich engine: pdfplumber text lines + ruled tables -> Markdown
# ---------------------------------------------------------------------------

# A line whose font size is this much larger than the body text becomes a heading.
_HEADING_RATIOS: Tuple[Tuple[float, int], ...] = ((1.6, 1), (1.35, 2), (1.15, 3))
_HEADING_MAX_CHARS = 120
# Vertical gap (relative to the line height) that separates two paragraphs.
_PARAGRAPH_GAP_RATIO = 0.6


def _table_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.split())
    return text.replace("|", "\\|")


def table_rows_to_markdown(rows: List[List[Any]]) -> str:
    """Render extracted table rows (first row is the header) as a GitHub-flavoured Markdown table."""
    cleaned = [[_table_cell(c) for c in row] for row in (rows or []) if row is not None]
    cleaned = [row for row in cleaned if any(cell.strip() for cell in row)]
    if not cleaned:
        return ""
    ncols = max(len(row) for row in cleaned)
    cleaned = [row + [""] * (ncols - len(row)) for row in cleaned]
    header, body = cleaned[0], cleaned[1:]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * ncols) + " |",
    ]
    for row in body:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _line_font_size(line: Dict[str, Any]) -> float:
    sizes = [
        float(c.get("size") or 0)
        for c in (line.get("chars") or [])
        if c.get("size") and (c.get("text") or "").strip()
    ]
    return statistics.median(sizes) if sizes else 0.0


def _line_is_bold(line: Dict[str, Any]) -> bool:
    """True when every visible character of the line uses a bold font face."""
    names = [
        str(c.get("fontname") or "")
        for c in (line.get("chars") or [])
        if (c.get("text") or "").strip()
    ]
    return bool(names) and all("bold" in n.lower() for n in names)


def _matches_vietnamese_heading(text: str) -> bool:
    return legal_heading_level(text) is not None


def _heading_level(text: str, size: float, body_size: float) -> int:
    if not size or not body_size or len(text) > _HEADING_MAX_CHARS:
        return 0
    # Vietnamese legal structure lines are handled by enhance_vietnamese_headings().
    if is_legal_structure_candidate(text):
        return 0
    ratio = size / body_size
    for threshold, level in _HEADING_RATIOS:
        if ratio >= threshold:
            return level
    return 0


class _RichPage:
    """One page as an ordered list of text segments and Markdown tables."""

    __slots__ = ("segments",)

    def __init__(self) -> None:
        # ("lines", [(text, font_size, paragraph_break, bold)]) | ("table", markdown)
        self.segments: List[Tuple[str, Any]] = []

    def render(self, body_size: float, enhance_headings: bool) -> str:
        blocks: List[str] = []
        for kind, payload in self.segments:
            if kind == "table":
                blocks.append(payload)
                continue
            out: List[str] = []
            for text, size, para_break, bold in payload:
                if para_break and out:
                    out.append("")
                level = _heading_level(text, size, body_size) if enhance_headings else 0
                if level:
                    out.append(f"{'#' * level} {text}")
                elif bold and not _matches_vietnamese_heading(text):
                    # Bold-only lines keep their emphasis (as pymupdf4llm did); bold "Điều/Chương"
                    # lines stay plain so enhance_vietnamese_headings() can turn them into headings.
                    out.append(f"**{text}**")
                else:
                    out.append(text)
            blocks.append("\n".join(out))
        return "\n\n".join(b for b in blocks if b and b.strip())


def _article_superscripts(line: Dict[str, Any]) -> str:
    """Preserve small raised digits in native Article headings as superscripts.

    PDF text strings merge footnotes with identifiers (46 + raised 33 becomes
    4633). Only measured glyph geometry supplies the distinction; plain text,
    ordinary small digits on the baseline, and body/math lines stay untouched.
    """
    text = (line.get("text") or "").strip()
    if not re.match(r"^Điều\s+\d", text, re.IGNORECASE) or legal_heading_level(text) != 3:
        return text
    chars = [c for c in (line.get("chars") or []) if (c.get("text") or "").strip()]
    body_size = _line_font_size(line)
    normal = [c for c in chars if float(c.get("size") or 0) >= body_size * 0.9]
    if not body_size or not normal:
        return text
    baseline = statistics.median(float(c["bottom"]) for c in normal)
    normal_top = statistics.median(float(c["top"]) for c in normal)
    spans: List[Tuple[int, int]] = []
    cursor = 0
    for char in chars:
        value = char["text"]
        start = text.find(value, cursor)
        if start < 0:
            # A nonliteral/ligature mapping cannot safely insert markup.
            return text
        end = start + len(value)
        cursor = end
        size = float(char.get("size") or 0)
        if not (value.isdigit() and 0 < size <= body_size * 0.8
                and baseline - float(char["bottom"]) >= body_size * 0.2
                and float(char["top"]) <= normal_top + body_size * 0.15):
            continue
        if spans and spans[-1][1] == start:
            spans[-1] = (spans[-1][0], end)
        else:
            spans.append((start, end))
    for start, end in reversed(spans):
        text = text[:start] + "<sup>" + text[start:end] + "</sup>" + text[end:]
    return text


def _format_lines(lines: List[Dict[str, Any]], sizes: Counter) -> List[Tuple[str, float, bool, bool]]:
    out: List[Tuple[str, float, bool, bool]] = []
    prev_bottom: Optional[float] = None
    for line in lines:
        text = _article_superscripts(line)
        if not text:
            continue
        size = _line_font_size(line)
        if size:
            sizes[round(size, 1)] += sum(1 for ch in line["text"] if not ch.isspace())
        line_top = float(line.get("top", 0))
        line_bottom = float(line.get("bottom", 0))
        height = max(1.0, line_bottom - line_top)
        para_break = prev_bottom is not None and (line_top - prev_bottom) > _PARAGRAPH_GAP_RATIO * height
        out.append((text, size, para_break, _line_is_bold(line)))
        prev_bottom = line_bottom
    return out


def _is_boxed_legal_prose(rows: List[List[Any]]) -> bool:
    nonempty = [row for row in (rows or []) if row and any(str(cell or "").strip() for cell in row)]
    if not nonempty or any(len(row) != 1 for row in nonempty):
        return False
    first_line = str(nonempty[0][0] or "").strip().splitlines()[0]
    heading = re.match(r"^Điều\s+\d+[a-z]?[.:]\s*(.+)$", first_line, re.IGNORECASE)
    if not heading or legal_heading_level(first_line) != 3 or len(heading.group(1).split()) < 2:
        return False
    # A titled Article followed by a substantive numbered clause is boxed
    # legal prose. Reference lists and catalogues containing bare Article
    # identifiers must retain their table structure.
    return any(
        re.match(r"^(?:\d+[.)]|[a-zđ]\))\s+", line.strip(), re.IGNORECASE)
        and len(line.strip()) >= 40 and len(line.split()) >= 6
        for row in nonempty[1:]
        for line in str(row[0] or "").splitlines()
    )


def _rich_page(pl_page: Any, sizes: Counter) -> _RichPage:
    page = _RichPage()
    try:
        tables = pl_page.find_tables()
    except Exception as e:  # noqa: BLE001
        logger.debug(f"PDFParser: table detection failed on page {pl_page.page_number}: {e}")
        tables = []
    rendered_tables = []
    rendered_cells = []
    for table in tables:
        try:
            rows = table.extract()
            if _is_boxed_legal_prose(rows):
                # Border/highlight rectangles can look like a one-column
                # table around entire legal articles. Keep the native lines,
                # including font/footnote geometry and legal heading semantics.
                continue
            markdown = table_rows_to_markdown(rows)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"PDFParser: table extract failed on page {pl_page.page_number}: {e}")
            markdown = ""
        if markdown:
            rendered_tables.append((table.bbox, markdown))
            rendered_cells.extend(cell for cell in table.cells if cell is not None)

    def outside_rendered_tables(obj: Dict[str, Any]) -> bool:
        if obj.get("object_type") != "char":
            return True
        # Use the same character-center membership as pdfplumber's table
        # extraction, against actual cells rather than the bounding rectangle:
        # irregular tables can have paragraphs in unoccupied corners.
        cx = (float(obj["x0"]) + float(obj["x1"])) / 2
        cy = (float(obj["top"]) + float(obj["bottom"])) / 2
        return not any(x0 <= cx < x1 and top <= cy < bottom for x0, top, x1, bottom in rendered_cells)

    text_page = pl_page.filter(outside_rendered_tables) if rendered_tables else pl_page
    lines = text_page.extract_text_lines(strip=True, return_chars=True)
    # Merge whole text lines and converted tables by their top coordinate.
    # Extracting lines once also avoids duplicating characters cut by a band
    # boundary. Failed/empty table conversions stay in the native text layer.
    events = [(float(line["top"]), float(line["x0"]), "line", line) for line in lines]
    events.extend((float(bbox[1]), float(bbox[0]), "table", md) for bbox, md in rendered_tables)
    pending = []
    for _top, _x0, kind, payload in sorted(events, key=lambda event: event[:2]):
        if kind == "line":
            pending.append(payload)
        else:
            if pending:
                page.segments.append(("lines", _format_lines(pending, sizes)))
                pending = []
            page.segments.append(("table", payload))
    if pending:
        page.segments.append(("lines", _format_lines(pending, sizes)))
    return page


def extract_markdown_pages(
    file_data: bytes, page_indices: List[int], *, enhance_headings: bool = True
) -> List[str]:
    """Markdown for the requested pages (0-based indices) using pdfplumber.

    Ruled tables become Markdown tables; lines noticeably larger than the dominant
    body font become ``#``/``##``/``###`` headings; vertical gaps become paragraph breaks.
    """
    import pdfplumber

    sizes: Counter = Counter()
    rich_pages: List[_RichPage] = []
    with pdfplumber.open(io.BytesIO(file_data), pages=[i + 1 for i in page_indices]) as pdf:
        for pl_page in pdf.pages:
            try:
                rich_pages.append(_rich_page(pl_page, sizes))
            finally:
                try:
                    pl_page.flush_cache()
                except Exception:  # noqa: BLE001
                    pass
    body_size = float(sizes.most_common(1)[0][0]) if sizes else 0.0
    return [page.render(body_size, enhance_headings) for page in rich_pages]


# ---------------------------------------------------------------------------
# PDF Parser Implementation
# ---------------------------------------------------------------------------

class PDFParser(BaseParser):
    """High-fidelity PDF parser (pdfplumber tables + PDFium text layer) with OCR fallback."""

    # Vision-model prompt; the OCR slot's model gets ocr_model_prompt.
    DEFAULT_OCR_PROMPT = VISION_OCR_PROMPT

    async def parse(
        self,
        file_data: bytes,
        file_name: str,
        *,
        vision_provider: Optional[Any] = None,
        tracker: Optional[Any] = None,
        engine: str = DEFAULT_PDF_ENGINE,
        ocr_mode: str = "auto",
        strip_headers_footers: bool = True,
        enhance_headings: bool = True,
        max_pages: Optional[int] = None,
        ocr_base_url: Optional[str] = None,
        ocr_api_key: Optional[str] = None,
        ocr_model: Optional[str] = None,
        ocr_prompt: Optional[str] = None,
        ocr_model_prompt: Optional[str] = None,
        ocr_fallback_vision: bool = True,
        ocr_llm_refine: bool = False,
        db: Optional[Any] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Parse PDF binary data into structured Markdown page records."""
        engine = normalize_pdf_engine(engine)
        doc = pdf_backend.open_document(file_data)
        page_cache: Dict[int, Any] = {}

        def _page(idx: int) -> Any:
            if idx not in page_cache:
                page_cache[idx] = doc[idx]
            return page_cache[idx]

        try:
            return await self._parse_open(
                doc,
                _page,
                file_data,
                file_name,
                vision_provider=vision_provider,
                tracker=tracker,
                engine=engine,
                ocr_mode=ocr_mode,
                strip_headers_footers=strip_headers_footers,
                enhance_headings=enhance_headings,
                max_pages=max_pages,
                ocr_base_url=ocr_base_url,
                ocr_api_key=ocr_api_key,
                ocr_model=ocr_model,
                ocr_prompt=ocr_prompt,
                ocr_model_prompt=ocr_model_prompt,
                ocr_fallback_vision=ocr_fallback_vision,
                ocr_llm_refine=ocr_llm_refine,
                db=db,
            )
        finally:
            for page in page_cache.values():
                try:
                    page.close()
                except Exception:  # noqa: BLE001
                    pass
            doc.close()

    async def _parse_open(
        self,
        doc: Any,
        _page: Any,
        file_data: bytes,
        file_name: str,
        *,
        vision_provider: Optional[Any],
        tracker: Optional[Any],
        engine: str,
        ocr_mode: str,
        strip_headers_footers: bool,
        enhance_headings: bool,
        max_pages: Optional[int],
        ocr_base_url: Optional[str],
        ocr_api_key: Optional[str],
        ocr_model: Optional[str],
        ocr_prompt: Optional[str],
        ocr_model_prompt: Optional[str],
        ocr_fallback_vision: bool,
        ocr_llm_refine: bool,
        db: Optional[Any],
    ) -> List[Dict[str, Any]]:
        total_doc_pages = len(doc)

        if max_pages is not None and max_pages > 0:
            num_pages = min(total_doc_pages, max_pages)
        else:
            num_pages = total_doc_pages

        raw_pages: List[str] = []
        target_page_indices = list(range(num_pages))

        # Step 1: Extract with chosen engine
        extracted_via_engine = False
        if engine == ENGINE_MARKITDOWN:
            try:
                from markitdown import MarkItDown
                md_converter = MarkItDown()
                res = md_converter.convert_stream(io.BytesIO(file_data), file_extension=".pdf")
                content = res.text_content or ""
                if content.strip():
                    raw_pages = [content]
                    extracted_via_engine = True
            except Exception as e:
                logger.warning(
                    f"PDFParser: markitdown failed for '{file_name}', falling back to PDFium text layer: {e}"
                )

        elif engine == ENGINE_RICH and num_pages > 0:
            try:
                raw_pages = extract_markdown_pages(
                    file_data, target_page_indices, enhance_headings=enhance_headings
                )
                extracted_via_engine = True
                logger.debug(
                    f"PDFParser: pdfplumber extracted {len(raw_pages)} pages for '{file_name}'"
                )
            except Exception as e:
                logger.warning(
                    f"PDFParser: pdfplumber failed for '{file_name}', falling back to PDFium text layer: {e}"
                )

        if not extracted_via_engine or len(raw_pages) != num_pages:
            raw_pages = [pdf_backend.page_text(_page(idx)) for idx in target_page_indices]

        # Step 2: Determine which pages require OCR based on ocr_mode
        scanned_indices: List[int] = []
        normalized_mode = (ocr_mode or "auto").lower()

        if normalized_mode == "disabled":
            scanned_indices = []
        elif normalized_mode == "force_ocr":
            scanned_indices = list(range(num_pages))
        else:  # 'auto'
            for idx in range(num_pages):
                page_text = raw_pages[idx] if idx < len(raw_pages) else ""
                if not page_text.strip() or is_scanned_page(PdfPageView(_page(idx)), page_text):
                    scanned_indices.append(idx)

        # Step 3: Trigger OCR for target pages if providers available
        from app.services.ocr_service import ocr_service, refine_ocr_with_llm, validate_ocr_text

        is_ocr_ready = ocr_service.is_configured(base_url=ocr_base_url, api_key=ocr_api_key)
        has_vision = bool(vision_provider and ocr_fallback_vision)
        ocr_successful_pages: Set[int] = set()

        if scanned_indices and (is_ocr_ready or has_vision):
            total_ocr = len(scanned_indices)
            logger.info(
                f"PDFParser: {total_ocr}/{num_pages} pages scheduled for OCR (mode={normalized_mode}) in '{file_name}'."
            )

            page_images: List[Tuple[int, bytes]] = []
            for idx in scanned_indices:
                try:
                    img_bytes = pdf_backend.render_page_jpeg(_page(idx))
                    page_images.append((idx, img_bytes))
                except Exception as render_err:
                    logger.warning(
                        f"PDFParser: render page {idx+1} failed for '{file_name}': {render_err}"
                    )

            from app.ai import upstream
            from app.services.ocr_service import OCR_UPSTREAM_KEY

            sem = asyncio.Semaphore(5)
            progress_lock = asyncio.Lock()
            completed = 0
            outage: List[upstream.UpstreamUnavailable] = []
            # ocr_prompt is for vision models. The OCR slot's model gets
            # ocr_model_prompt, else ocr_service resolves it ("OCR:" for kind="ocr").
            vision_prompt = ocr_prompt or self.DEFAULT_OCR_PROMPT

            async def _run_ocr_one(idx: int, img_bytes: bytes) -> None:
                nonlocal completed
                async with sem:
                    ocr_res = None
                    if is_ocr_ready:
                        try:
                            ocr_res = await ocr_service.ocr_image(
                                img_bytes,
                                mime_type="image/jpeg",
                                prompt=ocr_model_prompt,
                                base_url=ocr_base_url,
                                api_key=ocr_api_key,
                                model=ocr_model,
                                db=db,
                            )
                        except Exception as e:
                            logger.warning(
                                f"PDFParser: dedicated OCR failed on page {idx+1}: {e}"
                            )

                    # OCR + LLM: the Vision model proofreads the OCR draft
                    # against the page image (more accurate, ~2x slower).
                    if ocr_res and ocr_res.strip() and ocr_llm_refine and vision_provider:
                        refined = await refine_ocr_with_llm(
                            vision_provider, img_bytes, "image/jpeg", ocr_res
                        )
                        if refined:
                            ocr_res = refined

                    if (not ocr_res or not ocr_res.strip()) and has_vision and not outage:
                        try:
                            ocr_res = await vision_provider.analyze_image(
                                img_bytes,
                                mime_type="image/jpeg",
                                prompt=vision_prompt,
                            )
                        except upstream.UpstreamUnavailable as e:
                            outage.append(e)
                        except Exception as e:
                            logger.warning(
                                f"PDFParser: Vision OCR fallback failed on page {idx+1}: {e}"
                            )
                        if ocr_res:
                            cleaned, reason = validate_ocr_text(ocr_res)
                            if reason:
                                logger.warning(
                                    f"PDFParser: Vision OCR fallback output rejected on page "
                                    f"{idx+1} ({reason}); keeping native text"
                                )
                                ocr_res = None
                            else:
                                ocr_res = cleaned

                    if ocr_res and ocr_res.strip():
                        raw_pages[idx] = ocr_res.strip()
                        ocr_successful_pages.add(idx)

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

            # Indexing a scanned PDF without its OCR text yields an empty document that looks "ready";
            # fail it instead so it is retried once the AI gateway answers again.
            missing = [i for i, _ in page_images if i not in ocr_successful_pages]
            if missing and (outage or (not has_vision and upstream.is_open(OCR_UPSTREAM_KEY))):
                key = outage[0].key if outage else OCR_UPSTREAM_KEY
                raise upstream.UpstreamUnavailable(
                    key, f"{len(missing)}/{total_ocr} trang scan của '{file_name}' chưa OCR được"
                )

        # Step 4: Post-processing pipeline:
        # A. Strip recurring headers and footers
        if strip_headers_footers:
            cleaned_pages = strip_repeated_headers_and_footers(raw_pages)
        else:
            cleaned_pages = raw_pages

        # B. Enhance headings & normalize Unicode NFC
        final_pages: List[Dict[str, Any]] = []
        for i, page_text in enumerate(cleaned_pages):
            enhanced = enhance_vietnamese_headings(page_text) if enhance_headings else page_text
            normalized = normalize_text(enhanced)
            final_pages.append(
                {
                    "content": normalized,
                    "page_number": i + 1,
                    "total_doc_pages": total_doc_pages,
                    "is_ocr": i in ocr_successful_pages,
                    "ocr_required": i in scanned_indices,
                    "char_count": len(normalized),
                    "word_count": len(normalized.split()),
                }
            )

        return final_pages
