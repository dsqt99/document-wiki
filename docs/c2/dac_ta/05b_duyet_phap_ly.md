# 05b — Wiki: bản nháp, duyệt, AI tiền duyệt, nhánh đóng góp, API wiki và pháp lý

Phần 05b tiếp nối `05a_wiki_bien_soan.md`. Lược đồ bảng ở 05a §2. Tài liệu chỉ có văn xuôi và bảng, không có code, regex hay prompt nguyên văn.

---

## 1. Vòng đời bản nháp và revision (`wiki_service`)

### 1.1. Ngoại lệ

| Lớp | Thuộc tính | Thông điệp (nội dung) |
|---|---|---|
| `DraftConflictError(current_version, base_version)` | current_version, base_version | Bản nháp dựa trên v{base}, trang đã lên v{current}; cần re-base |
| `CreateDraftSlugConflict(slug, scope_type, scope_id)` | slug, scope_type, scope_id | Slug '{slug}' đã tồn tại trong {scope_type} (hoặc "scope_type:scope_id"); gợi ý đổi final_slug hoặc sửa trang có sẵn |

### 1.2. Hàm

**`create_draft(session, page_id, author_id, content_md, note=None, source="web_ui", source_metadata=None, base_version=None, draft_kind="edit", suggested_metadata=None) -> WikiPageDraft`**: tạo bản nháp `pending`, `session.add`, flush. Không commit.

**`approve_draft(session, draft, reviewer_id, reviewer_note=None, edited_content_md=None, allow_conflict=False, metadata_overrides=None) -> WikiPage`**:
1. Nội dung cuối = `edited_content_md` đã cắt khoảng trắng (nếu có), ngược lại nội dung bản nháp.
2. Khóa advisory theo băm slug đích (create: slug trong suggested_metadata; edit: slug trang). Với edit, nạp lại trang sau khi có khóa để có version mới nhất.
3. Bản nháp `create`: slug / title / page_type / knowledge_type_slugs lấy theo thứ tự ưu tiên `metadata_overrides` (khóa `final_slug`, `final_title`, `final_page_type`, `final_knowledge_type_slugs`) rồi `suggested_metadata`. page_type mặc định `concept`; phạm vi lấy từ suggested_metadata (scope_id là chuỗi UUID; không hợp lệ thì coi như null). Slug rỗng hoặc dành riêng → ValueError "Invalid slug for new page: '…'"; title rỗng → ValueError "Title is required to materialise a new page". Slug đã có trong phạm vi → `CreateDraftSlugConflict`. Tạo trang bằng `apply_create` (summary rỗng, source_ids rỗng); thêm revision `draft_approved_create` (version của trang, draft_id, changed_by = reviewer, change_note = reviewer_note); gán `draft.page_id`.
4. Bản nháp `edit`: không tìm thấy trang → ValueError "Wiki page {id} not found". Xung đột khi: `allow_conflict` false, không có `edited_content_md`, base_version và version đều khác null, base_version < version → `DraftConflictError`. Ngược lại: gán nội dung, version +1, flush, `refresh_links`, thêm revision `draft_approved`.
5. Bản nháp: status `approved`, reviewed_by_id, reviewed_at (UTC), reviewer_note. Flush, trả trang.

**`reject_draft(session, draft, reviewer_id, reviewer_note) -> WikiPageDraft`**: status `rejected`, cùng các trường người duyệt.

**`direct_edit_page(session, page, editor_id, content_md, change_note=None) -> WikiPage`**: gán nội dung, version +1, `refresh_links`, revision `editor_edit`.

**`rollback_to_revision(session, page, target_version, actor_id) -> WikiPage`**: tìm revision (page_id, target_version); không có → ValueError "Revision v{N} not found for page {slug}". Chép nội dung revision sang trang, version +1, `refresh_links`, revision `rollback` với change_note "rollback to v{N}".

### 1.3. Xuất bản ngay (`app/services/wiki_draft_publish.py`)

Bước duyệt đang bị tắt với đề xuất trực tiếp (web và MCP): đề xuất vẫn lưu thành bản nháp để giữ lịch sử, nhưng được chính tác giả duyệt trong cùng transaction.

**`publish_draft(session, draft, author) -> WikiPage`** (`test_wiki_draft_publish`):
1. Gọi `wiki_service.approve_draft(session, draft, author.id, reviewer_note=<ghi chú tiếng Việt "tự động áp dụng, không cần duyệt">)`. Tham số vị trí thứ 3 phải là `author.id`. Lỗi (`DraftConflictError`, `CreateDraftSlugConflict`, `ValueError`) được ném tiếp; nơi gọi rollback.
2. Phạm vi = `page.scope_type` hoặc `global`, `page.scope_id`. Gọi `wiki_service.regenerate_index(session, scope_type=…, scope_id=…)`; ví dụ trang có scope_type None thì gọi với `scope_type="global", scope_id=None`.
3. `wiki_service.append_log(session, "<Created|Updated> page: <title> (<slug>) → v<version> by <name hoặc email>", scope_type=, scope_id=)`. "Created" khi draft_kind là create. Chuỗi phải chứa "v<version>".
4. Gán `draft.page = page`.
5. `index_wiki_page_chunks(session, page)`; lỗi chỉ ghi cảnh báo.
6. Trả trang. Không commit.

Hàm phải gọi `approve_draft`, `regenerate_index`, `append_log` qua module `wiki_service`, và `index_wiki_page_chunks` qua tên được import vào module `wiki_draft_publish` (test thay thế ở đó).

---

## 2. Dịch vụ đóng góp (`app/services/contribution_service.py`)

Dịch vụ dùng chung cho bản nháp wiki và đóng góp kỹ năng (phần kỹ năng thuộc đặc tả MCP/kỹ năng).

### 2.1. Máy trạng thái

| Từ | Hành động | Đến | Ai |
|---|---|---|---|
| (mới) | nộp | pending | tác giả |
| pending | request_changes | needs_revision | người duyệt; bắt buộc có ghi chú |
| needs_revision | resubmit | pending | chỉ tác giả gốc |
| pending, needs_revision | withdraw | withdrawn (kết thúc) | tác giả gốc hoặc admin |
| pending | approve / reject (qua `wiki_service`) | approved / rejected | người duyệt |

