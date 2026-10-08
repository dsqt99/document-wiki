# 08 — Tiến độ triển khai: pipeline xử lý wiki & dual pipeline

> Cập nhật: 2026-10-05 · Nhánh: `feat/dual-pipeline-unified-retrieval` (chưa commit)
> Đối chiếu với: [06-lo-trinh-trien-khai.md](06-lo-trinh-trien-khai.md) và tài liệu
> `chatbot_local/docs/MO_TA_KY_THUAT_DATA_PIPELINE_VA_CHAT_CAHY.md` (gọi tắt **MO_TA**).

---

## 1. Những gì đã update trong pipeline (đã commit — 43 commit gần nhất)

| Nhóm (theo lộ trình 06) | Commit | Nội dung chính |
|---|---|---|
| **Sprint 1 — Sửa bug & độ bền** | `ca92b1e` BUG-01 | Task caption ảnh luôn nối tiếp sang MRP (trước đây có thể "rơi" pipeline) |
| | `bea060f` BUG-02 | Cô lập phạm vi phòng ban cho trang văn bản pháp luật |
| | `d812104` BUG-03 | Retry giữ trạng thái cũ để route đúng task |
| | `bf401f2` BUG-04 | Slug văn bản pháp luật theo số hiệu, không trùng |
| | `5e3287f` Task 1.5 | Chuẩn hoá Unicode NFC + chống trùng tài liệu bằng SHA-256 stream |
| | `359b3b4`, `3ca917d` Task 1.6 | `attempt_id` — task cũ/trùng tự bỏ qua, hết race condition |
| | `55d9265` | Dead-letter `task_failures`, đo thời gian từng stage, UI retry cho admin |
| **Sprint 2 — Đọc tài liệu đầu vào** | `12d8337` Task 2.1–2.2 | `pymupdf4llm` + heuristic tiêu đề tiếng Việt (Phần/Chương/Điều), bỏ header/footer lặp |
| | `06d2547` Task 2.3 | DOCX: bảng merged-cell → Markdown |
| | `aaca998` Task 2.4 | LibreOffice headless chuyển `.doc/.ppt/.rtf` → PDF |
| | `be85cc5` | Parser PPTX + chunk ảnh riêng |
| | `692a280`, `83c38e3`, `e215118`, `4f9644c`, `d11957d`, `e0ef45d`, `d4ad126`, `0d037e4` | Cấu hình OCR/PDF động (engine, OCR mode, max_pages), test kết nối OCR, **Extraction Playground** trong Settings |
| **Sprint 3 — Pháp luật** | `e2df9e4` Task 3.1 | Parser phân cấp văn bản pháp luật dạng state-machine (xử lý trích dẫn lồng) |
| | `d320255` Task 3.2 | Model `LegalUnit`, `LegalRelation` + migration |
| | `08952e8` Task 3.3 | Trích quan hệ pháp lý (sửa đổi/thay thế/hướng dẫn…) → graph, task relink |
| | `e9ec29a` Task 3.4–3.5 | Truy xuất parent-child (Điều ↔ Khoản), callout hiệu lực, MCP tool legal graph |
| | `74530d8` | Sinh câu hỏi nền cho chunk pháp luật để tăng recall |
| **Sprint 4 — Truy xuất** | `0f2ee67` Task 4.1 | Cross-encoder reranker + MMR |
| | `71ef683` Task 4.2 | Tách từ tiếng Việt `pyvi` + dual tsvector |
| | `8da70b1` Task 4.3 | Router khớp chính xác "Điều X Luật Y" |
| | `d267f26` Task 4.4 | Mở rộng 1-hop graph, gom vào `search_wiki` |
| **Sprint 5 — Excel/Graph/Kiểm chứng** | `79bbb7f` Task 5.1 | Excel row-wise parser, DuckDB `query_table`, MCP tool |
| | `4e8f842`, `1d7ea2c` | Quan hệ khái niệm có predicate đóng ở pha MAP, hiển thị cạnh có kiểu trên graph |
| | `9048793` | Footnote citation + verifier tự động |
| **Hạ tầng** | `15cfbdc`, `af419a5`, `f56fcb9`, `5395614`, `0ccd045`, `1f416d9` | Alembic idempotent, docker đổi tên `wiki_*`, tránh trùng DNS với `chatbot_local`, tắt Langfuse sync khi treo |

---

## 2. Những gì làm trong phiên này (chưa commit)

### 2.1 Dual pipeline đúng như MO_TA (nhánh A ∥ nhánh B)

