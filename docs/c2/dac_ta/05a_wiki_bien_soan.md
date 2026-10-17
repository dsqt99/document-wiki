# 05a — Wiki: mô hình trang, liên kết, phạm vi và pipeline biên soạn MRP

Phần 05a đặc tả phần lõi của wiki: lược đồ dữ liệu, `wiki_service` (trừ phần bản nháp), quan hệ khái niệm và pipeline biên soạn map → reduce → duyệt kế hoạch → refine → verify → commit. Phần bản nháp, vòng duyệt, AI tiền duyệt, nhánh đóng góp, toàn bộ router wiki và mảng pháp lý nằm ở `05b_duyet_phap_ly.md`.

Tài liệu tuân thủ `QUY_TAC_DAC_TA.md`: chỉ có văn xuôi, bảng và chữ ký, không có code, regex hay prompt nguyên văn.

---

## 1. Phân loại module

### 1.1. File loại C đã có trong c2 (không viết lại)

| Module | Vai trò trong mảng này |
|---|---|
| `app/services/wiki_write_guard.py` | Chặn bản ghi máy làm mất dòng bảng, co nội dung hoặc ghi đè bằng stub lỗi |
| `app/services/wiki_chunk_service.py` | Chia trang thành chunk và index embedding (`index_wiki_page_chunks`) |
| `app/services/citation_verifier.py` | `CitationVerifier`, `apply_citation_callout` |
| `app/ai/mrp/synthesizer.py` | `synthesize_footnotes`, `verify_and_polish_citations` |
| `app/models/concept_relation.py` | Bảng `concept_relations`, `ConceptPredicate`, `normalize_predicate`, `collect_concept_relations`, `persist_concept_relations`, `link_concept_relations_to_pages` |
| `app/services/source_status.py` | `update_source_dual_status` |
| `app/services/security_label.py` | Mệnh đề lọc nhãn mật cho trang (`page_label_clause`) |
| `app/services/search_fusion.py`, `app/services/retrieval_service.py` | Dùng hàm tìm kiếm của `wiki_service` (xem đặc tả 04, §8) |
| `app/services/legal_service.py` | Gọi `wiki_service.resolve_wiki_scopes`, `upsert_page`, `regenerate_index`, `append_log` |
| `app/scripts/audit_legal_scopes.py` | Import `resolve_wiki_scopes`, `regenerate_index` từ `app.services.wiki_service` |
| `app/core/vi_tokenizer.py` | `keyword_terms`, `quoted_phrases`, gấp dấu tiếng Việt |

### 1.2. Module phải tự xây theo đặc tả này

| Module | Nội dung |
|---|---|
| `app/services/wiki_service.py` | Toàn bộ, trừ các hàm tìm kiếm đã đặc tả ở 04 §8 (vẫn nằm trong cùng file) |
| `app/ai/mrp/mapper.py` | Pha MAP |
| `app/ai/mrp/reducer.py` | Pha REDUCE và gọi lập kế hoạch |
| `app/ai/mrp/writer.py` | Pha REFINE (viết trang) |
| `app/ai/mrp/verifier.py` | Pha VERIFY |
| `app/ai/mrp/merger.py` | Gộp nội dung khi cập nhật trang đã có |
| `app/ai/mrp/pipeline.py` | Điều phối, pha COMMIT, tự duyệt kế hoạch, chạy tiếp |
| `app/database/models.py` | Các bảng ở §2 |

### 1.3. Symbol mà test và file loại C import

Người viết code **phải** cung cấp đúng tên, chữ ký và hành vi dưới đây.

| Symbol | Nơi dùng | Hành vi bắt buộc |
|---|---|---|
| `wiki_service.INDEX_SLUG`, `LOG_SLUG`, `HOT_SLUG`, `PAGE_TYPES` | router, ai_review, legal | Giá trị `_index`, `_log`, `_hot`; `PAGE_TYPES` là tập {entity, concept, source, topic, index, log, hot} |
| `wiki_service.resolve_wiki_scopes(session, source)` | legal_service, script audit, test pháp lý | §3.4 |
| `wiki_service.upsert_page(session, slug=, title=, page_type=, content_md=, summary=, knowledge_type_slugs=, source_ids=, scope_type=, scope_id=, status=)` | legal_service | §3.7 |
| `wiki_service.regenerate_index(session, scope_type=, scope_id=)` | legal_service, publish, script | §3.8 |
| `wiki_service.append_log(session, entry, scope_type=, scope_id=)` | legal_service, publish | §3.8 |
| `wiki_service.render_scoped_index(session, *, allowed_kt_slugs=, department_ids=, all_scopes=, ...)` | `test_mcp_scope`, MCP | §3.8; phải gọi `list_pages` bằng keyword args |
| `wiki_service.get_page_by_slug`, `list_pages`, `apply_create`, `apply_update`, `refresh_links` | `test_wiki_write_guard`, `test_mcp_scope` | §3.5–3.7 |
| `wiki_service._lexical_plan`, `search_pages_hybrid`, `search_source_chunks_hybrid`, `search_pages_semantic` | `test_search_accuracy`, retrieval_service | Đặc tả 04 §8 |
| `app.ai.mrp.mapper.EXTRACTION_PROMPT_TEMPLATE` | `test_concept_relations` | Chuỗi mẫu prompt; phải chứa nguyên các từ `la_mot`, `thuoc`, `quy_dinh`, `ap_dung_cho`, `lien_quan`, `evidence` |
| `app.ai.mrp.merger.merge_page_content`, `APPEND_FALLBACK_HEADING` | `test_wiki_write_guard` | §5.7 |
| `app.ai.mrp.writer._pass_drops_rows`, `PageWriteResult` | `test_wiki_write_guard` | §5.5 |
| `app.ai.mrp.pipeline.run_commit_phase`, `pipeline._resolve_wiki_scopes` | `test_wiki_write_guard`, reducer | §5.8 |