Sai trạng thái → `InvalidTransition` với thông điệp "Cannot perform this action while {loại} is in status '{s}'. Allowed: …".

### 2.2. Symbol

| Symbol | Hành vi |
|---|---|
| `InvalidTransition` | Exception |
| `wiki_draft_adapter`, `skill_contribution_adapter` | Adapter cho từng loại; `artifact_type` lần lượt là `wiki_draft`, `skill_contribution` |
| `_enqueue_ai_review(db, draft)` | Router nhánh dùng. Không bao giờ ném lỗi. Cấu hình `ai_pre_review_enabled` (ConfigService) bằng chuỗi "false" → `ai_check_status = skipped`, dừng. Ngược lại: `queued`, xóa kết quả cũ, enqueue `ai_pre_review_draft_task(str(draft.id), revision_round)`; enqueue lỗi → `skipped` |
| `notify_submitted(db, adapter, obj, actor)` | Với bản nháp wiki: enqueue AI tiền duyệt. Gửi thông báo "New draft: …" tới người duyệt |
| `request_changes(db, adapter, obj, reviewer, note)` | Ghi chú rỗng → InvalidTransition "reviewer_note is required when requesting changes."; yêu cầu pending; đặt needs_revision và `last_returned_note`; audit `request_changes`; thông báo tác giả |
| `resubmit_wiki_draft(db, draft, author, new_content_md, author_note=None)` | Yêu cầu needs_revision; khác tác giả → InvalidTransition "Only the original author can resubmit this draft."; thêm hàng `wiki_draft_rounds` chụp lại vòng hiện tại (round_no = revision_round hiện tại, nội dung, note, lời trả lại, kết quả AI); thay nội dung, note (nếu truyền); xóa lời trả lại; AI về pending (xóa kết quả, thời điểm); tăng revision_round; status pending; enqueue AI; audit `resubmit` ("round N"); thông báo người duyệt |
| `withdraw(db, adapter, obj, author)` | Yêu cầu pending/needs_revision; khác tác giả và không phải admin → InvalidTransition "Only the original author can withdraw this contribution."; status withdrawn; audit; thông báo người duyệt |
| `notify_approved(db, adapter, obj, reviewer, version_label=None)` | Thông báo tác giả (tiêu đề kèm "(vN)" nếu có nhãn); với bản nháp wiki còn báo một lần cho mỗi tác giả khác đang có bản nháp pending cùng trang rằng trang đã tiến lên |
| `notify_rejected(db, adapter, obj, reviewer, reason=None)` | Thông báo tác giả kèm lý do |

Người nhận "người duyệt": bản nháp có trang → người duyệt của phạm vi trang; không có trang → người duyệt global (hàm của `notification_service`). Tên hiển thị bản nháp: "title (slug)" hoặc "draft {id}".

---

## 3. AI tiền duyệt (gói `app/services/ai_review/`)

Chế độ cho phép: không lớp nào chặn việc nộp; "fail" chỉ là cờ cho người duyệt xem.

### 3.1. Định dạng kết quả

`ai_check_results` = `{version: 1, summary: {pass, warn, fail, skipped}, checks: [...]}`. Mỗi check: `id`, `layer` (L1–L4), `severity` (`block` | `warn`), `status` (`pass` | `warn` | `fail` | `skipped`), `message` (hoặc null), `matches` (danh sách), cộng các trường riêng.

Symbol trong `runner.py` (gói export lại): `CheckResult` (dataclass id, layer, severity, status, message=None, matches=[], extra={}; `to_dict()` gộp `extra` vào cấp ngoài), `AiReviewResults` (bí danh dict), `run_sync_checks(db, content_md, self_slug=None, self_page_id=None, scope_type="global", scope_id=None)` (chỉ L1+L2), `run_async_checks(draft_id, expected_round=None)`, `merge_results(base, extra_checks)` (thay check trùng id, thêm check mới, tính lại summary).

### 3.2. L1 — mẫu nhạy cảm (`regex_checks.run(content_md)`)

Mỗi mẫu một check, theo thứ tự cố định:

| id | Nhãn | Mô tả mẫu |
|---|---|---|
| pii.email | Email address | dạng địa chỉ email |
| pii.phone_vn | Vietnamese phone number | 0 hoặc +84 rồi 9–10 chữ số, có ranh giới từ |
| pii.cccd_vn | 12-digit national ID | đúng 12 chữ số liền, không dính chữ số khác |
| secret.api_key_sk | API key (sk-...) | "sk-" + ≥ 20 ký tự chữ-số |
| secret.anthropic | Anthropic key | "sk-ant-" + ≥ 20 ký tự chữ-số, gạch dưới, gạch ngang |
| secret.aws_access | AWS access key | "AKIA" + 16 chữ hoa hoặc số |
| secret.github_pat | GitHub PAT | "ghp_" + 36 ký tự chữ-số |
| secret.google_api | Google API key | "AIza" + 35 ký tự chữ-số, gạch dưới, gạch ngang |
| secret.jwt | JWT | ba đoạn base64url ngăn bằng dấu chấm, hai đoạn đầu bắt đầu "eyJ" |
| secret.private_key | Private key block | dòng mở đầu khối khóa riêng (RSA / EC / OPENSSH hoặc không) |

- Có khớp: `pii.*` → status `warn`, severity `warn`; `secret.*` → status `fail`, severity `block`. Thông điệp nêu số lần và nhãn. `matches`: tối đa 10 phần tử `{line (đếm từ 1), snippet đã che}`. Có trường `suppressed` (số khớp bị bỏ qua).
- Không khớp: `pass`; thông điệp "N suppressed by pii-allow marker" nếu có khớp bị bỏ qua, ngược lại null.
- Đánh dấu cho phép: comment HTML có dạng "pii-allow: lý do"; áp dụng cho chính dòng đó và dòng đầu tiên không trống, không phải đánh dấu, trong 3 dòng kế tiếp.