Sau khi trích xuất text, mỗi source chạy **song song 2 nhánh độc lập**:

```
                        ┌─ Nhánh A (chunk_*): chunk theo heading → embed → source_chunk_embeddings_<dim>
extract → dispatch ─────┤                         (không bao giờ chờ duyệt)
                        └─ Nhánh B (wiki_*):  pháp luật → Điều-level pages
                                              | > ngưỡng token → awaiting_approval
                                              | còn lại → caption → MRP (MAP→REDUCE→plan→REFINE→VERIFY→COMMIT)
```

`source.status` là **trạng thái tổng hợp** của 2 nhánh:

| chunk_status | wiki_status | status tổng | Ý nghĩa |
|---|---|---|---|
| ready | ready | `ready` | |
| ready | error | **`partial`** | Raw chunk đã tra cứu được, wiki lỗi |
| error | ready | **`partial`** | Wiki dùng được, raw chunk lỗi |
| error | error | `error` | |
| bất kỳ | awaiting_approval / plan_ready | giữ cổng duyệt | kèm "(Raw chunks already searchable)" |
| đang chạy | ready | `ready` | wiki đã dùng được; re-index chunk không làm source "tụt" trạng thái |
| pending (source cũ) | ready | `ready` | source trước migration 044 |
| verbatim | skipped | theo nhánh A | |

**File chính**

| File | Thay đổi |
|---|---|
| `app/services/source_status.py` (mới) | `compute_source_dual_status`, `update_source_dual_status` (khoá dòng `FOR UPDATE` + `populate_existing`), `set_branch_state` (cập nhật 1 nhánh + tổng, commit nguyên tử), `reset_branches` |
| `app/worker.py` | `dispatch_dual_pipeline` dùng chung cho file & URL; `commit_and_enqueue_chunk_branch` (**commit trước, enqueue sau** — hết race ghi đè `ready`); `ingest_source_chunks_task` (kiểm `attempt_id` + `chunk_attempt_id`); `mark_wiki_error`; MRP/refine/legal chỉ ghi `wiki_*`; cron sweep chỉ fail nhánh bị treo; re-embed khi đổi model embedding re-index cả raw chunk của mọi source |
| `app/worker.py` | **Mới:** `backfill_source_chunks_task` — tạo raw chunk cho source cũ (chunk `pending`) hoặc nhánh A lỗi |
| `app/routers/admin_embeddings.py` | **Mới:** `POST /api/settings/embeddings/backfill-source-chunks?limit=500` (quyền `org:settings:manage`, có audit log) |
| `app/utils/progress.py` | `ProgressTracker` ghi vào `wiki_progress` khi nhánh B đang chạy |
| `app/ai/mrp/pipeline.py`, `app/services/legal_service.py` | Ghi `wiki_*` + tính lại tổng thay vì ghi đè `status` |
| `app/routers/sources.py` | `POST /sources/{id}/retry?branch=chunk\|wiki\|all` — mặc định **chỉ chạy lại nhánh lỗi** (wiki lỗi ở refine/verify/commit → resume `ingest_refine_task`, còn lại → MAP); cho phép retry `partial`; duyệt/từ chối plan & duyệt kích thước chỉ tác động nhánh B; `SourceResponse` trả thêm `chunk_*`, `wiki_*` |
| `alembic/versions/044_dual_pipeline_status.py` | Cột `chunk_*`, `wiki_*` + backfill trạng thái |
| `app/services/retrieval_service.py`, `reranker_service.py`, `verbatim_service.py`, `mcp/tools.py`, `wiki_service.py` | `unified_search` (RRF wiki + raw chunk, ngưỡng 0.35, gộp chunk liền kề, rerank có degrade floor, MMR); chunk theo heading path + contextual prefix |

**Sửa thêm 2 lỗi tiềm ẩn**

1. `dispatch_dual_pipeline` từng enqueue MRP **trước** khi ghi `wiki_status=processing` → nếu MRP lỗi rất nhanh, trạng thái lỗi bị ghi đè thành `processing` và treo tới khi cron sweep. Đã đổi thứ tự: ghi trạng thái rồi mới enqueue.
2. 5 closure xử lý lỗi trong worker (`_mark_error_file/_url/_mr/_refine`, `_mark_chunk_error`) đọc biến `e` của `except`. Khi task bị cancel, `asyncio.shield` chạy tiếp **sau** khi Python đã xoá `e` → `NameError`, mất bản ghi dead-letter. Đã bind `exc=e` làm tham số mặc định.

