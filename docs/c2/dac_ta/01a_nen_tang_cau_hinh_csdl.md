# 01a — Nền tảng backend: cấu hình, CSDL, migration, khởi động, triển khai

Tài liệu nền tảng, đọc trước mọi tài liệu khác. Phần tiếp theo là `01b_nen_tang_worker_ai_dich_vu.md`, gồm worker, AI, dịch vụ dùng chung và bảng "Giao diện bắt buộc".

Nguyên tắc chung:

- Các tài liệu 02–06 đã mô tả chi tiết từng miền. Tài liệu 01 chỉ nêu phần nền mà chúng dùng chung, kèm chỉ mục trỏ sang chúng.
- Khi hai tài liệu mô tả cùng một điều, tài liệu miền (02–06) là chuẩn cho chi tiết nghiệp vụ, còn tài liệu 01 là chuẩn cho hạ tầng: settings, engine, migration, lifespan, Docker.
- Trong tài liệu này, "loại C" là file đã có sẵn trong c2 và không được viết lại. Phải cung cấp đúng các ký hiệu mà file đó import.

---

## 1. Bố cục gói Python

| Đường dẫn | Vai trò | Ghi chú |
|---|---|---|
| `app/config.py` | Lớp `Settings` và singleton `settings` | Phải xây, xem §2 |
| `app/database/__init__.py` | `engine`, `async_session_factory`, `get_db` | Phải xây, xem §3 |
| `app/database/models.py` | `Base` cùng toàn bộ mô hình ORM | Phải xây, xem §4 và các tài liệu miền |
| `app/database/oauth_models.py` | `OAuthClient`, `OAuthAuthCode` | Xem 02 §3 |
| `app/database/repository.py` | `Repository` | Phải xây, xem §3.3 |
| `app/models/task_failure.py` | `TaskFailure`, `SourceStageTiming` và hai hàm ghi | Xem 03 §3.7–3.9 |
| `app/models/concept_relation.py` | Bảng `concept_relations` | Loại C |
| `app/main.py` | Ứng dụng FastAPI `app` | Phải xây, xem §6 |
| `app/worker.py` | Task arq, `WorkerSettings`, `SkillWorkerSettings` | Xem 01b §1 và 03 §11 |
| `app/scripts/seed_knowledge_types.py`, `app/scripts/seed_skills.py` | Seed lúc khởi động | Phải xây, xem §7 |
| `alembic.ini`, `alembic/env.py`, `alembic/versions/*` | Migration | Phải xây, xem §5 |
| `Dockerfile`, `entrypoint.sh`, `docker-compose.yml` | Triển khai | Phải xây, xem §8 |
| `skills/` | Kỹ năng dựng sẵn `cahy-kn1` … `cahy-kn7` | Đã có trong c2 |

Mọi package (`app`, `app/database`, `app/models`, `app/routers`, `app/services`, `app/ai`, `app/ai/providers`, `app/utils`, `app/scripts`, `app/mcp`) đều cần file `__init__.py`. Các file này để rỗng, trừ khi tài liệu khác yêu cầu khác.

---

## 2. `app/config.py` — `Settings`

### 2.1. Cơ chế

- Lớp `Settings` kế thừa `BaseSettings` của pydantic-settings, đọc từ file `.env` (mã hóa utf-8). Khóa thừa trong môi trường bị bỏ qua (extra = ignore). Tên biến môi trường là tên trường viết hoa, không phân biệt hoa thường.
- Có singleton cấp module `settings = Settings()`. Mọi module dùng `from app.config import settings`.
- Test gán trực tiếp thuộc tính trên singleton, ví dụ `settings.audit_hmac_key` và `settings.sso_role_global_map`. Vì vậy:
  - mọi thuộc tính dẫn xuất phải là property tính lại mỗi lần đọc, không được cache;
  - module khác phải đọc `settings.x` lúc gọi, không chép giá trị ra lúc import.
- Import `app.config` không được kết nối mạng hay CSDL.

### 2.2. Danh sách trường

