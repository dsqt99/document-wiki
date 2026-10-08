# Kế Hoạch Triển Khai Tối Ưu Hóa Arkon (Theo Phân Tích So Sánh WeKnora)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nâng cấp toàn diện hệ thống Arkon dựa trên các thế mạnh kỹ thuật từ Tencent WeKnora (Parser đa định dạng, Hybrid Search tiếng Việt, Reranking, Parent-Child chunking, Idempotency) kết hợp với bản sắc riêng của Arkon (Lõi Wiki có con người phê duyệt, đồ thị phân cấp văn bản pháp luật nghiệp vụ Việt Nam và kiểm soát chi phí LLM).

**Architecture:** Giữ nguyên kiến trúc cốt lõi FastAPI + ARQ/Redis + PostgreSQL (pgvector + full-text search) + Next.js. Bổ sung module phân cấp văn bản pháp lý (máy trạng thái Chương/Mục/Điều/Khoản/Điểm), nâng cấp pipeline xử lý tài liệu đầu vào (PyMuPDF4LLM + OCR nhận diện trang scan + chống trùng/chuẩn hóa Unicode), tích hợp BGE-Reranker-v2-m3 và Vietnamese word segmentation (`pyvi`), đồng thời gia cố độ tin cậy vận hành của worker bằng `attempt_id` và dead-letter table.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy (Async), PostgreSQL + pgvector, ARQ (Redis), PyMuPDF4LLM, pyvi, HuggingFace TEI / Infinity (bge-reranker-v2-m3), DuckDB, Next.js 14/16, React Flow / Force Graph.

---

## Danh Mục Các Giai Đoạn (Phased Roadmap)

```
Sprint 0 (Nền tảng kiểm thử & Eval) ──► Sprint 1 (Bug P0 & Vệ sinh đầu vào) ──► Sprint 2 (Bộ Parser đa định dạng)
           (2-3 ngày)                                 (4-5 ngày)                          (5 ngày)
                                                                                             │
Sprint 5 (Excel, Ảnh & Sinh câu hỏi) ◄── Sprint 4 (Chất lượng truy xuất) ◄── Sprint 3 (Pháp luật & Legal Graph)
           (5 ngày)                                   (4-5 ngày)                          (5-6 ngày)
       │
Sprint 6 (Concept Graph & Vận hành)
           (5 ngày)
```

---

## Sprint 0: Nền Móng Kiểm Thử & Bộ Đo Retrieval (Eval Baseline)

