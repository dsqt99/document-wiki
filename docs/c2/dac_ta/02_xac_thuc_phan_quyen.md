# 02. Xác thực, SSO, OAuth cho MCP và phân quyền

Phạm vi: đăng nhập email/mật khẩu và JWT phiên; SSO qua Trợ lý ảo AI (vé ký HS256) và qua Keycloak (OIDC); tự tạo tài khoản và ánh xạ vai trò/nhóm; máy chủ OAuth 2.0 cho client MCP; danh tính MCP; 4 vai trò toàn cục và ma trận quyền; cây phòng ban và phạm vi "đơn vị của mình"; nhãn mật; hợp đồng đồng bộ tổ chức (org-sync) và đồng bộ kỹ năng (skill-sync).

Tài liệu này mô tả hành vi. Không chứa code. Các file loại C đã có sẵn trong c2 và **không** viết lại: `app/routers/sso.py`, `app/routers/org_sync.py`, `app/services/security_label.py`, `app/services/sso_roles.py`, `app/routers/admin_custom_models.py`. Phần mô tả các file này để người viết code biết chúng cần gì từ các module còn lại.

Các module cần viết: `app/services/auth_service.py`, `app/routers/auth.py`, `app/routers/oauth.py`, `app/routers/rbac.py`, `app/services/oauth_service.py` (nếu tách), `app/services/mcp_auth_service.py`, `app/services/permissions.py`, `app/services/permission_engine.py`, `app/services/policy_engine.py` (di sản, tối thiểu), `app/mcp/permissions.py`, phần xác thực trong `app/mcp/tools.py`.

---

## 1. Gắn router và middleware (app/main.py)

| Router | Tiền tố | Ghi chú |
|---|---|---|
| `oauth.wellknown_router` | gốc (không tiền tố) | các tài liệu `/.well-known/...` |
| `oauth.router` | `/oauth` | đăng ký client, authorize, token |
| `auth.router` | `/api` | |
| `sso.router` | `/api` | loại C |
| `rbac.router` | `/api` | phòng ban, nhân viên, token MCP, ma trận quyền |
| `org_sync.router` | `/api` | loại C, đường dẫn `/api/internal/...` |

- `scopes.py` là di sản và **không được gắn**: nó tham chiếu các model đã bị xóa (ScopeMembership, ScopeRole, Action). Không viết lại. Trong model chỉ còn enum `ScopeType`.
- CORS: danh sách nguồn lấy từ `settings.cors_origin_list`. Cho phép gửi kèm credentials.
- Khi khởi động: đọc khóa cấu hình `role_permissions_custom` qua ConfigService. Nếu có giá trị, truyền chuỗi JSON đó vào `permissions.load_role_permissions_override`. Lỗi đọc chỉ ghi log, không chặn khởi động.

### Middleware chặn MCP

- Áp dụng cho đường dẫn đúng bằng `/mcp` hoặc bắt đầu bằng `/mcp/`.
- Nếu header `Authorization` không bắt đầu bằng `Bearer ` (có dấu cách), trả về:
  - mã 401;
  - JSON `{error: "unauthorized", error_description: <mô tả ngắn yêu cầu bearer token>}`;
  - header `WWW-Authenticate` có dạng: `Bearer realm="Arkon MCP", resource_metadata="<base>/.well-known/oauth-protected-resource"`.
- `<base>` là URL công khai suy ra từ request (xem mục 6.1).
- Middleware **không** kiểm tra token. Việc kiểm tra nằm ở tầng công cụ MCP (mục 8).

---

## 2. Cấu hình (app/config.py, lớp Settings, biến môi trường cùng tên viết hoa)

| Khóa | Kiểu | Mặc định | Ý nghĩa |
|---|---|---|---|
| `secret_key` | str | chuỗi giữ chỗ | Khóa ký mọi JWT HS256 của wiki (phiên, vé tệp, cookie giao dịch SSO) |
| `default_admin_email` | str | `admin@arkon.local` | Tài khoản quản trị khởi tạo. Luôn được đăng nhập bằng mật khẩu và không bị hạ quyền admin khi đồng bộ |
| `default_admin_password` | str | rỗng | Rỗng thì không tạo admin khởi tạo |
| `mcp_token_pepper` | str | chuỗi giữ chỗ | Khóa HMAC băm token MCP. Đổi khóa thì mọi token cũ mất hiệu lực |
| `cors_origins` | str | `*` | Danh sách phân tách bằng dấu phẩy |
| `portal_base_url` | str | rỗng | URL công khai của cổng. Rỗng thì suy ra từ header request |
| `sso_enabled` | bool | False | Bật OIDC Keycloak |
| `sso_issuer` | str | rỗng | Issuer công khai (URL trình duyệt thấy) |
| `sso_internal_issuer` | str | rỗng | Issuer trong mạng nội bộ, dùng cho các lời gọi từ máy chủ. Rỗng thì dùng `sso_issuer` |
| `sso_client_id` | str | `cahy-wiki` | |
| `sso_client_secret` | str | rỗng | Rỗng thì là client công khai |
| `sso_scopes` | str | `openid email profile` | |
| `sso_provider_name` | str | `Công an tỉnh (SSO)` | Tên hiển thị trên nút đăng nhập |
| `sso_auto_redirect` | bool | False | Vào /login thì chuyển thẳng sang SSO |
| `sso_allow_password_login` | bool | True | Còn cho đăng nhập bằng mật khẩu cục bộ |
| `sso_admin_roles` | str | `admin` | Danh sách realm role phân tách bằng dấu phẩy. Thuộc tính `sso_admin_role_set` trả về tập đã cắt khoảng trắng, bỏ phần tử rỗng |
| `sso_role_global_map` | str | `qt-dl:knowledge_manager,qt-nd:viewer,qt-ai:viewer,qt-ht:viewer` | Ánh xạ realm role sang global_role. Thuộc tính `sso_role_map` trả về kết quả `sso_roles.parse_role_map` của chuỗi này |
| `sso_default_global_role` | str | `viewer` | |
| `sso_sync_roles` | bool | True | Đồng bộ vai trò mỗi lần đăng nhập SSO |
| `sso_sync_departments` | bool | True | Đồng bộ phòng ban theo nhóm Keycloak |
| `sso_group_department_map` | str | rỗng | JSON ánh xạ tên nhóm sang tên phòng ban |
| `sso_trust_email` | bool | False | Cho phép liên kết theo email cả khi IdP báo email chưa xác minh |
| `chatbot_url` | str | rỗng | URL công khai của Trợ lý ảo AI |
| `chatbot_wiki_sso_secret` | str | rỗng | Secret HS256 dùng chung với chatbot, tối thiểu 32 ký tự. Dùng cho vé đăng nhập, org-sync và skill-sync |
| `sso_mcp_clients` | str | `cahy-chatbot` | Danh sách `azp` được gọi MCP bằng access token Keycloak. Thuộc tính `sso_mcp_client_set` trả về tập |
| `mcp_trust_forwarded_identity` | bool | **False** | Có tin các header danh tính do bên gọi tự khai hay không. Test kiểm tra giá trị mặc định này |

Ngoài ra chế độ MCP qua stdio dùng hai biến môi trường `MCP_TOKEN` và `MCP_STDIO_ADMIN`.

---

## 3. Lược đồ dữ liệu liên quan

### 3.1 `employees`

| Cột | Kiểu | Ràng buộc / mặc định |
|---|---|---|
| id | uuid | khóa chính, tự sinh |
| name | varchar(200) | not null |
| email | varchar(200) | unique, not null, có index |
| password_hash | varchar(500) | null (tài khoản SSO không có mật khẩu); bcrypt |
| role | varchar(20) | mặc định `employee`; giá trị `admin` hoặc `employee` (vai trò hệ thống) |
| global_role | varchar(30) | mặc định `viewer`; một trong `viewer`, `contributor`, `knowledge_manager`, `admin` |
| global_role_source | varchar(10) | not null, mặc định `manual`; `sso` hoặc `manual` |
| mcp_token | varchar(500) | unique, null. Di sản, không đọc, không ghi, chỉ xóa về null |
| mcp_token_hash | varchar(64) | null; unique có điều kiện (khi khác null) |
| mcp_token_prefix | varchar(12) | null; 12 ký tự đầu của token để hiển thị |
| mcp_token_rotated_at | timestamptz | null |
| external_id | varchar(255) | null; unique có điều kiện (khi khác null); là `sub` của Keycloak hoặc `chatbot:<id>` |
| auth_provider | varchar(30) | null; `oidc` hoặc `chatbot` |
| clearance_level | varchar(20) | not null, mặc định `INTERNAL` |
| is_active | bool | mặc định true |
| last_connected | timestamptz | null |
| created_at, updated_at | timestamptz | mặc định now; updated_at tự cập nhật |

- Quan hệ `employee_departments` (danh sách các dòng liên kết). Xóa nhân viên thì xóa luôn các dòng này.
- Quan hệ `departments` đi qua bảng liên kết, chỉ để đọc.
- Thuộc tính `department_ids` trả về danh sách department_id lấy từ `employee_departments`.

### 3.2 `departments`

| Cột | Kiểu | Ràng buộc |
|---|---|---|
| id | uuid | khóa chính |
| name | varchar(200) | unique, not null |
| description | text | null |
| code | varchar(64) | null; mã đơn vị (tên nhóm Keycloak) |
| external_id | varchar(64) | null; id nhóm Keycloak. Khác null nghĩa là phòng ban "được quản lý" (managed): chỉ sửa ở chatbot |
| parent_id | uuid | FK `departments.id`, ON DELETE SET NULL, có index |
| is_active | bool | not null, mặc định true |
| created_at, updated_at | timestamptz | |

### 3.3 `employee_departments` (nhiều-nhiều)

