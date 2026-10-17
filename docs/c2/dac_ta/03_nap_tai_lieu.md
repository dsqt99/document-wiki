# 03. Nạp tài liệu, trích xuất văn bản, OCR và pipeline worker

Tài liệu này mô tả toàn bộ luồng đưa một tài liệu (tệp hoặc URL) vào hệ thống. Luồng gồm các bước:
- tải lên và chống trùng;
- trích xuất văn bản theo trang, OCR, ảnh và chú thích ảnh;
- dựng mục lục (outline);
- hai nhánh xử lý song song: nhánh A chia chunk và nhúng, nhánh B biên soạn wiki;
- các cổng phê duyệt, thử lại, dead-letter và đo thời gian từng giai đoạn.

Mọi đường dẫn API đều gắn dưới tiền tố `/api`. Các router `sources`, `notes`, `wiki_images`, `admin_failures` và `knowledge_types` đều mount với `prefix="/api"`.

Các phần tham chiếu sang tài liệu khác:

| Nội dung | Xem ở |
|---|---|
| auth_service, permission_engine, nhãn bảo mật, `_checked_label`, `source_read_filter`, `_authenticate_request_user` | tài liệu xác thực và phân quyền (02) |
| `embedding_storage`, bảng embedding theo chiều, `get_spec` | tài liệu truy hồi (04) |
| Pipeline biên soạn wiki MRP (`run_mrp_pipeline`, `run_refine_pipeline`, `run_planning_call`, `reconcile_with_kb`, `_resolve_wiki_scopes`), `wiki_service`, nhánh văn bản pháp luật `finalize_legal_source` | tài liệu wiki và pháp luật |
| `ProviderRegistry`, `ConfigService`, `async_session_factory`, `trace_context` / `flush_langfuse` | tài liệu nền tảng backend |

Các module loại C đã có sẵn trong c2 được dùng nguyên trạng. Tài liệu này chỉ nêu hợp đồng gọi của chúng:
- `app.services.source_status`
- `app.services.chunk_budget`
- `app.services.ocr_service`
- `app.services.doc_metadata_service`
- `app.services.upload_guard`
- `app.services.legal_service`
- `app.services.parsers.*`, gồm `pdf_parser`, `docx_parser`, `excel_parser`, `pptx_parser`, `libreoffice_converter` và `base`

---

## 1. Module cần xây và vị trí

| Module | Vai trò |
|---|---|
| `app.routers.sources` | CRUD tài liệu, tải lên, URL, tệp/preview, tiến độ, retry, phê duyệt trích xuất, kế hoạch biên soạn |
| `app.routers.knowledge_types` | Danh mục loại tri thức |
| `app.routers.notes` | Ghi chú tự do |
| `app.routers.wiki_images` | Đổi `image://uuid` thành URL MinIO ký sẵn |
| `app.routers.admin_failures` | Xem và chạy lại tác vụ lỗi (dead-letter), xem thời gian các giai đoạn |
| `app.models.task_failure` | Mô hình `TaskFailure`, `SourceStageTiming` và hai hàm ghi |
| `app.services.kb_service` | Trích xuất văn bản theo định dạng, chèn marker ảnh, đoán content type |
| `app.services.image_service` | Trích ảnh từ PDF/DOCX/PPTX, tạo chunk ảnh, nhúng chunk ảnh |
| `app.services.verbatim_service` | Chia chunk văn bản gốc (nhánh A) và lập chỉ mục |
| `app.services.source_outline` | Ghép full_text theo trang, offset trang, outline theo heading |
| `app.services.storage_service` | Lớp bọc MinIO, singleton `storage_service` |
| `app.services.question_generator` | Sinh câu hỏi tìm kiếm cho điều khoản và lập chỉ mục |
| `app.utils.progress` | `ProgressTracker`, `WIKI_ACTIVE` |
| `app.utils.tokens` | `count_tokens` |
| `app.worker` | Các tác vụ arq, cron, `WorkerSettings` |

**Quy tắc import lười (bắt buộc).** Test patch các ký hiệu tại module gốc của chúng. Vì vậy các hàm worker và router phải tra những ký hiệu sau qua module tại thời điểm gọi, chứ không giữ tham chiếu lấy lúc import:
- `app.database.async_session_factory`
- `app.ai.tracing.trace_context`
- `app.models.task_failure.record_task_failure`
- `app.services.storage_service.storage_service` và các phương thức của nó
- `app.ai.registry.ProviderRegistry`, kể cả phương thức `get_vision`
- `app.services.question_generator.QuestionGenerator` và `index_question_chunks`
- `app.services.parsers.pdf_parser.PDFParser`
- `app.services.parsers.libreoffice_converter.libreoffice_converter`
- `app.services.source_status.update_source_dual_status`
- `app.worker.commit_and_enqueue_chunk_branch` và `enqueue_post_extraction_pipeline`, khi router gọi chúng

Bên trong `app.worker`, các hàm phải gọi nhau qua thuộc tính module để `patch("app.worker.X")` có hiệu lực. Các thuộc tính đó là `check_task_attempt_validity`, `_chain_to_mrp`, `get_arq_pool`, `set_branch_state`, `mark_wiki_error`, `enqueue_post_extraction_pipeline` và `commit_and_enqueue_chunk_branch`.

Hai module có `get_arq_pool` riêng, vì test patch cả hai:
- `app.routers.sources.get_arq_pool`
- `app.worker.get_arq_pool`

---

## 2. Cấu hình (Settings, biến môi trường cùng tên viết hoa)

| Khóa | Mặc định | Ý nghĩa |
|---|---|---|
| `minio_endpoint` | `localhost:9000` | Endpoint nội bộ của MinIO |
| `minio_public_endpoint` | rỗng | Endpoint dùng để ký URL cho trình duyệt; rỗng thì dùng `minio_endpoint` |
| `minio_access_key`, `minio_secret_key` | (bắt buộc từ env) | Thông tin truy cập MinIO |
| `minio_bucket` | `arkon-files` | Bucket lưu tệp |
| `minio_secure` | False | Có dùng HTTPS hay không |
| `minio_presign_expiry_hours` | 24 | Hạn mặc định của URL ký sẵn |
| `redis_host`, `redis_port`, `redis_db`, `redis_password` | | Kết nối arq. Mật khẩu rỗng thì coi là None |
| `worker_max_jobs` | 3 | Số job chạy đồng thời trong worker |
| `worker_job_timeout` | 7200 (giây) | Thời gian tối đa của một job |
| `max_upload_size_bytes` | 52428800 (50 MiB) | Giới hạn dung lượng tệp tải lên |
| `allowed_upload_extensions` | `pdf,docx,xlsx,pptx,txt,md,csv` | Danh sách đuôi được phép, phân tách bằng dấu phẩy |
| `auto_approve_extraction_threshold_tokens` | 0 | Ngưỡng cổng phê duyệt trích xuất. 0 hoặc âm thì tắt cổng |
| `extraction_approval_ttl_hours` | 24 | Sau thời gian này, tài liệu chờ duyệt bị dọn |
| `max_auto_recover_attempts` | 3 | Trần số lần cron tự đánh lỗi liên tiếp |
| `mrp_auto_approve_plan` | True | Tự duyệt kế hoạch biên soạn (dùng trong pipeline MRP) |
| `ocr_base_url`, `ocr_api_key`, `ocr_model` | `""`, `""`, `ggml-org/GLM-OCR-GGUF:f16` | Máy chủ OCR. Thuộc tính `effective_ocr_base_url` đã chuẩn hóa |
| `chunk_target_tokens` | 1500 | Kẹp vào khoảng 1000–2000, xem `chunk_budget` |
| `chunk_overlap_tokens` | 150 | Tối đa bằng một phần tư target |

Khóa cấu hình quản trị trong bảng `app_config`, đọc qua `ConfigService.get`:

| Khóa | Mặc định |
|---|---|
| `pdf_parser_engine` | `pymupdf4llm` |
| `excel_parser_engine` | `openpyxl` |
| `ocr_mode` | `auto` |
| `ocr_fallback_vision` | true |
| `ocr_llm_refine` | false |
| `pdf_strip_headers_footers` | true |
| `pdf_enhance_headings` | true |
| `ocr_base_url`, `ocr_api_key`, `ocr_model`, `ocr_prompt` | không có mặc định |

Giá trị bool đọc từ chuỗi. Các chuỗi `1`, `true`, `yes`, `on` (không phân biệt hoa thường) là true. Thiếu khóa thì dùng mặc định.

---

## 3. Lược đồ dữ liệu

### 3.1 `sources` (mô hình `Source` trong `app.database.models`)

| Cột | Kiểu | Ràng buộc / mặc định |
|---|---|---|
| id | uuid | PK, mặc định uuid4 |
| title | Text | null được |
| full_text | Text | Văn bản đã ghép mọi trang |
| source_type | String(50) | `file` hoặc `url` |
| scope_type | String(20) | mặc định `global`. Giá trị: `global`, `department`, `personal` (enum `ScopeType`) |
| scope_id | uuid | null được. Với `personal` là id nhân viên sở hữu |
| security_label | String(20) | not null, mặc định `INTERNAL` |
| knowledge_type_id | uuid | FK `knowledge_types.id`, ON DELETE SET NULL |
| contributed_by_employee_id | uuid | FK `employees.id`, ON DELETE SET NULL |
| file_path | String(1000) | di sản |
| url | String(2000) | |
| minio_key | String(500) | Khóa đối tượng gốc |
| file_name | String(500) | |
| file_size | Integer | byte |
| content_hash | String(64) | có index, SHA-256 hex |
| attempt_id | uuid | mặc định uuid4. Định danh lần nạp toàn tài liệu |
| status | String(50) | mặc định `pending`. Trạng thái tổng hợp |
| error_message | Text | |
| progress | Integer | mặc định 0 |
| progress_message | String(500) | |
| job_id | String(200) | id job arq gần nhất |
| chunk_status | String(50) | mặc định `pending` |
| chunk_progress | Integer | 0 |
| chunk_progress_message | String(500) | |
| chunk_attempt_id | uuid | null được |
| chunk_error_message | Text | |
| wiki_status | String(50) | mặc định `pending` |
| wiki_progress | Integer | 0 |
| wiki_progress_message | String(500) | |
| wiki_attempt_id | uuid | null được |
| wiki_error_message | Text | |
| extracted_token_count | Integer | null được |
| auto_recover_count | Integer | not null, mặc định 0 |
| pipeline_strategy | String(20) | `single_pass`, `standard`, `hierarchical` |
| pipeline_phase | String(30) | `map`, `reduce`, `plan_review`, `refine`, `verify`, `commit` |
| preserve_verbatim | Boolean | not null, mặc định false |
| outline_json | JSONB | Cây heading |
| page_offsets | JSONB | Danh sách offset ký tự đầu mỗi trang |
| metadata (thuộc tính Python `metadata_`) | JSONB | Khóa con `doc` chứa thông tin văn bản, xem doc_metadata_service |
| created_at | timestamptz | server now |
| updated_at | timestamptz | server now, tự cập nhật khi sửa |

Quy tắc ghi:
- Khi gán `progress_message`, `chunk_progress_message` hoặc `wiki_progress_message`, chuỗi dài hơn 500 ký tự bị cắt còn 499 ký tự và nối thêm dấu `…`. Có thể làm bằng validator của mô hình.
- Quan hệ cần có: `knowledge_type`, `contributor` (Employee), `departments` (danh sách SourceDepartment, mỗi phần tử có quan hệ `department`), `images`.

### 3.2 `source_departments`
- Cột: source_id (FK sources, CASCADE) và department_id (FK departments, CASCADE).
- Khóa chính ghép trên cả hai cột.
- Tài liệu không có dòng nào ở bảng này là tài liệu toàn cục.

### 3.3 `source_images` (mô hình `SourceImage`)

| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | uuid | PK. Đây chính là uuid trong marker `image://` |
| source_id | uuid | FK sources CASCADE, có index |
| minio_key | Text | not null |
| page_number | Integer | null được (DOCX) |
| image_index | Integer | not null |
| caption | Text | null được |
| content_type | String(64) | not null |
| size_bytes | Integer | not null |
| created_at | timestamptz | |

- Ràng buộc unique trên (source_id, image_index).
- Quan hệ `source`.

### 3.4 `source_compilation_plans` (mô hình `SourceCompilationPlan`)

| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | uuid | PK |
| source_id | uuid | FK sources CASCADE, unique |
| plan_json | JSONB | not null, mặc định `{}` |
| status | String(30) | mặc định `pending_review`. Giá trị: `pending_review`, `approved`, `rejected`, `regenerating` |
| reviewed_by | uuid | FK employees SET NULL |
| review_note | Text | |
| created_at | timestamptz | |
| reviewed_at | timestamptz | null được |

- Có index trên status.
- Các khóa nội bộ trong plan_json (`_claims`, `_entities`, `_concepts`, `_page_drafts`) không bao giờ trả ra API.

### 3.5 `knowledge_types` (mô hình `KnowledgeType`)
- Cột: id uuid PK; slug String(50) unique not null; name String(100) not null; color String(20) mặc định `#6366f1`; description Text; sort_order Integer mặc định 0; created_at.

### 3.6 `notes` (mô hình `Note`)
- Cột: id uuid PK; title String(500); content Text; note_type String(50); created_at; updated_at.