### Task 0.1: Khởi Tạo Test Harness Với Pytest & Fixture Cơ Sở Dữ Liệu
**Files:**
- Create: `tests/conftest.py`
- Create: `tests/test_health.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Viết cấu hình `pytest.ini` hoặc khai báo trong `pyproject.toml`**
  Cấu hình `asyncio_mode = "auto"`, `pythonpath = ["."]` và cấu hình fixture database (in-memory SQLite hoặc test Postgres schema).
- [ ] **Step 2: Viết test failing `tests/test_health.py` kiểm tra health endpoint**
  ```python
  import pytest
  from httpx import AsyncClient, ASGITransport
  from app.main import app

  @pytest.mark.asyncio
  async def test_health_check():
      async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
          response = await ac.get("/health")
      assert response.status_code == 200
  ```
- [ ] **Step 3: Chạy test kiểm tra trạng thái pass/fail**
  Run: `pytest tests/test_health.py -v`
- [ ] **Step 4: Commit**
  ```bash
  git add pyproject.toml tests/conftest.py tests/test_health.py
  git commit -m "test: setup pytest harness and basic test suite"
  ```

---

### Task 0.2: Xây Dựng Bộ Fixtures Tài Liệu Mẫu & Bộ Đo Đánh Giá Retrieval (Eval Harness)
**Files:**
- Create: `tests/fixtures/docs/README.md`
- Create: `eval/questions.yaml`
- Create: `eval/retrieval_eval.py`

- [ ] **Step 1: Chuẩn bị 10-15 tài liệu thật đã khử dữ liệu nhạy cảm**
  Bao gồm: 3 Nghị định/Thông tư quy phạm pháp luật (VD: NĐ 136/2020, NĐ 50/2024), 2 Báo cáo nội bộ, 2 File scan có chữ mờ, 1 File Excel biểu mẫu.
- [ ] **Step 2: Tạo bộ câu hỏi benchmark `eval/questions.yaml` (50 - 100 câu)**
  Mỗi câu bao gồm: `id`, `question`, `expected_doc_number`, `expected_articles` (VD: `["Điều 5", "Khoản 2"]`), `expected_keywords`.
- [ ] **Step 3: Viết script tính metric `eval/retrieval_eval.py` (Recall@5, Recall@10, MRR, nDCG@10)**
  ```python
  # eval/retrieval_eval.py
  import asyncio
  import yaml
  # Đo lường kết quả tìm kiếm wiki và verbatim chunks
  # Xuất ra báo cáo baseline: eval/results/baseline_sprint0.json
  ```
- [ ] **Step 4: Chạy baseline eval và lưu kết quả đối chứng**
  Run: `python eval/retrieval_eval.py --output eval/results/baseline_sprint0.json`
- [ ] **Step 5: Commit**
  ```bash
  git add tests/fixtures/ eval/
  git commit -m "test: add document fixtures and retrieval evaluation benchmark"
  ```

---

## Sprint 1: Sửa Triệt Để Bug P0 & Bảo Vệ Tầng Dữ Liệu Đầu Vào

### Task 1.1: Sửa BUG-01 (Caption Task Kẹt Pipeline Khi Không Có Vision Provider)
**Files:**
- Modify: `app/worker.py:56, 1202-1320`
- Test: `tests/test_worker_caption_fallback.py`

- [ ] **Step 1: Viết failing test mô phỏng trường hợp upload tài liệu có ảnh khi `vision_provider` bị tắt**
  Kiểm tra rằng task phải tự động chuyển tiếp (chain) sang `ingest_map_reduce_task` hoặc `finalize_legal_source` mà không bị kẹt ở `processing`.
- [ ] **Step 2: Chạy test để xác nhận lỗi kẹt pipeline**
  Run: `pytest tests/test_worker_caption_fallback.py -v` (FAIL do return sớm không enqueue).
- [ ] **Step 3: Triển khai hàm `_chain_to_mrp(ctx, source_id, attempt_id)` trong `app/worker.py`**
  Đảm bảo mọi nhánh thoát (`not vision_provider`, `not image_records`, lỗi bắt được) đều gọi hàm chain này trong khối `finally` hoặc xử lý phân nhánh an toàn.
  Tại `enqueue_post_extraction_pipeline`, kiểm tra nếu không có vision provider được kích hoạt thì nhảy thẳng sang MRP.
- [ ] **Step 4: Chạy lại test để xác nhận pass**
  Run: `pytest tests/test_worker_caption_fallback.py -v`
- [ ] **Step 5: Commit**
  ```bash
  git add app/worker.py tests/test_worker_caption_fallback.py
  git commit -m "fix(worker): ensure image caption task reliably chains to MRP pipeline"
  ```

---

### Task 1.2: Sửa BUG-02 (Trang Luật Bỏ Qua Phạm Vi Phòng Ban) & Rà Soát Dữ Liệu
**Files:**
- Modify: `app/services/legal_service.py:456, 526, 575, 633`
- Create: `app/scripts/audit_legal_scopes.py`
- Test: `tests/test_legal_scope_enforcement.py`

- [ ] **Step 1: Viết test kiểm tra bảo mật phân quyền của trang luật**
  Tạo source với `scope_type="department"` và gán `department_id`. Xác nhận các trang wiki sinh ra từ văn bản này không được mang `scope_type="global"`.
- [ ] **Step 2: Chạy test để kiểm tra hiện tượng rò rỉ scope**
  Run: `pytest tests/test_legal_scope_enforcement.py -v` (FAIL: trang được tạo thành `global`).
- [ ] **Step 3: Sửa `app/services/legal_service.py`**
  Sử dụng cơ chế giải quyết scope tương tự MRP (`_resolve_wiki_scopes`), tôn trọng `source.scope_type` và danh sách `SourceDepartment`.
- [ ] **Step 4: Viết script `audit_legal_scopes.py` để rà soát và khắc phục các trang bị gán nhầm trong database**
- [ ] **Step 5: Chạy lại test để xác nhận hoàn tất**
  Run: `pytest tests/test_legal_scope_enforcement.py -v`
- [ ] **Step 6: Commit**
  ```bash
  git add app/services/legal_service.py app/scripts/audit_legal_scopes.py tests/test_legal_scope_enforcement.py
  git commit -m "fix(legal): enforce department scope isolation on legal document pages"
  ```

---

### Task 1.3: Sửa BUG-03 (`retry_source` Ghi Đè Status Gây Sai Lệch Định Tuyến)
**Files:**
- Modify: `app/routers/sources.py:906-925`
- Test: `tests/test_source_retry.py`

- [ ] **Step 1: Viết test mô phỏng retry một source đang ở trạng thái `plan_ready`**
  Xác nhận source tiếp tục thực hiện phê duyệt/biên soạn thay vì chạy lại từ đầu trích xuất file (`ingest_file_task`).
- [ ] **Step 2: Chạy test xác nhận lỗi**
  Run: `pytest tests/test_source_retry.py -v`
- [ ] **Step 3: Sửa `app/routers/sources.py`**
  Lưu `prev_status = source.status` trước khi set `source.status = "pending"`, sử dụng `prev_status` để định tuyến chính xác sang task tương ứng.
- [ ] **Step 4: Chạy test xác nhận pass**
  Run: `pytest tests/test_source_retry.py -v`
- [ ] **Step 5: Commit**
  ```bash
  git add app/routers/sources.py tests/test_source_retry.py
  git commit -m "fix(sources): preserve previous status during retry routing"
  ```

---

### Task 1.4: Sửa BUG-04 (Trùng Slug Trang Luật Giữa Các Văn Bản Cùng Loại)
**Files:**
- Modify: `app/services/legal_service.py:346, 367, 466`
- Create: `alembic/versions/xxxx_fix_legal_page_slugs.py`
- Test: `tests/test_legal_slug_generation.py`

- [ ] **Step 1: Viết test tạo hai văn bản có tiêu đề dài bắt đầu giống nhau (VD: "Nghị định quy định chi tiết một số điều của Luật...")**
  Xác minh rằng slug của các Điều không bị trùng hay ghi đè lẫn nhau.
- [ ] **Step 2: Chạy test xác nhận slug collision**
- [ ] **Step 3: Chuẩn hóa slug generator cho văn bản luật**
  Ưu tiên định dạng: `{so_hieu_slug}/dieu-{n}` (Ví dụ: `nd-136-2020-nd-cp/dieu-5`). Nếu không có số hiệu: `{slugify(title)[:35]}-{hash8(source_id)}/dieu-{n}`.
- [ ] **Step 4: Chạy lại test xác nhận pass**
- [ ] **Step 5: Commit**
  ```bash
  git add app/services/legal_service.py tests/test_legal_slug_generation.py
  git commit -m "fix(legal): generate unique deterministic slugs based on official document numbers"
  ```

---

### Task 1.5: Chuẩn Hóa Văn Bản (Unicode NFC) & Chống Trùng Lặp File Upload
**Files:**
- Create: `app/core/text_normalizer.py`
- Modify: `app/routers/sources.py:613-680`
- Modify: `app/models/source.py`
- Create: `alembic/versions/xxxx_add_content_hash_to_sources.py`
- Test: `tests/test_text_normalizer.py`
- Test: `tests/test_upload_dedup.py`

- [ ] **Step 1: Viết test cho `normalize_text` (chuẩn hóa Unicode NFC, khoảng trắng, dấu ngoặc tiếng Việt, kí tự điều khiển)**
- [ ] **Step 2: Viết test upload trùng hash (SHA-256 theo stream nội dung file)**
  Nếu file cùng hash đã tồn tại trong cùng KnowledgeType và Scope -> Trả về thông báo cảnh báo hoặc liên kết tới source hiện có thay vì tải lại.
- [ ] **Step 3: Triển khai `normalize_text` và áp dụng cho: đầu vào parser, câu hỏi truy vấn, tiêu đề trang**
- [ ] **Step 4: Thêm trường `content_hash` vào bảng `sources` và xử lý stream hash khi upload**
- [ ] **Step 5: Chạy test xác nhận pass**
  Run: `pytest tests/test_text_normalizer.py tests/test_upload_dedup.py -v`
- [ ] **Step 6: Commit**
  ```bash
  git add app/core/text_normalizer.py app/routers/sources.py app/models/source.py tests/
  git commit -m "feat(ingest): add NFC unicode normalization and stream-based content deduplication"
  ```

---

### Task 1.6: Cơ Chế Idempotency Theo Lần Parse (`attempt_id`)
**Files:**
- Modify: `app/models/source.py`
- Modify: `app/worker.py`
- Create: `alembic/versions/xxxx_add_attempt_id_to_sources.py`
- Test: `tests/test_worker_idempotency.py`

- [ ] **Step 1: Viết test mô phỏng race-condition khi người dùng bấm retry liên tiếp 2 lần**
  Job cũ chạy trễ phải phát hiện `attempt_id` đã bị thay đổi và tự động hủy bỏ (early return), không ghi đè dữ liệu của job mới.
- [ ] **Step 2: Thêm `attempt_id` (UUID) vào model `Source` (sinh mới mỗi khi retry / reparse)**
- [ ] **Step 3: Cập nhật tất cả ARQ tasks nhận `attempt_id` làm tham số và kiểm tra tính hợp lệ ở đầu task**
- [ ] **Step 4: Chạy test xác nhận pass**
  Run: `pytest tests/test_worker_idempotency.py -v`
- [ ] **Step 5: Commit**
  ```bash
  git add app/models/source.py app/worker.py tests/test_worker_idempotency.py
  git commit -m "feat(worker): enforce task idempotency using attempt_id to eliminate race conditions"
  ```

---

## Sprint 2: Nâng Cấp Bộ Parser Đa Định Dạng (PDF / DOCX / DOC / OCR)

### Task 2.1: Chuyển Đổi PDF Parser Sang `PyMuPDF4LLM` & Lọc Header/Footer Lặp
**Files:**
- Modify: `app/services/kb_service.py:214-250`
- Create: `app/services/parsers/pdf_parser.py`
- Create: `app/services/parsers/base.py`
- Test: `tests/test_pdf_parser.py`

- [ ] **Step 1: Viết test so sánh kết quả trích xuất PDF văn bản pháp luật**
  Xác minh: văn bản trích xuất có heading markdown (`#`, `##`), giữ cấu trúc bảng markdown thay vì dính liền dòng.