| Cột | Kiểu | Ràng buộc |
|---|---|---|
| employee_id | uuid | PK, FK employees, ON DELETE CASCADE |
| department_id | uuid | PK, FK departments, ON DELETE CASCADE; có index riêng |
| created_at | timestamptz | not null, mặc định now |

- Mọi phòng ban của một người có vai trò ngang nhau; không có khái niệm "phòng ban chính".
- Quyền phạm vi `own_dept` được hiểu là hợp của tất cả phòng ban người đó thuộc về.
- Người không thuộc phòng ban nào chỉ thấy tài nguyên toàn cục.

### 3.4 `source_departments`

Bảng liên kết (source_id, department_id). Một tài liệu không có dòng nào ở bảng này được coi là **toàn cục**.

### 3.5 `oauth_clients`

| Cột | Kiểu | Ràng buộc |
|---|---|---|
| id | uuid | PK |
| client_id | varchar(64) | unique, có index |
| name | varchar(200) | |
| redirect_uris | mảng text | |
| created_at | timestamptz | mặc định now |

### 3.6 `oauth_auth_codes`

| Cột | Kiểu | Ràng buộc |
|---|---|---|
| id | uuid | PK |
| code | varchar(64) | unique, có index |
| client_id | varchar(64) | FK `oauth_clients.client_id`, ON DELETE CASCADE |
| employee_id | uuid | FK employees, ON DELETE CASCADE |
| redirect_uri | varchar(2000) | |
| code_challenge | varchar(128) | |
| code_challenge_method | varchar(10) | mặc định `S256` |
| scope | varchar(500) | null |
| expires_at | timestamptz | |
| used | bool | mặc định false |

### 3.7 `app_config`

Dùng các khóa `role_permissions_custom` (JSON ma trận quyền tùy chỉnh) và `sso_role_global_map` (JSON ánh xạ vai trò do chatbot đẩy sang). Model là `AppConfig(key, value)`, khóa chính là `key`.

---

## 4. auth_service: JWT, mật khẩu, bearer

### 4.1 Hằng số

| Tên | Giá trị |
|---|---|
| `JWT_ALGORITHM` | `HS256` |
| `JWT_EXPIRE_HOURS` | `24` (sso.py import) |

### 4.2 Các hàm công khai

**`hash_password(password: str) -> str`**
- Băm bcrypt với salt mới. Trả về chuỗi.

**`verify_password(password: str, password_hash: str) -> bool`**
- Kiểm tra bcrypt.

**`create_access_token(employee_id: str, role: str, name: str) -> str`**
- Tạo JWT HS256 ký bằng `settings.secret_key`.
- Claims: `sub` = employee_id, `role`, `name`, `exp` = bây giờ + 24 giờ, `iat` = bây giờ.
- **Không** có `aud`.

**`decode_access_token(token: str) -> Optional[dict]`**
- Giải mã HS256 với secret_key và **không khai báo audience**.
- Trả về None khi chữ ký sai, hết hạn hoặc định dạng hỏng.
- Vì không khai báo audience, token có claim `aud` (ví dụ vé tệp) sẽ bị thư viện JWT từ chối, nên trả về None. Nhờ vậy vé tệp không bao giờ dùng được như phiên đăng nhập.

**`create_source_file_token(employee_id: str, source_id: str) -> str`**
- JWT HS256 với claims: `sub` = employee_id, `src` = source_id, `aud` = `arkon-source-file`, `exp` = bây giờ + 15 phút, `iat`.
- Dùng làm `?token=` ngắn hạn cho URL mở tệp gốc của đúng một tài liệu.

**`decode_source_file_token(token: str, source_id: str) -> Optional[str]`**
- Giải mã với audience `arkon-source-file`.
- Trả về `sub` chỉ khi `src` bằng đúng `source_id` (so chuỗi) và `sub` không rỗng.
- Mọi trường hợp khác, kể cả lỗi giải mã, trả về None.

**`authenticate_employee(db, email: str, password: str) -> Optional[Employee]`**
- Tìm nhân viên có email khớp chính xác và `is_active` true, nạp sẵn phòng ban.
- Trả về None nếu không tìm thấy, không có password_hash, hoặc sai mật khẩu.

**`is_keycloak_token(token: str) -> bool`**
- Đọc header JWT mà không kiểm chữ ký.
- Trả về True nếu `alg` thuộc `SIGNING_ALGORITHMS` của `app.routers.sso`: RS256, RS384, RS512, PS256, ES256, ES384.
- Chuỗi không phải JWT (ví dụ `not-a-jwt`, `abc`, `a.b.c`) trả về False và không ném lỗi.
- Token HS256 của wiki trả về False.
- Phải import sso **bên trong hàm**, vì sso.py import auth_service ở cấp module (tránh import vòng).

**`_load_employee(db, employee_id: UUID) -> Optional[Employee]`** (test monkeypatch)
- Nạp nhân viên theo id, nạp sẵn `employee_departments` và phòng ban của từng dòng.
- Dùng chế độ ghi đè object đã có trong session (populate existing), để thấy ngay vai trò và phòng ban vừa đồng bộ.

**`employee_from_bearer(db, token: str) -> Employee`** (async)

Các bước:
1. Nếu `decode_access_token(token)` thành công: chuyển `sub` sang UUID. Nếu không hợp lệ thì coi như không tìm thấy. Nếu hợp lệ thì gọi `_load_employee`. Phải gọi qua tên module để monkeypatch có hiệu lực.
2. Ngược lại, nếu `is_keycloak_token(token)`:
   - Lấy `employee_from_access_token` từ module `app.routers.sso` **tại thời điểm gọi** (tra thuộc tính module, không giữ tham chiếu từ lúc import), rồi gọi nó với (db, token).
   - Nếu kết quả là chuỗi mã lỗi: gọi `db.rollback()` đúng một lần, rồi ném 401 với detail `Keycloak token rejected (<mã>)`.
   - Nếu kết quả là nhân viên: gọi `db.commit()` đúng một lần (lưu tài khoản, vai trò, đơn vị vừa đồng bộ), rồi nạp lại bằng `_load_employee(db, <id của kết quả>)`.
3. Ngược lại: ném 401 `Invalid or expired token`. Chuỗi rác không bao giờ được chuyển sang bước kiểm Keycloak.
4. Nếu không có nhân viên hoặc `is_active` false: ném 401 `Account not found or deactivated`.

### 4.3 Dependency FastAPI

**`get_current_user`**
- Dùng HTTPBearer với `auto_error=False`.
- Không có credentials: 401 `Not authenticated`.
- Có credentials: gọi `employee_from_bearer`. Nếu `global_role` rỗng thì gán `viewer` trên object (không ghi DB).

**`require_admin`**
- Phụ thuộc get_current_user.
- `role` khác `admin`: 403 `Admin access required`.

**`require_permission(permission: str)`**
- Trả về một đối tượng `Depends(...)`, nên được dùng trực tiếp làm giá trị mặc định của tham số (admin_custom_models.py dùng theo cách này).
- Quy tắc:
  1. `role == "admin"`: luôn cho qua.
  2. Lấy tập quyền hiệu lực bằng `permission_engine._get_user_permissions(user)`.
  3. Khớp chính xác: cho qua.
  4. Quyền dạng 2 phần `resource:action`: cho qua nếu người dùng có `resource:action:own_dept` hoặc `resource:action:all`.
  5. Quyền 3 phần có phạm vi `own_dept`: cũng cho qua nếu có biến thể `:all`.
  6. Còn lại: 403 `Permission required: <permission>`.
- Trả về đối tượng nhân viên.

---

## 5. Router auth (tiền tố /api)

### POST /api/auth/login
- Công khai.
- Body: `{email: string, password: string}`.

| Tình huống | Kết quả |
|---|---|
| Sai thông tin (authenticate_employee trả None) | 401 `Invalid email or password` |
| `sso_enabled` true, `sso_allow_password_login` false, và email (so không phân biệt hoa thường) khác `default_admin_email` | 403 `Password login is disabled, use SSO` |
| Thành công | 200 |

- Phản hồi thành công: `{access_token, token_type: "bearer", user: {...}}`, trong đó user gồm:
  - `id` (string)
  - `name`, `email`, `role`
  - `department_ids: string[]`, `department_names: string[]`
  - `permissions: string[]` (danh sách quyền hiệu lực đã sắp xếp)
  - `workspace_memberships: []` (luôn rỗng, giữ cho tương thích)
- Token tạo bằng `create_access_token(id, role, name)`.
- Lưu ý: điều kiện chặn mật khẩu chỉ xét `sso_enabled`. Chế độ chatbot không tự chặn API này.

### GET /api/auth/me
- Cần đăng nhập.
- Phản hồi: `{id, name, email, role, department_ids, department_names, is_active, has_mcp_token, auth_provider, permissions, workspace_memberships: []}`.
- `has_mcp_token` = mcp_token_hash có giá trị.

### POST /api/auth/change-password
- Cần đăng nhập.
- Body: `{current_password, new_password}`.

| Tình huống | Kết quả |
|---|---|
| Tài khoản không có password_hash | 400 `No password set. Contact admin.` |
| Mật khẩu hiện tại sai | 401 `Current password is incorrect` |
| Mật khẩu mới dưới 6 ký tự | 400 `New password must be at least 6 characters` |
| Thành công | ghi hash mới, trả về `{message: "Password changed successfully"}` |

### GET /api/auth/status
- Công khai. Trả về `{auth_required: true}`.

### Phiên và đăng xuất
- **Không có endpoint refresh.** Phiên là JWT không trạng thái, sống 24 giờ; hết hạn thì đăng nhập lại.
- Đăng xuất cục bộ: frontend xóa token.
- Đăng xuất SSO: qua `/api/auth/sso/logout` (mục 6.5).

---

## 6. SSO (app/routers/sso.py, loại C) — hợp đồng hành vi

### 6.1 Hằng số và điều kiện bật