### 3.7 `task_failures` (mô hình `TaskFailure`, module `app.models.task_failure`)

| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | uuid | PK, mặc định uuid4 |
| source_id | uuid | FK sources SET NULL, null được, có index |
| attempt_id | String(100) | null được |
| task_name | String(100) | not null, có index |
| error_type | String(255) | not null |
| error_message | Text | not null |
| traceback | Text | null được |
| payload_json | JSON | null được |
| status | String(20) | not null, mặc định `pending`. Giá trị: `pending`, `resolved`, `retried` |
| retry_count | Integer | not null, mặc định 0 |
| created_at, updated_at | timestamptz | server now. updated_at tự cập nhật |

- Có index ghép (status, created_at).
- Phương thức `to_dict()` trả về các khóa sau:
  - id, source_id, created_at, updated_at là chuỗi. source_id có thể None; hai mốc thời gian ở dạng ISO và có thể None.
  - attempt_id, task_name, error_type, error_message, traceback, payload_json, status, retry_count.

### 3.8 `source_stage_timings` (mô hình `SourceStageTiming`)
- Cột: id uuid PK; source_id FK sources CASCADE not null, có index; stage_name String(50) not null, có index; duration_ms Integer not null; metadata_json JSON; created_at.
- Có index ghép (source_id, stage_name).
- `to_dict()` trả về id, source_id, stage_name, duration_ms, metadata_json và created_at (ISO hoặc None).

### 3.9 Hai hàm ghi trong `app.models.task_failure`

**`async record_task_failure(session, task_name, error, source_id=None, attempt_id=None, payload=None, tb=None) -> TaskFailure`**
1. Tạo TaskFailure với các giá trị:
   - error_type là tên lớp của ngoại lệ;
   - error_message là chuỗi của ngoại lệ;
   - traceback là `tb` nếu có, nếu không thì định dạng traceback của ngoại lệ;
   - payload_json là `payload`;
   - status `pending`, retry_count 0.
2. Gọi `session.add(failure)` đúng một lần, rồi await `session.commit()` đúng một lần.
3. Commit lỗi chỉ được log, không ném ra ngoài.
4. Trả về đối tượng vừa tạo.

**`async record_stage_timing(session, source_id, stage_name, duration_ms, metadata=None) -> SourceStageTiming`**
1. Tạo bản ghi với metadata_json là `metadata` hoặc `{}`.
2. Gọi add một lần và commit một lần.
3. Lỗi commit chỉ được log.
4. Trả về đối tượng vừa tạo.

---

## 4. Lưu trữ MinIO (`app.services.storage_service`)

Lớp `StorageService` có singleton cấp module tên `storage_service`. Có hai client:
- client thao tác dùng `minio_endpoint`;
- client ký URL dùng endpoint công khai và đặt sẵn vùng `us-east-1`, để khỏi phải gọi mạng khi ký.

| Phương thức | Hành vi |
|---|---|
| `async ensure_bucket()` | Tạo bucket nếu chưa có |
| `upload_file(object_name, data: bytes, content_type="application/octet-stream") -> str` | Ghi đối tượng, trả về khóa |
| `download_file(object_name) -> bytes` | Đọc toàn bộ nội dung |
| `upload_stream(object_name, stream, length, content_type)` | Ghi từ luồng với độ dài biết trước |
| `async upload_stream_async(object_name, stream, length, content_type)` | Chạy `upload_stream` trong thread, trả về khóa |
| `get_presigned_url(object_name, expiry_hours=None) -> str` | URL GET ký sẵn. None thì dùng `minio_presign_expiry_hours` |
| `delete_object(object_name)` | Xóa một đối tượng |
| `list_objects(prefix, recursive=True)` | Liệt kê đối tượng theo tiền tố |
| `delete_prefix(prefix)` | Xóa mọi đối tượng dưới tiền tố |
| `copy_object(src, dest)`, `copy_prefix(src_prefix, dest_prefix)`, `move_prefix(src_prefix, dest_prefix)` | Sao chép hoặc chuyển |
| `calculate_prefix_hash(prefix) -> str` | SHA-256 trên chuỗi các cặp (đường dẫn tương đối, etag), sắp xếp theo đường dẫn |

Quy ước khóa đối tượng:

| Đối tượng | Khóa |
|---|---|
| Tệp gốc | `sources/{source_id}/original/{file_name}` |
| Ảnh PDF | `sources/{source_id}/images/page{p}_{idx}.{ext}` |
| Ảnh DOCX | `sources/{source_id}/images/docx_{idx}.{ext}` |
| Ảnh PPTX | `sources/{source_id}/images/slide{n}_{idx}.{ext}` |

Khi xóa tài liệu, toàn bộ tiền tố `sources/{source_id}/` bị xóa.

---

## 5. API

Quy ước chung:
- `get_current_user` nghĩa là cần đăng nhập.
- `require_permission("x")` nghĩa là cần quyền x ở bất kỳ phạm vi nào (`x:own_dept` hoặc `x:all`); admin luôn qua.
- `require_admin` nghĩa là chỉ dành cho admin.
- Thông báo lỗi trả trong trường `detail` và phải giữ đúng nguyên văn.

### 5.1 Đối tượng SourceResponse

Mọi endpoint trả về tài liệu đều dùng hàm `_to_response(source, wiki_page_count=0, image_count=0, lifecycle=None) -> SourceResponse`. Các trường:

| Trường | Kiểu | Nguồn |
|---|---|---|
| id | uuid | |
| security_label | str | Nhãn đã chuẩn hóa, mặc định `INTERNAL` |
| title, source_type, file_name, url | str hoặc null | |
| file_size | int hoặc null | |
| status | str | |
| error_message, progress_message, job_id | str hoặc null | |
| progress | int | |
| page_count | int | Độ dài `page_offsets`, rỗng thì 0 |
| wiki_page_count | int | Số trang wiki mà `source_ids` chứa tài liệu này |
| extracted_token_count | int hoặc null | |
| image_count | int | Số dòng source_images |
| auto_recover_count | int | null thì 0 |
| knowledge_type_id | uuid hoặc null | |
| knowledge_type_name, knowledge_type_color | str hoặc null | Lấy từ quan hệ |
| department_ids, department_names | list[str] | Lấy từ quan hệ departments |
| contributed_by_employee_id | uuid hoặc null | |
| contributed_by_name | str hoặc null | Tên của contributor |
| scope_type | str | null thì `global` |
| scope_id | uuid hoặc null | |
| preserve_verbatim | bool | |
| chunk_status, wiki_status | str | null thì `pending` |
| chunk_progress, wiki_progress | int | null thì 0 |
| chunk_progress_message, chunk_error_message, wiki_progress_message, wiki_error_message | str hoặc null | |
| doc_meta | object hoặc null | `get_doc_meta(source)`. Nếu khác rỗng thì thêm khóa `validity = compute_validity(meta, lifecycle)` |
| created_at, updated_at | str ISO | |

SourceDetail mở rộng SourceResponse bằng các trường:
- `full_text`;
- `outline` (lấy từ outline_json);
- `download_url`, `preview_url`, `file_url`.

Các truy vấn tài liệu nạp sẵn knowledge_type, departments kèm department, và contributor.

### 5.2 GET /api/sources
- **Quyền:** cần đăng nhập. Phạm vi được lọc bởi `source_read_filter(user)` (tài liệu 02).
  - Không có quyền doc:read nào: 403.
  - `allowed=False`: trả `{items: [], total: 0, page, page_size, total_pages: 1}`.
- **Tham số query:**
  - `knowledge_type_id` (uuid).
  - `department_id` (uuid): chỉ lấy tài liệu có dòng source_departments với phòng ban này.
  - `status`: một trạng thái hoặc danh sách phân tách bằng dấu phẩy, bỏ phần tử rỗng.
  - `search`: so khớp không phân biệt hoa thường, dạng chứa chuỗi con, trên title hoặc file_name.
  - `sort`: mặc định `created_desc`.
  - `page`: ≥ 1, mặc định 1.
  - `page_size`: 1–5000, mặc định 20.
- **Sắp xếp:** tách `sort` tại dấu gạch dưới cuối cùng thành trường và chiều.
  - Chiều khác `asc` đều hiểu là giảm dần.
  - `created` sắp theo created_at. `title` sắp theo title viết thường.
  - `issued` sắp theo chuỗi `metadata.doc.issued_date`, `effective` theo chuỗi `metadata.doc.effective_date`.
  - Trường lạ thì dùng created_at.
  - Giá trị null luôn xếp cuối. Tiêu chí phụ là created_at giảm dần.
- **Phản hồi:** `{items: SourceResponse[], total, page, page_size, total_pages}`.
  - `total_pages` = max(1, trần(total / page_size)).
  - Với mỗi item, lifecycle lấy bằng `load_lifecycle` với các doc_number có trong trang, sau đó `lifecycle_for` cho từng tài liệu.

### 5.3 GET /api/sources/{id}
- **Quyền:** cần đăng nhập và `can_access_document(db, user, source, "read")`.
- **Lỗi:** không thấy tài liệu: 404 `Source not found`. Bị từ chối: 403 `Access denied`.
- **Phản hồi:** SourceDetail. Nếu có minio_key:
  - tạo vé tệp `create_source_file_token(str(user.id), str(source.id))`;
  - `download_url` = `/api/sources/{id}/file?download=1&token={vé}`;
  - `preview_url` = `/api/sources/{id}/preview?token={vé}`;
  - `file_url` = `/api/sources/{id}/file?token={vé}`.
- Không bao giờ đưa token phiên vào URL. Tạo vé lỗi thì để các URL là null.

### 5.4 GET /api/sources/{id}/file
- **Xác thực:** `_authenticate_request_user(token, credentials, db, source_id)` (tài liệu 02), nhận vé `?token=` hoặc header Bearer.
  - Không có cả hai: 401 `Not authenticated`.
  - Vé sai hoặc hết hạn: 401 `Invalid or expired token`.
  - Chủ thể vé không phải UUID: 401 `Invalid token subject`.
  - Không thấy nhân viên hoặc nhân viên bị khóa: 401 `User not found or inactive`.
- **Tham số:** `download` (bool, mặc định false).
- **Lỗi khác:**
  - Không thấy tài liệu: 404 `Source not found`.
  - Không đọc được: 403 `Access denied`.
  - Chưa có minio_key: 404 `Source file not stored`.
  - Lỗi đọc MinIO: 500 `Failed to retrieve file from storage`.
- **Phản hồi:** nội dung nhị phân, media type đoán theo đuôi tệp (bảng ở 5.5). Header:
  - `Content-Disposition`: `attachment` khi download, ngược lại `inline`. Có filename đã URL-encode, kèm dạng `filename*=UTF-8''`.
  - `Content-Length`.
  - `Cache-Control: no-store`.

### 5.5 GET /api/sources/{id}/preview
- Xác thực và các lỗi giống 5.4.
- Media type theo đuôi:

| Đuôi | Media type |
|---|---|
| pdf | `application/pdf` |
| docx | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` |
| doc | `application/msword` |
| xlsx | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |
| xls | `application/vnd.ms-excel` |
| pptx | `application/vnd.openxmlformats-officedocument.presentationml.presentation` |
| ppt | `application/vnd.ms-powerpoint` |
| png | `image/png` |
| jpg, jpeg | `image/jpeg` |
| gif | `image/gif` |
| webp | `image/webp` |
| svg | `image/svg+xml` |
| txt | `text/plain; charset=utf-8` |
| csv | `text/csv; charset=utf-8` |
| md | `text/markdown; charset=utf-8` |
| json | `application/json` |
| khác | `application/octet-stream` |

- Hành vi theo đuôi của file_name (viết thường). Mọi phản hồi đều có `Cache-Control: no-store`.
  1. **PDF và ảnh** (png, jpg, jpeg, gif, webp, svg): trả thẳng nội dung với `Content-Disposition: inline` và Content-Length.
  2. **docx/doc:** chuyển sang HTML bằng thư viện mammoth, đặt trong một trang HTML hoàn chỉnh `lang="vi"`, tiêu đề là title hoặc file_name.
     - Bố cục: thẻ giấy trắng rộng tối đa khoảng 880px, căn giữa trên nền xám nhạt, chữ sans-serif, dòng cao 1.7. Bảng có viền, ô tiêu đề nền nhạt, dòng chẵn tô nền. Có kiểu in ấn bỏ bóng.
     - Chuyển đổi lỗi: thân trang là đoạn nghiêng `Không thể trích xuất định dạng HTML: {lỗi}`, theo sau là full_text trong khối giữ định dạng.
  3. **xlsx/xls/csv:** đọc bằng pandas.
     - CSV: tiêu đề `Dữ liệu CSV` và một bảng.
     - Excel: tối đa 10 sheet, mỗi sheet có tiêu đề `Sheet: {tên} ({n} dòng)` và một bảng.
     - Lỗi: đoạn `Lỗi đọc bảng tính: {lỗi}`.
     - Trang rộng gần toàn màn hình, cuộn ngang được, tiêu đề cột dính khi cuộn.
  4. **txt, md, json, xml, yaml, yml, py, sql:** giải mã UTF-8 (thay ký tự lỗi), escape HTML, hiển thị trong khối giữ định dạng chữ đơn cách, nền tối, tự xuống dòng.
  5. **Còn lại:** trả nội dung thô với media type đoán được.

### 5.6 GET /api/sources/{id}/progress
- **Quyền:** `doc:read`.
- **Lỗi:** 404 `Source not found`.
- **Phản hồi:** `{id: str, status, progress, progress_message, page_count, wiki_page_count}`.

### 5.7 POST /api/sources/upload (multipart)

Hàm `upload_source(file, title=None, knowledge_type_id=None, department_ids=None, scope_type=None, scope_id=None, preserve_verbatim=False, security_label=None, db, user)`. Test gọi trực tiếp với tham số từ khóa, có thể bỏ `security_label`. Khi đó giá trị nhận được là đối tượng mặc định của Form, không phải chuỗi, và phải coi như None.

- **Quyền:** `doc:create`.
- **Trường form:**
  - `file` (bắt buộc);
  - `title`;
  - `knowledge_type_id` (chuỗi uuid);
  - `department_ids` (uuid phân tách bằng dấu phẩy);
  - `scope_type`, `scope_id`;
  - `preserve_verbatim` (bool, mặc định false);
  - `security_label`.
- **Thứ tự xử lý (giữ đúng):**
  1. `label = _checked_label(user, security_label)`. Giá trị không phải chuỗi coi là None, tức `INTERNAL`.
  2. `upload_guard.validate(file.filename, file.file, upload_guard.parse_extensions(settings.allowed_upload_extensions))` trả về (file_name, ext).
     - Nếu ném `UploadRejected`: ghi audit `log_audit(db, user, "source.upload_rejected", "source", "-", decision="DENY", reason="{code}: ext={10 ký tự đầu của đuôi}")`, rồi trả HTTP `rejection.status` với `rejection.message`.
  3. Đuôi `doc`, `ppt` hoặc `rtf` mà `libreoffice_converter.is_available()` sai: 400 `Định dạng file .{ext} cần LibreOffice để chuyển đổi nhưng máy chủ chưa cài đặt. Vui lòng chuyển đổi file sang định dạng .docx hoặc .pdf trước khi tải lên.`
  4. Đọc tệp theo khối 64 KiB, cộng dồn kích thước và băm SHA-256. Không giữ cả tệp trong bộ nhớ.
     - Vượt `max_upload_size_bytes`: 413 `File tải lên vượt quá giới hạn dung lượng ({N}MB).` với N là phần nguyên của max_upload_size_bytes chia 1048576.
  5. **Chống trùng:** tìm Source có cùng content_hash và status khác `error`. Truy vấn này dùng `execute(...).scalars().first()` và là lần execute đầu tiên.
     - Tìm thấy: 409 `Tài liệu này đã tồn tại trên hệ thống (ID: {id}, Tiêu đề: '{title}').`
     - Tài liệu trùng ở trạng thái error không chặn tải lên lại.
  6. Phân tích `department_ids`. Phần tử không phải uuid: 400 `Invalid department_id: {d}`.
  7. `scope_type` không thuộc global/department/personal: 400 `scope_type phải là global, department hoặc personal`.
     - Với `personal`: bỏ mọi phòng ban, scope_id = id người tải, preserve_verbatim = true.
  8. Người không phải admin và không có `doc:create:all`: mọi phòng ban gán phải thuộc `user.department_ids`, nếu không thì 403 `You can only assign documents to your own departments`.
  9. Tạo Source qua `Repository(db).create(source)` với các giá trị:
     - title = title hoặc file_name;
     - source_type `file`, file_name, file_size = tổng byte, content_hash;
     - attempt_id = uuid mới;
     - status `pending`, progress 0, progress_message `Queued for ingestion...`;
     - knowledge_type_id, contributed_by_employee_id = user.id;
     - scope_type (mặc định `global`), scope_id, preserve_verbatim;
     - security_label = label.

     Sau đó flush, thêm các dòng SourceDepartment, flush lại, ghi audit `log_audit(db, user, "create", "source", id, reason="{title} [{label}]")`, commit và refresh.
  10. Tua tệp về đầu, rồi gọi `storage_service.upload_stream_async(object_name="sources/{id}/original/{file_name}", stream=file.file, length=tổng byte, content_type=_guess_content_type(file_name))`. Truyền đúng bốn tham số từ khóa này. Gán minio_key và file_name, rồi commit.
  11. Đẩy job `ingest_file_task` với (str(id), str(attempt_id)), gán job_id, commit.
  12. Nạp lại tài liệu kèm quan hệ (lần execute thứ hai, `scalar_one()`) và trả `_to_response(source)`.
- Trong luồng không lỗi chỉ có đúng hai lần `db.execute`: lần chống trùng và lần nạp lại. Kiểm tra phòng ban không dùng execute.

**`_guess_content_type(file_name) -> str`** (trong kb_service):

| Đuôi | Content type |
|---|---|
| pdf | `application/pdf` |
| docx | MIME wordprocessingml |
| doc | `application/msword` |
| txt | `text/plain` |
| md | `text/markdown` |
| csv | `text/csv` |
| xlsx | MIME spreadsheetml |
| pptx | MIME presentationml |
| khác | `application/octet-stream` |

### 5.8 POST /api/sources/url (JSON)
- **Quyền:** `doc:create`.
- **Body:**

| Trường | Kiểu | Mặc định |
|---|---|---|
| url | str | bắt buộc |
| title | str | null |
| knowledge_type_id | uuid | null |
| department_ids | uuid[] | `[]` |
| scope_type | str | null |
| preserve_verbatim | bool | false |
| security_label | str | null |

- **Xử lý:**
  - Kiểm nhãn bằng `_checked_label`.
  - scope_type sai: 400 như 5.7.
  - personal: bỏ phòng ban, scope_id = user.id, preserve_verbatim = true.
  - Kiểm phòng ban như 5.7.
  - Tạo Source với title = title hoặc url, source_type `url`, status `pending`, progress 0, `Queued for ingestion...`.
  - Thêm phòng ban, ghi audit `create`, commit.
  - Đẩy `ingest_url_task` với (id[, attempt_id]), gán job_id.
- **Phản hồi:** SourceResponse.

### 5.9 PATCH /api/sources/{id} (cập nhật metadata và phạm vi)
- **Quyền:** `doc:edit`.
- **Body (mọi trường tùy chọn):**
  - `title`;
  - `knowledge_type_id`;
  - `department_ids` (uuid[]);
  - `scope_type`, `scope_id`;
  - `security_label`;
  - `doc_meta` (map chuỗi sang chuỗi hoặc null).
- **Xử lý:**
  1. Không thấy tài liệu: 404 `Source not found`. Tài liệu cá nhân của người khác, khi người gọi không phải admin, cũng trả 404 này.
  2. scope_type sai: 400 `scope_type phải là global, department hoặc personal`.
  3. Chụp các thông tin cũ trước mọi thay đổi:
     - tập phòng ban cũ;
     - scope_type và scope_id cũ;
     - danh sách phạm vi wiki cũ `old_scopes = await _resolve_wiki_scopes(db, source)`, là các cặp (scope_type, scope_id);
     - cờ `was_compiled = not preserve_verbatim`.
  4. Có security_label:
     - Người không phải admin và không có `doc:edit:all`: 403 `Chỉ quản trị viên hoặc người có doc:edit:all được đổi nhãn bảo mật`.
     - Kiểm bằng `_checked_label`. Nếu khác nhãn cũ thì gán và ghi nhận chuỗi `OLD->NEW`.
  5. title và knowledge_type_id: gán khi khác null.
  6. doc_meta khác rỗng: `apply_manual_doc_meta(source, doc_meta)`. Nếu ném ValueError thì 400 với nội dung lỗi.
  7. Có scope_type: gán scope_type.
     - personal: scope_id = contributed_by_employee_id, hoặc user.id nếu không có.
     - Các loại khác: scope_id = null. Trường scope_id trong body không được dùng.
  8. Phòng ban:
     - `department_ids` khác null và không chuyển sang personal:
       - Người không phải admin và không có `doc:edit:all` phải gán đúng phòng ban của mình, nếu không thì 403 `You can only assign documents to your own departments`.
       - Xóa các dòng cũ và thêm dòng mới.
     - Nếu không, khi scope_type là `global` hoặc `personal`: xóa mọi dòng phòng ban.
  9. `scope_changed` đúng khi scope_type, scope_id hoặc tập phòng ban khác giá trị cũ.
  10. Ghi audit `update` với reason `{title} [security_label OLD->NEW]` khi nhãn đổi, nếu không thì reason là title. Sau đó flush.
  11. Chuyển sang personal và scope_changed:
      - preserve_verbatim = true;
      - wiki_status `skipped`, wiki_progress 100, wiki_progress_message `Skipped (personal source)`;
      - nếu `was_compiled`: đẩy `detach_source_wiki_task(id, [[scope_type, str(scope_id) hoặc null], ...])` từ old_scopes.
  12. scope_changed, status thuộc ready/partial và không verbatim:
      - wiki_status `queued`, wiki_progress 0, wiki_progress_message `Re-queued scope reassignment...`;
      - xóa wiki_error_message và error_message;
      - `update_source_dual_status`, flush;
      - đẩy `reassign_source_scope_task(id, old_scopes đã tuần tự hóa như trên)`, gán job_id.
  13. Commit, nạp lại và trả SourceResponse kèm wiki_page_count.
- API phải trả lời ngay. Việc gỡ khỏi wiki cũ và biên soạn lại luôn chạy nền.

### 5.10 POST /api/sources/{id}/retry

Hàm `retry_source(source_id, branch=None, db, _user)`. Test gọi với tham số từ khóa `source_id=, branch=, db=, _user=`.

- **Quyền:** `doc:edit`.
- **Query `branch`:** một trong `chunk`, `wiki`, `all`, hoặc bỏ trống.
- **Kiểm tra theo thứ tự:**
  1. Tài liệu nạp bằng `execute(...).scalar_one_or_none()`. Không có: 404 `Source not found`.
  2. status không thuộc ('error', 'partial', 'plan_ready'): 400 `Retry is only allowed for sources in ('error', 'partial', 'plan_ready') status`.
  3. auto_recover_count ≥ `max_auto_recover_attempts` và người gọi không phải admin: 409 `This source has failed {n} consecutive auto-recoveries (cap={cap}). Check LLM provider config and the source file, then ask an admin to reset and retry.`
  4. URL mà không có url: 400 `Source has no URL to retry`. Tệp mà không có minio_key: 400 `Source file not found in storage`.
- **Chọn nhánh.** Các biến dùng để chọn:
  - has_text: full_text sau khi cắt khoảng trắng khác rỗng;
  - chunk_failed: chunk_status = `error`;
  - wiki_failed: wiki_status = `error`, hoặc status trước đó = `plan_ready`;
  - legacy: cả chunk_status và wiki_status đều là `pending` (null coi là pending).

  Khi branch bỏ trống:
  - Không có text, hoặc legacy, hoặc không nhánh nào lỗi: chọn `all`.
  - Cả hai nhánh lỗi: chọn `both`.
  - Chỉ chunk lỗi: chọn `chunk`. Chỉ wiki lỗi: chọn `wiki`.

  Sau đó:
  - Nhánh chunk, wiki hoặc both mà không có text: 400 `Source has no extracted text; retry with branch=all`.
  - Nhánh wiki hoặc both với tài liệu verbatim: đổi thành `chunk`.
- **Thực thi.** Trước hết xóa error_message.
  - **all:**
    - Tạo attempt_id mới, để mọi job cũ trở thành lỗi thời.
    - status `pending`, progress 0, progress_message `Queued for retry...`, flush.
    - Đẩy `ingest_url_task` hoặc `ingest_file_task` với đúng hai đối số (str(id), str(attempt_id mới)).
  - **chunk hoặc both:** `await app.worker.commit_and_enqueue_chunk_branch(db, source, attempt hiện tại)`.
  - **wiki hoặc both:**
    1. pipeline_phase thuộc refine/verify/commit: chọn tác vụ `ingest_refine_task`. Các trường hợp khác (map, reduce, plan_review, plan_ready, lỗi trước MAP) chọn `ingest_map_reduce_task`.
    2. wiki_status `queued`, wiki_progress 0, wiki_progress_message `Queued for retry...`, wiki_error_message null.
    3. `wiki_attempt = start_wiki_attempt(source)`. attempt_id toàn cục giữ nguyên, nên nhánh A đang chạy không bị ảnh hưởng.
    4. `update_source_dual_status`, commit.
    5. Đẩy tác vụ đã chọn với đúng (str(id), wiki_attempt).
- Gán job_id nếu có, commit, nạp lại và trả `_to_response`.

### 5.11 POST /api/sources/{id}/approve-extraction
- **Quyền:** `doc:edit`.
- **Lỗi:**
  - 404 `Source not found`.
  - Cả status và wiki_status đều khác `awaiting_approval`: 400 `Source is not awaiting approval (status={status})`.
- **Xử lý:**
  1. has_images = có ít nhất một dòng source_images.
  2. `job_id = await enqueue_post_extraction_pipeline(str(id), has_images=has_images, attempt_id_str=wiki_attempt_of(source))`.
  3. wiki_status `processing`, wiki_progress 56, wiki_progress_message `Captioning images before extraction...` khi có ảnh, ngược lại `Extraction queued...`.
  4. `update_source_dual_status`, gán job_id, ghi audit `approve` trên `source_extraction`, commit.
- **Phản hồi:** `{status: "processing", job_id, has_images, token_count: extracted_token_count}`.

### 5.12 Kế hoạch biên soạn (plan)

**GET /api/sources/{id}/plan**
- **Quyền:** `doc:read`.
- Không có kế hoạch: 404 `No compilation plan found for this source`.
- **Phản hồi:** `{id, source_id, status, plan (plan_json đã bỏ _claims, _entities, _concepts, _page_drafts), created_at, reviewed_at (ISO hoặc null), review_note}`.

**POST /api/sources/{id}/plan/approve**
- **Quyền:** `doc:edit`.
- **Body:** `{note?: str}`.
- **Kiểm tra:** khóa dòng kế hoạch (FOR UPDATE).
  - Không có: 404 `No plan found for this source`.
  - status `regenerating`: 409 `Plan is being regenerated. Wait for it to finish before approving.`
  - status khác `pending_review`: 400 `Plan is not pending review (status={s})`.
- **Xử lý:**
  1. Kế hoạch: status `approved`, reviewed_by = user, review_note = note, reviewed_at = bây giờ (UTC). Ghi audit `approve` trên `compilation_plan`.
  2. Tài liệu: wiki_status `refining`, wiki_progress 78, `Plan approved — compiling wiki pages...`, `update_source_dual_status`, flush.
  3. Đẩy `ingest_refine_task(id[, wiki_attempt_of(source)])`, gán job_id, commit.
- **Phản hồi:** `{approved: true, job_id}`.

**POST /api/sources/{id}/plan/reject**
- **Quyền:** `doc:edit`.
- **Body:** `{note: str}` (bắt buộc).
- Kiểm tra giống approve. Thông báo 409 là `Plan is being regenerated. Wait for it to finish before rejecting.`
- **Xử lý:**
  1. Kế hoạch: status `rejected`, reviewed_by, review_note, reviewed_at. Ghi audit `reject`.
  2. Tài liệu: wiki_status `error`, wiki_error_message = `Compilation plan rejected: {note}`, error_message bằng cùng chuỗi đó. `update_source_dual_status`, commit.
- **Phản hồi:** `{rejected: true}`.

**POST /api/sources/{id}/plan/regenerate**
- **Quyền:** `doc:edit`.
- **Body:** `{note: str}`.
- **Kiểm tra:**
  - note rỗng sau khi cắt khoảng trắng: 400 `Note is required to regenerate plan`.
  - Khóa dòng. Không có kế hoạch: 404 `No plan found for this source`.
  - status không thuộc pending_review/rejected: 400 `Plan cannot be regenerated (status={s})`.
- **Xử lý:** status `regenerating`, review_note = 1000 ký tự đầu của note, ghi audit `regenerate` (reason là 200 ký tự đầu), commit, rồi đẩy `regenerate_plan_task(id, note)`.
- **Phản hồi:** `{queued: true, status: "regenerating", job_id}`.
- Máy trạng thái kế hoạch:
  - pending_review sang approved, rejected hoặc regenerating;
  - rejected sang regenerating;
  - regenerating quay lại pending_review khi task xong, kể cả khi task thất bại (xem 12.9).

### 5.13 DELETE /api/sources/{id}
- **Quyền:** cần đăng nhập.
  - Không thấy, hoặc là tài liệu cá nhân của người khác khi người gọi không phải admin: 404 `Source not found`.
  - Chủ tài liệu cá nhân được tự xóa. Các trường hợp khác cần `can_access_document(..., "delete")`, nếu không thì 403 `Permission required: doc:delete`.
- **Xử lý** (các bước dọn dẹp lỗi chỉ được log):
  1. `storage_service.delete_prefix("sources/{id}/")`.
  2. `delete_source_chunk_embeddings(db, id)`.
  3. `wiki_service.detach_source_from_wiki(db, id)`, rồi `regenerate_index(db, scope_type=scope_type hoặc global, scope_id=scope_id)`.
  4. Ghi audit `delete`, xóa dòng.
- **Phản hồi:** `{deleted: true}`.

### 5.14 Loại tri thức (/api/knowledge-types)

DTO đầu ra:

| Trường | Kiểu |
|---|---|
| id | str |
| slug | str |
| name | str |
| color | str (null thì `#6366f1`) |
| description | str hoặc null |
| sort_order | int |
| source_count | int |