- [ ] **Step 2: Viết test thuật toán lọc header/footer lặp (`strip_repeated_lines`)**
  Các dòng số trang, tiêu ngữ xuất hiện ở >50% số trang tại 2 dòng đầu/cuối phải được loại bỏ sạch sẽ.
- [ ] **Step 3: Tích hợp `pymupdf4llm.to_markdown(doc, page_chunks=True, table_strategy="lines_strict")`**
- [ ] **Step 4: Bổ sung heuristic nhận diện Heading tiếng Việt**
  Nếu `pymupdf4llm` không sinh thẻ `#` cho dòng in đậm dạng `CHƯƠNG I`, `Điều 12`, tự động bù tiền tố `#` / `##` tương ứng.
- [ ] **Step 5: Chạy test xác nhận pass**
  Run: `pytest tests/test_pdf_parser.py -v`
- [ ] **Step 6: Commit**
  ```bash
  git add app/services/parsers/ app/services/kb_service.py tests/test_pdf_parser.py
  git commit -m "feat(parser): integrate pymupdf4llm with vietnamese heading heuristics and repeated header stripping"
  ```

---

### Task 2.2: Nhận Diện Trang Scan Theo Tỷ Lệ Diện Tích Ảnh & Tối Ưu Hóa OCR
**Files:**
- Modify: `app/services/kb_service.py`
- Modify: `app/services/parsers/pdf_parser.py`
- Test: `tests/test_scanned_page_detection.py`