| Hằng số | Giá trị |
|---|---|
| Nhà cung cấp OIDC | `oidc` |
| Cookie giao dịch | `arkon_sso_tx` |
| Cookie id_token | `arkon_sso_idt` |
| Path của cookie | `/api/auth/sso` |
| Thời sống giao dịch | 600 giây; audience `arkon-sso-tx` |
| Bộ nhớ đệm discovery | 3600 giây |
| Kích thước cookie tối đa | 3800 byte |
| Đường dẫn trả vé phía chatbot | `/api/v1/arkon/sso/return` |
| Đường dẫn đăng xuất phía chatbot | `/api/v1/arkon/sso/logout` |
| Issuer vé | `cahy-chatbot` (`CHATBOT_TICKET_ISSUER`) |
| Audience vé | `cahy-wiki` |
| Tiền tố sub cục bộ | `chatbot:` (`CHATBOT_SUB_PREFIX`) |
| Nhà cung cấp chatbot | `chatbot` |
| `SIGNING_ALGORITHMS` | RS256, RS384, RS512, PS256, ES256, ES384 |

Điều kiện bật:
- OIDC bật khi `sso_enabled` true và cả `sso_issuer`, `sso_client_id` đều có giá trị.
- Chế độ chatbot bật khi `chatbot_url` có giá trị và `chatbot_wiki_sso_secret` dài ít nhất 32 ký tự.

URL công khai (base):
- Dùng `portal_base_url` nếu có.
- Nếu không, ghép từ `x-forwarded-proto` và `x-forwarded-host` (hoặc `host`). Mỗi header chỉ lấy giá trị đầu nếu có nhiều giá trị.

Cookie:
- Luôn httponly, SameSite lax.
- Có cờ Secure khi base bắt đầu bằng https.

Tham số `next` an toàn:
- Chỉ nhận đường dẫn bắt đầu bằng `/`.
- Từ chối nếu bắt đầu bằng `//`, chứa dấu gạch chéo ngược, hoặc trỏ về chính trang `/login` (`/login`, `/login/`, `/login?...`). Bị từ chối thì dùng `/`.
- Cắt tối đa 500 ký tự.

Chuyển hướng:
- Lỗi: về `<base>/login?error=<mã>`, kèm `&next=` khi có, đồng thời xóa cookie giao dịch.
- Thành công: phát JWT wiki bằng `create_access_token`, rồi chuyển về `<base>/login/sso#token=<jwt>&next=<next>`. Token nằm ở fragment nên không đi vào log máy chủ.

### 6.2 GET /api/auth/sso/config (công khai)
- Trả về:
  - `enabled` (OIDC bật)
  - `chatbot_login` (chế độ chatbot bật)
  - `provider_name`
  - `auto_redirect` = (enabled hoặc chatbot_login) và `sso_auto_redirect`
  - `allow_password_login` = không (enabled hoặc chatbot_login), hoặc `sso_allow_password_login`

### 6.3 Vé SSO từ chatbot (khuyến nghị dùng; wiki không có trang đăng nhập riêng)

**GET /api/auth/sso/chatbot/login?next=&prompt=**
1. Chế độ chatbot tắt: chuyển về lỗi `sso_disabled`.
2. Sinh `state` ngẫu nhiên (24 byte, dạng urlsafe).
3. Đặt cookie giao dịch. Cookie là JWT HS256 ký bằng secret_key, audience `arkon-sso-tx`, claims: `st` (state), `nx` (next), `src` = `chatbot`, `exp` (+600 giây).
4. Chuyển hướng tới `<chatbot_url>/api/v1/arkon/sso/return?state=<state>`, thêm `&prompt=none` nếu được yêu cầu. `prompt=none` dùng khi nhúng iframe: đăng nhập im lặng, không hiện màn hình.

**Phía chatbot: /api/v1/arkon/sso/return?state&prompt&retry**
- `state` phải dài 16–128 ký tự, chỉ gồm chữ, số, `_` và `-`. Sai thì trả lỗi `invalid_request`.
- Người dùng chưa đăng nhập chatbot:
  - nếu `prompt=none` hoặc đã thử lại (`retry`): trả `login_required`;
  - ngược lại: chuyển tới trang đăng nhập chatbot `/auth?redirect=...` kèm `retry=1`.
- Đã đăng nhập: ký vé HS256 bằng secret chung.
- Claims của vé:
  - `iss` = `cahy-chatbot`, `aud` = `cahy-wiki`
  - `sub` = id người dùng chatbot
  - `kc_sub` = id Keycloak, nếu có
  - `email`, `name`
  - `role` (`admin` hoặc khác)
  - `groups` (tên nhóm và mã đơn vị)
  - `unit_ids` (id nhóm Keycloak, hoặc null khi không biết)
  - `st` (state)
  - `iat`, `exp` = iat + 60 giây, `jti`
  - `roles` (realm role; vắng mặt khi chatbot không biết Keycloak)
- Chuyển hướng về `<wiki>/api/auth/sso/chatbot/callback?ticket=<vé>`, hoặc `?error=<mã>` khi lỗi.
- Đăng xuất phía chatbot bỏ qua request cross-site, rồi chuyển về `<ui>/login?logged_out=1`.

**GET /api/auth/sso/chatbot/callback?ticket=&error=**
1. Có tham số `error`: `login_required` thành `sso_login_required`; `invalid_request` thành `sso_misconfigured`; mọi mã khác thành `sso_denied`.
2. Thiếu cookie giao dịch, `src` khác `chatbot`, hoặc thiếu ticket: lỗi `sso_state`.
3. Kiểm vé: HS256, secret chung, aud `cahy-wiki`, iss `cahy-chatbot`, leeway 10 giây, bắt buộc có `exp`, `iat`, `sub`, `st`. Sai thì lỗi `sso_token`.
4. `st` của vé khác `st` trong cookie: lỗi `sso_state`.
5. Xác định subject:
   - Có `kc_sub`: subject là `kc_sub`. Nếu có tài khoản cũ mang `external_id` = `chatbot:<sub>` và chưa có tài khoản nào giữ `kc_sub`, thì đổi external_id của tài khoản cũ sang `kc_sub` (liên kết lại).
   - Không có `kc_sub`: nếu có tài khoản cùng email (không phân biệt hoa thường) đã có external_id thì dùng external_id đó; ngược lại subject là `chatbot:<sub>`.
6. Cấp tài khoản (mục 6.6) với các tham số:
   - `email_verified` = true
   - `groups` lấy từ claim
   - `unit_ids` là danh sách hoặc null
   - `roles` là danh sách hoặc null
   - `is_admin` = (claim role bằng `admin`)
   - provider = `chatbot`
7. Commit, xóa cookie id_token, chuyển hướng thành công.

### 6.4 OIDC Keycloak trực tiếp

Discovery:
- Đọc `<internal_issuer>/.well-known/openid-configuration`, lưu đệm 1 giờ.
- Các URL trình duyệt đi tới (authorization, end_session) được viết lại về issuer công khai.
- Các URL máy chủ gọi (token, jwks) được viết lại về issuer nội bộ.
- Issuer được chấp nhận: công khai, nội bộ, hoặc issuer trong discovery.

Kiểm JWT:
- Dùng JWKS, leeway 30 giây, bắt buộc có `exp`, `iat`, `sub`.
- Nếu `aud` là mảng có hơn một phần tử thì `azp` phải bằng audience mong đợi.
- Nonce so sánh theo thời gian hằng.

Lấy vai trò và nhóm:
- Realm role lấy từ `realm_access.roles`, nếu không có thì từ claim `roles`.
- Nhóm lấy đoạn cuối của đường dẫn nhóm.
- Nếu có `sso_group_department_map` thì đổi tên nhóm qua bảng đó.

**GET /api/auth/sso/login?next=&prompt=**
- OIDC tắt: lỗi `sso_disabled`. Discovery lỗi: lỗi `sso_unavailable`.
- Sinh `state`, `nonce` và PKCE verifier (32 byte ngẫu nhiên, base64url). Challenge là SHA-256 của verifier ở dạng base64url (phương thức S256).
- Cookie giao dịch chứa: `st`, `nn` (nonce), `cv` (verifier), `nx`, `exp`.
- Chuyển tới authorization endpoint với các tham số:
  - `response_type=code`, `client_id`
  - `redirect_uri=<base>/api/auth/sso/callback`
  - `scope` = `sso_scopes`, `state`, `nonce`
  - `code_challenge`, `code_challenge_method=S256`
  - `prompt=none` nếu được yêu cầu

**GET /api/auth/sso/callback?code=&state=&error=**
1. Có `error`: `login_required`, `interaction_required` hoặc `consent_required` thành `sso_login_required`; mọi mã khác thành `sso_denied`.
2. `state` không khớp cookie: lỗi `sso_state`.
3. Đổi code tại token endpoint. Gửi form gồm: `grant_type=authorization_code`, `code`, `redirect_uri`, `code_verifier`, `client_id`, và `client_secret` nếu có.
4. Mã khác 200 hoặc không có id_token: lỗi `sso_token`.
5. Kiểm id_token với aud = client_id và nonce. Nếu id_token không chứa vai trò thì lấy vai trò từ access_token (sau khi kiểm access_token).
6. Cấp tài khoản (provider `oidc`), rồi commit.
7. Nếu id_token không quá 3800 byte thì lưu vào cookie id_token (max_age 24 giờ) để dùng làm `id_token_hint` khi đăng xuất.

### 6.5 GET /api/auth/sso/logout
- Chọn đích như sau:
  1. Chế độ chatbot bật và không có cookie id_token: đích là `<chatbot>/api/v1/arkon/sso/logout`.
  2. Ngược lại, nếu OIDC có end_session endpoint: đích là end_session, kèm `client_id`, `post_logout_redirect_uri=<base>/login?logged_out=1` và `id_token_hint`.
  3. Còn lại: `<base>/login?logged_out=1`.