Tạo slug: chuyển về chữ thường, thay khoảng trắng bằng `-`, rồi chỉ giữ chữ thường a–z, chữ số và `-`. Body nhập có slug thì áp quy tắc này lên slug, không có thì sinh từ name.

| Method, path | Quyền | Body | Phản hồi / lỗi |
|---|---|---|---|
| GET /api/knowledge-types | không yêu cầu | | Danh sách sắp theo sort_order rồi name. source_count là số tài liệu theo knowledge_type_id |
| POST /api/knowledge-types | `documents.create` | `{name, slug?, color="#6366f1", description?}` | 201 với DTO, source_count 0. Trùng slug: 409 `Knowledge type with slug '{slug}' already exists`. sort_order = sort_order lớn nhất hiện có + 1 (không có thì 1) |
| PUT /api/knowledge-types/{kt_id} | `documents.edit` | như POST | Gán name, color, description; chỉ gán slug khi có. 404 `Knowledge type not found` |
| DELETE /api/knowledge-types/{kt_id} | `documents.delete` | | `{deleted: true, slug}`. 404 như trên. Tài liệu dùng loại này có knowledge_type_id thành null |
| PATCH /api/knowledge-types/reorder | `documents.edit` | mảng id theo thứ tự mong muốn | sort_order = vị trí (bắt đầu từ 0); id không tồn tại thì bỏ qua. Phản hồi `{reordered: số phần tử}` |

Route `/knowledge-types/reorder` phải đăng ký sao cho không bị nhầm với `{kt_id}`. PATCH chỉ có ở đường dẫn reorder.

### 5.15 Ghi chú (/api/notes)

| Method, path | Quyền | Body | Phản hồi |
|---|---|---|---|
| GET /api/notes | cần đăng nhập | | Mảng `{id, title, content, note_type, created_at, updated_at}`, mới nhất trước |
| POST /api/notes | `kb.create` | `{title?, content (bắt buộc), note_type="human"}` | Ghi chú vừa tạo |
| DELETE /api/notes/{note_id} | `kb.delete` | | `{deleted: true}`. Không có: 404 `Note not found` |

### 5.16 POST /api/wiki/images/resolve
- **Quyền:** cần đăng nhập.
- **Body:** `{ids: uuid[]}` (mặc định rỗng).
- **Hằng số:** `MAX_IDS_PER_REQUEST = 100`, `PRESIGN_EXPIRY_HOURS = 1`.
- **Xử lý:**
  1. ids rỗng: trả `{resolved: {}, denied: []}`.
  2. Quá 100 id: 400 `Too many ids (max 100 per request)`.
  3. Khử trùng id, nạp các SourceImage kèm source và departments của source.
  4. Với mỗi ảnh:
     - Quyết định truy cập bằng `can_access_document(db, user, source, "read")`, ghi nhớ theo source.
     - Không được phép: thêm id vào `denied`.
     - Được phép: `storage_service.get_presigned_url(minio_key, expiry_hours=1)`, đưa vào `resolved[id]`. Ký URL lỗi thì bỏ qua.
  5. Id không tồn tại không có mặt ở cả hai danh sách.
- **Phản hồi:** `{resolved: {uuid: url}, denied: [uuid]}`.

### 5.17 Dead-letter và thời gian giai đoạn (quyền `require_admin`)

**`list_task_failures(task_name=None, status=None, limit=50, offset=0, db, user)`**, GET /api/admin/failures
- Query: task_name, status (`pending`/`resolved`/`retried`), limit 1–200 (mặc định 50), offset ≥ 0.
- Truy vấn đếm chạy trước (`execute(...).scalar()`), truy vấn danh sách chạy sau (`execute(...).scalars().all()`).
- Danh sách sắp theo created_at giảm dần.
- **Phản hồi:** `{total, items: [to_dict()], offset, limit}`.

**`retry_task_failure(failure_id, db, user)`**, POST /api/admin/failures/{failure_id}/retry
- Không có bản ghi: 404 `Task failure record not found`.
- Lấy pool bằng `app.worker.get_arq_pool` (import lười) và đẩy `enqueue_job(task_name, **payload_json)` (payload rỗng thì `{}`).
- Lỗi khi đẩy: 500 `Failed to enqueue task: {lỗi}`.
- Thành công: status `retried`, retry_count + 1, commit đúng một lần.
- **Phản hồi:** `{ok: true, id, task_name, status, retry_count}`.

**`get_source_stage_timings(source_id, db, user)`**, GET /api/admin/timings/{source_id}
- Các giai đoạn sắp theo created_at tăng dần.
- **Phản hồi:** `{source_id: str, timings: [to_dict()], total_duration_ms: tổng duration_ms}`.

---

## 6. Trích xuất văn bản (`app.services.kb_service`)

### 6.1 `async _load_doc_processing_config() -> dict`
- Mở phiên riêng qua `app.database.async_session_factory` và đọc các khóa cấu hình ở mục 2 bằng `ConfigService`.
- Trả về dict với các khóa:
  - `pdf_engine`, `excel_engine`, `ocr_mode`;
  - `ocr_fallback_vision`, `ocr_llm_refine`, `strip_headers_footers`, `enhance_headings`;
  - `ocr_base_url`, `ocr_api_key`, `ocr_model`, `ocr_prompt`.
- Mọi ngoại lệ (không có DB, bảng chưa tạo, v.v.) đều được bắt: ghi cảnh báo và trả `{}`.

### 6.2 `async _extract_text_from_file(file_data: bytes, file_name: str, vision_provider=None, tracker=None) -> list[dict]`

Kết quả là danh sách trang, mỗi trang có dạng `{"content": str, "page_number": int, ...}`. Parser có thể thêm khóa, ví dụ `sheet_name`.

Đuôi lấy sau dấu chấm cuối cùng của tên tệp, viết thường.
- Cấu hình xử lý tài liệu chỉ được nạp với các đuôi pdf, xlsx, xls, doc, ppt, rtf.
- Hàm nạp được gọi qua tên module (`kb_service._load_doc_processing_config`) để test patch được.
- Tham số PDF dựng từ cấu hình, chỉ gồm những khóa có mặt và khác None:

| Tham số parser | Khóa cấu hình |
|---|---|
| engine | pdf_engine |
| ocr_mode | ocr_mode |
| ocr_fallback_vision | ocr_fallback_vision |
| ocr_llm_refine | ocr_llm_refine |
| strip_headers_footers | strip_headers_footers |
| enhance_headings | enhance_headings |
| ocr_base_url | ocr_base_url |
| ocr_api_key | ocr_api_key |
| ocr_model | ocr_model |
| ocr_prompt | ocr_prompt |

Định tuyến theo đuôi:

| Đuôi | Xử lý |
|---|---|
| pdf | `PDFParser().parse(file_data=, file_name=, vision_provider=, tracker=, **tham số PDF)` (tra `PDFParser` qua module `app.services.parsers.pdf_parser`) |
| xlsx, xls | `ExcelParser().parse(file_data=, file_name=, vision_provider=, tracker=, engine=excel_engine hoặc "openpyxl")` |
| csv | Đọc bằng pandas, xuất bảng markdown không chỉ số, trả một trang. Lỗi thì rơi xuống content-core |
| docx | `DocxParser().parse(...)`. Parser để lại placeholder ảnh ở đúng vị trí (xem 7.3) |
| pptx | `PPTXParser().parse(...)`, mỗi slide một trang (gồm cả ghi chú diễn giả) |
| txt, md | Giải mã UTF-8, bỏ byte lỗi, trả một trang |
| doc, ppt, rtf | Xem dưới |
| khác | Ghi ra tệp tạm có cùng đuôi, gọi content-core trích xuất ở dạng markdown, trả một trang, rồi xóa tệp tạm. Lỗi thì trả `[{"content": "", "page_number": 1}]` (không được giải mã nhị phân thành text) |

Với doc, ppt, rtf, dùng `libreoffice_converter` tra qua module `app.services.parsers.libreoffice_converter`:
- `is_available()` đúng:
  - `pdf = await convert_to_pdf(file_data, ext)`, gọi với đúng hai đối số vị trí.
  - Sau đó `PDFParser().parse(file_data=pdf, file_name="{file_name}.pdf", vision_provider=, tracker=, **tham số PDF)`.
  - Bất kỳ lỗi nào: ValueError `Không thể chuyển đổi file .{ext} sang PDF: {lỗi}`.
- `is_available()` sai: ValueError `Định dạng file .{ext} yêu cầu LibreOffice để chuyển đổi tự động nhưng hệ thống chưa cài đặt. Vui lòng chuyển đổi sang .docx hoặc .pdf trước khi tải lên.`

### 6.3 `async _extract_text_from_url(url) -> list[dict]`
- Thử content-core với `url` và đầu ra markdown.
- Lỗi thì GET bằng httpx, theo redirect, timeout 30 giây, trả `resp.text` thành trang 1.
- Kết quả luôn là danh sách một trang.