- [ ] **Step 1: Viết test nhận diện trang scan**
  Trang chứa ảnh phủ >50% diện tích trang và số ký tự text trích xuất được < 15 ký tự -> Phải được đánh dấu là `is_scanned=True` để kích hoạt OCR.
- [ ] **Step 2: Cải tiến prompt OCR chuyên biệt cho văn bản hành chính tiếng Việt**
  Prompt yêu cầu: Giữ nguyên số hiệu, tiêu đề, dấu chấm phẩy, không tự ý sửa đổi từ ngữ viết tắt công an (CAND, CSGT, PCCC...).
- [ ] **Step 3: Thêm bước kiểm tra kết quả OCR (post-OCR sanity check)**
  Kiểm tra tỷ lệ từ vô nghĩa hoặc rác OCR trước khi lưu vào full_text.
- [ ] **Step 4: Chạy test xác nhận pass**
  Run: `pytest tests/test_scanned_page_detection.py -v`
- [ ] **Step 5: Commit**
  ```bash
  git add app/services/parsers/pdf_parser.py tests/test_scanned_page_detection.py
  git commit -m "feat(parser): add image-coverage scanned page detection and specialized OCR prompts"
  ```

---

### Task 2.3: Parser DOCX Sang Markdown Chuẩn (Hỗ Trợ Bảng & Ô Gộp)
**Files:**
- Create: `app/services/parsers/docx_parser.py`
- Modify: `app/services/kb_service.py`
- Test: `tests/test_docx_parser.py`

- [ ] **Step 1: Viết test parser file DOCX có bảng biểu phức tạp và ô gộp (merged cells)**
  Xác minh: nội dung ô gộp được điền đầy đủ (không bị mất thông tin), cấu trúc xuất ra là Markdown Table.
- [ ] **Step 2: Triển khai parser DOCX sử dụng `mammoth` hoặc `markitdown` kết hợp xử lý ô gộp từ `python-docx`**
- [ ] **Step 3: Chạy test xác nhận pass**
  Run: `pytest tests/test_docx_parser.py -v`
- [ ] **Step 4: Commit**
  ```bash
  git add app/services/parsers/docx_parser.py tests/test_docx_parser.py
  git commit -m "feat(parser): enhance docx parser with table merged-cell filling and markdown conversion"
  ```

---

### Task 2.4: Hỗ Trợ Định Dạng Cũ (DOC, PPT, XLS) Qua Headless LibreOffice
**Files:**
- Create: `app/services/parsers/libreoffice_converter.py`
- Modify: `Dockerfile`
- Test: `tests/test_libreoffice_converter.py`

- [ ] **Step 1: Viết test chuyển đổi file `.doc` cũ sang `.docx` hoặc `.pdf` qua converter có timeout**
- [ ] **Step 2: Thêm gói LibreOffice headless vào Dockerfile**
- [ ] **Step 3: Triển khai `LibreOfficeConverter` bọc lệnh subprocess với timeout tối đa 45 giây và xử lý lỗi an toàn**
- [ ] **Step 4: Chạy test xác nhận pass**
  Run: `pytest tests/test_libreoffice_converter.py -v`
- [ ] **Step 5: Commit**
  ```bash
  git add Dockerfile app/services/parsers/libreoffice_converter.py tests/test_libreoffice_converter.py
  git commit -m "feat(parser): add headless LibreOffice fallback converter for legacy doc and ppt formats"
  ```

---

## Sprint 3: Cấp Bậc Pháp Luật & Đồ Thị Pháp Lý Nghiệp Vụ (Legal Hierarchy & Graph)

### Task 3.1: Máy Trạng Thái Tách Cấp Bậc Pháp Luật Đến Khoản & Điểm + Quoted Text Boundary
**Files:**
- Create: `app/services/legal_hierarchy_parser.py`
- Modify: `app/services/legal_service.py`
- Test: `tests/test_legal_hierarchy_parser.py`

- [ ] **Step 1: Viết test case máy trạng thái với văn bản chuẩn (NĐ 136/2020) và văn bản sửa đổi (NĐ 50/2024)**
  Xác minh:
  - Tách đúng: Phần -> Chương -> Mục -> Điều -> Khoản -> Điểm -> Phụ lục.
  - Vùng trích dẫn (Quoted Text Boundary): Khi gặp `1. Sửa đổi Điều 5 như sau: "Điều 5. ..."` thì "Điều 5" bên trong ngoặc kép **không** được tách thành một Điều độc lập của NĐ 50, mà phải được phân loại là khối sửa đổi của Điều 5 NĐ 136.
- [ ] **Step 2: Chạy test xác nhận failure của parser cũ**
  Run: `pytest tests/test_legal_hierarchy_parser.py -v`
- [ ] **Step 3: Triển khai `LegalHierarchyParser` sử dụng State Machine tuần tự**
  Theo dõi ngữ cảnh: `current_part`, `current_chapter`, `current_section`, `current_article`, `current_clause`, `current_point`, `in_quoted_block`.
