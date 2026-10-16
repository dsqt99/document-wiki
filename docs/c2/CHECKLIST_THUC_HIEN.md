# Checklist thực hiện nhánh c2 (viết lại clean-room trên stack hiện tại)

**Mục tiêu:** giữ đủ tính năng mà `document-wiki` (Arkon + phần nhóm làm) đang có, giữ nguyên hợp đồng tích hợp với `chatbot_local`, và không còn dòng code nào của Arkon. Khi đạt được thì phát hành theo Apache 2.0.

**Stack:** Python 3.12, FastAPI, SQLAlchemy async, Alembic, arq/Redis, Postgres 16 + pgvector, MinIO, Milvus tùy chọn. Frontend: Next.js, React, Tailwind, shadcn/ui (MIT).

**Ký hiệu**

| Ký hiệu | Nghĩa |
|---|---|
| ✅ ĐÃ CHUYỂN | File loại C, đã chép sang c2 (xem `NGUON_GOC.csv`) |
| 🔌 TÁCH PHỤ THUỘC | File đã chuyển nhưng còn import module Arkon. Phải viết module nền mới có cùng giao diện thì mới chạy được |
| ✍️ VIẾT LẠI | Module Arkon (loại A/B) hoặc loại D. Viết mới từ đặc tả, **không mở code cũ** |
| 🧪 | Test đã chuyển sang, dùng làm tiêu chí nghiệm thu |

> Bộ test đã chuyển (`tests/`) ghi lại hành vi mong đợi và do nhóm tự viết. Đây là "đặc tả chạy được" mạnh nhất hiện có. Cứ viết module mới cho đến khi test tương ứng chạy xanh. Không sửa test cho khớp code.

---

## 0. Pháp lý: phải xong trước khi phát hành (không chặn việc code)

- [ ] **Hỏi Bitsness trước** về khả năng cấp lại giấy phép hoặc mua bản quyền (phương án 1). Nếu được thì không cần làm clean-room.
- [ ] Xác nhận **chủ sở hữu mã** của nhóm: hợp đồng lao động / hợp đồng dịch vụ với khách hàng quy định code thuộc về ai. Điền vào dòng `Copyright` của `NOTICE` (hiện là placeholder).
- [ ] Xác nhận người viết các file loại C không bị ràng buộc điều khoản nào với Bitsness (NDA, hợp đồng cộng tác).
- [ ] Pháp chế duyệt danh sách `docs/c2/NGUON_GOC.csv` (129 file loại C).
- [ ] Ghi nhận rằng nhóm đã đọc code Arkon. Biện pháp bù đắp: tách vai (mục 1), ghi nhật ký, kiểm tra trùng mã (mục 10).
- [ ] Riêng `chatbot_local` (fork Open WebUI): điều 4 giấy phép cấm thay thương hiệu khi có trên 50 người dùng / 30 ngày. Phải xử lý riêng.
- [ ] Rà giấy phép dependency: chạy `pip-licenses` và `license-checker`. Image AGPL/GPL (MinIO, ParadeDB nếu dùng, Neo4j) chỉ chạy nguyên bản, không sửa và không nhúng.

## 1. Thiết lập quy trình clean-room

- [x] Tạo nhánh mồ côi `c2` trong worktree riêng (`document-wiki-c2`), không mang lịch sử Arkon.
- [x] Thêm `LICENSE` (Apache 2.0), `NOTICE`, `README.md`, `.gitignore`.
- [x] Chuyển 129 file loại C, ghi nguồn gốc vào `docs/c2/NGUON_GOC.csv` (commit nguồn `f2b73f3`, có sha256).
- [x] Loại khỏi c2 các tài liệu trích code Arkon: `docs/research/weknora-comparison/*`, `docs/API.md`.
- [ ] Phân vai:
  - **Người viết đặc tả** (được đọc Arkon): viết `docs/c2/dac_ta/<mảng>.md`. Chỉ mô tả hành vi, API (method, path, trường JSON, mã lỗi), schema bảng (tên cột, kiểu, ràng buộc), luồng UI kèm ảnh chụp. **Không dán code, không dán SQL hay JSX.**
  - **Người code** (lý tưởng là chưa từng mở `app/` của Arkon): chỉ đọc đặc tả, test và file loại C.