---

## 2. Lược đồ dữ liệu

### 2.1. Enum

| Enum | Giá trị |
|---|---|
| Phạm vi (`scope_type`) | `global`, `department`, `personal`; mã còn dùng `project` ở một số bộ lọc (không có bảng project nữa) |
| Trạng thái trang (`status`) | `seed`, `developing`, `mature`, `evergreen` |
| Loại bản nháp (`draft_kind`) | `edit`, `create` |
| Trạng thái bản nháp | `pending`, `needs_revision`, `withdrawn`, `approved`, `rejected` |
| Trạng thái AI tiền duyệt (`ai_check_status`) | `pending`, `queued`, `running`, `passed`, `warned`, `failed`, `skipped` |
| Nguồn bản nháp (`source`) | `web_ui`, `mcp_claude_desktop`, `mcp_claude_code`, `mcp_other`, `api_direct` |
| Loại revision (`change_type`) | `agent_compile`, `agent_retry`, `editor_edit`, `draft_approved`, `draft_approved_create`, `manual_rebuild`, `rollback` |
| Trạng thái nhánh | `draft`, `pending_merge`, `merged`, `closed` |
| Trạng thái kế hoạch biên soạn | `pending_review`, `approved`, `in_progress`, `done`, `rejected` |
| Trạng thái trích xuất chunk | `pending`, `done`, `error` |

### 2.2. `wiki_pages`

| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | UUID PK | |
| slug | varchar(300) | Không unique toàn cục; duy nhất trong một cặp (scope_type, scope_id) theo nghiệp vụ |
| title | text | |
| status | varchar | seed / developing / mature / evergreen, mặc định `seed` |
| content_md | text | |
| summary | text, null | |
| scope_type | varchar | mặc định `global` |
| scope_id | UUID, null | id phòng ban khi scope_type = department |
| knowledge_type_slugs | mảng chuỗi | mặc định rỗng |
| source_ids | mảng UUID | các văn bản nguồn đã đóng góp vào trang |
| version | int | mặc định 1 |
| orphaned | bool | mặc định false |
| created_at, updated_at | timestamptz | |

`page_type` **không phải cột lưu**: là thuộc tính tính toán dùng được cả trên đối tượng lẫn trong truy vấn SQL (chọn cột, lọc). Quy tắc: slug `_index` → `index`, `_log` → `log`, `_hot` → `hot`; slug bắt đầu bằng `source/` → `source`; còn lại → `concept`.

### 2.3. `wiki_links`

Khóa chính ghép (`from_page_id` FK → wiki_pages, xóa dây chuyền; `to_slug` varchar(300)). Lưu liên kết ra của mỗi trang theo slug đích (đích có thể chưa tồn tại).

### 2.4. `wiki_page_revisions`

| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | UUID PK | |
| page_id | UUID FK → wiki_pages, xóa dây chuyền | |
| version | int | unique (page_id, version) |
| content_md | text | nội dung tại phiên bản này |
| change_type | varchar | enum §2.1 |
| draft_id | UUID, null | bản nháp gây ra thay đổi |
| changed_by_id | UUID FK employees, null | |
| change_note | text, null | |
| created_at | timestamptz | |

### 2.5. `wiki_page_drafts`

| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | UUID PK | |
| page_id | UUID FK wiki_pages, null | null với bản nháp tạo trang mới cho tới khi được duyệt |
| draft_kind | varchar | `edit` (mặc định) / `create` |
| suggested_metadata | JSONB, null | với `create`: slug, title, page_type, knowledge_type_slugs, scope_type, scope_id (chuỗi UUID hoặc null) |
| author_id | UUID FK employees, null | |
| content_md | text | |
| note | text, null | ghi chú của tác giả |
| base_version | int, null | phiên bản trang khi tác giả bắt đầu sửa |
| revision_round | int | mặc định 0 |
| last_returned_note | text, null | lời nhắn trả lại gần nhất của người duyệt |
| ai_check_status | varchar | mặc định `pending` |
| ai_check_results | JSONB, null | §4 của 05b |
| ai_checked_at | timestamptz, null | |
| status | varchar | mặc định `pending` |
| source | varchar | mặc định `web_ui` |
| source_metadata | JSONB, null | |
| branch_id | UUID FK wiki_branches, null | |
| reviewed_by_id | UUID FK employees, null | |
| reviewed_at | timestamptz, null | |
| reviewer_note | text, null | |
| created_at, updated_at | timestamptz | |

Quan hệ ORM: `page`, `author`, `reviewer` (nạp được bằng selectin).

### 2.6. `wiki_draft_rounds`

id, draft_id (FK, xóa dây chuyền), round_no (int), content_md, author_note, reviewer_return_note, ai_check_results (JSONB), submitted_at. Mỗi hàng là ảnh chụp một lần nộp trước khi tác giả nộp lại.

### 2.7. `wiki_branches`

id, name varchar(100), description, scope_type (mặc định global), scope_id, author_id (FK employees), status (mặc định `draft`), has_conflict (bool, mặc định false), reviewer_id, reviewed_at, reviewer_note, created_at, updated_at.

### 2.8. `source_chunk_extracts`

| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | UUID PK | |
| source_id | UUID FK sources, xóa dây chuyền | |
| chunk_index | int | unique (source_id, chunk_index) |
| start_char, end_char | int | vị trí trong full_text |
| section_path | text, null | |
| extract_json | JSONB, null | kết quả trích xuất (§5.2) |
| status | varchar | pending / done / error |
| error_message | text, null | tối đa 500 ký tự |
| created_at | timestamptz | |

Index (source_id, status).

### 2.9. `source_compilation_plans`

id, source_id (unique, FK sources xóa dây chuyền), plan_json (JSONB), status (mặc định `pending_review`), reviewed_by (FK employees, set null), review_note, created_at, reviewed_at.

### 2.10. Cột của `sources` mà pipeline dùng