- [ ] **Step 4: Chạy test xác nhận pass toàn bộ các trường hợp**
  Run: `pytest tests/test_legal_hierarchy_parser.py -v`
- [ ] **Step 5: Commit**
  ```bash
  git add app/services/legal_hierarchy_parser.py tests/test_legal_hierarchy_parser.py
  git commit -m "feat(legal): implement state-machine legal hierarchy parser with quoted text boundary support"
  ```

---

### Task 3.2: Database Migration Cho Đồ Thị Pháp Luật (`legal_units`, `legal_relations`)
**Files:**
- Create: `app/models/legal_graph.py`
- Create: `alembic/versions/xxxx_create_legal_graph_tables.py`
- Test: `tests/test_legal_graph_models.py`

- [ ] **Step 1: Định nghĩa schema ORM cho `LegalDocument`, `LegalUnit`, `LegalRelation`**
  ```python
  # LegalRelation: rel_type in ('sua_doi', 'thay_the', 'bai_bo', 'huong_dan', 'can_cu', 'dan_chieu')
  # src_unit_id, dst_unit_ref, dst_unit_id, is_resolved, effective_date
  ```
- [ ] **Step 2: Tạo Alembic migration và kiểm tra tính toàn vẹn khóa ngoại trên PostgreSQL**
- [ ] **Step 3: Viết test CRUD và query quan hệ pháp lý**
- [ ] **Step 4: Commit**
  ```bash
  git add app/models/legal_graph.py alembic/versions/ tests/test_legal_graph_models.py
  git commit -m "feat(db): add schema for legal units and relational legal knowledge graph"
  ```

---

### Task 3.3: Trích Xuất Quan Hệ Pháp Lý (Regex & Heuristics) & Job Nối Quan Hệ Tự Động
**Files:**
- Create: `app/services/legal_relation_extractor.py`
- Modify: `app/services/legal_service.py`
- Test: `tests/test_legal_relation_extractor.py`

- [ ] **Step 1: Viết test nhận diện quan hệ pháp luật qua regex**
  Bắt các mẫu câu:
  - "Sửa đổi, bổ sung Khoản 1 Điều 5 của Nghị định số 136/2020/NĐ-CP" -> `sua_doi`
  - "Nghị định này thay thế Nghị định số 79/2014/NĐ-CP" -> `thay_the`
  - "Căn cứ Luật Phòng cháy và chữa cháy ngày..." -> `can_cu`
- [ ] **Step 2: Triển khai trích xuất quan hệ khi biên soạn văn bản pháp luật**
- [ ] **Step 3: Triển khai job `relink_legal_relations_task` trong worker**
  Mỗi khi có một văn bản mới được nạp, tự động quét các quan hệ `is_resolved=False` trước đó trỏ tới văn bản này để nối lại liên kết (`dst_unit_id`).
- [ ] **Step 4: Chạy test xác nhận pass**
  Run: `pytest tests/test_legal_relation_extractor.py -v`
- [ ] **Step 5: Commit**
  ```bash
  git add app/services/legal_relation_extractor.py app/services/legal_service.py tests/
  git commit -m "feat(legal): add legal relation extraction and automatic graph relinking background job"
  ```

---

### Task 3.4: Parent-Child Retrieval Cho Văn Bản Pháp Luật
**Files:**
- Modify: `app/services/legal_service.py`
- Modify: `app/services/retrieval_service.py`
- Test: `tests/test_parent_child_retrieval.py`

- [ ] **Step 1: Viết test chunking và embedding theo cơ chế Parent-Child**
  - **Child Chunk:** Tách theo Khoản (hoặc Điểm nếu Khoản quá dài). Tiền tố embedding bao gồm: Số hiệu văn bản + Chương + Tên Điều.
  - **Parent Chunk:** Toàn bộ nội dung của Điều đó.
  - Khi vector search khớp trúng Child Chunk, kết quả trả về cho LLM hoặc người đọc là Parent Context kèm đánh dấu vị trí Khoản được tìm thấy.
- [ ] **Step 2: Triển khai lưu trữ mapping child -> parent trong vector chunks**
- [ ] **Step 3: Chạy test xác nhận pass**
  Run: `pytest tests/test_parent_child_retrieval.py -v`
- [ ] **Step 4: Commit**
  ```bash
  git add app/services/legal_service.py app/services/retrieval_service.py tests/
  git commit -m "feat(retrieval): implement parent-child chunking and retrieval for legal clauses"
  ```

---

### Task 3.5: Cảnh Báo Hiệu Lực Trên Giao Diện Wiki & MCP Tools
**Files:**
- Modify: `frontend/src/components/wiki/wiki-page-view.tsx`
- Modify: `app/mcp/server.py`
- Test: `tests/test_mcp_legal_tools.py`

- [ ] **Step 1: Viết test cho MCP Tool mới: `get_legal_status(doc_number, article)` và `get_related_legal_units(unit_id)`**
- [ ] **Step 2: Cập nhật MCP server đăng ký 2 tools này cho Claude**
- [ ] **Step 3: Frontend hiển thị Banner cảnh báo trên trang wiki của Điều luật:**
  - "⚠️ Điều này đã được sửa đổi bởi [Điều 1 Nghị định 50/2024/NĐ-CP]"
  - "🛑 Văn bản này đã hết hiệu lực, được thay thế bởi [Nghị định XYZ]"
