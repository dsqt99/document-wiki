# 04 — Truy hồi, embedding và tìm kiếm

Phạm vi: lưu trữ embedding, Milvus, chia chunk trang wiki, tìm kiếm lai (vector + toàn văn), hợp nhất RRF, rerank và MMR, `unified_search`, mở rộng đồ thị pháp lý 1 bước, sinh câu hỏi tìm kiếm, job đổi model embedding, API quản trị model, các đường tìm kiếm MCP/REST và màn cài đặt embedding.

Tài liệu tuân thủ `QUY_TAC_DAC_TA.md`: chỉ có văn xuôi, bảng và chữ ký.

---

## 1. Phân loại module

### 1.1. File loại C đã có trong c2 (không viết lại, chỉ cần cung cấp phụ thuộc)

| Module | Vai trò |
|---|---|
| `app/services/milvus_service.py` | Kết nối và đọc/ghi Milvus |
| `app/services/reranker_service.py` | Rerank remote/local, ngưỡng, MMR |
| `app/services/search_fusion.py` | Reciprocal Rank Fusion |
| `app/services/wiki_chunk_service.py` | Chia trang wiki thành chunk theo heading và index |
| `app/services/retrieval_service.py` | `unified_search`, gộp chunk liền kề, đồ thị pháp lý |
| `app/services/chunk_budget.py` | Ngân sách token của chunk |
| `app/services/security_label.py` | Mệnh đề lọc theo nhãn mật |
| `app/services/legal_route_service.py` | Tra cứu chính xác theo số hiệu văn bản / điều |
| `app/core/vi_tokenizer.py` | Tách từ tiếng Việt, từ dừng, số hiệu văn bản |

Các file này import những symbol dưới đây. Người viết code **phải** cung cấp đúng tên, chữ ký và hành vi.

### 1.2. Module phải tự xây theo đặc tả này

| Module | Nội dung |
|---|---|
| `app/services/embedding_storage.py` | Đọc/ghi bảng embedding theo chiều, băm nội dung, dọn dẹp |
| `app/services/question_generator.py` | Sinh câu hỏi tìm kiếm cho điều khoản |
| `app/services/wiki_service.py` (phần tìm kiếm) | `search_pages_semantic`, `search_pages_hybrid`, `search_source_chunks_hybrid`, `_lexical_plan` |
| `app/routers/admin_embeddings.py` | API catalog/trạng thái/đổi model/job/backfill/probe/test |
| `app/routers/admin_models.py` | API catalog và đổi model LLM, vision |
| `app/ai/embedding_catalog.py` | Danh mục model embedding |
| `app/ai/registry.py` | `ProviderRegistry` |
| `app/database/models.py` | Bảng embedding, `EmbeddingJob`, các model pháp lý |
| `app/worker.py` | Task `reembed_all_pages_task`, `generate_questions_task`, `backfill_source_chunks_task` |
| `app/services/verbatim_service.py` | Chunk nguyên văn của văn bản gốc (chi tiết thuộc đặc tả nạp tài liệu; ở đây chỉ nêu phần tìm kiếm cần) |

### 1.3. Ai gọi gì (ràng buộc giao diện)

| Bên gọi (file c2) | Symbol cần có |
|---|---|
| `legal_service` | `upsert_page_embedding`, `wiki_chunk_content_hash`, `index_wiki_page_chunks` (từ `wiki_chunk_service`), `get_spec`, `ProviderRegistry` |
| `admin_custom_models` | `_get_current_job` từ `app.routers.admin_embeddings`: dùng để chặn xóa model embedding tùy chỉnh đang được một job `pending`/`running` sử dụng (trả 409) |
| `tracing` | `EMBEDDING_CATALOG` từ `app.ai.embedding_catalog` |
| `retrieval_service` | `wiki_service.search_pages_hybrid`, `wiki_service.search_source_chunks_hybrid`, `wiki_service.search_pages_semantic`, `legal_route_service.route_exact_legal_query`, các model `LegalRelation`, `LegalUnit`, `WikiPage` |
| `wiki_chunk_service` | `upsert_page_embedding`, `upsert_wiki_chunk_embedding`, `delete_wiki_page_chunk_embeddings`, `wiki_chunk_content_hash`, `get_spec`, `ProviderRegistry` |

---

## 2. Cấu hình

### 2.1. Biến môi trường / settings

| Khóa | Mặc định | Ý nghĩa |
|---|---|---|
| `milvus_enabled` | `False` | Tắt thì mọi thao tác vector trả rỗng, không lỗi |
| `milvus_host` | `"milvus"` | |
| `milvus_port` | `19530` | |
| `milvus_user` | rỗng | |
| `milvus_password` | rỗng | |
| `milvus_database` | `"default"` | |
| `reranker_enabled` | `True` | |
| `reranker_provider` | `"http"` | |
| `reranker_base_url` | `""` | Rỗng = không có reranker remote |
| `reranker_api_key` | `""` | |
| `reranker_model` | `"BAAI/bge-reranker-v2-m3"` | |
| `reranker_top_n` | `10` | |
| `reranker_threshold` | `0` | Đọc tùy chọn (thiếu thì coi là 0) |
| `chunk_target_tokens` | `1500` | Kẹp trong 1000–2000 |
| `chunk_overlap_tokens` | `150` | Tối đa 1/4 target |
| `portal_base_url` | | Dùng tạo link văn bản gốc trong kết quả MCP |

### 2.2. Khóa cấu hình trong bảng config (DB)

| Khóa | Ý nghĩa |
|---|---|
| `active_embedding_model_spec_id` | Spec embedding đang hoạt động |
| `active_llm_model_spec_id` | Spec LLM đang hoạt động |
| `active_vision_model_spec_id` | Spec vision đang hoạt động |
| `embedding_api_key__<provider>` | API key embedding theo provider |
| `llm_api_key__<provider>`, `vision_api_key__<provider>` | API key LLM/vision theo provider |
| `llm_api_key`, `vision_api_key`, `embedding_api_key` | Khóa kiểu cũ (legacy), chấp nhận nếu hợp provider |

