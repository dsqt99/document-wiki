# 02 · Xử lý tài liệu đầu vào

Điểm vào hiện tại của Arkon: `kb_service._extract_text_from_file` ([app/services/kb_service.py:214](../../../app/services/kb_service.py)), trả về `list[{"content", "page_number"}]`. Sau đó `image_service.extract_images` → `source_outline.build_outline` → `assemble_full_text`.

**Vấn đề gốc:** `build_outline` chỉ nhận heading dạng `#` (ATX). PyMuPDF `get_text()` và `mammoth.extract_raw_text` **không bao giờ sinh `#`**, nên outline của hầu hết PDF/DOCX là rỗng. Hệ quả dây chuyền: MAP chunker rơi về `_sliding_window_chunks`, không có `section_path`, wiki mất cấu trúc. **Sửa parser để ra markdown có heading là việc đem lại nhiều giá trị nhất.**

---

## 1. PDF có sẵn lớp chữ

### Hiện trạng Arkon
```python
# kb_service.py:236
text = (page.get_text() or "").strip()
```
Chữ thô, không heading, bảng bị trộn thành dòng, cột báo bị đọc lẫn, header/footer (số trang, "CỘNG HÒA XÃ HỘI...") lặp lại trên mọi trang.

### WeKnora làm gì
`docreader/parser/pdf_parser.py` (pypdfium2):
- Thứ tự đọc bằng XY-cut (chia cột).
- Đoán heading theo cỡ chữ.
- Lọc chữ ẩn, bỏ dòng lặp ở nhiều trang (header/footer), bỏ mảnh vụn biểu đồ.
- Trích hình nhúng, lọc logo/icon, tối đa 50 hình/tài liệu.
- Engine nâng cao cắm ngoài: MinerU (`internal/infrastructure/docparser/mineru_converter.go`), PaddleOCR-VL (`paddleocr_vl_converter.go`), OpenDataLoader.
- Chọn engine theo loại file: `ChunkingConfig.ResolveParserEngine`, gộp cấu hình tenant + lần upload.

### Đề xuất cho Arkon

**Bước 1 (nhanh, 0.5–1 ngày): chuyển sang `pymupdf4llm`.** Cùng họ PyMuPDF đã có, cho markdown có heading (theo cỡ chữ), bảng markdown, thứ tự đọc nhiều cột, và tách theo trang.

```python
# phác thảo — kb_service.py
import pymupdf4llm, fitz

doc = fitz.open(stream=file_data, filetype="pdf")
chunks = pymupdf4llm.to_markdown(
    doc,
    page_chunks=True,        # trả list theo trang, giữ page_number
    write_images=False,      # ảnh đã có image_service xử lý riêng
    table_strategy="lines_strict",
    show_progress=False,
)
for i, c in enumerate(chunks):
    pages_data.append({"content": c["text"].strip(), "page_number": i + 1})
```

Cần kiểm tra:
- Heading tiếng Việt (in đậm, cỡ chữ gần bằng thân) có được nhận không. Nếu không, bổ sung heuristic: dòng in đậm/viết hoa khớp `^(CHƯƠNG|Chương|MỤC|Mục|Điều)\s+` → gán `##`/`###`.
- Tốc độ trên PDF 300+ trang.

**Bước 2: bỏ header/footer lặp.** Học WeKnora: dòng nào (sau khi chuẩn hoá số) xuất hiện ở ≥ 50% số trang, nằm ở 2 dòng đầu/cuối trang → bỏ.

```python
from collections import Counter
import re

def strip_repeated_lines(pages: list[str], ratio=0.5) -> list[str]:
    norm = lambda s: re.sub(r"\d+", "#", s.strip().lower())
    edge = Counter()
    for p in pages:
        lines = [l for l in p.splitlines() if l.strip()]
        for l in set(lines[:2] + lines[-2:]):
            edge[norm(l)] += 1
    bad = {k for k, v in edge.items() if v >= max(3, ratio * len(pages))}
    return ["\n".join(l for l in p.splitlines() if norm(l) not in bad) for p in pages]
```

**Bước 3: lớp engine có thể cắm.** Tạo `app/services/parsers/` với interface:

```python
class ParserEngine(Protocol):
    name: str
    def supports(self, ext: str) -> bool: ...
    async def parse(self, data: bytes, file_name: str, opts: ParseOptions) -> ParseResult: ...

# ParseResult: pages: list[PageResult(markdown, page_number, is_scanned, images, tables)]
```

Engine gợi ý: `builtin` (pymupdf4llm), `docling` (IBM, chạy local, bảng tốt, có OCR), `mineru` (layout tốt nhất cho tài liệu phức tạp, cần GPU). Chọn engine theo `KnowledgeType` (thêm cột `parser_engine` + `parser_options` JSON) và cho phép ghi đè khi upload.

---

## 2. Nhận diện trang scan và OCR

### Hiện trạng Arkon
Chỉ OCR khi `text == ""`. Bỏ sót:
- PDF scan có lớp OCR kém do máy scan tự tạo (chữ rác, sai dấu).
- Trang lai: chữ in + ảnh chụp đính kèm, con dấu, chữ ký, bảng dạng ảnh.
- Trang chỉ có vài ký tự (số trang).

Prompt OCR không nhắc tiếng Việt; không kiểm tra chất lượng kết quả.

### WeKnora làm gì
- `SCAN_IMAGE_AREA_RATIO = 0.5`, `SCAN_MIN_CHARS_PER_PAGE = 10`: ảnh phủ > 50% trang **hoặc** < 10 ký tự → coi là trang scan, render JPEG, gắn `image_source_type=scanned_pdf`.
- OCR bằng VLM (`internal/application/service/image_multimodal.go`), prompt riêng cho trang scan, **prompt do hệ thống quản lý** (chỉ dẫn tuỳ biến của KB không lọt vào).
- Tuỳ chọn gọi VLM lần 1 để quan sát thuộc tính ảnh, rồi mới quyết định có OCR không (`DecideOCR`).
- Kết quả thành chunk riêng `image_ocr` / `image_caption`, có `ParentChunkID` trỏ về chunk chữ.

### Đề xuất cho Arkon

```python
VI_CHARS = set("aăâbcdđeêghiklmnoôơpqrstuưvxyáàảãạắằẳẵặấầẩẫậéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ")

def page_needs_ocr(page: fitz.Page, text: str) -> tuple[bool, str]:
    area = page.rect.width * page.rect.height
    img_area = sum(
        (r.width * r.height) for info in page.get_image_info() for r in [fitz.Rect(info["bbox"])]
    )
    if len(text.strip()) < 10:
        return True, "empty"
    if img_area / area > 0.5:
        return True, "image_dominant"
    # chất lượng lớp chữ: tỷ lệ ký tự rác / ký tự lạ
    letters = [c for c in text.lower() if c.isalpha()]
    if letters:
        bad = sum(1 for c in letters if c not in VI_CHARS)
        if bad / len(letters) > 0.15 or text.count("�") > 5:
            return True, "garbled_text_layer"
    return False, ""
```

Cải thiện prompt OCR (`kb_service.py`, khối `ocr_prompt`):
- Nói rõ: "Văn bản tiếng Việt, giữ nguyên dấu; văn bản hành chính Việt Nam; giữ Quốc hiệu, số hiệu, trích yếu; Chương/Mục/Điều dùng heading markdown; bảng dùng markdown table; bỏ qua con dấu và chữ ký, ghi `[Con dấu]`/`[Chữ ký]`."
- Lưu lý do OCR (`empty` / `image_dominant` / `garbled_text_layer`) vào metadata trang để thống kê.

Kiểm tra sau OCR:
- Kết quả rỗng hoặc lặp một cụm nhiều lần (VLM bị lặp) → đánh dấu `ocr_failed`, không nhét vào `full_text`.
- Lưu cả văn bản gốc (lớp chữ cũ) lẫn văn bản OCR để có thể so sánh.

Song song hoá: hiện chạy 5 trang/lượt; thêm semaphore theo cấu hình và timeout mỗi trang.

---

## 3. DOCX

### Hiện trạng
`mammoth.extract_raw_text` ([kb_service.py:365](../../../app/services/kb_service.py)) → mất heading, bảng, danh sách.

### WeKnora
`Docx2Parser = FirstParser(MarkitdownParser, DocxParser)`; `docx_merge.py` điền giá trị ô gộp dọc trước khi chuyển bảng.