- [ ] **Step 4: Commit**
  ```bash
  git add frontend/src/components/wiki/ app/mcp/server.py tests/test_mcp_legal_tools.py
  git commit -m "feat(ui,mcp): add legal validity warning banner and MCP legal status inspection tools"
  ```

---

## Sprint 4: Nâng Cao Chất Lượng Truy Xuất (Hybrid Search, Vietnamese NLP & Reranking)

### Task 4.1: Tích Hợp Reranker Đa Ngôn Ngữ (BGE-Reranker-v2-m3) & Lọc MMR
**Files:**
- Create: `app/services/reranker_service.py`
- Modify: `app/config.py`
- Modify: `app/services/retrieval_service.py`
- Test: `tests/test_reranker_service.py`

- [ ] **Step 1: Viết test cho `RerankerService` (kết nối qua HuggingFace TEI, Infinity hoặc provider HTTP bên ngoài với fallback)**
- [ ] **Step 2: Thêm cấu hình `RERANKER_PROVIDER`, `RERANKER_URL`, `RERANKER_TOP_N` vào `app/config.py`**
- [ ] **Step 3: Triển khai reranking danh sách top-K ứng viên từ Hybrid search và lọc đa dạng hóa MMR (Maximal Marginal Relevance)**
- [ ] **Step 4: Chạy test xác nhận pass**
  Run: `pytest tests/test_reranker_service.py -v`
- [ ] **Step 5: Commit**
  ```bash
  git add app/services/reranker_service.py app/config.py app/services/retrieval_service.py tests/
  git commit -m "feat(retrieval): integrate cross-encoder reranker and MMR diversification"
  ```

---

### Task 4.2: Tách Từ Tiếng Việt (`pyvi`) Cho Full-Text Search (Tsvector Có Dấu & Bỏ Dấu)
**Files:**
- Modify: `pyproject.toml`
- Create: `app/core/vi_tokenizer.py`
- Create: `alembic/versions/xxxx_add_vi_tokenized_tsvectors.py`
- Modify: `app/services/retrieval_service.py`
- Test: `tests/test_vi_tokenizer.py`

- [ ] **Step 1: Thêm `pyvi` vào dependencies**
- [ ] **Step 2: Viết test so khớp FTS với từ ghép tiếng Việt (Ví dụ: "phòng cháy chữa cháy" -> `phòng_cháy chữa_cháy`)**
  Đảm bảo BM25/FTS không bị xé nhỏ các cụm từ chuyên ngành thành các từ đơn vô nghĩa.
- [ ] **Step 3: Tạo migration bổ sung 2 cột tsvector (có dấu đã tách từ và bỏ dấu) trên bảng chunks/wiki**
- [ ] **Step 4: Cập nhật logic FTS trong `retrieval_service` kết hợp Reciprocal Rank Fusion (RRF)**
- [ ] **Step 5: Chạy test xác nhận pass**
  Run: `pytest tests/test_vi_tokenizer.py -v`
- [ ] **Step 6: Commit**
  ```bash
  git add pyproject.toml app/core/vi_tokenizer.py alembic/ app/services/retrieval_service.py tests/
  git commit -m "feat(search): add pyvi vietnamese word tokenization and dual tsvector hybrid search"
  ```

---

### Task 4.3: Tuyến Tra Cứu Trực Tiếp Theo Số Hiệu Văn Bản & Tên Điều
**Files:**
- Modify: `app/services/retrieval_service.py`
- Test: `tests/test_exact_legal_route.py`

- [ ] **Step 1: Viết test nhận diện intent câu hỏi tra cứu chính xác**
  Ví dụ: "Điều 5 Nghị định 136/2020", "Khoản 2 Điều 15 Luật PCCC".
- [ ] **Step 2: Triển khai Exact Match Router ưu tiên truy xuất trực tiếp bảng `legal_units` trước khi fallback về hybrid search**
- [ ] **Step 3: Chạy test xác nhận pass**
  Run: `pytest tests/test_exact_legal_route.py -v`
- [ ] **Step 4: Commit**
  ```bash
  git add app/services/retrieval_service.py tests/test_exact_legal_route.py
  git commit -m "feat(retrieval): add high-priority exact routing for legal article and document queries"
  ```

---

### Task 4.4: Mở Rộng 1 Bước Qua Đồ Thị Trong `search_wiki` & Tắt Milvus Write-Only
**Files:**
- Modify: `app/services/retrieval_service.py`
- Modify: `app/config.py`
- Test: `tests/test_graph_expanded_search.py`

- [ ] **Step 1: Viết test mở rộng kết quả tìm kiếm qua 1-hop quan hệ đồ thị**
  Từ top 3 kết quả hàng đầu, tự động lấy thêm các node có quan hệ `sua_doi`, `huong_dan`, `quy_dinh` liên quan đưa vào reranker.
- [ ] **Step 2: Đặt `MILVUS_ENABLED=False` mặc định trong cấu hình để loại bỏ overhead ghi lãng phí khi hệ thống đang sử dụng pgvector**
- [ ] **Step 3: Chạy lại bộ benchmark eval từ Sprint 0 để so sánh chỉ số Recall & MRR**
  Run: `python eval/retrieval_eval.py --output eval/results/sprint4_eval.json`