---

## 3. Lược đồ dữ liệu

### 3.1. Chiều vector hỗ trợ

`SUPPORTED_DIMENSIONS` = 768, 1024, 1536, 3072. Mỗi chiều có một bộ bảng riêng, hậu tố `_<dim>`.

Cột `embedding` trong PostgreSQL **cho phép NULL** và khi ghi luôn để NULL: vector thật nằm trong Milvus. Cột vẫn tồn tại để giữ tương thích (kiểu `vector(dim)`; riêng 3072 dùng `halfvec(3072)`). Lưu ý: migration cũ khai báo NOT NULL; bản c2 phải là nullable.

### 3.2. `wiki_page_embeddings_<dim>`

| Cột | Kiểu | Ràng buộc |
|---|---|---|
| page_id | UUID | PK, FK `wiki_pages.id` ON DELETE CASCADE |
| model_spec_id | varchar(128) | PK |
| content_hash | varchar(64) | NOT NULL |
| embedded_at | timestamptz | mặc định now() |
| embedding | vector(dim) / halfvec(3072) | nullable |

Index: theo `model_spec_id`; HNSW cosine trên `embedding` (m=16, ef_construction=64).

### 3.3. `source_chunk_embeddings_<dim>`

| Cột | Kiểu | Ràng buộc |
|---|---|---|
| source_id | UUID | PK, FK `sources.id` ON DELETE CASCADE |
| chunk_index | int | PK |
| model_spec_id | varchar(128) | PK |
| start_char | int | |
| end_char | int | |
| page_number | int | mặc định 1 |
| text | text | |
| content_hash | varchar(64) | |
| embedded_at | timestamptz | mặc định now() |
| embedding | vector / halfvec | nullable |

Index: HNSW cosine; theo model_spec_id; theo source_id; GIN toàn văn trên `text` (biểu thức tsvector cấu hình `simple` bọc `f_unaccent`).

### 3.4. `wiki_page_chunk_embeddings_<dim>`

| Cột | Kiểu | Ràng buộc |
|---|---|---|
| page_id | UUID | PK, FK `wiki_pages.id` CASCADE |
| chunk_index | int | PK |
| model_spec_id | varchar(128) | PK |
| heading_path | text | mặc định "" |
| text | text | |
| content_hash | varchar(64) | |
| embedded_at | timestamptz | |
| embedding | vector / halfvec | nullable |

Index: HNSW cosine; theo model; theo page_id; GIN toàn văn trên `text`.

### 3.5. Toàn văn tiếng Việt

- Cần extension `unaccent` và một hàm `f_unaccent(text)` khai báo IMMUTABLE bọc unaccent (để dùng được trong index biểu thức).
- Cấu hình FTS là `simple` (không stemming), áp lên `f_unaccent(lower(...))` hoặc tương đương: tìm kiếm không phân biệt dấu và hoa/thường.
- Truy vấn dùng `websearch_to_tsquery('simple', ...)`.
- Có index GIN toàn văn trên `sources.full_text`.

### 3.6. `embedding_jobs`

| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | UUID | PK |
| model_spec_id | varchar(128) | spec đích |
| status | varchar(20) | `pending`, `running`, `completed`, `failed`, `cancelled`; mặc định `pending` |
| total_pages | int | nullable |
| done_pages | int | mặc định 0 |
| error_message | text | nullable |
| started_at | timestamptz | nullable |
| finished_at | timestamptz | nullable |
| created_at | timestamptz | mặc định now() |

Index: (status, created_at).

### 3.7. Model pháp lý (test dựng trực tiếp bằng keyword args)

`LegalUnitType` (enum chuỗi): `part`, `chapter`, `section`, `article`, `clause`, `point`.

`LegalRelationType` (enum chuỗi): `sua_doi`, `bo_sung`, `thay_the`, `bai_bo`, `huong_dan`, `can_cu`, `dan_chieu`.

`LegalUnit`: id, wiki_page_id, source_id, unit_type, unit_number, title, doc_number, content (và các cột khác do đặc tả wiki/pháp lý quy định).

`LegalRelation`: id, source_unit_id, target_unit_id (nullable), target_doc_number, target_article_number, target_clause_number, relation_type, quote_context, is_effective. Có relationship `source_unit` và `target_unit` tới `LegalUnit`, dùng được sau khi gọi `configure_mappers()`.

### 3.8. Hàm tra model ORM theo chiều

`get_embedding_model_for_dim(dim)`, `get_source_chunk_embedding_model_for_dim(dim)`, `get_wiki_page_chunk_embedding_model_for_dim(dim)`: trả lớp ORM của bảng tương ứng; chiều không hỗ trợ thì ném `ValueError`.

---

## 4. Danh mục embedding và registry

### 4.1. `app/ai/embedding_catalog.py`

`EmbeddingModelSpec` (dataclass frozen): id, provider, model_id, dimension, max_input_tokens, label, cost_per_1m_tokens, notes.

`EMBEDDING_CATALOG`: dict id → spec, gồm:

| id | provider | dimension | max_input_tokens | cost / 1M |
|---|---|---|---|---|
| google/gemini-embedding-001 | google | 3072 | 2048 | 0.15 |
| google/gemini-embedding-2 | google | 3072 | 8192 | 0.15 |
| openai/text-embedding-3-small | openai | 1536 | 8191 | 0.02 |
| openai/text-embedding-3-large | openai | 3072 | 8191 | 0.13 |

Ngoài ra:

- `get_spec(spec_id)`: trả spec của catalog, hoặc dựng spec cho model tùy chỉnh có id dạng `custom/<dim>/<model_id>`. Không tìm thấy thì ném `UnknownEmbeddingModel` (lớp con của `KeyError`).
- `list_specs()`: danh sách spec của catalog.
- `SUPPORTED_DIMENSIONS`: tập 4 chiều nêu trên (router còn gọi là `EMBEDDING_DIMENSIONS`).

