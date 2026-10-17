# 06 — MCP, Kho kỹ năng, Prompt và Quản trị hệ thống

Tài liệu đặc tả clean-room theo `QUY_TAC_DAC_TA.md`. Phạm vi gồm:

- **MCP:** máy chủ `app/mcp/*`, gồm công cụ, tài nguyên, xác thực, ghi log truy vấn và dữ liệu cho báo cáo "lỗ hổng tri thức".
- **Kỹ năng:** kho kỹ năng (skills), luồng đóng góp kỹ năng (skill contributions) và kho prompt.
- **Quản trị:** cài đặt quản trị, mô hình tùy chỉnh và OCR, thống kê và cuộn số liệu hằng ngày, thông báo cùng kênh gửi ra ngoài, nhật ký kiểm toán dạng chuỗi HMAC.

Mọi thông báo lỗi trong ngoặc kép phải trả về **đúng nguyên văn**, vì giao diện và test so khớp chuỗi.

---

## 0. Quy ước chung

- Tất cả router HTTP gắn dưới tiền tố `/api`, trừ khi ghi khác.
- **Xác thực:**
  - "get_current_user" nghĩa là cần người dùng đăng nhập (xem tài liệu 02).
  - "require_permission(X)" nghĩa là cần quyền X; admin luôn đạt.
  - Lỗi xác thực và phân quyền chung theo tài liệu 02.
- **Lỗi HTTP** trả dạng `{"detail": ...}` theo FastAPI. Riêng 409 trùng kỹ năng có `detail` là object.
- **Nhãn mật** (security label) theo thứ tự tăng dần: `PUBLIC < INTERNAL < RESTRICTED < CONFIDENTIAL`.
  - Hàm chuẩn hóa nhãn và mệnh đề lọc theo nhãn đã đặc tả ở tài liệu 02 và 04, ở đây chỉ dùng lại.
  - Giá trị mặc định khi thiếu là `INTERNAL`.
- **Phân quyền:** "admin" là `Employee.role == "admin"`. Tập quyền người dùng lấy từ engine quyền của tài liệu 02 (hàm `_get_user_permissions(user)` trả tập chuỗi quyền).

---

## 1. Máy chủ MCP

### 1.1 Module và điểm vào

| Module | Ký hiệu công khai | Mô tả |
|---|---|---|
| `app.mcp.server` | `create_mcp_server() -> FastMCP` | Tạo `FastMCP("Arkon", instructions=...)`, gọi `register_tools(mcp)`, `register_resources(mcp)`, rồi gắn middleware `ScopedToolsMiddleware()`. |
| `app.mcp.tools` | `register_tools(mcp) -> None` | Đăng ký toàn bộ công cụ ở mục 1.7. |
| `app.mcp.tools` | `_get_identity() -> (identity, None)` hoặc `(None, str_lỗi)` | Hàm async. Test patch tại `app.mcp.tools._get_identity`. |
| `app.mcp.tools` | `_get_allowed_source_ids(identity, session=None) -> Optional[set[str]]` | Hàm async. Test patch tại `app.mcp.tools._get_allowed_source_ids`. |
| `app.mcp.tools` | `forwarded_role(headers, trust: bool) -> str` | Xem 1.3. |
| `app.mcp.resources` | `register_resources(mcp) -> None` | Đăng ký `arkon://about` và `arkon://wiki-index`. |
| `app.mcp.permissions` | `ToolRequirement`, `ANY_AUTHENTICATED`, `CAN_CONTRIBUTE_WIKI`, `CAN_REVIEW_WIKI`, `CAN_CREATE_WIKI_DIRECT`, `kb_tool`, `requirement_for`, `REQUIRES_ATTR` | Xem 1.5. |
| `app.mcp.middleware` | `ScopedToolsMiddleware` | Xem 1.5. |
| `app.mcp.logging` | `current_identity` (ContextVar), `logged_tool(tool_name, query_arg=None)` | Xem 1.6. |
| `app.services.mcp_auth_service` | `ResolvedIdentity`, `MCPAuthService` (hoặc instance dùng chung) | Xem 1.2. |

**Ràng buộc để test patch được**

- **Tra cứu lúc gọi.** Trong mọi công cụ, `_get_identity` và `_get_allowed_source_ids` là hàm cấp module, tra tên lúc gọi, không gắn sẵn lúc định nghĩa.
- **Phiên CSDL.** Mỗi công cụ lấy `async_session_factory` bằng cách import trễ từ `app.database` ngay trong thân hàm, rồi mở phiên bằng `async with async_session_factory() as session`.
- **Dịch vụ wiki.** Gọi qua thuộc tính module `app.services.wiki_service` (vd. `wiki_service.render_scoped_index`, `wiki_service.get_page_by_slug`, `wiki_service.list_pages`), để `patch` trên module có tác dụng.
- **Kho lưu trữ.** Tải file qua `app.services.storage_service.storage_service.download_file(key)`.
- **Tài nguyên.** `resources.py` import `_get_identity` từ `app.mcp.tools` ngay trong handler, không import ở đầu file.

**Hướng dẫn hệ thống** (instructions) của server là đoạn văn tiếng Anh ngắn. Nội dung tự viết, chỉ cần truyền đạt:

- Luôn tìm trong Arkon trước khi trả lời.
- Thứ tự dùng công cụ: `search_wiki` → `read_wiki_page` → `read_wiki_index` → các công cụ văn bản gốc (`get_source_outline`, `get_source_pages`).
- Với kỹ năng: `list_skills` → `read_skill` → `read_skill_file`.
- Luôn trích dẫn slug trang hoặc ID văn bản kèm số trang.

### 1.2 Danh tính và token

**`ResolvedIdentity`** là dataclass:

| Trường | Kiểu | Mặc định | Ý nghĩa |
|---|---|---|---|
| employee_id | UUID | — | Nhân viên |
| employee_name | str | — | |
| department_ids | list[UUID] | [] | |
| department_names | list[str] | [] | |
| allowed_knowledge_types | Optional[list[str]] | None | None = không giới hạn loại tri thức (danh sách slug) |
| allowed_source_ids | Optional[list[UUID]] | None | None = không giới hạn văn bản |
| is_admin | bool | False | |
| permissions | list[str] | [] | |
| delegated_role | Optional[str] | None | Vai trò được ủy quyền qua header chuyển tiếp |
| clearance_level | str | "INTERNAL" | Nhãn mật tối đa được đọc |

Các phương thức:

- **`allowed_labels`** (property): danh sách nhãn ≤ clearance_level.
- **`has_permission(perm)`**: True nếu perm có trong permissions.
- **`has_any_permission(*perms)`**: True nếu có ít nhất một quyền trong danh sách.

**`MCPAuthService`**

- **`hash_token(token)`**
  - Trả HMAC-SHA256 dạng hex.
  - Khóa là `settings.mcp_token_pepper`, thông điệp là token.
- **`generate_token(session, employee)`**
  - Sinh token `"ark_"` + chuỗi urlsafe ngẫu nhiên 32 byte, trả plaintext đúng một lần.
  - Lưu `mcp_token_hash`, `mcp_token_prefix` (12 ký tự đầu) và `mcp_token_rotated_at`; xóa cột plaintext cũ nếu có.
- **`revoke_token(session, employee)`**: xóa hash và prefix.
- **`verify_token(session, token) -> Optional[ResolvedIdentity]`**
  - Tìm nhân viên **đang hoạt động** có `mcp_token_hash` khớp.
  - Cập nhật `last_connected`, nhưng chỉ khi lần trước cách hiện tại hơn 60 giây.
    - Đối tượng trả về có thuộc tính `bumped_last_connected` (bool) cho biết đã cập nhật hay chưa.
    - Người gọi chỉ commit khi giá trị này là True.
  - Phân giải phạm vi, rồi đặt `clearance_level` theo `employee.clearance_level` đã chuẩn hóa.
- **`verify_sso_token(session, token) -> (identity, None) | (None, mã_lỗi)`**
  - Dùng `employee_from_access_token` của router SSO (tài liệu 02) để ra nhân viên.
  - Phân giải phạm vi như trên. Người gọi commit.
- **Phân giải phạm vi**:
  1. Admin → `is_admin=True`, không giới hạn.
  2. Có quyền `doc:read` phạm vi `all` → không giới hạn: cả hai danh sách allowed là None.
  3. Có `doc:read` phạm vi `own_dept`:
     - `allowed_source_ids` = các văn bản toàn cục (không có dòng nào trong `source_departments`) **cộng** các văn bản gắn phòng ban của người dùng.
  4. Còn lại → `allowed_source_ids = []`.
- **`apply_scope_filter(query, identity)`**: thêm điều kiện vào truy vấn trên bảng `sources`, gồm:
  - **Luôn có:**
    - Lọc nhãn theo `identity.clearance_level`.
    - Lọc văn bản cá nhân: văn bản cá nhân chỉ hiện với chủ sở hữu, kể cả với admin.
  - **Không lọc thêm** nếu cả `allowed_source_ids` và `allowed_knowledge_types` đều None.
  - **Ngược lại**, thêm điều kiện HOẶC giữa hai vế:
    - id thuộc `allowed_source_ids`;
    - loại tri thức có slug thuộc `allowed_knowledge_types`.
- **`page_source_clause(identity)`** trả về mệnh đề lọc trên `wiki_pages`.
  - **Quy tắc ẩn:** trang bị ẩn nếu **bất kỳ** id nào trong `WikiPage.source_ids` trỏ tới văn bản mà danh tính không đọc được, xét theo nhãn, tính cá nhân và phạm vi.
  - Trang không có nguồn thì luôn qua.
  - **Với admin:** bỏ giới hạn phạm vi (coi cả hai danh sách là None) nhưng vẫn áp nhãn và tính cá nhân.
  - **Thuộc tính thiếu:** phải đọc `employee_id`, `allowed_*` và `is_admin` theo kiểu khoan dung, tức thiếu thuộc tính thì coi là None hoặc False. Test dùng `SimpleNamespace` không có `employee_id`.

### 1.3 `_get_identity()` — luồng xác thực mỗi lời gọi

**Bước 1. Lấy bearer token**

- **Có ngữ cảnh HTTP:** đọc header `Authorization: Bearer <token>`.
- **Không có ngữ cảnh HTTP** (chạy stdio):
  - Dùng biến môi trường `MCP_TOKEN`.
  - Nếu biến rỗng và `MCP_STDIO_ADMIN` ∈ {true, 1, yes} (không phân biệt hoa thường): trả một danh tính admin cố định, có `clearance_level = "CONFIDENTIAL"`, tên hiển thị kiểu "stdio admin".

**Bước 2. Token rỗng**

Trả chuỗi lỗi bắt đầu bằng "Authentication required". Nội dung giải thích cách cấu hình header `Authorization: Bearer ark_…` trong Claude Desktop hoặc client MCP. Lời văn tự viết.

**Bước 3. Token SSO**

Token **không** bắt đầu bằng `ark_` và có **đúng 2 dấu chấm** được coi là JWT SSO và chuyển qua `verify_sso_token`. Các mã lỗi được đổi thành thông báo:

| Mã | Thông báo |
|---|---|
| sso_disabled | "SSO tokens are not accepted by this server. Use an Arkon MCP token (ark_…)." |
| sso_token_expired | "SSO token expired. Sign in again." |
| sso_token_invalid (và mọi mã lạ) | "Invalid SSO token." |
| sso_client_not_allowed | "This SSO client may not call Arkon MCP (see SSO_MCP_CLIENTS)." |
| sso_email_conflict | "The SSO account's email belongs to another linked Arkon account." |
| sso_email_unverified | "The SSO account's email is not verified, so it cannot be linked to the existing Arkon account." |
| sso_inactive | "Arkon account is inactive. Contact your administrator." |

Nhánh SSO bỏ qua mọi header chuyển tiếp danh tính. Thành công thì commit, rồi đặt `current_identity`.

**Bước 4. Token `ark_`**

- Gọi `verify_token`. Sai hoặc nhân viên không hoạt động → "Invalid or inactive MCP token. Contact your administrator."
- Commit nếu `bumped_last_connected` là True.

**Bước 5. Danh tính chuyển tiếp** (dành cho chatbot gọi thay người dùng)

1. Tính `user_role = forwarded_role(request.headers, settings.mcp_trust_forwarded_identity)`.
2. Nếu `user_role` rỗng, giữ danh tính của token.
3. Nếu `user_role` khác rỗng:
   - `delegated_role = user_role`.
   - `clearance_level` = chuẩn hóa header `x-user-clearance`; thiếu thì là `INTERNAL`.
   - **Vai trò `admin`:** `is_admin = True`.
   - **Vai trò khác:** `is_admin = False`, rồi khớp phòng ban từ các header `x-department-id`, `x-department-code`, `x-department-name`. Chỉ xét phòng ban đang hoạt động, đi lần lượt các bước sau và dừng ở bước đầu cho kết quả khác rỗng:
     1. `external_id` bằng `x-department-id`.
     2. `code` bằng `x-department-code`, không phân biệt hoa thường.
     3. `name` bằng `x-department-name`.
     4. Dự phòng cho phòng ban cũ (external_id rỗng, đang hoạt động): tên chứa mã hoặc tên, không phân biệt hoa thường.
     5. Nếu vẫn không có và header mã có giá trị: tự tạo `Department(name=mã, description=tên hoặc mã)`, trừ khi đã tồn tại phòng ban cùng tên (khi đó dùng phòng ban đó).
   - **Kết quả khớp phòng ban:**
     - Khớp được: `department_ids` và `department_names` theo kết quả; `allowed_source_ids` = văn bản của các phòng ban đó.
     - Không khớp: hai danh sách phòng ban rỗng; `allowed_source_ids` = chỉ văn bản toàn cục.

**Bước 6.** Đặt `current_identity`, rồi trả `(identity, None)`.

**`forwarded_role(headers, trust)`**

- `trust` False → `""`.
- `trust` True → giá trị header `x-user-role` đã strip và lowercase, hoặc `""` nếu không có.

Cấu hình `settings.mcp_trust_forwarded_identity` (env `MCP_TRUST_FORWARDED_IDENTITY`) **mặc định False**.

**Các khóa cấu hình liên quan**

| Khóa | Mặc định |
|---|---|
| `mcp_token_pepper` | — |
| `portal_base_url` | — |
| `sso_mcp_clients` | `"cahy-chatbot"` |
| `MCP_TOKEN` (env) | — |
| `MCP_STDIO_ADMIN` (env) | — |

### 1.4 `_get_allowed_source_ids(identity, session=None)`

- **Hai cờ trung gian:**
  - `label_restricted`: clearance đã chuẩn hóa khác mức cao nhất (CONFIDENTIAL).
  - `open_scope`: là admin, hoặc cả hai danh sách allowed đều None.
- **Trả None** (không giới hạn) khi đồng thời:
  - không `label_restricted`;
  - `open_scope`;
  - không tồn tại văn bản cá nhân nào của **người khác**.
