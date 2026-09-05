# Arkon Backend REST API Integration Guide

Tài liệu hướng dẫn sử dụng REST API của **Arkon** dành cho việc tích hợp với các dịch vụ khác (microservices, ứng dụng nội bộ, hệ thống bên ngoài).

---

## 1. Tổng quan (Overview)

- **Production Base URL:** `https://api-arkon.anm05.com/api`
- **Local/Dev Base URL:** `http://localhost:8000/api`
- **Swagger / OpenAPI Documentation:** `https://api-arkon.anm05.com/docs` (hoặc `http://localhost:8000/docs`)
- **OpenAPI Schema File:** [`docs/api.json`](file:///home/cahy/code/arkon/docs/api.json)
- **Định dạng dữ liệu:** `application/json` (Ngoại trừ API upload tệp tin sử dụng `multipart/form-data`).

---

## 2. Xác thực & Phân quyền (Authentication & Authorization)

Arkon sử dụng **JSON Web Token (JWT)** để xác thực tất cả các yêu cầu REST API.

### 2.1. Đăng nhập lấy Token

* **Endpoint:** `POST /api/auth/login`
* **Full URL:** `https://api-arkon.anm05.com/api/auth/login`
* **Content-Type:** `application/json`

#### cURL Example
```bash
curl -X 'POST' \
  'https://api-arkon.anm05.com/api/auth/login' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "email": "haimanhdo1999@gmail.com",
  "password": "your_password"
}'
```

#### Request Body
```json
{
  "email": "haimanhdo1999@gmail.com",
  "password": "your_password"
}
```

#### Response (200 OK)
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Admin",
    "email": "admin@example.com",
    "role": "admin",
    "department_ids": ["8f1103c8-1234-5678-9abc-def012345678"],
    "department_names": ["Administration"],
    "permissions": ["*"]
  }
}
```

### 2.2. Gửi Token trong các Request tiếp theo

Trong tất cả các API phía dưới, hãy thêm Header:
```http
Authorization: Bearer <access_token>
```

### 2.3. Lấy thông tin tài khoản hiện tại

* **Endpoint:** `GET /api/auth/me`
* **Header:** `Authorization: Bearer <access_token>`

---

## 3. Quản lý Phòng ban & Nhân sự (Departments & Employees API)

### 3.1. Danh sách Phòng ban

* **Endpoint:** `GET /api/departments`
* **Permission required:** `org:departments:read` (hoặc role `admin`)

#### Response Example
```json
[
  {
    "id": "8f1103c8-1234-5678-9abc-def012345678",
    "name": "Kỹ thuật (Engineering)",
    "description": "Phòng phát triển phần mềm & hạ tầng",
    "employee_count": 12
  },
  {
    "id": "7a9901b2-8888-4444-9999-111122223333",
    "name": "Nhân sự (HR)",
    "description": "Phòng quản trị nhân sự & chính sách",
    "employee_count": 5
  }
]
```

### 3.2. Tạo Phòng ban mới

* **Endpoint:** `POST /api/departments`
* **Permission required:** `org:departments:manage`

#### Request Body
```json
{
  "name": "Kế toán & Tài chính",
  "description": "Quản lý doanh thu, chi phí và ngân sách"
}
```

#### Response (201 Created)
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "name": "Kế toán & Tài chính"
}
```

### 3.3. Cập nhật / Xóa Phòng ban

* **Cập nhật:** `PUT /api/departments/{dept_id}` (Body giống như `POST /api/departments`)
* **Xóa:** `DELETE /api/departments/{dept_id}`

---

### 3.4. Danh sách Nhân sự (Employees)

* **Endpoint:** `GET /api/employees`
* **Query Parameters:**
  - `department_id` *(optional, UUID)*: Lọc nhân sự theo phòng ban
  - `search` *(optional, string)*: Tìm kiếm theo tên hoặc email
  - `page` *(optional, int, mặc định 1)*
  - `page_size` *(optional, int, mặc định 20)*