### 3.3. L2 — cấu trúc (`structural_checks.run(db, content_md, self_slug=None, scope_type, scope_id)`)

Mọi check severity `warn`:

| id | Điều kiện warn | Thông điệp |
|---|---|---|
| links.broken | wikilink tới slug không tồn tại ở bất kỳ phạm vi nào (trừ chính nó) | "N wikilink target(s) do not exist in any scope"; matches tối đa 20 |
| links.self | có wikilink tới `self_slug` | "Page links back to itself" |
| length.sanity | < 100 ký tự / > 45 000 ký tự | "Content is unusually short (N chars)" / "Content is approaching the 50KB hard cap (N chars)" |
| markdown.heading_jump | cấp heading nhảy hơn 1 (ví dụ H1 → H3) | "Heading levels jump non-incrementally: …" (liệt kê 5 cặp đầu), matches tối đa 10 |
| markdown.unclosed_fence | số dòng rào code ở đầu dòng là lẻ | "Code fence appears to be unclosed" |

### 3.4. L3 — trùng lặp (`semantic_checks.run(db, content_md, self_page_id, scope_type, scope_id, draft_kind)`)

Check `semantic.duplicate`. Bản nháp edit → `skipped` ("chỉ chạy cho đề xuất trang mới"). Bản nháp create: embed 4 000 ký tự đầu (task `document`; lỗi → skipped "Embedding lookup failed: …"); `search_pages_semantic` top 6 trong phạm vi; bỏ trang của chính nó; giữ trang có sim ≥ 0,85 → `warn` "N existing page(s) look similar — consider editing instead of creating", matches tối đa 5 phần tử `{slug, title, score làm tròn 3 chữ số}`; không có → `pass`.

### 3.5. L4 — LLM (`llm_checks.run(db, content_md, title, page_type)`)

- Ý đồ prompt: đánh giá giọng văn (nhất quán, phù hợp wiki nội bộ), các nhận định cần kiểm chứng, và mức phù hợp với page_type. Đầu vào: title, page_type, 8 000 ký tự đầu nội dung. Đầu ra: JSON với `tone_consistent` (bool), `tone_notes`, `factual_concerns` (danh sách chuỗi), `scope_fit` (bool), `scope_notes`. max_tokens 400, nhiệt độ 0.
- Không lấy được LLM / gọi lỗi / không parse được → một check `llm.judgment` status `skipped`, thông điệp lần lượt "LLM provider unavailable: …", "LLM call failed: …", "LLM returned unparseable response".
- Thành công → ba check (severity warn): `llm.tone` (warn khi tone_consistent false, "Tone may be off: …"; pass kèm ghi chú), `llm.scope_fit` (warn "Content may not fit page_type='X'"), `llm.factual` (warn "N claim(s) flagged for verification", matches = 5 mối lo đầu). Trường thiếu mặc định là true / rỗng.

### 3.6. Runner và worker

**`run_async_checks(draft_id, expected_round=None)`** — tự mở session:
1. id không hợp lệ, không tìm thấy bản nháp, hoặc bản nháp không pending → dừng.
2. Đặt `running`, commit.
3. Ngữ cảnh: slug, phạm vi, title, page_type lấy từ trang; bản nháp create lấy từ suggested_metadata (scope_id null).
4. Chạy L1+L2; lỗi → thêm check `runner.l12_error` (L2, skipped). Chạy L3+L4; lỗi → thêm `runner.error` (L4, skipped).
5. Nếu có `expected_round`: nạp lại revision_round và status; round khác hoặc không còn pending → bỏ kết quả (không ghi).
6. Ghi đè kết quả; status: có fail → `failed`; có warn → `warned`; còn lại → `passed`; `ai_checked_at` = bây giờ. Commit.

Worker: `ai_pre_review_draft_task(ctx, draft_id, expected_round=None)` gọi `run_async_checks`. Cron `sweep_stuck_ai_review_cron`: bản nháp ở `running` lâu hơn max(2 × `worker_job_timeout`, 1 800 giây) (theo updated_at, hoặc updated_at null) → `skipped`.

---

## 4. Quyền dùng chung trong các router wiki

| Hàm | Quy tắc |
|---|---|
| `_build_wiki_scope_filter(user)` (router `wiki`, legal_docs import) | admin → None; mức `wiki:read` = `all` → None; `own_dept` → trang global HOẶC trang department có scope_id thuộc `user.department_ids` (không có phòng ban → không thấy trang department); mức khác → bộ lọc rỗng |
| `_page_read_filter(user)` | AND của các mệnh đề khác None trong {bộ lọc phạm vi, `page_source_read_clause(user)`}; cả hai None → None. Với admin phải trả None mà không truy vấn DB |
| `page_source_read_clause(user)` | (file loại C về quyền nguồn) ẩn trang xây từ tài liệu người dùng không đọc được |
| `_can_propose(user, page)` | admin → có; trang department có scope_id → `wiki:write:all`, hoặc `wiki:write:own_dept` khi phòng ban của trang thuộc `user.department_ids`; còn lại → có bất kỳ quyền `wiki:write:*` |
| `_can_review(user)` | admin hoặc `wiki:write:all` |
| `_can_review_draft(user, draft)` | create → `_can_review`; edit → trang phải tồn tại (không có thì chỉ admin), phải đọc được qua `page_source_read_clause`, và qua `_can_review` |

Quy tắc tra trang theo slug ở các endpoint (gọi là "tra trang chuẩn"): có `scope_type` → `get_page_by_slug(phạm vi, page_filter = page_source_read_clause)`; không có → thử global, rồi `get_page_by_slug_any_scope`. Không thấy → 404 "Wiki page not found: {slug}".

Thứ tự đăng ký router dưới tiền tố `/api`: wiki_branches, wiki_drafts, legal_docs, wiki, wiki_images. Đường dẫn có hậu tố (`/drafts`, `/revisions`, `/status`) phải được khớp trước đường dẫn chung `/wiki/pages/{slug:path}`.

---

## 5. Router `wiki` (`app/routers/wiki.py`)

### 5.1. Mô hình