- [ ] Tạo `docs/c2/NHAT_KY_CLEAN_ROOM.md`. Mỗi module ghi: người viết đặc tả, người code, ngày, nguồn tham khảo (đặc tả nào, tài liệu công khai nào).
- [ ] Cấu hình máy người code: không mở kho `document-wiki` trong IDE khi làm c2. Không dùng AI assistant có context là kho Arkon.
- [ ] Bật CI: pytest, ruff, `jscpd` / script trùng dòng so với snapshot Arkon (mục 10).

## 2. Nền tảng backend: viết trước, vì mọi module đã chuyển đều cần

Đây là các module mà file loại C đang import. Viết lại **đúng tên và chữ ký** dưới đây để file đã chuyển chạy được mà không phải sửa. Tên hàm, tên lớp là giao diện, không phải nội dung được bảo hộ.

### 2.1 `app/config.py` ✍️
- [ ] `settings` (pydantic-settings, đọc `.env`). Các trường mà code đã chuyển dùng:
  - **Chung:** `secret_key`, `portal_base_url`, `chatbot_url`, `chatbot_wiki_sso_secret`, `default_admin_email`, `audit_hmac_key`
  - **Chunking:** `chunk_target_tokens`, `chunk_overlap_tokens`
  - **SSO:** `sso_enabled`, `sso_issuer`, `sso_internal_issuer`, `sso_client_id`, `sso_client_secret`, `sso_scopes`, `sso_provider_name`, `sso_auto_redirect`, `sso_allow_password_login`, `sso_trust_email`, `sso_default_global_role`, `sso_role_map`, `sso_admin_role_set`, `sso_group_department_map`, `sso_sync_roles`, `sso_sync_departments`, `sso_mcp_client_set`
  - **MCP:** `mcp_trust_forwarded_identity`
  - **OCR:** `ocr_api_key`, `ocr_model`, `effective_ocr_base_url`
  - **Reranker:** `reranker_enabled`, `reranker_base_url`, `reranker_api_key`, `reranker_model`, `reranker_top_n`
  - **Milvus:** `milvus_enabled`, `milvus_host`, `milvus_port`, `milvus_user`, `milvus_password`, `milvus_database`
  - **Langfuse:** `langfuse_enabled`, `langfuse_public_key`, `langfuse_secret_key`, `effective_langfuse_host`
- [ ] Viết `.env.example` mới, liệt kê đủ biến (không chép `.env.example` cũ).

### 2.2 `app/database/__init__.py` ✍️
- [ ] `engine`, `async_session_factory`, dependency `get_db()` (async generator `AsyncSession`).

### 2.3 `app/database/models.py` ✍️
- [ ] `Base` cùng các model được import: `AppConfig`, `AuditLog`, `AuditChainHead`, `Department`, `Employee`, `EmployeeDepartment`, `KnowledgeType`, `Source`, `SourceDepartment`, `WikiPage`, `Skill`, `LegalUnit`, `LegalUnitType`, `LegalRelation`, `LegalRelationType`.
- [ ] Các model còn lại theo đặc tả: draft/review round, wiki link, prompt template, task failure, MCP token, OAuth client, notification, query log, embedding job…
- [ ] Đặc tả schema lấy từ **CSDL đang chạy** (`\d+` từng bảng), không lấy từ file model Arkon. Đặt lại thứ tự cột và tên index theo quy ước mới.
- [ ] `app/models/concept_relation.py` 🔌 và `app/models/task_failure.py` (D ✍️) gộp vào cùng gói models.