`pipeline_phase` (map / reduce / plan_review / refine / verify / commit), `pipeline_strategy` (single_pass / standard / hierarchical), `wiki_status`, `wiki_progress`, `wiki_progress_message`, `wiki_error_message`, `auto_recover_count`, `outline_json`. Định nghĩa đầy đủ thuộc đặc tả nạp tài liệu.

### 2.11. Bảng pháp lý và quan hệ khái niệm

`legal_units`, `legal_relations` mô tả ở 05b §8.2; `concept_relations` là file loại C (§4).

---

## 3. `wiki_service` — trang, liên kết, phạm vi

### 3.1. Trang dành riêng

Ba slug dành riêng tồn tại theo từng phạm vi: `_index` (mục lục, tiêu đề "Wiki Index"), `_log` (nhật ký, tiêu đề "Wiki Log"), `_hot` (bản tin tri thức nóng). Các trang này không xuất hiện trong danh sách, đồ thị, lint; không được sửa trực tiếp, đổi trạng thái hay xóa qua API; bộ lọc nhãn mật và bộ lọc nguồn không áp lên chúng.

### 3.2. Wikilink

- `extract_wikilinks(content_md) -> list[str]`: nhận cả dạng `[[slug]]` và `[[slug|chữ hiển thị]]`; trả slug đã cắt khoảng trắng, bỏ trùng, giữ thứ tự xuất hiện đầu tiên.
- `refresh_links(session, from_page_id, from_slug, content_md) -> None`: xóa mọi liên kết ra của trang rồi chèn lại từ nội dung; bỏ liên kết tới chính nó; bỏ qua xung đột khóa. Test thay hàm này bằng monkeypatch, nên `apply_update` phải gọi nó qua tên module.
- `get_backlinks(session, slug, scope_type=None, scope_id=None) -> list[str]`: slug các trang (không trùng) có liên kết tới `slug`. Khi truyền phạm vi: chỉ tính trang nguồn cùng phạm vi đó hoặc trang global.
- `get_outlinks(session, slug, scope_type="global", scope_id=None) -> list[str]`: các `to_slug` của trang (slug, phạm vi).
- `get_neighborhood(session, slug, depth=1) -> {nodes, edges}`: duyệt vô hướng (cả liên kết ra và vào) tối đa `depth` bước (1–3) từ trang trung tâm. `nodes`: `{slug, title, page_type}` (chỉ trang tồn tại); `edges`: `{from, to}`.

### 3.3. Bộ lọc phạm vi

| Bộ lọc | Điều kiện |
|---|---|
| Chính xác `_scope_filter(scope_type, scope_id)` | scope_type bằng; scope_id bằng giá trị đã cho, hoặc IS NULL khi không cho. Router dùng hàm này |
| Theo danh tính | global, cộng department có scope_id thuộc `department_ids`, cộng project có scope_id thuộc `project_ids` |
| Nghịch đảo (`inverse_scope`) | department có scope_id **không** thuộc danh sách, cộng project không thuộc danh sách (để phát hiện kết quả ngoài phạm vi) |

### 3.4. `resolve_wiki_scopes(session, source) -> list[(scope_type, scope_id)]`

Xác định các phạm vi wiki mà một văn bản nguồn ghi trang vào:

1. Đọc lại bản ghi nguồn mới nhất từ DB (nếu không đọc được thì dùng đối tượng truyền vào).
2. Nguồn thuộc project → `[("project", id)]`.
3. Ngược lại, nếu có hàng `SourceDepartment` → mỗi phòng ban một phần tử `("department", department_id)`.
4. Ngược lại, nếu scope_type là department và có scope_id → `[("department", scope_id)]`.
5. Còn lại → `[("global", None)]`.

### 3.5. Đọc trang

- `get_page_by_slug(session, slug, allowed_kt_slugs=None, scope_type="global", scope_id=None, clearance=None, page_filter=None) -> WikiPage | None`: tra chính xác theo phạm vi. Với slug không dành riêng: áp mệnh đề nhãn mật khi có `clearance`, áp `page_filter` khi có. Kiểm tra loại tri thức: trả trang nếu không truyền `allowed_kt_slugs`, hoặc trang không có loại tri thức nào, hoặc có giao với danh sách; ngược lại trả None. Nơi gọi chỉ truyền các keyword cần thiết (test thay hàm này bằng bản chỉ nhận `session, slug, scope_type, scope_id`, nên `apply_update` và pha commit **chỉ** được truyền `scope_type`, `scope_id` ngoài hai tham số vị trí).
- `get_page_by_slug_any_scope(session, slug, clearance=None, page_filter=None)`: lấy trang đầu tiên khớp slug ở bất kỳ phạm vi nào, cùng quy tắc lọc.
- `list_pages(session, page_type=None, knowledge_type_slug=None, allowed_kt_slugs=None, query=None, limit=50, offset=0, scope_type="global", scope_id=None, department_ids=None, project_ids=None, all_scopes=False, clearance=None, page_filter=None) -> list[WikiPage]`: loại slug dành riêng; sắp `updated_at` giảm dần. Phạm vi: `all_scopes` → không lọc; có `department_ids`/`project_ids` → lọc theo danh tính; còn lại → lọc chính xác. `allowed_kt_slugs`: giao với danh sách hoặc trang không có loại tri thức. `query`: so khớp không phân biệt hoa thường trên title, slug, content.

### 3.6. Tìm kiếm

`_lexical_plan`, `search_pages_semantic`, `search_pages_hybrid`, `search_source_chunks_hybrid` đã đặc tả ở 04 §8 và giữ nguyên chữ ký ở đó. Pha REDUCE và AI tiền duyệt gọi `search_pages_semantic(session, vec, top_k=..., scope_type=..., scope_id=...)` và nhận danh sách `(page, similarity)`.

### 3.7. Ghi trang