- **WikiPageSummary**: slug, title, page_type, status (mặc định seed), summary (chuỗi, rỗng nếu null), knowledge_type_slugs, source_ids, scope_type (mặc định global), scope_id, scope_name (tên phòng ban hoặc null), version (mặc định 1), updated_at (ISO hoặc "").
- **WikiPageDetail**: Summary + content_md, backlinks (sắp xếp), outlinks (sắp xếp), orphaned.
- **WikiScope**: scope_type, scope_id, name.
- **WikiDirectEditRequest**: content_md (không rỗng: "content_md must not be empty"), change_note.
- **WikiDirectCreateRequest**: slug (cắt; rỗng hoặc dành riêng → "slug must be non-empty and not reserved"; có khoảng trắng → "slug must not contain whitespace"), title, page_type = concept (thuộc PAGE_TYPES, lỗi "page_type must be one of [...]"), knowledge_type_slugs = [], scope_type = global (global|department, lỗi "scope_type must be global or department"), scope_id, content_md (không rỗng; ≤ 50 000: "content_md exceeds 50,000 character limit"), summary = "".
- **WikiRevisionSummary**: id, version, change_type, changed_by_name, change_note, created_at.

Lỗi validate trả 422.

### 5.2. Endpoint

| Method, đường dẫn | Quyền | Hành vi, lỗi |
|---|---|---|
| GET `/wiki/pages?page_type&knowledge_type_slug&source_id&scope_type&scope_id&limit(1–50000)&offset` | wiki:read | Trả [Summary]. Bỏ trang dành riêng; sắp updated_at giảm dần; áp `_page_read_filter`; scope_type global → scope_id null, khác → scope_id bằng; lọc page_type, loại tri thức (chứa), source_id (chứa); kèm scope_name |
| GET `/wiki/search?q(1–500)&limit=30(1–100)` | wiki:read | Embed q (4 000 ký tự, task search_query); lỗi → 503 "Embedding model is not available". `search_pages_hybrid(top_k = 3 × limit, all_scopes = bộ lọc phạm vi là None, department_ids, clearance, page_filter = page_source_read_clause)`; lọc lại bằng `_page_read_filter`; giữ thứ tự hit; cắt limit |
| GET `/wiki/pages/{slug}?scope_type&scope_id` | wiki:read | Tra trang chuẩn. Không phải admin và trang vượt nhãn mật (`page_label_clause`) → 404 như trên. Trang department của phòng khác, không có wiki:read:all → 403 "Access denied — this page belongs to another department". Trả Detail |
| GET `/wiki/index?scope_type&scope_id` | wiki:read | Kiểm tra phòng ban (403). Có bộ lọc nguồn cho người dùng → `render_scoped_index(all_scopes=True, page_filter = bộ lọc phạm vi chính xác AND bộ lọc nguồn)`; ngược lại nội dung `_index` đã lưu hoặc "". Trả `{content_md}` |
| GET `/wiki/my-scopes` | đăng nhập | [{global, null, "Global"}] + các phòng ban người dùng thuộc, sắp theo tên |
| GET `/wiki/log` | wiki:read | `{content_md}` của `_log` global hoặc "" |
| POST `/wiki/pages` (201) | đăng nhập | Không phải admin, thiếu wiki:write:all → 403 "Requires wiki:write:all permission to create global/department wiki pages". Slug có trong phạm vi → 409 "Slug '{slug}' already exists in {scope_type}. Edit the existing page instead.". `apply_create`; audit create "direct create: slug"; regenerate_index; log "Created page: T (slug) by X"; index chunk (lỗi chỉ cảnh báo); commit; trả Detail |
| PATCH `/wiki/pages/{slug}/status?scope_type&scope_id` body {status} | đăng nhập | status ngoài 4 giá trị → 400 "Invalid status. Must be one of: …"; trang dành riêng → 400 "Cannot update status of reserved pages"; tra trang chuẩn (404); thiếu wiki:write:all (không phải admin) → 403 "Requires wiki:write:all permission". Trả {slug, status} |
| PUT `/wiki/pages/{slug}?scope_type&scope_id` | đăng nhập | Trang dành riêng → 400 "Cannot directly edit reserved pages"; tra trang chuẩn; thiếu wiki:write:all → 403 "Requires wiki:write:all permission to directly edit global/department wiki pages". `direct_edit_page`; audit update "direct edit: slug"; regenerate_index; log "Edited page: T (slug) → vN by X"; index chunk; commit; Detail |
| GET `/wiki/pages/{slug}/revisions?limit=20(1–100)` | wiki:read | `get_page_by_slug_any_scope(page_filter = _page_read_filter)`; 404; sắp version giảm dần; kèm tên người sửa |
| POST `/wiki/pages/{slug}/revisions/{version}/rollback` | admin | Không phải admin → 403 "Only admins can rollback wiki pages"; 404 trang; ValueError → 404; audit "rollback to vN: slug"; index chunk; commit; Detail. Không dựng lại mục lục |
| GET `/wiki/orphaned` | admin | 403 "Only admins can view orphaned pages"; trang có orphaned = true |
| DELETE `/wiki/pages/{slug}?scope_type&scope_id` | wiki:delete | Trang dành riêng → 400 "Cannot delete reserved pages"; tra trang (404); vai trò không phải admin/super_admin → 403 "Only admins can delete wiki pages". Audit delete; `delete_page_cascade`; regenerate_index phạm vi trang; log global "Deleted page: T (slug)"; commit; `{ok: true, deleted_slug}` |
| GET `/wiki/graph` | wiki:read | §5.3 |
| GET `/wiki/lint?scope_type&scope_id` | wiki:read | Trang department của phòng khác (không phải admin, không wiki:read:all) → 403 "Access denied — this belongs to another department". Trả `lint_wiki` |
| GET `/wiki/hot?scope_type&scope_id` | wiki:read | Cùng kiểm tra 403. Trả `{content_md}` của `_hot`, hoặc câu giữ chỗ tiếng Việt (in nghiêng) báo bản tin chưa được khởi tạo và sẽ tự tạo sau lần nạp tiếp theo |
| POST `/wiki/hot/rebuild?scope_type&scope_id` | đăng nhập | Không admin, thiếu wiki:write:all → 403 "Requires wiki:write:all permission to edit global/department wiki pages". `regenerate_hot_cache`; commit; `{ok: true, content_md}` |