- **Còn lại:** trả tập id (chuỗi) của các văn bản `status = ready` qua `apply_scope_filter`. Tập có thể rỗng.
- Không truyền session thì tự mở phiên.

**Các hàm phụ trợ quyền ghi wiki dùng trong công cụ**

- **Duyệt:** admin, hoặc có `wiki:write:all`.
- **Đóng góp trên trang phòng ban:** có `wiki:write:all`; hoặc có `wiki:write:own_dept` **và** phòng ban của trang thuộc phòng ban của người dùng.
- **Đóng góp trên trang toàn cục:** có bất kỳ quyền `wiki:write:*` nào.

**Gợi ý ngoài phạm vi** (dùng trong search_wiki và read_wiki_page)

- Gom các trang phòng ban khớp nhưng người dùng không xem được, theo phòng ban.
- In số lượng và tên phòng ban, kèm lời mời liên hệ quản trị viên phòng ban đó.
- **Không bao giờ** lộ tiêu đề trang.

### 1.5 Phân quyền công cụ và middleware

- **`REQUIRES_ATTR`** = `"__arkon_requires__"`.
- **`ToolRequirement(predicate, label)`** có `allows(identity) -> bool`.
- **Các yêu cầu định sẵn:**

| Hằng | Điều kiện | label |
|---|---|---|
| ANY_AUTHENTICATED | luôn True | "authenticated" |
| CAN_CONTRIBUTE_WIKI | admin, hoặc có một trong `wiki:write:own_dept`, `wiki:write:all` | "wiki:write:*" |
| CAN_REVIEW_WIKI | admin, hoặc `wiki:write:all` | "wiki:write:all" |
| CAN_CREATE_WIKI_DIRECT | bằng CAN_REVIEW_WIKI | |

- **`kb_tool(mcp, *, requires=ANY_AUTHENTICATED, **kwargs)`** trả decorator. Decorator gắn thuộc tính `REQUIRES_ATTR` lên hàm, rồi ủy quyền cho `mcp.tool(**kwargs)`.
- **`requirement_for(fn)`** trả requirement đã gắn, mặc định `ANY_AUTHENTICATED`.

**`ScopedToolsMiddleware.on_list_tools`** chỉ phục vụ trải nghiệm người dùng; kiểm tra quyền bên trong từng công cụ vẫn là quyết định cuối.

- Lấy danh tính bằng `_get_identity` (import từ `app.mcp.tools`).
- **Không có danh tính:**
  - Chỉ trả các công cụ có yêu cầu `ANY_AUTHENTICATED`.
  - Mỗi mô tả được thêm tiền tố gợi ý "[Authenticate to use]". Mô tả rỗng thì chỉ còn gợi ý.
- **Có danh tính:** lọc theo `requirement.allows(identity)`.

### 1.6 Ghi log truy vấn (`mcp_query_log`)

- **`current_identity`**: ContextVar, mặc định None.
- **`logged_tool(tool_name, query_arg=None)`**: decorator bọc hàm công cụ async, ghi một dòng log cho mỗi lần gọi.

**Các trường được tính**

- **`latency_ms`**: thời gian chạy công cụ.
- **`status`**, suy từ chuỗi kết quả đã lowercase:
  - `denied` nếu chứa một trong các gợi ý:
    - lỗi xác thực: "authentication required", "invalid or inactive mcp token", "no http request context";
    - từ chối: "access denied", "you do not have permission", "not allowed", "forbidden".
  - `error` nếu bắt đầu bằng "error" hoặc "failed".
  - `ok` trong mọi trường hợp còn lại.
  - Nếu công cụ ném ngoại lệ: status `error`, `error_message` dạng "TênLớp: thông điệp", và ngoại lệ được ném lại.
- **`result_count`** (chỉ tính khi `ok`), thứ tự ưu tiên:
  1. 0 nếu chứa một trong: "no wiki pages found", "no sources found", "no results", "no pages found", "no drafts pending", "no skills found".
  2. Con số trong các mẫu "N result(s)" / "N results" / "N result", "N pages found", "N sources found", "N drafts pending", "N skill(s)", "N match(es)" (không phân biệt hoa thường).
  3. 1 với các công cụ đọc đơn: read_wiki_page, get_source, read_skill, read_skill_file.
  4. Còn lại: None.
- **`query_text`**: giá trị kwarg `query_arg`; không có thì lấy đối số vị trí đầu tiên nếu là chuỗi. Cắt còn 2000 ký tự.
- **`error_message`**: cắt còn 1000 ký tự.
- **`employee_id`**: lấy từ `current_identity`.

**Cách ghi:** ghi kiểu "bắn và quên" trong phiên riêng. Mọi lỗi khi ghi bị nuốt và không ảnh hưởng kết quả công cụ.

Các dòng có `result_count = 0` của nhóm công cụ tìm kiếm là nguồn dữ liệu cho báo cáo lỗ hổng tri thức (mục 8.3).

**Bảng `mcp_query_log`**

| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | UUID PK | |
| created_at | timestamptz | index |
| employee_id | UUID FK employees, ON DELETE SET NULL | index |
| tool_name | varchar(80) | index |
| query_text | text, null | |
| result_count | int, null | |
| latency_ms | int, null | |
| scope_metadata | JSONB, null | |
| result_ids | JSONB, null | |
| status | varchar(20), mặc định "ok" | ok, error, denied |
| error_message | text, null | |

Index ghép: (created_at, result_count).

### 1.7 Danh mục công cụ MCP

**Quy ước chung cho mọi công cụ**

- Đều async, trả chuỗi Markdown.
- Bước đầu tiên luôn là `_get_identity()`. Có lỗi thì trả nguyên chuỗi lỗi.
- Tham số số được kẹp (clamp) trong khoảng ghi ở bảng.
- Công cụ tìm kiếm được bọc `logged_tool`, với `query_arg` như ghi chú.

| Công cụ | Tham số (kiểu = mặc định) | Yêu cầu | Log query_arg |
|---|---|---|---|
| search_wiki | query: str; top_k: int = 10 (1–50) | ANY | query |
| read_wiki_index | — | ANY | |
| read_wiki_page | slug: str | ANY | slug |
| get_document_relations | doc_number: str = None; article_number: str = None; slug: str = None; limit: int = 50 (1–200) | ANY | |
| list_wiki_pages | page_type = None; knowledge_type = None; query = None; limit = 50 (1–50); offset = 0 | ANY | query |
| get_source | source_id: str | ANY | |
| get_source_outline | source_id: str | ANY | |
| get_source_pages | source_id: str; pages: str | ANY | |
| search_source_content | query: str; limit = 10; offset = 0 | ANY | query |
| list_sources | status = "ready"; knowledge_type = None; query = None; limit = 20; offset = 0 | ANY | query |
| list_knowledge_types | — | ANY | |
| get_knowledge_type_docs | knowledge_type_slug: str; limit = 10 | ANY | |
| edit_wiki_page | slug; content_md; note = None; scope_type = None; scope_id = None; base_version: int = None; allow_row_removal: bool = False | CAN_CONTRIBUTE_WIKI | |
| create_wiki_page | slug; title; content_md; page_type = "concept"; knowledge_type_slugs: list[str] = None; scope_type = "global"; scope_id = None; note = None | CAN_CONTRIBUTE_WIKI (kiểm thêm bên trong) | |
| query_table | source_id: str; sql_query: str; max_rows: int = 50 (1–100) | ANY | sql_query |
| list_skills | query: str = None; limit = 30 (1–100) | ANY | query |
| read_skill | slug: str | ANY | slug |
| read_skill_file | slug: str; path: str | ANY | path |

#### search_wiki

- Ngưỡng `MIN_SIM_FLOOR = 0.30`.
- Nhúng câu hỏi với task "search_query", rồi gọi tìm kiếm hợp nhất (tài liệu 04) với các tham số:
  - lọc: allowed_kt_slugs, department_ids, all_scopes = is_admin, allowed_source_ids từ `_get_allowed_source_ids`, clearance, page_filter = page_source_clause(identity);
  - xếp hạng: bật reranker và MMR;
  - kiểm tra ngoài phạm vi khi không phải admin.
- **Lỗi:**
  - Cả nhánh trang wiki lẫn nhánh văn bản gốc đều lỗi và không có kết quả khớp số hiệu → "Tìm kiếm thất bại: cả trang wiki và văn bản gốc đều bị lỗi. Thử lại sau hoặc báo quản trị viên."
  - Lỗi một phần → dòng cảnh báo liệt kê các nhánh lỗi, dùng nhãn "trang wiki", "văn bản gốc", "tra cứu theo số hiệu".
  - `rerank_mode == "local"` → thêm ghi chú thông tin rằng đang dùng xếp hạng cục bộ.
- **Có khớp chính xác theo số hiệu văn bản:** khối đầu tiên có tiêu đề "KẾT QUẢ TRA CỨU CHÍNH XÁC THEO SỐ HIỆU VĂN BẢN", gồm số hiệu, đường dẫn điều khoản, tiêu đề, nội dung và callout cảnh báo hiệu lực nếu có.
- **Không có kết quả:** 'No knowledge base matches found for: "<query>"', kèm gợi ý ngoài phạm vi nếu có.
- **Có kết quả:**
  - Tiêu đề `**KB search — N result(s) for: "<query>"**`, rồi một dòng mô tả phạm vi ACL.
  - **Mục wiki:** slug, loại trang, loại tri thức, nhãn điểm, tiêu đề, heading_path, tóm tắt, gợi ý gọi `read_wiki_page`.
  - **Mục văn bản gốc:** tiêu đề kèm "(nguyên văn)", điểm, số trang, đoạn xem trước cắt 200 ký tự, gợi ý `get_source_pages`, liên kết `{portal_base_url}/wiki/source/{id}`.
  - **Nhãn điểm:**
    - "rerank x.xx" nếu đã rerank;
    - nếu không, % cosine;
    - nếu không có cả hai, "từ khóa";
    - thêm tiền tố đánh dấu khi là khớp chính xác.
  - `total_candidates` > số đã hiển thị → ghi chú tăng `top_k` (tối đa 50).
  - Tiếp theo là phần "trang lân cận theo đồ thị" (tài liệu 04), rồi gợi ý ngoài phạm vi.

#### read_wiki_index

Gọi `wiki_service.render_scoped_index(session, allowed_kt_slugs=identity.allowed_knowledge_types, department_ids=identity.department_ids, all_scopes=identity.is_admin, clearance=identity.clearance_level, page_filter=page_source_clause(identity))` và trả nguyên kết quả. Không bao giờ gọi `get_page_by_slug`.

**`render_scoped_index(session, *, allowed_kt_slugs=None, department_ids=None, all_scopes=False, max_pages=2000, clearance=None, page_filter=None)`** (thuộc `app.services.wiki_service`)

- Gọi `list_pages` với các kwargs tương ứng (allowed_kt_slugs, department_ids, all_scopes, clearance, page_filter) và `limit = max_pages + 1`.
- **Định dạng đầu ra:**
  - Tiêu đề "# Wiki Index".
  - Nhóm theo `page_type` (thiếu thì là "other"), các nhóm sắp theo tên, tiêu đề nhóm viết hoa chữ đầu.
  - Mỗi mục là "- [[slug|title]] — summary", sắp theo tiêu đề.
- **Trường hợp đặc biệt:**
  - Rỗng → ghi chú chỉ mục trống.
  - Vượt `max_pages` → ghi chú tiếng Việt rằng danh sách bị cắt, hướng dẫn dùng `list_wiki_pages` hoặc `search_wiki`.

#### read_wiki_page(slug)

- **Tìm trang:**
  - Admin: `get_page_by_slug_any_scope`.
  - Người khác: `get_page_by_slug` ở phạm vi toàn cục, rồi lần lượt từng phòng ban của người dùng.
  - Mọi lần tra đều truyền clearance và page_filter.
- **Không thấy:**
  - Không phải admin và slug tồn tại ở phòng ban người dùng không được truy cập → "Wiki page `slug` exists in department **X** … but you don't have access. Contact the scope's admin to request access."
  - Ngược lại → "Wiki page not found or out of scope: `slug`".
- **Thấy trang:** trả theo thứ tự:
  1. Callout hiệu lực pháp lý, nếu có LegalUnit gắn trang.
  2. Nội dung trang.
  3. "## Outlinks": các liên kết ra, sắp xếp, bỏ chính nó.
  4. "## Backlinks": các liên kết vào, sắp xếp.

#### get_document_relations

- **Phạm vi rỗng:** gọi `_get_allowed_source_ids`. Kết quả là tập rỗng → trả "Bạn chưa được cấp quyền truy cập văn bản nào." và **không thực thi truy vấn nào**.
- **Ràng buộc truy vấn:** khi tập allowed khác None, **mọi** truy vấn đụng bảng `legal_units` đều phải lọc `source_id IN (tập allowed)`. Test kiểm SQL sinh ra có chứa "source_id IN".
- **Tra theo slug:**
  - Nối `legal_units` với trang wiki theo slug, ưu tiên đơn vị loại ARTICLE.
  - Không thấy và không có cặp số hiệu + điều → "Không tìm thấy điều khoản gắn với trang `slug` (hoặc bạn không có quyền)."
- **Tra theo doc_number + article_number:** đây phải là truy vấn **đầu tiên** được thực thi, và SQL chứa cả "source_id IN" lẫn "unit_type". Điều kiện:
  - số hiệu chuẩn hóa so khớp LIKE;
  - `unit_type = ARTICLE`;
  - `lower(unit_number)` khớp số điều.
  - Xếp hạng: khớp chính xác > khớp tiền tố > chứa.
- **Có đơn vị cụ thể:**
  - Tiêu đề "## Quan hệ văn bản: <full_path> (<doc_number hoặc 'chưa rõ số hiệu'>)", kèm cảnh báo hiệu lực.
  - Chiều đi: quan hệ có đơn vị nguồn là đơn vị này.
  - Chiều đến: quan hệ có đơn vị đích là đơn vị này, hoặc có số hiệu đích + số điều đích khớp.
- **Cả văn bản** (chỉ có doc_number, hoặc không thấy điều):
  - Tiêu đề "## Quan hệ văn bản: <doc_number>".
  - Chiều đi: từ mọi đơn vị của văn bản.
  - Chiều đến: số hiệu đích khớp LIKE, hoặc đơn vị đích thuộc văn bản; loại trừ quan hệ nội bộ.
- **Không có tham số hợp lệ:** "Vui lòng cung cấp `doc_number` (kèm `article_number` nếu cần) hoặc `slug` hợp lệ."
- **Nhãn loại quan hệ:**

| Mã | Nhãn |
|---|---|
| sua_doi | Sửa đổi |
| bo_sung | Bổ sung |
| thay_the | Thay thế |
| bai_bo | Bãi bỏ |
| huong_dan | Hướng dẫn |
| can_cu | Căn cứ |
| dan_chieu | Dẫn chiếu |