### 6.4 OCR
- PDF scan, hoặc trang không có lớp chữ, được OCR bên trong `PDFParser` theo `ocr_mode`:
  - `auto`: chỉ OCR trang scan;
  - `force`: OCR mọi trang;
  - các giá trị khác là tắt OCR.
- Máy chủ OCR tương thích OpenAI có cấu hình `ocr_base_url` / `ocr_model` / `ocr_api_key` / `ocr_prompt`. Có thể bật thêm `ocr_fallback_vision` (dùng vision provider khi máy chủ OCR lỗi) và `ocr_llm_refine` (LLM sửa bản nháp OCR).
- Toàn bộ logic đã có trong `app.services.ocr_service` (loại C), gồm:
  - `OCRService`;
  - `validate_ocr_text(text, *, truncated=False) -> (text, lý do hoặc None)`: loại phản hồi rỗng hoặc lặp vô hạn;
  - `normalize_ocr_base_url`;
  - `refine_ocr_with_llm` và `refine_drift(draft, refined)`: chặn bản sửa lệch quá nhiều.
- kb_service chỉ truyền tham số, không tự cài đặt lại OCR.

---

## 7. Ảnh (`app.services.image_service`)

### 7.1 Hằng số và kiểu dữ liệu
- `MIN_IMAGE_BYTES = 2048`. Ảnh nhỏ hơn bị coi là biểu tượng và bỏ qua (PDF và DOCX).
- Bảng đuôi sang MIME:

| Đuôi | MIME |
|---|---|
| png | image/png |
| jpg, jpeg | image/jpeg |
| gif | image/gif |
| bmp | image/bmp |
| tiff | image/tiff |
| webp | image/webp |
| svg | image/svg+xml |

  Đuôi không có trong bảng dùng `image/png`.
- Lớp `ImageInfo(minio_key, page_number, image_index, content_type, size_bytes, caption=None, image_id=None, ref=None)`.
  - Lưu các tham số thành thuộc tính cùng tên.
  - Test khởi tạo theo vị trí cho 5 tham số đầu và theo từ khóa cho các tham số sau.
  - `ref` là rId của quan hệ ảnh trong DOCX.
  - `image_id` là chuỗi uuid của dòng source_images, gán sau khi lưu.
- Module import ở cấp module các ký hiệu: `storage_service` (từ storage_service), `ProviderRegistry`, `get_spec`, `upsert_chunk_embedding` và `chunk_content_hash`. Test patch `app.services.image_service.storage_service`, `.ProviderRegistry`, `.get_spec` và `.upsert_chunk_embedding`.

### 7.2 Trích ảnh

Cả bốn hàm dùng chung bộ đếm `image_index` cho toàn tài liệu, bắt đầu từ 0. Bộ đếm chỉ tăng khi ảnh thực sự được giữ. Mỗi ảnh giữ lại được tải lên bằng `storage_service.upload_file(object_name=, data=, content_type=)`.

- **`extract_images_from_pdf(file_data, source_id) -> list[ImageInfo]`**
  - Mở bằng PyMuPDF và duyệt ảnh từng trang. Trang đánh số từ 1.
  - Bỏ ảnh nhỏ hơn MIN_IMAGE_BYTES.
  - Khóa `sources/{sid}/images/page{p}_{idx}.{ext}`, page_number = p.
  - Lỗi từng ảnh thì bỏ qua ảnh đó. Không mở được tệp thì trả `[]`.
- **`extract_images_from_docx(file_data, source_id)`**
  - Duyệt các quan hệ ảnh của gói DOCX.
  - Bỏ ảnh nhỏ hơn MIN_IMAGE_BYTES.
  - Đuôi lấy từ content type; `svg+xml` thành `svg`.
  - Khóa `sources/{sid}/images/docx_{idx}.{ext}`, page_number None, ref = rId.
- **`docx_image_blobs(file_data) -> dict[rId, (content_type, bytes)]`**
  - Mọi ảnh trong quan hệ của tài liệu, không lọc kích thước và không tải lên.
  - content_type thiếu thì dùng `image/png`. Không mở được thì trả `{}`.
  - Một DOCX có một ảnh trả về đúng một phần tử.
- **`extract_images_from_pptx(file_data, source_id)`**
  - Gom các shape ảnh của từng slide một cách đệ quy, kể cả trong group shape.
  - page_number = số thứ tự slide (từ 1).
  - Đuôi và content type lấy từ đối tượng ảnh.
  - Khóa `sources/{sid}/images/slide{n}_{idx}.{ext}`. Ảnh đầu tiên nằm ở slide 3 sẽ có khóa `slide3_0.png`.
  - Gọi upload_file đúng một lần cho mỗi ảnh. Không lọc kích thước.
- **`extract_images(file_data, file_name, source_id)`**
  - Chọn hàm theo đuôi pdf, docx hoặc pptx (không phân biệt hoa thường).
  - Đuôi khác trả `[]`.

### 7.3 Marker ảnh trong văn bản: `_inline_image_markers(pages_data, images) -> None` (kb_service)
- Placeholder do parser DOCX để lại có dạng `<!--img:REF-->`. Hằng `IMAGE_PLACEHOLDER_RE` và hàm `image_placeholder(ref)` nằm ở `app.services.parsers.base`.
- Marker có dạng `![alt](image://{image_id})`.
  - alt là caption đã làm sạch: thay xuống dòng bằng khoảng trắng, `[` thành `(`, `]` thành `)`, rồi cắt khoảng trắng.
  - Không có caption thì alt rỗng.
- Quy tắc:
  1. Bỏ qua ảnh không có image_id.
  2. Ảnh có `ref` được gom theo ref. Ảnh không có ref được gom theo trang (`page_number`, hoặc 1 nếu không có).
  3. Trong mỗi trang có placeholder:
     - Placeholder có ref khớp và chưa được đặt: thay bằng marker có một dòng trống trước và sau. Mỗi ref chỉ đặt một lần.
     - Placeholder không khớp, hoặc đã đặt: xóa đi.
     - Sau đó gộp ba lần xuống dòng trở lên thành hai.
  4. Ảnh có ref nhưng không có placeholder nào được đặt sẽ nối vào cuối trang 1.
  5. Ảnh theo trang được nối vào cuối trang tương ứng. Các marker cách nhau một dòng trống, cả khối có một dòng trống phía trước và một xuống dòng phía sau.
- Hàm sửa `pages_data` tại chỗ.
- Kết quả bắt buộc:
  - Không còn chuỗi `<!--img:` nào.
  - Thứ tự đoạn văn quanh ảnh được giữ, ví dụ "Bước 1", ảnh, "Hình 1", "Bước 2".
  - Danh sách ảnh rỗng thì chỉ xóa placeholder.

### 7.4 Chú thích ảnh và chunk ảnh
- **`create_image_chunk(image_info, chunk_type, text) -> dict`**
  - Các khóa: `chunk_type`, `text`, `page_number` (page_number của ảnh, hoặc 1), `image_id`, `minio_key`.
  - text được thêm tiền tố `[{chunk_type} | Trang {page}]: `, trừ khi text sau khi cắt khoảng trắng đã bắt đầu bằng `[{chunk_type}`.
  - chunk_type thường là `image_caption` hoặc `image_ocr`.
- **`async index_image_chunks(session, source_id, chunks, spec_id=None) -> int`**
  1. chunks rỗng: trả 0.
  2. Tạo `registry = ProviderRegistry(session)`. spec_id = tham số, hoặc `await registry.get_active_embedding_spec_id()`. Không có thì trả 0.
  3. `spec = get_spec(spec_id)`, `provider = await registry.get_embedding(task="document", spec_id=spec_id)`.
  4. Gọi `embed_batch` một lần cho mọi text.
  5. Với chunk thứ i, gọi `upsert_chunk_embedding` với tham số từ khóa:
     - session, source_id, chunk_index = 80000 + i, spec, vector;
     - text, start_char = 0, end_char = độ dài text;
     - page_number = page_number của chunk, hoặc 1;
     - content_hash = `chunk_content_hash(text)`.
  6. Trả số chunk.

  Dải chỉ số 80000 trở lên dành cho chunk ảnh, để không đụng chunk văn bản.

---

## 8. Outline và offset trang (`app.services.source_outline`)

| Ký hiệu | Hành vi |
|---|---|
| `PAGE_JOIN_SEPARATOR = "\n\n"` | |
| `assemble_full_text(pages) -> (full_text, page_offsets)` | Chuẩn hóa nội dung từng trang bằng `app.core.text_normalizer.normalize_text`, rồi nối các trang bằng separator. page_offsets là vị trí bắt đầu của mỗi trang trong full_text |
| `slice_pages_by_range(full_text, page_offsets, page_numbers) -> list[{page, content}]` | Cắt nội dung các trang được yêu cầu (đánh số từ 1). Trang ngoài phạm vi bị bỏ |
| `parse_page_range(spec) -> list[int]` | Ví dụ `"5-7,3,8"` cho [3,5,6,7,8]: tăng dần, không trùng. Bỏ phần không hợp lệ và khoảng đảo ngược |
| `build_outline(pages) -> list[node]` | Tìm heading ATX markdown 1–6 dấu `#` (bỏ `#` ở cuối dòng). Nút gồm `{title, level, page, char_start, char_end, children}` |
| `slice_by_outline_node(full_text, start, end, max_chars=None)` | Cắt đoạn. Vượt max_chars thì cắt và nối `\n\n[…truncated…]` |
| `flatten_outline(nodes)` | Duyệt theo chiều sâu, trả danh sách `{title, level, page, char_start, char_end}` |
| `flatten_outline_with_depth(nodes, depth=0)` | Như trên, có thêm `_depth` |
| `find_smallest_node_containing(flat, offset)` | Nút nhỏ nhất có khoảng chứa offset, hoặc None |

Chi tiết `build_outline`:
- page = page_number của trang, hoặc thứ tự trang + 1.
- char_start tính trên con trỏ cộng dồn của nội dung thô (chưa chuẩn hóa) cộng separator.
- char_end = char_start của heading kế tiếp, hoặc tổng độ dài.
- Dựng cây bằng ngăn xếp theo level. Không có heading thì trả `[]`.

Đánh chỉ mục trang: trang i của full_text nằm từ `page_offsets[i]` đến `page_offsets[i+1] − 2` (bỏ separator). Trang cuối kéo đến hết văn bản.

---

## 9. Chia chunk văn bản gốc, nhánh A (`app.services.verbatim_service`)

### 9.1 Kiểu và hằng số
- Dataclass `SourceChunk` có các trường:
  - `index: int`;
  - `page_number: int` (từ 1);
  - `start_char: int`, `end_char: int`;
  - `text: str`;
  - `heading_path: str = ""`.
- `VerbatimChunk` là cùng một đối tượng với `SourceChunk` (test kiểm `VerbatimChunk is SourceChunk`).
- `MIN_CHUNK_CHARS = 50`.
- Ngân sách token lấy từ `app.services.chunk_budget` (loại C):
  - `CHUNK_TARGET_TOKENS`, kẹp vào [MIN_TARGET_TOKENS = 1000, MAX_TARGET_TOKENS = 2000];
  - `CHUNK_OVERLAP_TOKENS`, không quá một phần tư target;
  - `estimate_tokens(text)`;
  - `end_for_tokens(text, start, limit, tokens=CHUNK_TARGET_TOKENS)`: vị trí kết thúc sao cho đoạn đạt khoảng `tokens` token và không vượt `limit`;
  - `overlap_chars(span_chars)`: số ký tự gối đầu tương ứng với overlap cho một cửa sổ dài span_chars.

### 9.2 Nhận diện heading
- Dòng markdown `#` đến `######`: level = số dấu `#`, tiêu đề là phần còn lại.
- Dòng bắt đầu (không phân biệt hoa thường) bằng `Phần`, `Chương`, `Mục` hoặc `Điều`, theo sau là số Ả Rập hoặc La Mã: level lần lượt 1, 2, 3, 4. Tiêu đề là cả dòng.
- `heading_path` của chunk:
  - Duyệt các heading có vị trí trước điểm kết thúc của chunk. Nếu end ≤ start thì dùng điểm bắt đầu.
  - Dùng ngăn xếp: heading mới loại khỏi ngăn các heading cùng level hoặc sâu hơn, rồi được đẩy vào.
  - Kết quả là các tiêu đề trong ngăn nối bằng ` > `.
- Ví dụ: bảng nằm dưới `## Bảng tính: DanhSach` có heading_path đúng bằng `Bảng tính: DanhSach`.

### 9.3 `build_source_chunks(full_text, page_offsets, doc_title="") -> list[SourceChunk]`

`build_verbatim_chunks` là bí danh của hàm này.

1. Chia văn bản thành các trang theo page_offsets như mục 8. page_offsets rỗng thì cả văn bản là một trang; văn bản rỗng thì không có trang nào.
2. Trong mỗi trang, tìm **bảng lớn**:
   - một dãy liên tiếp từ 3 dòng trở lên, mọi dòng bắt đầu bằng `|`;
   - dòng thứ hai là dòng phân cách markdown (chỉ gồm `|`, `-`, `:` và khoảng trắng, có ít nhất một `-`);
   - ước lượng token của cả bảng vượt CHUNK_TARGET_TOKENS.

   Bảng nhỏ hơn được xử lý như văn bản thường.
