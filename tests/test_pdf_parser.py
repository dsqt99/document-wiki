import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from pdf_fixtures import make_image_pdf, make_text_pdf
from app.services.parsers.pdf_parser import (
    PDFParser,
    Rect,
    enhance_vietnamese_headings,
    extract_markdown_pages,
    is_scanned_page,
    normalize_pdf_engine,
    strip_repeated_headers_and_footers,
    table_rows_to_markdown,
)

JPEG_MAGIC = b"\xff\xd8\xff"


@pytest.mark.parametrize("reference", [
    "Điều 41 của Nghị định này thì bị xử phạt như sau:",
    "Điều 85 của Luật Xử lý vi phạm hành chính.",
    "Điều 5, Điều 6 của Nghị định này.",
    "Điều 5; các khoản còn lại giữ nguyên.",
    "Chương II của Nghị định này quy định về xử phạt.",
    "Mục 2 của Chương này.",
    "PHỤ LỤC của văn bản này.",
    "Điều 10 Nghị định này;",
    "Điều 42 Nghị định này;",
    "Điều 5 Luật số 12/2025/QH15;",
    "Điều 5 Bộ luật năm 2025;",
    "Điều 5 Thông tư của Bộ Công an;",
    "Điều 5 Quyết định và các văn bản liên quan;",
    "Điều 5 Pháp lệnh này;",
])
def test_legal_references_at_wrapped_line_start_remain_body_text(reference):
    assert enhance_vietnamese_headings(reference) == reference


@pytest.mark.parametrize(("heading", "level"), [
    ("Điều 1. Phạm vi điều chỉnh", 3),
    ("Điều 12a: Hiệu lực thi hành", 3),
    ("Điều 3", 3),
    ("Điều 4 Phạm vi điều chỉnh", 3),
    ("Điều 10. Nghị định này có hiệu lực thi hành", 3),
    ("CHƯƠNG II", 2),
    ("Chương IIIa", 2),
    ("CHƯƠNG IIA. QUY ĐỊNH BỔ SUNG", 2),
    ("Chương 2a Quy định bổ sung", 2),
    ("Chương II. Quy định chung", 2),
    ("MỤC 2 QUYỀN VÀ NGHĨA VỤ", 3),
    ("TIỂU MỤC 1", 3),
    ("PHẦN THỨ NHẤT", 1),
    ("PHỤ LỤC I", 2),
])
def test_legal_structure_headings_remain_recognized(heading, level):
    assert enhance_vietnamese_headings(heading) == f"{'#' * level} {heading}"


def test_rich_pdf_legal_reference_is_not_promoted_through_legal_heuristic():
    from app.services.parsers.pdf_parser import _matches_vietnamese_heading, _RichPage

    assert not _matches_vietnamese_heading("Điều 85 của Luật Xử lý vi phạm hành chính.")
    page = _RichPage()
    page.segments.append(("lines", [("Điều 85 của Luật Xử lý vi phạm hành chính.", 18, False, False)]))
    assert not page.render(12, True).startswith("#")


def test_existing_ocr_headings_for_inline_citations_are_demoted_without_changing_words():
    text = "### Điều 85 của Luật Xử lý vi phạm hành chính.\n# Tiêu đề khác\n### Điều 1. Phạm vi điều chỉnh"
    assert enhance_vietnamese_headings(text) == text.removeprefix("### ")


@pytest.mark.parametrize("reference", ["Điều 41.", "### Điều 41."])
def test_bare_article_after_citation_list_remains_body_text(reference):
    raw = f"Các trường hợp quy định tại Điều 40;\n\n{reference}"
    assert enhance_vietnamese_headings(raw) == "Các trường hợp quy định tại Điều 40;\n\nĐiều 41."


def test_bare_article_after_ordinary_body_remains_a_heading():
    raw = "Cơ quan, tổ chức thực hiện theo quy định;\n\nĐiều 41."
    assert enhance_vietnamese_headings(raw).endswith("### Điều 41.")