| Trường | Kiểu | Mặc định | Ý nghĩa |
|---|---|---|---|
| database_url | str | `postgresql+asyncpg://arkon:arkon_secret@localhost:5432/arkon` | Chuỗi kết nối async |
| secret_key | str | `change-me-to-a-random-secret-string` | Ký JWT HS256 và sinh khóa Fernet cho cấu hình nhạy cảm. Khi còn giá trị mặc định, lúc khởi động ghi cảnh báo |
| default_admin_email | str | `admin@arkon.local` | Email admin seed |
| default_admin_password | str | rỗng | Rỗng thì không seed admin |
| audit_hmac_key | str | rỗng | Khóa HMAC cho chuỗi audit. Rỗng thì dẫn xuất từ secret_key (06 §10). Đổi khóa làm chuỗi cũ không kiểm chứng được |
| mcp_token_pepper | str | `change-me-to-a-random-pepper` | Pepper băm token MCP (02) |
| minio_endpoint | str | `localhost:9000` | |
| minio_public_endpoint | str | rỗng | Host dùng khi ký URL công khai (03 §4) |
| minio_access_key / minio_secret_key | str | `minioadmin` / `minioadmin123` | |
| minio_bucket | str | `arkon-files` | |
| minio_secure | bool | False | |
| minio_presign_expiry_hours | int | 24 | |
| cors_origins | str | `*` | Danh sách cách nhau bằng dấu phẩy |
| portal_base_url | str | rỗng | Gốc URL công khai, dùng tạo link tuyệt đối trong kết quả MCP. Rỗng thì dùng đường dẫn tương đối |
| sso_enabled | bool | False | Xem 02 §2 |
| sso_issuer | str | rỗng | Issuer công khai |
| sso_internal_issuer | str | rỗng | Issuer trong mạng Docker. Rỗng thì dùng sso_issuer |
| sso_client_id | str | `cahy-wiki` | |
| sso_client_secret | str | rỗng | |
| sso_scopes | str | `openid email profile` | |
| sso_provider_name | str | `Công an tỉnh (SSO)` | |
| sso_auto_redirect | bool | False | |
| sso_allow_password_login | bool | True | |
| sso_admin_roles | str | `admin` | Realm role được coi là admin, cách nhau bằng dấu phẩy |
| sso_role_global_map | str | `qt-dl:knowledge_manager,qt-nd:viewer,qt-ai:viewer,qt-ht:viewer` | Ánh xạ realm role sang global_role, dạng JSON hoặc `role:global,...` |
| sso_default_global_role | str | `viewer` | |
| sso_sync_roles / sso_sync_departments | bool | True / True | |
| sso_group_department_map | str | rỗng | JSON ánh xạ group sang tên phòng ban |
| sso_trust_email | bool | False | |
| chatbot_url | str | rỗng | URL Trợ lý ảo. Có giá trị (cùng chatbot_wiki_sso_secret) thì đăng nhập qua vé chatbot |
| chatbot_wiki_sso_secret | str | rỗng | Secret HS256 dùng chung với chatbot, tối thiểu 32 ký tự |
| sso_mcp_clients | str | `cahy-chatbot` | Danh sách azp được gọi MCP bằng access token người dùng |
| mcp_trust_forwarded_identity | bool | False | Xem 02 |
| redis_host / redis_port / redis_password / redis_db | str/int/str/int | `localhost` / 6379 / rỗng / 0 | |
| worker_max_jobs | int | 3 | |
| worker_job_timeout | int | 7200 | Giây |
| mrp_auto_approve_plan | bool | True | Xem 05a |
| mrp_multipass_writer_enabled | bool | True | Xem 05a |
| max_upload_size_bytes | int | 52428800 (50 MiB) | |
| allowed_upload_extensions | str | `pdf,docx,xlsx,pptx,txt,md,csv` | |
| auto_approve_extraction_threshold_tokens | int | 0 | Xem 03 |
| extraction_approval_ttl_hours | int | 24 | |
| max_auto_recover_attempts | int | 3 | |
| langfuse_public_key / langfuse_secret_key | str | rỗng | |
| langfuse_host | str | `https://cloud.langfuse.com` | |
| langfuse_base_url | str | rỗng | Bí danh, ưu tiên hơn langfuse_host |
| langfuse_enabled | bool | True | |
| milvus_host | str | `milvus` | |
| milvus_port | int | 19530 | |
| milvus_enabled | bool | False | |
| milvus_user / milvus_password | str | rỗng | |
| milvus_database | str | `default` | |
| ocr_base_url / ocr_api_key | str | rỗng | |
| ocr_model | str | `ggml-org/GLM-OCR-GGUF:f16` | |
| reranker_enabled | bool | True | |
| reranker_provider | str | `http` | `http` hoặc `local` |
| reranker_base_url / reranker_api_key | str | rỗng | |
| reranker_model | str | `BAAI/bge-reranker-v2-m3` | |
| reranker_top_n | int | 10 | |
| chunk_target_tokens | int | 1500 | Dùng bởi chunk_budget (loại C) |
| chunk_overlap_tokens | int | 150 | |

### 2.3. Thuộc tính dẫn xuất