### 4.2. `app/ai/registry.py` — `ProviderRegistry`

| Thành phần | Hành vi |
|---|---|
| `get_embedding(task="document" \| "search_query", spec_id=None)` | Trả provider embedding (async) có `embed(text)` và `embed_batch(texts)`; spec_id None thì dùng spec đang hoạt động |
| `get_active_embedding_spec_id()` | Đọc khóa `active_embedding_model_spec_id`; chỉ hợp lệ nếu là id trong catalog hoặc model tùy chỉnh còn tồn tại; nếu không, trả None |
| `get_llm()` | Provider LLM đang hoạt động |
| `_load_embedding_config(spec_id)` | Trả cấu hình có thuộc tính `api_key` (router dùng để kiểm tra có key hay chưa) |

---

## 5. `app/services/embedding_storage.py`

Mọi hàm là async trừ khi ghi "đồng bộ". Không hàm nào commit; người gọi commit.

| Chữ ký | Hành vi |
|---|---|
| `compute_content_hash(title, summary, content_md) -> str` (đồng bộ) | SHA-256 dạng hex của ba trường nối bằng một dòng trống; None coi là chuỗi rỗng |
| `embedding_input_text(title, summary, content_md) -> str` (đồng bộ) | Cùng cách nối, cắt tối đa 8000 ký tự |
| `upsert_page_embedding(session, page_id, spec, vector, content_hash, *, title=None, summary=None, content_md=None)` | Upsert vào `wiki_page_embeddings_<spec.dimension>` theo khóa (page_id, model_spec_id), cột embedding để NULL; nếu đã có thì cập nhật content_hash và embedded_at. Sau đó upsert bản ghi trang vào Milvus (kèm vector, title, summary, content) |
| `get_existing_hash(session, page_id, spec_id, dimension) -> str \| None` | Hash đang lưu, không có thì None |
| `cleanup_stale_embeddings(session, keep_spec_id) -> int` | Xóa các dòng có model_spec_id khác keep_spec_id trên cả 4 bảng trang; trả tổng số dòng đã xóa |
| `cleanup_stale_source_chunk_embeddings(session, keep_spec_id) -> int` | Như trên cho bảng chunk văn bản gốc |
| `cleanup_stale_wiki_chunk_embeddings(session, keep_spec_id) -> int` | Như trên cho bảng chunk trang wiki |
| `delete_wiki_page_embeddings(session, page_id) -> int` | Xóa trên 4 bảng trang và xóa trong Milvus cho từng chiều |
| `get_spec_for_job(job)` | Spec ứng với `job.model_spec_id` |
| `chunk_content_hash(text) -> str` (đồng bộ) | SHA-256 hex của text |
| `wiki_chunk_content_hash(heading_path, text) -> str` (đồng bộ) | SHA-256 hex của heading_path, một dòng trống, rồi text |
| `upsert_chunk_embedding(session, source_id, chunk_index, spec, vector, *, text, start_char, end_char, page_number, content_hash)` | Upsert theo (source_id, chunk_index, model_spec_id); cập nhật hash, text, start_char, end_char, page_number, embedded_at; đồng bộ sang Milvus |
| `delete_source_chunk_embeddings(session, source_id) -> int` | Xóa trên mọi bảng chiều và trong Milvus |
| `upsert_wiki_chunk_embedding(session, page_id, chunk_index, spec, vector, *, text, heading_path, content_hash)` | Upsert theo (page_id, chunk_index, model_spec_id); đồng bộ Milvus |
| `delete_wiki_page_chunk_embeddings(session, page_id, spec_id=None) -> int` | Xóa chunk của trang; có spec_id thì chỉ xóa của spec đó (cả ở Milvus) |

---

## 6. Milvus (`milvus_service`, loại C)

- Collection: `arkon_wiki_pages_<dim>`, `arkon_wiki_chunks_<dim>`, `arkon_source_chunks_<dim>`; metric COSINE.
- Id bản ghi xác định từ: trang = page_id + spec; chunk wiki = page_id + chunk_index + spec; chunk nguồn = source_id + chunk_index + spec.
- Khi ghi cắt trường: content 12000, title 500, summary 2000, heading_path 500 ký tự.
- `search_milvus_vectors(collection, vector, limit=10, filter_expr=...)` trả danh sách dict phẳng chứa các trường entity và `score` (cosine); nprobe 10; consistency Strong.
- `test_milvus_connection()` trả (ok, message).
- `milvus_enabled=False` → mọi hàm tìm kiếm trả rỗng.

---

## 7. Chia chunk trang wiki (`wiki_chunk_service`, loại C)

Hành vi (để đối chiếu, không cần viết lại):

1. Trang có slug dành riêng `_index`, `_log`, `_hot` bị bỏ qua (trả 0). Không có spec hoạt động: trả 0.
2. Tách theo heading cấp 1–3; heading_path là chuỗi breadcrumb nối bằng " > ".
3. Phần dài hơn `CHUNK_TARGET_TOKENS` được cắt cửa sổ có chồng lấn; chunk dưới 50 ký tự bị bỏ.
4. Văn bản đưa vào embedding của chunk: tiêu đề trang, " — ", heading_path, dòng trống, rồi nội dung.
5. Xóa chunk cũ của trang **cho spec này**, embed một lô gồm [toàn văn trang] + các chunk, upsert vector cấp trang (hash = `wiki_chunk_content_hash("", content_md)`), rồi upsert từng chunk. Không commit.

Ngân sách (`chunk_budget`): target 1500 kẹp 1000–2000; overlap 150, không quá 1/4 target.

---

## 8. Tìm kiếm trong `wiki_service`

### 8.1. Hằng số

| Tên | Giá trị |
|---|---|
| `_HYBRID_CANDIDATE_POOL` | 50 |
| `_FTS_CONFIG` | `"simple"` |
| `_STRONG_COVERAGE` | 0.6 |
| Slug dành riêng luôn bị loại | `_index`, `_log`, `_hot` |