@pytest.mark.parametrize(("text", "small_digits", "expected"), [
    ("Điều 4633. (được bãi bỏ)", "33", "Điều 46<sup>33</sup>. (được bãi bỏ)"),
    ("Điều 4835. (được bãi bỏ)", "35", "Điều 48<sup>35</sup>. (được bãi bỏ)"),
    ("Điều 4a. Phạm vi điều chỉnh4", "4", "Điều 4a. Phạm vi điều chỉnh<sup>4</sup>"),
])
def test_rich_pdf_preserves_geometric_article_footnotes(text, small_digits, expected):
    from collections import Counter
    from app.services.parsers.pdf_parser import _format_lines

    start = text.rfind(small_digits)
    chars = []
    for i, ch in enumerate(text):
        elevated = start <= i < start + len(small_digits)
        chars.append({"text": ch, "size": 9 if elevated else 14,
                      "top": 287.861 if elevated else 288.183,
                      "bottom": 296.861 if elevated else 302.183})
    line = {"text": text, "chars": chars, "top": 287.861, "bottom": 302.183}
    rendered = _format_lines([line], Counter())[0][0]
    assert rendered == expected
    assert enhance_vietnamese_headings(rendered) == f"### {expected}"


def test_rich_pdf_does_not_split_normal_or_baseline_small_article_digits():
    from collections import Counter
    from app.services.parsers.pdf_parser import _format_lines

    text = "Điều 4633. Phạm vi điều chỉnh"
    chars = [{"text": ch, "size": 9 if i in (7, 8) else 14,
              "top": 293.183 if i in (7, 8) else 288.183, "bottom": 302.183}
             for i, ch in enumerate(text)]
    line = {"text": text, "chars": chars, "top": 288.183, "bottom": 302.183}
    assert _format_lines([line], Counter())[0][0] == text


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

    # Case 1: Page has a large image (covers 62.5% of the area) and almost no text (3 chars)
    mock_page.get_image_rects.return_value = [Rect(50, 50, 550, 650)]
    assert is_scanned_page(mock_page, text="abc") is True

    # Case 2: Page has plenty of text (> 50 chars) even if it has an image
    assert is_scanned_page(mock_page, text="Đây là văn bản hoàn chỉnh có độ dài lớn hơn 50 ký tự được trích xuất bằng bộ parser.") is False

    # Case 3: Page has tiny icon/logo (area 400) and 5 chars
    mock_page.get_image_rects.return_value = [Rect(10, 10, 30, 30)]
    assert is_scanned_page(mock_page, text="12345") is False


def test_image_scan_with_short_native_stamp_still_needs_ocr():
    mock_page = MagicMock()
    mock_page.rect.width = 600
    mock_page.rect.height = 800
    mock_page.get_image_rects.return_value = [Rect(0, 0, 600, 800)]
    assert is_scanned_page(mock_page, "Electronic signature stamp") is True


def test_short_native_title_without_large_image_does_not_need_ocr():
    mock_page = MagicMock()
    mock_page.rect.width = 600
    mock_page.rect.height = 800
    mock_page.get_image_rects.return_value = []
    assert is_scanned_page(mock_page, "Short document title") is False


def test_normalize_pdf_engine_accepts_legacy_names():
    assert normalize_pdf_engine(None) == "pdfplumber"
    assert normalize_pdf_engine("") == "pdfplumber"
    assert normalize_pdf_engine("PDFPLUMBER") == "pdfplumber"
    assert normalize_pdf_engine("pdfium_plain") == "pdfium_plain"
    assert normalize_pdf_engine("markitdown") == "markitdown"
    # Tên engine của bản cài cũ còn trong bảng app_config
    assert normalize_pdf_engine("pymupdf4llm") == "pdfplumber"
    assert normalize_pdf_engine("pymupdf") == "pdfplumber"
    assert normalize_pdf_engine("pymupdf_plain") == "pdfium_plain"
    # Tên lạ: về lớp chữ thuần như hành vi cũ
    assert normalize_pdf_engine("khong-ton-tai") == "pdfium_plain"


def test_table_rows_to_markdown_escapes_and_pads():
    md = table_rows_to_markdown([["A", "B"], ["x | y", None], [], ["only"]])
    assert md.splitlines() == ["| A | B |", "| --- | --- |", "| x \\| y |  |", "| only |  |"]
    assert table_rows_to_markdown([]) == ""
    assert table_rows_to_markdown([[None, ""]]) == ""