| Thuộc tính | Hành vi |
|---|---|
| `effective_ocr_base_url` | Cắt khoảng trắng ở ocr_base_url. Rỗng thì trả rỗng. Bỏ "/" ở cuối. Gộp các "//" liên tiếp trong phần đường dẫn sau scheme thành "/". Nếu chưa kết thúc bằng "/v1" thì nối thêm "/v1" |
| `effective_langfuse_host` | langfuse_base_url nếu khác rỗng, nếu không thì langfuse_host, cuối cùng là `https://cloud.langfuse.com` |
| `sso_admin_role_set` | Tập role từ sso_admin_roles: tách theo dấu phẩy, cắt khoảng trắng, bỏ phần tử rỗng |
| `sso_role_map` | Gọi `parse_role_map(sso_role_global_map)` (import lười từ `app.services.sso_roles`, loại C) |
| `sso_mcp_client_set` | Tập client từ sso_mcp_clients, tách giống trên |
| `cors_origin_list` | cors_origins bằng "*" thì trả ["*"]. Ngược lại tách theo dấu phẩy, cắt khoảng trắng, bỏ phần tử rỗng |

Các khóa cấu hình động lưu trong bảng `app_config` (không phải Settings) được mô tả ở 01b §4 và ở từng tài liệu miền.

---

## 3. `app/database`

### 3.1. `app/database/__init__.py`

- `engine`: async engine tạo từ `settings.database_url`, với pool_size 20, max_overflow 10, pool_pre_ping bật, echo tắt. Tạo engine không mở kết nối nên import module không cần CSDL đang chạy. Test và `test_admin_settings_preview_api` import `app.main` mà không có CSDL.
- `async_session_factory`: sessionmaker async, lớp phiên AsyncSession, `expire_on_commit=False`. Dùng được như async context manager. Test patch `app.database.async_session_factory` ở 10 chỗ, nên mọi nơi dùng phải import lười bên trong hàm (`from app.database import async_session_factory` lúc chạy), trừ khi tài liệu miền nói khác.
- `get_db()`: dependency FastAPI dạng async generator. Mở một phiên rồi yield. Khi handler xong mà không lỗi thì commit. Có ngoại lệ thì rollback rồi ném lại. Luôn đóng phiên.

### 3.2. Phụ thuộc driver

Cần có `asyncpg`, `pgvector` (kiểu Vector và HALFVEC cho SQLAlchemy) và `sqlalchemy[asyncio]`. Venv c2 hiện chưa có asyncpg và pgvector; phải thêm vào `pyproject.toml` (xem §8.5).

### 3.3. `app/database/repository.py` — `Repository(session)`

Router sources, notes và admin_settings dùng lớp này. Test patch `app.routers.sources.Repository`, nên router phải import tên `Repository` ở cấp module.

| Phương thức (async) | Hành vi |
|---|---|
| `get_by_id(model, id)` | Bản ghi theo khóa chính, không có thì None |
| `get_all(model, *, order_by=None, limit=None, offset=None)` | Danh sách, áp dụng order_by, limit, offset nếu có |
| `create(obj)` | add, flush, refresh, rồi trả obj |
| `update_fields(model, id, **fields)` | UPDATE … RETURNING theo id. Có dòng thì flush rồi trả bản ghi, không có thì None |
| `delete_by_id(model, id) -> bool` | True nếu xóa được ít nhất một dòng |
| `count(model) -> int` | Đếm số dòng |

Repository không commit; `get_db` hoặc người gọi commit.

---

## 4. Lược đồ dữ liệu — chỉ mục

`Base` là `DeclarativeBase` trong `app/database/models.py`. Mọi bảng dùng khóa chính UUID (sinh phía ứng dụng bằng uuid4), trừ khi ghi khác. Thời gian là `timestamp with time zone`, mặc định now. updated_at tự cập nhật khi sửa.

### 4.1. Enum dùng chung (trong `app.database.models`)

| Enum | Giá trị |
|---|---|
| `ScopeType` | global, department, personal |
| `SkillContributionStatus` | draft, pending, needs_revision, withdrawn, approved, rejected |
| `WIKI_DRAFT_STATUSES` (tuple) | pending, needs_revision, withdrawn, approved, rejected |
| `LegalUnitType` | part, chapter, section, article, clause, point |
| `LegalRelationType` | sua_doi, bo_sung, thay_the, bai_bo, huong_dan, can_cu, dan_chieu |

Enum có giá trị là chuỗi (lớp con của str), trừ khi tài liệu miền nói khác.

### 4.2. Bảng và nơi đặc tả chi tiết

