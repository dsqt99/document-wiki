# Document Processing & OCR Settings and Preview Playground Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thêm các tùy chọn cấu hình động cho trích xuất văn bản (PDF engine, OCR chuyên dụng, chuẩn hóa đề mục, lọc header/footer) vào Settings và xây dựng công cụ Test & Preview kết quả bóc tách/OCR trực tiếp trên giao diện Admin.

**Architecture:** Mở rộng `AppConfig` trong Database thông qua `ConfigService` lưu trữ các cấu hình OCR và PDF. Cập nhật `OCRService` và `PDFParser` nhận cấu hình động cùng tùy chọn `max_pages` & `is_ocr` tagging. Xây dựng 2 API endpoint `/api/settings/test-ocr` và `/api/settings/test-extraction` trong `admin_settings.py`. Xây dựng 2 thẻ giao diện Next.js `DocumentProcessingSettingsCard` và `ExtractionPlaygroundCard` trong Settings.

**Tech Stack:** FastAPI, PyMuPDF (fitz) & PyMuPDF4LLM, OpenAI-compatible OCR client, Next.js 15, TailwindCSS, React Markdown, lucide-react / Material Symbols.

---

### Task 1: Cấu hình động trong ConfigService cho OCR & PDF Processing

**Files:**
- Modify: `app/services/config_service.py`
- Test: `tests/test_config_service_ocr.py`

- [ ] **Step 1: Viết test cho các key cấu hình OCR & PDF mới trong ConfigService**
Tạo file `tests/test_config_service_ocr.py`: kiểm tra get/set cho `ocr_base_url`, `ocr_api_key`, `ocr_model`, `ocr_prompt`, `ocr_mode`, `pdf_parser_engine`, `pdf_strip_headers_footers`, `pdf_enhance_headings`, và đảm bảo `ocr_api_key` được mã hóa Fernet và che dấu trên UI.

- [ ] **Step 2: Chạy test để kiểm tra lỗi FAIL (chưa có key mới)**
Chạy: `pytest tests/test_config_service_ocr.py -v`
Kỳ vọng: FAIL

- [ ] **Step 3: Cập nhật `app/services/config_service.py`**
Bổ sung:
  - `_is_sensitive(key)` bao gồm `"ocr_api_key"`
  - `ALL_CONFIG_KEYS` bổ sung các key:
    - `"ocr_base_url"`, `"ocr_api_key"`, `"ocr_model"`, `"ocr_prompt"`
    - `"ocr_mode"` (`auto` / `force_ocr` / `disabled`)
    - `"ocr_fallback_vision"` (`true` / `false`)
    - `"pdf_parser_engine"` (`pymupdf4llm` / `pymupdf_plain`)
    - `"pdf_strip_headers_footers"` (`true` / `false`)
    - `"pdf_enhance_headings"` (`true` / `false`)
  - Trong phương thức `get()`, nếu DB chưa có giá trị, fallback sang `settings.ocr_base_url`, `settings.ocr_api_key`, `settings.ocr_model`, và giá trị mặc định hợp lý cho các trường khác.

- [ ] **Step 4: Chạy lại test để đảm bảo PASS**
Chạy: `pytest tests/test_config_service_ocr.py -v`
Kỳ vọng: PASS

- [ ] **Step 5: Commit task 1**
```bash
git add app/services/config_service.py tests/test_config_service_ocr.py
git commit -m "feat(config): add dynamic OCR and PDF extraction config keys"
```

---

### Task 2: Cải tiến OCRService hỗ trợ cấu hình động & kiểm tra kết nối

**Files:**
- Modify: `app/services/ocr_service.py`
- Test: `tests/test_ocr_service_dynamic.py`

- [ ] **Step 1: Viết test cho OCRService**
Tạo file `tests/test_ocr_service_dynamic.py`: kiểm tra hàm `test_connection()` và khả năng khởi tạo client với cấu hình override hoặc cấu hình từ config.

- [ ] **Step 2: Chạy test để kiểm tra FAIL**
Chạy: `pytest tests/test_ocr_service_dynamic.py -v`
Kỳ vọng: FAIL (chưa có `test_connection` và hỗ trợ override params)

- [ ] **Step 3: Cập nhật `app/services/ocr_service.py`**
  - Bổ sung hàm `get_effective_config()` đọc cấu hình từ `db` hoặc tham số ghi đè.
  - Cập nhật hàm `ocr_image()` cho phép nhận `base_url`, `api_key`, `model`, `prompt` tùy chọn khi gọi.
  - Thêm phương thức `test_connection(base_url, api_key, model)`: gửi request kiểm tra danh sách model (`client.models.list()`) hoặc tạo prompt mẫu 1 từ để xác nhận kết nối và đo độ trễ `latency_ms`.