### 5.3. `get_wiki_graph(slug=None, depth=1(1–3), offset=0, limit=100(1–500), edge_type=None, db, user)`

Test gọi trực tiếp hàm này với các tham số keyword và một user admin giả.

1. `visible`: nếu `_page_read_filter` khác None → tập slug người dùng thấy (một truy vấn); admin → None, không truy vấn.
2. Có `slug`: slug không thuộc `visible` → 404 "Wiki page not found: {slug}". Trả `get_neighborhood(db, slug, depth=depth)`, lọc nút và cạnh theo `visible` (nếu có).
3. Toàn đồ thị, thứ tự truy vấn cố định: (a) đếm (đọc bằng scalar), (b) nút trang theo slug tăng dần với offset/limit (đọc bằng all), rồi nếu offset = 0, với edge_type (mặc định `all`): (c) wikilink, (d) concept, (e) legal. edge_type `concept` → chỉ (a), (b), (d). Bỏ trang dành riêng; áp bộ lọc đọc.
4. Cạnh — các khóa chung: `from`, `to`, `type`, `label`, `predicate`, `weight`, `evidence`.
   - wikilink: label và predicate là "wikilink", weight 1.0, evidence null.
   - concept: chỉ quan hệ đã gán cả trang nguồn và trang đích; label = predicate; weight = float(weight hoặc 1.0); evidence; thêm `source_concept`, `target_concept`.
   - legal: quan hệ pháp lý `is_effective` true mà cả hai đơn vị đều gắn trang wiki; label = predicate = giá trị của relation_type (enum lấy `.value`, chuỗi giữ nguyên); weight 1.2; evidence = quote_context; thêm `target_doc_number`.
5. Khi `visible` khác None, chỉ giữ cạnh có cả hai đầu thuộc `visible`.
6. Trả `{nodes: [{slug, title, page_type, status, scope_type (mặc định global), scope_id (chuỗi hoặc null), scope_name}], edges, total, offset, has_more = offset + limit < total}`.

### 5.4. Router `wiki_images`

POST `/wiki/images/resolve` (đăng nhập), body `{ids: [UUID]}`. Rỗng → `{resolved: {}, denied: []}`; > 100 id → 400 "Too many ids (max 100 per request)". Bỏ trùng; với mỗi ảnh nguồn có thật: không đọc được tài liệu nguồn (`can_access_document`, cache theo nguồn) → vào `denied`; đọc được → `resolved[id]` = URL ký sẵn MinIO hạn 1 giờ (lỗi ký → bỏ qua). Id không tồn tại không xuất hiện ở đâu.

---

## 6. Router `wiki_drafts` (`app/routers/wiki_drafts.py`)

### 6.1. Mô hình request

| Mô hình | Trường và kiểm tra |
|---|---|
| ProposeDraftRequest | content_md (không rỗng "content_md must not be empty"; ≤ 50 000 "content_md exceeds 50,000 character limit"), note, base_version, scope_type, scope_id, branch_id |
| ProposeCreateRequest | slug, title, page_type = concept, knowledge_type_slugs = [], scope_type = global, scope_id, content_md, summary = "", note, branch_id — cùng quy tắc kiểm tra như WikiDirectCreateRequest |
| ApproveDraftRequest | reviewer_note, edited_content_md, allow_conflict = false, final_slug, final_title, final_page_type, final_knowledge_type_slugs |
| RejectDraftRequest | reviewer_note bắt buộc không rỗng ("reviewer_note is required when rejecting") |
| RequestChangesRequest | reviewer_note bắt buộc ("reviewer_note is required when requesting changes") |
| ResubmitDraftRequest | content_md (như trên), note |
| BulkApproveRequest | draft_ids, allow_conflict = false, reviewer_note |

### 6.2. Mô hình response

**DraftResponse**:

| Nhóm | Trường |
|---|---|
| Định danh | id, page_id |
| Trang | page_slug, page_title (từ trang; bản nháp create lấy từ suggested_metadata), page_scope_type (mặc định global), page_scope_id, page_scope_name (tên phòng ban) |
| Phiên bản | page_version (version hiện tại hoặc 1), base_version, has_conflict (status pending và base_version < version hiện tại) |
| Loại | draft_kind (mặc định edit), suggested_metadata |
| Tác giả | author_id, author_name, author_stats, suggested_reviewers |
| Nội dung | content_md, note, status, revision_round (mặc định 0), last_returned_note |
| AI | ai_check_status (mặc định pending), ai_check_results, ai_checked_at |
| Duyệt | source, reviewed_by_name, reviewed_at, reviewer_note |
| Thời gian | created_at, updated_at (ISO) |

- **AuthorStats** (null nếu không có tác giả): approved, rejected, needs_revision (đếm bản nháp của tác giả theo status), total_reviewed = approved + rejected, accuracy = approved / total_reviewed làm tròn 3 chữ số (0 nếu total = 0).
- **SuggestedReviewer**: id, name, email, score. Chỉ tính cho bản nháp pending / needs_revision (khác → []). Xếp hạng người dùng theo số revision có change_type thuộc {editor_edit, draft_approved, draft_approved_create, rollback} trên các trang trùng loại tri thức với bản nháp hoặc cùng phạm vi (scope khớp chính xác; global là scope_id null); bản nháp create lấy loại tri thức và phạm vi từ suggested_metadata. Loại trừ tác giả; tối đa 3.
- **DraftRoundResponse**: id, round_no, content_md, author_note, reviewer_return_note, ai_check_results, submitted_at (ISO).

Nạp bản nháp theo id: id sai định dạng → 400 "Invalid draft ID format"; không có → 404 "Draft {id} not found".

### 6.3. Endpoint

