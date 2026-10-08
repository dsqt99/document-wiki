# Thiết Kế: Cấu Hình Xử Lý Tài Liệu, OCR & Công Cụ Test Preview Trong Settings

## 1. Mục tiêu & Tổng quan
Hệ thống Wiki Văn bản hiện tại đã hỗ trợ bóc tách tài liệu (PyMuPDF, PyMuPDF4LLM, docx, excel) và tích hợp OCR chuyên dụng (GLM-OCR OpenAI-compatible) cùng Vision Model fallback. Tuy nhiên, các cấu hình này hiện đang cố định trong biến môi trường `.env`, quản trị viên không thể tinh chỉnh linh hoạt trên UI Settings và không có công cụ trực tiếp để kiểm tra (test) kết quả bóc tách/OCR của một file cụ thể trước khi đưa vào luồng ingestion thực tế.

Mục tiêu của tính năng:
1. **Quản lý cấu hình linh hoạt (Dynamic Config)**: Cho phép cấu hình OCR (URL, API key, Model, Prompt, Chế độ quét) và cơ chế bóc tách PDF (Engine, chuẩn hóa đề mục, lọc header/footer, Vision fallback) lưu trữ trong Database (`AppConfig`), có fallback về `.env`.
2. **Khu vực Test & Preview trực quan (Extraction & OCR Playground)**: Cung cấp 2 chế độ test ngay trong trang Settings:
   - **Test OCR đơn trang / ảnh**: Tải ảnh tài liệu hoặc PDF 1 trang để chạy OCR tức thì, xem trước kết quả text/markdown, thời gian xử lý và model sử dụng.
   - **Test bóc tách tài liệu (Document Extraction Preview)**: Tải tài liệu (PDF, Word, Text...), tùy chọn số trang xem trước, hiển thị báo cáo thống kê (tổng trang, trang OCR, số từ, thời gian) và giao diện duyệt từng trang dạng Markdown kèm nhãn phân biệt trang scan/text gốc.

---

## 2. Kiến trúc Backend & Dữ liệu

### 2.1 Cấu hình động trong Database (`app/services/config_service.py`)
Mở rộng danh sách `ALL_CONFIG_KEYS` và logic mã hóa / giải mã:
- **Khóa nhạy cảm (mã hóa Fernet):**
  - `ocr_api_key`
- **Khóa thông thường:**
  - `ocr_base_url`: Endpoint dịch vụ OCR (mặc định lấy từ `settings.ocr_base_url`).
  - `ocr_model`: Tên mô hình OCR (mặc định lấy từ `settings.ocr_model`).
  - `ocr_prompt`: Lời nhắc hệ thống hướng dẫn bóc tách cấu trúc bảng biểu, đề mục.
  - `ocr_mode`: `auto` (chỉ OCR trang scan/ảnh), `force_ocr` (ép OCR mọi trang), `disabled` (tắt OCR).
  - `ocr_fallback_vision`: `true` / `false` (fallback sang Vision model khi OCR server không phản hồi).
  - `pdf_parser_engine`: `pymupdf4llm` (ưu tiên markdown/bảng biểu) hoặc `pymupdf_plain` (text thuần).
  - `pdf_strip_headers_footers`: `true` / `false` (lọc tiêu ngữ và header/footer lặp lại).
  - `pdf_enhance_headings`: `true` / `false` (nhận diện và gán thứ bậc Markdown `#`, `##` cho Phần, Chương, Mục, Điều).

### 2.2 Cải tiến `OCRService` (`app/services/ocr_service.py`)
- Cho phép nhận cấu hình động từ `ConfigService` hoặc các tham số ghi đè (`override_base_url`, `override_api_key`, `override_model`).
- Thêm phương thức `test_connection()` để kiểm tra kết nối tới endpoint OCR mà không cần file lớn.
- Bổ sung hỗ trợ OCR trực tiếp từ `bytes` ảnh hoặc render từ trang PDF.