- **Định dạng đầu ra:**
  - Hai mục "### Văn bản này tác động đến:" và "### Bị tác động bởi:".
  - Đích ngoài phạm vi chỉ hiện số hiệu.
  - Quan hệ hết hiệu lực gắn "(không còn hiệu lực)".
  - Có ngữ cảnh trích dẫn thì nối vào sau.
  - Vượt limit → dòng "… còn thêm".
  - Không có quan hệ nào → "Không ghi nhận quan hệ sửa đổi, thay thế hay dẫn chiếu nào."

#### list_wiki_pages

- Gọi `wiki_service.list_pages` với limit+1 và offset, kèm các bộ lọc (page_type, knowledge_type, query, department_ids, all_scopes, clearance, page_filter).
- Rỗng → "No wiki pages match the filters."
- Có kết quả → tiêu đề "**Wiki pages — N result(s)**". Còn trang sau thì thêm gợi ý "gọi lại với offset=<offset+limit>".

#### get_source / get_source_outline / get_source_pages

**Lỗi chung:**

| Điều kiện | Thông báo |
|---|---|
| ID không phải UUID | "Invalid source ID: <x>" |
| Không tồn tại | "Source not found: <x>" |
| Ngoài tập allowed | "Access denied: this source is outside your knowledge scope." |

**get_source** trả các dòng:

| Dòng | Giá trị thay thế khi trống |
|---|---|
| tiêu đề | |
| ID | |
| Type | |
| Knowledge type | "Uncategorized" |
| Status | |
| Pages | "(single block)" |
| Contributed by | "(admin upload)" |
| File | |
| URL | |
| Added | |

**get_source_outline**

- Không có dàn ý → "_(no outline — this document has no detectable headings)_".
- Có dàn ý → "# Outline" và cây thụt lề, mỗi mục kèm "(page N)".

**get_source_pages(pages)**

- Phân tích dải trang (tài liệu 04: `parse_page_range`). Sai cú pháp → "Invalid page range: '<pages>'. Use formats like '5-7', '3,8', '12'."
- Không có văn bản hoặc offset trang → "_(no extractable text or page offsets for this source)_".
- Các trang yêu cầu không có nội dung → "No content for pages: [...]".
- Có nội dung → mỗi trang một khối mở đầu bằng "--- page N ---".

#### search_source_content

- Query rỗng → "Error: query parameter must not be empty."
- Tìm trên các văn bản `ready` trong phạm vi, qua ba tầng; dừng ở tầng đầu có kết quả:
  1. Full-text kiểu web-search trên văn bản bỏ dấu.
  2. HOẶC các từ khóa: bỏ stopword, độ dài > 1.
  3. ILIKE bỏ dấu trên tối đa 3 từ dài hơn 2 ký tự.
- Không có kết quả → 'No document content matches found for: "<query>"'.
- Mỗi văn bản là "### <title> (ID: <id>)", kèm tối đa 5 dòng khớp được tô đậm, có số trang.

#### list_sources

- `status = "all"` thì bỏ lọc trạng thái.
- `query` dùng ILIKE trên tiêu đề, tên file và URL. Có lọc phạm vi. Sắp theo ngày tạo giảm dần.
- Rỗng → "No documents found[ of type '<kt>'][ matching '<q>']." (các phần trong ngoặc vuông chỉ xuất hiện khi có tham số tương ứng).
- Có kết quả → tiêu đề "**Knowledge Base — N document(s)**", nhóm theo tên loại tri thức.

#### list_knowledge_types / get_knowledge_type_docs

**list_knowledge_types**

- Đếm số văn bản `ready` theo từng loại; sắp theo `sort_order` rồi tên; lọc theo `allowed_knowledge_types`.
- Chưa định nghĩa loại nào → "No knowledge types have been defined yet."
- Có loại nhưng bị lọc hết → "No accessible knowledge types found for your scope."

**get_knowledge_type_docs**

- Slug không được phép → "Access denied: knowledge type '<slug>' is outside your scope. Use `list_knowledge_types` to see the types you can access."
- Không tồn tại → "Knowledge type '<slug>' not found."
- Rỗng → "No documents found for knowledge type: **<name>**".

#### edit_wiki_page

Lỗi kiểm tra, theo thứ tự:

| Điều kiện | Thông báo |
|---|---|
| thiếu slug hoặc nội dung | "Error: slug and content_md are required." |
| slug dành riêng (INDEX, LOG, HOT, không phân biệt hoa thường) | "Error: reserved pages cannot be edited." |
| > 50 000 ký tự | "Error: content_md exceeds 50,000 character limit." |
| scope_type lạ | "Error: scope_type must be global or department." |
| scope_id sai | "Error: scope_id must be a valid UUID." |
| slug ở nhiều phạm vi mà không chỉ định | "Error: slug '<slug>' exists in multiple scopes (<danh sách>). Re-call with scope_type and scope_id." |
| không thấy | "Page '<slug>' not found. Use search_wiki() or list_wiki_pages() to find the slug." |
| không thấy nhân viên | "Error: employee not found." |
| không đủ quyền | "Error: insufficient permission to edit '<slug>'." |
| bộ chặn ghi của agent từ chối (vd. xóa dòng bảng khi `allow_row_removal` False, tài liệu wiki) | "Error: <lý do từ chối>" |
| base_version > phiên bản hiện tại | "Error: base_version N is ahead of current page vM." |

Khi qua hết kiểm tra:

- Tạo bản nháp nguồn "mcp_claude_desktop" rồi xuất bản ngay.
- Xung đột phiên bản → "Error: page '<slug>' is now vN (your edit was based on vM). Re-read the page and re-apply your change."
- Thành công → "Page `<slug>` updated to vN. Note: …" (ghi chú tóm tắt).

#### create_wiki_page

**Lỗi kiểm tra đầu vào:**

| Điều kiện | Thông báo |
|---|---|
| thiếu trường bắt buộc | "Error: …" (lời văn tự viết) |
| slug dành riêng | "Error: this slug is reserved." |
| vượt giới hạn độ dài | lỗi tương tự edit_wiki_page |
| slug có khoảng trắng | "Error: slug must not contain whitespace." |
| page_type ngoài PAGE_TYPES | "Error: …" (lời văn tự viết) |
| scope_type lạ | "Error: …" (lời văn tự viết) |
| scope_type = department mà thiếu scope_id | "Error: scope_id is required when scope_type is department." |

**Lỗi quyền:**

- Trang phòng ban → "Error: insufficient permission to create pages in this department."
- Trang toàn cục → "Error: insufficient permission to create wiki pages."

**Xử lý:**

- Trang đã tồn tại trong phạm vi → "Error: page '<slug>' already exists in <phạm vi>. Use edit_wiki_page() to change it."
- Tạo bản nháp loại "create", kèm suggested_metadata (title, page_type, knowledge_type_slugs), rồi xuất bản.
- Xung đột slug hoặc ValueError → "Error: could not create page '<slug>': <e>".
- Thành công → "Page `<slug>` created at vN. Note: …".

#### query_table

Kiểm tra, đúng thứ tự (test phụ thuộc):

1. `source_id` không phải UUID → "Invalid source_id format: '<x>'."
2. `session.get(Source, uuid)` trả None → "Source '<x>' not found."
3. Không có `minio_key` → "Source '<x>' has no stored file."
4. `_get_allowed_source_ids` khác None và `str(id)` không thuộc tập → "Access denied to source '<x>'." Trường hợp này **không** được tải file.

Khi qua kiểm tra:

- Gọi `storage_service.download_file(minio_key)`. Rỗng → "Failed to retrieve file content for source '<x>'."
- Gọi `TableQueryService(default_max_rows).query_excel_bytes(file_bytes, file_name or "table.xlsx", sql_query, max_rows)` (tài liệu 03/04).
  - Lỗi → "❌ Lỗi truy vấn bảng: <lỗi>".
  - 0 dòng → thông báo tiếng Việt "không có dòng phù hợp".
  - Có dòng → tiêu đề kèm bảng Markdown.

#### Công cụ kỹ năng (list_skills, read_skill, read_skill_file)

**Hằng số**

- `SKILL_FILE_MAX_CHARS = 60000`. Văn bản dài hơn bị cắt và thêm ghi chú "(truncated: N more characters)".
- Phần mở rộng đọc được: .md .txt .json .yaml .yml .csv .xml .html .py .js .ts .sh .sql .ini .cfg.

**Nạp bundle**

- Liệt kê object dưới `storage_path/`.
- File SKILL.md (không phân biệt hoa thường) ở độ sâu nông nhất (ưu tiên độ sâu, rồi tên) xác định thư mục gốc. Đường dẫn file tính tương đối với thư mục này.
- Frontmatter đọc theo YAML; lỗi thì dùng bộ đọc từng dòng "khóa: giá trị".
- Cache theo (storage_path, version_hash), tối đa 256 mục; đầy thì xóa toàn bộ.

**Quyền đọc kỹ năng**, theo thứ tự:

1. Admin → được.
2. Có `skill:read:all` **và** `delegated_role` là None → được.
3. Kỹ năng không gắn phòng ban → được.
4. Ngược lại → được khi kỹ năng có chung ít nhất một phòng ban với danh tính.

**Lỗi tra kỹ năng**

| Điều kiện | Thông báo |
|---|---|
| không thấy hoặc không active | "Skill '<slug>' not found. Use `list_skills` to see available skills." |
| ngoài phạm vi | "Access denied: skill '<slug>' is outside your scope." |
| không có storage_path | "Skill '<slug>' has no stored content." |

**list_skills**

- Chọn kỹ năng `active`, có storage_path và đọc được; sắp theo slug.
- Nạp bundle song song. Bundle hỏng thì bỏ qua và ghi cảnh báo.
- Có `query`:
  - Tách từ, bỏ dấu, casefold.
  - Điểm = số từ xuất hiện trong chuỗi ghép slug + name + description.
  - Loại điểm 0; sắp ổn định theo điểm giảm dần.
- Rỗng → "No skills found[ matching '<q>']. Use `list_skills` without a query to see every skill you can use."
- Có kết quả:
  - Tiêu đề "**Kho kỹ năng — N skill(s)**" và gợi ý gọi `read_skill`.
  - Mỗi dòng "`slug` (vN) — name: description", mô tả cắt 400 ký tự.
  - Vượt limit → dòng "… N more — narrow with `query`."

**read_skill(slug)**

- Không có SKILL.md → "Skill '<slug>' has no SKILL.md in its bundle."
- Có → "# Skill `slug` (vN)", nội dung SKILL.md (cắt nếu quá dài), rồi mục "Bundled files" liệt kê đường dẫn và kích thước.
- Kích thước ghi "N B" nếu dưới 1024, ngược lại "x.x KB".

**read_skill_file(slug, path)**

- **Chuẩn hóa path:** `\` thành `/`, bỏ `/` đầu, chuẩn hóa `.` và `..`.
- **Lỗi:**
  - Path phải có trong danh sách bundle, nếu không → "File '<p>' not found in skill '<slug>'. Files: <danh sách>".
  - Không phải phần mở rộng văn bản → "File '<p>' is not a text file; only text files can be read."
- **Định dạng trả về:**
  - `.md` trả nguyên văn, kèm tiêu đề.
  - Loại khác bọc trong khối rào, có nhãn ngôn ngữ: json, yaml, csv, xml, html, python, sql; còn lại không nhãn.

### 1.8 Tài nguyên MCP

**`arkon://about`**

Markdown tĩnh, tự soạn, gồm:

- giới thiệu;
- các nhóm công cụ: wiki, đào sâu văn bản gốc, duyệt danh mục, kỹ năng, ghi dành cho người đóng góp;
- ba nguyên tắc:
  - tìm trước khi nói "không biết";
  - đi theo wikilink;
  - trích dẫn slug hoặc ID văn bản kèm trang.

**`arkon://wiki-index`**

- Import `_get_identity` từ `app.mcp.tools` lúc gọi. Có lỗi thì trả chuỗi lỗi.
- Gọi `wiki_service.render_scoped_index(session, allowed_kt_slugs=…, department_ids=…, all_scopes=is_admin)`.
  - Nguồn gốc **không** truyền clearance và page_filter.
  - Bản c2 **nên** truyền thêm hai tham số này cho nhất quán với công cụ. Test chỉ kiểm ba kwargs kia, nên việc truyền thêm không làm hỏng test.
- Ngoại lệ → "Wiki index: failed to load."
- Không bao giờ gọi `get_page_by_slug`.

---

## 2. Kho kỹ năng (Skills)

### 2.1 Lược đồ

**skills**

| Cột | Kiểu | Ràng buộc |
|---|---|---|
| id | UUID | PK |
| name | varchar(200) | unique |
| slug | varchar(200) | unique, index |
| scope_type | varchar(20) | mặc định "global" (global, department) |
| scope_id | UUID null | phòng ban chính (để tương thích cũ) |
| current_version | int | mặc định 1 |
| version_hash | varchar(64) null | |
| storage_path | varchar(1000) null | |
| status | enum `skill_status` | active, processing, deleting, deprecated, archived (worker có thể ghi "error"); mặc định active |
| is_system | bool | mặc định false |
| created_at, updated_at | timestamptz | |

**skill_departments**

- PK (skill_id, department_id).
- Cả hai cột là FK với ON DELETE CASCADE.

**skill_versions**

| Cột | Kiểu |
|---|---|
| id | UUID PK |
| skill_id | FK CASCADE |
| version_number | int |
| version_hash | varchar(64) |
| storage_path | varchar |
| changelog | text null |
| created_by | FK employees SET NULL |
| created_at | timestamptz |

**skill_contributions**

| Cột | Kiểu |
|---|---|
| id | UUID PK |
| skill_id | FK CASCADE, null |
| contributor_id | FK employees CASCADE |
| base_version | int null |
| status | varchar(20), mặc định draft, index |
| revision_round | int, mặc định 0 |
| last_returned_note | text null |
| scope_type | mặc định global |
| scope_ids | JSONB null (danh sách UUID chuỗi) |
| title | varchar(200) |
| storage_path | varchar null |
| created_at, updated_at | timestamptz |

**SkillContributionStatus:** draft, pending, needs_revision, withdrawn, approved, rejected.

**Bố cục lưu trữ MinIO**

- Phiên bản kỹ năng: `skills/<skill_id>/versions/<n>/`. Worker nạp ZIP ghi file vào `…/<n>/content/<đường dẫn>`.
- Đóng góp: `skill-contributions/<contribution_id>/<thư mục gốc>/…`.
- ZIP tạm: `temp_uploads/<uuid>.zip`.

### 2.2 Quyền kỹ năng

- **`can_access_skill(db, user, skill, action="read")`**, action ∈ read, create, edit, delete:
  - Admin → được.
  - Có `skill:<action>:all` → được.
  - Ngược lại: được nếu kỹ năng không có phòng ban, hoặc chung ít nhất một phòng ban với người dùng.