3. **Bảng lớn** được chia theo dòng:
   - header gồm dòng tiêu đề và dòng phân cách, kèm xuống dòng.
   - Gom các dòng dữ liệu vào nhóm. Bắt đầu nhóm mới khi token(header) + token(nhóm) + token(dòng mới) + 1 vượt target.
   - text của chunk = header + các dòng của nhóm. start_char/end_char chỉ phủ phần dòng dữ liệu, nên text bỏ đi phần header đúng bằng `full_text[start:end]`.
   - Các nhóm không gối nhau. Mỗi dòng nằm trong đúng một chunk.
4. **Đoạn văn bản thường** (ngoài bảng lớn) chia theo cửa sổ trượt. Bắt đầu tại pos = đầu đoạn và lặp:
   1. Điểm cắt thô = `end_for_tokens(text, pos, cuối đoạn)`.
   2. Nắn điểm cắt theo thứ tự ưu tiên:
      1. Điểm cắt chạm hoặc vượt cuối đoạn: lấy cuối đoạn.
      2. Dấu xuống dòng gần nhất trước điểm cắt cách không quá 150 ký tự, và phần dòng sau nó bắt đầu bằng `|` (đang cắt giữa một dòng bảng): kéo điểm cắt tới dấu xuống dòng kế tiếp trong phạm vi 300 ký tự.
      3. Nếu không, tìm dòng trống (`\n\n`) cuối cùng trong 200 ký tự cuối, nhưng không sớm hơn pos + 50. Có thì cắt ngay sau nó.
      4. Nếu không, cắt ngay sau dấu xuống dòng đơn cuối cùng trong cùng vùng.
      5. Nếu không, giữ điểm cắt thô.
   3. Tạo chunk cho `[pos, end)`. text là đúng lát cắt, không cắt khoảng trắng.
   4. end tới cuối đoạn thì dừng. Ngược lại, pos tiếp theo = end − `overlap_chars(end − pos)`. Nếu giá trị đó không lớn hơn đầu đoạn hoặc pos hiện tại thì lấy pos = end, để tránh vòng lặp vô hạn.
5. Chỉ giữ chunk có text sau khi cắt khoảng trắng dài ít nhất 50 ký tự. index đánh liên tục từ 0. page_number là trang chứa chunk.

Các tính chất test kiểm:
- Văn bản ngắn (khoảng 5 câu) cho đúng một chunk.
- Với văn bản dài, mọi chunk trừ chunk cuối có từ 1000 đến 2000 token.
- Chunk đầu bắt đầu ở 0 và chunk cuối kết thúc ở cuối văn bản.
- Hai chunk liền kề thỏa `b.start_char < a.end_char <= b.end_char`, tức là gối đầu và không mất nội dung.
- Không dòng bảng nào bị cắt ngang: mọi dòng bắt đầu bằng `|` trong chunk đều kết thúc bằng `|`.
- Bảng dài: mọi chunk chứa bảng bắt đầu bằng header và có token ≤ target + 40. Các dòng ghép lại đúng bằng các dòng gốc. Đoạn văn sau bảng nằm ở chunk cuối.
- Bảng ngắn vừa một chunk: một chunk duy nhất, text = lát cắt.

### 9.4 `async index_source_chunks(session, source, spec_id=None) -> int`

`index_verbatim_source` là bí danh của hàm này.

1. full_text rỗng: trả 0.
2. Không có embedding spec đang hoạt động: ghi cảnh báo rằng chỉ còn tìm kiếm từ khóa, trả 0.
3. Xóa các dòng cũ của tài liệu và spec này trong bảng `get_source_chunk_embedding_model_for_dim(spec.dimension)`.
4. Dựng chunk bằng `build_source_chunks(full_text, page_offsets, doc_title=title)`.
5. Text dùng để nhúng có dạng `[{title} — {heading_path}]` + dòng trống + text.
   - Thiếu một trong hai phần thì chỉ dùng phần còn lại trong ngoặc.
   - Thiếu cả hai thì dùng text trần.
6. Nhúng theo lô 16 (embedding task `document`). Ghi bằng `upsert_chunk_embedding(session, source.id, chunk.index, spec, vector, text=text gốc, start_char, end_char, page_number, content_hash=chunk_content_hash(text gốc))`.
7. Commit, trả số chunk.

---

## 10. Trạng thái kép (`app.services.source_status`, loại C) và tiến độ

### 10.1 Trạng thái từng nhánh

| Nhánh | Trường | Giá trị |
|---|---|---|
| A (chunk và embed text gốc) | chunk_* | `pending`, `queued`, `extracting`, `chunking`, `embedding`, `processing`, `ready`, `error`, `skipped` |
| B (biên soạn wiki) | wiki_* | `pending`, `queued`, `processing`, `mapping`, `reducing`, `awaiting_approval`, `plan_ready`, `refining`, `verifying`, `indexing`, `ready`, `error`, `skipped` |

Tập hằng:
- `CHUNK_ACTIVE` = {queued, processing, extracting, chunking, embedding};
- `WIKI_GATES` = {awaiting_approval, plan_ready};
- `WIKI_ACTIVE` (trong `app.utils.progress`) = {queued, processing, mapping, reducing, refining, verifying, indexing}.

Chuyển trạng thái nhánh A:
1. pending → queued (5%, `Queued: chunk & embed raw text`).
2. queued → embedding (20%).
3. embedding → ready (100%) hoặc error (0%).

Với tài liệu verbatim, nhánh A đi pending → processing (60%) → ready ngay trong worker.

Chuyển trạng thái nhánh B:
1. pending → queued (50%) → processing (55%), sau đó qua caption ảnh nếu có.
2. processing → mapping (56%) → reducing.
3. reducing → plan_ready (80%) hoặc thẳng refining khi kế hoạch được tự duyệt.
4. refining (78%) → verifying → indexing → ready.
5. Lối rẽ thứ nhất: processing hoặc queued → awaiting_approval (55%, cổng trích xuất). Khi được duyệt thì → processing (56%).
6. Lối rẽ thứ hai: plan_ready → refining khi kế hoạch được duyệt, hoặc → error khi bị từ chối.
7. Mọi trạng thái đều có thể → error.
8. skipped dùng cho tài liệu verbatim hoặc cá nhân.

Các bước trung gian của MRP do tài liệu wiki mô tả.

### 10.2 Trạng thái tổng hợp
- `status`, `progress` và `progress_message` luôn được tính bằng `compute_source_dual_status(source) -> (status, progress, message)`.
- Giá trị tổng hợp: `pending`, `processing`, `awaiting_approval`, `plan_ready`, `ready`, `partial`, `error`.
- Cách tính đã cài đặt trong c2. Tóm tắt:
  - Nhánh A còn pending (dữ liệu cũ): kết quả theo nhánh B.
  - Verbatim, hoặc B là skipped/pending: kết quả theo nhánh A.
  - Cả hai ready: `ready` 100. Cả hai error: `error` 0.
  - B ở cổng: giữ tên cổng, progress 55 hoặc 80, thông điệp kèm tình trạng nhánh A.
  - Một nhánh ready và nhánh kia error: `partial` 100.
  - A ready, B đang chạy: progress = 30 + 0,7 × tiến độ B.
  - B ready, A đang chạy: `ready`.
  - Còn lại là `processing` với trọng số 0,3 × A + 0,7 × B, tối thiểu 5.
- `update_source_dual_status(session, source)` flush, khóa dòng FOR UPDATE, nạp lại rồi tính tổng hợp. Người gọi chịu trách nhiệm commit.
- `set_branch_state(source_id, branch, status=None, progress=None, message=None, error=None, session=None) -> Optional[str]`:
  - Khóa dòng, gán các trường của nhánh. Có error thì gán cả error_message.
  - Tính tổng hợp, commit, trả trạng thái tổng hợp.
  - Không truyền session thì mở phiên riêng.
- `start_wiki_attempt(source) -> str`: tạo wiki_attempt_id mới.
- `wiki_attempt_of(source)`: trả wiki_attempt_id, hoặc attempt_id nếu chưa có, ở dạng chuỗi hoặc None.
- `reset_branches(source, wiki_skipped=False)`: đưa A về pending/0. B về pending/0, hoặc skipped/100 với `Skipped (verbatim source)` khi wiki_skipped.

### 10.3 `ProgressTracker` (`app.utils.progress`)
- `ProgressTracker(source_id)` có phương thức `async update(progress: int, message: str)`.
- Mỗi lần gọi mở phiên riêng qua `async_session_factory` và nạp Source.
  - Nếu wiki_status (null coi là pending) thuộc WIKI_ACTIVE: ghi wiki_progress và wiki_progress_message, tính lại tổng hợp bằng `compute_source_dual_status` rồi gán vào status/progress/progress_message.
  - Nếu không: ghi thẳng progress và progress_message.
- Sau đó commit. Lỗi chỉ được log và không làm hỏng tác vụ.

### 10.4 `count_tokens(text) -> int` (`app.utils.tokens`)
Đếm token bằng tiktoken mã hóa `cl100k_base`. Văn bản rỗng trả 0.

### 10.5 Định dạng báo tiến độ
- Client đọc trạng thái qua GET /api/sources/{id}/progress hoặc qua SourceResponse.
- Các mốc tiến độ là số nguyên 0–100, thông điệp tiếng Anh ngắn như liệt kê ở mục 11.
- Thông điệp lỗi có dạng `Error: {200 ký tự đầu}`, `Wiki error: {200 ký tự đầu}` hoặc `Chunking error: {200 ký tự đầu}`.

---

## 11. Worker (`app.worker`)

### 11.1 Kết nối và idempotency
- **`async get_arq_pool()`**: tạo pool arq một lần (lazy) từ redis_host, redis_port, redis_db và redis_password (rỗng thì None).
- **`async check_task_attempt_validity(session, source_id, attempt_id_str, branch=None) -> bool`**
  1. attempt rỗng hoặc None: True, không truy vấn.
  2. Chuỗi không phải UUID: False.
  3. Truy vấn hai cột attempt_id và wiki_attempt_id bằng `execute(...).one_or_none()`. Không có dòng: True.
  4. branch = `wiki` và wiki_attempt_id khác None: so với wiki_attempt_id. Các trường hợp khác so với attempt_id.
  5. Giá trị hiện tại là None: True. Ngược lại, chỉ True khi bằng nhau.

  Hệ quả:
  - Job wiki còn mang attempt toàn cục trở thành lỗi thời ngay khi đã có wiki attempt.
  - Job nhánh A và job toàn tài liệu vẫn kiểm theo attempt_id.
  - Job wiki của dữ liệu cũ (chưa có wiki_attempt_id) kiểm theo attempt_id.
- Mọi tác vụ đều kiểm validity ngay sau khi nạp tài liệu. Job lỗi thời trả về sớm: không tải tệp, không đổi trạng thái.
- Khóa attempt:
  - `attempt_id` bị thay khi retry `all`;
  - `wiki_attempt_id` bị thay khi bắt đầu nhánh B mới (dispatch, retry wiki);
  - `chunk_attempt_id` bị thay mỗi lần đẩy nhánh A.

### 11.2 Nối tiếp pipeline
- **`async _chain_to_mrp(source_id, attempt_id_str=None) -> Optional[str]`**
  - Đẩy `ingest_map_reduce_task` với đối số (source_id), thêm attempt_id_str chỉ khi có.
  - Thành công: mở phiên mới, gán job_id và progress_message `Extraction queued...`, commit. Lỗi ở bước này chỉ được log.
  - Trả job_id. Đẩy lỗi thì trả None.
- **`async enqueue_post_extraction_pipeline(source_id, has_images, attempt_id_str=None) -> Optional[str]`**
  - Không có ảnh: trả `_chain_to_mrp(...)`. Với pool thật, việc này đẩy `("ingest_map_reduce_task", source_id)` khi không có attempt.
  - Có ảnh: đẩy `caption_images_task` với (source_id[, attempt]) và trả job_id, hoặc None.
- **Re-export** từ source_status để test import `app.worker.compute_source_dual_status`: `compute_source_dual_status`, `reset_branches`, `set_branch_state`, `start_wiki_attempt`, `update_source_dual_status`, `wiki_attempt_of`.

### 11.3 Nhánh A
- **`async commit_and_enqueue_chunk_branch(session, source, attempt_id_str=None) -> Optional[str]`**
  1. Gán chunk_attempt_id mới; chunk_status `queued`, chunk_progress 5, `Queued: chunk & embed raw text`, chunk_error_message null.
  2. `update_source_dual_status`, commit.
  3. Đẩy `ingest_source_chunks_task(id, attempt_id_str hoặc str(source.attempt_id), str(chunk_attempt_id))`.
  4. Trả job_id.
- **`async ingest_source_chunks_task(ctx, source_id, attempt_id_str=None, chunk_attempt_id_str=None)`** chạy trong `trace_context`.
  1. Không thấy tài liệu: `{status: "not_found"}`.
  2. Attempt lỗi thời, hoặc chunk_attempt_id_str khác chunk_attempt_id hiện tại: `{status: "stale"}`.
  3. Không có full_text: nhánh A sang error/0 với `No extracted text to chunk`, error `No full_text`. Trả `{status: "no_text"}`.
  4. Nhánh A sang embedding/20 với `Building chunks with heading hierarchy & embedding...`.
  5. Chạy `index_source_chunks`, ghi timing `source_chunks` với metadata `{chunks: n}`.
  6. Nhánh A sang ready/100: `Indexed {n} raw chunks` khi n > 0, ngược lại `No embedding model: keyword search only`. Trả `{status: "ready", chunks: n}`.
  7. Ngoại lệ:
     - Trong vùng che hủy (shield): nhánh A sang error/0 với `Chunking error: {200 ký tự đầu}`, error là 500 ký tự đầu.
     - `record_task_failure(task_name="ingest_source_chunks_task", ...)`.
     - Ném lại ngoại lệ.
  8. Luôn gọi `flush_langfuse()` khi kết thúc.