| Bảng | Mô hình | Đặc tả cột |
|---|---|---|
| employees | Employee | 02 §3.1 |
| departments | Department | 02 §3.2 |
| employee_departments | EmployeeDepartment | 02 §3.3 |
| source_departments | SourceDepartment | 02 §3.4, 03 §3.2 |
| oauth_clients, oauth_auth_codes | OAuthClient, OAuthAuthCode | 02 §3 |
| app_config | AppConfig | 02 §3.7 (key String(100) PK, value Text, updated_at not null) |
| sources | Source | 03 §3.1 |
| source_images | SourceImage | 03 §3.3 |
| source_compilation_plans | SourceCompilationPlan | 03 §3.4, 05a |
| knowledge_types | KnowledgeType | 03 §3.5 |
| notes | Note | 03 §3.6 |
| task_failures, source_stage_timings | TaskFailure, SourceStageTiming | 03 §3.7–3.8 |
| wiki_pages | WikiPage | 05a §2.2 |
| wiki_links | WikiLink | 05a §2.3 |
| wiki_page_revisions, wiki_page_drafts, wiki_draft_rounds, wiki_branches, source_chunk_extracts | | 05a §2 |
| legal_units, legal_relations | LegalUnit, LegalRelation | 05a, 05b, 04 §3.7 |
| concept_relations | (loại C) | 05a |
| wiki_page_embeddings_<d>, source_chunk_embeddings_<d>, wiki_page_chunk_embeddings_<d> (d ∈ 768, 1024, 1536, 2560, 3072) | | 04 §3.2–3.4 |
| embedding_jobs | EmbeddingJob | 04 §3.6 |
| skills, skill_versions, skill_departments, skill_contributions | Skill, … | 06 |
| prompt_templates | PromptTemplate | 06 |
| notifications | Notification | 06 |
| mcp_query_log | MCPQueryLog | 06 |
| stats_daily_rollup | StatsDailyRollup | 06 |
| audit_log, audit_chain_head | AuditLog, AuditChainHead | 06 §10.3 |

Bổ sung một số điểm mà tài liệu miền có thể chưa nêu:

- **Source:** khi gán `progress_message`, `chunk_progress_message` hoặc `wiki_progress_message` dài quá 500 ký tự, validator của mô hình giữ 499 ký tự đầu rồi nối ký tự "…". Kết quả đúng 500 ký tự.
- **WikiPage:**
  - Có thuộc tính lai `page_type`, không phải cột: slug `_index` cho index, `_log` cho log, `_hot` cho hot, slug bắt đầu bằng `source/` cho source, còn lại là concept. Thuộc tính phải dùng được cả ở mức Python lẫn trong biểu thức truy vấn (hybrid property dạng CASE).
  - Có index `ix_wiki_pages_status`.
- **Bảng embedding:** cột `embedding` cho **phép NULL**. Vector thật nằm ở Milvus; PostgreSQL chỉ giữ metadata, hash và text. Chiều 3072 dùng kiểu HALFVEC, các chiều khác dùng VECTOR.
- **Hàm tra mô hình theo chiều:** `get_embedding_model_for_dim(d)`, `get_source_chunk_embedding_model_for_dim(d)` và `get_wiki_page_chunk_embedding_model_for_dim(d)`. Chiều lạ thì ném ValueError với thông báo "Unsupported embedding dimension: <d>".
- **Skill.status:** dùng kiểu ENUM PostgreSQL tên `skill_status` với các giá trị active, processing, deleting, deprecated, archived. Mặc định phía server là active.
- **OAuthClient.generate_client_id():** trả "client_" nối với 16 byte ngẫu nhiên mã hóa urlsafe.

### 4.3. Đối tượng chỉ có trong migration (ORM không khai báo)

Các đối tượng sau phải được tạo trong migration baseline (§5.3), vì `create_all` từ ORM không sinh ra chúng.

**Extension và hàm**

| Đối tượng | Mô tả |
|---|---|
| extension `vector` | pgvector |
| extension `unaccent` | |
| hàm `f_unaccent(text) -> text` | Hàm SQL IMMUTABLE, PARALLEL SAFE, bọc `public.unaccent` với từ điển `public.unaccent`. Cần IMMUTABLE để dùng được trong index biểu thức. Tìm kiếm toàn văn (04 §3.5) gọi hàm này |

**Index HNSW và B-tree trên bảng embedding.** Với mỗi d trong {768, 1024, 1536, 2560, 3072}:

| Bảng | Index |
|---|---|
| wiki_page_embeddings_<d> | `ix_<bảng>_hnsw`: HNSW trên embedding, opclass cosine (`halfvec_cosine_ops` cho 3072, `vector_cosine_ops` cho chiều khác), m = 16, ef_construction = 64. `ix_<bảng>_model` trên model_spec_id |
| source_chunk_embeddings_<d> | `ix_<bảng>_hnsw` như trên; `ix_<bảng>_model`; `ix_<bảng>_source` trên source_id; `ix_<bảng>_fts`: GIN trên to_tsvector cấu hình 'simple' của f_unaccent(text) |
| wiki_page_chunk_embeddings_<d> | `ix_<bảng>_hnsw`; `ix_<bảng>_model`; `ix_<bảng>_page` trên page_id; `ix_<bảng>_fts` như trên |

Index HNSW vẫn được tạo dù cột hầu như luôn NULL, để giữ tương thích khi tắt Milvus.

**Index khác**