- **`build_skill_filter(user, action) -> (needs_filter, allowed_department_ids)`**:
  - Admin hoặc có quyền `:all` → (False, []).
  - Có `own_dept` → (True, phòng ban của người dùng).
  - Còn lại → (True, None).
  - Router coi (True, None) là "không thấy gì".
- **Kỹ năng hệ thống** (`is_system`): chỉ admin được sửa hoặc xóa. Người khác → 403 "Kỹ năng hệ thống chỉ quản trị viên được sửa hoặc xóa".

### 2.3 Mô hình API

| Model | Trường |
|---|---|
| SkillResponse | id, name, slug, department_ids: list[UUID], department_names: list[str], current_version: int, version_hash, status, scope_type = "global", scope_id, is_system = False, created_at, updated_at |
| SkillVersionResponse | version_number, version_hash, storage_path, changelog, created_at |
| SkillListResponse | items: list[SkillResponse], total: int |
| SkillUpdateRequest | name?, department_ids?, scope_type?, scope_id?, increment_version = False |
| SkillComposeRequest | name, description, body = "", scope_type = "global", department_ids = [] |
| SkillContentRequest | description?, body (bắt buộc) |

### 2.4 Endpoint kỹ năng (đều cần get_current_user, trừ khi ghi khác)

**POST /api/skills/compose** (body SkillComposeRequest)

- **Kiểm tra, theo thứ tự:**
  1. `name` được lowercase. Phải bắt đầu bằng a-z0-9, các ký tự sau là a-z0-9 hoặc "-", tổng 2–80 ký tự. Sai → 400 "Tên kỹ năng chỉ gồm chữ thường không dấu, số và '-' (2–80 ký tự)".
  2. Mô tả rỗng sau khi strip → 400 "Cần mô tả khi nào dùng kỹ năng".
  3. Trùng tên → 409 "Đã có kỹ năng '<name>'".
  4. scope department mà không có phòng ban → 400 "Chọn ít nhất một phòng ban".
- **Xử lý:**
  - Dựng ZIP tên `<name>.zip` chứa `<name>/SKILL.md`. Frontmatter có `name` và `description`; description đặt trong ngoặc kép kiểu JSON. Sau frontmatter là body.
  - Chuyển cho luồng upload: department_ids; scope_id = phòng ban đầu tiên nếu scope department.
- **Kết quả:** như POST /skills/upload.

**GET /api/skills/{slug}/content**

- Cần quyền đọc, nếu không → 403 "Access denied".
- Trả `{name, description, body, is_system}`.
  - Đọc SKILL.md, ưu tiên `<name>/SKILL.md`.
  - Tách frontmatter: không có frontmatter thì description "" và body là toàn văn đã strip.
  - Description bắt đầu bằng `"` thì giải mã JSON; nếu không, bỏ nháy đơn bao quanh.
- Không có storage_path → 404 "Kỹ năng chưa có nội dung".

**PUT /api/skills/{slug}/content** (SkillContentRequest)

- Cần quyền edit, cộng ràng buộc kỹ năng hệ thống.
- Dựng lại ZIP gồm mọi file hiện có và SKILL.md mới. Thiếu description thì giữ mô tả cũ.
- **Không phải admin:** tạo đóng góp từ ZIP với base_version = phiên bản hiện tại. Trả `{status:"contribution_pending", contribution_id, message:"Đã gửi bản sửa, chờ duyệt"}`.
- **Admin:** `reupload_skill`; trả kết quả của nó.

**POST /api/skills/upload** (multipart)

- **Trường:**
  - `files`: nhiều file .zip.
  - `department_ids`: danh sách UUID.
  - `scope_type` = "global".
  - `scope_id`.
  - `force` = false.
- **Quyền:** người không phải admin và không có `skill:create:all`:
  - Thiếu `skill:create:own_dept` → 403 "Permission required: skill:create".
  - Có phòng ban không thuộc mình (trong department_ids, hoặc scope department với scope_id ngoài phòng ban của mình) → 403 "You can only assign skills to your own departments".
  - Scope global → 403 "You do not have permission to create global skills".
- **Không phải admin:**
  - Mỗi file tạo một đóng góp (mục 3.1, `create_contribution_from_zip`).
  - Trả `{results:[{name:<filename>, status:"contribution_pending", contribution_id, message:"Submitted contribution for review"}], message:"Skills submitted for review."}`.
- **Admin:** `SkillService.upload_skills(...)`; trả `{results}`.

**POST /api/skills/{slug}/reupload** (multipart `file`)

- Cần quyền create, cộng ràng buộc kỹ năng hệ thống.
- **Không phải admin:** tạo đóng góp với skill_id và base_version hiện tại. Trả `{status:"contribution_pending", contribution_id, message:"Update submitted for review."}`.
- **Admin:** `SkillService.reupload_skill`.

**POST /api/skills/inspect-zip** (require_permission "skill:create"; multipart file)

- Trả `{name: tên file bỏ đuôi, description: toàn văn SKILL.md}`.
- ZIP hỏng → 400 "Invalid ZIP file.".

**GET /api/skills**

- **Tham số:**
  - `q`, `department_id`, `scope_type`, `scope_id`.
  - `ids`: list[UUID].
  - `cursor`: slug của mục cuối trang trước.
  - `limit` = 20.
- Gọi `build_skill_filter(user, "read")`. Nếu needs_filter và allowed là None → `{items:[], total:0}`.
- Trả SkillListResponse. Bản ghi hỏng (không serialize được) bị bỏ qua.

**GET /api/skills/{skill_id}/files?version=**

- **Lỗi:**
  - 404 "Skill not found".
  - 403 "Access denied".
  - 404 "Version N not found".
- Không có prefix → `[]`.
- Trả danh sách `{path, size, last_modified (ISO), is_text}`, sắp theo path.
- **Phần mở rộng văn bản** (is_text) phía portal: .py .md .txt .json .yaml .yml .sh .js .ts .tsx .html .css .sql .env .cfg .ini .xml .csv .bat .ps1.

**GET /api/skills/{skill_id}/files/content?path=&version=**

- **Lỗi trước khi đọc:**
  - 404 "Skill not found".
  - 403 "Access denied".
  - 404 "Version N not found".
  - 404 "Skill storage path not found".
  - Không phải file văn bản → 400 "Only text-based files can be viewed.".
- **Thứ tự dò file:**
  1. Thử prefix và prefix + "/content".
  2. Với mỗi prefix, thử path và path đã bỏ đoạn đầu tiên.
  3. Cuối cùng, so khớp mờ theo hậu tố.
- **Lỗi khi đọc:**
  - Không thấy → 404 "File <path> not found in skill storage.".
  - Lỗi khác → 500 "Failed to read file content: <e>".
- Trả `{content}` (UTF-8).

**Các endpoint còn lại**

| Endpoint | Quyền | Kết quả và lỗi |
|---|---|---|
| GET /api/skills/{slug}?version= | quyền đọc | SkillResponse |
| GET /api/skills/{slug}/versions | require_permission "skill:read" | list[SkillVersionResponse], phiên bản giảm dần |
| POST /api/skills/{slug}/set-latest?version= | quyền edit + ràng buộc hệ thống | `{message:"Version N set as latest", current_version}` |
| DELETE /api/skills/{slug} | quyền delete + ràng buộc hệ thống | Kỹ năng hệ thống (admin) → status archived, `{message:"Skill archived"}`. Còn lại → `delete_skill`, `{message:"Skill marked for deletion"}` |
| PATCH /api/skills/{slug} (SkillUpdateRequest) | quyền edit + ràng buộc hệ thống | Xem dưới |

**Chi tiết PATCH /api/skills/{slug}**

- Đổi tên kỹ năng hệ thống → 400 "Không đổi tên kỹ năng hệ thống (tên gắn với thư mục nguồn); hãy nhân bản để tạo kỹ năng mới".
- Người không có `skill:edit:all`:
  - Phòng ban ngoài phòng ban của mình → 403 "You can only assign skills to your own departments".
  - Đặt global → 403 "You do not have permission to make skills global".
- Chuyển cho service danh sách các trường được gửi tường minh. Trả SkillResponse.

### 2.5 `SkillService` (app.services.skill_service)

**Băm nội dung ZIP**

- SHA-256 trên dãy các entry không phải thư mục, sắp theo tên.
- Mỗi entry đóng góp tên file và md5 hex của nội dung.
- ZIP hỏng → None.

**validate_zip_content(data, zip_name) -> (ok, err)**

- Cần entry tên "skill.md", "<zip_name>/skill.md", hoặc kết thúc bằng "/skill.md" (không phân biệt hoa thường).
- Thiếu → "Missing mandatory SKILL.md file in ZIP package.".
- ZIP hỏng → "Invalid or corrupted ZIP file.".

**Upsert theo tên**

- **Đã tồn tại, không `force`** → đánh dấu trùng.
- **Đã tồn tại, có `force`:**
  - Cập nhật phòng ban:
    - scope department hoặc có department_ids → scope department; scope_id = giá trị gửi lên, hoặc phòng ban đầu tiên.
    - Ngược lại → global và xóa liên kết.
  - Cùng hash → chỉ cập nhật metadata.
  - Khác hash → status processing, hash mới, version + 1.
- **Mới:** slug = slugify(name), status processing, version 1, scope department nếu có phòng ban.

**upload_skills(db, files, department_ids, scope_type, scope_id, force, current_user_id)**

- Tên kỹ năng = tên file bỏ đuôi.
- Kết quả từng file:
  - ZIP hỏng → `{name, status:"error", message:"Invalid ZIP file."}`.
  - Kiểm tra nội dung thất bại → `{name, status:"rejected", message:<err>}`.
  - Chỉ đổi metadata → `{name, status:"updated_metadata", message:"Metadata updated, content unchanged."}`.
  - Còn lại:
    - Tạo SkillVersion (`created_by` = người upload).
    - Ghi ZIP vào `temp_uploads/<uuid>.zip`.
    - Ghi kết quả trạng thái processing.
- **Có trùng tên khi không force:** rollback, rồi 409 với detail `{message:"Duplicate skill names detected", conflicts:[tên…]}`.
- **Sau commit:** đẩy job `ingest_skill_task(skill_id, version_id, temp_path, filename)` vào hàng đợi arq "skills_queue".
- Lỗi thì xóa file tạm.

**reupload_skill(db, slug_or_uuid, file, user_id)**

- **Lỗi:**
  - 404 "Skill not found".
  - 400 "Invalid ZIP file.".
  - Tên file khác `<skill.name>.zip` → 400 "Filename mismatch. Expected '<name>.zip', got '<filename>'.".
- **Cùng hash** → `{status:"skipped", message:"Content unchanged. No new version created.", skill_id, version}`.
- **Kiểm tra nội dung lỗi** → 400 kèm thông điệp lỗi.
- **Còn lại:** phiên bản mới, đẩy job ingest, trả `{status:"processing", skill_id, version}`.

**list_skills(db, allowed_department_ids, q, department_id, scope_type, scope_id, ids, cursor, limit) -> (items, total)**

- **Sắp xếp:** updated_at giảm dần, rồi id giảm dần. Cursor dùng keyset theo (updated_at, id) của kỹ năng có slug = cursor.
- **Bộ lọc:**
  - Khi có allowed_department_ids: kỹ năng không có phòng ban, hoặc gắn một phòng ban được phép.
  - Loại status deleting và archived.
  - ids.
  - q: ILIKE trên name.
  - department_id; scope_type (kèm scope_id).
- `total` là số đếm distinct.

**get_skill(db, slug, version_number=None)**

- Tra theo UUID nếu parse được, nếu không thì theo slug; nạp kèm phòng ban.
- Không thấy, hoặc status deleting/archived → 404 "Skill not found".
- version_number khác phiên bản hiện tại mà không tồn tại → 404 "Version N not found".
- Lỗi bất ngờ → 500 "Internal server error while fetching skill".

**Các phương thức còn lại**

| Phương thức | Hành vi |
|---|---|
| list_versions(db, slug) | danh sách SkillVersion, version_number giảm dần |
| set_latest_version(db, slug, n) | Trùng hiện tại thì không đổi. Không có → 404 "Version N not found". Có → chép version_hash và storage_path của phiên bản đó lên kỹ năng. |
| delete_skill(db, slug) | Đặt status "deleting", commit, đẩy `delete_skill_task(skill_id)` vào "skills_queue". Lỗi đẩy job chỉ ghi log. |
| update_skill(db, slug, req_data) | Xem dưới |
| bulk_change_scope(db, skill_ids, scope_type, scope_id) -> int | Cập nhật hàng loạt; đồng bộ liên kết phòng ban (một phòng ban nếu scope department). Trả số lượng. |

**update_skill(db, slug, req_data)**

- `req_data` có thể chứa khóa `_explicit_fields`, liệt kê các trường gửi tường minh.
- Đổi tên:
  - Trùng tên khác → 409 "Skill with name '<name>' already exists.".
  - Hợp lệ → cập nhật name và slug = slugify(name).
- Khi scope_type hoặc department_ids được gửi (kể cả tường minh là null):
  - Hợp tập department_ids và scope_id, bỏ rỗng.
  - Tập khác rỗng → scope department, scope_id = scope_id gửi lên hoặc phần tử đầu, đồng bộ lại liên kết.
  - Tập rỗng → global, scope_id null, xóa liên kết.

**Worker ingest_skill_task**

- **Giới hạn ZIP:**
  - Không có đường dẫn bắt đầu bằng "/" hoặc chứa "..".
  - Tối đa 100 file.
  - Tối đa 10 MB sau giải nén.
- Ghi từng file vào `skills/<id>/versions/<n>/content/<file>`, tính lại hash theo prefix bằng `storage_service.calculate_prefix_hash`.
- **Thành công:** kỹ năng active; storage_path và version_hash trỏ phiên bản mới.
- **Thất bại:** status "error".
- Luôn xóa file tạm.

**Worker delete_skill_task(skill_id)**

- Xóa prefix `skills/<id>/` và storage của các đóng góp liên quan.
- Xóa dòng kỹ năng.

---

## 3. Đóng góp kỹ năng (Skill contributions)

### 3.1 Service

**create_contribution(db, skill_id, base_version, user_id, title, scope_type="global", scope_ids=None)**

- Tạo bản ghi status draft, `storage_path = "skill-contributions/<id>/"`.
- **Thư mục gốc:** slug kỹ năng nếu có skill_id. Nếu không, tiêu đề lowercase, thay mọi chuỗi ký tự không phải chữ hoặc số bằng "-" và bỏ "-" ở hai đầu.
- **Nội dung ban đầu:**
  - Có skill_id và base_version: chép toàn bộ prefix của phiên bản gốc. Không thấy phiên bản thì chỉ ghi cảnh báo.
  - Ngược lại: ghi `<gốc>/SKILL.md` với tiêu đề cấp 1 là title và một dòng giới thiệu.