- Luôn xóa cả hai cookie.

### 6.6 Cấp tài khoản và đồng bộ khi đăng nhập SSO

**Tìm tài khoản:**
1. Tìm theo `external_id` = subject.
2. Không thấy thì tìm theo email (chữ thường). Khi tìm được qua email:
   - Tài khoản có external_id khác subject và không bắt đầu bằng `chatbot:`: mã lỗi `sso_email_conflict`.
   - Email chưa xác minh và `sso_trust_email` tắt: mã lỗi `sso_email_unverified`.
   - Ngược lại: liên kết, tức gán `external_id` và `auth_provider`.

**Tạo tài khoản mới:**
- `name`: lấy `name`; nếu không có thì ghép `given_name` và `family_name`; nếu vẫn không có thì `preferred_username`. Tối đa 200 ký tự.
- `email`: email; nếu không có thì `<username>@sso.invalid`.
- Không có mật khẩu.
- `role`: `admin` nếu is_admin, ngược lại `employee`.
- `global_role`: `admin` nếu is_admin; ngược lại vai trò suy ra từ ánh xạ; nếu không suy ra được thì `sso_default_global_role`.
- `global_role_source` = `sso`, `is_active` = true.

**Tài khoản bị khóa:** mã lỗi `sso_inactive`.

**Đồng bộ vai trò** (chỉ với tài khoản đã tồn tại, khi `sso_sync_roles` bật):
- Gọi `sso_roles.sync_employee_roles`.
- Nếu có thay đổi, ghi audit `SSO_GLOBAL_ROLE_SYNC`. Metadata gồm trạng thái trước và sau (`global_role`, `source`) và danh sách realm role đã sắp xếp.

**Đồng bộ phòng ban** (khi `sso_sync_departments` bật):
- Tên nhóm (sau khi ánh xạ) được khớp với tên các phòng ban đang hoạt động.
- Khi không có `unit_ids`: khớp thêm theo `code` (viết hoa). Chỉ thêm thành viên, không gỡ.
- Khi có `unit_ids`:
  - Khớp theo tên chỉ áp dụng cho phòng ban không đồng bộ (external_id null), và chỉ thêm.
  - Với phòng ban đồng bộ, thành viên được đặt đúng bằng tập phòng ban đang hoạt động có external_id thuộc `unit_ids`. Liên kết tới phòng ban đồng bộ không còn trong tập bị gỡ.

**`employee_from_access_token(db, token) -> Employee | str`** (auth_service gọi; test monkeypatch)
- Dùng để chấp nhận access token Keycloak của người dùng do chatbot chuyển tiếp.
- Trả về chuỗi mã lỗi trong các trường hợp:
  - OIDC tắt hoặc `sso_mcp_client_set` rỗng: `sso_disabled`.
  - Token hết hạn: `sso_token_expired`.
  - Token sai: `sso_token_invalid`.
  - Claim `typ` khác `Bearer` (so không phân biệt hoa thường): `sso_token_invalid`.
  - `azp` không thuộc `sso_mcp_client_set`: `sso_client_not_allowed`.
  - Lỗi khi cấp tài khoản: các mã ở trên (`sso_email_conflict`, `sso_email_unverified`, `sso_inactive`).
- Thành công thì cấp hoặc đồng bộ tài khoản như mục 6.6 và trả về nhân viên. Hàm **không** commit; nơi gọi commit.

---

## 7. Ánh xạ vai trò (app/services/sso_roles.py, loại C)

| Ký hiệu | Giá trị / chữ ký | Hành vi |
|---|---|---|
| `GLOBAL_ROLE_RANK` | viewer 0, contributor 1, knowledge_manager 2 | `admin` không nằm trong thang |
| `ROLE_MAP_CONFIG_KEY` | `sso_role_global_map` | |
| `SOURCE_SSO` / `SOURCE_MANUAL` | `sso` / `manual` | |
| `parse_role_map(raw) -> dict[str,str]` | | Nhận JSON object hoặc chuỗi cặp `role:global,role:global`. Rỗng hoặc JSON hỏng cho ra rỗng. Bỏ các cặp có đích không thuộc thang (kể cả admin) |
| `derived_global_role(roles, role_map) -> Optional[str]` | | Vai trò được ánh xạ có hạng cao nhất; None nếu không có |
| `reconcile_global_role(current, source, roles, role_map, default) -> (role, source)` | | Xem bảng dưới |
| `sync_employee_roles(emp, roles, is_admin, role_map, default, default_admin_email) -> (before, after)` | | Xem bảng dưới |
| `load_role_map(db)` (async) | | Lấy dòng AppConfig `sso_role_global_map` nếu có (kể cả khi giá trị là `{}`), ngược lại dùng `settings.sso_role_map` |

Quy tắc của `reconcile_global_role`:

| Điều kiện | Kết quả |
|---|---|
| current rỗng | coi như `default` |
| current không thuộc thang (admin, giá trị lạ) | giữ nguyên; source giữ nguyên, rỗng thì là `manual` |
| source `manual` | chỉ **nâng**: nếu vai trò suy ra cao hơn current thì lấy vai trò suy ra và source thành `sso`; ngược lại giữ nguyên, source `manual` |
| source `sso` | lấy vai trò suy ra, nếu không có thì `default`; source `sso`. Có thể hạ cấp |

Quy tắc của `sync_employee_roles`:
- is_admin: role và global_role đều là `admin`, source `sso`.
- Không phải admin nhưng tài khoản đang là admin và email khác `default_admin_email`: role thành `employee`; nếu global_role đang là `admin` thì đổi về `default`, source `sso`.
- Sau đó, nếu `roles` khác None và tài khoản không phải admin: áp dụng `reconcile_global_role`.
- `roles` bằng None nghĩa là không biết, nên global_role giữ nguyên.

---

## 8. MCP: token, danh tính, phạm vi

### 8.1 app/services/mcp_auth_service.py

**`hash_token(token: str) -> str`**
- HMAC-SHA256 với khóa `mcp_token_pepper`, trả về dạng hex (64 ký tự).

**`ResolvedIdentity`** (dataclass, test tạo trực tiếp bằng keyword)

| Trường | Kiểu | Mặc định |
|---|---|---|
| employee_id | UUID | bắt buộc |
| employee_name | str | bắt buộc |
| department_ids | list | [] |
| department_names | list | [] |
| allowed_knowledge_types | Optional[list[str]] | None |
| allowed_source_ids | Optional[list] | None |
| is_admin | bool | False |
| permissions | list[str] | [] |
| delegated_role | Optional[str] | None |
| clearance_level | str | `INTERNAL` |

- Thuộc tính `allowed_labels`: bằng `security_label.allowed_labels(clearance_level)`. Ví dụ với INTERNAL là `["PUBLIC", "INTERNAL"]`.
- `has_permission(p)`: is_admin, hoặc p nằm trong permissions.
- `has_any_permission(*p)`: is_admin, hoặc ít nhất một p nằm trong permissions.

**`MCPAuthService(db)`**

`verify_token(token) -> Optional[ResolvedIdentity]`
- Tìm nhân viên theo `hash_token(token)`, chỉ nhận tài khoản đang hoạt động.
- Cập nhật `last_connected` nếu lần cập nhật trước đã quá 60 giây. Đặt thuộc tính `bumped_last_connected` của service cho biết có cập nhật hay không.
- Tính phạm vi bằng `_resolve_scope`, đặt `clearance_level` theo nhân viên.

`verify_sso_token(token) -> (Optional[ResolvedIdentity], Optional[str])`
- Gọi `sso.employee_from_access_token`. Nhận chuỗi thì trả về (None, mã lỗi). Nhận nhân viên thì commit và trả về (danh tính, None).

`_resolve_scope(emp)`: điền permissions bằng danh sách quyền hiệu lực, rồi:
- Nhân viên admin: `is_admin` true, không giới hạn.
- Có `doc:read:all`: không giới hạn (allowed_source_ids None).
- Có `doc:read:own_dept`: `allowed_source_ids` = các tài liệu toàn cục (không có dòng source_departments) hợp với các tài liệu gắn với bất kỳ phòng ban nào của người đó.
- Không có quyền đọc nào: `allowed_source_ids` = [] (không thấy gì).

`generate_token(employee_id) -> str`
- Token có dạng `ark_` + 32 byte ngẫu nhiên urlsafe.
- Lưu hash, prefix (12 ký tự đầu) và rotated_at = bây giờ; xóa cột mcp_token cũ về null.
- Trả về token thô đúng một lần. Mỗi lần gọi là xoay token, token trước mất hiệu lực.

`revoke_token(employee_id) -> bool`
- Xóa mcp_token, hash, prefix và rotated_at. Trả về True nếu có dòng thay đổi.

**`apply_scope_filter(query, identity)`** (test dùng với `select(Source.id)`)
- Luôn thêm điều kiện nhãn `security_label.source_label_clause(identity.clearance_level)`. Điều kiện này có dạng `sources.security_label IN (...)` và được áp **kể cả khi có giới hạn phạm vi**.
- Luôn thêm `permission_engine.personal_visible_clause(identity.employee_id)`.
- Nếu `allowed_source_ids` hoặc `allowed_knowledge_types` khác None: thêm điều kiện OR giữa "id tài liệu thuộc allowed_source_ids" và "slug loại tri thức thuộc allowed_knowledge_types". Chỉ những vế có giá trị mới tham gia.
- Admin: bỏ giới hạn phạm vi, nhưng vẫn áp nhãn và quy tắc tài liệu cá nhân.

**`page_source_clause(identity)`**
- Ẩn trang wiki nếu có bất kỳ tài liệu nguồn nào trong `source_ids` của trang mà người gọi không đọc được, xét theo nhãn, tài liệu cá nhân và phạm vi.
- Admin chỉ xét nhãn và tài liệu cá nhân.

### 8.2 Xác thực trong app/mcp/tools.py