| Method, đường dẫn | Quyền | Hành vi, lỗi |
|---|---|---|
| POST `/wiki/pages/{slug}/drafts` (201) | đăng nhập | Slug dành riêng (`_index`/`_log`) → 400 "Cannot propose drafts for reserved pages". Tra trang: có scope_type → theo phạm vi (bộ lọc nguồn); không → `get_page_by_slug_any_scope`; 404. `_can_propose` sai → 403 "Insufficient permission to propose a draft for this page". base_version mặc định version trang; lớn hơn → 400 "base_version X is ahead of current page vY". `create_draft` (nguồn web_ui), gán draft.page, branch_id; audit update wiki_draft "published edit: slug"; `publish_draft`. Lỗi (sau rollback): DraftConflictError → 409 thông điệp tiếng Việt "Trang đã được cập nhật lên v{current} sau khi bạn mở. Tải lại trang rồi sửa lại."; CreateDraftSlugConflict → 409 "Slug '{slug}' đã tồn tại."; ValueError → 400. Commit; DraftResponse |
| GET `/wiki/drafts?status=pending&mine=false&limit=50(1–200)&offset=0` | wiki:read | Gồm cả bản nháp create (left join trang); sắp created_at giảm dần. `mine` → chỉ của mình. Ngược lại: loại bản nháp thuộc nhánh có status khác pending_merge; người không có quyền duyệt (không admin, không wiki:write:all) → []; áp bộ lọc nguồn (page_id null hoặc trang đọc được) |
| GET `/wiki/pages/{slug}/drafts?status&scope_type&scope_id` | đăng nhập | Tra trang như propose (404). Người không duyệt được chỉ thấy bản nháp của mình (không trả 403). Sắp created_at giảm dần |
| GET `/wiki/drafts/{id}` | đăng nhập | admin, tác giả hoặc người duyệt được; khác → 403 "Insufficient permission to view this draft" |
| POST `/wiki/drafts/{id}/approve` | đăng nhập | Không pending → 400 "Draft is already {status}"; không duyệt được → 403 "Insufficient permission to approve this draft"; bản nháp của chính mình (không phải admin) → 403 "You cannot approve your own draft. Ask another editor to review it.". Override metadata chỉ áp cho bản nháp create. Lỗi: DraftConflictError → 409 detail {error "draft_conflict", message, current_version, base_version, hint gợi ý gửi lại với allow_conflict=true hoặc cung cấp edited_content_md}; CreateDraftSlugConflict → 409 {error "slug_conflict", message, slug, scope_type, scope_id (chuỗi hoặc null), hint gợi ý đổi final_slug}; ValueError → 400. Thành công: audit "created|approved draft for: slug"; regenerate_index; log "Created|Approved page: T (slug) → vN by X"; `notify_approved(version_label "vN")`; index chunk (lỗi chỉ cảnh báo); commit; DraftResponse |
| POST `/wiki/drafts/{id}/reject` | đăng nhập | Không pending → 400; không duyệt được → 403 "Insufficient permission to reject this draft". `reject_draft`; audit "rejected draft for: slug" (hoặc "(unknown)" / "(new page)"); `notify_rejected(reason)`; commit |
| POST `/wiki/drafts/{id}/request-changes` | đăng nhập | Không duyệt được → 403 "Insufficient permission to review this draft". `contribution_service.request_changes`; InvalidTransition → 400 |
| PATCH `/wiki/drafts/{id}/content` | đăng nhập | `resubmit_wiki_draft(nội dung đã cắt, author_note = note)`; InvalidTransition → 400 |
| POST `/wiki/drafts/{id}/withdraw` | đăng nhập | `contribution_service.withdraw`; InvalidTransition → 403 |
| GET `/wiki/drafts/{id}/rounds` | đăng nhập | admin, tác giả hoặc người duyệt; khác → 403 "Insufficient permission to view this draft's rounds". Sắp round_no tăng dần |
| POST `/wiki/drafts/create` (201) | đăng nhập | Không phải admin: department có scope_id → cần wiki:write:all hoặc own_dept thuộc phòng đó, ngược lại 403 "Insufficient permission to propose pages in this department"; phạm vi khác → cần quyền wiki write bất kỳ, ngược lại 403 "Insufficient permission to propose new pages". Slug có trong phạm vi → 409 "Slug '{slug}' already exists in {scope_type}. Use edit_wiki_page to edit the existing page.". suggested_metadata = {slug, title, page_type, knowledge_type_slugs, scope_type, scope_id dạng chuỗi}. `create_draft(page_id None, draft_kind create)`; branch_id; audit create "published new page: slug"; `publish_draft` (cùng ánh xạ lỗi); commit |
| POST `/wiki/drafts/bulk-approve` | đăng nhập | Từng bản nháp: không có → error "Draft not found"; không pending → skipped "Draft is already X"; không duyệt được → skipped "Insufficient permission"; của chính mình → skipped "Cannot approve your own draft". Mỗi bản duyệt trong savepoint riêng: approve (reviewer_note, allow_conflict), audit "bulk-approved: slug", regenerate_index, log "Bulk-approved draft for: T (slug) -> vN by X", notify_approved, index chunk. Lỗi → error str(e), làm hết hạn đối tượng bản nháp và trang. Một commit cuối. Response {results: [{draft_id, status approved/skipped/error, message, page_version}], approved, skipped, errored} |

---

## 7. Router `wiki_branches` (`app/routers/wiki_branches.py`)

Nhánh đóng góp gom nhiều bản nháp để duyệt hợp nhất một lần. Trạng thái: draft → pending_merge → merged | closed.

**BranchCreate**: name (cắt; rỗng → "Tên nhánh không được để trống"; > 100 → "Tên nhánh không được vượt quá 100 ký tự"), description, scope_type (global|department, lỗi "scope_type phải là global hoặc department"), scope_id.

**BranchResponse**: id, name, description, scope_type, scope_id, author_id, author_name, status, has_conflict, reviewer_id, reviewer_name, reviewed_at, reviewer_note, created_at, updated_at, draft_count. **BranchDetailResponse** thêm `drafts: [DraftResponse]` (created_at giảm dần).

Quyền: tạo nhánh dùng quy tắc như `_can_propose` theo phạm vi của nhánh; duyệt / hợp nhất: admin hoặc wiki:write:all.