**create_contribution_from_zip(db, file, user, skill_id=None, base_version=None)**

- Status **pending**, title "Upload: <tên zip>".
- Giải nén lên storage của đóng góp.
  - ZIP chỉ có một thư mục gốc chung thì giữ nguyên.
  - Nếu không, bọc mọi file trong `<slug>/`. slug là slug kỹ năng, hoặc slugify tên zip.
- **Lỗi:**
  - ZIP không có file → 400 "ZIP file contains no files.".
  - Lỗi giải nén → 500 "ZIP extraction failed: <e>".

**submit_contribution(db, id)**

- Không thấy → 404 "Contribution not found".
- Chuyển status sang pending.

**approve_contribution(db, id, admin_id, final_scope_type=None, final_scope_ids=None)** → Skill. Các bước:

1. Không thấy → 404 "Contribution not found".
2. Tính hash theo prefix của đóng góp. Kỹ năng đã có phiên bản cùng hash → đặt status rejected, commit, rồi 400 "This contribution is identical to an existing version of the skill.".
3. Xác định phạm vi: final_scope_type, nếu không thì scope của đóng góp. scope_ids: final_scope_ids nếu khác None, nếu không thì của đóng góp.
4. Lấy kỹ năng đích:
   - Chưa có: tạo Skill(name=title, slug=slugify(title), current_version=0, status processing).
   - Đã có: áp final_scope_type nếu được truyền.
5. Đồng bộ phòng ban:
   - department có ids → thay liên kết, scope_id = phần tử đầu.
   - global → xóa liên kết, scope_id null.
6. Phiên bản mới n = current + 1. Chép prefix đóng góp sang `skills/<id>/versions/<n>/`.
7. Tạo SkillVersion: changelog "Approved contribution: <title>", created_by = người đóng góp.
8. Cập nhật kỹ năng: current_version, storage_path, version_hash, status active.
9. Đóng góp: status approved, gắn skill_id.

**reject_contribution(db, id)**

- Không thấy → 404.
- Đưa status về **draft**.

### 3.2 Chuyển trạng thái (contribution_service, dùng chung với bản nháp wiki)

- **Ngoại lệ chung:** `InvalidTransition`, thông điệp dạng "… in status 'X'. Allowed: …".
- **request_changes(db, adapter, contribution, reviewer, reviewer_note)**
  - Ghi chú rỗng → InvalidTransition "reviewer_note is required when requesting changes.".
  - Chỉ cho phép pending → needs_revision.
  - Lưu last_returned_note; thông báo tác giả với loại changes_requested.
- **resubmit_skill_contribution(db, contribution, user)**
  - needs_revision → pending; revision_round + 1.
  - Thông báo người duyệt với tiêu đề "Resubmitted: <title> (round N)".
- **withdraw(db, adapter, contribution, user)**
  - Chỉ chủ đóng góp được rút.
  - Từ pending hoặc needs_revision → withdrawn; thông báo người duyệt.
- **Thông báo theo sự kiện:**
  - notify_submitted → người duyệt.
  - notify_approved(…, version_label="vN") → tác giả.
  - notify_rejected → tác giả.
- **Người duyệt kỹ năng** = người duyệt toàn cục (`get_global_reviewers`, mục 9.2).

**Trạng thái cho phép sửa file:** draft và needs_revision. Trạng thái khác → 400 "Cannot edit contribution while status='<s>'. Withdraw it (or ask a reviewer to request changes) before editing."

### 3.3 Mô hình

| Model | Trường |
|---|---|
| SkillContributionCreate | skill_id?, base_version?, title (bắt buộc), scope_type = "global", scope_ids? |
| SkillContributionResponse | id, skill_id, contributor_id, base_version, status, title, storage_path, scope_type, scope_ids, contributor_name (thiếu → "Unknown"), created_at, updated_at |
| PutFileRequest | path, content |
| SkillContributionApprove | final_scope_type?, final_scope_ids? |
| RequestChangesSkillRequest | reviewer_note |

### 3.4 Endpoint

"Chủ" là người đóng góp. "Người duyệt" là người có quyền `skill:contribution:review`. "Xem được" là admin, chủ, hoặc người duyệt.

| Method + path | Quyền | Hành vi, kết quả, lỗi |
|---|---|---|
| GET /api/skill-contributions/check?title=&skill_id= | đăng nhập | Bản nháp (status draft) của chính người dùng, khớp skill_id nếu có, nếu không thì khớp title. Trả bản ghi hoặc null. |
| POST /api/skill-contributions (SkillContributionCreate) | đăng nhập; không phải admin và không có skill:create:all thì cần skill:create:own_dept, nếu không → 403 "Permission required: skill:create" | Kỹ năng gốc là kỹ năng hệ thống → 403 "System skills cannot be modified via contributions". Trả SkillContributionResponse. |
| GET /api/admin/skill-contributions?skill_id= | skill:contribution:review | Các đóng góp pending, mới nhất trước, có contributor_name. |
| GET /api/skill-contributions?status= | đăng nhập | Chỉ đóng góp của chính người dùng (kể cả admin), mới nhất trước. |
| GET /api/skill-contributions/{id} | xem được | 404 "Contribution not found"; 403 "Access denied". |
| DELETE /api/skill-contributions/{id} | admin hoặc chủ | 404; 403 "Access denied"; không phải admin và đã approved → 400 "Cannot delete an approved contribution". Xóa prefix storage và bản ghi; trả `{status:"ok"}`. |
| GET /api/skill-contributions/{id}/files | xem được | Đã approved → 400 "Cannot access contribution files in status: approved". Không có prefix → []. Trả [{path, size, is_text}], sắp theo path. |
| GET /api/skill-contributions/{id}/files/content?path= | xem được | Trả `{content}`, giải mã UTF-8 bỏ qua lỗi. Lỗi → 500 "Failed to read file: <e>". |
| POST /api/skill-contributions/{id}/rename?old_path=&new_path= | admin hoặc chủ; trạng thái sửa được | Đường dẫn chỉ một đoạn → 400 "Cannot rename the root folder."; kết thúc bằng SKILL.md → 400 "Cannot rename SKILL.md.". Di chuyển prefix; trả `{status:"ok", old_path, new_path, contribution_status}`. |
| DELETE /api/skill-contributions/{id}/files?path= | admin hoặc chủ; sửa được | Xóa file hoặc prefix; trả `{status:"ok", path, contribution_status}`. |
| POST /api/skill-contributions/{id}/upload?path= (multipart file) | admin hoặc chủ; sửa được | Đường dẫn = path, hoặc tên file. Chuẩn hóa về thư mục gốc (xem dưới). Lỗi ghi → 500 "MinIO upload failed: <e>". Trả `{status:"ok", path, contribution_status}`. |
| PUT /api/skill-contributions/{id}/files (PutFileRequest) | admin hoặc chủ; sửa được | Như upload nhưng nội dung văn bản UTF-8, content type text/plain. |
| POST /api/skill-contributions/{id}/submit | đăng nhập | 404; trạng thái không phải draft/needs_revision → 400 "Cannot submit contribution in status: <s>". Chuyển pending, gửi thông báo submitted; trả `{status}`. |
| POST /api/skill-contributions/{id}/approve (body SkillContributionApprove, tùy chọn) | skill:contribution:review | Xem dưới. |
| POST /api/skill-contributions/{id}/reject | skill:contribution:review | Về draft, thông báo rejected; trả `{status}`. Không thấy → 404. |
| POST /api/skill-contributions/{id}/request-changes (reviewer_note) | skill:contribution:review | 404; InvalidTransition → 400 kèm thông điệp. Trả `{status, revision_round}`. |
| POST /api/skill-contributions/{id}/resubmit | đăng nhập | 404; InvalidTransition → 400. Trả `{status, revision_round}`. |
| POST /api/skill-contributions/{id}/withdraw | đăng nhập (chủ) | 404; InvalidTransition → **403** kèm thông điệp. Trả `{status}`. |
| GET /api/skill-contributions/{id}/diff-status | xem được | Trả map `{đường_dẫn: "A"|"D"|"M"}` (xem dưới). |

**Chuẩn hóa thư mục gốc khi upload hoặc PUT file**

1. Thư mục gốc = đoạn đầu của file đầu tiên đang có trong storage.
2. Không có file nào: lấy slug kỹ năng, nếu không thì slugify(title bỏ tiền tố "Upload: ").
3. Đường dẫn chưa bắt đầu bằng `<gốc>/` thì được thêm tiền tố này.

**Chi tiết approve**

- **Lỗi:**
  - Không thấy → 404 "Contribution not found".
  - Đã approved hoặc rejected → 400 "Contribution already approved".
  - Người không phải admin, đóng góp scope department, mà người duyệt không thuộc phòng ban đích nào → 403 "You do not have permission to approve contributions for these departments. Reviewer must belong to one of the target departments."
- **Xử lý:** gọi approve_contribution, thông báo approved với nhãn "v<n>".
- **Kết quả:** `{status:"approved", skill_id, skill_slug, version}`.

**Chi tiết diff-status**

- So file của đóng góp với phiên bản **mới nhất** của kỹ năng.
- Phía phiên bản: bỏ tiền tố "content/".
- Nếu mỗi bên có một thư mục gốc chung riêng, so theo đường dẫn đã bỏ thư mục gốc.
- Ký hiệu:
  - A = chỉ có ở đóng góp.
  - D = chỉ có ở bản gốc; khóa là đường dẫn mang thư mục gốc của đóng góp.
  - M = có ở cả hai nhưng khác kích thước hoặc etag.

---

## 4. Kho prompt (`/api/prompts`)

### 4.1 Bảng `prompt_templates` (model PromptTemplate)

| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | UUID PK | |
| title | varchar(200) | |
| command | varchar(100) | index |
| description | text null | |
| content | text | |
| tags | ARRAY(varchar) | mặc định {} |
| scope_type | varchar(20) | mặc định personal |
| department_ids | ARRAY(UUID) | mặc định {} |
| owner_id | FK employees SET NULL | index; quan hệ `owner` |
| source | varchar(20) | mặc định "wiki" |
| external_ref | varchar(200) null | index |
| created_at, updated_at | timestamptz | |

### 4.2 Quy tắc

- **SCOPES:** personal, department, global.
- **Chuẩn hóa command:**
  - strip, bỏ các "/" đầu, lowercase.
  - Phải bắt đầu bằng a-z0-9; các ký tự sau là a-z0-9, "_" hoặc "-"; tổng 1–100 ký tự.
  - Sai → 400 "Lệnh chỉ gồm chữ thường không dấu, số, '-' hoặc '_' (ví dụ: tom-tat-van-ban)".
- **Chuẩn hóa tags:** strip, cắt 50 ký tự, bỏ rỗng, bỏ trùng (giữ thứ tự), tối đa 20 thẻ.
- **Quyền xem:**
  - Admin hoặc `skill:read:all` → xem tất cả.
  - Ngược lại → global, của mình, hoặc department có giao với phòng ban của người dùng.
- **Kiểm tra phạm vi (scope_type, dept_ids)**, theo thứ tự:
  1. Không thuộc SCOPES → 400 "scope_type phải là personal, department hoặc global".
  2. Admin bỏ qua các bước sau.
  3. global mà thiếu `skill:create:all` → 403 "Bạn không có quyền tạo prompt toàn hệ thống".
  4. department không có phòng ban → 400 "Chọn ít nhất một phòng ban".
  5. department có phòng ban ngoài của mình mà thiếu `skill:create:all` → 403 "Chỉ gán được cho phòng ban của bạn".
- **`can_edit`** (action là edit hoặc delete): admin, chủ sở hữu, hoặc có `skill:<action>:all`.

### 4.3 Mô hình

| Model | Trường |
|---|---|
| PromptIn | title 1–200; command 1–100; description ≤2000 (null); content 1–50000; tags = []; scope_type = "personal"; department_ids = []; source ≤20 (null → "wiki"); external_ref ≤200 |
| PromptPatch | title, command, description, content, tags, scope_type, department_ids — tất cả tùy chọn, cùng ràng buộc độ dài; không có source và external_ref |
| PromptOut | id, title, command, description, content, tags, scope_type, department_ids, department_names, owner_id, owner_name, source, external_ref, can_edit, created_at, updated_at |

`department_names` được tra từ bảng departments. Id không còn tồn tại bị bỏ. `can_edit` tính theo action edit.

### 4.4 Endpoint (đều cần get_current_user)

| Method + path | Hành vi |
|---|---|
| GET /api/prompts | Xem dưới |
| GET /api/prompts/{id} | Không có hoặc không xem được → 404 "Không tìm thấy prompt". Trả PromptOut. |
| POST /api/prompts (PromptIn) | Xem dưới |
| PATCH /api/prompts/{id} (PromptPatch) | Xem dưới |
| DELETE /api/prompts/{id} | 404 như trên; không phải chủ, admin, hoặc người có `skill:delete:all` → 403 "Bạn không có quyền xóa prompt này". Trả `{message:"Đã xóa prompt"}`. |

**GET /api/prompts**

- **Tham số:**
  - `q`: ILIKE trên title, command, description và content.
  - `scope_type`.
  - `department_id`: chứa trong department_ids.
  - `tag`: chứa trong tags.
  - `mine` = false: chỉ của mình.
  - `external_ref`: so khớp bằng.
  - `limit` = 200 (1–500).
- Áp quyền xem; sắp updated_at giảm dần.
- Trả `{items: PromptOut[], total}`. `total` đếm trước khi áp limit.

**POST /api/prompts**

- department_ids chỉ giữ khi scope department, ngược lại là [].
- Kiểm tra phạm vi, rồi chuẩn hóa command.
- **Upsert theo external_ref:** nếu có external_ref và đã có prompt cùng chủ + cùng external_ref, cập nhật bản đó thay vì tạo mới. Bản mới lấy source = (source hoặc "wiki"), cắt 20 ký tự.
- **Giá trị lưu:** title đã strip; description đã strip, rỗng thành null; tags đã chuẩn hóa.
- Trả PromptOut.

**PATCH /api/prompts/{id}**

- Không có hoặc không xem được → 404. Không có quyền sửa → 403 "Bạn không có quyền sửa prompt này".
- **Phạm vi**, khi có scope_type hoặc department_ids:
  - scope mới = gửi lên, hoặc giá trị cũ.
  - Phòng ban = gửi lên, hoặc cũ; chỉ khi scope department, ngược lại [].
  - Kiểm tra phạm vi lại rồi gán.
- **Các trường khác** chỉ cập nhật khi khác null, chuẩn hóa như POST. Description rỗng thành null.

---

## 5. Cài đặt quản trị (`app.routers.admin_settings`, tiền tố /api)