### 2.3 Cải tiến `PDFParser` (`app/services/parsers/pdf_parser.py`)
- Hỗ trợ tham số cấu hình:
  - `engine`: Chọn giữa `pymupdf4llm` và `pymupdf_plain`.
  - `ocr_mode`: `auto`, `force_ocr`, `disabled`.
  - `strip_headers_footers`: Bật/tắt hàm `strip_repeated_headers_and_footers`.
  - `enhance_headings`: Bật/tắt hàm `enhance_vietnamese_headings`.
  - `max_pages`: Giới hạn số trang xử lý (dành cho chế độ preview nhanh).
- Ghi nhận trạng thái từng trang (`is_ocr: bool`) để trả về cho giao diện preview.

### 2.4 API Endpoints Mới (`app/routers/admin_settings.py`)

#### A. `POST /api/settings/test-ocr`
- **Tham số (Form/Multipart):**
  - `file`: File upload (`UploadFile`) - chấp nhận ảnh (`image/png`, `image/jpeg`, `image/webp`) hoặc `.pdf`.
  - `override_base_url` (tùy chọn)
  - `override_api_key` (tùy chọn)
  - `override_model` (tùy chọn)
  - `override_prompt` (tùy chọn)
- **Xử lý:**
  - Nếu là PDF: render trang đầu tiên thành ảnh JPEG (2x matrix).
  - Gửi tới `ocr_service.ocr_image`.
  - Tính toán `latency_ms`, số ký tự, số từ.
- **Phản hồi:**
  ```json
  {
    "success": true,
    "text": "# Trích xuất văn bản...",
    "model": "ggml-org/GLM-OCR-GGUF:f16",
    "latency_ms": 1250,
    "chars_count": 680,
    "words_count": 120,
    "error": null
  }
  ```

#### B. `POST /api/settings/test-extraction`
- **Tham số (Form/Multipart):**
  - `file`: File upload (`UploadFile`) - PDF, DOCX, XLSX, TXT...
  - `max_pages`: `int` (mặc định: 3, 0 = tất cả)
  - `engine` (tùy chọn ghi đè)
  - `ocr_mode` (tùy chọn ghi đè)
  - `strip_headers_footers` (tùy chọn ghi đè)
  - `enhance_headings` (tùy chọn ghi đè)
- **Xử lý:**
  - Đọc file bytes.
  - Sử dụng cấu hình hiện hành từ DB kết hợp tham số ghi đè.
  - Chạy qua pipeline trích xuất với giới hạn `max_pages`.
  - Trả về danh sách trang và thống kê tổng hợp.
- **Phản hồi:**
  ```json
  {
    "success": true,
    "file_name": "tailieu.pdf",
    "file_type": "pdf",
    "stats": {
      "total_pages": 10,
      "preview_pages_count": 3,
      "ocr_pages_count": 1,
      "total_words": 1420,
      "total_chars": 8200,
      "latency_ms": 2840
    },
    "pages": [
      {
        "page_number": 1,
        "content": "...",
        "is_ocr": false,
        "char_count": 2500,
        "word_count": 420
      },
      {
        "page_number": 2,
        "content": "...",
        "is_ocr": true,
        "char_count": 3100,
        "word_count": 550
      }
    ],
    "error": null
  }
  ```

---

## 3. Thiết Kế Giao Diện Frontend (`frontend/src/app/(portal)/settings`)

### 3.1 Thẻ Cấu Hình: `DocumentProcessingSettingsCard`
- **Mục Cấu hình OCR:**
  - Input: OCR Base URL (kèm nút Test kết nối).
  - Input: OCR API Key (kiểu password, hỗ trợ che dấu `••••` và lưu an toàn).
  - Input: OCR Model Name.
  - Textarea: Custom OCR Prompt (có nút "Đặt về mặc định").
  - Radio/Select: Chế độ OCR (`Tự động (chỉ trang scan)`, `Ép OCR toàn bộ`, `Tắt OCR`).
  - Toggle Switch: Cho phép fallback sang Vision Model nếu OCR lỗi.