- **`async backfill_source_chunks_task(ctx, limit=500, force=False)`**
  - Chọn tài liệu status ready/partial có full_text. Khi không force, chỉ lấy chunk_status pending/error.
  - Sắp theo created_at, giới hạn `limit`.
  - Gọi commit_and_enqueue_chunk_branch cho từng tài liệu. Trả `{candidates, enqueued}`.
- **`async finalize_verbatim_source(session, source, tracker) -> dict`**
  1. tracker 60 `Indexing verbatim document (no wiki)...`.
  2. Nhánh B sang skipped/100 `Skipped (verbatim source)`. Nhánh A sang processing/60 `Indexing verbatim chunks...`.
  3. Chạy `index_source_chunks`, đặt auto_recover_count = 0.
  4. Nhánh A sang ready/100 với `Verbatim: indexed {n} chunks, no wiki`, hoặc `Verbatim: stored, no embedding model (keyword search only)` khi n = 0.
  5. Trả `{status: "ready", verbatim_chunks: n}`.

### 11.4 Điều phối sau trích xuất: `async dispatch_dual_pipeline(session, source, tracker, token_count, n_images=0, attempt_id_str=None) -> dict`
1. attempt = tham số, hoặc str(source.attempt_id).
2. Nhánh B ban đầu:
   - Verbatim: skipped/100 `Skipped (verbatim source)`.
   - Ngược lại: queued/50 `Waiting to compile wiki...` và `start_wiki_attempt(source)`.
3. `wiki_attempt = wiki_attempt_of(source)`.
4. `await commit_and_enqueue_chunk_branch(session, source, attempt)`: nhánh A luôn chạy.
5. `is_legal = await is_legal_source(session, source)` (legal_service).
6. Verbatim hoặc không phải văn bản pháp luật: `store_document_metadata(session, source)` rồi commit. Mọi lỗi ở bước này bị nuốt. Văn bản pháp luật lấy metadata trong nhánh pháp luật.
7. Verbatim: trả `{status: source.status, branch_a: "queued", branch_b: "skipped"}`.
8. Văn bản pháp luật:
   - Nhánh B sang processing/50 `Parsing legal document articles...`.
   - Trả `finalize_legal_source(session, source, tracker)`.
   - Lỗi: trong vùng shield gọi `mark_wiki_error`, rồi ném lại.
9. **Cổng trích xuất:** ngưỡng `auto_approve_extraction_threshold_tokens` > 0 và token_count > ngưỡng:
   - `agg = set_branch_state(id, "wiki", status="awaiting_approval", progress=55, message="Awaiting approval for wiki compilation: {token_count:,} tokens > {ngưỡng:,} threshold", session=session)`. Số có dấu phẩy phân nghìn.
   - Trả `{status: agg, token_count, images: n_images}`.
10. Trường hợp còn lại:
    - `agg = set_branch_state(wiki, status="processing", progress=55, message="Captioning {n} images before extraction..." khi có ảnh, ngược lại "Extraction queued...")`.
    - `job = enqueue_post_extraction_pipeline(id, has_images=n_images > 0, attempt_id_str=wiki_attempt)`. Có job thì gán job_id và commit.
    - Trả `{status: agg, token_count, images: n_images}`.

Tài liệu ở awaiting_approval chỉ đi tiếp qua POST approve-extraction (5.11). Nếu không ai duyệt, cron 11.8 dọn tài liệu sau TTL.

### 11.5 `async ingest_file_task(ctx, source_id, attempt_id_str=None)`

Tạo `tracker = ProgressTracker(sid)` và chạy trong `trace_context("ingest_file_task", ...)`. Mở phiên qua `app.database.async_session_factory()`.

1. `session.get(Source, sid)`. Không có: return.
2. `app.worker.check_task_attempt_validity(session, sid, attempt_id_str)` sai: return, không tải tệp.
3. Không có minio_key: ValueError.
4. file_name = file_name, hoặc đoạn cuối của minio_key.
5. `reset_branches(source, wiki_skipped=preserve_verbatim)`; status `processing`, progress 0, `Starting processing...`; commit.
6. Các bước:

| Tiến độ | Thông điệp | Việc làm | Timing |
|---|---|---|---|
| 5 | `Loading file...` | `storage_service.download_file(minio_key)` | `download` {size_bytes} |
| 10 | `File loaded` | | |
| 15 | `Extracting text (per page)...` | Lấy vision provider bằng `ProviderRegistry(session).get_vision()` (lỗi coi là None), rồi `_extract_text_from_file(data, file_name, vision_provider=, tracker=)` | `parse` {pages_count} |
| | | Không trang nào có nội dung sau khi cắt khoảng trắng: status `error`, error_message `Unable to extract text content`, progress 0, commit, trả `{status: "error", message: "No text content"}` | |
| 25 | `Text extraction complete` | | |
| 30 | `Extracting images...` | `extract_images`. Với mỗi ảnh, thêm một dòng SourceImage (minio_key, page_number, image_index, caption, content_type, size_bytes), flush để có id, gán `img.image_id = str(id)`. Sau đó `_inline_image_markers(pages, images)` | `extract_images` {images_count} |
| 40 | `Analyzed {n} images` | | |
| 45 | `Building document outline...` | outline_json = `build_outline(pages)`; (full_text, page_offsets) = `assemble_full_text(pages)`; extracted_token_count = `count_tokens(full_text)`; commit | `outline` {token_count} |
| 50 | `Outline: {k} top-level sections, ~{t} tokens` | | |

7. Trả `dispatch_dual_pipeline(session, source, tracker, token_count, n_images=len(images), attempt_id_str=attempt_id_str)`.
8. **Xử lý ngoại lệ** (bắt cả BaseException):
   1. Dựng error_msg: kiểu = tên lớp ngoại lệ, thông điệp = chuỗi đã cắt khoảng trắng, hoặc tên kiểu nếu rỗng. error_msg = `{kiểu}: {thông điệp}`, hoặc chỉ `{kiểu}` khi hai giá trị trùng nhau.
   2. Trong vùng shield, mở phiên mới qua `app.database.async_session_factory` và nạp lại Source:
      - chunk_status khác None/pending (đã sang giai đoạn hai nhánh): `mark_wiki_error(sid, error_msg)`;
      - ngược lại: status `error`, error_message = error_msg, progress 0, progress_message `Error: {200 ký tự đầu}`, commit.
   3. Sau đó gọi `app.models.task_failure.record_task_failure(session=phiên lỗi, task_name="ingest_file_task", error=ngoại lệ gốc, source_id=sid (UUID), attempt_id=attempt_id_str, payload={"file_name": file_name} hoặc None)`. Gọi bằng tham số từ khóa, đúng một lần.
   4. **Bắt buộc:** lỗi khi cập nhật trạng thái (kể cả với session giả) không được làm mất bước ghi dead-letter. Bước cập nhật trạng thái phải được bọc riêng, rồi luôn gọi record_task_failure.
   5. Lỗi của toàn khối xử lý bị nuốt. Cuối cùng ném lại ngoại lệ gốc. Test kiểm `RuntimeError("MinIO connection failed")` được ném ra.
9. Luôn gọi `flush_langfuse()` khi kết thúc.

Hàm phụ **`async mark_wiki_error(source_id, msg)`**: `set_branch_state(source_id, "wiki", status="error", progress=0, message="Wiki error: {200 ký tự đầu}", error=msg)`.

### 11.6 `async ingest_url_task(ctx, source_id, attempt_id_str=None)`
- Cấu trúc như 11.5, gồm reset_branches, processing và `Starting processing...`.
- tracker 15 `Fetching content from URL...`.
  - Không có url: ValueError `Source has no URL`.
  - Gọi `_extract_text_from_url`, ghi timing `fetch_url`.
  - Rỗng: status error, `Unable to fetch content from URL`.
- tracker 40 `Building outline...`, dựng outline, full_text, page_offsets và token như trên, ghi timing `outline`.
- Gọi dispatch với n_images 0.
- Ngoại lệ: thông điệp lỗi là 500 ký tự đầu của chuỗi lỗi; record_task_failure với task_name `ingest_url_task`; ném lại.

### 11.7 Nhánh B
- **`async caption_images_task(ctx, source_id, attempt_id_str=None)`** chạy trong trace_context.
  1. Nạp tài liệu. Kiểm validity với branch `wiki` (attempt None thì không truy vấn).
  2. `vision = await ProviderRegistry(session).get_vision()`, tra `ProviderRegistry` qua `app.ai.registry` lúc gọi.
     - None: `await app.worker._chain_to_mrp(source_id)` khi không có attempt, hoặc `_chain_to_mrp(source_id, attempt)` khi có, rồi return.
     - Test kiểm lời gọi với đúng một đối số.
  3. Nạp các dòng SourceImage theo image_index (`execute(...).scalars().all()`). Rỗng: `_chain_to_mrp` như trên, rồi return.
  4. Chú thích song song, tối đa 4 ảnh cùng lúc, timeout 120 giây mỗi ảnh. Với mỗi ảnh:
     - tải bytes từ MinIO;
     - gọi `vision.analyze_image(bytes, content_type, prompt=...)`;
     - lưu caption trong phiên riêng.

     Lỗi từng ảnh chỉ được log.
  5. Prompt chú thích (chỉ mô tả mục đích): yêu cầu mô tả ngắn 1–3 câu về nội dung ảnh, nêu sơ đồ, biểu đồ, nhãn, số liệu, các bước nếu có, không mở đầu sáo rỗng. Đầu ra là văn bản thuần.
  6. Viết lại full_text: mọi marker `![...](image://{id})` của ảnh đã có caption được thay alt bằng caption đã bỏ xuống dòng. Thao tác này idempotent. Commit khi văn bản thay đổi.
  7. Tạo chunk `image_caption` bằng `create_image_chunk` (text dạng `[image_caption | Trang {p}]: {caption}`) và gọi `index_image_chunks`. Lỗi chỉ được log.
  8. Gọi `_chain_to_mrp`.
  9. Ngoại lệ không xử lý được: vẫn gọi `_chain_to_mrp` rồi ném lại, để tài liệu không kẹt ở processing.
  10. Luôn gọi flush_langfuse.
- **`async ingest_map_reduce_task(ctx, source_id, attempt_id_str=None)`**
  1. Kiểm validity với branch `wiki`. Không có full_text: ValueError.
  2. Văn bản pháp luật: `finalize_legal_source`.
  3. Verbatim: `finalize_verbatim_source`. Lỗi thì nhánh A sang error với `Verbatim indexing failed`.
  4. Ngược lại:
     - Nhánh B sang mapping/56 `Extracting knowledge from document...`.
     - Nạp knowledge type (slug, name, description).
     - Gọi `run_mrp_pipeline(session=, source=, attempt_id_str=, full_text=, tracker=, registry=, kt_slug=, kt_name=, kt_desc=)`.
     - Ghi timing `map_reduce` {status}.
  5. Xử lý kết quả:
     - `plan_ready`: auto_recover_count = 0, nhánh B sang plan_ready/80 `Compilation plan ready — awaiting review`.
     - `plan_auto_approved`: pipeline đã tự đẩy refine (khi `mrp_auto_approve_plan`).
  6. Lỗi: mark_wiki_error, `record_task_failure("ingest_map_reduce_task")`, ném lại.
- **`async ingest_refine_task(ctx, source_id, attempt_id_str=None)`**
  1. Kiểm validity với branch `wiki`.
  2. Nhánh B sang refining/78 `Writing wiki pages...`.
  3. Gọi `run_refine_pipeline`, ghi timing `refine` {pages_created, pages_updated}.
  4. Lỗi: mark_wiki_error, `record_task_failure("ingest_refine_task")`, ném lại.
- **`async regenerate_plan_task(ctx, source_id, user_note)`**
  1. Nạp tài liệu kèm knowledge type, và kế hoạch.
  2. Thử `reconcile_with_kb` (cần embedding provider cùng entity/concept của kế hoạch cũ). Lỗi thì bỏ qua.
  3. Gọi `run_planning_call(llm, source, strategy=pipeline_strategy hoặc "standard", canonical_entities, canonical_concepts, reconciliation, kt_name, kt_desc, user_note)`.
  4. Ghi plan_json mới nhưng giữ lại các khóa nội bộ `_claims`, `_entities`, `_concepts`.
  5. status `pending_review`; reviewed_by, review_note, reviewed_at về null; commit.
  6. Thất bại: nếu kế hoạch vẫn đang regenerating thì đưa về pending_review với review_note `Regeneration failed: {200 ký tự đầu}`.