| Method + path | Quyền | Mô tả |
|---|---|---|
| GET /api/dashboard/stats | không | `{total_sources, total_departments, total_employees}` |
| GET /api/settings | get_current_user | Xem dưới |
| PUT /api/settings | org:settings:manage | Xem dưới |
| POST /api/settings/test-providers | không | `{embedding, llm, vision}`, mỗi phần `{success, message, details?}`, qua ProviderRegistry.test_all. Thiếu cấu hình → success false, message "Not configured: <lý do>". |
| POST /api/settings/test-embedding, /test-llm, /test-vision | không | `{success, message}`. Ngoại lệ → success false, message = nội dung ngoại lệ. Vision không có provider → "No vision provider configured". |
| GET /api/settings/providers | không | Xem dưới |
| POST /api/settings/test-ocr-connection | không | Xem 5.1 |
| POST /api/settings/test-ocr | không | Xem 5.2 |
| POST /api/settings/test-extraction | không | Xem 5.3 |

**GET /api/settings**

- Trả `ConfigService.get_all_for_ui()`: map khóa → giá trị.
- Che giá trị nhạy cảm:
  - Dài hơn 8 ký tự → 8 ký tự "•" + 4 ký tự cuối.
  - Ngắn hơn → toàn "•".
- Mỗi khóa nhạy cảm kèm khóa `<key>_configured` (bool).

**PUT /api/settings**

- Body `{settings: {str: str}}`, ghi bằng `set_batch`.
- Khóa lạ → false. Giá trị bắt đầu bằng "••••" (bản đã che) bị bỏ qua và báo true.
- Ghi kiểm toán: action "update", resource "settings"/"global", reason "Updated keys: <danh sách>".
- Trả `{updated: {key: bool}}`.

**GET /api/settings/providers**

- Trả `supported_providers()`: `{embedding, llm, vision: [{id, name, models:[{id, model_id, label, …tùy chọn}]}]}`.
- Trường model tùy chọn: context_window_tokens, max_output_tokens, supports_tools, supports_vision, dimension, max_input_tokens, cost_per_1m_input_tokens, cost_per_1m_output_tokens, cost_per_1m_tokens, cost_per_image, notes.
- Nhãn provider:

| id | Nhãn |
|---|---|
| google | Google Gemini |
| openai | OpenAI |
| anthropic | Anthropic |
| ollama | Ollama |
| voyage | Voyage AI |
| cohere | Cohere |

Các endpoint test-* **không có** dependency xác thực; test c2 dựa vào điều này (gọi không kèm token mà vẫn được 200). Xem mục 11.

### 5.1 POST /api/settings/test-ocr-connection

- **Body JSON (tùy chọn):** `{base_url?, api_key?, model?, model_spec_id?}`.
- **Phân giải endpoint:**
  - Có model_spec_id → `resolve_ocr_endpoint(db, spec_id)` (mục 6.3). HTTPException → trả `{success:false, message:<detail>}`.
  - Thiếu giá trị → lấy cấu hình `ocr_base_url`, `ocr_api_key`, `ocr_model`.
- **Gọi** `app.services.ocr_service.ocr_service.test_connection(base_url=, api_key=, model=)`, nhận về `(ok, msg, latency_ms)`.
- **Trả** `{success: ok, message: msg, latency_ms}`. Test: patch trả (True, "Connection OK", 120) thì response phải là success true, message "Connection OK", latency_ms 120.

### 5.2 POST /api/settings/test-ocr (multipart)

- **Trường form:**
  - `file`.
  - `target_page` = 1.
  - `override_base_url`, `override_api_key`, `override_model`, `override_prompt`.
  - `model_spec_id`.
  - `llm_refine` = false.
- **Ảnh đầu vào:** dùng trực tiếp, mime theo content type.
- **PDF:**
  - Trang được kẹp trong khoảng hợp lệ, render ở zoom 2×, ra JPEG chất lượng 85.
  - PDF không có trang → error "File PDF không có trang nào".
  - Lỗi render → "Không thể render trang PDF: <e>".
- **Chọn model:** override → cấu hình `ocr_model` → `settings.ocr_model`.
- **Chọn prompt:** override → cấu hình `ocr_prompt`.
- **Gọi** `ocr_service.ocr_image(image_bytes=, mime_type=, prompt=, base_url=, api_key=, model=, db=)`. Trả None → error "OCR không trả về nội dung hoặc OCR endpoint chưa được cấu hình.".
- **llm_refine:**
  - Dùng provider vision đang chọn với hàm hiệu đính OCR (tài liệu 03).
  - Không có vision → refine_error "Chưa cấu hình Vision Model để hiệu đính.".
  - Kết quả rỗng → refine_error "LLM không trả về kết quả hợp lệ — giữ bản OCR.".
  - Thành công: raw_text = bản OCR, text = bản đã hiệu đính.
- **Trả:** success, text, model, latency_ms (≥ 1), chars_count, words_count, page_number, total_pages, error, raw_text, ocr_latency_ms, refine_model, refine_latency_ms, refine_error.

### 5.3 POST /api/settings/test-extraction (multipart)

- **Trường form:**
  - `file`.
  - `max_pages` = 3 (≤ 0 nghĩa là tất cả).
  - `engine`, `pdf_parser_engine`, `excel_parser_engine`, `ocr_mode`.
  - `strip_headers_footers`, `enhance_headings`.
  - `override_ocr_base_url`, `override_ocr_api_key`, `override_ocr_model`.
  - `ocr_llm_refine`.
- **Mặc định:**

| Tham số | Mặc định |
|---|---|
| pdf engine | cấu hình `pdf_parser_engine`, hoặc "pdfplumber" |
| excel engine | `excel_parser_engine`, hoặc "openpyxl" |
| ocr_mode | "auto" |
| strip, enhance | bật, trừ khi cấu hình là "false" |
| refine | bật khi cấu hình `ocr_llm_refine` == "true" |

- **Bộ phân tích theo loại file:**
  - PDF → PDFParser với `ocr_fallback_vision=False`.
  - xlsx/xls → ExcelParser.
  - Còn lại → bộ trích văn bản chung (tài liệu 03).
- **Ảnh trong DOCX:**
  - Nhúng thành data URI, tổng ngân sách 8 MB.
  - Ảnh < 2048 byte bị bỏ.
  - Vượt ngân sách hoặc không phải ảnh → ghi chú "*[Ảnh — quá dung lượng xem trước]*".
- **Trả:** `{success, file_name, file_type, stats:{total_pages, preview_pages_count, ocr_pages_count, total_words, total_chars, latency_ms}, pages:[{page_number, content, is_ocr, char_count, word_count}], error}`. Test: PDF một trang với max_pages=1 → một phần tử pages, total_pages ≥ 1.

---

## 6. Mô hình tùy chỉnh, catalog và OCR

### 6.1 `app.ai.custom_models`

**Hằng số**

| Hằng | Giá trị |
|---|---|
| CUSTOM_PREFIX | "custom/" |
| KINDS | llm, vision, embedding, ocr |
| PROTOCOLS | openai, anthropic |
| PROVIDERS | openai, anthropic, google, custom |
| EMBEDDING_DIMENSIONS | (768, 1024, 1536, 3072) |
| MAX_MODEL_ID_LEN | 100 |

**URL tương thích OpenAI**

| Provider | URL |
|---|---|
| openai | https://api.openai.com/v1 |
| anthropic | https://api.anthropic.com/v1/ |
| google | https://generativelanguage.googleapis.com/v1beta/openai/ |
| Anthropic gốc (native) | https://api.anthropic.com |

**Lưu trữ**

- Khóa cấu hình "custom_models" chứa danh sách JSON các model.
- Khóa API riêng từng model: "custom_model_api_key__" + 24 ký tự hex đầu của sha256("<kind>:<id>").
- Đọc và ghi qua `ConfigService(db).get/set`, tra lúc gọi tại `app.services.config_service.ConfigService` để test patch được.

**`CustomModel`** là dataclass:

| Trường | Mặc định |
|---|---|
| id | |
| kind | |
| model_id | |
| label | |
| base_url | |
| protocol | "openai" |
| dimension | None |
| provider | "custom" |

Bản ghi cũ không có provider → "custom".

**Hàm**

| Hàm | Hành vi |
|---|---|
| provider_endpoint(kind, provider) -> (base_url, protocol) | anthropic + llm → (URL native, "anthropic"); còn lại → (URL tương thích, "openai") |
| provider_key_config_key(kind, provider) | "<kind>_api_key__<provider>" |
| is_custom(spec_id) | bắt đầu bằng "custom/" |
| make_id(kind, model_id, dimension=None) | embedding → "custom/<dim>/<model_id>"; còn lại → "custom/<model_id>". Vd. make_id("llm","qwen3:32b") = "custom/qwen3:32b"; make_id("embedding","bge-m3",1024) = "custom/1024/bge-m3" |
| parse_id(spec_id) -> (Optional[int], rest) | Bỏ tiền tố. Nếu đoạn đầu toàn chữ số **và** còn phần sau → (int, phần sau); ngược lại (None, rest). Vd. "custom/org/model-x" → (None, "org/model-x") |
| api_key_config_key(kind, id), is_custom_api_key(key) | khóa API riêng / nhận diện khóa đó |
| list_custom(db, kind=None) | danh sách CustomModel, lọc theo kind nếu có |
| get_custom(db, kind, id) | CustomModel hoặc None |
| save_custom(db, m, api_key) | Thay bản cùng kind + id hoặc thêm mới. api_key None → giữ khóa cũ; chuỗi → ghi |
| delete_custom(db, kind, id) -> bool | Xóa, làm trống khóa API |
| get_api_key(db, kind, id) | Khóa riêng, "" nếu không có |
| resolve_api_key(db, m) | Xem dưới |

**`resolve_api_key(db, m)`**

1. Dùng khóa riêng của model nếu có.
2. Provider "custom" thì dừng ở đây: trả "" nếu không có.
3. Dùng khóa chung `<kind>_api_key__<provider>`.
4. Riêng kind ocr: dự phòng `vision_api_key__<provider>`.
5. Không có gì → "".

### 6.2 Catalog và ProviderRegistry (tài liệu 03 nêu chi tiết; đây là phần test c2 dùng)

**Catalog**

- `ProviderType` là enum, gồm ít nhất OPENAI, ANTHROPIC, GOOGLE.
- `LLM_CATALOG` và `VISION_CATALOG` có tập provider đúng bằng {openai, anthropic, google}. `EMBEDDING_CATALOG` có tập provider {openai, google}.
- `embedding_catalog.get_spec(id)`:
  - Id lạ, hoặc id custom có số chiều ngoài EMBEDDING_DIMENSIONS (vd. "custom/999/…") → ném `UnknownEmbeddingModel` (lớp con của KeyError).
- `llm_catalog.get_spec` xử lý được id "custom/…".

**ProviderRegistry**

- **Hằng:** `ANTHROPIC_OPENAI_BASE_URL` = "https://api.anthropic.com/v1/". `DEFAULT_LLM_SPEC_ID` = `DEFAULT_VISION_SPEC_ID` = "openai/gpt-6-luna".
- **Khóa cấu hình:** active_llm_model_spec_id, active_vision_model_spec_id, active_embedding_model, ocr_model_spec_id, `<kind>_api_key__<provider>`.
- **`ProviderRegistry(None)`** cung cấp:
  - `_load_llm_config()`
  - `_load_embedding_config(spec_id=None)`
  - `_load_vision_config()`
  - `get_active_llm_spec_id()`
  - `get_active_vision_spec_id()`
- **Spec đang chọn không còn tồn tại** và không suy được từ cặp khóa cũ → dùng giá trị mặc định ("openai/gpt-6-luna").
- **Khóa cũ** `llm_api_key` / `vision_api_key`:
  - Bắt đầu bằng "sk-ant-" → chỉ dùng cho anthropic.
  - Ngược lại → chỉ dùng cho provider khác anthropic. Vd. khóa OpenAI cũ không cấp cho Anthropic, nên khóa Anthropic là "".
- **Model custom:**
  - provider = ProviderType(protocol); api_key thiếu → "none".
  - Model custom đã bị xóa → lỗi "Custom model <id> was deleted. Pick another model in Settings.".
  - Embedding custom → extra["send_dimensions"] = False.
- **Vision không custom** với provider anthropic → base_url = ANTHROPIC_OPENAI_BASE_URL, khóa `vision_api_key__anthropic`.
- **Embedding:**
  - Khóa: `embedding_api_key__<provider>`, rồi khóa cũ `embedding_api_key`.
  - base_url: cấu hình `embedding_base_url`.
- **Lỗi khi chưa cấu hình:**
  - "No active embedding model. Pick one in Settings → Embedding."
  - "No active LLM. Pick one in Settings → LLM."
  - "No active vision model. Pick one in Settings → Vision."
- **`OpenAILLM(ProviderConfig(...))._is_reasoning_or_gpt5()`**: True với các model thuộc họ reasoning hoặc GPT-5 trở lên, gồm "gpt-6-luna".

### 6.3 Router `app.routers.admin_custom_models` (mọi endpoint cần org:settings:manage)

**OCR_PRESETS** là dict theo id "provider/model". Mỗi giá trị có:

- `provider`, `label`, `model_id`;
- `base_url` = provider_endpoint("ocr", provider)[0].

| id | label |
|---|---|
| openai/gpt-6-luna | GPT-6 Luna |
| anthropic/claude-sonnet-5-5 | Claude Sonnet 5.5 |
| anthropic/claude-haiku-5-5 | Claude Haiku 5.5 |
| google/gemini-3.5-flash | Gemini 3.5 Flash |
| google/gemini-3.1-flash-lite | Gemini 3.1 Flash-Lite |

Tập provider của các preset là {openai, anthropic, google}.

**Mô hình**

| Model | Trường |
|---|---|
| CustomModelOut | id, kind, model_id, label, base_url, protocol, dimension, provider, api_key_configured (theo resolve_api_key) |
| CustomModelIn | kind, model_id, provider = "custom", base_url = "", label = None, protocol = "openai", dimension = None, api_key = None, original_id = None |

Trong CustomModelIn, `api_key` là None hoặc chuỗi bắt đầu bằng "••••" thì giữ khóa cũ.

**Hàm cấp module** (test monkeypatch các tên này trên module):

- `log_audit`: import vào module, tra lúc gọi.
- `_active_ids(db) -> {llm, vision, embedding, ocr}`: id đang dùng của từng kind.
- `resolve_ocr_endpoint(db, spec_id) -> (base_url, model_id, api_key)`:
  - **Custom:**
    - Không thấy → 400 "Unknown OCR model '<id>'".
    - Khóa thiếu → "none".
  - **Preset:**
    - Khóa lấy từ `ocr_api_key__<provider>`, rồi `vision_api_key__<provider>`.
    - Thiếu cả hai → 400 "No <provider> API key. Enter the API key for this model.".
- **Áp OCR**, dùng khi chọn hoặc lưu model OCR đang dùng:
  - Khóa gõ tay cho preset được lưu vào `ocr_api_key__<provider>`.
  - Ghi các khóa `ocr_base_url`, `ocr_model`, `ocr_api_key`, `ocr_model_spec_id`.