**`apply_create(session, slug, title, page_type, content_md, summary, knowledge_type_slugs, source_ids, embedding=None, scope_type="global", scope_id=None, status="seed") -> WikiPage`**
Tạo trang version 1, flush, `refresh_links`, thêm một revision `agent_compile` (version 1).

**`apply_update(session, slug, new_content_md, summary=None, title=None, add_knowledge_type_slug=None, add_source_id=None, embedding=None, scope_type="global", scope_id=None, status=None, guard=True) -> WikiPage | None`**
1. Lấy trang bằng `get_page_by_slug(session, slug, scope_type=..., scope_id=...)`. Không có → None.
2. Nếu `guard` là true: gọi `check_machine_rewrite(nội dung cũ, nội dung mới)` của write guard. Có lý do từ chối → ghi cảnh báo và trả trang **không đổi gì** (không đổi nội dung, tiêu đề, version, nguồn; không tạo revision; không `session.add`).
3. Ngược lại: gán nội dung; gán title, summary, status nếu được truyền; thêm `add_knowledge_type_slug` và `add_source_id` vào danh sách nếu chưa có; tăng version 1; `refresh_links`; thêm đúng **một** đối tượng mới vào session là revision `agent_compile` với version mới.
4. `guard=False` bỏ qua bước 2 (cho phép ghi đè cả khi mất dòng bảng).

Write guard (loại C) từ chối khi: nội dung mới là stub lỗi mà nội dung cũ không phải; nội dung mới rỗng trong khi cũ không rỗng; tỉ lệ định danh dòng bảng bị mất > 0,2; trang cũ ≥ 500 ký tự mà trang mới < 50% độ dài cũ.

**`upsert_page(session, slug, title, page_type, content_md, summary, knowledge_type_slugs, source_ids, scope_type="global", scope_id=None, status=...) -> WikiPage`**
Lấy khóa advisory theo băm slug trong transaction; nếu trang chưa có → `apply_create` (status mặc định `seed`); có rồi → `apply_update` (thêm loại tri thức và nguồn đầu tiên trong danh sách) và trả kết quả, hoặc trả trang hiện có nếu bị guard chặn.

### 3.8. Mục lục, nhật ký, bản tin nóng

**`render_scoped_index(session, *, allowed_kt_slugs=None, department_ids=None, all_scopes=False, max_pages=2000, clearance=None, page_filter=None) -> str`**
Gọi `list_pages` bằng keyword args (`allowed_kt_slugs`, `department_ids`, `all_scopes`, `clearance`, `page_filter`, `limit = max_pages + 1`). Kết quả Markdown: tiêu đề cấp 1 "Wiki Index"; nhóm theo `page_type` (tiêu đề cấp 2 viết hoa chữ đầu); trong nhóm sắp theo title; mỗi dòng là gạch đầu dòng chứa wikilink dạng `[[slug|title]]`, kèm " — summary" nếu có. Không có trang → dòng ghi chú rỗng. Vượt `max_pages` → chỉ in `max_pages` trang và thêm ghi chú tiếng Việt rằng danh sách bị cắt, hướng người đọc dùng công cụ `list_wiki_pages` / `search_wiki`.

**`regenerate_index(session, scope_type="global", scope_id=None)`**: dựng lại nội dung mục lục của đúng phạm vi đó (cùng định dạng như trên, phạm vi chính xác) và ghi vào trang `_index` của phạm vi (tạo nếu chưa có; title "Wiki Index", summary "Catalog of all wiki pages").

**`append_log(session, entry, scope_type="global", scope_id=None)`**: nối vào trang `_log` của phạm vi một mục mới gồm tiêu đề cấp 2 dạng `[YYYY-MM-DD HH:MM UTC] <entry>` (giờ UTC). Nếu trang đang chứa dòng giữ chỗ "rỗng" thì thay dòng đó. Tạo trang "Wiki Log" nếu chưa có.

**`regenerate_hot_cache(session, scope_type="global", scope_id=None) -> WikiPage`**: dựng trang `_hot` (status `evergreen`) không dùng LLM, gồm ba mục tiêu đề tiếng Việt: các trang đang có callout mâu thuẫn (`[!contradiction]`), 10 trang cập nhật gần nhất, tối đa 20 trang đang ở trạng thái `seed` (cần phát triển). Mỗi mục là danh sách wikilink. Pha commit hiện **không** gọi hàm này; chỉ API rebuild gọi.

### 3.9. Xóa và tách nguồn

**`delete_page_cascade(session, page)`**:
1. Xóa liên kết tới slug trang: trang global → mọi liên kết tới slug đó; trang phạm vi khác → chỉ liên kết từ trang cùng phạm vi.
2. Sửa nội dung các trang tham chiếu: `[[slug|chữ]]` thành `chữ`; `[[slug]]` thành đoạn cuối của slug (sau dấu `/` cuối).
3. Xóa embedding của trang, rồi xóa trang.

**`detach_source_from_wiki(session, source_id) -> int`**: gỡ source_id khỏi mọi trang; trang nào không còn nguồn nào thì xóa bằng `delete_page_cascade`. Trả số trang đã xóa.

### 3.10. Lint

**`lint_wiki(session, scope_type="global", scope_id=None) -> dict`** trả:

| Khóa | Phần tử | Quy tắc |
|---|---|---|
| `dead_links` | `{from_slug, from_title, to_slug}` | Liên kết từ trang trong phạm vi mà đích không có trong phạm vi đó (với phạm vi khác global thì đích ở global vẫn tính là sống). Slug dành riêng không bao giờ là chết |
| `orphans` | `{slug, title, status}` | Trang trong phạm vi không có backlink nào |
| `contradictions` | `{slug, title}` | Trang có callout `[!contradiction]` |

---

## 4. Quan hệ khái niệm (concept relations — loại C)