| Index | Bảng | Định nghĩa |
|---|---|---|
| ix_sources_fulltext | sources | GIN trên to_tsvector cấu hình 'simple' của f_unaccent(full_text) |
| ix_sources_security_label | sources | B-tree trên security_label |
| ix_sources_content_hash | sources | B-tree trên content_hash (nếu ORM chưa khai báo) |
| ix_departments_external_id | departments | UNIQUE, partial với điều kiện external_id IS NOT NULL |
| ix_departments_code | departments | UNIQUE, partial với điều kiện code IS NOT NULL |
| ix_departments_parent_id | departments | B-tree trên parent_id |
| ix_employees_mcp_token_hash | employees | UNIQUE, partial với điều kiện mcp_token_hash IS NOT NULL (ORM có thể đã khai báo) |
| ix_employees_external_id | employees | UNIQUE, partial với điều kiện external_id IS NOT NULL (ORM có thể đã khai báo) |

**Ràng buộc**

| Ràng buộc | Định nghĩa |
|---|---|
| ck_sources_security_label | security_label thuộc {PUBLIC, INTERNAL, RESTRICTED, CONFIDENTIAL} |
| ck_employees_clearance_level | clearance_level thuộc cùng tập trên |
| ck_employees_global_role_source | global_role_source thuộc {sso, manual} |
| fk_departments_parent_id | departments.parent_id tham chiếu departments.id, ON DELETE SET NULL |

**Không tạo:**

- Ràng buộc duy nhất trên slug của wiki_pages, kể cả `wiki_pages_slug_key` lẫn `uq_wiki_pages_slug_scope`. Ở hệ thống gốc, index duy nhất theo (slug, scope_type, scope_id) từng tồn tại nhưng đã bị một migration về sau gỡ. Từ đó ứng dụng tự đảm bảo không trùng slug trong cùng phạm vi (05a).
- Các index GIN cũ trên wiki_pages (`ix_wiki_pages_fulltext`, `ix_wiki_pages_kt_slugs`, `ix_wiki_pages_source_ids`), vì cũng đã bị gỡ.

**Dữ liệu seed trong migration** (chèn bỏ qua nếu trùng slug):

| slug | name | color | sort_order | description |
|---|---|---|---|---|
| general | Chung | #6B7280 | 0 | Tài liệu, quy định và thông tin chung |
| legal | Văn bản luật | #DC2626 | 1 | (để trống hoặc mô tả ngắn về văn bản quy phạm pháp luật) |

**Chuyển đổi dữ liệu khi nâng cấp từ CSDL cũ.** CSDL mới tạo không cần bước này; chỉ áp dụng khi chạy trên dữ liệu có sẵn.

- Giá trị app_config `active_llm_model_spec_id` và `active_vision_model_spec_id` không thuộc danh mục hiện hành và không bắt đầu bằng "custom/" được đổi thành `openai/gpt-6-luna`.
- Giá trị `ocr_model` bắt đầu bằng "gpt-5" được đổi thành `gpt-6-luna`.
- Tài khoản có external_id khác null và global_role khác admin được gán global_role_source = sso.

---

## 5. Alembic

### 5.1. `alembic.ini`

- script_location = alembic. Giá trị sqlalchemy.url trong file chỉ là chỗ giữ chỗ; env.py ghi đè bằng settings.database_url.
- Cấu hình logging gồm logger root, sqlalchemy và alembic, handler console và formatter generic. Mức: root WARN, sqlalchemy.engine WARN, alembic INFO.

### 5.2. `alembic/env.py`

1. Thêm thư mục gốc dự án vào sys.path để import được `app`.
2. Đặt `sqlalchemy.url` bằng `settings.database_url`, rồi nạp cấu hình logging từ alembic.ini nếu có.
3. `target_metadata = Base.metadata`. Phải import `app.database.oauth_models`, `app.models.task_failure` và `app.models.concept_relation` để các bảng đó đăng ký vào metadata.
4. Chế độ offline: cấu hình với url và literal binds, rồi chạy migration.
5. Chế độ online: tạo async engine từ section cấu hình với NullPool, mở kết nối, chạy migration qua `run_sync`, rồi dispose engine. Toàn bộ chạy bằng asyncio.run.

### 5.3. Chuỗi revision cho c2

c2 không tái tạo 51 migration lịch sử. Thay vào đó dùng chuỗi rút gọn sau, giữ đúng các id mà test và tài liệu khác tham chiếu.

| Thứ tự | revision | down_revision | Nội dung |
|---|---|---|---|
| 1 | `048_security_label_acl` | None | Baseline: toàn bộ lược đồ cuối cùng ở §4, cộng mọi đối tượng ở §4.3 và seed knowledge types, **trừ** phần chuỗi băm audit. Bảng audit_log ở dạng cũ, xem dưới |
| 2 | `049_audit_hash_chain` | `048_security_label_acl` | Đặc tả ở 06 §10.6. File phải đặt đúng tại `alembic/versions/049_audit_hash_chain.py`, vì test nạp file theo đường dẫn |
| 3 | `050_global_role_source` | `049_audit_hash_chain` | Thêm employees.global_role_source (String(10), not null, server default manual) cùng ck_employees_global_role_source, rồi chuyển dữ liệu như §4.3 |
| 4 | `051_prompt_templates` | `050_global_role_source` | Tạo bảng prompt_templates (06) |