**`save_custom_model(req, db, user)`** (handler POST; test gọi trực tiếp theo vị trí, db chỉ có `commit()`)

Kiểm tra, theo thứ tự:

| Điều kiện | Lỗi |
|---|---|
| kind lạ | 400 "kind must be one of llm, vision, embedding, ocr" |
| provider lạ | 400 "provider must be one of openai, anthropic, google, custom" |
| anthropic + embedding | 400 "Anthropic has no embedding models." |
| protocol lạ | 400 "protocol must be one of openai, anthropic" |
| protocol anthropic mà kind khác llm | 400 "Anthropic protocol is only supported for LLM; use an OpenAI-compatible URL." |
| model_id sau strip ngoài 1–100 | 400 "Model name must be 1–100 characters" |
| base_url không bắt đầu bằng http:// hoặc https:// | 400 "Base URL must start with http:// or https://" |
| embedding với dimension ngoài danh sách | 400 "dimension must be one of 768, 1024, 1536, 3072" |

Provider custom dùng protocol và base_url từ body. Provider khác dùng `provider_endpoint`.

Lưu:

1. `id = make_id(kind, model_id, dimension)`.
2. Có original_id mà không thấy → 404 "Model not found".
3. "Đổi tên" nghĩa là có bản gốc và id mới khác id gốc.
4. Id mới đã tồn tại, trong trường hợp thêm mới hoặc đổi tên → 409 "Model này đã có trong danh sách.".
5. Đổi tên model đang dùng (id gốc = `_active_ids(db)[kind]`) → 409 "Model đang dùng: không đổi được tên model/số chiều. Chuyển sang model khác trước.". Chỉ đổi label thì vẫn được.
6. Đổi tên mà không gửi khóa mới → chuyển khóa cũ sang id mới; xóa bản cũ.
7. label mặc định = model_id.
8. Là model OCR đang dùng → áp OCR.
9. Ghi kiểm toán: action "save_custom_model", reason "Saved <kind> model <id> (<base_url>)". Commit. Trả CustomModelOut.

**Endpoint**

| Method + path | Hành vi |
|---|---|
| GET /api/settings/custom-models?kind= | list[CustomModelOut] |
| POST /api/settings/custom-models (CustomModelIn) | save_custom_model |
| DELETE /api/settings/custom-models?kind=&id= | Xem dưới |
| GET /api/settings/ocr/catalog | Xem dưới |
| POST /api/settings/ocr/select `{model_spec_id, api_key?}` | Phân giải endpoint, áp OCR, ghi kiểm toán "select_ocr_model". Trả `{active_spec_id}`. |
| POST /api/settings/models/discover `{kind, provider="custom", base_url, api_key}` | Xem dưới |

**DELETE /api/settings/custom-models**

- Lỗi:
  - Model đang dùng → 409 "This model is in use. Switch to another model first.".
  - Embedding đang được job nhúng lại dùng → 409 "A re-embed job is using this model.".
  - Không thấy → 404 "Model not found".
- Thành công: ghi kiểm toán "delete_custom_model". Trả `{deleted: id}`.

**GET /api/settings/ocr/catalog**

- Trả `{active_spec_id, specs:[{id, provider, label, base_url, model_id, custom, group, api_key_configured}]}`.
- Cấu hình cũ chưa có ocr_model_spec_id → suy active bằng cách khớp `ocr_model` với model_id của preset.
- Mục custom có provider "custom" và group = provider của model.

**POST /api/settings/models/discover**

- Trả `{models:[id…]}`.
- **Khóa API:**
  - Custom: kiểm tra http(s); khóa thiếu → "none".
  - Provider đã biết mà chưa có khóa → 400 "Chưa có API key <provider>. Lưu key trước.".
- Gọi danh sách /models kiểu OpenAI, timeout 15 giây, không thử lại. Lỗi → 502 "Không lấy được danh sách model: <e>".
- **Xử lý danh sách:** bỏ tiền tố "models/", bỏ trùng, sắp xếp. Embedding với provider không phải custom chỉ giữ id chứa "embed".

---

## 7. (dành chỗ) — xem mục 8 cho thống kê

## 8. Thống kê (`/api/admin/stats`, mọi endpoint cần org:settings:manage)

### 8.1 Khoảng ngày

- Tham số query có alias `from` và `to` (ISO date).
- **Mặc định:** `to` = hôm qua theo UTC; `from` = to − 29 ngày.
- **Lỗi:**
  - from > to → 400 "from must be <= to".
  - Quá 366 ngày → 400 "range cannot exceed 366 days".

### 8.2 Endpoint

**GET /overview** trả `{as_of, kpis:{key: number}, top_gap_topic, top_contributor}`.

- Cửa sổ là 30 ngày gần nhất đến hôm nay. Không có dòng rollup nào thì chạy `run_daily_rollup(hôm nay)` tại chỗ.
- Các khóa KPI (lấy giá trị mới nhất):
  - wiki.pages.total, wiki.pages.stale_30d, wiki.pages.orphan, wiki.pages.updated;
  - draft.pending, draft.time_to_review_avg_seconds, compile_plan.pending_review;
  - mcp.active_users, mcp.weekly_active_users, mcp.queries.total, mcp.queries.zero_result;
  - audit.denied.
- Thiếu wiki.pages.total → đếm trực tiếp số trang wiki, không tính các slug index, log, hot.
- top_gap_topic = phần tử đầu của mcp.gaps.zero_result mới nhất; top_contributor = phần tử đầu của draft.top_contributors mới nhất.

**Các endpoint mục** (tham số from và to) trả SectionResponse:

- `from_date`, `to_date`;
- `series`: {metric: [{date, value, dimensions, items}]};
- `latest`: {metric vô hướng: số};
- `latest_lists`: {metric danh sách: items}.

| Endpoint | Metric vô hướng | Metric danh sách |
|---|---|---|
| GET /content | wiki.pages.total, .created, .updated, .stale_30d, .orphan; wiki.revisions.daily | wiki.pages.by_type, wiki.top_pages |
| GET /contribution | draft.created, .approved, .rejected, .pending, draft.time_to_review_avg_seconds, compile_plan.pending_review | draft.top_contributors, draft.top_reviewers, draft.created.by_source |
| GET /usage | mcp.queries.total, .zero_result, .error, .denied; mcp.active_users, mcp.weekly_active_users, mcp.latency_ms_avg | mcp.queries.by_tool, mcp.top_employees |

**GET /gaps?limit=50 (1–500)**

- Trả `{from_date, to_date, items:[{normalized, count, samples (≤5), requester_ids (đã sắp)}]}`.
- Gộp items hằng ngày theo `normalized`, sắp theo count giảm dần.

**GET /export/{section}.csv**

- section ∈ content, contribution, usage, gaps. Khác → 404 "unknown section: <X>".
- Cột: date, metric_key, dimensions_json, value_numeric, value_json.
- Media type text/csv; tên file đính kèm `stats_<section>_<from>_<to>.csv`.

**POST /rollup?target=YYYY-MM-DD**

- Mặc định là hôm qua UTC. Sai định dạng → 400 "target must be ISO date YYYY-MM-DD".
- Trả `{target_date, sections_written}`.

### 8.3 `stats_aggregator.run_daily_rollup(target_date)`

- **Trả** `{content, contribution, usage, gaps, audit}`: số dòng đã ghi của từng phần, hoặc −1 nếu phần đó lỗi.
- **Cửa sổ UTC:** [ngày 00:00, +1 ngày). Mỗi phần commit riêng.
- **Upsert** theo khóa duy nhất (date, metric_key, dimensions_hash):
  - dimensions_hash = md5 của JSON chuẩn hóa (khóa sắp xếp); "" khi không có dimensions.
  - Cập nhật value_numeric, value_json, computed_at.

**Phần Content**

- Tổng số trang; số trang tạo và số trang cập nhật trong cửa sổ.
- stale: updated_at < cuối cửa sổ − 30 ngày.
- orphan: slug chưa từng là đích của liên kết nào.
- Số revision trong cửa sổ.
- by_type: dimension page_type, thiếu thì "unknown".
- top_pages: 10 trang nhiều revision nhất, items {slug, title, revisions}.

**Phần Contribution** (bản nháp wiki)

- created trong cửa sổ.
- approved và rejected tính theo reviewed_at trong cửa sổ và theo status.
- pending tính trên toàn thời gian.
- Thời gian duyệt trung bình (giây) = reviewed_at − created_at, xét các bản duyệt trong cửa sổ.
- by_source: dimension source, thiếu thì "unknown".
- top 10 người đóng góp {author_id, name hoặc "(unknown)", count}; top 10 người duyệt {reviewer_id, name, count}.
- compile_plan.pending_review = số kế hoạch biên soạn có status pending_review.

**Phần Usage** (mcp_query_log)

- Tổng số truy vấn.
- zero_result = result_count 0 của nhóm công cụ tìm kiếm: search_wiki, list_wiki_pages, list_sources, get_knowledge_type_docs.
- error và denied theo status.
- DAU = số nhân viên khác nhau trong cửa sổ; WAU = số nhân viên khác nhau trong 7 ngày kết thúc ở cuối cửa sổ.
- Latency trung bình.
- by_tool {tool_name, count}; top 10 nhân viên.

**Phần Gaps** (lỗ hổng tri thức)

- Lấy các dòng zero-result của nhóm công cụ trên có query_text.
- **Chuẩn hóa query_text:**
  - lowercase;
  - bỏ dấu câu ASCII;
  - bỏ stopword tiếng Anh và tiếng Việt không dấu;
  - nối lại bằng khoảng trắng, cắt 200 ký tự;
  - rỗng thì bỏ.
- **Stopword tiếng Anh:** the, a, an, of, for, to, in, on, at, and, or, is, are, was, were, be, been, what, how, why, where, when, who, do, does, did, i, we, you, it, this, that, these, those, about, with.
- **Stopword tiếng Việt:** la, lam, co, khong, nao, the, nay, do, thi, va, hoac, cua, trong, voi, cho, den, ai, gi, sao, minh, ban, ta, ho, duoc, phai, se, da, dang.
- **Mỗi nhóm:** count, samples (tối đa 5 câu gốc khác nhau), requester_ids.
- Top 100 nhóm theo count được ghi vào value_json.items của metric `mcp.gaps.zero_result`.

**Phần Audit**

- audit.denied = số dòng kiểm toán có decision không phân biệt hoa thường là "deny", trong cửa sổ. Xem mục 12.
- audit.denied.by_resource: items {resource_type, count}.

**Cron:** `daily_stats_rollup_cron` chạy lúc 02:00 cho ngày hôm qua theo UTC.

**Bảng `stats_daily_rollup`**

| Cột | Kiểu |
|---|---|
| id | UUID PK |
| date | timestamptz |
| metric_key | varchar(80) |
| dimensions | JSONB null |
| dimensions_hash | varchar(64), mặc định "" |
| value_numeric | float null |
| value_json | JSONB null |
| computed_at | timestamptz |

- Unique `uq_stats_rollup_keys` (date, metric_key, dimensions_hash).
- Index (date) và (metric_key, date).

---

## 9. Thông báo

### 9.1 Router (get_current_user)

| Method + path | Hành vi |
|---|---|
| GET /api/notifications?unread=false&limit=50 (1–200)&offset=0 | Danh sách của chính người dùng, mới nhất trước. NotificationResponse: id, type, subject, body, target_type, target_id, actor_id, read_at (ISO hoặc null), created_at (ISO) |
| GET /api/notifications/unread-count | `{count}` |
| POST /api/notifications/{id}/read | Không phải của mình hoặc không có → 404 "Notification not found"; đặt read_at (chỉ lần đầu). Trả NotificationResponse |
| POST /api/notifications/read-all | `{updated: số dòng}` |

### 9.2 Service (`app.services.notification_service`)

**NotificationType**

- `wiki_draft.` ghép với submitted, resubmitted, approved, rejected, changes_requested, withdrawn.
- `skill_contribution.` ghép với cùng tập hậu tố.

**Hàm**

| Hàm | Hành vi |
|---|---|
| notify(db, recipient_id, type, subject, target_type, target_id, body="", actor_id=None) | Thêm dòng (người gọi commit), đưa vào hàng chờ gửi ngoài |
| notify_each(db, items[{recipient_id, subject, body, target_id}], type, target_type, actor_id=None, exclude_actor=True) | Mỗi mục một thông báo |
| notify_many(db, recipient_ids, type, subject, target_type, target_id, body="", actor_id=None, exclude_actor=True) | Bỏ trùng, bỏ chính actor |
| get_reviewers_for_scope(db, scope_type, scope_id) | Nhân viên có role admin, hoặc global_role ∈ {admin, knowledge_manager} |
| get_global_reviewers(db) | **Phải có**, trả cùng tập như trên. Nguồn gốc gọi hàm này nhưng thiếu định nghĩa |

**Hàng chờ gửi ngoài**

- Trong request: danh sách nằm trong ContextVar theo request. Ngoài request: dict theo session.
- Các hàm:
  - `init_request_dispatch_scope()`;
  - `take_pending_dispatch(db=None)`;
  - `dispatch_pending(db=None)`: sau commit, mở phiên mới và gọi gửi ngoài.

### 9.3 Gửi ngoài (`notification_dispatch`)

**Email** (khi `smtp_enabled`)

- **Khóa cấu hình:**

| Khóa | Mặc định |
|---|---|
| smtp_host | |
| smtp_port | 587 |
| smtp_username | |
| smtp_password | |
| smtp_from | "arkon@localhost" |
| smtp_use_tls | "true" |

- Mỗi người nhận có email nhận một thư.
- Tiêu đề: subject của mục nếu chỉ có một mục, nếu không "Arkon — N new notifications".
- Thân thư văn bản thuần: lời chào, các mục, rồi lời mời mở Arkon.
- Dùng STARTTLS, timeout 15 giây.

**Webhook** (khi `webhook_enabled`)

- Khóa `webhook_url`, `webhook_secret`.
- POST JSON `{events:[{id, type, subject, body, target_type, target_id, recipient_id, actor_id, created_at}]}`.
- Header:
  - `Content-Type: application/json`;
  - `User-Agent: Arkon-Webhook/1`;
  - khi có secret: `X-Arkon-Signature: sha256=<HMAC-SHA256 hex của body>`.
- Timeout 10 giây.

Các kênh chạy song song. Mọi lỗi chỉ ghi log và bị nuốt.

**Bảng `notifications`**

| Cột | Kiểu |
|---|---|
| id | UUID PK |
| recipient_id | FK employees CASCADE |
| type | varchar(80) |
| subject | varchar(200) |
| body | text, mặc định "" |
| target_type | varchar(40) |
| target_id | varchar(100) |
| actor_id | FK SET NULL |
| read_at | timestamptz null |
| created_at | timestamptz |