### 2.4 Alembic ✍️
- [ ] Không chép migration 001–051. Tạo **một migration baseline mới** `0001_baseline` sinh ra từ models mới.
- [ ] Viết thêm migration cho trigger chống UPDATE/DELETE trên `audit_logs`, bảng chia theo số chiều vector, index full-text tiếng Việt.
- [ ] Viết script chuyển dữ liệu từ CSDL hiện hành (dump → map cột → load). Không nâng cấp tại chỗ.

### 2.5 Dịch vụ dùng chung ✍️
- [ ] `app/services/config_service.py`: `ConfigService` (đọc/ghi `AppConfig`, cache, giải mã secret) và `vision_api_key_for(...)`.
- [ ] `app/ai/registry.py`: `ProviderRegistry` (client LLM / vision / embedding tương thích OpenAI, chọn theo cấu hình).
- [ ] `app/ai/providers/`: lớp client cho từng nhà cung cấp (được `custom_models` dùng).
- [ ] `app/ai/llm_catalog.py`, `vision_catalog.py`, `embedding_catalog.py`: `LLM_CATALOG`, `VISION_CATALOG`, `EMBEDDING_CATALOG`, `get_spec()`. Dựng danh mục mới từ tài liệu công khai của nhà cung cấp.
- [ ] `app/services/embedding_storage.py`: lưu/đọc vector theo bảng chia theo số chiều.
- [ ] `app/services/auth_service.py`: `create_access_token`, `JWT_EXPIRE_HOURS`, `require_permission(...)`, băm mật khẩu bằng argon2/bcrypt.
- [ ] `app/services/audit_service.py`: `log_audit(...)`, gọi `audit_chain` đã chuyển.
- [ ] `app/utils/text.py`: `slugify`, `parse_json_loose`.
- [ ] `app/main.py`: tạo app, CORS, middleware correlation id, health, gắn router.
- [ ] `app/worker.py` (arq): `ingest_file_task`, `generate_questions_task`, `caption_images_task`, `enqueue_post_extraction_pipeline`, `check_task_attempt_validity`, `compute_source_dual_status`.
- [ ] Dockerfile và `docker-compose.yml` mới.

**Nghiệm thu mục 2:** `python -c "import app.main"` chạy được; `pytest tests/test_audit_chain.py tests/test_chunk_budget.py tests/test_security_label.py` xanh.

---

## 3. Xác thực và SSO

| | File | Ghi chú |
|---|---|---|
| 🔌 | `app/routers/sso.py` | Cần config, database, models, auth_service. Giữ đường dẫn tích hợp chatbot |
| 🔌 | `app/services/sso_roles.py` | Ánh xạ realm role / group Keycloak |
| ✅ | `frontend/src/lib/login-round.ts`, `frontend/src/app/logout/sso/page.tsx` | |
| ✍️ | Router `auth` (login, `auth/me`, đổi mật khẩu, refresh), trang `/login`, `/login/sso` (D) | |
| ✍️ | Máy chủ OAuth 2.0 cho client MCP: dynamic client registration, authorization code + PKCE, discovery `/.well-known/oauth-authorization-server` | Viết theo RFC 6749 / 7591 / 8414 |
| 🧪 | `test_sso_role_map.py`, `test_bearer_auth.py`, `test_org_sync_accounts.py` | |

- [ ] Viết đặc tả `dac_ta/xac_thuc.md`: luồng email/mật khẩu, luồng OIDC, cờ `sso_allow_password_login`, vé SSO ký từ chatbot (HS256), cookie, đường trả về.
- [ ] Viết `auth_service` và router auth.
- [ ] Ráp `sso.py` vào, chạy test.
- [ ] Viết OAuth server cho MCP.
- [ ] Trang login và login/sso (frontend).

## 4. Phân quyền, đơn vị, nhãn mật