def test_rich_pdf_preserves_text_beside_partial_width_table():
    body = ["Above table", "Beside first row", "Beside second row", "Beside third row", "Below table"]
    pdf_bytes = make_text_pdf(
        [body], table=(300, 770, [70, 90], [["Key", "Value"], ["1", "Alpha"], ["2", "Beta"]])
    )
    content = extract_markdown_pages(pdf_bytes, [0])[0]
    for line in body:
        assert content.count(line) == 1
    assert content.count("Alpha") == 1
    assert "| Key | Value |" in content


def test_rich_pdf_keeps_table_text_when_table_conversion_fails():
    pdf_bytes = make_text_pdf(
        [["Before table"]], table=(50, 680, [70, 90], [["Key", "Value"], ["1", "Alpha"]])
    )
    with patch("pdfplumber.table.Table.extract", side_effect=RuntimeError("broken table")):
        content = extract_markdown_pages(pdf_bytes, [0])[0]
    assert "Before table" in content
    assert "Alpha" in content


def test_rich_pdf_keeps_single_column_boxed_legal_prose_as_native_lines():
    # The fixture's native Helvetica encoding supports Latin-1 only; supply
    # the recognized Vietnamese cell heading at the table-detection boundary.
    # The fallback must retain the actual native glyphs, not re-render cells.
    native_body = "1. Native legal provision describes the authority and scope of this article."
    pdf_bytes = make_text_pdf([[]], table=(50, 680, [500], [["Native heading"], [native_body]]))
    rows = [["Điều 44. Thẩm quyền xử phạt"], [native_body]]
    with patch("pdfplumber.table.Table.extract", return_value=rows):
        content = extract_markdown_pages(pdf_bytes, [0])[0]
    assert "Native heading" in content
    assert content.count(native_body) == 1
    assert "|" not in content


def test_rich_pdf_preserves_multicolumn_legal_table():
    pdf_bytes = make_text_pdf([[]], table=(50, 680, [200, 200], [["Heading", "Meaning"], ["One", "Two"]]))
    rows = [["Điều 44. Thẩm quyền xử phạt", "Meaning"], ["One", "Two"]]
    with patch("pdfplumber.table.Table.extract", return_value=rows):
        content = extract_markdown_pages(pdf_bytes, [0])[0]
    assert "| Điều 44. Thẩm quyền xử phạt | Meaning |" in content


def test_rich_pdf_preserves_single_column_data_table_without_legal_heading():
    pdf_bytes = make_text_pdf([[]], table=(50, 680, [300], [["Equipment"], ["Computer"], ["Keyboard"]]))
    content = extract_markdown_pages(pdf_bytes, [0])[0]
    assert "| Equipment |" in content
    assert "| Computer |" in content


@pytest.mark.parametrize("rows", [
    [["Danh mục"], ["Điều 5."], ["Điều 7."]],
    [["Điều 5."], ["1. Nội dung quy định về thẩm quyền xử phạt vi phạm hành chính."]],
    [["Điều 5. Thẩm quyền xử phạt"], ["Điều 7."]],
])
def test_rich_pdf_keeps_single_column_article_reference_lists_as_tables(rows):
    pdf_bytes = make_text_pdf([[]], table=(50, 680, [300], [["Category"], ["Item 5"], ["Item 7"]]))
    with patch("pdfplumber.table.Table.extract", return_value=rows):
        content = extract_markdown_pages(pdf_bytes, [0])[0]
    assert "| " + rows[0][0] + " |" in content
    assert "| --- |" in content


def test_rich_pdf_keeps_text_in_empty_corner_of_nonrectangular_table():
    # Two cells on the top row and only the left cell on the bottom row.
    # The bottom-right paragraph is inside the bounding box, outside all cells.
    ops = ["0.5 w"]
    for x0, y0, x1, y1 in [
        (50, 750, 250, 750), (50, 730, 250, 730), (50, 710, 150, 710),
        (50, 750, 50, 710), (150, 750, 150, 710), (250, 750, 250, 730),
    ]:
        ops.append(f"{x0} {y0} m {x1} {y1} l S")
    for x, y, text in [
        (53, 736, "LeftHeader"), (153, 736, "RightHeader"),
        (53, 716, "LeftBody"), (153, 716, "SHOULD_STAY"),
    ]:
        ops.append(f"BT /F1 10 Tf {x} {y} Td ({text}) Tj ET")
    with patch("pdf_fixtures._page_stream", return_value="\n".join(ops).encode("ascii")):
        pdf_bytes = make_text_pdf([[]])
    content = extract_markdown_pages(pdf_bytes, [0])[0]
    assert "| LeftHeader | RightHeader |" in content
    assert content.count("LeftBody") == 1
    assert content.count("SHOULD_STAY") == 1