- Năm vị từ đóng (`ConceptPredicate`): `la_mot` (là một loại), `thuoc` (thuộc về / thành phần), `quy_dinh` (quy định / điều chỉnh), `ap_dung_cho` (áp dụng cho đối tượng), `lien_quan` (liên quan chung).
- `normalize_predicate(pred)`: hạ chữ thường, cắt khoảng trắng, thay khoảng trắng bằng gạch dưới, ánh xạ qua bảng đồng nghĩa (ví dụ is_a / part_of / regulates / applies_to / relates_to và các biến thể gạch nối); rỗng hoặc không biết → `lien_quan`.
- `collect_concept_relations(chunk_extracts)`: gom `relations` từ `extract_json` mọi chunk, bỏ quan hệ thiếu đầu hoặc tự trỏ, bỏ trùng theo (from, to, vị từ) không phân biệt hoa thường; quan hệ lặp cộng `weight` thêm 1 và giữ evidence dài nhất.
- `persist_concept_relations(session, source_id, relations)`: xóa quan hệ cũ của nguồn rồi chèn mới, commit.
- `link_concept_relations_to_pages(session, source_id)`: gán `source_page_id`/`target_page_id` bằng cách khớp tên khái niệm với title hoặc slug trang (không phân biệt hoa thường). Pipeline MRP hiện không gọi hàm này; đồ thị chỉ hiển thị cạnh khái niệm đã được gán trang.
- Pha REDUCE gọi `collect` rồi `persist`; lỗi chỉ ghi cảnh báo.

---

## 5. Pipeline biên soạn MRP

### 5.1. Tổng quan

| Pha | `pipeline_phase` | Tiến độ (%) | Module |
|---|---|---|---|
| MAP: chia chunk và trích xuất | map | 10 → 50 | mapper |
| REDUCE: gộp, đối chiếu kho, lập kế hoạch | reduce → plan_review | 66, 68, 72, 76, 80 | reducer |
| Duyệt kế hoạch | plan_review | — | người dùng hoặc tự duyệt |
| REFINE: viết trang | refine | 78 | writer |
| VERIFY: trạng thái, mâu thuẫn, trích dẫn | verify | 88, 91, 95 | verifier |
| COMMIT: ghi trang, embedding, mục lục, nhật ký | commit | 95 → 100 | pipeline |

Hai task worker: task ingest chính gọi `run_mrp_pipeline` (MAP + REDUCE); `ingest_refine_task(source_id, attempt_id=None)` gọi `run_refine_pipeline` (REFINE + VERIFY + COMMIT). Định nghĩa task nằm ở đặc tả nạp tài liệu.

### 5.2. MAP (`mapper.py`)

Hằng số: kích thước chunk mục tiêu 20 000 ký tự, phần ngữ cảnh chồng lấp 1 000 ký tự, tối đa 6 lời gọi song song, timeout 300 giây mỗi lời gọi.

**Chọn chiến lược** (`classify_strategy`): dưới 30 000 ký tự → `single_pass`; tới 200 000 → `standard`; lớn hơn → `hierarchical`.

**Chia chunk** (`build_chunks`):
1. Nếu có outline: lấy các nút cấp ≤ 2 có khoảng ký tự, ghép liên tiếp tới khi chạm 20 000 ký tự. Chunk cuối kéo tới hết văn bản. Nếu phần đuôi chưa phủ > 100 ký tự thì thêm một chunk đuôi.
2. Mỗi chunk (trừ chunk đầu) được thêm tiền tố 1 000 ký tự cuối của đoạn trước, ngăn bằng một dòng đánh dấu "ngữ cảnh từ phần trước". `overlap_prefix_len` ghi lại độ dài tiền tố.
3. Không có outline: cửa sổ trượt 20 000 ký tự.
4. `DocumentChunk(index, start_char, end_char, section_path, text, overlap_prefix_len)`.

**Trích xuất** (`extract_chunk`, nhiệt độ 0,1). Mục đích prompt: đọc một đoạn văn bản và trả JSON gồm:
- `entities`: luôn để rỗng (không trích xuất thực thể).
- `concepts`: `{term, definition_excerpt, local_offset}`.
- `claims`: `{statement, subject, local_offset, evidence_length, confidence}`.
- `relations`: `{from, to, predicate, evidence}`, với predicate thuộc năm vị từ ở §4 (mẫu prompt phải nêu rõ năm tên vị từ và trường `evidence`).
- `topics`.
Kết quả được đổi offset: `absolute_offset = start_char + max(0, local_offset)`. JSON parse dễ dãi (chấp nhận khối rào code).

**`run_map_phase(session, source_id, full_text, outline_json, tracker, llm) -> (strategy, done_rows)`**: chạy tiếp được (bỏ qua chunk đã `done`); upsert hàng `source_chunk_extracts`; tiến độ = 10 + 40 × tỉ lệ hoàn thành; lỗi ghi `error` với thông điệp cắt 500 ký tự; các chunk lỗi được thử lại tuần tự một lần. Trả chiến lược và danh sách hàng `done`.

### 5.3. REDUCE (`reducer.py`)

Ngưỡng: gộp tự động 0,90; vùng mơ hồ từ 0,75; cập nhật trang kho 0,85; "có thể cập nhật" 0,60.