| | File | Ghi chú |
|---|---|---|
| 🔌 | `app/services/security_label.py` | PUBLIC < INTERNAL < RESTRICTED < CONFIDENTIAL |
| 🔌 | `app/scripts/audit_legal_scopes.py` | Cần `wiki_service` |
| ✍️ | Ma trận quyền `tài nguyên:hành động:phạm vi`, 4 vai trò, router `departments` (cây đơn vị), "phạm vi của tôi" | |
| ✍️ | `roles-permissions-card.tsx` (D), `scope-picker.tsx` (D) | |
| 🧪 | `test_security_label.py`, `test_legal_scope_enforcement.py` | |

- [ ] Đặc tả ma trận quyền: liệt kê từ bảng quyền trong CSDL đang chạy, không từ code.
- [ ] Router `departments` CRUD và cây đơn vị.
- [ ] Bộ lọc nhãn mật và phạm vi áp cho mọi truy vấn tìm kiếm, wiki, MCP.

## 5. Đồng bộ với chatbot

| | File | Ghi chú |
|---|---|---|
| 🔌 | `app/routers/org_sync.py` | `POST /internal/org-sync`, JWT HS256, chống phát lại. Cần `routers/skills` |
| ✍️ | `POST /internal/skill-sync` (trong router skills mới) | |
| 🧪 | `test_org_sync_accounts.py` | |

- [ ] Giữ **nguyên** payload mà `chatbot_local/backend/src/utils/org_sync.py` và `wiki_skill_sync.py` đang gửi/nhận. Đây là hợp đồng của nhóm, ghi lại thành đặc tả.
- [ ] Kiểm thử end-to-end với chatbot ở môi trường dev.

## 6. Nạp tài liệu và OCR

| | File | Ghi chú |
|---|---|---|
| ✅ | `app/services/parsers/` (base, pdf, docx, excel, pptx, libreoffice_converter) | Độc lập |
| ✅ | `upload_guard.py`, `upload_limit.py`, `trace_context.py` | Độc lập |
| 🔌 | `ocr_service.py`, `source_status.py`, `doc_metadata_service.py`, `chunk_budget.py` | |
| ✍️ | `routers/sources.py` (upload, url, progress, preview, file, retry, approve-extraction, plan approve/reject/regenerate, PATCH metadata, delete) | |
| ✍️ | `kb_service` (trích text, chèn marker ảnh), `image_service` (`ImageInfo`, `docx_image_blobs`), `verbatim_service` (`build_source_chunks`), lưu MinIO | |
| ✍️ | `admin_failures.py` (D), `task_failure.py` (D): dead letter | |
| ✍️ | UI `/knowledge`: bảng tài liệu, drawer bài viết (D `source-articles-drawer.tsx`), upload dialog | |
| 🧪 | `test_pdf_parser*.py`, `test_docx_parser.py`, `test_docx_image_position.py`, `test_excel_parser.py`, `test_pptx_parser.py`, `test_libreoffice_converter.py`, `test_upload_guard.py`, `test_upload_dedup.py`, `test_ingest_formats.py`, `test_ocr_*.py`, `test_config_service_ocr.py`, `test_source_status*.py`, `test_source_retry.py`, `test_worker_*.py`, `test_dead_letter_and_timings.py`, `test_doc_metadata_service.py` | |

- [ ] Đặc tả hai nhánh xử lý A (chunk + embed) và B (biên soạn wiki): trạng thái, chuyển trạng thái, cổng duyệt.
- [ ] Router sources và worker ingest.
- [ ] Băm nội dung chống trùng, `attempt_id` chống chạy trùng.
- [ ] OCR qua endpoint vision (GLM-OCR), cấu hình trong CSDL.

## 7. Tiếng Việt, chunking và truy hồi