- [ ] **Step 4: Commit**
  ```bash
  git add app/services/retrieval_service.py app/config.py tests/
  git commit -m "feat(retrieval): enable 1-hop graph neighbor expansion and disable redundant milvus writes"
  ```

---

## Sprint 5: Bảng Tính (Excel), Đa Phương Tiện & Tăng Cường Truy Xuất

### Task 5.1: Xử Lý Bảng Tính Excel Chuyên Biệt & Tích Hợp DuckDB
**Files:**
- Create: `app/services/parsers/excel_parser.py`
- Create: `app/services/table_query_service.py`
- Modify: `app/mcp/server.py`
- Test: `tests/test_excel_parser.py`
- Test: `tests/test_table_query.py`

- [ ] **Step 1: Viết test phân tích bảng tính Excel**
  - Trích xuất: Chunk dạng `Cột: Giá trị` theo từng hàng kèm tóm tắt cấu trúc bảng.
  - Đường ống xử lý riêng cho bảng dữ liệu lớn (bỏ qua MAP/REDUCE để tiết kiệm chi phí).
- [ ] **Step 2: Viết test tool MCP `query_table(table_id, sql_query)` sử dụng DuckDB an toàn (Read-Only, timeout, limit dòng)**
- [ ] **Step 3: Triển khai `ExcelParser` và `DuckDB` table query service**
- [ ] **Step 4: Chạy test xác nhận pass**
  Run: `pytest tests/test_excel_parser.py tests/test_table_query.py -v`
- [ ] **Step 5: Commit**
  ```bash
  git add app/services/parsers/excel_parser.py app/services/table_query_service.py app/mcp/server.py tests/
  git commit -m "feat(excel): add row-wise structured chunking and read-only duckdb table querying"
  ```

---

### Task 5.2: Chunking Độc Lập Cho Hình Ảnh & Trích Xuất File Trình Chiếu (PPTX)
**Files:**
- Create: `app/services/parsers/pptx_parser.py`
- Modify: `app/services/image_service.py`
- Modify: `app/worker.py`
- Test: `tests/test_pptx_parser.py`

- [ ] **Step 1: Viết test trích xuất slide và ảnh từ file PPTX**
- [ ] **Step 2: Đảm bảo hình ảnh sau khi OCR/Caption được tạo thành các chunk độc lập mang loại `image_ocr` và `image_caption` có vector nhúng riêng**
- [ ] **Step 3: Chạy test xác nhận pass**
  Run: `pytest tests/test_pptx_parser.py -v`
- [ ] **Step 4: Commit**
  ```bash
  git add app/services/parsers/pptx_parser.py app/services/image_service.py tests/
  git commit -m "feat(multimodal): add pptx presentation parser and dedicated visual image chunks"
  ```

---

### Task 5.3: Hàng Đợi Sinh Câu Hỏi Cho Chunk Luật (Question Generation)
**Files:**
- Create: `app/services/question_generator.py`
- Modify: `app/worker.py`
- Test: `tests/test_question_generator.py`

- [ ] **Step 1: Viết test sinh 2-3 câu hỏi tiềm năng cho mỗi Khoản luật trọng tâm**
- [ ] **Step 2: Triển khai worker task chạy nền với độ ưu tiên thấp (`low_priority_queue`), áp dụng giới hạn token/ngân sách**
- [ ] **Step 3: Nhúng vector các câu hỏi được sinh để gia tăng độ phủ tìm kiếm khi người dùng hỏi theo ngôn ngữ tự nhiên**
- [ ] **Step 4: Commit**
  ```bash
  git add app/services/question_generator.py app/worker.py tests/test_question_generator.py
  git commit -m "feat(ai): add background question generation queue for legal chunks to boost natural query recall"
  ```

---

## Sprint 6: Đồ Thị Khái Niệm, Xác Minh Trích Dẫn & Vận Hành Bền Bỉ

### Task 6.1: Khai Thác Quan Hệ Khái Niệm Với Tập Nhãn Đóng Trong MAP Prompt
**Files:**
- Modify: `app/ai/mrp/mapper.py`
- Create: `app/models/concept_relation.py`
- Create: `alembic/versions/xxxx_create_concept_relations.py`
- Test: `tests/test_concept_relations.py`

- [ ] **Step 1: Chuẩn hóa `EXTRACTION_PROMPT_TEMPLATE` trong MAP**
  Yêu cầu trả về `relations` theo tập vị từ đóng (Closed Predicates): `la_mot` (is-a), `thuoc` (part-of), `quy_dinh` (regulates), `ap_dung_cho` (applies-to), `lien_quan` (relates-to) kèm câu chứng cứ (`evidence`).
- [ ] **Step 2: Tạo bảng `concept_relations` lưu trữ các liên kết này gắn với wiki pages sau khi REDUCE hoàn tất**
- [ ] **Step 3: Chạy test xác nhận pass**
  Run: `pytest tests/test_concept_relations.py -v`
- [ ] **Step 4: Commit**
  ```bash
  git add app/ai/mrp/mapper.py app/models/concept_relation.py alembic/ tests/
  git commit -m "feat(graph): capture structured concept relations with closed predicates during map phase"
  ```

---

### Task 6.2: Hiển Thị Quan Hệ Có Kiểu (Typed Edges) Trên Giao Diện Đồ Thị
**Files:**
- Modify: `frontend/src/components/wiki/wiki-graph.tsx`
- Modify: `app/routers/wiki.py`