@pytest.mark.asyncio
async def test_pdf_parser_generates_markdown():
    """Verify PDFParser converts a synthetic PDF to structured markdown."""
    pdf_bytes = make_text_pdf(
        [["CHAPTER I: GENERAL PROVISIONS", "Article 1. Scope of regulation", "Testing document content here."]]
    )

    pages_data = await PDFParser().parse(pdf_bytes, "test_doc.pdf", ocr_mode="disabled")

    assert len(pages_data) == 1
    assert pages_data[0]["page_number"] == 1
    content = pages_data[0]["content"]
    assert "Article 1" in content
    assert pages_data[0]["is_ocr"] is False
    assert pages_data[0]["char_count"] == len(content)
    assert pages_data[0]["word_count"] == len(content.split())


@pytest.mark.asyncio
async def test_pdf_parser_extracts_ruled_table_as_markdown():
    pdf_bytes = make_text_pdf(
        [["Bang thong ke", "Noi dung truoc bang"], ["Trang hai"]],
        table=(
            50,
            680,
            [60, 150, 80],
            [["STT", "Ten", "So luong"], ["1", "May tinh", "10"], ["2", "Ban phim", "25"]],
        ),
    )

    pages = await PDFParser().parse(pdf_bytes, "bang.pdf", ocr_mode="disabled")

    assert len(pages) == 2
    content = pages[0]["content"]
    assert "Noi dung truoc bang" in content
    assert "| STT | Ten | So luong |" in content
    assert "| --- | --- | --- |" in content
    assert "| 2 | Ban phim | 25 |" in content
    assert content.index("Noi dung truoc bang") < content.index("| STT")
    assert pages[1]["content"] == "Trang hai"


@pytest.mark.asyncio
async def test_pdf_parser_plain_engine_keeps_text_layer_only():
    pdf_bytes = make_text_pdf(
        [["Noi dung truoc bang"]],
        table=(50, 680, [60, 150], [["STT", "Ten"], ["1", "May tinh"]]),
    )

    pages = await PDFParser().parse(pdf_bytes, "bang.pdf", engine="pdfium_plain", ocr_mode="disabled")

    assert "Noi dung truoc bang" in pages[0]["content"]
    assert "May tinh" in pages[0]["content"]
    assert "| --- |" not in pages[0]["content"]


@pytest.mark.asyncio
async def test_pdf_parser_marks_large_font_lines_as_headings():
    pdf_bytes = make_text_pdf(
        [[
            ("TITLE OF THE DOCUMENT", 20),
            "Body line one of the document, written in the usual size.",
            "Body line two of the document, written in the usual size.",
            "Body line three of the document, also in the usual size.",
        ]]
    )

    pages = await PDFParser().parse(pdf_bytes, "title.pdf", ocr_mode="disabled")
    assert "# TITLE OF THE DOCUMENT" in pages[0]["content"]
    assert "Body line one" in pages[0]["content"]

    pages = await PDFParser().parse(pdf_bytes, "title.pdf", ocr_mode="disabled", enhance_headings=False)
    assert "# TITLE" not in pages[0]["content"]
    assert "TITLE OF THE DOCUMENT" in pages[0]["content"]


@pytest.mark.asyncio
async def test_pdf_parser_preserves_tables_and_vietnamese_headings():
    """Verify PDFParser enhances Vietnamese headings and keeps table formatting intact."""
    engine_output = [
        "Điều 1. Phạm vi điều chỉnh\n\n| STT | Tên | Số lượng |\n| --- | --- | --- |\n| 1 | Máy tính | 10 |"
    ]
    with patch("app.services.parsers.pdf_parser.extract_markdown_pages", return_value=engine_output):
        pages = await PDFParser().parse(make_text_pdf([["x"]]), "mock_table.pdf", ocr_mode="disabled")

    assert len(pages) == 1
    assert "### Điều 1. Phạm vi điều chỉnh" in pages[0]["content"]
    assert "| STT | Tên | Số lượng |" in pages[0]["content"]