### Đề xuất
- Đổi sang `mammoth.convert_to_markdown` (đã có thư viện) **hoặc** `markitdown` (bảng tốt hơn).
- Style map cho văn bản Việt dùng style tuỳ biến: `p[style-name='Heading 1'] => h1`, `p[style-name^='Chuong'] => h2`…
- Ô gộp: dùng python-docx duyệt `tc.vMerge` để điền lại giá trị trước khi xuất bảng (theo `docx_merge.py`).
- DOCX không có số trang → đặt `page_number=None`, dùng `section_path` từ heading.
- Ảnh trong DOCX có thể là bản scan dán vào (rất phổ biến trong văn bản hành chính) → cho OCR ảnh DOCX có kích thước lớn (ví dụ > 800px cạnh dài), không chỉ caption.

---

## 4. DOC (Word 97-2003)

Hiện Arkon từ chối. WeKnora: LibreOffice → DOCX (subprocess có sandbox), dự phòng antiword.

```dockerfile
# Dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends libreoffice-writer-nogui fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*
```
```python
async def doc_to_docx(data: bytes) -> bytes:
    with tempfile.TemporaryDirectory() as d:
        src = Path(d, "in.doc"); src.write_bytes(data)
        proc = await asyncio.create_subprocess_exec(
            "soffice", "--headless", "--norestore", "--convert-to", "docx", "--outdir", d, str(src),
            env={**os.environ, "HOME": d},   # tránh khoá profile khi chạy song song
        )
        await asyncio.wait_for(proc.wait(), timeout=120)
        return Path(d, "in.docx").read_bytes()
```
Lưu ý: LibreOffice không chịu chạy song song với cùng profile → mỗi lần một `HOME` tạm, hoặc giới hạn 1 worker chuyển đổi. Tăng dung lượng image khoảng 300–500MB.

Có thể dùng cùng cơ chế cho `.ppt`, `.xls` cũ.

---

## 5. Excel / CSV

### Hiện trạng
pandas → `df.to_markdown()`, mỗi sheet là một "trang". Sheet 5.000 dòng thành một bảng markdown khổng lồ: embedding vô nghĩa, LLM MAP tốn token.

### WeKnora
- `ExcelParser`: sửa file lỗi (`xlsx_repair.py`), điền ô gộp (`xlsx_merge.py`), mỗi dòng thành `cột: giá trị, cột: giá trị`.
- Chunker gom dòng, giữ locator (sheet, dòng).
- `DataTableSummaryService` (`extract.go`): LLM viết **tóm tắt bảng** và **mô tả từng cột** → chunk `table_summary`, `table_column`.
- Khi hỏi: DuckDB chạy SQL trên bảng (`chat_pipeline/data_analysis.go`, tool `data_analysis`).

### Đề xuất cho Arkon
1. **Nhận diện header**: dòng đầu tiên không rỗng có ≥ 60% ô là chuỗi, không phải số → header. Xử lý header nhiều tầng (ô gộp ngang) bằng cách nối "Cha / Con".
2. **Điền ô gộp** bằng openpyxl `ws.merged_cells.ranges` trước khi đưa vào pandas.
3. **Biểu diễn theo dòng** cho chunk verbatim:
   ```
   [Sheet: Danh sách | Dòng 15]
   Họ tên: Nguyễn Văn A; Đơn vị: Phòng PC06; Chức vụ: ...
   ```
   Gom 20–50 dòng/chunk, lặp lại tên cột ở mỗi chunk.
4. **Chunk tóm tắt bảng**: số dòng, tên cột, kiểu dữ liệu, 5 dòng mẫu, LLM viết 3–5 câu mô tả.
5. **Chế độ bảng dữ liệu**: nếu là bảng dữ liệu thuần (danh sách, thống kê) → **không đi MRP wiki**, đi đường verbatim + lưu Parquet trong MinIO. Thêm MCP tool `query_table(source_id, sql)` chạy DuckDB (chỉ SELECT, có timeout, giới hạn số dòng trả về).
6. CSV: dò encoding (`charset-normalizer`), dò dấu phân cách (`csv.Sniffer`). File CSV xuất từ phần mềm Việt Nam hay dùng `cp1258`/`utf-16`.

---