- **Mục Cấu hình Bóc tách PDF & Văn bản:**
  - Select: Bộ công cụ bóc tách PDF (`PyMuPDF4LLM` - Khuyến nghị cho bảng biểu / `PyMuPDF Plain Text`).
  - Toggle Switch: Tự động lọc tiêu ngữ, đầu trang/chân trang lặp lại.
  - Toggle Switch: Tự động chuẩn hóa tiêu đề thứ bậc pháp lý tiếng Việt.
- Nút "Lưu cấu hình bóc tách & OCR": Gọi `PUT /api/settings` cập nhật đồng bộ vào DB.

### 3.2 Thẻ Môi Trường Thử Nghiệm: `ExtractionPlaygroundCard`
Gồm 2 Tab chuyển đổi:
- **Tab 1: Thử nghiệm OCR Nhanh:**
  - Khu vực kéo thả hoặc chọn file ảnh (`.png`, `.jpg`, `.jpeg`, `.webp`) hoặc chọn 1 file `.pdf`.
  - Tùy chọn nhanh: Nhập prompt thử nghiệm hoặc dùng prompt mặc định.
  - Nút "Bắt đầu OCR" kèm trạng thái loading spinner.
  - Khung kết quả:
    - Thẻ thống kê: Tốc độ xử lý (ms), số từ, số ký tự, model thực thi.
    - Bộ chuyển đổi hiển thị: Tab "Rendered Markdown" (xem bảng biểu, format đẹp) và Tab "Raw Markdown" (kèm nút Copy).
- **Tab 2: Thử nghiệm Trích xuất Tài liệu (Document Parser Preview):**
  - Kéo thả file tài liệu (`.pdf`, `.docx`, `.xlsx`, `.txt`).
  - Bộ chọn số trang xem trước: `1 trang`, `3 trang đầu`, `5 trang đầu`, hoặc `Tất cả`.
  - Nút "Trích xuất & Xem trước".
  - Khung kết quả:
    - Thanh tóm tắt: Tổng số trang trong file, số trang đã xem trước, số trang kích hoạt OCR, tổng từ bóc tách được, thời gian hoàn thành.
    - Bộ điều hướng trang trực quan: Tabs hoặc Pagination cho từng trang.
    - Mỗi trang hiển thị huy hiệu:
      - `[Văn bản gốc]` (màu xanh lá) đối với trang trích xuất text trực tiếp.
      - `[Trang scan - Đã OCR]` (màu tím/xanh dương) đối với trang được xử lý bằng OCR.
    - Trình xem nội dung Markdown chi tiết của từng trang.

---

## 4. Kịch bản Kiểm Thử & Tiêu Chí Thành Công (Acceptance Criteria)

1. **Lưu & Đọc Cấu hình**:
   - Thay đổi các giá trị OCR URL, Key, Model, Engine PDF và lưu thành công.
   - Khi tải lại trang, các giá trị hiển thị đúng giá trị đã lưu (Key được che dấu an toàn).
   - Backend `ConfigService` trả về đúng giá trị ưu tiên từ DB thay vì giá trị cố định.
2. **Kiểm tra kết nối OCR**:
   - Nhấn nút "Kiểm tra kết nối", nếu thông tin hợp lệ hiển thị thông báo thành công cùng độ trễ.
3. **Test OCR nhanh**:
   - Tải lên 1 ảnh hóa đơn / trang văn bản chụp.
   - Nhận về kết quả OCR định dạng Markdown với bảng biểu nguyên vẹn.
4. **Test Document Extraction**:
   - Tải lên file PDF hỗn hợp (có cả trang văn bản số hóa và trang scan).
   - Hệ thống bóc tách đúng, hiển thị trang số hóa là `[Văn bản gốc]` và trang scan là `[Trang scan - Đã OCR]`.
   - Xem trước hiển thị mượt mà, phân trang rõ ràng, không gây treo giao diện hay crash worker.