Baseline tạo bảng audit_log ở **dạng cũ**:

- Cột: id UUID PK; timestamp timestamptz not null mặc định now(); principal_id UUID not null; principal_type String(20) not null mặc định 'human'; action String(50) not null; resource_type String(50) not null; resource_id String(100) not null; scope_type String(20) cho phép null; scope_id UUID cho phép null; decision String(10) not null; reason Text; metadata JSONB.
- Index: ix_audit_log_timestamp (timestamp), ix_audit_log_principal (principal_id), ix_audit_log_resource (resource_type, resource_id).

Baseline không tạo audit_chain_head; revision 049 tạo bảng đó và chuyển audit_log sang dạng chuỗi băm. Vì vậy baseline không được dựng audit_log từ ORM mà phải khai báo tường minh, và cũng không được dựng prompt_templates hay cột global_role_source.

Yêu cầu khác:

- Đầu baseline, nới cột `alembic_version.version_num` lên varchar(64).
- Downgrade của baseline xóa mọi thứ nó tạo, gồm bảng, kiểu enum skill_status, hàm f_unaccent và các extension, theo thứ tự ngược với khi tạo.
- Mỗi revision có các biến chuẩn revision, down_revision, branch_labels và depends_on, cùng hai hàm upgrade() và downgrade().

---

## 6. `app/main.py`

### 6.1. Lúc import

1. Tạo `mcp_server = create_mcp_server()` (từ `app.mcp.server`, xem 06).
2. Tạo `mcp_http_app` là ứng dụng HTTP của FastMCP, với path "/" và chế độ stateless HTTP.
3. Tạo `app = FastAPI(title="Arkon API", version="0.1.0", lifespan=lifespan)`.

Import `app.main` không được kết nối CSDL, Redis hay MinIO. Mọi kết nối chỉ xảy ra trong lifespan hoặc khi có request.

### 6.2. `seed_default_admin()` (async)

1. Nếu `default_admin_password` rỗng: ghi cảnh báo rồi bỏ qua.
2. Mở phiên qua async_session_factory. Nếu đã có Employee với role = admin thì bỏ qua.
3. Nếu chưa có:
   - Tạo Department tên "Administration", mô tả "System administrators".
   - Tạo Employee tên "Admin", email = default_admin_email, password_hash = `hash_password(default_admin_password)` (bcrypt, 02 §4), role admin.
   - Tạo liên kết EmployeeDepartment giữa hai bản ghi trên.
   - Commit.
4. Mọi lỗi chỉ ghi cảnh báo.

### 6.3. Lifespan

Lifespan lồng bên trong lifespan của mcp_http_app; bắt buộc, vì FastMCP cần khởi động task group của nó. Thứ tự khi khởi động:

1. `storage_service.ensure_bucket()`.
2. `seed_default_admin()`.
3. `seed_default_knowledge_types()` (§7.1).
4. `seed_builtin_skills()` (§7.2).
5. Đọc khóa `role_permissions_custom` qua ConfigService. Có giá trị thì gọi `permissions.load_role_permissions_override(giá_trị)` (02).
6. Nếu secret_key còn bằng giá trị mặc định: ghi cảnh báo.

Mỗi bước bọc riêng: lỗi chỉ ghi cảnh báo, không chặn khởi động. Khi tắt: gọi `app.ai.tracing.shutdown_langfuse()`, lỗi bỏ qua.

### 6.4. Middleware

Liệt kê theo thứ tự đăng ký. Middleware đăng ký sau nằm ngoài cùng.

1. **CORS:** allow_origins = settings.cors_origin_list; cho phép credentials, mọi method và mọi header.
2. **Cổng MCP:** áp dụng cho đường dẫn `/mcp` và `/mcp/...`. Hành vi xem 02 §1; middleware này không tự xác thực token.
3. **Phát thông báo:** trước khi xử lý request gọi `notification_service.init_request_dispatch_scope()`. Sau khi có response gọi `await notification_service.dispatch_pending()`; lỗi ở bước này chỉ ghi cảnh báo, response vẫn trả bình thường (06).
4. **`UploadSizeLimitMiddleware`** (loại C) với `limit_for(method, path)`: trả settings.max_upload_size_bytes khi method là POST và path là `/api/sources/upload`, các trường hợp khác trả None.
5. **`CorrelationIdMiddleware`** (loại C): đăng ký cuối cùng nên nằm ngoài cùng; mọi request và mọi bản ghi audit đều mang một trace id.

### 6.5. Mount và router

- `app.mount("/mcp", mcp_http_app)`.
- Thứ tự include router:

| Thứ tự | Router | Prefix |
|---|---|---|
| 1 | oauth.wellknown_router | không có |
| 2 | oauth.router | /oauth |
| 3 | auth, sso, sources, notes, wiki_branches, wiki_drafts, legal_docs, wiki, wiki_images | /api |
| 4 | admin_settings, admin_embeddings, admin_models, admin_custom_models, admin_stats, admin_failures | /api |
| 5 | rbac, org_sync, knowledge_types, audit, skills, skill_contributions, prompts, notifications | /api |

Thứ tự trên có ý nghĩa. wiki_branches và wiki_drafts phải đứng trước wiki, để các đường dẫn cụ thể không bị route động của wiki chặn mất.

### 6.6. Endpoint hệ thống

| Method, đường dẫn | Phản hồi (luôn 200) |
|---|---|
| GET / | `{name: "Arkon", description: "Enterprise AI Control Center", version: "0.1.0", mcp_endpoint: "/mcp", docs: "/docs"}` |
| GET /health | `{status, services: {database, redis, minio}}`. Mỗi dịch vụ là "healthy" hoặc "error". database: chạy truy vấn SELECT 1 qua async_session_factory. redis: lấy `get_arq_pool()` của router sources rồi ping. minio: `storage_service.ensure_bucket()`. status là "healthy" nếu cả ba healthy, ngược lại "degraded". Lỗi được ghi cảnh báo |
| GET /api/health | `{api: "healthy", database, worker}`. database kiểm tra như trên. worker là ping Redis trực tiếp với host, port, password (rỗng thì None), db từ settings và timeout kết nối 2 giây, rồi đóng kết nối. Mỗi trường là "healthy" hoặc "error" |

---

## 7. Seed lúc khởi động

### 7.1. `app/scripts/seed_knowledge_types.py`

- Hằng `DEFAULT_KNOWLEDGE_TYPES` gồm hai mục general và legal, cùng dữ liệu như bảng seed ở §4.3.
- `async seed_default_knowledge_types()`:
  - Idempotent: chỉ chèn slug chưa có.
  - Bỏ qua mục legal nếu đã có một loại slug "luat", là slug cũ dùng cho văn bản luật.
  - Commit. Lỗi chỉ ghi cảnh báo.
- Chạy được bằng `python -m app.scripts.seed_knowledge_types`.

### 7.2. `app/scripts/seed_skills.py` — `async seed_builtin_skills(skills_root=None)`

1. **Thư mục gốc:** mặc định là thư mục `skills/` ở gốc dự án. Không tồn tại thì ghi cảnh báo rồi trả về.
2. **Bucket:** gọi `storage_service.ensure_bucket()`. Lỗi thì ghi cảnh báo rồi trả về.
3. **Chọn thư mục:** mọi thư mục con trực tiếp có file `SKILL.md`, duyệt theo tên tăng dần.
4. **Đóng gói:** với mỗi thư mục, tạo zip trong bộ nhớ, nén deflate. Tên mỗi mục trong zip là "<tên thư mục>/<đường dẫn tương đối>". Băm nội dung bằng `SkillService._calculate_zip_content_hash` (06), để kết quả băm khớp với luồng upload.
5. **Kỹ năng đã có** (tra theo slug = tên thư mục):
   - status archived: bỏ qua.
   - Phiên bản hiện hành có created_by khác null, nghĩa là người dùng đã sửa: bỏ qua, không ghi đè.
   - Hash trùng version_hash: bỏ qua.
   - Ngược lại: tạo SkillVersion n+1 với created_by null, tải nội dung lên, rồi cập nhật Skill: current_version = n+1, version_hash, storage_path = `skills/<id>/versions/<n+1>/content/`, status active.
6. **Kỹ năng mới:** Skill với name = slug = tên thư mục, scope global, current_version 1, is_system true, status active; kèm SkillVersion 1.
7. **Tải lên:** mỗi file trong zip lên `skills/<skill_id>/versions/<n>/content/<tên mục trong zip>`. Content type đoán theo đuôi file, không đoán được thì application/octet-stream.
8. **Lỗi:** commit theo từng kỹ năng. IntegrityError nghĩa là một tiến trình seed khác chạy đồng thời đã làm việc này: ghi info rồi rollback. Lỗi khác ghi log rồi tiếp tục với kỹ năng sau.

Chạy được bằng `python -m app.scripts.seed_skills`.

---

## 8. Triển khai

### 8.1. `Dockerfile` (backend)