| | File | Ghi chú |
|---|---|---|
| ✅ | `app/core/vi_tokenizer.py`, `app/core/text_normalizer.py`, `app/services/search_fusion.py` | Độc lập |
| 🔌 | `retrieval_service.py`, `reranker_service.py`, `milvus_service.py` | |
| ✍️ | Migration hybrid search (D `037_hybrid_search` → viết lại trong baseline), job đổi mô hình embedding (`admin_embeddings`) | |
| ✍️ | Sinh câu hỏi giả định (`question_generator.py` là D) | |
| 🧪 | `test_vi_tokenizer.py`, `test_text_normalizer.py`, `test_rerank_mode.py`, `test_reranker_service.py`, `test_dual_pipeline_retrieval.py`, `test_search_accuracy.py`, `test_question_generator.py` | |

- [ ] Hybrid vector + full-text, RRF, ngưỡng, gộp chunk liền kề, rerank, MMR.
- [ ] Gợi ý "có kết quả ở đơn vị bạn không được xem".

## 8. Pháp lý và wiki

| | File | Ghi chú |
|---|---|---|
| ✅ | `legal_hierarchy_parser.py`, `citation_verifier.py`, `wiki_write_guard.py`, `app/ai/mrp/synthesizer.py` | Độc lập |
| 🔌 | `legal_service.py` (6 phụ thuộc), `legal_relation_extractor.py`, `legal_route_service.py`, `wiki_chunk_service.py`, `app/models/concept_relation.py` | |
| ✅ | `frontend/src/lib/legal-doc.ts`, `frontend/src/types/legal-doc.ts`, `frontend/src/lib/wiki-store.ts`, `frontend/src/app/(portal)/wiki/law/page.tsx` | |
| ✍️ | `wiki_service` (CRUD, `resolve_wiki_scopes`, `regenerate_index`, lập kế hoạch), pipeline biên soạn map → reduce → plan → refine → verify → commit: gói `app/ai/mrp/` (`mapper`, `reducer`, `merger` với `merge_page_content` / `APPEND_FALLBACK_HEADING`, `writer` với `_pass_drops_rows`, `verifier`, `pipeline`; chỉ `synthesizer.py` là ✅) | Đủ thì 9 test còn lại của `test_wiki_write_guard.py` mới chạy |
| ✍️ | Bản nháp và duyệt: vòng duyệt, AI duyệt trước, duyệt / từ chối / yêu cầu sửa / rút, duyệt hàng loạt; `wiki_draft_publish.py` (D) | |
| ✍️ | Wikilink, backlink, đồ thị, trang mồ côi, lint, trang "hot", nhật ký | |
| ✍️ | Router `legal_docs.py` (D), trang `/wiki/law/[key]` (D), `wiki-facets.tsx` (D), `formatted-inline-text.tsx` (D) | |
| ✍️ | `app/routers/wiki.py` (pages CRUD, status, index, my-scopes, graph, hot, lint, orphaned) | `test_graph_api.py` cần |
| ✍️ | Trang `/wiki`, `/wiki/[...slug]`, `/wiki/graph`, `/wiki/review` | |
| 🧪 | `test_legal_*.py` (8 file), `test_exact_legal_route.py`, `test_citation_verifier.py`, `test_wiki_write_guard.py`, `test_wiki_draft_publish.py`, `test_concept_relations.py`, `test_graph_api.py`, `test_graph_expanded_search.py` | |

- [ ] Đặc tả hiệu lực văn bản (còn / chưa / bị thay thế / hết) và quan hệ (sửa đổi, bổ sung, thay thế, bãi bỏ, hướng dẫn, căn cứ, dẫn chiếu).
- [ ] Chế độ nguyên văn cho văn bản pháp luật, đánh chỉ mục theo trang.
- [ ] Nhánh / gộp / rebase bản nháp: có thể để giai đoạn sau.

## 9. Bảng tính, MCP, skill, prompt, quản trị, kiểm toán

### 9.1 Bảng tính
- [x] ✅ `table_query_service.py` (DuckDB, chỉ đọc). 🧪 `test_table_query.py`.