## 6. Ảnh, PPTX, HTML/URL

| Mục | Đề xuất |
|---|---|
| Ảnh upload lẻ (jpg/png) | Hiện rơi vào content-core. Tạo đường riêng: OCR (nếu có chữ) + caption, lưu như 1 trang |
| Lọc ảnh | Đang bỏ < 2KB. Thêm lọc theo kích thước < 64px (như WeKnora), lọc ảnh trùng hash (logo lặp mọi trang) |
| PPTX | Dùng `python-pptx` hoặc markitdown: mỗi slide là một trang, lấy notes, trích ảnh slide |
| URL | Thay dự phòng "lưu HTML thô" bằng `trafilatura.extract(html, output_format="markdown", include_tables=True)`. Chặn SSRF (không cho IP nội bộ) |
| URL scope | `add_url_source` luôn đặt `GLOBAL` → nhận `scope_type` + `department_ids` như upload file |

---

## 7. Chuẩn hoá văn bản (bắt buộc cho tiếng Việt)

WeKnora có `sanitizeReadResult` (sửa UTF-8 lỗi, chuẩn hoá xuống dòng). Với tiếng Việt cần thêm **NFC**: văn bản copy từ Word/PDF có thể ở dạng tổ hợp (`e` + dấu mũ + dấu sắc tách rời). Khi đó regex `Điều`, full-text search và so khớp slug đều trượt.

```python
import unicodedata, re

def normalize_text(s: str) -> str:
    s = s.encode("utf-8", "replace").decode("utf-8")
    s = unicodedata.normalize("NFC", s)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[​‌‍﻿]", "", s)      # zero-width
    s = s.replace(" ", " ")
    s = re.sub(r"[ \t]+\n", "\n", s)
    s = re.sub(r"\n{4,}", "\n\n\n", s)
    return s
```
Gọi ngay sau mỗi engine parser, và cả với **câu hỏi** trước khi tìm kiếm.

Tuỳ chọn: chuẩn hoá kiểu bỏ dấu cũ/mới (`hoà` ↔ `hòa`, `thuỷ` ↔ `thủy`) cho nhánh tìm kiếm.

---

## 8. Chống trùng file và giới hạn upload

- Thêm cột `Source.content_hash` (SHA-256), index unique theo `(content_hash, scope)` hoặc chỉ cảnh báo.
- Upload trùng → trả về source cũ kèm cờ `duplicate=true`; cho phép "tải lên phiên bản mới" để thay thế (thay vì tạo nguồn mới).
- Upload hiện đọc toàn bộ file vào RAM ([sources.py:613](../../../app/routers/sources.py)) → đọc từng khối, tính hash khi stream, giới hạn `max_upload_mb` trong settings.

---

## 9. Chunk ảnh/OCR thành đơn vị riêng (học WeKnora)

Hiện Arkon "nướng" caption vào `full_text`. Đề xuất bổ sung (không thay thế):
- Mỗi ảnh có caption/OCR → một chunk verbatim loại `image_caption` / `image_ocr`, trỏ về `source_id` + `page_number` + `image_id`.
- Khi tìm trúng chunk ảnh → trả kèm link ảnh (`image://uuid` → presigned URL MinIO). Hữu ích cho sơ đồ tổ chức, biểu mẫu.

---

## 10. Tiêu chí nghiệm thu lớp parser

Dựng bộ mẫu `tests/fixtures/docs/` (15–20 file thật, đã ẩn thông tin):

| Loại | Tiêu chí |
|---|---|
| Luật/Nghị định PDF có chữ | Outline nhận đủ Chương/Điều; không còn header/footer lặp |
| Văn bản scan PDF | 100% trang được OCR; tỷ lệ ký tự tiếng Việt hợp lệ > 95% |
| PDF lai (có con dấu) | Trang có con dấu vẫn có chữ |
| DOCX có bảng | Bảng thành markdown table, ô gộp đúng |
| DOC cũ | Chuyển được, không lỗi |
| Excel danh sách 5.000 dòng | Không đi MRP; chunk theo dòng có tên cột; `query_table` trả đúng |
| CSV cp1258 | Đọc đúng dấu |

Viết test `pytest` so sánh outline/từ khoá kỳ vọng, chạy mỗi lần đổi parser.