- [ ] **Step 1: Cập nhật API `/api/wiki/graph` trả về danh sách edges có `type`, `label`, `weight`, `evidence`**
- [ ] **Step 2: Cập nhật đồ thị frontend (React Force Graph / 2D Canvas) tô màu và gắn nhãn các liên kết theo loại quan hệ**
- [ ] **Step 3: Thêm bộ lọc hiển thị (Lọc quan hệ khái niệm / Quan hệ pháp luật / Wikilinks thuần túy)**
- [ ] **Step 4: Commit**
  ```bash
  git add frontend/src/components/wiki/wiki-graph.tsx app/routers/wiki.py
  git commit -m "feat(ui): display typed relation edges and interactive filters in knowledge graph view"
  ```

---

### Task 6.3: Cơ Chế Xác Minh Trích Dẫn & Footnote Nhẹ (`[^sN]`)
**Files:**
- Create: `app/services/citation_verifier.py`
- Modify: `app/ai/mrp/synthesizer.py`
- Test: `tests/test_citation_verifier.py`

- [ ] **Step 1: Viết test cho bộ kiểm tra trích dẫn: Đối chiếu khẳng định (claim) với nguồn gốc**
- [ ] **Step 2: Triển khai định dạng chú thích nguồn nhẹ `[^sN]` trong quá trình tổng hợp trang wiki**
- [ ] **Step 3: Tự động đánh dấu cảnh báo nếu câu khẳng định không tìm thấy căn cứ trong nguồn tài liệu**
- [ ] **Step 4: Commit**
  ```bash
  git add app/services/citation_verifier.py app/ai/mrp/synthesizer.py tests/
  git commit -m "feat(wiki): add lightweight footnote citations and automated factual verifier"
  ```

---

### Task 6.4: Bảng Dead-Letter Task Failures & Giám Sát Thời Gian Từng Bước (Stage Timings)
**Files:**
- Create: `app/models/task_failure.py`
- Create: `alembic/versions/xxxx_create_task_failures_table.py`
- Modify: `app/worker.py`
- Modify: `app/routers/admin.py`
- Test: `tests/test_dead_letter_and_timings.py`

- [ ] **Step 1: Tạo bảng `task_failures` lưu vết các lỗi task không thể phục hồi (source_id, attempt_id, task_name, error, traceback, payload)**
- [ ] **Step 2: Bổ sung bảng `source_stage_timings` ghi nhận thời lượng thực thi chi tiết (Parse, OCR, MAP, REDUCE, Vector Index)**
- [ ] **Step 3: Tạo giao diện Admin xem danh sách task hỏng và nút "Chạy lại task (Re-dispatch)"**
- [ ] **Step 4: Commit**
  ```bash
  git add app/models/task_failure.py alembic/ app/worker.py app/routers/admin.py tests/
  git commit -m "feat(ops): add dead-letter task failure tracking, stage execution timings, and retry admin UI"
  ```

---

## Tiêu Chí Nghiệm Thu Toàn Diện (Acceptance Criteria)

1. **Hiệu năng tìm kiếm (Retrieval Benchmark):**
   - Recall@5 và Recall@10 trên bộ câu hỏi văn bản pháp luật tăng ít nhất **25%** so với baseline ban đầu.
   - Điểm MRR (Mean Reciprocal Rank) cải thiện rõ rệt, đặc biệt với các câu hỏi dẫn chiếu cụ thể theo Điều / Khoản.
   - P95 latency của API `search_wiki` và MCP search không vượt quá **1.5 giây**.
2. **Độ chính xác dữ liệu pháp luật:**
   - 100% các nghị định sửa đổi phức tạp (như NĐ 50/2024 sửa đổi NĐ 136/2020) không bị tách nhầm các Điều trong phần trích dẫn thành Điều của văn bản sửa đổi.
   - Cảnh báo hiệu lực và quan hệ `sua_doi`, `thay_the` hiển thị chính xác trên giao diện wiki.
3. **Độ ổn định hệ thống (Reliability):**
   - 0 trường hợp tài liệu bị treo ở trạng thái `processing` khi tắt vision provider hoặc khi người dùng thao tác retry liên tục.
   - Toàn bộ các định dạng phổ biến (PDF scan, PDF văn bản, DOCX có bảng ô gộp, DOC cũ) đều được phân tích thành công và có outline cấu trúc rõ ràng.
4. **Bảo mật & Phân quyền:**
   - Tuyệt đối không rò rỉ văn bản nội bộ của phòng ban sang phạm vi toàn hệ thống (`global`) trong module xử lý văn bản pháp luật.

---

## Hướng Dẫn Thực Hiện Tiếp Theo (Execution Handoff)

Kế hoạch này được cấu trúc để thực hiện tuần tự hoặc song song các module độc lập. Hai phương thức triển khai khả dụng:

1. **Subagent-Driven Development (Khuyến nghị):** Phân chia mỗi Task thành một nhiệm vụ độc lập cho một subagent chuyên trách, có review checkpoint và kiểm thử nghiêm ngặt trước khi chuyển sang task kế tiếp.
2. **Inline Execution:** Thực hiện tuần tự từng task ngay trong phiên làm việc hiện tại, theo dõi tiến độ qua checkbox.