### 9.2 MCP ✍️
- [ ] `app/services/mcp_auth_service.py`: xác thực token MCP (được `security_label` dùng khi lọc theo danh tính).
- [ ] `app/mcp/tools.py`: `register_tools`, `forwarded_role`, FastMCP streamable HTTP tại `/mcp`.
- [ ] Giữ **tên và tham số của 18 tool** để chatbot và skill không phải sửa: `search_wiki`, `read_wiki_index`, `read_wiki_page`, `list_wiki_pages`, `get_document_relations`, `get_source`, `get_source_outline`, `get_source_page`, …
- [ ] Viết thân từng tool từ đặc tả.
- [ ] Xác thực bằng token cá nhân hoặc access token Keycloak; lọc tool theo danh tính; ghi log truy vấn, đưa truy vấn 0 kết quả vào báo cáo lỗ hổng.
- 🧪 `test_mcp_scope.py`, `test_mcp_forwarded_identity.py`.

### 9.3 Skill và prompt
- [x] ✅ `skills/cahy-kn1..kn7`
- [ ] ✍️ Router skills: upload ZIP, phiên bản, phạm vi đơn vị, đóng góp và duyệt, `_read_skill_files`, `_split_skill_md`.
- [ ] ✍️ `skill-form-dialog.tsx` (D).
- [ ] ✍️ Router `prompts` (D), trang `/prompts` (D), `prompt-form-dialog.tsx` (D).

### 9.4 Mô hình và cấu hình
- [ ] 🔌 `app/ai/custom_models.py`, `app/routers/admin_custom_models.py` (6 phụ thuộc), `app/ai/tracing.py`.
- [x] ✅ `custom-model-form.tsx`, `document-processing-settings-card.tsx`, `ocr-settings-card.tsx`.
- [ ] ✍️ `admin_settings` (settings, providers, test-*), `test-lab.tsx` (D), `provider-model-picker.tsx` (D), `model-catalog-card.tsx`.
- 🧪 `test_custom_models.py`, `test_admin_settings_preview_api.py`.

### 9.5 Thống kê và thông báo ✍️
- [ ] `dashboard/stats`, `admin/stats/*` (nội dung, đóng góp, sử dụng, lỗ hổng tri thức, xuất CSV).
- [ ] Thông báo trong ứng dụng.

### 9.6 Kiểm toán
- [ ] 🔌 `audit_chain.py` (chuỗi băm HMAC, đầu chuỗi có chữ ký).
- [ ] ✍️ Trigger chặn UPDATE/DELETE (thay cho migration 049 là D).
- 🧪 `test_audit_chain.py`.

## 10. Frontend nền

| | File | Ghi chú |
|---|---|---|
| ✅ | `frontend/src/lib/i18n.tsx` (từ điển vi/en), `theme.tsx`, `embed.ts`, `components/shared/library-list.tsx` | |
| ✍️ | `package.json`, `next.config`, Tailwind, `layout.tsx`, `(portal)/layout`, sidebar, header | |
| ✍️ | `components/ui/*`: **sinh mới bằng `npx shadcn@latest add button input label switch dropdown-menu dialog table …`** (MIT). Không chép thư mục `components/ui` của Arkon | |
| ✍️ | `lib/api.ts` (client fetch + JWT), `lib/utils.ts` (`cn`), `lib/wiki.ts`, `empty-state.tsx` | |
| ✍️ | Toàn bộ trang và component loại A/B/D còn lại | |

- [ ] Đặc tả UI = ảnh chụp từng màn và mô tả tương tác. Không dùng `DESIGN.md`, CSS hay asset của Arkon.
- [ ] Chọn bảng màu, font, logo mới của CAHY.
- [ ] Rà `i18n.tsx`: bỏ chuỗi nhắc tên Arkon (`dash.mcpDesc`, `profile.mcpTokenDesc`).

## 11. Đổi thương hiệu Arkon → tên mới

Các định danh dưới đây là giao diện với hệ thống đang chạy. Đổi tên phải kèm thời gian chuyển tiếp: chấp nhận cả tên cũ lẫn tên mới.

