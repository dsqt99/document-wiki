# Arkon Backend REST API Reference & Integration Guide

Tài liệu tham chiếu và hướng dẫn tích hợp toàn diện cho hệ thống REST API của **Arkon — Enterprise AI Control Center**.

Tài liệu này được thiết kế để phục vụ việc tích hợp đa nền tảng: dịch vụ nội bộ (Internal Services), các ứng dụng Microservices, Agentic workflows, và hệ thống của bên thứ ba.

---

## Mục lục

1. [Tổng quan & Chuẩn giao tiếp (Overview & Standards)](#1-tổng-quan--chuẩn-giao-tiếp-overview--standards)
2. [Xác thực & Ủy quyền (Authentication & Authorization)](#2-xác-thực--ủy-quyền-authentication--authorization)
3. [Quản lý Tổ chức, Phân quyền & MCP Tokens (RBAC API)](#3-quản-lý-tổ-chức-phân-quyền--mcp-tokens-rbac-api)
4. [Quản lý Phân loại Tri thức (Knowledge Types API)](#4-quản-lý-phân-loại-tri-thức-knowledge-types-api)
5. [Tài liệu Nguồn & Quy trình Tiếp nhận (Sources & Ingestion Pipeline API)](#5-tài-liệu-nguồn--quy-trình-tiếp-nhận-sources--ingestion-pipeline-api)
6. [Cơ sở Tri thức Wiki (Wiki Knowledge Base API)](#6-cơ-sở-tri-thức-wiki-wiki-knowledge-base-api)
7. [Quy trình Đề xuất, Duyệt bài & Nhánh (Wiki Drafts & Branches API)](#7-quy-trình-đề-xuất-duyệt-bài--nhánh-wiki-drafts--branches-api)
8. [Quản lý Kỹ năng AI & Công cụ Agent (Skills & Skill Contributions API)](#8-quản-lý-kỹ-năng-ai--công-cụ-agent-skills--skill-contributions-api)
9. [Ghi chú Nhanh (Notes API)](#9-ghi-chú-nhanh-notes-api)
10. [Hệ thống Thông báo (Notifications API)](#10-hệ-thống-thông-báo-notifications-api)
11. [Nhật ký Kiểm toán (Audit Logs API)](#11-nhật-ký-kiểm-toán-audit-logs-api)
12. [Cấu hình Hệ thống & Quản lý Mô hình AI (Admin Settings & Models API)](#12-cấu-hình-hệ-thống--quản-lý-mô-hình-ai-admin-settings--models-api)
13. [Báo cáo & Thống kê Quản trị (Admin Statistics & Analytics API)](#13-báo-cáo--thống-kê-quản-trị-admin-statistics--analytics-api)
14. [Kiểm tra Trạng thái Hệ thống (Health Checks API)](#14-kiểm-tra-trạng-thái-hệ-thống-health-checks-api)
15. [Mẫu Code Tích hợp Chi tiết (Integration Code Samples)](#15-mẫu-code-tích-hợp-chi-tiết-integration-code-samples)

---

## 1. Tổng quan & Chuẩn giao tiếp (Overview & Standards)

### 1.1. Base URLs
- **Production Server:** `https://api-arkon.anm05.com`
- **API Base Prefix:** `https://api-arkon.anm05.com/api`
- **Local Dev Server:** `http://localhost:8000/api`
- **Interactive OpenAPI UI (Swagger):** `https://api-arkon.anm05.com/docs`
- **OpenAPI Schema:** [`docs/api.json`](file:///home/cahy/code/arkon/docs/api.json) hoặc `https://api-arkon.anm05.com/openapi.json`
- **MCP Server Endpoint:** `https://api-arkon.anm05.com/mcp`

### 1.2. Định dạng & Tiêu chuẩn
- **Content-Type:** Mặc định gửi và nhận `application/json` (trừ các endpoint upload file sử dụng `multipart/form-data`, hoặc export sử dụng `text/csv`).
- **Mã hóa:** UTF-8 cho toàn bộ dữ liệu văn bản.
- **Quy ước múi giờ:** Toàn bộ timestamps trả về định dạng chuẩn ISO 8601 UTC (ví dụ `2026-09-09T14:30:00Z`).

### 1.3. Cấu trúc Lỗi Chuẩn (Standard Error Response)
Khi request không thành công, API trả về mã HTTP Status lỗi kèm payload JSON mô tả chi tiết:

```json
{
  "detail": "Mô tả lý do phát sinh lỗi"
}
```

Một số mã trạng thái thường gặp:
- `200 OK`: Thao tác thành công, có dữ liệu trả về.
- `201 Created`: Tạo tài nguyên thành công.
- `204 No Content`: Thao tác thành công, không có nội dung trả về (thường gặp khi Delete).
- `400 Bad Request`: Payload sai cú pháp, giá trị không hợp lệ hoặc thiếu điều kiện tiên quyết.
- `401 Unauthorized`: Chưa đăng nhập hoặc Access Token không hợp lệ / hết hạn.
- `403 Forbidden`: Người dùng không có quyền truy cập hoặc thao tác trên tài nguyên tương ứng.
- `404 Not Found`: Tài nguyên không tồn tại.
- `409 Conflict`: Xung đột phiên bản dữ liệu (ví dụ trùng slug, edit conflict).
- `422 Unprocessable Entity`: Dữ liệu không thỏa mãn validation schema của FastAPI/Pydantic.
- `500 Internal Server Error`: Lỗi phát sinh trong quá trình xử lý nội bộ phía máy chủ.

---

## 2. Xác thực & Ủy quyền (Authentication & Authorization)

Arkon cung cấp hai hình thức xác thực chính:
1. **JWT Bearer Token** cho người dùng đăng nhập qua Web App hoặc REST Client.
2. **OAuth 2.0 (RFC 9728 / PKCE) & Static Personal Access Token (PAT)** dành cho AI Clients / Claude Desktop / MCP Tools kết nối giao thức MCP.

### 2.1. Đăng nhập lấy JWT Token
* **Endpoint:** `POST /api/auth/login`
* **Content-Type:** `application/json`

#### Request Body
```json
{
  "email": "user@example.com",
  "password": "YourSecurePassword"
}
```

#### Response (200 OK)
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": "7b0f69a5-7f99-4d83-9b9f-0cbf7471253c",
    "name": "Nguyen Van A",
    "email": "user@example.com",
    "role": "admin",
    "global_role": "admin",
    "department_ids": ["9f8b417e-61c0-4229-9e8a-bf5c8d0e4a7a"],
    "department_names": ["Engineering"],
    "permissions": ["*"]
  }
}
```

### 2.2. Gửi Header Xác thực
Sau khi có `access_token`, thêm header sau vào mọi request:
```http
Authorization: Bearer <access_token>
```

### 2.3. Lấy thông tin tài khoản hiện tại (Profile)
* **Endpoint:** `GET /api/auth/me`
* **Mô tả:** Lấy thông tin tài khoản, phòng ban, và danh sách quyền hạn chi tiết của người dùng đang đăng nhập.

### 2.4. Đổi mật khẩu
* **Endpoint:** `POST /api/auth/change-password`
* **Request Body:**
```json
{
  "current_password": "OldPassword123!",
  "new_password": "NewSecurePassword456!"
}
```

### 2.5. Kiểm tra trạng thái xác thực
* **Endpoint:** `GET /api/auth/status`
* **Mô tả:** Kiểm tra token có còn hiệu lực hay không. Trả về `{"authenticated": true, "user": {...}}`.

### 2.6. Khám phá OAuth 2.0 & MCP Resource Metadata
Phục vụ chuẩn **RFC 8414 & RFC 9728** để Claude Desktop hoặc MCP Agent tự động nhận diện luồng xác thực:
- `GET /.well-known/oauth-authorization-server`: Siêu dữ liệu OAuth 2.0 Server.
- `GET /.well-known/oauth-protected-resource`: Siêu dữ liệu máy chủ tài nguyên bảo vệ.
- `GET /.well-known/oauth-protected-resource/mcp`: Siêu dữ liệu bảo vệ riêng cho MCP endpoint `/mcp`.
- `POST /oauth/register`: Đăng ký client động (Dynamic Client Registration).
- `GET /oauth/authorize`: Trang giao diện cấp quyền truy cập OAuth.
- `POST /oauth/authorize`: Xử lý chấp thuận hoặc từ chối ủy quyền.
- `POST /oauth/token`: Cấp phát token cho flow Authorization Code with PKCE.

---

## 3. Quản lý Tổ chức, Phân quyền & MCP Tokens (RBAC API)

Module RBAC quản lý cấu trúc phòng ban (Departments), hồ sơ nhân sự (Employees), phân chia quyền hạn theo Scope (Department/Global), và cấp phát token truy cập MCP.

### 3.1. Quản lý Phòng ban (Departments)

| Phương thức | Endpoint | Mô tả | Quyền yêu cầu |
|---|---|---|---|
| `GET` | `/api/departments` | Lấy danh sách tất cả phòng ban | Người dùng đã đăng nhập |
| `POST` | `/api/departments` | Tạo phòng ban mới | `admin` |
| `PUT` | `/api/departments/{dept_id}` | Cập nhật thông tin phòng ban | `admin` |
| `DELETE` | `/api/departments/{dept_id}` | Xóa phòng ban | `admin` |

#### Request Body (Tạo / Cập nhật phòng ban)
```json
{
  "name": "Trung tâm Trí tuệ Nhân tạo",
  "description": "Nghiên cứu, phát triển giải pháp AI và tích hợp LLM"
}
```

---

### 3.2. Quản lý Nhân sự (Employees)

| Phương thức | Endpoint | Mô tả | Quyền yêu cầu |
|---|---|---|---|
| `GET` | `/api/employees` | Lấy danh sách nhân viên kèm phân trang | `admin` hoặc quyền quản trị |
| `POST` | `/api/employees` | Tạo nhân viên mới | `admin` |
| `PUT` | `/api/employees/{emp_id}` | Cập nhật thông tin nhân viên | `admin` |
| `DELETE` | `/api/employees/{emp_id}` | Xóa nhân viên | `admin` |
| `PATCH` | `/api/employees/{emp_id}/toggle` | Bật / tắt kích hoạt tài khoản | `admin` |

#### Query Parameters của `GET /api/employees`
- `department_id` *(optional, UUID)*: Lọc nhân sự theo phòng ban.
- `search` *(optional, string)*: Tìm kiếm theo tên hoặc email.
- `page` *(optional, int, mặc định `1`)*: Số trang.
- `page_size` *(optional, int, mặc định `20`)*: Số lượng bản ghi trên một trang.

#### Request Body (Tạo nhân sự mới)
```json
{
  "name": "Tran Thi B",
  "email": "ttb@company.com",
  "password": "StrongPassword2026!",
  "role": "employee",
  "global_role": "contributor",
  "department_ids": ["9f8b417e-61c0-4229-9e8a-bf5c8d0e4a7a"]
}
```

---

### 3.3. Phân quyền Phòng ban cho Nhân viên
- **Thêm nhân viên vào phòng ban:** `POST /api/employees/{emp_id}/departments`
  - Body: `{"department_id": "UUID"}`
- **Gỡ nhân viên khỏi phòng ban:** `DELETE /api/employees/{emp_id}/departments/{dept_id}`

---

### 3.4. Quản lý MCP Token (Model Context Protocol Access)
Dành cho việc cấu hình kết nối Claude Desktop hoặc Cursor IDE đến Arkon MCP Server:
- `POST /api/my/mcp-token`: Tự tạo / làm mới MCP Bearer Token cho chính mình.
- `GET /api/my/mcp-token/status`: Kiểm tra token MCP cá nhân đã kích hoạt hay chưa.
- `DELETE /api/my/mcp-token`: Thu hồi token MCP của chính mình.
- `POST /api/employees/{emp_id}/token`: Admin tạo / cấp phát MCP token cho nhân sự chỉ định.
- `DELETE /api/employees/{emp_id}/token`: Admin thu hồi MCP token của nhân sự chỉ định.

---

## 4. Quản lý Phân loại Tri thức (Knowledge Types API)

Knowledge Types đóng vai trò là danh mục phân loại tài liệu (SOP, Quy trình, Kiến trúc, Chính sách...) với mã định danh slug và màu sắc hiển thị.

| Phương thức | Endpoint | Mô tả |
|---|---|---|
| `GET` | `/api/knowledge-types` | Lấy danh sách các loại tri thức hiện có |
| `POST` | `/api/knowledge-types` | Tạo loại tri thức mới |
| `PUT` | `/api/knowledge-types/{kt_id}` | Chỉnh sửa tên, slug, màu sắc, mô tả |
| `DELETE` | `/api/knowledge-types/{kt_id}` | Xóa loại tri thức |
| `PATCH` | `/api/knowledge-types/reorder` | Cập nhật thứ tự sắp xếp hiển thị |

#### Request Body (Tạo / Cập nhật Loại tri thức)
```json
{
  "name": "Quy chuẩn Bảo mật (Security Standards)",
  "slug": "security-standards",
  "color": "#e11d48",
  "description": "Các tiêu chuẩn, checklist an toàn thông tin và bảo mật ứng dụng"
}
```

#### Request Body (Sắp xếp thứ tự `PATCH /api/knowledge-types/reorder`)
```json
{
  "order": [
    "11111111-2222-3333-4444-555555555555",
    "22222222-3333-4444-5555-666666666666"
  ]
}
```

---

## 5. Tài liệu Nguồn & Quy trình Tiếp nhận (Sources & Ingestion Pipeline API)

Module Sources xử lý việc thu thập tài liệu gốc (PDF, Word DOCX, Plain text, URL Web), thực hiện pipeline bóc tách dữ liệu thông minh (MRP - Multi-stage Refinement Pipeline) và chuyển đổi thành bài viết Wiki.

### 5.1. Danh sách Tài liệu Nguồn
* **Endpoint:** `GET /api/sources`
* **Query Parameters:**
  - `knowledge_type_id` *(optional, UUID)*: Lọc theo loại tri thức.
  - `department_id` *(optional, UUID)*: Lọc theo phòng ban sở hữu.
  - `status` *(optional, string)*: `pending`, `processing`, `extracting`, `awaiting_approval`, `completed`, `failed`.
  - `search` *(optional, string)*: Từ khóa tìm kiếm theo tên tệp hoặc tiêu đề.
  - `page` *(optional, int, mặc định `1`)*.
  - `page_size` *(optional, int, mặc định `20`)*.

---

### 5.2. Tải lên Tài liệu Tệp tin (Upload File)
* **Endpoint:** `POST /api/sources/upload`
* **Content-Type:** `multipart/form-data`

#### Form Parameters
- `file` *(bắt buộc, Binary File)*: Hỗ trợ `.pdf`, `.docx`, `.doc`, `.txt`, `.md`.
- `title` *(tùy chọn, string)*: Tiêu đề hiển thị của tài liệu.
- `knowledge_type_id` *(tùy chọn, UUID)*: ID loại tri thức áp dụng.
- `department_ids` *(tùy chọn, list of UUIDs)*: Danh sách ID các phòng ban có quyền truy cập.
- `preserve_verbatim` *(tùy chọn, boolean, mặc định `false`)*: Yêu cầu AI giữ nguyên văn bản gốc, tránh tóm lược quá mức.

---

### 5.3. Thêm Tài liệu từ Đường dẫn Web (URL)
* **Endpoint:** `POST /api/sources/url`
* **Content-Type:** `application/json`

#### Request Body
```json
{
  "url": "https://raw.githubusercontent.com/org/repo/main/README.md",
  "title": "Tài liệu Kiến trúc Microservices",
  "knowledge_type_id": "22222222-3333-4444-5555-666666666666",
  "department_ids": ["9f8b417e-61c0-4229-9e8a-bf5c8d0e4a7a"],
  "preserve_verbatim": false
}
```

---

### 5.4. Xem Chi tiết, Tải tệp & Tiến trình Xử lý
- `GET /api/sources/{source_id}`: Xem chi tiết tài liệu (kèm toàn văn trích xuất `full_text` và mục lục `outline`).
- `PATCH /api/sources/{source_id}`: Cập nhật tiêu đề, loại tri thức hoặc phòng ban sở hữu.
- `DELETE /api/sources/{source_id}`: Xóa tài liệu khỏi hệ thống.
- `GET /api/sources/{source_id}/file`: Tải tệp tài liệu gốc lưu trữ tại MinIO.
- `GET /api/sources/{source_id}/preview`: Xem nội dung trích xuất dạng bản xem trước.
- `GET /api/sources/{source_id}/progress`: Lấy tiến trình xử lý thời gian thực (`progress` từ 0 - 100, `progress_message`, trạng thái hiện tại).
- `POST /api/sources/{source_id}/retry`: Thử xử lý lại tài liệu nếu pipeline trước đó gặp sự cố kỹ thuật.

---

### 5.5. Quy trình Kiểm duyệt Con người (Human-in-the-Loop Pipeline)
Nếu hệ thống bật chế độ kiểm duyệt trước khi tổng hợp thành trang Wiki:
- `POST /api/sources/{source_id}/approve-extraction`: Người dùng kiểm tra và chấp thuận dữ liệu văn bản vừa trích xuất.
- `GET /api/sources/{source_id}/plan`: Xem kế hoạch biên soạn Wiki do AI đề xuất (danh sách trang Wiki sẽ được tạo hoặc cập nhật).
- `POST /api/sources/{source_id}/plan/approve`: Duyệt kế hoạch để tiến hành sinh bài Wiki.
- `POST /api/sources/{source_id}/plan/regenerate`: Yêu cầu AI lập lại kế hoạch biên soạn kèm ghi chú định hướng.
- `POST /api/sources/{source_id}/plan/reject`: Từ chối kế hoạch biên soạn.

---

## 6. Cơ sở Tri thức Wiki (Wiki Knowledge Base API)

Wiki Knowledge Base là kho bài viết Markdown hoàn chỉnh được tạo tự động từ tài liệu nguồn hoặc do nhân sự biên tập trực tiếp.

### 6.1. Tra cứu & Đọc Bài viết Wiki

| Phương thức | Endpoint | Mô tả |
|---|---|---|
| `GET` | `/api/wiki/pages` | Danh sách bài viết Wiki theo bộ lọc |
| `GET` | `/api/wiki/pages/{slug}` | Đọc chi tiết bài viết theo Slug |
| `GET` | `/api/wiki/index` | Lấy cây mục lục bài viết theo danh mục |
| `GET` | `/api/wiki/my-scopes` | Danh sách Scopes người dùng hiện tại có quyền đọc |
| `GET` | `/api/wiki/log` | Lịch sử hoạt động chỉnh sửa Wiki toàn hệ thống |

#### Query Parameters của `GET /api/wiki/pages`
- `page_type` *(optional, string)*: `concept`, `process`, `system`, `guide`, `reference`.
- `knowledge_type_slug` *(optional, string)*: Lọc theo slug loại tri thức.
- `scope_type` *(optional, string)*: `global` hoặc `department`.
- `scope_id` *(optional, UUID)*: ID phòng ban nếu scope là department.
- `limit` *(optional, int, mặc định `20`)*.
- `offset` *(optional, int, mặc định `0`)*.

#### Response Chi tiết Bài viết (`GET /api/wiki/pages/{slug}`)
```json
{
  "slug": "kien-truc-he-thong-arkon",
  "title": "Kiến trúc Hệ thống Arkon",
  "page_type": "system",
  "summary": "Mô tả chi tiết kiến trúc microservices và pipeline bóc tách dữ liệu",
  "content_md": "# Kiến trúc Hệ thống Arkon\n\n## 1. Thành phần\n...",
  "knowledge_type_slugs": ["tech-spec"],
  "scope_type": "global",
  "scope_id": null,
  "status": "published",
  "version": 3,
  "backlinks": ["tong-quan-tri-thuc"],
  "outlinks": ["quy-trinh-mrp-ingestion"],
  "source_ids": ["33333333-4444-5555-6666-777777777777"],
  "updated_at": "2026-09-08T10:00:00Z"
}
```

---

### 6.2. Tạo, Sửa & Xóa Trực tiếp (Dành cho Quản trị viên)
- `POST /api/wiki/pages`: Tạo trực tiếp trang Wiki mới (bỏ qua bước duyệt).
- `PUT /api/wiki/pages/{slug}`: Biên tập trực tiếp nội dung bài viết.
- `DELETE /api/wiki/pages/{slug}`: Xóa bài viết.
- `PATCH /api/wiki/pages/{slug}/status`: Chuyển đổi trạng thái bài viết (`published` hoặc `archived`).

#### Request Body (Tạo bài viết `POST /api/wiki/pages`)
```json
{
  "slug": "huong-dan-trien-khai-docker",
  "title": "Hướng dẫn Triển khai Docker và Compose",
  "page_type": "guide",
  "knowledge_type_slugs": ["tech-spec"],
  "scope_type": "global",
  "content_md": "# Hướng dẫn Docker\n\nChạy `docker compose up -d`...",
  "summary": "Tài liệu hướng dẫn vận hành hệ thống container"
}
```

---

### 6.3. Lịch sử Phiên bản & Rollback (Versioning)
- `GET /api/wiki/pages/{slug}/revisions`: Lấy danh sách toàn bộ các phiên bản trong quá khứ kèm tác giả và ghi chú thay đổi.
- `POST /api/wiki/pages/{slug}/revisions/{version}/rollback`: Khôi phục nội dung bài viết về đúng phiên bản chỉ định.

---

### 6.4. Đồ thị Tri thức, Kiểm tra Lỗi & Chủ đề Hot
- `GET /api/wiki/graph`: Trả về dữ liệu nút (Nodes) và cạnh (Edges) để hiển thị sơ đồ mạng lưới liên kết bài viết (Knowledge Graph).
- `GET /api/wiki/lint`: Phát hiện các vấn đề trong kho tri thức (liên kết gãy `broken_links`, bài viết thiếu tóm tắt, trang mồ côi).
- `GET /api/wiki/orphaned`: Liệt kê các bài viết mồ côi (không có liên kết nào trỏ đến).
- `GET /api/wiki/hot`: Danh sách các bài viết đang được xem và tra cứu nhiều nhất.
- `POST /api/wiki/hot/rebuild`: Tính toán lại bảng xếp hạng bài viết hot.
- `POST /api/wiki/images/resolve`: Phân tích và chuyển đổi URL hình ảnh nội bộ trong Markdown sang đường dẫn tải hợp lệ.

---

## 7. Quy trình Đề xuất, Duyệt bài & Nhánh (Wiki Drafts & Branches API)

Nhằm đảm bảo chất lượng tri thức doanh nghiệp, nhân sự thông thường sẽ gửi bản nháp đề xuất (Draft) để người quản lý (Manager/Admin) phê duyệt trước khi cập nhật vào bài viết chính thức.

### 7.1. Đề xuất Bản nháp (Drafts)
- **Đề xuất tạo trang mới:** `POST /api/wiki/drafts/create`
- **Đề xuất sửa trang hiện có:** `POST /api/wiki/pages/{slug}/drafts`
- **Danh sách toàn bộ bản nháp:** `GET /api/wiki/drafts` (Hỗ trợ lọc theo `status`, `mine=true`, phân trang).
- **Danh sách bản nháp của một trang:** `GET /api/wiki/pages/{slug}/drafts`
- **Xem chi tiết bản nháp & diff:** `GET /api/wiki/drafts/{draft_id}`
- **Xem các vòng góp ý (Review Rounds):** `GET /api/wiki/drafts/{draft_id}/rounds`

#### Request Body (`POST /api/wiki/pages/{slug}/drafts`)
```json
{
  "content_md": "# Nội dung cập nhật bổ sung...\n\nThêm chương 3...",
  "note": "Bổ sung chính sách hoàn tiền năm 2026",
  "base_version": 2
}
```

---

### 7.2. Phê duyệt & Xử lý Bản nháp
- `POST /api/wiki/drafts/{draft_id}/approve`: Duyệt bản nháp và gộp vào bài viết chính thức (Merge).
- `POST /api/wiki/drafts/{draft_id}/reject`: Từ chối bản nháp kèm lý do.
- `POST /api/wiki/drafts/{draft_id}/request-changes`: Yêu cầu tác giả chỉnh sửa lại bản nháp kèm nhận xét chi tiết.
- `PATCH /api/wiki/drafts/{draft_id}/content`: Tác giả nộp lại nội dung bản nháp sau khi đã tiếp thu góp ý.
- `POST /api/wiki/drafts/{draft_id}/withdraw`: Tác giả tự rút lại bản nháp đã nộp.
- `POST /api/wiki/drafts/bulk-approve`: Duyệt đồng loạt nhiều bản nháp cùng lúc.

#### Request Body (Duyệt bản nháp `POST /api/wiki/drafts/{draft_id}/approve`)
```json
{
  "reviewer_note": "Nội dung chuẩn xác, đã kiểm tra kỹ thuật.",
  "allow_conflict": false
}
```

---

### 7.3. Phân nhánh Wiki Đa Trang (Wiki Branches)
Hỗ trợ việc chuẩn bị bản cập nhật lớn trải dài trên nhiều trang tài liệu cùng lúc theo mô hình phân nhánh tương tự Git:
- `POST /api/wiki/branches`: Tạo nhánh đề xuất mới.
- `GET /api/wiki/branches`: Lấy danh sách các nhánh đang hoạt động.
- `GET /api/wiki/branches/{branch_id}`: Xem thông tin nhánh và danh sách các trang đã được sửa đổi bên trong nhánh.
- `POST /api/wiki/branches/{branch_id}/submit`: Nộp toàn bộ nhánh để chờ phê duyệt.
- `POST /api/wiki/branches/{branch_id}/merge`: Hợp nhất toàn bộ thay đổi trong nhánh vào Wiki chính thức.
- `POST /api/wiki/branches/{branch_id}/close`: Đóng hoặc hủy nhánh đề xuất.
- `POST /api/wiki/branches/{branch_id}/rebase/{draft_id}`: Cập nhật lại bản nháp trong nhánh nếu trang gốc đã có phiên bản mới hơn ngoài master.

---

## 8. Quản lý Kỹ năng AI & Công cụ Agent (Skills & Skill Contributions API)

Module Skills quản lý các gói kỹ năng (Agent Skills theo chuẩn YAML Frontmatter + Markdown + Scripts) giúp mở rộng năng lực cho các trợ lý AI và MCP Clients.

### 8.1. Quản lý Gói Kỹ năng Hệ thống (Skills)

| Phương thức | Endpoint | Mô tả |
|---|---|---|
| `POST` | `/api/skills/upload` | Tải lên gói kỹ năng mới (file `.zip`) |
| `POST` | `/api/skills/{slug}/reupload` | Nâng cấp phiên bản mới cho kỹ năng có sẵn (file `.zip`) |
| `POST` | `/api/skills/inspect-zip` | Đọc thông tin mô tả bên trong file `.zip` mà không cần cài đặt |
| `GET` | `/api/skills` | Danh sách các kỹ năng đang hoạt động |
| `GET` | `/api/skills/{slug}` | Xem chi tiết metadata, phiên bản, hướng dẫn sử dụng |
| `PATCH` | `/api/skills/{slug}` | Cập nhật cấu hình hoặc bật/tắt kỹ năng |
| `DELETE` | `/api/skills/{slug}` | Xóa kỹ năng khỏi hệ thống |
| `GET` | `/api/skills/{skill_id}/files` | Liệt kê danh sách tệp bên trong gói kỹ năng |
| `GET` | `/api/skills/{skill_id}/files/content` | Đọc nội dung tệp tin cụ thể (ví dụ `SKILL.md`) |
| `GET` | `/api/skills/{slug}/versions` | Xem lịch sử các phiên bản đã phát hành |
| `POST` | `/api/skills/{slug}/set-latest` | Chỉ định phiên bản mặc định được kích hoạt |

---

### 8.2. Quy trình Đóng góp Kỹ năng Cộng đồng (Skill Contributions)
Nhân sự có thể tạo, chỉnh sửa tệp tin mã nguồn và đề xuất kỹ năng mới mà không cần quyền Admin:
- `GET /api/skill-contributions/check`: Kiểm tra xem đã có bản nháp nào đang dở dang cho kỹ năng hay chưa.
- `POST /api/skill-contributions`: Khởi tạo bản đóng góp kỹ năng mới.
- `GET /api/skill-contributions`: Danh sách các bản đóng góp của tôi.
- `GET /api/admin/skill-contributions`: Danh sách các đóng góp đang chờ Admin phê duyệt.
- `GET /api/skill-contributions/{id}`: Xem chi tiết bản đóng góp.
- `GET /api/skill-contributions/{id}/files`: Liệt kê các tệp tin trong bản đóng góp.
- `PUT /api/skill-contributions/{id}/files`: Tạo mới hoặc cập nhật nội dung tệp tin mã nguồn trực tiếp trên web.
- `DELETE /api/skill-contributions/{id}/files?path=...`: Xóa tệp tin khỏi gói đóng góp.
- `GET /api/skill-contributions/{id}/files/content?path=...`: Đọc nội dung tệp tin.
- `POST /api/skill-contributions/{id}/rename`: Đổi tên đường dẫn tệp.
- `POST /api/skill-contributions/{id}/upload`: Tải tệp tin riêng lẻ vào gói đóng góp.
- `POST /api/skill-contributions/{id}/submit`: Nộp bản đóng góp để ban quản trị review.
- `POST /api/skill-contributions/{id}/approve`: Duyệt và chính thức đóng gói thành kỹ năng của tổ chức.
- `POST /api/skill-contributions/{id}/reject`: Từ chối bản đóng góp.
- `POST /api/skill-contributions/{id}/request-changes`: Yêu cầu tác giả sửa đổi mã nguồn.
- `POST /api/skill-contributions/{id}/resubmit`: Nộp lại sau khi đã chỉnh sửa.
- `POST /api/skill-contributions/{id}/withdraw`: Rút lại đề xuất.
- `GET /api/skill-contributions/{id}/diff-status`: Xem so sánh thay đổi (diff) so với kỹ năng gốc.

---

## 9. Ghi chú Nhanh (Notes API)

Cho phép người dùng hoặc Agent lưu trữ nhanh các ý tưởng, trích đoạn văn bản, hoặc ghi chú cá nhân phục vụ công việc:
- `GET /api/notes`: Lấy danh sách các ghi chú của người dùng.
- `POST /api/notes`: Tạo ghi chú mới.
  - Body: `{"title": "Ý tưởng triển khai RAG", "content": "Cần tối ưu chunk size 512 tokens...", "note_type": "quick"}`
- `DELETE /api/notes/{note_id}`: Xóa ghi chú cá nhân.

---

## 10. Hệ thống Thông báo (Notifications API)

Hệ thống thông báo đẩy tới người dùng khi có sự kiện liên quan đến quy trình duyệt bài, tài liệu xử lý hoàn tất, hoặc có phản hồi đánh giá:
- `GET /api/notifications`: Lấy danh sách thông báo (hỗ trợ lọc `unread_only=true`, phân trang `limit`, `offset`).
- `GET /api/notifications/unread-count`: Đếm nhanh số lượng thông báo chưa đọc (đáp ứng badge thông báo trên UI).
- `POST /api/notifications/{notification_id}/read`: Đánh dấu một thông báo là đã đọc.
- `POST /api/notifications/read-all`: Đánh dấu toàn bộ thông báo là đã đọc.

---

## 11. Nhật ký Kiểm toán (Audit Logs API)

Lưu trữ vết kiểm toán bảo mật toàn bộ các thao tác trọng yếu (đăng nhập, truy cập dữ liệu nhạy cảm, phê duyệt bài viết, thay đổi cấu hình):
* **Endpoint:** `GET /api/audit/log`
* **Quyền yêu cầu:** `admin`

#### Query Parameters
- `action` *(optional, string)*: Tên hành động (ví dụ: `auth.login`, `wiki.page.delete`, `source.create`).
- `resource_type` *(optional, string)*: `source`, `wiki_page`, `employee`, `skill`.
- `principal_id` *(optional, UUID)*: ID người thực hiện hành vi.
- `decision` *(optional, string)*: `allow` hoặc `deny`.
- `page` *(optional, int, mặc định `1`)*.
- `page_size` *(optional, int, mặc định `50`)*.

---

## 12. Cấu hình Hệ thống & Quản lý Mô hình AI (Admin Settings & Models API)

Module dành cho Quản trị viên hệ thống để giám sát hạ tầng AI và chuyển đổi mô hình (LLM, Embeddings, Vision).

### 12.1. Cấu hình & Bảng điều khiển Quản trị
- `GET /api/dashboard/stats`: Lấy các số liệu tổng quan nhanh (tổng số tài liệu, phòng ban, nhân sự).
- `GET /api/settings`: Đọc toàn bộ cấu hình hệ thống hiện tại.
- `PUT /api/settings`: Lưu cập nhật cấu hình hệ thống.
- `GET /api/settings/providers`: Danh sách các nhà cung cấp AI đã được đăng ký và hỗ trợ (OpenAI, Anthropic, Google Gemini, Ollama, vLLM, Azure...).

---

### 12.2. Kiểm tra Kết nối AI Providers (Health Diagnostics)
- `POST /api/settings/test-providers`: Kiểm tra toàn diện kết nối tới tất cả các AI Providers đang kích hoạt.
- `POST /api/settings/test-embedding`: Kiểm tra khả năng tạo vector nhúng của mô hình Embedding.
- `POST /api/settings/test-llm`: Kiểm tra khả năng sinh nội dung và tốc độ của mô hình LLM.
- `POST /api/settings/test-vision`: Kiểm tra mô hình thị giác máy tính đọc tệp hình ảnh.

---

### 12.3. Quản lý & Chuyển đổi Mô hình Vector Embeddings
- `GET /api/settings/embeddings/catalog`: Xem danh mục các mô hình embedding hỗ trợ (kích thước chiều vector `dimension`, context length, provider).
- `GET /api/settings/embeddings/status`: Xem mô hình embedding đang vận hành và trạng thái index vector.
- `POST /api/settings/embeddings/switch`: Bắt đầu quy trình chuyển sang mô hình embedding mới. Thao tác này sẽ khởi chạy một background job để tự động tái tính toán vector (re-indexing) toàn bộ cơ sở tri thức.
- `GET /api/settings/embeddings/jobs/{job_id}`: Theo dõi tiến độ job re-indexing (số văn bản đã xử lý, tốc độ, ước tính thời gian còn lại).
- `POST /api/settings/embeddings/jobs/{job_id}/cancel`: Hủy tác vụ re-indexing đang chạy.

---

### 12.4. Quản lý & Chuyển đổi Mô hình LLM & Vision
- `GET /api/settings/llm/catalog`: Danh mục các mô hình ngôn ngữ lớn hỗ trợ.
- `POST /api/settings/llm/switch`: Đổi mô hình LLM mặc định cho các tác vụ tổng hợp Wiki và Chat.
- `GET /api/settings/vision/catalog`: Danh mục các mô hình Vision hỗ trợ.
- `POST /api/settings/vision/switch`: Đổi mô hình Vision dùng để bóc tách sơ đồ, hình ảnh từ tài liệu.

---

## 13. Báo cáo & Thống kê Quản trị (Admin Statistics & Analytics API)

Cung cấp báo cáo phân tích toàn diện phục vụ việc đo lường hiệu quả vận hành kho tri thức số của doanh nghiệp.

| Phương thức | Endpoint | Mô tả |
|---|---|---|
| `GET` | `/api/admin/stats/overview` | Tổng quan số lượng tài liệu, trang wiki, tỷ lệ hoàn tất pipeline |
| `GET` | `/api/admin/stats/content` | Phân tích dung lượng kho tri thức, phân bổ theo loại tri thức và phòng ban |
| `GET` | `/api/admin/stats/contribution` | Xếp hạng nhân viên đóng góp tài liệu và biên soạn bài viết |
| `GET` | `/api/admin/stats/usage` | Tần suất tìm kiếm, số lượng câu hỏi và công cụ AI được gọi |
| `GET` | `/api/admin/stats/gaps` | Thống kê các câu hỏi chưa có câu trả lời (Khoảng trống tri thức) |
| `GET` | `/api/admin/stats/export/{section}.csv` | Xuất file báo cáo dạng CSV cho mục `overview`, `content`, `contribution`, `usage`, hoặc `gaps` |
| `POST` | `/api/admin/stats/rollup` | Kích hoạt tổng hợp dữ liệu phân tích định kỳ ngay lập tức |

#### Query Parameters chung cho các API Thống kê
- `from` *(optional, string)*: Thời gian bắt đầu (ISO date: `YYYY-MM-DD`).
- `to` *(optional, string)*: Thời gian kết thúc (ISO date: `YYYY-MM-DD`).

---

## 14. Kiểm tra Trạng thái Hệ thống (Health Checks API)

### 14.1. Kiểm tra Nhanh
* **Endpoint:** `GET /health`
* **Response:**
```json
{
  "status": "healthy",
  "services": {
    "database": "healthy",
    "redis": "healthy",
    "minio": "healthy"
  }
}
```

### 14.2. Kiểm tra Chi tiết
* **Endpoint:** `GET /api/health`
* **Response:**
```json
{
  "api": "healthy",
  "database": "healthy",
  "worker": "healthy"
}
```

---

## 15. Mẫu Code Tích hợp Chi tiết (Integration Code Samples)

### 15.1. Python Client Example (Đồng bộ tài liệu & Tra cứu Wiki)

```python
import requests

BASE_URL = "https://api-arkon.anm05.com/api"

class ArkonClient:
    def __init__(self, email: str, password: str):
        self.session = requests.Session()
        self.login(email, password)

    def login(self, email: str, password: str):
        res = self.session.post(f"{BASE_URL}/auth/login", json={
            "email": email,
            "password": password
        })
        res.raise_for_status()
        token = res.json()["access_token"]
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        })
        print(f"Logged in successfully as {email}")

    def list_knowledge_types(self):
        res = self.session.get(f"{BASE_URL}/knowledge-types")
        res.raise_for_status()
        return res.json()

    def upload_document(self, file_path: str, title: str, knowledge_type_id: str = None):
        with open(file_path, "rb") as f:
            files = {"file": (file_path, f, "application/pdf")}
            data = {"title": title}
            if knowledge_type_id:
                data["knowledge_type_id"] = knowledge_type_id
            res = self.session.post(f"{BASE_URL}/sources/upload", files=files, data=data)
            res.raise_for_status()
            return res.json()

    def get_wiki_page(self, slug: str):
        res = self.session.get(f"{BASE_URL}/wiki/pages/{slug}")
        res.raise_for_status()
        return res.json()

if __name__ == "__main__":
    client = ArkonClient("admin@example.com", "YourPassword123")
    
    # 1. Lấy danh sách loại tri thức
    types = client.list_knowledge_types()
    print("Available types:", [t["name"] for t in types])

    # 2. Đọc bài viết Wiki
    page = client.get_wiki_page("kien-truc-he-thong-arkon")
    print(f"Title: {page['title']}")
    print(f"Content preview: {page['content_md'][:200]}...")
```

---

### 15.2. TypeScript / Node.js Integration Example (Axios)

```typescript
import axios, { AxiosInstance } from 'axios';
import * as fs from 'fs';
import FormData from 'form-data';

const BASE_URL = 'https://api-arkon.anm05.com/api';

export class ArkonAPI {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({ baseURL: BASE_URL });
  }

  async authenticate(email: string, password: string): Promise<void> {
    const res = await this.client.post('/auth/login', { email, password });
    const token = res.data.access_token;
    this.client.defaults.headers.common['Authorization'] = `Bearer ${token}`;
  }

  async listWikiPages(query?: string) {
    const res = await this.client.get('/wiki/pages', {
      params: { limit: 50, q: query }
    });
    return res.data;
  }

  async uploadFile(filePath: string, title: string, knowledgeTypeId?: string) {
    const form = new FormData();
    form.append('file', fs.createReadStream(filePath));
    form.append('title', title);
    if (knowledgeTypeId) {
      form.append('knowledge_type_id', knowledgeTypeId);
    }

    const res = await this.client.post('/sources/upload', form, {
      headers: form.getHeaders(),
    });
    return res.data;
  }
}
```

---

### 15.3. cURL Cheat Sheet (Tổng hợp Lệnh Nhanh)

```bash
# 1. Đăng nhập hệ thống lấy Access Token
TOKEN=$(curl -s -X POST "https://api-arkon.anm05.com/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "your_password"}' \
  | jq -r .access_token)

# 2. Kiểm tra tài khoản hiện tại
curl -s -X GET "https://api-arkon.anm05.com/api/auth/me" \
  -H "Authorization: Bearer $TOKEN"

# 3. Lấy danh sách phòng ban
curl -s -X GET "https://api-arkon.anm05.com/api/departments" \
  -H "Authorization: Bearer $TOKEN"

# 4. Upload tệp tài liệu PDF lên Arkon
curl -X POST "https://api-arkon.anm05.com/api/sources/upload" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/path/to/tai_lieu.pdf" \
  -F "title=Quy trình vận hành chuẩn 2026"

# 5. Đọc bài viết Wiki theo Slug
curl -s -X GET "https://api-arkon.anm05.com/api/wiki/pages/quy-trinh-van-hanh-chuan" \
  -H "Authorization: Bearer $TOKEN"

# 6. Lấy đồ thị liên kết tri thức (Knowledge Graph)
curl -s -X GET "https://api-arkon.anm05.com/api/wiki/graph" \
  -H "Authorization: Bearer $TOKEN"
```