### 8.2. Bộ lọc dùng chung cho trang wiki

- **Phạm vi (scope)**:
  - Theo danh tính (department_ids, project_ids): trang `global` + trang phòng ban có scope_id thuộc department_ids + trang dự án có scope_id thuộc project_ids.
  - `all_scopes=True` (quản trị): không lọc phạm vi.
  - `inverse_scope=True` (dùng cho gợi ý ngoài phạm vi): trang phòng ban **không** thuộc phòng ban của người dùng + trang dự án không thuộc dự án của người dùng; loại trang global.
  - Khi chỉ truyền scope_type/scope_id (không có danh tính): khớp đúng scope_type và scope_id.
- **Loại tri thức**: nếu có `allowed_kt_slugs` thì giữ trang có `knowledge_type_slugs` giao với danh sách, hoặc trang không gắn loại nào.
- **Nhãn mật**: nếu có `clearance` thì thêm `page_label_clause(clearance)` (trang) hoặc `source_label_clause(clearance)` (văn bản gốc) từ `security_label`.
- **page_filter**: mệnh đề SQLAlchemy bổ sung do bên gọi truyền (ví dụ MCP truyền `page_source_clause`), AND vào điều kiện.

### 8.3. `_lexical_plan(query_text) -> (terms, needles)` (test dùng)

- `terms` = `keyword_terms(query_text)` (từ `vi_tokenizer`): từ nội dung đã bỏ dấu, ghép từ ghép bằng `_`, bỏ cụm hỏi, số hiệu văn bản và từ dừng, khử trùng lặp, giữ thứ tự.
- `needles` là danh sách cặp (loại, mẫu):
  - Mỗi số hiệu văn bản tìm được bằng `find_doc_numbers` → cặp `("doc", mẫu)`. Mẫu khớp trên chữ thường đã bỏ dấu; các phần của số hiệu (tách tại `/` hoặc `-`) được nối bởi một trong `/`, `.`, `-` (cho phép khoảng trắng hai bên); có ranh giới hai đầu để `13/2023` không khớp bên trong `113/2023` và không khớp khi phía sau còn ký tự chữ/số hoặc phần nối tiếp kiểu `-nd-cp`.
  - Mỗi cụm trong ngoặc kép (`quoted_phrases`) → cặp `("phrase", cụm đã bỏ dấu, chữ thường)`.
- Mệnh đề "exact": khớp trên `lower(f_unaccent(text))`: needle `doc` dùng so khớp biểu thức chính quy của PostgreSQL; needle `phrase` dùng LIKE có escape ký tự đặc biệt.

### 8.4. Nhánh từ vựng (lexical arm)

1. Hàng khớp needle chính xác đứng đầu, đánh dấu `strong=True`, `exact=True`.
2. Sau đó là hàng khớp FTS **bất kỳ** term (`websearch_any`), xếp: hàng khớp **tất cả** term (`websearch_all`) trước, rồi theo ts_rank giảm dần; giới hạn 50.
3. Một hàng FTS là `strong` nếu chỉ có 1 term, hoặc `term_coverage(terms, text) >= 0.6`.
4. Không có term và không có needle → nhánh rỗng.

### 8.5. `search_pages_semantic`

Chữ ký: `search_pages_semantic(session, query_embedding, top_k=10, allowed_kt_slugs=None, scope_type="global", scope_id=None, spec_id=None, department_ids=None, project_ids=None, inverse_scope=False, all_scopes=False, clearance=None, page_filter=None) -> list[tuple[WikiPage, float]]`

1. Tìm Milvus trên collection chunk wiki của spec, limit = top_k × 8, lọc theo spec.
2. Mỗi trang giữ điểm cao nhất trong các chunk của nó.
3. Nạp các trang từ PG với đầy đủ bộ lọc §8.2; trang không qua lọc bị bỏ.
4. Trả top_k cặp (trang, độ tương đồng) giảm dần.

### 8.6. `search_pages_hybrid`

Chữ ký: `search_pages_hybrid(session, query_embedding, query_text, top_k=10, allowed_kt_slugs=None, spec_id=None, department_ids=None, project_ids=None, all_scopes=False, clearance=None, page_filter=None) -> list[dict]`

Mỗi dict: `page` (WikiPage), `rrf` (float), `cosine` (float hoặc None), `heading_path` (str), `fts_matched` (bool), `exact_match` (bool), `chunk_index` (int), `chunk_text` (str).

1. Không có spec hoạt động (và không truyền spec_id) → [].
2. Nhánh vector: Milvus chunk wiki, limit 50, rồi lọc qua PG như §8.2.
3. Nhánh từ vựng: trên bảng chunk wiki của chiều tương ứng, như §8.4, cùng bộ lọc.
4. Hợp nhất RRF (k=60) trên khóa chunk; gom chunk về trang cha: chunk có RRF cao nhất làm đại diện (heading_path, chunk_index, chunk_text, cosine), cờ `fts_matched` và `exact_match` là OR trên mọi chunk của trang.
5. Sắp RRF giảm dần, trả top_k.

### 8.7. `search_source_chunks_hybrid`

Chữ ký: `search_source_chunks_hybrid(session, query_embedding, query_text, top_k=10, allowed_source_ids=None, spec_id=None, clearance=None) -> list[dict]`

Mỗi dict: `source` (Source), `chunk` (hàng bảng chunk nguồn), `rrf`, `cosine`, `heading_path` (luôn ""), `fts_matched`, `exact_match`.

- `allowed_source_ids` là tập rỗng → [] ngay. None → không giới hạn.
- Văn bản gốc đủ điều kiện: `chunk_status = ready`, hoặc `status` thuộc {ready, partial}, hoặc `preserve_verbatim = True`.
- Áp `source_label_clause(clearance)` nếu có clearance.
- Hai nhánh vector (Milvus chunk nguồn, limit 50) và từ vựng như trang, hợp nhất RRF k=60 theo khóa (source_id, chunk_index); trả top_k.
- Không có spec → [].