Hai ký hiệu bắt buộc: `register_tools(mcp)` (đặc tả công cụ ở tài liệu MCP) và `forwarded_role`.

**`forwarded_role(headers: Mapping[str,str], trust: bool) -> str`**
- `trust` false: trả về chuỗi rỗng, kể cả khi có header `x-user-role: admin`.
- `trust` true: trả về giá trị header `x-user-role` đã cắt khoảng trắng và chuyển chữ thường. Ví dụ `" Admin "` thành `admin`. Không có header thì trả về chuỗi rỗng.
- Nơi gọi truyền `settings.mcp_trust_forwarded_identity`.

**Phân giải danh tính cho mỗi lời gọi công cụ:**
1. Lấy bearer token từ header.
2. Token **không** bắt đầu bằng `ark_` và có đúng 2 dấu chấm: coi là access token Keycloak, xác thực bằng `verify_sso_token`. Thông báo lỗi trả cho client theo mã:

| Mã | Thông báo |
|---|---|
| sso_disabled | `SSO tokens are not accepted by this server. Use an Arkon MCP token (ark_…).` |
| sso_token_expired | `SSO token expired. Sign in again.` |
| sso_token_invalid | `Invalid SSO token.` |
| sso_client_not_allowed | `This SSO client may not call Arkon MCP (see SSO_MCP_CLIENTS).` |
| sso_email_conflict | `The SSO account's email belongs to another linked Arkon account.` |
| sso_email_unverified | `The SSO account's email is not verified, so it cannot be linked to the existing Arkon account.` |
| sso_inactive | `Arkon account is inactive. Contact your administrator.` |

3. Ngược lại: `verify_token`. Sai thì trả `Invalid or inactive MCP token. Contact your administrator.`
4. Danh tính được ủy quyền: chỉ xét khi `forwarded_role(...)` trả về chuỗi khác rỗng.
   - Gán `delegated_role`. Chuẩn hóa `x-user-clearance` thành `clearance_level`.
   - Vai trò `admin`: is_admin true.
   - Vai trò khác: tìm phòng ban trong các phòng ban đang hoạt động, theo thứ tự:
     1. `x-department-id` khớp external_id;
     2. `x-department-code` (viết hoa) khớp code;
     3. `x-department-name` khớp đúng tên.
   - Vẫn chưa thấy: khớp gần đúng theo tên, chỉ trong các phòng ban không đồng bộ.
   - Vẫn chưa thấy, có code và chưa phòng ban nào mang tên đó: tự tạo phòng ban.
   - Sau đó tính lại `allowed_source_ids` theo phòng ban tìm được.

### 8.3 app/mcp/permissions.py

- `ToolRequirement(predicate, label)`: lớp nhỏ có phương thức `allows(identity) -> bool`.
- Các mức yêu cầu:
  - `ANY_AUTHENTICATED`: mọi danh tính.
  - `CAN_CONTRIBUTE_WIKI`: admin, hoặc có `wiki:write:own_dept`, hoặc có `wiki:write:all`.
  - `CAN_REVIEW_WIKI`: admin, hoặc có `wiki:write:all`.
  - `CAN_CREATE_WIKI_DIRECT`: giống CAN_REVIEW_WIKI.
- `kb_tool(mcp, requires=ANY_AUTHENTICATED, **kw)`: decorator đăng ký công cụ với mcp và gắn yêu cầu vào thuộc tính `__arkon_requires__` của hàm.
- `requirement_for(fn)`: đọc thuộc tính đó; không có thì là ANY_AUTHENTICATED.
- Lọc danh sách công cụ theo yêu cầu chỉ để hiển thị. Mỗi công cụ vẫn phải tự kiểm quyền khi chạy.

---

## 9. Máy chủ OAuth 2.0 cho client MCP (app/routers/oauth.py)

Base là URL công khai suy ra như mục 6.1.

### GET /.well-known/oauth-authorization-server
Trả về:
- `issuer`: base
- `authorization_endpoint`: `<base>/oauth/authorize`
- `token_endpoint`: `<base>/oauth/token`
- `registration_endpoint`: `<base>/oauth/register`
- `response_types_supported`: `["code"]`
- `grant_types_supported`: `["authorization_code"]`
- `code_challenge_methods_supported`: `["S256"]`
- `token_endpoint_auth_methods_supported`: `["none"]`

### GET /.well-known/oauth-protected-resource
Cũng phục vụ cùng nội dung tại `/.well-known/oauth-protected-resource/mcp`. Trả về:
- `resource`: `<base>/mcp`
- `authorization_servers`: `[base]`
- `bearer_methods_supported`: `["header"]`
- `scopes_supported`: `[]`
- `resource_name`: `Arkon MCP`
- `resource_documentation`: `<base>/docs`

### POST /oauth/register (đăng ký client động)
- Body JSON: `client_name` (mặc định `Claude Desktop`), `redirect_uris: string[]`.
- `redirect_uris` rỗng: 400 `redirect_uris required`.
- Thành công trả 201 với:
  - `client_id`: `client_` + 16 byte ngẫu nhiên urlsafe
  - `client_name`, `redirect_uris`
  - `grant_types: ["authorization_code"]`, `response_types: ["code"]`
  - `token_endpoint_auth_method: "none"`
  - `registration_client_uri`
- Không có endpoint GET cho registration_client_uri.

### GET /oauth/authorize
- Query: `client_id`, `redirect_uri`, `response_type`, `code_challenge`, `code_challenge_method` (mặc định S256), `state`.
- Các lỗi trả 400:

| Tình huống | Mã lỗi |
|---|---|
| response_type khác `code` | `unsupported_response_type` |
| method khác `S256` | `unsupported_code_challenge_method` |
| client không tồn tại | `invalid_client` |
| redirect_uri không khớp chính xác phần tử nào trong danh sách đã đăng ký | `invalid_redirect_uri` |

- Hợp lệ thì trả về trang HTML đăng nhập (ô email, mật khẩu) kèm các trường ẩn mang tham số trên.

### POST /oauth/authorize (form)
- Các trường form: `client_id`, `redirect_uri`, `code_challenge`, `code_challenge_method`, `state`, `email`, `password`.
- Client sai: 400 `invalid_client`.
- Sai thông tin đăng nhập: hiển thị lại form với thông báo lỗi, mã 401.
- **Không** kiểm cờ tắt đăng nhập mật khẩu (giữ đúng hành vi gốc).
- Thành công:
  1. Tạo mã ủy quyền: 32 byte ngẫu nhiên urlsafe, hạn 10 phút. Lưu kèm challenge, method và redirect_uri.
  2. Chuyển hướng 302 tới `redirect_uri?code=<code>&state=<state>`.

### POST /oauth/token (form)
- Các trường: `grant_type`, `code`, `redirect_uri`, `client_id`, `code_verifier`.
- grant_type khác `authorization_code`: 400 `unsupported_grant_type`.
- Mã hợp lệ khi thỏa tất cả các điều kiện sau. Sai bất kỳ điều kiện nào: 400 `invalid_grant`.
  - chưa dùng;
  - thuộc đúng client;
  - chưa hết hạn;
  - redirect_uri trùng với lúc tạo mã;
  - base64url (không padding) của SHA-256(code_verifier) bằng code_challenge.
- Thành công:
  1. Đánh dấu mã đã dùng.
  2. Gọi `MCPAuthService.generate_token(employee_id)`. Thao tác này xoay token `ark_`, nên token cũ của người đó mất hiệu lực.
  3. Trả về `{access_token: <ark_...>, token_type: "bearer"}`.

---

## 10. Vai trò và ma trận quyền (app/services/permissions.py)

### 10.1 Danh sách quyền (`ALL_PERMISSIONS`)
Quyền có định dạng `resource:action[:scope]`, với scope là `own_dept` hoặc `all`.

| Nhóm (`PERMISSION_GROUPS`) | Quyền |
|---|---|
| Documents | doc:read, doc:create, doc:edit, doc:delete, mỗi quyền có biến thể `:own_dept` và `:all` |
| Wiki | wiki:read, wiki:write, wiki:delete, mỗi quyền có `:own_dept` và `:all` |
| AI Skills | skill:read, skill:create, skill:edit, skill:delete, mỗi quyền có `:own_dept` và `:all`; thêm `skill:contribution:review` |
| Organization | org:departments:read, org:departments:manage, org:employees:read, org:employees:manage, org:roles:read, org:roles:manage, org:settings:read, org:settings:manage, org:audit:read |
| Workspaces | workspace:view:all |

`PERMISSION_LABELS` và `PERMISSION_DESCRIPTIONS` là hai map từ mã quyền sang nhãn và mô tả ngắn bằng tiếng Anh, tự soạn. Mọi phần tử của ALL_PERMISSIONS phải có nhãn.

### 10.2 Vai trò hệ thống (`SYSTEM_ROLES`)

| id | Tên hiển thị |
|---|---|
| viewer | Viewer (Người xem) |
| contributor | Contributor (Người đóng góp) |
| knowledge_manager | Knowledge Manager (Quản trị tri thức) |
| admin | System Admin (Quản trị viên) |

### 10.3 Quyền mặc định (`ROLE_PERMISSIONS_MAP`)

Ký hiệu: ✓ là có quyền; O là chỉ có biến thể own_dept; A là có biến thể all (A bao gồm cả quyền phạm vi own_dept).