Index: (recipient_id, read_at), (created_at), (target_type, target_id).

---

## 10. Kiểm toán (audit)

### 10.1 Router (tiền tố /api/audit, quyền "audit.read")

| Method + path | Hành vi |
|---|---|
| GET /api/audit/log?page=1&page_size=50 (1–200)&principal_id&action&decision&resource_type | `{items, total, page, page_size}`, mới nhất trước. Item: id, timestamp, principal_id, principal_type, principal_name, principal_email, action, resource_type, resource_id, decision, reason, seq, trace_id, event_hash |
| POST /api/audit/verify | Kết quả `verify_chain(db)` |

### 10.2 `app.services.audit_service.log_audit(db, user, action, resource_type, resource_id, decision="ALLOW", reason=None)`

- Gọi `audit_chain.record(principal_id=user.id, action, resource_type, resource_id, decision, reason)`.
- Tham số `db` bị bỏ qua (có thể là None); việc ghi chạy trong giao dịch riêng.

### 10.3 Model `AuditLog` (bảng audit_log)

| Thuộc tính | Cột | Kiểu |
|---|---|---|
| id | id | UUID PK |
| seq | seq | bigint unique not null |
| timestamp | timestamp | timestamptz not null |
| principal_id | principal_id | UUID not null |
| principal_type | principal_type | varchar(20), mặc định human |
| action | action | varchar(50) |
| resource_type | resource_type | varchar(50) |
| resource_id | resource_id | varchar(100) |
| decision | decision | varchar(10) |
| reason | reason | text |
| metadata_ | metadata | JSONB |
| trace_id | trace_id | varchar(64) not null |
| prev_hash | prev_hash | varchar(64) |
| event_hash | event_hash | varchar(64) |

Index: timestamp, principal_id, (resource_type, resource_id), trace_id.

**Bảng `audit_chain_head`**

| Cột | Kiểu |
|---|---|
| id | int PK (luôn = 1) |
| last_seq | bigint |
| last_hash | varchar(64) |
| key_fingerprint | varchar(16) |
| signature | varchar(64) |
| updated_at | timestamptz |

### 10.4 `app.services.audit_chain`

**Hằng**

| Hằng | Giá trị |
|---|---|
| CHAIN_VERSION | 2 |
| GENESIS_HASH | "GENESIS_HASH_ARKON_WIKI_CHAIN_0000000000" |
| BASELINE_ACTION | "AUDIT_CHAIN_BASELINE" |
| NIL_UUID | UUID toàn số 0 |

Khóa advisory của ứng dụng là 7420501003; migration dùng 7420501004.

**Khóa HMAC**

- `settings.audit_hmac_key` (env `AUDIT_HMAC_KEY`).
- Rỗng → khóa dẫn xuất bằng HMAC(SECRET_KEY, một nhãn cố định), kèm cảnh báo một lần.
- Fingerprint = 16 ký tự hex đầu của sha256 trên một tiền tố cố định ghép với khóa.

**Băm từng mục**

- Các trường đưa vào:
  - v (CHAIN_VERSION), seq, id, trace_id;
  - principal_id, principal_type;
  - action, resource_type, resource_id, decision, reason, metadata;
  - timestamp (ISO UTC có micro giây);
  - prev_hash.
- JSON chuẩn hóa (khóa sắp xếp, dạng gọn, UTF-8), rồi HMAC-SHA256 ra hex.
- Chữ ký đầu chuỗi (head) = HMAC trên chuỗi "head:<seq>:<hash>".

**trace_id** lấy từ trace_context. Không có thì sinh "tr-YYYYMMDD-<8 hex>". Cắt 64 ký tự.

**`append_entry(session, *, principal_id, action, resource_type, resource_id, decision="allow", reason=None, principal_type="human", metadata=None)`**

1. Lấy khóa advisory giao dịch, đọc head (id = 1) và mục cuối.
2. **Log rỗng:** chèn mục baseline trước. Mục baseline có:
   - principal NIL, principal_type "system", action BASELINE_ACTION, resource "audit"/"audit_log", prev_hash = GENESIS_HASH;
   - metadata {chain_version, algorithm "HMAC-SHA256", legacy_rows, legacy_digest}.
   - `legacy_digest` = sha256 trên dãy JSON đã sắp khóa của từng dòng `audit_log_legacy`, mỗi dòng kèm ký tự xuống dòng, theo thứ tự (timestamp, id).
   - Không có bảng legacy → 0 dòng và sha256 của chuỗi rỗng.
   - Đã có head mà không có mục nào → metadata "_chain_alert": "head_without_entries", coi là không tin cậy.
3. **Có mục:** tin cậy khi head khớp mục cuối và chữ ký hợp lệ.
4. **Không tin cậy:** metadata "_chain_alert": "head_mismatch_or_missing", log mức critical, **không** sửa head.
5. Cắt độ dài: action 50, resource_type 50, resource_id 100, decision 10.
6. Chỉ cập nhật head (last_seq, last_hash, fingerprint, signature, updated_at) khi tin cậy.
7. Sau commit, ghi log neo "AUDIT_ANCHOR seq=… hash=…". Rollback thì bỏ.

**`record(**kwargs)`**: mở phiên riêng, gọi append_entry, commit, trả mục đã ghi (có id, seq, trace_id). Ghi đồng thời vẫn tuyến tính: 20 lần ghi song song cộng baseline ra 21 mục, seq liên tục.

**`verify_chain(session, batch_size=2000)`** duyệt seq tăng dần theo lô.

Khi lỗi, trả `{valid:false, broken_at_event_id, broken_at_seq, total_events, verified_at, algorithm, message}`. Các lỗi theo từng mục:

| Lỗi | message (phải chứa) |
|---|---|
| hở seq | "Sequence gap: expected X, found Y; …" (chứa "gap") |
| prev_hash không khớp | "… does not link to its predecessor; the chain was forked or replaced." |
| HMAC không khớp (sửa bất kỳ trường nào) | "HMAC of entry … does not match its content; the entry was modified." |

Kiểm tra head (broken_at_event_id = None):

| Lỗi | message |
|---|---|
| không có head nhưng có mục | "Signed chain head is missing; …" |
| fingerprint khác | "The current HMAC key differs from the one that signed the chain (AUDIT_HMAC_KEY changed or lost)." |
| chữ ký sai | "Signature of the chain head is invalid; the head was modified." (chứa "invalid") |
| head khác mục cuối | "Last entry (N) does not match the signed head (M); the tail was deleted." (chứa "tail") |
| fingerprint legacy trong baseline không khớp | seq 1, "The archived pre-chain log no longer matches the fingerprint recorded in the baseline." (chứa "archived") |

Khi không lỗi:

- Log rỗng và không có head → `{valid:true, message:"No audit entries to verify yet."}`.
- Hợp lệ → `{valid:true, total_events, verified_at, algorithm, chain_version, head_seq, head_hash, legacy_rows, message:"All N entries match the HMAC chain and the signed head; no tampering detected."}`.

### 10.5 `app.utils.trace_context` (hoặc module tương đương mà test import)

**Hàm**

- `set_trace_id(value) -> Token`
- `reset_trace_id(token)`
- `get_trace_id() -> Optional[str]`, mặc định None
- `new_trace_id() -> str` (uuid4)

**`CorrelationIdMiddleware`** (ASGI thuần, chỉ áp cho http)

- Header `x-correlation-id` khác rỗng và in được → dùng lại, cắt 64 ký tự. Nếu không → sinh uuid4 (≥ 32 ký tự).
- Đặt ngữ cảnh trong suốt request, reset sau đó; ra khỏi request `get_trace_id()` là None.
- Response có header `x-correlation-id`, thay giá trị cũ nếu có.

### 10.6 Migration `alembic/versions/049_audit_hash_chain.py`

- revision "049_audit_hash_chain", down_revision "048_security_label_acl". Có `upgrade()` và `downgrade()`.
- **upgrade:**
  1. Lấy khóa advisory.
  2. Đổi tên audit_log → audit_log_legacy, kèm pkey và các index `ix_audit_log_{timestamp, principal, resource}` → `ix_audit_log_legacy_*`.
  3. Tạo audit_log mới và audit_chain_head như 10.3.
  4. Tạo hàm `audit_guard_immutable()`, ném ngoại lệ có chữ "append-only", errcode insufficient_privilege.
  5. Tạo trigger:
     - audit_log và audit_log_legacy: BEFORE UPDATE OR DELETE theo dòng, cộng BEFORE TRUNCATE theo câu lệnh.
     - audit_chain_head: BEFORE DELETE theo dòng, cộng TRUNCATE.
  6. Migration **không** tạo baseline; ứng dụng tạo khi ghi lần đầu.
- **downgrade:** gỡ trigger, hàm, head và bảng mới; đổi tên ngược lại. Bảng audit_log cũ không có cột seq. Upgrade chạy lại được.
- **Cột legacy** mà test dựng: id, timestamp, principal_id, principal_type, action, resource_type, resource_id, scope_type, scope_id, decision, reason, metadata.

---

## 11. Ký hiệu mà test c2 import và hành vi kỳ vọng

### tests/test_mcp_scope.py

| Ký hiệu | Kỳ vọng |
|---|---|
| `app.mcp.tools.register_tools(FastMCP(...))` | Đăng ký công cụ; test gọi bằng `mcp.call_tool(name, args)` |
| `app.mcp.resources.register_resources(mcp)` | Test gọi `mcp.read_resource("arkon://wiki-index")` |
| patch `app.mcp.tools._get_identity` (async) | Trả (identity, None). identity là SimpleNamespace(is_admin, allowed_knowledge_types, allowed_source_ids=None, department_ids, department_names, clearance_level), **không có employee_id** |
| patch `app.mcp.tools._get_allowed_source_ids` (async) | Tập chuỗi hoặc None |
| patch `app.database.async_session_factory` | Context manager async trả session giả (execute và get là mock) |
| patch `app.services.storage_service.storage_service.download_file` | query_table ngoài phạm vi → kết quả chứa "Access denied" và không gọi download; trong phạm vi → có gọi |
| patch `app.services.wiki_service.render_scoped_index` | Công cụ read_wiki_index và resource wiki-index gọi với kwargs allowed_kt_slugs, department_ids, all_scopes; không gọi `get_page_by_slug` |
| patch.object(wiki_service, "list_pages") rồi gọi `render_scoped_index` thật | list_pages nhận allowed_kt_slugs, department_ids, all_scopes; đầu ra chứa "[[dieu-1|Điều 1]]" |
| get_document_relations, allowed = set() | Trả chuỗi chứa "chưa được cấp quyền", `session.execute` không được gọi |
| get_document_relations, allowed khác rỗng | SQL đầu tiên chứa "source_id IN" và "unit_type"; mọi SQL đụng legal_units chứa "source_id IN" |

### tests/test_mcp_forwarded_identity.py

- `from app.mcp.tools import forwarded_role`, có hành vi như 1.3.
- `settings.mcp_trust_forwarded_identity` mặc định False.

### tests/test_custom_models.py

- `app.ai.custom_models` (as cm): CustomModel, make_id, parse_id, save_custom, get_api_key, get_custom, list_custom, delete_custom, provider_endpoint, resolve_api_key, EMBEDDING_DIMENSIONS.
- Catalog: ProviderType, EMBEDDING_CATALOG, LLM_CATALOG, VISION_CATALOG, `embedding_catalog.get_spec`, UnknownEmbeddingModel, `llm_catalog.get_spec`.
- `ProviderRegistry` và các phương thức `_load_*`, `get_active_*_spec_id`; ANTHROPIC_OPENAI_BASE_URL; `OpenAILLM`, `ProviderConfig`.
- `app.routers.admin_custom_models` (as r): OCR_PRESETS, CustomModelIn, save_custom_model, thuộc tính module `log_audit` và `_active_ids` (monkeypatch được).
- `app.services.config_service.ConfigService` bị patch (get/set trên dict trong bộ nhớ), nên mọi module phải tra lúc gọi.

### tests/test_admin_settings_preview_api.py

- Dùng `app.main.app`, override `get_db`.
- Patch `app.services.ocr_service.ocr_service.test_connection` và `ocr_image`.
- Các endpoint ở mục 5.1–5.3, không kèm xác thực.

### tests/test_audit_chain.py (cần PostgreSQL)

| Nguồn | Ký hiệu |
|---|---|
| Model | AuditLog (metadata_, seq, prev_hash, trace_id, action, resource_id) |
| audit_chain | record, verify_chain(session, batch_size=), BASELINE_ACTION, GENESIS_HASH |
| trace_context | set_trace_id, reset_trace_id, get_trace_id, CorrelationIdMiddleware |
| audit_service | log_audit(None, emp, action, rtype, rid, decision="ALLOW", reason="r") |
| Migration | 049 |

- Thông điệp chứa các chuỗi "gap", "tail", "invalid", "archived"; trigger ném "append-only".
- 20 lần ghi song song cộng baseline ra 21 mục; correlation id sinh ra ≥ 32 ký tự; sau request `get_trace_id()` là None.

---

## 12. Sai lệch đã biết của nguồn gốc và cách xử lý trong c2

| # | Nguồn gốc | c2 |
|---|---|---|
| 1 | Overview thống kê dùng hàm đếm SQL mà quên import, nên nhánh dự phòng lỗi | Cài đúng việc đếm trang dự phòng |
| 2 | `notification_service.get_global_reviewers` bị gọi nhưng không định nghĩa | Định nghĩa như 9.2 |
| 3 | `build_skill_filter` trả (True, None) với người không có quyền đọc; router coi là danh sách rỗng | Giữ: trả rỗng |
| 4 | `log_audit` mặc định decision "ALLOW" (hoa) trong khi `append_entry` mặc định "allow" và thống kê đếm "deny" | Thống kê so khớp không phân biệt hoa thường; giữ mặc định "ALLOW" của log_audit cho test |
| 5 | Các endpoint test-* của cài đặt không có xác thực | Giữ như vậy để test qua; ghi chú rủi ro: nên siết lại ở bản sau |
| 6 | Resource wiki-index không truyền clearance và page_filter | Nên truyền, vì không ảnh hưởng test |
| 7 | page_source_clause cần chịu được danh tính thiếu employee_id | Bắt buộc đọc khoan dung |
| 8 | `_get_identity` tự tạo phòng ban từ mã chuyển tiếp | Giữ hành vi (chỉ khi tin header chuyển tiếp) |
| 9 | approve: kiểm tra trạng thái trước khi kiểm tra None | Kiểm tra None (404) trước |
| 10 | reject: đưa về draft, kiểm tra "already approved" sau khi đổi trạng thái | Kiểm tra trạng thái approved hoặc rejected trước (400 "Contribution already approved"), rồi mới đưa về draft |
| 11 | submit không kiểm tra chủ đóng góp | Nên yêu cầu admin hoặc chủ (403 "Access denied") |