### 8.8. REST `GET /api/wiki/search`

- Quyền: `wiki:read`.
- Tham số: `q` (1–500 ký tự, bắt buộc), `limit` (mặc định 30, 1–100).
- Embed `q[:4000]` với task `search_query`; lỗi → 503 "Embedding model is not available".
- Gọi `search_pages_hybrid` với top_k = limit × 3 và phạm vi của người dùng; lọc lại theo quyền đọc từng trang; trả danh sách tóm tắt trang theo thứ tự xếp hạng, tối đa `limit`.

---

## 9. Hợp nhất RRF (`search_fusion`, loại C)

- `reciprocal_rank_fusion(ranked_lists, k=60) -> dict[key, float]`: điểm mỗi khóa = tổng 1/(k + rank) qua các danh sách (rank bắt đầu từ 1).
- `fuse_and_sort(ranked_lists, k=60) -> list[(key, score)]`: như trên, sắp giảm dần.

---

## 10. Reranker và MMR (`reranker_service`, loại C)

### 10.1. Giao diện test dùng

- `RerankResult(index, score, document)`.
- `RerankerService(base_url=None, api_key=None, model=None, enabled=None, top_n=None)`; `RerankerService.get_instance()` singleton.
- `_call_remote_reranker(query, documents, text_key)`: có thể bị test monkeypatch.
- `_remote_down_until`: mốc thời gian; đặt về 0 thì được thử remote lại.
- `_blend_prior(...)`: trộn điểm local với điểm ưu tiên (prior).
- `diversify_mmr(...)`: chọn đa dạng theo MMR.

### 10.2. Chế độ rerank (`info["mode"]`)

| Mode | Khi nào |
|---|---|
| `off` | reranker tắt |
| `remote` | có base_url và remote trả kết quả |
| `local` | không có remote, hoặc remote lỗi (ConnectError, mã khác 200…) — không ném lỗi |

Remote lỗi → đặt thời gian chờ 60 giây (`REMOTE_RETRY_AFTER_SECONDS`); trong khoảng đó không gọi remote mà dùng local luôn.

### 10.3. Gọi remote

- URL: base_url, nối thêm `/rerank` nếu chưa kết thúc bằng `/rerank`. Header Bearer khi có key. Timeout 10 giây.
- Lần đầu gửi JSON `model`, `query`, `documents`, `top_n`. Nếu không phải 200, thử lại dạng TEI: `query`, `texts`.
- Đọc kết quả là danh sách có `index` và `relevance_score` (hoặc `score`); giữ nguyên điểm remote (ví dụ 0.96 và 0.12).

### 10.4. Chấm điểm local

- Token hóa: các chuỗi ký tự chữ/số sau khi bỏ dấu, chữ thường.
- Điểm = độ phủ token truy vấn trong tài liệu × 0.5 + Jaccard × 0.2, cộng thêm 0.3 nếu toàn bộ truy vấn xuất hiện nguyên chuỗi trong tài liệu.
- Chỉ ở mode local: trộn prior = 0.6 × điểm local + 0.4 × (prior / prior lớn nhất), làm tròn 4 chữ số. Dùng để phá thế hòa theo thứ tự ban đầu.

### 10.5. Ngưỡng, ghim và MMR

1. Tài liệu được **ghim** (có pin key bằng true) luôn đứng đầu, không chịu ngưỡng và MMR.
2. Ngưỡng `threshold`: giữ tài liệu có điểm ≥ ngưỡng.
3. Không tài liệu nào qua ngưỡng nhưng có tài liệu ≥ `degrade floor` (floor < threshold) → giữ các tài liệu đó. Ví dụ ngưỡng 0.25, floor 0.15 chỉ giữ d1.
4. Không tài liệu nào qua cả floor → giữ thứ tự đầu vào (gắn điểm), tắt MMR.
5. MMR chọn tối đa (limit − số tài liệu ghim) với lambda mặc định 0.7, độ tương tự giữa tài liệu = Jaccard token. Ví dụ test: lambda 0.5 chọn c1 rồi c3.
6. Trường nội bộ `_rr_idx` bị gỡ khỏi kết quả.

---

## 11. `unified_search` (`retrieval_service`, loại C)

Hằng số: `MIN_SIM_FLOOR = 0.35`; ngưỡng rerank mặc định 0.2, degrade floor 0.15; MMR lambda 0.7.

Luồng (đối chiếu để cung cấp phụ thuộc đúng):

1. Nhánh tra cứu chính xác: `route_exact_legal_query(session, query, allowed_source_ids=...)`; trả khối exact (doc_number, full_path, title, content, warning_callout) nếu tìm thấy.
2. Nhánh trang wiki: `search_pages_hybrid` (keyword args như §8.6).
3. Nhánh văn bản gốc: `search_source_chunks_hybrid` (§8.7), sau đó `merge_sequential_chunks(hits, max_gap_chars=200)` gộp các chunk liền kề cùng văn bản khi khoảng cách ký tự ≤ 200.
4. Mỗi nhánh chạy trong `session.begin_nested()` (savepoint, dùng làm async context manager) để lỗi một nhánh không hỏng phiên. Nhánh lỗi được ghi vào `failed_arms` ("wiki", "source", "exact"); các nhánh khác vẫn trả kết quả.
5. Hit vector-only có cosine dưới `MIN_SIM_FLOOR` bị loại (hit có FTS/exact được giữ).
6. Rerank + ngưỡng + MMR như §10; hit exact được ghim.
7. Mở rộng đồ thị 1 bước (§12) nếu bật.
8. `check_out_of_scope=True`: gọi `search_pages_semantic(..., inverse_scope=True)` để đếm kết quả ngoài phạm vi (§13.3).
9. Trả kết quả gồm danh sách xếp hạng, `total_candidates`, `rerank_mode`, `failed_arms`, khối exact, đồ thị và gợi ý ngoài phạm vi.