| Quyền | viewer | contributor | knowledge_manager | admin |
|---|---|---|---|---|
| doc:read | O | O | A | A |
| doc:create | – | O | A | A |
| doc:edit | – | – | A | A |
| doc:delete | – | – | A | A |
| wiki:read | O | O | A | A |
| wiki:write | – | O | A | A |
| wiki:delete | – | – | A | A |
| skill:read | O | O | A | A |
| skill:create | – | O | A | A |
| skill:edit | – | – | A | A |
| skill:delete | – | – | A | A |
| skill:contribution:review | – | – | ✓ | ✓ |
| org:departments:read | ✓ | ✓ | ✓ | ✓ |
| org:departments:manage | – | – | ✓ | ✓ |
| org:employees:read | ✓ | ✓ | ✓ | ✓ |
| org:employees:manage | – | – | ✓ | ✓ |
| org:roles:read / manage | – | – | – | ✓ |
| org:settings:read / manage | – | – | – | ✓ |
| org:audit:read | – | – | ✓ | ✓ |
| workspace:view:all | – | – | – | ✓ |

Chú thích:
- knowledge_manager giữ biến thể `:all` của mọi quyền doc, wiki và skill. Việc kiểm quyền vẫn chấp nhận yêu cầu own_dept (mục 4.3 và 11).
- admin có toàn bộ ALL_PERMISSIONS và không bao giờ bị sửa.

Các hằng số khác:
- `EMPLOYEE_DEFAULT_PERMISSIONS`: doc:read:own_dept, doc:create:own_dept, wiki:read:own_dept, wiki:write:own_dept, skill:read:own_dept, org:departments:read.
- `ROLE_PRESETS`: map tên vai trò sang danh sách quyền, dùng để đổ sẵn trên UI. Có cùng nội dung với ROLE_PERMISSIONS_MAP.
- `LEGACY_PERMISSION_MAP`: map quyền cũ dạng 2 phần (ví dụ `doc:read`) sang danh sách quyền 3 phần tương ứng.

### 10.4 Ghi đè ma trận
- `load_role_permissions_override(json_str)`:
  - Đọc JSON; hỏng thì bỏ qua.
  - Với từng vai trò khác `admin`: lọc chỉ giữ quyền thuộc ALL_PERMISSIONS, rồi lưu vào bộ nhớ của tiến trình.
- `get_effective_role_permissions() -> dict[str, list[str]]`:
  - Bắt đầu từ ROLE_PERMISSIONS_MAP; vai trò nào có ghi đè thì thay bằng bản ghi đè.
  - admin luôn là toàn bộ quyền.

---

## 11. permission_engine (app/services/permission_engine.py)

| Ký hiệu | Hành vi |
|---|---|
| `parse_permission(p) -> (resource, action, scope|None)` | Tách theo dấu `:` |
| `has_permission(perms, resource, action, scope="any") -> bool` | scope `all` đòi biến thể `:all`. scope `own_dept` hoặc `any` nhận cả biến thể `:own_dept` lẫn `:all` |
| `has_any_permission(perms, *checks)` | Đúng nếu một trong các bộ (resource, action[, scope]) thỏa |
| `get_scope_level(perms, resource, action) -> "all" / "own_dept" / None` | Mức rộng nhất người dùng có |
| `PERSONAL_SCOPE` | `personal` |
| `is_personal(source) -> bool` | `scope_type` của tài liệu bằng `personal` |
| `personal_visible_clause(employee_id)` | Điều kiện SQL: scope_type (null coi là `global`) khác `personal`, **hoặc** scope_id bằng employee_id. employee_id là None thì chỉ còn vế thứ nhất |
| `can_access_document(db, user, source, action) -> bool` (async) | Xem các bước dưới |
| `build_document_filter(user, action) -> (needs_filter: bool, dept_ids: Optional[list])` | admin hoặc có `:all`: (False, None). Có own_dept: (True, danh sách phòng ban). Không có quyền: (True, []) |
| `can_access_skill(db, user, skill, action)` | admin hoặc có `:all`: True. Kỹ năng toàn cục hoặc giao với phòng ban của người dùng: True. Đặc điểm cần giữ: nhánh này **không** kiểm người dùng có quyền own_dept hay không |
| `build_skill_filter(user, action)` | Tương tự build_document_filter, cho resource `skill` |
| `_get_user_permissions(user) -> set[str]` | `role` hoặc `global_role` là `admin`: toàn bộ ALL_PERMISSIONS. Ngược lại: quyền hiệu lực của global_role (mục 10.4); vai trò lạ hoặc rỗng dùng quyền của viewer |
| `get_effective_permissions(user) -> list[str]` | Bản sắp xếp của `_get_user_permissions` |

Các bước của `can_access_document`:
1. admin: True.
2. Tài liệu cá nhân không thuộc người dùng: False.
3. Nhãn tài liệu cao hơn mức tiếp cận của người dùng: False.
4. Có quyền `doc:<action>:all`: True.
5. Không có quyền own_dept: False.
6. Tài liệu không gắn phòng ban nào: True.
7. Còn lại: True khi tập phòng ban của người dùng giao với tập phòng ban của tài liệu.

**Phạm vi "đơn vị của mình" (own_dept):**
- Bằng hợp mọi phòng ban người dùng thuộc về (đa thành viên), cộng với tài nguyên toàn cục.
- Không bao gồm phòng ban con. Cây cha–con (`parent_id`) chỉ dùng để hiển thị.
- Trang wiki kế thừa phạm vi (`scope_type`, `scope_id`) của tài liệu nguồn tạo ra nó. Xem tài liệu wiki: `finalize_legal_source` gọi `wiki_service.resolve_wiki_scopes(session, source)` đúng một lần, rồi dùng phạm vi đó cho mọi `upsert_page` và `regenerate_index`.

### policy_engine (di sản)
- `PolicyEngine(db)` có `check_document_access(user, source, action) -> PolicyDecision(allowed: bool, reason: str)`.
- Lý do là `Allowed` hoặc `Access denied`; kết quả dựa trên can_access_document.
- `check_workspace_access` trong bản gốc là code chết. Có thể bỏ hoặc luôn trả về từ chối.

---

## 12. Router rbac (tiền tố /api): phòng ban, nhân viên, token, ma trận

Phòng ban "managed" là phòng ban có `external_id` khác null. Mọi thao tác ghi bên dưới gọi `log_audit(db, user, action, resource_type, resource_id, reason=...)` của audit_service.

### 12.1 Phòng ban

| Method | Đường dẫn | Quyền | Body / query | Kết quả |
|---|---|---|---|---|
| GET | /api/departments | org:departments:read | `include_inactive` (bool, mặc định false) | danh sách DepartmentOut (không sắp xếp riêng) |
| POST | /api/departments | org:departments:manage | `{name, description?}` | 201 `{id, name}`; audit create/department |
| PUT | /api/departments/{id} | org:departments:manage | `{name, description?}` | `{id, name}`; audit update |
| DELETE | /api/departments/{id} | org:departments:manage | | `{deleted: true}`; audit delete |

- Trường của DepartmentOut: `id`, `name`, `description`, `employee_count`, `code`, `parent_id`, `managed` (bool), `is_active`.
- Lỗi của PUT và DELETE:
  - 404 `Department not found`;
  - phòng ban managed: 409 `Phòng ban đồng bộ từ Keycloak — sửa tại trang Quản trị của Trợ lý ảo AI`.

### 12.2 Nhân viên

**GET /api/employees** (org:employees:read)
- Query: `department_id?`, `search?` (khớp một phần, không phân biệt hoa thường, trên tên hoặc email), `page` = 1, `page_size` = 20.
- Kết quả sắp theo tên.
- Phản hồi: `{items: EmployeeOut[], total, page, page_size, total_pages}`. total_pages = max(1, làm tròn lên total / page_size).
- Trường của EmployeeOut:
  - `id`, `name`, `email`, `role`
  - `global_role`, `global_role_source`
  - `department_ids`, `department_names`
  - `is_active`
  - `has_token` (bool)
  - `last_connected` (ISO hoặc null)

**POST /api/employees** (org:employees:manage) → 201 `{id, name, email}`, audit create/employee.
- Body: `{name, email, password?, role = "employee", global_role = "viewer", global_role_source?, department_ids = []}`.
- Lỗi 400:
  - `Password is required`
  - `Password must be at least 8 characters`
  - `Role must be 'admin' or 'employee'`
  - `Global role must be one of: viewer, contributor, knowledge_manager, admin`
  - `One or more departments not found`
- Phòng ban managed trong danh sách bị bỏ qua: thành viên của chúng chỉ đến từ Keycloak.

**PUT /api/employees/{id}** (org:employees:manage) → `{id, name}`, audit update.
- Body gồm các trường như POST, đều tùy chọn.
- Lỗi:
  - 404 `Employee not found`
  - 400 global_role không hợp lệ (thông báo như trên)
  - 400 `global_role_source must be 'sso' or 'manual'`
  - đặt source `sso` cho tài khoản không có external_id: 400 `Chỉ tài khoản đăng nhập qua Keycloak mới để Keycloak quản lý mức quyền`
- Hành vi:
  - Gửi source `sso`: đặt source `sso`, trả quyền quản lý cho Keycloak; có hiệu lực từ lần SSO kế tiếp.
  - Không gửi source mà global_role thay đổi: source thành `manual`. Keycloak sẽ chỉ nâng mức này, không hạ.
  - Có password: băm lại.
  - Có department_ids: đối soát thành viên chỉ với các phòng ban không managed. Liên kết tới phòng ban managed giữ nguyên.

**Các endpoint nhân viên khác:**

| Method | Đường dẫn | Quyền | Kết quả / lỗi |
|---|---|---|---|
| DELETE | /api/employees/{id} | manage | 404 `Employee not found`; tài khoản `role` admin: 400 `Cannot delete an admin account`; thành công `{deleted: true}` |
| POST | /api/employees/{id}/departments | manage | body `{department_id}`; 201; 404 `Employee not found` hoặc `Department not found`; đã thuộc: 409 `Employee already belongs to this department` |
| DELETE | /api/employees/{id}/departments/{dept_id} | manage | 404 `Membership not found`; `{removed: true}` |
| PATCH | /api/employees/{id}/toggle | manage | đảo is_active; `{id, is_active}`; audit với lý do ghi trạng thái mới |

### 12.3 Token MCP