`run_reduce_phase(session, source, chunk_extracts, llm, embedding_provider, kt_name, kt_desc, tracker) -> SourceCompilationPlan`:
1. (66 %) Gom khái niệm, thực thể, nhận định thô từ mọi chunk.
2. Khử trùng chính xác: chuẩn hóa tên (hạ chữ thường, bỏ dấu câu, gọn khoảng trắng); giữ cách viết xuất hiện nhiều nhất, định nghĩa dài nhất, cộng `mention_count`.
3. (68 %) Khử trùng bằng embedding (khi có > 1 khái niệm và có provider): cặp có cosine ≥ 0,90 gộp (union-find); cặp trong [0,75; 0,90) gửi LLM phân xử (một lời gọi, trả mảng boolean, nhiệt độ 0, timeout 60 s). Lỗi → giữ kết quả khử trùng chính xác.
4. (72 %) Đối chiếu kho (`reconcile_with_kb`): lấy phạm vi bằng `pipeline._resolve_wiki_scopes(session, source)` (import trễ trong hàm); embed mỗi mục (khái niệm: "thuật ngữ: 200 ký tự đầu định nghĩa", cắt 4 000 ký tự); ở mỗi phạm vi tìm `search_pages_semantic` top 3 và giữ kết quả tốt nhất. ≥ 0,85 → UPDATE trang đó; ≥ 0,60 → MAYBE; còn lại → CREATE. Các mục MAYBE gửi LLM một lời gọi (mảng boolean, nhiệt độ 0, timeout 30 s): true → UPDATE, false/lỗi/không có LLM → CREATE. Embed lỗi → tất cả CREATE.
5. (76 %) Gọi lập kế hoạch (§5.3.1).
6. Gắn thêm vào plan: `_claims` (nhận định thô), `_entities`, `_concepts`.
7. Upsert `source_compilation_plans`: status `pending_review`, xóa reviewed_by / review_note / reviewed_at. Đặt `pipeline_phase = plan_review`.
8. Gom và lưu quan hệ khái niệm (§4). Commit.

#### 5.3.1. Gọi lập kế hoạch (`run_planning_call`)

- Đầu vào prompt: tên nguồn, ngữ cảnh loại tri thức (tên — mô tả), chiến lược, tối đa 300 khái niệm sắp theo số lần xuất hiện giảm dần (kèm quyết định đối chiếu), danh sách UPDATE, ý kiến người duyệt (tùy chọn, `user_note`), số trang mục tiêu.
- Số trang mục tiêu theo n = số khái niệm: single_pass max(3, min(30, n/2)); standard max(8, min(80, n/3)); hierarchical max(15, min(200, n/3)) (chia nguyên).
- Ràng buộc đầu ra: slug phẳng, chữ thường, nối gạch ngang; trả **chỉ** JSON `{pages: [{action CREATE|UPDATE, slug, title, page_type, entity_names[], related_kb_pages[], priority}], estimated_page_count, compilation_notes}`.
- Nhiệt độ 0,1; timeout 120 s; parse JSON dễ dãi.

### 5.4. Duyệt kế hoạch và tự duyệt

- `settings.mrp_auto_approve_plan` (bool) bật thì kế hoạch được tự duyệt ngay sau REDUCE.
- Tự duyệt: kế hoạch `pending_review` → `approved`, ghi chú "Auto-approved"; nguồn `wiki_status = refining`, thông điệp "Plan approved — compiling wiki pages...", cập nhật trạng thái kép; lấy attempt id hiện hành rồi enqueue `ingest_refine_task(source_id[, attempt_id])`; trả `{status: "plan_auto_approved", job_id}`.
- Không tự duyệt → trả `{status: "plan_ready", plan_id}`; người dùng duyệt qua API kế hoạch (đặc tả nạp tài liệu), có thể kèm ý kiến để lập lại kế hoạch.

### 5.5. REFINE (`writer.py`)

Hằng số: tối đa 4 trang viết song song; timeout 300 s mỗi lời gọi LLM; chế độ "phức tạp" khi có > 8 mục bằng chứng hoặc nội dung cũ > 3 000 ký tự; agent tối đa 10 bước. Nhiều lượt: ngưỡng co của lượt mở rộng 0,9; đánh bóng khi ≥ 3 lô; tỉ lệ dự trữ 0,7; ngân sách mỗi lượt 0,5; 2 lần thử lại mở rộng; khoảng gần tầng B 5 000 ký tự; tỉ lệ mất dòng mỗi lượt 0,2.

**`PageWriteResult`** (dataclass): `slug`, `title`, `page_type`, `action` (CREATE | UPDATE), `content_md`, `summary`, `citations=[]`, `entity_names=[]`, `related_kb_pages=[]`. Có `to_dict()` và `from_dict(d)` (mặc định page_type `concept`, action `CREATE`). Pha VERIFY gắn thêm thuộc tính `status`; pha COMMIT đọc bằng getattr có giá trị mặc định.

**`_pass_drops_rows(before, after) -> bool`**: false nếu `before` không có định danh dòng bảng nào; ngược lại true khi số định danh mất / số định danh trước > 0,2 (dùng `table_row_identities`, `missing_row_identities` của write guard). Test: 5→5 false, 5→4 false, 5→2 true, không có bảng false.

**Gom bằng chứng** (`assemble_evidence(plan_item, claims, full_text)`): chọn nhận định có subject trùng (không phân biệt hoa thường) một entity_name của mục kế hoạch hoặc chứa tên đó như một từ trọn vẹn. Mỗi mục: statement, subject, confidence, source_excerpt (đoạn full_text từ absolute_offset dài min(evidence_length, 2 000), mặc định 200), absolute_offset, evidence_length.

**Ngân sách nguồn**: `context_window_tokens` của model × 4 ký tự × 0,85, trần 2 500 000 ký tự; không biết cửa sổ → 120 000 ký tự.

**Chọn phần văn bản**: dùng nút lá của outline; không có outline thì tách theo heading cấp 1–4, hoặc khối đoạn văn ~3 000 ký tự.
- Tầng A: phần chứa offset của bằng chứng.
- Tầng B: phần kề phần A hoặc có bằng chứng trong 5 000 ký tự; giữ nếu còn ngân sách.
- Tầng C: phần còn lại; chỉ hiện dấu "bỏ qua" (nêu tên 3 phần đầu, rồi "và N phần nữa").

**Chọn chiến lược**: một lượt khi (độ dài phần liên quan + phần bằng chứng + nội dung cũ) < 0,7 × ngân sách; ngược lại nhiều lượt với ngân sách mỗi lượt 0,5 × ngân sách (cấu hình `mrp_multipass_writer_enabled`, mặc định true; tắt thì luôn một lượt).