---

## 12. Mở rộng đồ thị pháp lý 1 bước

`expand_graph_neighbors(session, page_ids/hits, ...)`:

- Thực hiện **đúng 2** lệnh `session.execute`: (1) lấy `LegalUnit` thuộc các trang kết quả, (2) lấy `LegalRelation` có đầu nguồn hoặc đầu đích là các unit đó.
- Quan hệ đi vào (unit khác tác động đến unit kết quả) và đi ra (unit kết quả tác động đến văn bản khác).

`format_graph_neighbors_section(...)` tạo khối Markdown, các chuỗi test kiểm tra:

- Tiêu đề: "🔗 **VĂN BẢN & ĐIỀU KHOẢN LIÊN QUAN**"
- Quan hệ đi vào bắt đầu bằng "Bị tác động bởi **"
- Quan hệ đi ra bắt đầu bằng "Văn bản này tác động đến **"

---

## 13. Đường tìm kiếm MCP

### 13.1. `search_wiki(query, top_k)`

- top_k kẹp 1..50.
- Embed query với task `search_query`.
- Gọi `unified_search` với: department_ids/project_ids của người dùng, `all_scopes = is_admin`, `allowed_source_ids` theo quyền, bật reranker và MMR, `check_out_of_scope = not is_admin`, `clearance` của người dùng, `page_filter = page_source_clause`.
- Thông báo:
  - Cả nhánh wiki và nhánh văn bản gốc lỗi, không có exact → thông báo thất bại bằng tiếng Việt.
  - Một số nhánh lỗi → cảnh báo nêu tên nhánh: "trang wiki", "văn bản gốc", "tra cứu theo số hiệu".
  - `rerank_mode = local` → ghi chú reranker chuyên dụng không khả dụng.
- Khối exact (nếu có): doc_number, full_path, title, content, warning_callout.
- Nhãn điểm mỗi kết quả: có điểm rerank → 2 chữ số thập phân; không có thì cosine dạng phần trăm; không có cosine thì nhãn "từ khóa". Kết quả exact có tiền tố đánh dấu khớp chính xác.
- Kết quả trang wiki: slug, type, loại tri thức, title, heading, summary.
- Kết quả văn bản gốc: tiêu đề, trang, xem trước 200 ký tự, gợi ý dùng `get_source_pages`, link `{portal_base_url}/wiki/source/{id}`.
- `total_candidates > len(ranked)` → dòng "đang hiển thị X trên tổng".
- Sau cùng là khối đồ thị và gợi ý ngoài phạm vi.

### 13.2. `search_source_content(query, limit=10, offset=0)`

- Query rỗng → lỗi.
- FTS trên `sources.full_text`, chỉ văn bản `status = ready`, cộng bộ lọc phạm vi.
- Không có kết quả → dự phòng 1: to_tsquery OR các term không phải từ dừng, dài hơn 1 ký tự.
- Vẫn không có → dự phòng 2: ILIKE trên `f_unaccent` với tối đa 3 term dài hơn 2 ký tự.
- Đoạn trích: tối đa 5 dòng mỗi văn bản, chấm theo tổng độ dài phần khớp; số trang suy từ `page_offsets`; phần khớp in đậm.

### 13.3. Gợi ý ngoài phạm vi (OOS hint)

- Chỉ khi `check_out_of_scope` bật (người dùng không phải quản trị).
- Nhóm các hit không phải global theo (scope_type, scope_id), đếm số lượng.
- **Chỉ hiển thị số lượng và tên phòng ban, không bao giờ hiện tiêu đề trang.**
- Tiêu đề khối "Out-of-scope matches", mỗi phòng ban một dòng đề nghị liên hệ quản trị viên để được cấp quyền.

---

## 14. Sinh câu hỏi tìm kiếm (`question_generator`)

### 14.1. `QuestionGenerator(llm_provider=None)`

`async generate_questions_for_chunk(text, title=None, max_questions=3) -> list[str]`

1. Text sau khi strip dưới 30 ký tự, hoặc không có provider → [].
2. Nội dung = tiêu đề (nếu có) trên một dòng, rồi text; cắt 3000 ký tự.
3. Prompt (chỉ mô tả): vai trò trợ lý pháp luật Việt Nam phục vụ công an và người dân; viết tối đa N câu hỏi bằng ngôn ngữ đời thường mà người dùng có thể hỏi về điều khoản; tập trung mức phạt, hành vi vi phạm, điều kiện, thẩm quyền, thủ tục; mỗi câu một dòng, không đánh số, không gạch đầu dòng, không lời dẫn.
4. Gọi `generate_text(prompt)` nếu provider có, không thì `complete(prompt)`.
5. Hậu xử lý từng dòng: bỏ ký tự đầu dòng là chữ số, dấu chấm, gạch ngang, dấu sao, bullet, khoảng trắng; giữ dòng ≥ 8 ký tự; dừng khi đủ max_questions.
6. Mọi exception → [].

### 14.2. `build_question_chunks(source_id, parent_chunk_index, questions, page_number=1, context_preview="") -> list[dict]`

Mỗi câu hỏi một dict: `chunk_type = "generated_question"`, `question`, `text`, `source_id`, `parent_chunk_index`, `page_number`.

`text` = nhãn `[câu_hỏi_tìm_kiếm | Trang {page_number}]: {câu hỏi}`; nếu có context_preview thì thêm một dòng trống, "Nội dung liên quan: " và preview (xuống dòng thay bằng khoảng trắng, cắt 300 ký tự). Test kiểm tra có chuỗi "câu_hỏi_tìm_kiếm" và có nội dung preview (ví dụ "Điều 5").

### 14.3. `async index_question_chunks(session, source_id, chunks, spec_id=None) -> int`