| Method | Đường dẫn | Quyền | Kết quả |
|---|---|---|---|
| POST | /api/employees/{id}/token | org:employees:manage | 404 `Employee not found`; `{token, employee_name, instructions}` |
| DELETE | /api/employees/{id}/token | org:employees:manage | 404 `Employee not found or has no token`; `{revoked: true}` |
| POST | /api/my/mcp-token | đăng nhập | xoay token của chính mình; cùng dạng phản hồi |
| DELETE | /api/my/mcp-token | đăng nhập | thu hồi token của chính mình |
| GET | /api/my/mcp-token/status | đăng nhập | `{has_token}` |

- `instructions` là chuỗi hướng dẫn thêm máy chủ MCP vào cấu hình Claude Desktop. Chuỗi này chứa URL `/mcp` và header Authorization Bearer kèm token.

### 12.4 Ma trận quyền

**GET /api/rbac/matrix** (org:employees:read)
- Trả về `{roles, groups, labels, descriptions, all_permissions, role_permissions}`.
- `role_permissions` là kết quả của get_effective_role_permissions.

**PUT /api/rbac/matrix** (org:roles:manage)
- Body: `{role_permissions: {role_id: string[]}}`.
- Xử lý theo thứ tự:
  1. Bỏ qua vai trò admin; lọc chỉ giữ quyền hợp lệ.
  2. Lưu JSON vào khóa cấu hình `role_permissions_custom`.
  3. Nạp lại ghi đè bằng load_role_permissions_override.
  4. Ghi audit update/rbac_matrix, kèm lý do liệt kê các vai trò đã sửa.
  5. Commit.
- Trả về `{success: true, role_permissions}`.

---

## 13. Nhãn mật (app/services/security_label.py, loại C)

| Ký hiệu | Hành vi |
|---|---|
| `LEVELS` | Thứ tự tăng dần: PUBLIC < INTERNAL < RESTRICTED < CONFIDENTIAL |
| `DEFAULT_LEVEL` | INTERNAL |
| `normalize(value)` | Cắt khoảng trắng và viết hoa. Rỗng hoặc không hợp lệ thành INTERNAL |
| `allowed_labels(clearance)` | Các mức từ PUBLIC tới mức tiếp cận, tính cả mức tiếp cận. Không bao giờ vượt mức tiếp cận |
| `describe(clearance)` | Chuỗi mô tả điều kiện lọc và mức, để ghi log/audit |
| `source_label_clause(clearance)` | Điều kiện nhãn của tài liệu thuộc allowed_labels |
| `page_label_clause(clearance)` | Ẩn trang nếu tồn tại tài liệu nguồn trong `source_ids` của trang có nhãn ngoài danh sách cho phép |

Quy tắc áp dụng:
- Mức tiếp cận của nhân viên lấy từ `employees.clearance_level`, do org-sync đặt.
- Người dùng không phải admin chỉ thấy tài liệu và trang wiki có nhãn không vượt mức tiếp cận của mình.
- Admin thấy mọi nhãn trên giao diện quản trị.
- Qua MCP, nhãn luôn được áp, kể cả với admin (mục 8.1).

Hai helper của router sources mà test kiểm (đặc tả chi tiết ở tài liệu sources):

**`_checked_label(user, value) -> str`**
- value None hoặc rỗng: trả về INTERNAL.
- Ngược lại: cắt khoảng trắng và viết hoa.
- Không thuộc LEVELS: 400 `security_label phải thuộc PUBLIC, INTERNAL, RESTRICTED, CONFIDENTIAL`.
- Người không phải admin đặt nhãn cao hơn mức của mình: 403 `Không thể đặt nhãn cao hơn mức tiếp cận của bạn`.
- Admin được đặt mọi mức.

**`source_read_filter(user) -> (allowed: bool, clause | None)`**
- Dùng `_get_user_permissions`, tra **qua tên trong module sources** vì test monkeypatch `sources._get_user_permissions`.
- Người không phải admin và không có quyền doc:read nào: 403 `Permission required: doc:read`.
- Admin: (True, None).
- Người khác: clause là AND của điều kiện nhãn và `personal_visible_clause(id)`, cộng với lọc phòng ban nếu chỉ có own_dept.
- Test truyền object không có thuộc tính `id`, nên đọc id theo kiểu an toàn: không có thì là None.

---

## 14. Đồng bộ tổ chức (app/routers/org_sync.py, loại C) — hợp đồng

### 14.1 Hằng số
- Audience `cahy-wiki-org-sync`; audience kỹ năng `cahy-wiki-skill-sync`.
- Secret tối thiểu 32 ký tự.
- Body tối đa 5 MiB.
- Tên phòng ban tối đa 200 ký tự.
- Bộ nhớ `jti` chống phát lại: 120 giây.
- Dùng `CHATBOT_SUB_PREFIX` và `CHATBOT_TICKET_ISSUER` từ sso.py.

### 14.2 Lược đồ payload (Pydantic)

| Model | Trường |
|---|---|
| SyncUnit | `external_id` (1–64), `code` (1–64), `name` (1–200), `description` (≤4000, tùy chọn), `parent_external_id` (≤64, tùy chọn), `level` (int 1–100, mặc định 1) |
| SyncMember | `keycloak_id` (1–255), `chatbot_id?`, `email?` (≤200), `unit_external_ids` (list, ≤1000) |
| SyncClearance | `keycloak_id`, `chatbot_id?`, `email?`, `clearance_level` (≤20) |
| SyncAccount | `keycloak_id`, `chatbot_id?`, `enabled: bool`, `reactivate: bool = False`, `roles: Optional[list[str]]` (≤500) |
| SyncPayload | `units` (≤20000), `members` (≤200000), `clearances: Optional[list]`, `role_map: Optional[dict]` (≤1000), `accounts: Optional[list]`, `reason: Optional[str]` (≤200) |

### 14.3 Xác thực request (dùng chung cho org-sync và skill-sync)
- `chatbot_wiki_sso_secret` dưới 32 ký tự: 503 `Org sync is not configured (CHATBOT_WIKI_SSO_SECRET)`.
- Thiếu bearer: 401 `Missing sync token`.
- Kiểm token: HS256, secret chung, đúng audience, iss `cahy-chatbot`, leeway 10 giây, bắt buộc có `exp`, `iat`, `jti`, `body_sha256`. Sai: 401 `Invalid sync token`.
- SHA-256 hex của body thô khác `body_sha256`: 401 `Body does not match sync token`.
- Chống phát lại: lưu `jti` trong bộ nhớ tiến trình 120 giây. Gặp lại `jti`: 409 `Sync token already used`.

### 14.4 POST /api/internal/org-sync
- content-length hoặc body quá giới hạn: 413 `Payload too large`.
- JSON không qua được model: 422 `Invalid payload: N error(s)`.
- Gọi `apply_org_sync`, commit, trả về thống kê.

**`apply_org_sync(db, payload) -> dict`**

Trường hợp payload chỉ có tài khoản (accounts có giá trị, units rỗng, members rỗng, clearances None):
- Áp role_map nếu có, rồi áp accounts.
- Bỏ qua kiểm tra cây đơn vị rỗng.
- Trả về `accounts_deactivated`, `accounts_reactivated`, `accounts_roles_changed`, `role_map_changed`.

Trường hợp đầy đủ:
1. Loại trùng unit theo external_id. Code trùng (không phân biệt hoa thường): 422 `Duplicate unit codes in payload`.
2. Cây rỗng trong khi còn phòng ban đồng bộ đang hoạt động: 409 `Empty unit tree; refusing to deactivate all synced departments`.
3. Lần đầu (nhận phòng ban có sẵn): với phòng ban chưa đồng bộ, khớp lần lượt theo code, theo tên bằng code, rồi theo tên bằng tên unit. So sánh casefold.
4. Trước khi đổi tên, tạm giải phóng các tên và code sắp thay đổi để tránh vi phạm unique.
5. Chọn tên duy nhất theo thứ tự ưu tiên: tên; `tên (CODE)`; `tên (CODE <8 ký tự đầu external_id>)`; `CODE <external_id>`.
6. code viết hoa, is_active true. Mô tả rỗng không xóa mô tả cũ. parent_id lấy theo parent_external_id.
7. Phòng ban đồng bộ có unit không còn trong payload: đặt is_active false và gỡ mọi thành viên. Không bao giờ xóa hẳn.
8. Khớp member với nhân viên lần lượt theo: keycloak_id (external_id), `chatbot:<chatbot_id>`, email. Thành viên của các phòng ban đồng bộ được đối soát chính xác theo `unit_external_ids`.
9. Áp clearances, role_map, accounts.
10. Trả về: `accounts_*`, `departments`, `created`, `updated`, `adopted`, `deactivated`, `members_matched`, `members_pending`, `memberships_added`, `memberships_removed`, `clearances_set`, `role_map_changed`.

**`_apply_clearances(db, clearances) -> int`**
- Khớp theo external_id, rồi `chatbot:<id>`, rồi email (không phân biệt hoa thường).
- Đặt mức đã chuẩn hóa cho người khớp. Mọi nhân viên **khác** được hạ về INTERNAL.
- Trả về số dòng thay đổi.

**`_apply_role_map(db, role_map) -> bool`**
- Phần tử có role rỗng, role dài quá 255 ký tự, hoặc đích không thuộc thang: 422 `Invalid role_map entry for '<role>'`.
- Role thuộc `sso_admin_role_set`: 422 `Admin role '<role>' cannot be mapped`.
- Đã có dòng lưu và bằng map mới: trả False, không ghi gì.
- Ngược lại: lưu JSON đã sắp xếp vào AppConfig. Nếu map thực sự đổi so với giá trị đang hiệu lực (có thể là từ env), ghi audit `SSO_ROLE_MAP_UPDATE` với principal là `NIL_UUID`, loại system, resource config, metadata trước/sau.
- Trả về (trước khác sau).