**Ý đồ prompt hệ thống của writer**: biên soạn chứ không tóm tắt — giữ số liệu, quy định, các bước, ví dụ, định nghĩa; viết cùng ngôn ngữ với nguồn; đoạn mở đầu rồi các mục H2, in đậm thuật ngữ, mục "Xem thêm"; không tạo mục trích dẫn hay chú thích cuối trang; chỉ liên kết tới slug trong danh sách "trang hiện có"; giữ nguyên marker ảnh dạng `image://<uuid>`, không bịa marker; tối thiểu 150 từ.

**Writer đơn giản**: một lời gọi, nhiệt độ 0,15. Đầu vào: action, slug, title, loại trang, danh sách slug có thể liên kết (trừ chính nó), nội dung cũ (với UPDATE), ngữ cảnh nguồn đã chọn, danh mục bằng chứng dạng "[ĐỘ TIN CẬY] chủ thể / nhận định", các marker ảnh trong phạm vi ±1 500 ký tự quanh bằng chứng. Tóm tắt: các dòng không phải heading đầu tiên cho tới khi > 100 ký tự, cắt 300.

**Writer phức tạp (agent)**: vòng lặp gọi công cụ với 3 công cụ: `read_kb_page(slug)` (đọc trang cùng phạm vi), `read_source_excerpt(start_char, length)` (length mặc định 5 000, tối đa 10 000), `finish(content_md, summary)`. Không gọi `finish` → lấy văn bản trợ lý cuối, hoặc một trang chỉ có tiêu đề và dòng "(content generation incomplete)".

**Nhiều lượt**: lô 1 là lượt tạo; mỗi lô tiếp theo là lượt mở rộng (prompt hệ thống riêng: giữ nguyên bản nháp, chỉ nối thêm mục mới, đầu ra ≥ bản nháp + 60 % nội dung mới) với tối đa 3 lần thử; chấp nhận khi độ dài ≥ 0,9 × bản trước và `_pass_drops_rows` là false; hết lượt thử → nối cứng các phần của lô dưới dạng mục H2 "tiêu đề" + nội dung. Lượt đánh bóng (khi ≥ 3 lô hoặc có marker ảnh; nhiệt độ 0,1) chỉ được nhận nếu độ dài ≥ 0,95 × bản trước và không mất dòng.

**`run_refine_phase(session, source, plan, chunk_extracts, full_text, llm, embedding_provider, kt_slug, tracker) -> list[PageWriteResult]`**:
1. Sắp mục kế hoạch theo `priority` tăng dần (thiếu = 99); mọi slug trong kế hoạch đều được coi là có thể liên kết. Tiến độ 78.
2. Mỗi trang viết trong session DB riêng, tối đa 4 song song.
3. Ngoại lệ khi viết → `content_md = make_failure_stub(title, lỗi)`, summary = title.
4. Thành công trên trang đã có nội dung: nếu `check_machine_rewrite` sẽ từ chối thì ghi cảnh báo sớm (không chặn ở đây).
5. Lưu `plan_json["_page_drafts"]` = danh sách `to_dict()` và commit; lỗi lưu chỉ ghi cảnh báo.

### 5.6. VERIFY (`verifier.py`)

`run_verify_phase(session, source, page_results, chunk_extracts, full_text, llm, embedding_provider, tracker)`:
1. (88 %) Độ phủ: khái niệm có ≥ 3 lần xuất hiện mà không trang nào nhắc tới → chỉ ghi log.
2. (91 %) Mâu thuẫn (`check_conflicts`, ngưỡng 0,80): bỏ qua slug dành riêng và trang `source/`. Embed "title + summary + 3 000 ký tự đầu nội dung"; tìm top 3 trang kho; với trang có sim ≥ 0,80 gửi LLM (mỗi văn bản 1 500 ký tự) và nhận JSON `{contradicts, description}`. Có mâu thuẫn → chèn lên đầu trang một callout `[!contradiction]` tiếng Việt nêu trang kia và mô tả.
3. Trạng thái (`assess_page_status(content_md)`): < 600 ký tự hoặc < 1 wikilink → `seed`; < 2 000 hoặc < 3 → `developing`; < 4 000 hoặc < 5 → `mature`; còn lại → `evergreen`. Trang `source/` luôn `evergreen`. Gán vào thuộc tính `status` của kết quả.
4. (95 %) Trích dẫn: `CitationVerifier.verify_page(page_slug, content_md, source_text)`; báo cáo có nội dung bịa → `apply_citation_callout`.
5. Trang là stub lỗi được giữ nguyên (không đánh giá).

### 5.7. Gộp nội dung (`merger.py`)

Hằng số: ngưỡng co thân 0,7; timeout 120 s; tỉ lệ mất dòng tối đa 0,2; `APPEND_FALLBACK_HEADING` = "## Bổ sung từ nguồn mới".

**`append_fallback(existing, incoming)`**: nội dung cũ (cắt khoảng trắng cuối) + dòng trống + `---` + dòng trống + `APPEND_FALLBACK_HEADING` + dòng trống + nội dung mới đã bỏ heading H1 đầu, kết thúc bằng xuống dòng. Nội dung mới sau khi bỏ H1 rỗng → trả nguyên nội dung cũ.

**`merge_page_content(llm, existing_content, new_content, slug) -> str`**:
1. Nội dung cũ sau cắt < 50 ký tự, hoặc hai nội dung giống hệt → trả nội dung mới.
2. Gọi LLM gộp. Ý đồ: giữ mọi dữ kiện của cả hai, bỏ trùng, tổ chức theo mục H2, giữ wikilink và marker ảnh, cùng ngôn ngữ; chỉ trả Markdown.
3. Dùng `append_fallback` khi: kết quả < 0,7 × độ dài lớn hơn trong hai đầu vào; hoặc mất > 20 % định danh dòng bảng so với nội dung cũ; hoặc có ngoại lệ/timeout.
4. Thành công → kết quả đã cắt khoảng trắng.