- Dùng `ProviderRegistry`, `get_spec`, `upsert_chunk_embedding` ở **cấp module** `app.services.question_generator` (test patch tại đây).
- Spec: spec_id hoặc spec đang hoạt động; không có → 0. Chunks rỗng → 0.
- `ProviderRegistry.get_embedding(task="document", spec_id=...)` rồi `embed_batch([c["text"] ...])`.
- Với chunk thứ i: gọi `upsert_chunk_embedding` bằng keyword args: chunk_index = 70000 + i, start_char = 0, end_char = len(text), page_number = chunk["page_number"] (mặc định 1), content_hash = `chunk_content_hash(text)`.
- Trả số chunk đã index.

### 14.4. Task worker `generate_questions_task(ctx, source_id, attempt_id_str=None, max_provisions=15)`

- Import **bên trong hàm**: `async_session_factory` từ `app.database`; `ProviderRegistry` từ `app.ai.registry`; `QuestionGenerator`, `build_question_chunks`, `index_question_chunks` từ `app.services.question_generator` (test patch các đường dẫn này).
- Gọi `check_task_attempt_validity` cấp module `app.worker`; không hợp lệ → `{"status": "stale"}`. Không tìm thấy source → `{"status": "not_found"}`.
- Lấy tối đa max_provisions `LegalUnit` của source; tiêu đề mỗi unit = loại unit viết hoa chữ đầu + số + title.
- Không có unit → dự phòng `build_verbatim_chunks(full_text, page_offsets)` cắt max_provisions.
- Sinh câu hỏi, dựng chunk, index.
- Trả `{"status": "success", "source_id", "questions_generated", "chunks_indexed"}`.

---

## 15. Job đổi model embedding

### 15.1. `reembed_all_pages_task(ctx, job_id)`

1. Nạp job; nếu không ở `pending`/`running` thì bỏ qua.
2. Spec không xác định hoặc khởi tạo provider lỗi → `failed` kèm `error_message`.
3. Đếm tổng trang (loại `_index`, `_log`) → `total_pages`; đặt `running`, `started_at`.
4. Xử lý theo lô 50 trang, mỗi lô một session riêng. **Trước mỗi lô** đọc lại trạng thái job: `cancelled` thì dừng ngay. Mỗi trang gọi `index_wiki_page_chunks(..., spec_id=spec mới)`. Lỗi gọi API → `failed` với "Embedding API failed: ...". Cập nhật `done_pages` sau mỗi lô.
5. Index lại chunk văn bản gốc (chunk_status ready, hoặc preserve_verbatim và ready) bằng `verbatim_service.index_source_chunks(session, src, spec_id)`; lỗi từng văn bản chỉ ghi log và tiếp tục.
6. Kiểm tra hủy lần nữa. Sau đó, trong một giao dịch: ghi `active_embedding_model_spec_id` = spec mới, chạy ba hàm cleanup (§5) giữ spec mới, đặt `completed` và `finished_at`. Việc đổi model active xảy ra **chỉ khi** toàn bộ đã xong (lật nguyên tử); trong lúc chạy, tìm kiếm vẫn dùng spec cũ.

### 15.2. `backfill_source_chunks_task(ctx, limit=500, force=False) -> {"candidates", "enqueued"}`

Ứng viên: văn bản `status` ready hoặc partial và có full_text; không force thì chỉ những văn bản có chunk_status `pending` hoặc `error`; sắp theo created_at; tối đa limit. Mỗi ứng viên được xếp hàng tác vụ chunk.

---

## 16. API quản trị embedding (`app/routers/admin_embeddings.py`)

Gắn dưới tiền tố `/api`. Mọi endpoint cần quyền `org:settings:manage`.

### 16.1. Schema

| Schema | Trường |
|---|---|
| EmbeddingSpecOut | id, provider, model_id, dimension, label, cost_per_1m_tokens, notes, api_key_configured (bool), api_key_config_key, custom (mặc định False), base_url, group (mặc định "custom") |
| EmbeddingCatalogOut | active_spec_id, specs |
| EmbeddingJobOut | id, model_spec_id, status, total_pages, done_pages, error_message, started_at, finished_at, created_at |
| EmbeddingStatusOut | active_spec_id, total_pages, embedded_pages, total_sources=0, embedded_sources=0, wiki_chunks_count=0, source_chunks_count=0, current_job, latest_job |

### 16.2. `_get_current_job(db) -> EmbeddingJob | None`

Job mới nhất (theo created_at) có trạng thái `pending` hoặc `running`; không có thì None. Hàm có tên công khai này vì `admin_custom_models` import.

### 16.3. Endpoint

| Method & path | Hành vi |
|---|---|
| GET `/settings/embeddings/catalog` | Spec catalog (api_key_configured từ khóa `embedding_api_key__<provider>`, group = provider) cộng model tùy chỉnh (custom=True, base_url). Kèm active_spec_id |
| GET `/settings/embeddings/status` | total_pages (loại `_index`, `_log`); embedded_pages = số page_id khác nhau trong bảng chunk wiki của spec đang hoạt động; total_sources; embedded_sources = số văn bản chunk_status ready; wiki_chunks_count, source_chunks_count; current_job; latest_job |
| POST `/settings/embeddings/reindex-current` | Chưa có model active → 400 "Chưa có model embedding nào được kích hoạt"; ngược lại xử lý như switch với spec đang active |
| POST `/settings/embeddings/switch` | Body `{model_spec_id}`. Spec lạ → 400. Đang có job → 409 "Another embedding job is already {status}. Cancel it before starting a new switch.". Model tùy chỉnh: phải tồn tại; provider "custom" không cần key. Model preset: thiếu key → 400 "No API key configured for provider '{p}'. Save the API key first, then switch.". Tạo job `pending`, ghi audit "switch_embedding_model", commit, xếp hàng "reembed_all_pages_task". Xếp hàng lỗi → đặt job `failed` với "Enqueue failed: …", trả 500. Thành công trả `{job_id}` |
| GET `/settings/embeddings/jobs/{id}` | EmbeddingJobOut; không có → 404 "Job not found" |
| POST `/settings/embeddings/jobs/{id}/cancel` | 404 nếu không có; không ở pending/running → 400 "Job is {status}, cannot cancel"; ngược lại đặt `cancelled`, `finished_at` |
| POST `/settings/embeddings/backfill-source-chunks?limit=500&force=false` | Trả job_id, candidates, enqueued, message. Không có ứng viên → message tiếng Việt cho biết mọi tài liệu đã có chunk thô. Có → audit "backfill_source_chunks", xếp hàng "backfill_source_chunks_task" với (limit, force) |
| POST `/settings/embeddings/probe-dimension` | Body: provider="custom", base_url, api_key, model_id. Embed chuỗi "Xin chào", trả `{dimension, supported (thuộc SUPPORTED_DIMENSIONS), latency_ms}`. Lỗi gọi → 502 "Gọi embedding thất bại: …" |
| POST `/settings/embeddings/test` | Body: model_spec_id, query, passages. Query cắt 2000; tối đa 8 passage, mỗi passage 2000. Query rỗng → 400 "Nhập câu truy vấn". Trả success, model, dimension, expected_dimension, latency_ms, similarities (cosine, 4 chữ số), preview (8 giá trị đầu, 5 chữ số), error. Thiếu key → error "Chưa có API key cho model này." |