| Method, đường dẫn | Hành vi, lỗi |
|---|---|
| POST `/wiki/branches` (201) | Không có quyền → 403 "Bạn không có quyền đóng góp trong phạm vi này". Tạo status draft; commit; audit create_branch |
| GET `/wiki/branches?status&scope_type&scope_id&mine` | Sắp updated_at giảm dần; không lọc theo quyền |
| GET `/wiki/branches/{id}` | 404 "Không tìm thấy nhánh đóng góp này"; trả Detail |
| POST `/wiki/branches/{id}/submit` | 404 "Không tìm thấy nhánh đóng góp"; không phải tác giả, không phải admin → 403 "Chỉ có tác giả của nhánh mới có quyền gửi yêu cầu"; không ở draft → 400 "Không thể gửi yêu cầu hợp nhất khi nhánh đang ở trạng thái '{s}'"; không có bản nháp → 400 "Nhánh đóng góp của bạn đang trống. Vui lòng thêm nháp trang trước khi gửi.". Mỗi bản nháp → pending và `notify_submitted`; nhánh → pending_merge; audit submit_branch |
| POST `/wiki/branches/{id}/close` | Chỉ tác giả hoặc người duyệt, khác → 403 "Bạn không có quyền đóng hoặc hủy nhánh này"; đã merged/closed → 400 "Nhánh đã đóng hoặc đã được hợp nhất". Rút (withdrawn) các bản nháp pending/needs_revision; nhánh → closed; audit close_branch |
| POST `/wiki/branches/{id}/merge` body {reviewer_note} | Không duyệt được → 403 "Bạn không có quyền hợp nhất tài liệu trong phạm vi này"; không ở pending_merge → 400 "Chỉ có thể hợp nhất nhánh khi đang ở trạng thái 'pending_merge'". Kiểm tra trước: bản nháp edit nào có base_version < version trang → đặt has_conflict true, commit, 409 với thông điệp tiếng Việt nêu tiêu đề, slug, version hiện tại, version gốc và yêu cầu tác giả rebase. Sau đó trong transaction lồng: `approve_draft` từng bản (reviewer_id, reviewer_note) và `notify_approved`; nhánh → merged, ghi người duyệt, has_conflict false. Lỗi bất kỳ → rollback, 400 "Lỗi hợp nhất nhánh: {e}". Audit merge_branch. Khác duyệt lẻ: không dựng lại mục lục, không ghi log |
| POST `/wiki/branches/{branch_id}/rebase/{draft_id}` body {resolved_content_md} | Chỉ tác giả nhánh hoặc admin, khác → 403 "Chỉ có tác giả nhánh mới có quyền xử lý xung đột"; bản nháp không có hoặc không thuộc nhánh → 404 "Không tìm thấy bản nháp cần xử lý trong nhánh này"; bản nháp create → 400 "Bản nháp trang tạo mới không cần xử lý rebase"; trang gốc mất → 404 "Không tìm thấy trang gốc trên wiki". Gán nội dung, base_version = version trang, status pending; `_enqueue_ai_review`; tính lại has_conflict của nhánh; commit; audit rebase_draft; trả DraftResponse |

---

## 8. Mảng pháp lý

### 8.1. Phân loại

Mọi service pháp lý là file loại C có sẵn: `legal_service`, `legal_relation_extractor`, `legal_route_service`, `legal_hierarchy_parser`, `doc_metadata_service`. Người viết code chỉ cần xây model (§8.2), router (§8.3), task worker (§8.4), và các hàm của `wiki_service` mà chúng gọi (05a §1.3).

Vai trò tóm tắt:
- `legal_service`: nhận diện văn bản pháp luật, tách metadata (`parse_legal_metadata`), tạo slug văn bản (`build_legal_doc_slug`), tách theo Điều (`split_legal_text_by_articles` → {preamble, articles: [{num, heading, title, content_md, chapter_num, chapter_title, slug}]}), `finalize_legal_source` (tạo trang tổng quan và trang từng Điều ở status mature cho từng phạm vi của `resolve_wiki_scopes`, rồi regenerate_index và append_log), `ingest_legal_graph` (ghi đơn vị và quan hệ), ngữ cảnh có phân cấp và cảnh báo hiệu lực cho truy hồi.
- `legal_relation_extractor`: trích quan hệ sửa đổi / thay thế / bãi bỏ… và `relink_legal_relations(session, source_id=None)` nối lại quan hệ chưa phân giải tới đơn vị đích.
- `legal_route_service`: `find_doc_numbers`, `normalize_doc_number`, tuyến tra cứu chính xác theo số hiệu (đặc tả 04).
- `doc_metadata_service`: metadata văn bản (doc_type, doc_number, issuing_authority, official_title, issued_date, effective_date, expiry_date — ngày dạng ISO; lĩnh vực theo danh mục `FIELDS`), `get_doc_meta`, `compute_validity`, `load_lifecycle`, `lifecycle_for`, `load_doc_relations`, `backfill_document_metadata`.

Tình trạng hiệu lực (`compute_validity`): bị thay thế → "thay thế"; bị bãi bỏ hoặc đã qua expiry_date → hết hiệu lực; không có ngày hiệu lực/ban hành → chưa xác định; ngày hiệu lực ở tương lai → chưa có hiệu lực; còn lại → còn hiệu lực. Vòng đời (replaced_by / repealed_by) lấy từ các quan hệ cấp văn bản (không có số Điều đích) loại thay_the / bai_bo còn hiệu lực trỏ tới số hiệu đó (so khớp chữ hoa).

### 8.2. Model (`app/database/models.py`)

Enum (`str` enum, test kiểm tra giá trị):

| Enum | Thành viên → giá trị |
|---|---|
| `LegalUnitType` | PART part, CHAPTER chapter, SECTION section, ARTICLE article, CLAUSE clause, POINT point |
| `LegalRelationType` | SUA_DOI sua_doi, BO_SUNG bo_sung, THAY_THE thay_the, BAI_BO bai_bo, HUONG_DAN huong_dan, CAN_CU can_cu, DAN_CHIEU dan_chieu |

**`legal_units`** (`LegalUnit`):

| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | UUID PK | |
| source_id | UUID FK sources, xóa dây chuyền, index | |
| wiki_page_id | UUID FK wiki_pages, set null, index | |
| unit_type | varchar(20), index | LegalUnitType |
| unit_number | varchar(50), index | ví dụ "1", "5a", "I", "a" |
| title | varchar(500), null | |
| full_path | varchar(500) | mặc định ""; đường dẫn phân cấp kiểu "Chương I > Điều 1 > Khoản 2" |
| content | text | mặc định "" |
| parent_unit_id | UUID FK legal_units, xóa dây chuyền, index | |
| doc_number | varchar(100), null, index | |
| created_at, updated_at | timestamptz | |

Index ghép (doc_number, unit_type, unit_number). Quan hệ ORM: source, wiki_page, parent / children, outgoing_relations (xóa theo), incoming_relations.

**`legal_relations`** (`LegalRelation`): id; source_unit_id (FK legal_units, xóa dây chuyền, index); target_unit_id (FK, set null, index); target_doc_number varchar(100) index; target_article_number varchar(50) index; target_clause_number varchar(50); relation_type varchar(30) index; quote_context text; is_effective bool mặc định true, index; created_at, updated_at. Index ghép (target_doc_number, target_article_number).

Test dựng các đối tượng này bằng keyword và đọc lại đúng giá trị (không cần DB).

### 8.3. Router `legal_docs` (`app/routers/legal_docs.py`)

Item văn bản (dùng ở danh sách và chi tiết): id, title (title hoặc file_name hoặc ""), file_name, knowledge_type ({id, name, slug, color} hoặc null), scope_type (mặc định global), departments ([{id, name}]), status, has_file, url, doc_slug, meta, validity (null khi không có meta), replaced_by, repealed_by, created_at, updated_at.

| Method, đường dẫn | Quyền | Hành vi, lỗi |
|---|---|---|
| GET `/wiki/legal-doc-fields` | đăng nhập | `{fields: FIELDS}` |
| GET `/wiki/legal-docs?content_q` | đăng nhập | `source_read_filter(user)` → (allowed, bộ lọc). knowledge_types: mọi loại sắp sort_order, name. Không allowed → `{items: [], knowledge_types}`. Ngược lại: mọi nguồn status ready (không chỉ văn bản pháp luật), sắp created_at giảm dần, áp bộ lọc; `content_q` → full_text chứa chuỗi (không phân biệt hoa thường); nạp vòng đời theo số hiệu; phòng ban theo SourceDepartment sắp theo tên |
| POST `/wiki/legal-docs/backfill?only_missing=true&use_llm=true&limit=1000(1–20000)` | org:settings:manage | Audit (backfill_doc_metadata, settings, global, kèm tham số); commit; enqueue `backfill_doc_metadata_task(only_missing, use_llm, limit)`; `{job_id}` hoặc null |
| GET `/wiki/legal-docs/{key}` | đăng nhập | key là UUID nguồn hoặc doc_slug (lấy bản mới nhất). Không có → 404 "Document not found"; `can_access_document(read)` sai → 403 "Access denied". Trả item + preamble, articles [{num, heading, title, content_md, chapter_num, chapter_title, wiki_slug (slug Điều nếu trang đó hiển thị được, ngược lại null)}], relations ({outgoing, incoming}: relation_type, doc_number, article, clause, from_article, quote), wiki_pages (trang có source_ids chứa nguồn, trừ trang dành riêng, lọc bằng `_build_wiki_scope_filter`, bỏ trùng slug, sắp slug: {slug, title, page_type, summary}), overview_slug (trang có slug = doc_slug), summary (summary của trang page_type "summary", hoặc trang tổng quan, hoặc official_title, hoặc ""), download_url / preview_url / file_url (khi có tệp; dùng token tệp riêng `create_source_file_token(user id, source id)` lần lượt cho tải về, xem trước, tệp gốc; lỗi tạo → null), file_size, source_type (hoặc url/file), contributed_by_name. Cấu trúc Điều được tách lại từ full_text, slug mặc định "doc-" + 8 ký tự hex đầu của id khi không có doc_slug |

### 8.4. Task worker liên quan

| Task | Hành vi |
|---|---|
| `ingest_refine_task(ctx, source_id, attempt_id_str=None)` | REFINE + VERIFY + COMMIT (05a §5.9) |
| `relink_legal_relations_task(ctx, source_id=None)` | Gọi `relink_legal_relations(session, source_id=UUID hoặc None)`, trả kết quả |
| `backfill_doc_metadata_task(ctx, only_missing=True, use_llm=True, limit=1000)` | Gọi `backfill_document_metadata`, trả kết quả |
| `ai_pre_review_draft_task(ctx, draft_id, expected_round=None)` | §3.6 |
| `sweep_stuck_ai_review_cron(ctx)` | §3.6 |

---

## 9. Bảng đối chiếu test

| Test | Kiểm tra gì | Mục |
|---|---|---|
| test_wiki_write_guard | `apply_update` từ chối/cho phép/guard=False; merger dùng phương án nối; `_pass_drops_rows`; `run_commit_phase` bỏ qua stub | 05a §3.7, §5.5, §5.7, §5.8 |
| test_wiki_draft_publish | `publish_draft` | §1.3 |
| test_graph_api | `get_wiki_graph`, `_page_read_filter` | §4, §5.3 |
| test_mcp_scope | `render_scoped_index` | 05a §3.8 |
| test_concept_relations | `EXTRACTION_PROMPT_TEMPLATE`, quan hệ khái niệm | 05a §4, §5.2 |
| test_search_accuracy, test_graph_expanded_search, test_dual_pipeline_retrieval | `_lexical_plan`, tìm kiếm lai | 04 §8 |
| test_legal_scope_enforcement | legal_service gọi `wiki_service.resolve_wiki_scopes / upsert_page / regenerate_index / append_log` qua module | 05a §3.4, §3.7, §3.8 |
| test_legal_graph_models | enum và model pháp lý | §8.2 |
| test_legal_* khác, test_exact_legal_route, test_question_generator | file loại C | §8.1 |
| test_source_status, test_citation_verifier | file loại C | 05a §1.1 |