### 5.8. COMMIT (`pipeline.py`)

`pipeline.py` import `resolve_wiki_scopes` ở mức module dưới tên `_resolve_wiki_scopes` (test thay thế thuộc tính này).

**`run_commit_phase(session, source, page_results, plan, embedding_provider, embedding_spec, kt_slug, tracker) -> dict`** (test gọi bằng 8 tham số vị trí):
1. `wiki_scopes = _resolve_wiki_scopes(session, source)`.
2. `failed_slugs` = danh sách slug (sắp xếp) có nội dung là stub lỗi (`is_failure_stub`). Các trang này **không** được chạm tới: không tra `get_page_by_slug`, không create/update.
3. Lấy LLM gộp bằng `ProviderRegistry(session).get_llm()`; `ProviderRegistry` phải được tra từ module `app.ai.registry` lúc chạy (test thay lớp ở đó); lỗi → không có LLM gộp.
4. Tiến độ 95. Các hàm dịch vụ phải được gọi qua thuộc tính module (`wiki_service.get_page_by_slug`, `wiki_service.apply_create`, `wiki_service.apply_update`, `wiki_service.regenerate_index`, `wiki_service.append_log`, `wiki_chunk_service.index_wiki_page_chunks`, `source_status.update_source_dual_status`) để monkeypatch có hiệu lực.
5. Với mỗi phạm vi, mỗi kết quả không phải stub:
   - Lấy khóa advisory trong transaction theo băm chuỗi "slug:scope_type:scope_id".
   - CREATE: nếu `get_page_by_slug(session, slug, scope_type=, scope_id=)` thấy trang → chuyển sang UPDATE; ngược lại `apply_create` (loại tri thức `[kt_slug]` nếu có, nguồn `[source.id]`, phạm vi, status = thuộc tính `status` của kết quả hoặc `seed`).
   - UPDATE: lấy trang hiện có; nếu có nội dung cũ, có LLM gộp, nguồn này chưa có trong `source_ids` của trang và nội dung cũ sau cắt > 100 ký tự → `merge_page_content`. Gọi `apply_update` bằng keyword (`slug`, `new_content_md`, `summary`, `title`, `add_knowledge_type_slug=kt_slug`, `add_source_id=source.id`, `scope_type`, `scope_id`, `status`). Trả None (không có trang) → `apply_create` và tính là tạo mới; ngược lại tính là cập nhật.
   - Flush; nếu có `embedding_spec` → `index_wiki_page_chunks(session, page, spec_id=embedding_spec.id)` (lỗi chỉ cảnh báo).
   - Ngoại lệ của từng trang chỉ ghi log, không dừng vòng lặp.
6. Sau mỗi phạm vi: `regenerate_index`; `append_log` dạng "MRP: ingested '<title hoặc file_name hoặc id>': +N created, ~M updated". Không dựng lại `_hot`.
7. Nếu có `plan` → status `done` (plan có thể là None).
8. Đọc lại nguồn bằng `session.get(Source, id)` và đặt: `pipeline_phase = commit`, `wiki_status = ready`, `wiki_progress = 100`, `wiki_progress_message` = "Done" hoặc, khi có trang bị bỏ qua, "Done (N page(s) skipped — generation failed: <tối đa 5 slug, ngăn bằng dấu phẩy>)" (phải chứa từ "skipped"), `wiki_error_message = None`, `auto_recover_count = 0`; gọi `update_source_dual_status`.
9. Commit. Trả `{pages_created, pages_updated, pages_skipped: failed_slugs}`.

### 5.9. Điều phối và chạy tiếp

**`run_mrp_pipeline(session, source, full_text, tracker, registry, kt_slug, kt_name, kt_desc, attempt_id_str=None) -> dict`**:
1. Chạy tiếp: nếu `pipeline_phase = plan_review` và có kế hoạch `pending_review`/`approved` → nếu đã `approved` hoặc bật tự duyệt thì tự kích hoạt refine (§5.4), ngược lại trả `plan_ready`. Nếu pha đang là refine/verify/commit → trả `{status: "already_in_<pha>"}`.
2. Lấy LLM và embedding provider (task `document`, không bắt buộc).
3. Đặt pha map, chạy MAP; không có chunk nào thành công → ValueError.
4. Đặt pha reduce, chạy REDUCE; tiến độ 80 "Compilation plan ready".
5. Tự duyệt hoặc trả `plan_ready`.

**`run_refine_pipeline(session, source, full_text, tracker, registry, kt_slug, kt_name, kt_desc)`**:
1. Kế hoạch phải tồn tại với status approved / in_progress / done, ngược lại ValueError.
2. Nạp các chunk extract `done`; lấy embedding provider và spec đang hoạt động.
3. Nếu pha chưa là verify/commit: đặt pha refine, kế hoạch `in_progress`, chạy REFINE, rồi đặt pha verify. Ngược lại nạp `_page_drafts` từ kế hoạch (thiếu thì chạy lại REFINE).
4. Chạy VERIFY rồi COMMIT.

### 5.10. Tích hợp write guard — tóm tắt

| Điểm | Hành vi |
|---|---|
| Writer khi lỗi | Ghi stub lỗi (`make_failure_stub`) thay vì ném lỗi |
| Writer nhiều lượt | Lượt mở rộng / đánh bóng làm mất > 20 % dòng bảng bị loại (`_pass_drops_rows`) |
| Writer trên trang cũ | Cảnh báo sớm nếu guard sẽ từ chối |
| Merger | Mất > 20 % dòng → nối thêm thay vì dùng bản gộp |
| Commit | Bỏ qua stub lỗi, báo trong `pages_skipped` và thông điệp tiến độ |
| `apply_update` | `check_machine_rewrite` từ chối → trang giữ nguyên, không revision |
| Sửa qua MCP | `check_agent_write` (đặc tả MCP) |