---

## 17. API quản trị model LLM / vision (`app/routers/admin_models.py`)

Quyền `org:settings:manage`, tiền tố `/api`.

| Method & path | Hành vi |
|---|---|
| GET `/settings/llm/catalog` | active_spec_id + danh sách LLMSpecOut: id, provider, model_id, context_window_tokens, max_output_tokens, supports_tools, supports_vision, label, cost_per_1m_input_tokens, cost_per_1m_output_tokens, notes, api_key_configured, api_key_config_key, custom, base_url, protocol, group |
| POST `/settings/llm/switch` | Body `{model_spec_id}`; ghi `active_llm_model_spec_id`; audit "switch_llm_model"; trả `{active_spec_id}` |
| GET `/settings/vision/catalog` | VisionSpecOut: id, provider, model_id, max_image_size_mb, label, cost_per_1m_input_tokens, cost_per_image, notes, api_key_configured, api_key_config_key, custom, base_url, group |
| POST `/settings/vision/switch` | Ghi `active_vision_model_spec_id`; audit "switch_vision_model"; trả `{active_spec_id}` |

Quy tắc chung:

- Preset có key nếu tồn tại khóa `{kind}_api_key__{provider}`, hoặc khóa legacy `{kind}_api_key` phù hợp provider.
- Model tùy chỉnh: label rỗng thì dùng model_id.
- Spec lạ → 400. Preset thiếu key → 400 "No {provider} API key configured. Save the API key first, then switch."

---

## 18. Giao diện: thẻ cài đặt embedding

Thành phần `embedding-settings-card` trong trang Cài đặt; tiêu đề theo khóa i18n `settings.embeddingTitle`.

- Hiển thị model đang active, số trang/chunk đã embed so với tổng, số văn bản có chunk.
- Danh sách spec theo nhóm (provider / custom) kèm chiều, giá, trạng thái key.
- Nút đổi model và nút index lại model hiện tại, mỗi nút có hộp thoại xác nhận.
- Backfill chunk văn bản gốc, có công tắc "force".
- Job đang chạy: thanh tiến độ done_pages/total_pages, nút hủy.
- Khi có job pending/running hoặc đang reindex/backfill: cứ 2 giây gọi lại catalog, status và `/api/settings`.
- Phòng thử: kiểm tra kết nối (probe) và thử truy vấn/đoạn văn qua `/settings/embeddings/test`, hiện độ tương đồng và độ trễ.

---

## 19. Test và symbol phải có

| Test | Import | Hành vi kỳ vọng |
|---|---|---|
| `test_rerank_mode` | `RerankerService` | Mode off/local/remote; remote lỗi → local và không gọi lại trong 60 giây; đặt `_remote_down_until = 0` thì thử lại; `_call_remote_reranker(query, documents, text_key)` monkeypatch được |
| `test_reranker_service` | `RerankerService`, `RerankResult` | Thứ tự local đúng; remote mock qua `httpx.AsyncClient.post` giữ điểm 0.96/0.12; `ConnectError` → fallback không ném; `diversify_mmr` lambda 0.5 chọn c1 rồi c3 |
| `test_dual_pipeline_retrieval` | `Source`, `WikiPage` (`app.database.models`); `SourceChunk`, `VerbatimChunk` (bí danh của SourceChunk), `build_source_chunks`, `build_verbatim_chunks` (`app.services.verbatim_service`); `compute_source_dual_status` (`app.worker`); `merge_sequential_chunks`, `unified_search` | Chunk bảng không bị cắt giữa và lặp header; thông điệp trạng thái kép "Ready", "Raw chunks already searchable", "Raw chunks searchable", partial; ngưỡng 0.25 với floor 0.15 chỉ giữ d1; nhánh wiki ném lỗi → "wiki" trong `failed_arms`, kết quả văn bản gốc vẫn trả |
| `test_search_accuracy` | `keyword_terms`, `websearch_all`, `websearch_any`, `term_coverage`, `normalize_doc_number`, `find_doc_numbers` (`app.core.vi_tokenizer`); `wiki_service._lexical_plan`; reranker | Kế hoạch từ vựng §8.3 (ranh giới số hiệu); ghim; giữ thứ tự khi không gì qua ngưỡng; `_blend_prior` phá thế hòa |
| `test_question_generator` | `QuestionGenerator`, `build_question_chunks`, `index_question_chunks`; `app.worker.generate_questions_task` | Như §14 |
| `test_graph_expanded_search` | `LegalUnit`, `LegalRelation`, `LegalUnitType`, `LegalRelationType`, `WikiPage`; `expand_graph_neighbors`, `format_graph_neighbors_section` | Model dựng bằng keyword args; đúng 2 lần `session.execute` (units rồi relations); chuỗi định dạng §12 |