### 2.2 Đầu vào tài liệu (khoảng trống so với MO_TA)

| Vấn đề | Đã xử lý |
|---|---|
| API từ chối `.doc` dù đã có LibreOffice converter | Chấp nhận `.doc/.ppt/.rtf` khi server có LibreOffice; báo lỗi rõ nếu chưa cài. Upload dialog nhận thêm DOC/RTF/PPT |
| `.xls` đọc bằng openpyxl → lỗi | `ExcelParser` đọc `.xls` bằng `xlrd` (cả `parse` và `parse_file`) |
| Cấu hình engine PDF / OCR mode / bỏ header-footer trong Settings **chỉ áp dụng cho Playground**, ingest thật vẫn dùng mặc định | `_extract_text_from_file` đọc cấu hình admin (DB > .env > default) và truyền vào `PDFParser` (kể cả file `.doc` sau khi convert) và `ExcelParser` |
| Giới hạn upload backend 100 MB lệch UI 50 MB, không có setting | Thêm `settings.max_upload_size_bytes` (mặc định 50 MiB, cấu hình qua env `MAX_UPLOAD_SIZE_BYTES`) |
| `pymupdf4llm` là engine mặc định nhưng thiếu trong `pyproject.toml` | Đã thêm dependency (test `test_pdf_parser` hết lỗi) |

### 2.3 Frontend

- Trạng thái `partial` (chấm vàng hổ phách, "Một phần"), hiển thị `Chunk: ✓/✗/… · Wiki: ✓/✗/…` dưới trạng thái.
- Nút **Thử lại** hiện cho cả `error` và `partial` (backend tự chọn nhánh cần chạy lại).
- `tsc --noEmit` sạch.

### 2.4 Kiểm thử

```
D:/.arkon-venv/Scripts/python -m pytest tests/ -q -p no:cacheprovider
129 passed
```

Test mới: `tests/test_source_status.py` (bảng trạng thái tổng + định tuyến `dispatch_dual_pipeline`, thứ tự ghi-trạng-thái-trước-enqueue), `tests/test_source_retry.py` (retry theo nhánh), `tests/test_ingest_formats.py` (`.xls`, truyền cấu hình PDF/OCR).

---

## 3. Việc cần làm khi triển khai

1. `alembic upgrade head` (migration 044).
2. Cài dependency mới: `pip install -e ".[dev]"` (`pymupdf4llm`; `xlwt` chỉ cho test). Docker image cần build lại.
3. Gọi backfill một lần để các source cũ có raw chunk (lặp lại tới khi `enqueued = 0`):
   `POST /api/settings/embeddings/backfill-source-chunks?limit=500`
4. Restart worker để nạp `backfill_source_chunks_task`.

---

## 4. Khoảng trống so với MO_TA — đã xử lý (phiên 2026-10-06, chưa commit)

Backup DB trước khi triển khai: `backups/wiki_arkon_20261006_080859.dump` (pg_dump custom format của DB `arkon`, khôi phục bằng `pg_restore`).

| # | Hạng mục | Trạng thái | Thay đổi |
|---|---|---|---|
| 1 | Upload stream thẳng lên MinIO | ✅ | `upload_source` (`app/routers/sources.py`) chỉ băm SHA-256 + đếm kích thước khi đọc; sau khi commit thì `file.seek(0)` và `storage_service.upload_stream_async(...)` từ file spool của Starlette — không còn gom cả file vào RAM. Test: `test_upload_source_streams_file_to_minio` |
| 2 | Chunk theo dòng cho bảng dài (Excel) ở nhánh A | ✅ | `build_source_chunks` (`app/services/verbatim_service.py`): bảng Markdown dài hơn `CHUNK_TARGET_CHARS` được cắt theo nhóm dòng; mỗi chunk lặp lại header (tên cột) để embedding giữ ngữ cảnh, `start/end_char` chỉ trỏ vào các dòng (không trùng, không mất dòng). Bảng ngắn giữ cách chia cũ. Test: `test_build_source_chunks_long_table_row_wise_with_header`, `..._short_table_unchanged` |
| 3 | Retry theo nhánh trên UI | ✅ | Menu dòng tài liệu (`knowledge-table/index.tsx`) thêm "Chạy lại chunk thô" / "Chạy lại biên dịch wiki" (ẩn với verbatim) / "Xử lý lại từ đầu" → `POST /api/sources/{id}/retry?branch=chunk\|wiki\|all`. `branch=all` sinh `attempt_id` mới |
| 4 | Nút backfill trong Settings | ✅ | Card Embeddings có nút "Index chunk thô cho tài liệu cũ" gọi `POST /api/settings/embeddings/backfill-source-chunks?limit=500`. Endpoint xếp một job arq và trả về `{job_id}`; UI báo "Đã xếp hàng job index chunk thô". Bấm lại nếu còn source cũ chưa có chunk |
| 5 | `wiki_attempt_id` cho nhánh B | ✅ | `start_wiki_attempt` / `wiki_attempt_of` (`source_status.py`). Dispatcher và retry nhánh wiki sinh `wiki_attempt_id` mới; task MRP / refine / caption kiểm tra với `branch="wiki"` (fallback `attempt_id` cho source cũ). Retry wiki chỉ vô hiệu job wiki cũ, nhánh A đang chạy không bị ảnh hưởng |
| 6 | Test tích hợp Postgres thật | ✅ | `tests/test_source_status_pg.py`: khoá `FOR UPDATE` thực sự chặn và đọc lại trạng thái nhánh kia; cập nhật xen kẽ đồng thời 2 nhánh không mất dữ liệu; kiểm tra `wiki_attempt_id` trên dòng thật. Chỉ chạy khi có `ARKON_IT_DATABASE_URL` (DB tạm, **không** trỏ vào `arkon`), xem docstring file |