**`_apply_accounts(db, accounts, reason) -> {deactivated, reactivated, roles_changed}`**
- Chỉ khớp theo external_id hoặc `chatbot:<id>`. **Không bao giờ khớp theo email.**
- `enabled` false:
  - Nếu đang hoạt động: khóa tài khoản và ghi audit `SSO_ACCOUNT_DEACTIVATED`. Lý do mặc định là `đồng bộ từ cổng quản trị`; metadata chứa email.
  - Luôn xóa các trường token MCP, kể cả khi tài khoản đã bị khóa (khi đó không ghi audit lần nữa).
- `reactivate` true và tài khoản đang khóa: mở khóa và ghi audit `SSO_ACCOUNT_REACTIVATED`. Đồng bộ định kỳ không gửi reactivate, nên không bao giờ tự mở khóa.
- `roles` khác None:
  - is_admin = roles giao với sso_admin_role_set.
  - Gọi `sync_employee_roles` với map từ `load_role_map`.
  - Có thay đổi thì ghi audit `SSO_GLOBAL_ROLE_SYNC`. Hạ quyền có hiệu lực ngay.
- `roles` None: global_role giữ nguyên.

### 14.5 POST /api/internal/skill-sync
- Body tối đa 4096 byte. Kiểm như 14.3 với audience `cahy-wiki-skill-sync`.
- Trả về `{items: [...]}`, mỗi phần tử gồm:
  - `slug`, `name`, `description`, `content`
  - `is_system`
  - `version` (current_version)
  - `updated_at` (ISO)
- Chỉ gồm các kỹ năng toàn cục đang hoạt động, sắp theo tên. Kỹ năng có SKILL.md không đọc được hoặc rỗng bị bỏ qua.
- Phụ thuộc: `app.routers.skills._read_skill_files` và `_split_skill_md` phải tồn tại (xem tài liệu skills).

### 14.6 Phía chatbot (để đối chiếu)

**Gửi org-sync**
- Đích: `<arkon_base>/internal/org-sync`, với base đã kết thúc bằng `/api` (ví dụ `http://wiki_api:5055/api`).
- Body là JSON gọn, mã UTF-8.
- Claims của token:
  - `iss` = `cahy-chatbot`, `aud`
  - `iat`, `exp` = iat + 60 giây
  - `jti` (uuid hex)
  - `body_sha256`
- Timeout 30 giây; riêng lệnh đẩy tài khoản là 8 giây.
- Gặp 404 thì thử base kế tiếp; lỗi khác thì dừng.

**Nội dung payload**
- `units`:
  - `external_id` = id nhóm
  - `code` = tên nhóm viết hoa, tối đa 32 ký tự; trùng thì thêm `~<8 ký tự id>`
  - `name` = thuộc tính display_name, hoặc tên nhóm
  - `description`, `parent_external_id`
  - `level` = độ sâu
- `members`: `keycloak_id`, `chatbot_id`, `email`, `unit_external_ids` đã sắp xếp.
- `clearances`: `keycloak_id`, `chatbot_id`, `email`, `clearance_level` (hết hạn hoặc thiếu thì là INTERNAL); hoặc null.
- `role_map`: từ ánh xạ vai trò của chatbot.
- `accounts`: các user Keycloak bị khóa với `enabled` false; hoặc null.
- `reason`: `Đồng bộ định kỳ` hoặc `Đồng bộ từ cổng quản trị`.

**Đẩy tài khoản riêng lẻ**
- Gửi `units: []`, `members: []` và `accounts` gồm `{keycloak_id, chatbot_id?, enabled, reactivate?, roles?}`.

**Chu kỳ và host**
- Chu kỳ `ORG_SYNC_INTERVAL_SECONDS`: mặc định 300, tối thiểu 30, 0 là tắt.
- Host ngoài phải dùng https.

**Skill-sync phía chatbot**
- Gửi body `{}`, aud `cahy-wiki-skill-sync`, TTL 60 giây.
- Mỗi phần tử trở thành kỹ năng có id `wiki-<slug>`. Tiêu đề lấy từ dòng tiêu đề cấp 1 đầu tiên.
- Thẻ gồm `kho-tri-thuc`, cộng `he-thong` nếu is_system. Metadata gồm source `wiki`, `wiki_slug`, `wiki_version`.
- Phần tử biến mất thì bị vô hiệu, không bị xóa. Phản hồi rỗng bị coi là lỗi và không thay đổi gì.
- Quyền đọc công khai.
- Chu kỳ `WIKI_SKILL_SYNC_INTERVAL_SECONDS`: mặc định 600, tối thiểu 60, trễ 15 giây sau khởi động.

---

## 15. Ký hiệu c2 và test bắt buộc phải có

| Module | Ký hiệu | Chữ ký / yêu cầu |
|---|---|---|
| app.services.auth_service | `JWT_EXPIRE_HOURS` | int = 24 |
| | `create_access_token` | (employee_id: str, role: str, name: str) -> str |
| | `decode_access_token` | (token) -> Optional[dict]; None với token có aud |
| | `create_source_file_token` / `decode_source_file_token` | mục 4.2 |
| | `is_keycloak_token` | (token) -> bool, không ném lỗi |
| | `_load_employee` | async (db, UUID) -> Optional[Employee]; tra qua module |
| | `employee_from_bearer` | async (db, token) -> Employee; đúng 1 commit hoặc 1 rollback ở nhánh Keycloak; tra `sso.employee_from_access_token` lúc gọi |
| | `require_permission` | (permission: str) -> Depends |
| | `get_current_user`, `require_admin`, `hash_password`, `verify_password`, `authenticate_employee` | mục 4 |
| app.routers.sso (C) | `employee_from_access_token`, `SIGNING_ALGORITHMS`, `CHATBOT_SUB_PREFIX`, `CHATBOT_TICKET_ISSUER` | cần `audit_chain.record`, `sso_roles`, `settings.*` |
| app.services.mcp_auth_service | `ResolvedIdentity`, `apply_scope_filter`, `MCPAuthService`, `hash_token`, `page_source_clause` | mục 8.1 |
| app.mcp.tools | `forwarded_role(headers, trust) -> str`, `register_tools(mcp)` | mục 8.2 |
| app.mcp.permissions | `ToolRequirement`, `kb_tool`, `requirement_for`, các hằng số CAN_* | mục 8.3 |
| app.services.permissions | `ALL_PERMISSIONS`, `ROLE_PERMISSIONS_MAP`, `SYSTEM_ROLES`, `PERMISSION_GROUPS`, `PERMISSION_LABELS`, `PERMISSION_DESCRIPTIONS`, `EMPLOYEE_DEFAULT_PERMISSIONS`, `ROLE_PRESETS`, `LEGACY_PERMISSION_MAP`, `get_effective_role_permissions`, `load_role_permissions_override` | mục 10 |
| app.services.permission_engine | các ký hiệu ở mục 11, đặc biệt `_get_user_permissions`, `get_scope_level`, `personal_visible_clause` | |
| app.services.audit_chain | `record(**kwargs)` (async, chỉ nhận keyword; test monkeypatch), `NIL_UUID` | xem tài liệu nền tảng/audit |
| app.services.audit_service | `log_audit(db, user, action, resource_type, resource_id, reason=None)` | |
| app.database.models | `AppConfig`, `Department`, `Employee`, `EmployeeDepartment`, `Source`, `SourceDepartment`, `WikiPage` (cột như mục 3); `OAuthClient`, `OAuthAuthCode` nằm ở module riêng `app.database.oauth_models` | |
| app.config.settings | các khóa ở mục 2, cùng các thuộc tính `sso_admin_role_set`, `sso_role_map`, `sso_mcp_client_set`, `cors_origin_list` | |
| app.routers.sources | `_authenticate_request_user`, `source_read_filter`, `_checked_label`, `_get_user_permissions` (tên được import vào module) | Xem dưới |

**`_authenticate_request_user(token, credentials, db, source_id) -> Employee`** (async)
- Có header bearer: gọi `auth_service.employee_from_bearer(db, credentials.credentials)`. Tra qua module auth_service tại thời điểm gọi, vì test monkeypatch.
- Không có cả hai: 401 `Not authenticated`.
- Có `?token=`:
  - `decode_source_file_token(token, str(source_id))` trả None: 401 `Invalid or expired token`. Trường hợp này gồm cả JWT phiên và vé của tài liệu khác.
  - sub không phải UUID: 401 `Invalid token subject`.
  - Nạp nhân viên bằng tra khóa chính `db.get(Employee, uuid)`. Test dùng session giả chỉ có phương thức `get(model, id)`, không có `execute`.
  - Không thấy hoặc bị khóa: 401 `User not found or inactive`.

Tóm tắt các test liên quan:
- test_bearer_auth: phân biệt token Keycloak; số lần commit/rollback; 401 với chuỗi rác mà không gọi Keycloak; vé tệp không phải phiên.
- test_sso_role_map: sso_roles, load_role_map, `_apply_role_map` cùng audit.
- test_org_sync_accounts: `_apply_accounts` và `apply_org_sync` với payload chỉ có tài khoản. Session giả có `execute` trả về `scalars().all()` và `flush`.
- test_security_label: nhãn, `apply_scope_filter`, `ResolvedIdentity.allowed_labels`, `source_read_filter`, `_checked_label`, `_apply_clearances`.
- test_mcp_forwarded_identity: `forwarded_role` và giá trị mặc định False.
- test_legal_scope_enforcement: trang kế thừa phạm vi của tài liệu nguồn.

---

## 16. Di sản, không xây lại
- `app/routers/scopes.py`: không gắn, không viết lại.
- `policy_engine.check_workspace_access`: code chết.
- Cột `employees.mcp_token`: chỉ xóa về null, không đọc.
- `workspace_memberships` trong phản hồi auth luôn là mảng rỗng.