| Vị trí | Định danh hiện tại | Ảnh hưởng khi đổi |
|---|---|---|
| `app/routers/sso.py` | cookie `arkon_sso_tx`, `arkon_sso_idt`; audience `arkon-sso-tx` | Phiên SSO đang mở bị mất (chấp nhận được) |
| `app/routers/sso.py` | `CHATBOT_RETURN_PATH = /api/v1/arkon/sso/return` | **Phải đổi đồng thời** route bên `chatbot_local` (`routers/arkon.py`) |
| `frontend/src/app/logout/sso/page.tsx` | localStorage `arkon_sso` | Không đáng kể |
| `app/services/audit_chain.py` | `GENESIS_HASH_ARKON_WIKI_CHAIN_…` | **Không đổi** với chuỗi đã có dữ liệu. Chỉ đổi khi khởi tạo CSDL mới |
| `app/services/milvus_service.py` | collection `arkon_wiki_pages_{dim}`… | Phải re-index hoặc đổi alias |
| `skills/*/SKILL.md` | `mcp__arkon__*` (tên server MCP) | Đổi tên server MCP bên chatbot và skill cùng lúc |
| `app/ai/tracing.py`, `i18n.tsx`, test | chữ "Arkon" trong docstring/chuỗi | Đổi tự do |

- [ ] Chọn tên sản phẩm mới.
- [ ] Đổi theo bảng trên.
- [ ] Cuối cùng: `git grep -i arkon` không còn kết quả, ngoài `NOTICE` và tài liệu lịch sử.

## 12. Kiểm tra trùng mã và phát hành

- [ ] Script so trùng dòng có nghĩa (≥25 ký tự, không phải import hay chú thích) giữa c2 và snapshot Arkon `274a2d2` + `upstream/main`. Ngưỡng: mỗi file dưới 10%. Dòng trùng còn lại phải là boilerplate (import framework, khai báo kiểu thông dụng) và phải giải trình trong nhật ký.
- [ ] Chạy `jscpd --min-tokens 50` chéo hai kho. Không còn khối trùng nào ngoài boilerplate.
- [ ] Rà thủ công các file loại C có tỷ lệ trùng 5–10%:
  - `custom-model-form.tsx` (10%)
  - `admin_custom_models.py`, `wiki/law/page.tsx`, `ocr-settings-card.tsx`, `library-list.tsx`, `concept_relation.py` (8–9%)
  - `audit_legal_scopes.py`, `retrieval_service.py`, `wiki_chunk_service.py` (7%)
  - `document-processing-settings-card.tsx` (6%)
- [ ] Thêm header SPDX `# SPDX-License-Identifier: Apache-2.0` vào mọi file nguồn.
- [ ] Hoàn tất mục 0 (pháp lý), điền chủ sở hữu vào `NOTICE`.
- [ ] Toàn bộ test xanh. Chạy end-to-end với `chatbot_local` (SSO, org-sync, skill-sync, proxy `routers/arkon.py`, MCP).
- [ ] Chuyển dữ liệu thử từ CSDL hiện hành sang schema mới. So số lượng bản ghi.

---

## Thứ tự đề xuất

1. Mục 2: nền backend (khoảng 1–2 tuần). Mở khóa phần lớn file 🔌.
2. Mục 3, 4, 5: xác thực, phân quyền, đồng bộ chatbot. Đây là điều kiện để tích hợp.
3. Mục 6, 7: nạp tài liệu và truy hồi.
4. Mục 9.2: MCP. Chatbot dùng được từ đây.
5. Mục 8: wiki và pháp lý (khối lớn nhất).
6. Mục 9.3–9.6, 10: phần còn lại và frontend.
7. Mục 11, 12: đổi thương hiệu, kiểm tra trùng mã, phát hành.

## Trạng thái test lúc tạo nhánh

Xem mục "Kết quả chạy thử" trong `README.md`. Mỗi lần viết xong một module nền, chạy lại `pytest` và cập nhật bảng đó.