Kết quả: `pytest tests/` → **138 passed** (gồm 3 test Postgres trên container pgvector tạm); `npx tsc --noEmit` sạch.

---

## 5. Cấu hình model: preset GPT-6 Luna / Claude Sonnet 5.5 + model tự thêm (phiên 2026-10-06, chưa commit)

- **Preset**:
  - LLM, Vision và OCR chỉ còn 2 model: `openai/gpt-6-luna` và `anthropic/claude-sonnet-5-5`.
  - Embedding chỉ còn `openai/text-embedding-3-large`, model đang chạy (582 vector) nên không cần re-embed.
- **Model tự thêm** (`app/ai/custom_models.py`, `app/routers/admin_custom_models.py`):
  - Trên mỗi card có nút "Thêm model". Nhập base URL, model name, tên hiển thị (tuỳ chọn) và API key (tuỳ chọn), rồi bấm "Lưu model".
  - Danh sách model được lưu trong `app_config.custom_models` (JSON). API key của từng model lưu mã hoá trong `custom_model_api_key__<hash>`.
  - Định dạng id:
    - LLM, Vision, OCR: `custom/<model>`;
    - Embedding: `custom/<dim>/<model>`, với dim là 768, 1024, 1536 hoặc 3072.
  - LLM chọn được giao thức OpenAI-compatible hoặc Anthropic. Các loại còn lại phải là endpoint tương thích OpenAI.
  - Không xoá được model đang active, hoặc model embedding đang có job chạy (trả về 409).
- **API key preset theo provider**:
  - Các key là `llm_api_key__openai|anthropic` và `vision_api_key__openai|anthropic`.
  - Key cũ `llm_api_key` / `vision_api_key` vẫn được dùng làm fallback cho OpenAI. Key bắt đầu bằng `sk-ant-` chỉ dùng cho Anthropic.
  - Claude Vision và Claude OCR gọi qua endpoint OpenAI-compatible của Anthropic (`https://api.anthropic.com/v1/`).
- **OCR**:
  - Bỏ ô nhập tự do, chuyển sang chọn từ danh sách bằng `GET /api/settings/ocr/catalog` và `POST /api/settings/ocr/select`.
  - Nếu để trống key của preset thì dùng Vision key của cùng provider.
- **Migration** `045_model_presets_gpt6` (chỉ đổi dữ liệu):
  - Chuyển LLM và Vision đang active không còn trong catalog sang `openai/gpt-6-luna`.
  - Đổi `ocr_model gpt-5*` thành `gpt-6-luna`.
  - Khi chạy, registry cũng tự fallback về GPT-6 Luna nếu id lưu trong DB không còn tồn tại.
- **Test**:
  - `tests/test_custom_models.py` (8 test).
  - `pytest tests/` cho kết quả **143 passed, 3 skipped**.
- **Đã triển khai**:
  - Migration 045 đã chạy trên DB `arkon`.
  - API và worker đã restart, frontend đã build lại.

**Còn thiếu:** pipeline ingest chưa truyền cấu hình OCR trong DB (`ocr_*`) vào `PDFParser`.