- **`async reassign_source_scope_task(ctx, source_id, old_scopes)`**
  1. tracker 0 `Detaching from old wiki scopes...`.
  2. `wiki_service.detach_source_from_wiki`. Sau đó `regenerate_index(scope_type, scope_id)` cho từng phạm vi cũ; lỗi chỉ được log.
  3. Nhánh B sang queued/5 `Re-queued after scope change...`.
  4. Đẩy `ingest_map_reduce_task(id)` không kèm attempt, gán job_id.
- **`async detach_source_wiki_task(ctx, source_id, old_scopes)`**: gỡ khỏi wiki, dựng lại index các phạm vi cũ, commit. Không biên soạn lại.
- Các tác vụ khác có đăng ký nhưng thuộc tài liệu khác:
  - `relink_legal_relations_task(ctx, source_id=None)`;
  - `backfill_doc_metadata_task(ctx, only_missing=True, use_llm=True, limit=1000)`;
  - `reembed_all_pages_task`;
  - `ai_pre_review_draft_task`.

### 11.8 Cron
- **`sweep_stuck_processing_cron`**
  - Đối tượng: tài liệu status `processing` có updated_at cũ hơn max(2 × worker_job_timeout, 1800) giây, hoặc updated_at null.
  - Với mỗi tài liệu:
    1. auto_recover_count tăng 1. Ký hiệu {min} là ngưỡng tính bằng phút, {n} là số lần mới, {cap} là trần.
    2. Thông điệp:
       - n ≥ cap: `Worker died with no progress for >{min} min on {n} consecutive attempts (cap={cap}). Retry is blocked — check LLM provider config and source file, then ask an admin to reset auto_recover_count.`
       - Ngược lại: `Worker died with no progress for >{min} min. Press Retry to try again ({n}/{cap} auto-recoveries used).`
    3. Cập nhật trạng thái:
       - Nhánh A đang ở CHUNK_ACTIVE: nhánh A sang error với thông điệp đó.
       - Nhánh B đang ở WIKI_ACTIVE: nhánh B sang error với thông điệp đó.
       - Có nhánh nào bị đổi thì tính lại tổng hợp. Không thì status `error`, error_message và progress_message là thông điệp.
    4. `record_task_failure(task_name=job_id hoặc "pipeline_stuck_sweep", error=TimeoutError(thông điệp), payload={auto_recover_count, cap})`.
  - Commit.
- **`cleanup_orphan_awaiting_approval_cron`**: tài liệu status `awaiting_approval` có updated_at cũ hơn max(1, extraction_approval_ttl_hours) giờ. Xóa đối tượng minio_key (lỗi bỏ qua) rồi xóa dòng.
- Các cron khác không thuộc phạm vi tài liệu này: `daily_stats_rollup_cron`, `sweep_stuck_ai_review_cron`.

### 11.9 `WorkerSettings`
- `functions`:
  - ingest_file_task, ingest_url_task;
  - ingest_source_chunks_task, backfill_source_chunks_task;
  - caption_images_task (timeout riêng 3600 giây);
  - ingest_map_reduce_task, ingest_refine_task, regenerate_plan_task;
  - reembed_all_pages_task, ai_pre_review_draft_task;
  - reassign_source_scope_task, detach_source_wiki_task;
  - relink_legal_relations_task, backfill_doc_metadata_task;
  - generate_questions_task.
- `redis_settings` dựng từ cấu hình Redis.
- `max_jobs = worker_max_jobs`, `job_timeout = worker_job_timeout`, `max_tries = 3`, `retry_delay = 10`, `health_check_interval = 30`.
- `cron_jobs`:

| Cron | Lịch |
|---|---|
| daily_stats_rollup | 02:00 |
| sweep_stuck_ai_review | phút 0, 10, 20, 30, 40, 50 |
| sweep_stuck_processing | phút 5, 15, 25, 35, 45, 55 |
| cleanup_orphan_awaiting_approval | phút 15 mỗi giờ |

- Có `SkillWorkerSettings` riêng cho hàng đợi `skills_queue`, thuộc tài liệu kỹ năng.

### 11.10 Thời gian các giai đoạn
- Mỗi giai đoạn đo bằng đồng hồ hiệu năng và tính ra mili giây (số nguyên).
- Kết quả ghi bằng `record_stage_timing(session, source_id, stage_name, duration_ms, metadata)` trên phiên đang dùng.
- Tên giai đoạn: `download`, `parse`, `extract_images`, `outline`, `fetch_url`, `source_chunks`, `map_reduce`, `refine`.

---

## 12. Văn bản pháp luật, verbatim và tài liệu cá nhân
- **Verbatim** (`preserve_verbatim = true`): bỏ nhánh B (skipped/100) và chỉ lập chỉ mục chunk gốc theo trang. Mục đích là giữ nguyên văn để tra cứu điều khoản và trích dẫn số trang.
- Trang của chunk lấy từ page_offsets (mục 8). Mỗi chunk mang page_number để trích dẫn.
- Tài liệu cá nhân luôn là verbatim và không thuộc phòng ban nào.
- Văn bản pháp luật nhận biết bằng `is_legal_source` (theo knowledge type Luật/Legal). Khi không verbatim, nhánh B đi đường `finalize_legal_source`: tách theo Điều thành trang wiki và tự lấy metadata (tài liệu pháp luật). Nhánh A vẫn chạy song song.
- Metadata văn bản (`metadata.doc`) được ghi bằng `store_document_metadata`. Người dùng sửa qua PATCH `doc_meta`, xử lý bởi `apply_manual_doc_meta`: chỉ nhận các khóa trong `EDITABLE_META_KEYS`, ngày chuyển sang ISO, sai định dạng thì ValueError.
- Trường `validity` trong `doc_meta` tính bằng `compute_validity`.

---

## 13. Sinh câu hỏi tìm kiếm (`app.services.question_generator`)

Module import ở cấp module `ProviderRegistry`, `get_spec`, `upsert_chunk_embedding` và `chunk_content_hash`, để test patch được qua tên module này.

- **`QuestionGenerator(llm_provider=None)`** có phương thức **`async generate_questions_for_chunk(text, title=None, max_questions=3) -> list[str]`**:
  1. text sau khi cắt khoảng trắng ngắn hơn 30 ký tự, hoặc không có provider: trả `[]` và không gọi LLM.
  2. Nội dung gửi đi = title (nếu có) + xuống dòng + text, cắt còn 3000 ký tự.
  3. Prompt tiếng Việt (chỉ mô tả mục đích): sinh tối đa N câu hỏi tự nhiên, đời thường, mà người dân hoặc cán bộ hay tìm. Tập trung vào mức phạt, hành vi vi phạm, điều kiện, thẩm quyền, thủ tục. Mỗi dòng một câu, không đánh số, không gạch đầu dòng, không lời dẫn.
  4. Gọi `provider.generate_text(prompt)`. Provider không có phương thức đó thì gọi `complete(prompt)`.
  5. Tách dòng, bỏ ở đầu dòng các chữ số, dấu chấm, gạch, sao, bullet và khoảng trắng. Giữ dòng dài ít nhất 8 ký tự, dừng khi đủ max_questions.
  6. Mọi ngoại lệ trả `[]`.
- **`build_question_chunks(source_id, parent_chunk_index, questions, page_number=1, context_preview="") -> list[dict]`**
  - Mỗi câu hỏi cho một dict với các khóa: `chunk_type="generated_question"`, `question`, `text`, `source_id`, `parent_chunk_index`, `page_number`.
  - text = `[câu_hỏi_tìm_kiếm | Trang {p}]: {câu hỏi}`. Khi có preview thì nối thêm dòng trống và `Nội dung liên quan: {preview}`, với preview là 300 ký tự đầu của context đã thay xuống dòng bằng khoảng trắng.
- **`async index_question_chunks(session, source_id, chunks, spec_id=None) -> int`**
  - Giống `index_image_chunks` (7.4), nhưng chunk_index = 70000 + i và page_number = page_number của chunk, hoặc 1.
- **`async generate_questions_task(ctx, source_id, attempt_id_str=None, max_provisions=15) -> dict`** (trong app.worker)
  - Import lười `app.database.async_session_factory`, các ký hiệu của question_generator, và `app.ai.registry.ProviderRegistry`.
  1. Kiểm validity. Lỗi thời: `{status: "stale", source_id}`. Không thấy: `{status: "not_found", source_id}`.
  2. `llm = await ProviderRegistry(session).get_llm()`; `generator = QuestionGenerator(llm_provider=llm)`.
  3. Nạp LegalUnit của tài liệu (`execute(...).scalars().all()`), tối đa max_provisions.
     - Có LegalUnit: với mỗi đơn vị, tiêu đề = `{loại đơn vị viết hoa chữ đầu} {số}: {tên}`. Sinh tối đa 3 câu hỏi, rồi `build_question_chunks(source.id, idx, questions, page_number=1, context_preview=nội dung)`.
     - Không có LegalUnit: dùng `build_verbatim_chunks(full_text, page_offsets or [])`, lấy max_provisions chunk đầu, parent = chunk.index, page = chunk.page_number, tiêu đề là title tài liệu.
  4. Có chunk thì gọi `index_question_chunks(session, source.id, chunks)`.
  5. Trả `{status: "success", source_id, questions_generated, chunks_indexed}`.

---

## 14. Hợp đồng với test (tóm tắt các ký hiệu được import)

| Module | Ký hiệu | Chữ ký và điểm test kiểm |
|---|---|---|
| app.routers.sources | `upload_source` | Tham số từ khóa như 5.7. Có 409 khi trùng hash (thông báo chứa `đã tồn tại trên hệ thống`). Stream lên MinIO đúng bốn tham số từ khóa, khóa kết thúc bằng `/original/{tên}`, length = kích thước. `Repository(db).create` nhận Source có file_size đúng. `enqueue_job` được await một lần. Patch qua `app.routers.sources.Repository`, `.log_audit`, `.get_arq_pool`, `._to_response` |
| app.routers.sources | `retry_source` | 5.10. plan_ready: chỉ đẩy `("ingest_map_reduce_task", id, wiki_attempt mới)`, attempt_id giữ nguyên, wiki_status `queued`. partial và chunk lỗi: chỉ gọi commit_and_enqueue_chunk_branch. partial, wiki lỗi, phase refine: đẩy `ingest_refine_task`. Không có text: `ingest_file_task` với status `pending`. branch all: attempt mới, đẩy `(task, id, attempt mới)` |
| app.routers.sources | `_checked_label`, `source_read_filter`, `_authenticate_request_user`, `_get_user_permissions`, `Source` | Xem tài liệu 02 |
| app.routers.admin_failures | `list_task_failures`, `retry_task_failure`, `get_source_stage_timings` | 5.17 |
| app.models.task_failure | `TaskFailure`, `SourceStageTiming`, `record_task_failure`, `record_stage_timing` | 3.7–3.9 |
| app.services.kb_service | `_extract_text_from_file`, `_inline_image_markers`, `_load_doc_processing_config`, `_guess_content_type` | 6, 7.3. Với doc: `convert_to_pdf(data, "doc")` và kết quả của PDFParser được trả về nguyên vẹn. Cấu hình không nạp được thì dùng `{}` |
| app.services.image_service | `ImageInfo`, `docx_image_blobs`, `extract_images`, `extract_images_from_pptx`, `extract_images_from_pdf`, `extract_images_from_docx`, `create_image_chunk`, `index_image_chunks`, `MIN_IMAGE_BYTES` | 7 |
| app.services.verbatim_service | `SourceChunk`, `VerbatimChunk`, `build_source_chunks`, `build_verbatim_chunks`, `index_source_chunks`, `index_verbatim_source`, `MIN_CHUNK_CHARS` | 9 |
| app.services.question_generator | `QuestionGenerator`, `build_question_chunks`, `index_question_chunks` | 13 |
| app.worker | `check_task_attempt_validity`, `ingest_file_task`, `caption_images_task`, `enqueue_post_extraction_pipeline`, `generate_questions_task`, `compute_source_dual_status`, `get_arq_pool`, `_chain_to_mrp`, `commit_and_enqueue_chunk_branch` | 11, 13 |
| app.services.source_status | `compute_source_dual_status`, `reset_branches`, `set_branch_state`, `start_wiki_attempt` | Loại C, mục 10.2 |

Các tình huống mock cần chịu được:
- **ingest_file_task, khi download lỗi:**
  - `async_session_factory` là MagicMock trả về AsyncMock session; `session.get` trả MagicMock Source.
  - `check_task_attempt_validity` bị patch tại `app.worker`.
  - Tác vụ phải ném lại RuntimeError và await `record_task_failure` đúng một lần, với kwargs `task_name="ingest_file_task"`, `source_id=sid` (UUID) và `error` là RuntimeError.
  - `ProgressTracker` và `set_branch_state` chạy trên mock có thể lỗi; các lỗi đó phải được nuốt.
- **ingest_file_task, khi attempt lỗi thời:** `trace_context` bị patch. Hàm trả về mà không gọi download_file.
- **caption_images_task, không có vision hoặc không có dòng ảnh:** `_chain_to_mrp` được gọi đúng một lần với một đối số `source_id`.
- **generate_questions_task:** `ProviderRegistry` bị patch tại `app.ai.registry`; QuestionGenerator và index_question_chunks bị patch tại module question_generator; execute trả danh sách LegalUnit rỗng. Hàm rơi về chunk verbatim và trả status success với ít nhất 1 câu hỏi và 1 chunk.