@pytest.mark.asyncio
async def test_pdf_parser_falls_back_to_text_layer_when_rich_engine_fails():
    with patch("app.services.parsers.pdf_parser.extract_markdown_pages", side_effect=RuntimeError("boom")):
        pages = await PDFParser().parse(make_text_pdf([["Fallback line"]]), "f.pdf", ocr_mode="disabled")
    assert pages[0]["content"] == "Fallback line"


@pytest.mark.asyncio
async def test_pdf_parser_legacy_engine_names_still_parse():
    pdf_bytes = make_text_pdf([["Legacy engine line"]])
    for engine in ("pymupdf4llm", "pymupdf_plain", "pymupdf"):
        pages = await PDFParser().parse(pdf_bytes, "legacy.pdf", engine=engine, ocr_mode="disabled")
        assert pages[0]["content"] == "Legacy engine line", engine


def test_extract_markdown_pages_respects_requested_pages():
    pdf_bytes = make_text_pdf([["One"], ["Two"], ["Three"]])
    assert extract_markdown_pages(pdf_bytes, [0, 2]) == ["One", "Three"]
    assert extract_markdown_pages(pdf_bytes, []) == []


@pytest.mark.asyncio
async def test_pdf_parser_scanned_pdf_goes_through_ocr():
    """A PDF whose pages are only images is detected as scanned and each page is OCR'd from a JPEG render."""
    pdf_bytes = make_image_pdf(2)
    with patch("app.services.ocr_service.ocr_service.is_configured", return_value=True), \
         patch("app.services.ocr_service.ocr_service.ocr_image", new_callable=AsyncMock) as mock_ocr:
        mock_ocr.side_effect = ["Van ban OCR trang mot", "Van ban OCR trang hai"]
        pages = await PDFParser().parse(pdf_bytes, "scan.pdf")

    assert mock_ocr.await_count == 2
    for call in mock_ocr.await_args_list:
        assert call.args[0][:3] == JPEG_MAGIC
        assert call.kwargs["mime_type"] == "image/jpeg"
        assert call.kwargs["prompt"] == PDFParser.DEFAULT_OCR_PROMPT
    assert [p["page_number"] for p in pages] == [1, 2]
    assert [p["is_ocr"] for p in pages] == [True, True]
    assert sorted(p["content"] for p in pages) == ["Van ban OCR trang hai", "Van ban OCR trang mot"]


@pytest.mark.asyncio
async def test_pdf_parser_scanned_pdf_without_ocr_keeps_empty_pages():
    with patch("app.services.ocr_service.ocr_service.is_configured", return_value=False), \
         patch("app.services.ocr_service.ocr_service.ocr_image", new_callable=AsyncMock) as mock_ocr:
        pages = await PDFParser().parse(make_image_pdf(1), "scan.pdf")

    assert mock_ocr.await_count == 0
    assert pages == [{"content": "", "page_number": 1, "total_doc_pages": 1, "is_ocr": False, "ocr_required": True, "char_count": 0, "word_count": 0}]


@pytest.mark.asyncio
async def test_pdf_parser_text_pdf_is_not_sent_to_ocr():
    with patch("app.services.ocr_service.ocr_service.is_configured", return_value=True), \
         patch("app.services.ocr_service.ocr_service.ocr_image", new_callable=AsyncMock) as mock_ocr:
        pages = await PDFParser().parse(make_text_pdf([["A full line of real text that is long enough to count."]]), "t.pdf")

    assert mock_ocr.await_count == 0
    assert pages[0]["is_ocr"] is False


@pytest.mark.asyncio
async def test_pdf_parser_vision_fallback_receives_jpeg_render():
    vision = MagicMock()
    vision.analyze_image = AsyncMock(
        return_value="Noi dung trang scan do mo hinh vision doc ra, du dai de duoc chap nhan la van ban hop le."
    )
    with patch("app.services.ocr_service.ocr_service.is_configured", return_value=False):
        pages = await PDFParser().parse(make_image_pdf(1), "scan.pdf", vision_provider=vision)

    vision.analyze_image.assert_awaited_once()
    assert vision.analyze_image.await_args.args[0][:3] == JPEG_MAGIC
    assert vision.analyze_image.await_args.kwargs["mime_type"] == "image/jpeg"
    assert pages[0]["is_ocr"] is True
    assert "mo hinh vision" in pages[0]["content"]