- [ ] **Step 4: Chạy lại test để đảm bảo PASS**
Chạy: `pytest tests/test_ocr_service_dynamic.py -v`
Kỳ vọng: PASS

- [ ] **Step 5: Commit task 2**
```bash
git add app/services/ocr_service.py tests/test_ocr_service_dynamic.py
git commit -m "feat(ocr): add connection test and dynamic parameter support in OCRService"
```

---

### Task 3: Cải tiến PDFParser với Engine Tùy Biến, OCR Mode & Giới Hạn Trang

**Files:**
- Modify: `app/services/parsers/pdf_parser.py`
- Test: `tests/test_pdf_parser_options.py`

- [ ] **Step 1: Viết test cho PDFParser**
Tạo file `tests/test_pdf_parser_options.py`:
  - Test trích xuất PDF với `max_pages=1` (chỉ trả về 1 trang đầu).
  - Test trường `is_ocr` trong kết quả từng trang.
  - Test tùy chọn bật/tắt `strip_headers_footers` và `enhance_headings`.
  - Test tùy chọn `engine="pymupdf_plain"`.

- [ ] **Step 2: Chạy test để kiểm tra FAIL**
Chạy: `pytest tests/test_pdf_parser_options.py -v`
Kỳ vọng: FAIL

- [ ] **Step 3: Cập nhật `app/services/parsers/pdf_parser.py`**
  - Thêm các tham số cho phương thức `parse()`:
    - `engine: str = "pymupdf4llm"` (`pymupdf4llm` hoặc `pymupdf_plain`)
    - `ocr_mode: str = "auto"` (`auto`, `force_ocr`, `disabled`)
    - `strip_headers_footers: bool = True`
    - `enhance_headings: bool = True`
    - `max_pages: Optional[int] = None`
    - `ocr_config: Optional[dict] = None`
  - Nếu `max_pages` được chỉ định, chỉ xử lý `min(num_pages, max_pages)`.
  - Gắn nhãn `is_ocr: bool` vào từng trang trả về (`{"content": ..., "page_number": i + 1, "is_ocr": bool, "char_count": int, "word_count": int}`).
  - Xử lý các chế độ `ocr_mode`:
    - `disabled`: Bỏ qua hoàn toàn OCR.
    - `force_ocr`: Đánh dấu toàn bộ các trang để đưa vào danh sách chạy OCR.
    - `auto`: Quét text trước và dùng `is_scanned_page`.

- [ ] **Step 4: Chạy lại test để đảm bảo PASS**
Chạy: `pytest tests/test_pdf_parser_options.py -v`
Kỳ vọng: PASS

- [ ] **Step 5: Commit task 3**
```bash
git add app/services/parsers/pdf_parser.py tests/test_pdf_parser_options.py
git commit -m "feat(parser): enhance PDFParser with engine selection, OCR mode and max_pages"
```

---

### Task 4: Xây dựng các API Endpoints Test & Preview trong Admin Settings

**Files:**
- Modify: `app/routers/admin_settings.py`
- Test: `tests/test_admin_settings_preview_api.py`

- [ ] **Step 1: Viết test cho 3 endpoint mới**
Tạo file `tests/test_admin_settings_preview_api.py`:
  - `POST /api/settings/test-ocr-connection`
  - `POST /api/settings/test-ocr` (upload ảnh giả lập hoặc PDF 1 trang)
  - `POST /api/settings/test-extraction` (upload file text hoặc PDF với `max_pages=2`)

- [ ] **Step 2: Chạy test để kiểm tra FAIL**
Chạy: `pytest tests/test_admin_settings_preview_api.py -v`
Kỳ vọng: FAIL (404 Not Found)

- [ ] **Step 3: Triển khai 3 endpoint trong `app/routers/admin_settings.py`**
  - `POST /api/settings/test-ocr-connection`: Nhận JSON `{ base_url, api_key, model }`, gọi `ocr_service.test_connection(...)`.
  - `POST /api/settings/test-ocr`: Nhận `UploadFile`, render nếu là PDF, gọi OCR, đo `latency_ms`, trả về `TestOCRResponse(success, text, model, latency_ms, chars_count, words_count, error)`.
  - `POST /api/settings/test-extraction`: Nhận `UploadFile`, các tham số override tùy chọn (`max_pages`, `engine`, `ocr_mode`), chạy trích xuất, trả về `TestExtractionResponse(success, file_name, file_type, stats, pages, error)`.

- [ ] **Step 4: Chạy lại test để đảm bảo PASS**
Chạy: `pytest tests/test_admin_settings_preview_api.py -v`
Kỳ vọng: PASS