1. Ảnh nền python:3.12-slim, thư mục làm việc /app.
2. Cài gói hệ thống bằng apt: build-essential, libgl1, libglib2.0-0, libreoffice-nogui. LibreOffice cần cho bộ chuyển định dạng (03). Dọn cache apt.
3. Nâng pip. Sao chép pyproject.toml rồi cài gói dự án. Làm bước này trước khi chép mã nguồn để Docker cache được lớp phụ thuộc.
4. Sao chép app/, alembic/, alembic.ini, skills/ và entrypoint.sh. Bỏ ký tự CR khỏi entrypoint.sh và cấp quyền thực thi.
5. Tạo người dùng không phải root tên appuser, chuyển quyền sở hữu /app cho người dùng đó, rồi chạy bằng appuser.
6. Biến môi trường: PYTHONPATH=/app, PYTHONUNBUFFERED=1.
7. ENTRYPOINT là ./entrypoint.sh. CMD mặc định chạy uvicorn với `app.main:app`, host 0.0.0.0, cổng 5055.

### 8.2. `entrypoint.sh`

Shell POSIX, dừng ngay khi có lỗi.

1. Chạy `alembic upgrade head`.
2. Chạy module seed_knowledge_types; lỗi ở bước này được bỏ qua.
3. Chạy module seed_skills.
4. Thay tiến trình bằng lệnh được truyền vào (exec các tham số).

### 8.3. `docker-compose.yml`

Có một khối cấu hình dùng chung cho api, worker, worker_skills và migrator:

- Ảnh `wiki-backend:latest`, env_file `.env.docker`, restart always.
- Phụ thuộc postgres, redis và minio ở trạng thái healthy.
- Volume: `./temp_uploads` gắn vào /app/temp_uploads; `./app` và `./alembic` gắn vào để phát triển nóng.

| Dịch vụ | Mô tả |
|---|---|
| postgres | Ảnh pgvector/pgvector:pg16. Biến POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB mặc định arkon, arkon_secret, arkon. Volume dữ liệu riêng. Alias mạng wiki_postgres. Healthcheck bằng pg_isready mỗi 5 giây, thử 10 lần |
| redis | Ảnh redis:7-alpine, bật lưu định kỳ và yêu cầu mật khẩu REDIS_PASSWORD (mặc định arkon_secret). Healthcheck ping |
| minio | Ảnh minio/minio, console ở cổng 9001. Root user/password lấy từ MINIO_ACCESS_KEY/MINIO_SECRET_KEY. Ánh xạ cổng host 9002→9000 và 9003→9001. Healthcheck sẵn sàng mỗi 10 giây |
| etcd | Phụ trợ cho Milvus: etcd v3.5, auto compaction theo revision, quota 4 GiB |
| milvus | milvusdb/milvus v2.4.x chế độ standalone, dùng etcd và minio. Cổng 19530 và 9091. Healthcheck qua /healthz |
| milvus_ui | Giao diện Attu trỏ tới milvus:19530, cổng host 9004 |
| migrator | Khối dùng chung, build từ Dockerfile, chạy `alembic upgrade head` một lần, không restart |
| api | Khối dùng chung, chỉ chạy sau khi migrator kết thúc thành công. Cổng 5055. Chạy uvicorn `app.main:app` với proxy headers bật và tin mọi IP forward. Healthcheck gọi GET /health mỗi 15 giây, start period 30 giây. Tham gia mạng mặc định và mạng ngoài `cahy-internal` (tên lấy từ CAHY_NETWORK_NAME) để chatbot và Keycloak gọi được |
| worker | Khối dùng chung, chạy arq với `app.worker.WorkerSettings`, chờ api healthy |
| worker_skills | Khối dùng chung, chạy arq với `app.worker.SkillWorkerSettings`, chờ api healthy |
| frontend | Build từ ./frontend, với tham số build NEXT_PUBLIC_API_URL (mặc định http://localhost:5055) và INTERNAL_API_URL = http://api:5055. Cổng host 3119→3000. Chờ api healthy |

Volume có tên: postgres_data, redis_data, minio_data, milvus_etcd_data, milvus_data.

### 8.4. Biến môi trường triển khai

- File `.env.docker` chứa các biến tương ứng với trường Settings ở §2.2, viết hoa.
- Trong Docker, host lấy theo tên dịch vụ: DATABASE_URL trỏ tới postgres, REDIS_HOST=redis, MINIO_ENDPOINT=minio:9000, MILVUS_HOST=milvus.
- Không đưa giá trị bí mật thật vào repo. Chỉ được commit file mẫu với giá trị giữ chỗ.

### 8.5. Phụ thuộc phải bổ sung vào `pyproject.toml` của c2

pyproject hiện tại của c2 chưa có các gói sau, mà mã nền tảng cần:

- uvicorn, python-multipart, alembic (đã có), asyncpg (đã có nhưng chưa cài trong venv), pgvector
- minio, arq, redis, bcrypt, cryptography, tiktoken
- anthropic, google-genai
- tabulate (nếu bộ phân tích bảng cần, xem 03)

Thêm cấu hình build setuptools tìm package `app*`, để `pip install .` trong Dockerfile cài được ứng dụng. Giữ nguyên các mục pytest đã có (testpaths tests, asyncio_mode auto).