#### Response Example
```json
{
  "items": [
    {
      "id": "e8888888-4444-4444-8888-1234567890ab",
      "name": "Nguyen Van A",
      "email": "nva@company.com",
      "role": "employee",
      "global_role": "contributor",
      "department_ids": ["8f1103c8-1234-5678-9abc-def012345678"],
      "department_names": ["Kỹ thuật (Engineering)"],
      "is_active": true,
      "has_token": false,
      "last_connected": null
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

### 3.5. Tạo Nhân sự mới

* **Endpoint:** `POST /api/employees`

#### Request Body
```json
{
  "name": "Nguyen Van B",
  "email": "nvb@company.com",
  "password": "SecurePassword123!",
  "role": "employee",
  "global_role": "contributor",
  "department_ids": ["8f1103c8-1234-5678-9abc-def012345678"]
}
```

---

## 4. Quản lý Loại Tri thức (Knowledge Types API)

Loại tri thức (Knowledge Type) giúp phân loại tài liệu thành các chuyên mục như **SOP, Quy trình, Hướng dẫn, Báo cáo, Tài liệu kỹ thuật**.

### 4.1. Danh sách Loại Tri thức

* **Endpoint:** `GET /api/knowledge-types`

#### Response Example
```json
[
  {
    "id": "11111111-2222-3333-4444-555555555555",
    "slug": "sop",
    "name": "Quy trình SOP",
    "color": "#6366f1",
    "description": "Standard Operating Procedures",
    "sort_order": 1,
    "source_count": 8
  },
  {
    "id": "22222222-3333-4444-5555-666666666666",
    "slug": "tech-spec",
    "name": "Tài liệu Kỹ thuật",
    "color": "#10b981",
    "description": "Kiến trúc hệ thống, API Docs & Database Spec",
    "sort_order": 2,
    "source_count": 15
  }
]
```

### 4.2. Tạo Loại Tri thức mới

* **Endpoint:** `POST /api/knowledge-types`
* **Permission required:** `documents.create`

#### Request Body
```json
{
  "name": "Chính sách HR",
  "slug": "hr-policy",
  "color": "#ec4899",
  "description": "Chính sách đãi ngộ, nghỉ phép và quy định công ty"
}
```

### 4.3. Cập nhật & Xóa Loại Tri thức

* **Cập nhật:** `PUT /api/knowledge-types/{kt_id}`
* **Xóa:** `DELETE /api/knowledge-types/{kt_id}`

---

## 5. Tài liệu Tri thức (Knowledge Documents / Sources API)

Tài liệu tri thức (Source) là tệp gốc (PDF, DOCX, TXT, URL) được tải lên Arkon để chạy qua **MRP Ingestion Pipeline** và biên soạn thành Wiki.

### 5.1. Lấy danh sách Tài liệu Tri thức

* **Endpoint:** `GET /api/sources`
* **Query Parameters:**
  - `knowledge_type_id` *(optional, UUID)*: Lọc theo loại tri thức
  - `department_id` *(optional, UUID)*: Lọc theo phòng ban
  - `status` *(optional, string)*: `pending`, `processing`, `completed`, `failed`
  - `search` *(optional, string)*: Tìm kiếm theo tiêu đề hoặc tên file
  - `page` *(optional, int, mặc định 1)*
  - `page_size` *(optional, int, mặc định 20)*

#### Response Example
```json
{
  "items": [
    {
      "id": "33333333-4444-5555-6666-777777777777",
      "title": "Hướng dẫn sử dụng hệ thống CRM v2.0.pdf",
      "source_type": "file",
      "file_name": "crm_guide_v2.pdf",
      "file_size": 2048576,
      "status": "completed",
      "progress": 100,
      "progress_message": "Ingestion completed",
      "page_count": 15,
      "wiki_page_count": 4,
      "knowledge_type_id": "11111111-2222-3333-4444-555555555555",
      "knowledge_type_name": "Quy trình SOP",
      "department_ids": ["8f1103c8-1234-5678-9abc-def012345678"],
      "department_names": ["Kỹ thuật (Engineering)"],
      "created_at": "2026-08-10T14:30:00Z",
      "updated_at": "2026-08-10T14:32:15Z"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

---

### 5.2. Xem Chi tiết Tài liệu (Gồm text trích xuất & download link)

* **Endpoint:** `GET /api/sources/{source_id}`

#### Response Example
```json
{
  "id": "33333333-4444-5555-6666-777777777777",
  "title": "Hướng dẫn sử dụng hệ thống CRM v2.0.pdf",
  "status": "completed",
  "full_text": "...[Nội dung văn bản trích xuất từ PDF]...",
  "outline": [
    {"title": "Chương 1: Tổng quan", "page": 1},
    {"title": "Chương 2: Đăng nhập & Phân quyền", "page": 4}
  ],
  "download_url": "http://localhost:9000/arkon-sources/crm_guide_v2.pdf?X-Amz-Signature=..."
}
```

---

### 5.3. Tải lên Tài liệu Tri thức mới (File Upload)

Dịch vụ khác có thể đẩy tệp tài liệu trực tiếp vào Arkon thông qua API này.

* **Endpoint:** `POST /api/sources/upload`
* **Content-Type:** `multipart/form-data`

#### Form Fields
- `file` *(Required, Binary File)*: Tệp đính kèm (PDF, DOCX, DOC, TXT, MD)
- `title` *(Optional, string)*: Tiêu đề tài liệu
- `knowledge_type_id` *(Optional, UUID)*: ID của Loại tri thức
- `department_ids` *(Optional, list of UUIDs, truyền nhiều lần hoặc định dạng JSON/comma-separated)*: Danh sách ID phòng ban áp dụng
- `preserve_verbatim` *(Optional, boolean, mặc định false)*: Giữ nguyên văn bản khi tổng hợp Wiki

#### Response (200 OK)
```json
{
  "id": "33333333-4444-5555-6666-777777777777",
  "title": "Quy trinh Onboarding 2026.pdf",
  "status": "pending",
  "progress": 0,
  "progress_message": "Queued for processing"
}
```

---

### 5.4. Thêm Tài liệu từ Liên kết Web (URL)

* **Endpoint:** `POST /api/sources/url`
* **Content-Type:** `application/json`

#### Request Body
```json
{
  "url": "https://docs.company.com/architecture-guide",
  "title": "Hướng dẫn Kiến trúc Hệ thống",
  "knowledge_type_id": "22222222-3333-4444-5555-666666666666",
  "department_ids": ["8f1103c8-1234-5678-9abc-def012345678"]
}
```

---

### 5.5. Cập nhật / Xóa / Retry Tài liệu

* **Cập nhật Metadata:** `PUT /api/sources/{source_id}`
* **Xóa tài liệu:** `DELETE /api/sources/{source_id}`
* **Thử lại khi lỗi Ingestion:** `POST /api/sources/{source_id}/retry`

---

## 6. Tra cứu & Đọc Wiki Tri thức (Wiki Knowledge API)

Sau khi tài liệu tri thức được xử lý, Arkon sẽ tự động tổng hợp thành các trang Wiki liên kết với nhau. Các service khác có thể truy vấn các bài viết này.

### 6.1. Tìm kiếm & Danh sách Trang Wiki

* **Endpoint:** `GET /api/wiki`
* **Query Parameters:**
  - `q` *(optional, string)*: Từ khóa tìm kiếm (full-text & semantic)
  - `knowledge_type` *(optional, string)*: Lọc theo slug của Knowledge Type
  - `limit` *(optional, int, mặc định 20)*
  - `offset` *(optional, int, mặc định 0)*

---

### 6.2. Đọc Bài viết Wiki theo Slug

* **Endpoint:** `GET /api/wiki/{slug}`

#### Response Example
```json
{
  "slug": "quy-trinh-onboarding-nhan-vien-moi",
  "title": "Quy trình Onboarding Nhân viên mới",
  "page_type": "process",
  "summary": "Hướng dẫn chi tiết các bước chuẩn bị tài khoản và bàn giao thiết bị cho nhân sự mới",
  "content_md": "# Quy trình Onboarding\n\n## 1. Chuẩn bị tài khoản\n- Tạo email công ty...\n",
  "backlinks": ["chinh-sach-nhan-su"],
  "outlinks": ["danh-sach-thiet-bi-it"],
  "source_ids": ["33333333-4444-5555-6666-777777777777"],
  "version": 2,
  "updated_at": "2026-08-12T10:00:00Z"
}
```

---

## 7. Ví dụ Tích hợp (Code Examples for External Services)

### 7.1. Python Integration Example (`httpx` / `requests`)

```python
import requests

BASE_URL = "https://api-arkon.anm05.com/api"

# Step 1: Login to get Bearer Token
login_res = requests.post(f"{BASE_URL}/auth/login", json={
    "email": "haimanhdo1999@gmail.com",
    "password": "your_password"
})
token = login_res.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Step 2: Get List of Departments
dept_res = requests.get(f"{BASE_URL}/departments", headers=headers)
departments = dept_res.json()
print("Departments:", departments)

# Step 3: Get List of Knowledge Types
kt_res = requests.get(f"{BASE_URL}/knowledge-types", headers=headers)
knowledge_types = kt_res.json()
print("Knowledge Types:", knowledge_types)

# Step 4: Upload a new Knowledge Document
with open("ban_huong_dan.pdf", "rb") as f:
    files = {"file": ("ban_huong_dan.pdf", f, "application/pdf")}
    data = {
        "title": "Bản Hướng Dẫn Kỹ Thuật 2026",
        "knowledge_type_id": knowledge_types[0]["id"]
    }
    upload_res = requests.post(f"{BASE_URL}/sources/upload", headers=headers, files=files, data=data)
    print("Upload result:", upload_res.json())
```

---

### 7.2. JavaScript / TypeScript Integration Example (`fetch` / `axios`)

```typescript
import axios from 'axios';

const BASE_URL = 'https://api-arkon.anm05.com/api';

async function syncKnowledgeData() {
  // 1. Login
  const loginRes = await axios.post(`${BASE_URL}/auth/login`, {
    email: 'haimanhdo1999@gmail.com',
    password: 'your_password'
  });
  const token = loginRes.data.access_token;
  const client = axios.create({
    baseURL: BASE_URL,
    headers: { Authorization: `Bearer ${token}` }
  });

  // 2. Fetch Knowledge Types & Departments
  const [deptsRes, typesRes, sourcesRes] = await Promise.all([
    client.get('/departments'),
    client.get('/knowledge-types'),
    client.get('/sources?page_size=50')
  ]);

  console.log('Departments:', deptsRes.data);
  console.log('Knowledge Types:', typesRes.data);
  console.log('Documents:', sourcesRes.data.items);
}

syncKnowledgeData();
```

---

### 7.3. cURL Quick Reference

```bash
# 1. Đăng nhập
curl -X 'POST' \
  'https://api-arkon.anm05.com/api/auth/login' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "email": "haimanhdo1999@gmail.com",
  "password": "your_password"
}'

# 2. Lấy danh sách phòng ban
curl -X GET "https://api-arkon.anm05.com/api/departments" \
     -H "Authorization: Bearer <YOUR_TOKEN>"

# 3. Lấy danh sách Knowledge Types
curl -X GET "https://api-arkon.anm05.com/api/knowledge-types" \
     -H "Authorization: Bearer <YOUR_TOKEN>"

# 4. Lấy danh sách Tài liệu tri thức
curl -X GET "https://api-arkon.anm05.com/api/sources?page=1&page_size=10" \
     -H "Authorization: Bearer <YOUR_TOKEN>"
```