- [ ] **Step 5: Commit task 4**
```bash
git add app/routers/admin_settings.py tests/test_admin_settings_preview_api.py
git commit -m "feat(api): implement test-ocr, test-extraction and test-ocr-connection endpoints"
```

---

### Task 5: Xây dựng Component Frontend `DocumentProcessingSettingsCard`

**Files:**
- Create: `frontend/src/components/settings/document-processing-settings-card.tsx`

- [ ] **Step 1: Triển khai `DocumentProcessingSettingsCard`**
  - Form nhập thông tin OCR:
    - Base URL, API Key (input password với icon toggle eye), Model name.
    - Custom OCR Prompt textarea kèm nút "Đặt về mặc định".
    - Nút "Kiểm tra kết nối OCR" (gọi `/api/settings/test-ocr-connection`) kèm badge trạng thái (xanh/đỏ).
  - Tùy chọn OCR Mode: Radio/Select chọn giữa `auto`, `force_ocr`, `disabled`.
  - Tùy chọn PDF Parser Engine: Dropdown chọn `pymupdf4llm` hoặc `pymupdf_plain`.
  - Các công tắc Switch:
    - Lọc Header/Footer lặp lại (`pdf_strip_headers_footers`)
    - Chuẩn hóa đề mục tiếng Việt (`pdf_enhance_headings`)
    - Fallback sang Vision Model nếu OCR lỗi (`ocr_fallback_vision`)
  - Nút "Lưu cấu hình bóc tách & OCR": gọi `PUT /api/settings`, hiển thị toast thông báo thành công.

- [ ] **Step 2: Commit task 5**
```bash
git add frontend/src/components/settings/document-processing-settings-card.tsx
git commit -m "feat(frontend): create DocumentProcessingSettingsCard"
```

---

### Task 6: Xây dựng Component Frontend `ExtractionPlaygroundCard`

**Files:**
- Create: `frontend/src/components/settings/extraction-playground-card.tsx`

- [ ] **Step 1: Triển khai `ExtractionPlaygroundCard`**
  - Giao diện 2 Tab đẹp mắt:
    - **Tab 1: Test OCR Nhanh (Ảnh / 1 Trang PDF)**:
      - Vùng kéo thả file hỗ trợ PNG, JPG, WEBP, PDF.
      - Nút "Bắt đầu Test OCR" với animation loading.
      - Kết quả hiển thị:
        - Thẻ thống kê: Tốc độ xử lý (ms), số từ, số ký tự, model sử dụng.
        - Chuyển đổi giữa 2 chế độ: **Rendered Markdown** (xem bảng biểu, đề mục) và **Raw text** kèm nút Copy.
    - **Tab 2: Test Trích Xuất Tài Liệu (Document Preview)**:
      - Kéo thả file tài liệu (PDF, DOCX, XLSX, TXT...).
      - Tùy chọn số trang preview: `1 trang`, `3 trang đầu`, `5 trang đầu`, `Toàn bộ`.
      - Nút "Trích xuất & Xem trước".
      - Kết quả hiển thị:
        - Thanh tóm tắt: Tổng số trang, số trang scan cần OCR, tổng số từ, thời gian chạy.
        - Thanh phân trang trực quan: Tabs / Pagination cho từng trang.
        - Badge trên từng trang: `[Văn bản gốc]` (xanh lá) hoặc `[Trang scan - Đã OCR]` (xanh dương).
        - Hiển thị nội dung chi tiết từng trang bằng trình xem Markdown.

- [ ] **Step 2: Commit task 6**
```bash
git add frontend/src/components/settings/extraction-playground-card.tsx
git commit -m "feat(frontend): create ExtractionPlaygroundCard with 2 test tabs"
```

---

### Task 7: Tích hợp vào Settings Page & Kiểm thử Toàn diện

**Files:**
- Modify: `frontend/src/app/(portal)/settings/page.tsx`

- [ ] **Step 1: Tích hợp 2 thẻ vào `page.tsx`**
Import và đặt `DocumentProcessingSettingsCard` và `ExtractionPlaygroundCard` vào trang Settings.

- [ ] **Step 2: Kiểm thử lint và build frontend**
Chạy: `cd frontend && npm run build` hoặc `npx tsc --noEmit`
Kỳ vọng: Không có lỗi TypeScript hay cú pháp.

- [ ] **Step 3: Chạy toàn bộ test suite backend**
Chạy: `pytest tests/test_config_service_ocr.py tests/test_ocr_service_dynamic.py tests/test_pdf_parser_options.py tests/test_admin_settings_preview_api.py -v`
Kỳ vọng: 100% tests PASS.

- [ ] **Step 4: Commit task 7**
```bash
git add frontend/src/app/\(portal\)/settings/page.tsx
git commit -m "feat(settings): integrate document processing config and extraction playground"
```
