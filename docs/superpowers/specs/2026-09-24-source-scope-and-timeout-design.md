# Thiết Kế: Hệ Thống Phạm Vi Hiển Thị (Scope) Hỗ Trợ Phân Quyền Cán Bộ (User) & Tối Ưu Hóa Timeout

- **Ngày tạo:** 2026-09-24
- **Trạng thái:** Proposed

---

## 1. Bối cảnh & Vấn đề (Context & Problem Statement)

### 1.1. Lỗi `Request timed out` khi chuyển đổi phòng ban/phạm vi
- Khi người dùng thay đổi phòng ban trên một tài liệu đã biên soạn xong (`status == "ready"`), endpoint `PATCH /api/sources/{source_id}` thực hiện toàn bộ việc tháo gỡ tài liệu (`detach_source_from_wiki`), xoá các trang wiki liên quan (`delete_page_cascade`), xoá vector embeddings (pgvector và Milvus), và tạo lại `_index` một cách **đồng bộ (synchronous)** trong request HTTP.
- Với các tài liệu lớn (như các văn bản luật pháp có hàng chục trang và hàng trăm chunk embeddings), tác vụ này tốn hơn 30 giây.
- Phía frontend (`frontend/src/lib/api.ts`) quy định `REQUEST_TIMEOUT_MS = 30_000` (30 giây), dẫn đến việc request bị ngắt kết nối và giao diện báo lỗi đỏ `Request timed out`.

### 1.2. Mâu thuẫn và bất cập trong giao diện chọn phạm vi
- Modal "Chỉnh sửa tài liệu" hiện chia làm 2 trường độc lập: **"Phòng ban"** (danh sách checkbox chọn nhiều phòng ban) và **"Phạm vi hiển thị"** (Dropdown gồm "Toàn Hệ Thống" và "Workspace").
- Việc chia tách này gây mâu thuẫn: người dùng vừa chọn "Toàn hệ thống" vừa tick phòng ban "PC08", khiến logic pipeline ưu tiên phòng ban và tài liệu không còn mang tính toàn hệ thống như người dùng lầm tưởng.
- Hệ thống chưa hỗ trợ chia sẻ riêng tư theo từng cán bộ cụ thể (**User/Employee**).
- Khi tài liệu đang trong quá trình xử lý (`inFlight`), modal khóa cứng toàn bộ việc chọn phòng ban và phạm vi hiển thị.
- Hộp thoại xác nhận biên soạn lại dùng sai key đa ngôn ngữ (`knowledge.edit.inFlight`) khiến người dùng thấy thông báo không đúng ngữ cảnh.

---

## 2. Mục tiêu (Goals & Non-Goals)

### Mục tiêu (Goals)
1. **Dứt điểm lỗi timeout:** Chuyển toàn bộ tác vụ dọn dẹp wiki cũ, xóa vector embeddings và tái tạo mục lục sang Background Worker (ARQ job). API `PATCH /api/sources/{id}` phản hồi ngay lập tức (`< 100ms`).
2. **Gộp chung 1 trường "Phạm vi hiển thị":** Thay thế 2 mục riêng rẽ thành 1 trường đồng nhất với 4 chế độ:
   - `Toàn hệ thống (Global)`: Mọi nhân sự đều có quyền xem.
   - `Theo phòng ban (Department)`: Chọn 1 hoặc nhiều phòng ban được cấp quyền.
   - `Theo Workspace (Project)`: Chọn 1 Workspace cụ thể.
   - `Riêng tư theo Cán bộ (User)`: Chọn 1 hoặc nhiều cán bộ/user cụ thể được cấp quyền xem (cùng với Admin).
3. **Mô hình dữ liệu hỗ trợ User Scope:** Tạo bảng quan hệ `source_users` và mở rộng `ScopeType` với giá trị `USER = "user"`.
4. **Mở khóa linh hoạt:** Cho phép điều chỉnh phạm vi hiển thị bất cứ lúc nào, worker luôn áp dụng phạm vi mới nhất khi commit.
5. **Khắc phục UI bug:** Sửa đúng nội dung thông báo xác nhận biên soạn lại và nâng timeout phía client.

### Ngoài phạm vi (Non-Goals)
- Không thay đổi thuật toán trích xuất hay cấu trúc prompt của pipeline Map-Reduce-Pipeline (MRP).
- Không can thiệp vào các quyền hệ thống khác (chỉ áp dụng cho quyền truy cập tài liệu và wiki).

---

## 3. Kiến trúc Chi Tiết (Detailed Architecture)

### 3.1. Mô hình dữ liệu (Database Schema)

#### Bảng `source_users`
Tương tự bảng `source_departments`, lưu danh sách các user được cấp quyền truy cập tài liệu khi chọn chế độ `user`:
```sql
CREATE TABLE source_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT uq_source_user UNIQUE (source_id, employee_id)
);
CREATE INDEX ix_source_users_source_id ON source_users(source_id);
CREATE INDEX ix_source_users_employee_id ON source_users(employee_id);
```

#### Cập nhật `ScopeType`
```python
class ScopeType(str, PyEnum):
    GLOBAL = "global"
    DEPARTMENT = "department"
    PROJECT = "project"
    USER = "user"
```

#### Cập nhật Model `Source`
- Bổ sung relationship `users`:
  ```python
  users: Mapped[list["SourceUser"]] = relationship(
      back_populates="source", cascade="all, delete-orphan"
  )
  ```

---

### 3.2. Background Worker hóa Thao Tác Chuyển Phạm Vi (Giải quyết Timeout)

#### Luồng xử lý khi người dùng đổi phạm vi trên tài liệu đã `ready`:
1. `PATCH /api/sources/{source_id}` nhận payload mới:
   - Cập nhật `scope_type`, `scope_id`, `department_ids`, `employee_ids`.
   - Nếu phạm vi thay đổi:
     - Ghi nhận trạng thái `source.status = "processing"`, `progress = 0`, `progress_message = "Đang chuyển đổi phạm vi hiển thị và dọn dẹp wiki cũ..."`.
     - Đẩy job vào Redis queue:
       ```python
       await pool.enqueue_job("reassign_source_scope_task", str(source_id), old_scopes)
       ```
     - Commit DB và trả về HTTP 200 ngay lập tức cho client.
2. Background Worker thực thi `reassign_source_scope_task`:
   - Bước 1: Gọi `detach_source_from_wiki(db, source_id)` và `delete_page_cascade` ngầm trong worker.
   - Bước 2: Tái tạo lại mục lục `regenerate_index` cho các scope cũ.
   - Bước 3: Đẩy tiếp job `ingest_map_reduce_task` để biên soạn tài liệu vào phạm vi mới.

Nhờ vậy, request HTTP chỉ thực hiện 1 câu lệnh UPDATE đơn giản trong DB, hoàn tất chỉ trong khoảng **20ms - 50ms**, loại bỏ 100% rủi ro timeout.

---

### 3.3. Phân quyền và Lọc tài liệu (Access Control & RBAC)

Trong `app/routers/sources.py`, logic lọc danh sách tài liệu (`get_sources`, `search_sources`, `get_source`) được cập nhật:
- **Admin** (`role == "admin"` hoặc có quyền `doc:edit:all`): Xem được toàn bộ tài liệu.
- **Cán bộ thường**: Chỉ xem được tài liệu thỏa mãn một trong các điều kiện:
  1. `scope_type == "global"`
  2. `scope_type == "department"` VÀ `department_id IN (user.department_ids)`
  3. `scope_type == "project"` VÀ `scope_id IN (user.project_ids)`
  4. `scope_type == "user"` VÀ (`employee_id == user.id` HOẶC `contributed_by_employee_id == user.id`)

---

### 3.4. Thiết Kế Giao Diện Frontend (UI/UX)

#### Trong `edit-source-dialog.tsx`:
1. **Trường "Phạm vi hiển thị":**
   - Single Select gồm 4 options có icon nhận diện rõ ràng:
     - 🌐 **Toàn hệ thống** (Tất cả nhân sự)
     - 🏢 **Theo phòng ban** (Chỉ các phòng ban được chọn)
     - 📁 **Theo Workspace** (Chỉ nhân sự trong Workspace)
     - 👤 **Riêng tư theo Cán bộ** (Chỉ các cán bộ được chỉ định)
2. **Khu vực chọn đối tượng động:**
   - Khi chọn **Theo phòng ban**: Hiển thị bảng chọn checkbox các phòng ban (Department multi-select).
   - Khi chọn **Theo Workspace**: Hiển thị dropdown chọn Workspace (Project single-select).
   - Khi chọn **Riêng tư theo Cán bộ**: Hiển thị danh sách cán bộ nhân sự (Employee multi-select với ô tìm kiếm tên/email).
3. **Mở khóa khi đang xử lý:** Bỏ `disabled={inFlight}` trên các trường phạm vi.
4. **Sửa lỗi hiển thị Confirm Dialog:**
   - Thay key `knowledge.edit.inFlight` bằng key đúng `knowledge.edit.scopeChangeConfirm`:
     *"Thay đổi phạm vi hiển thị sẽ kích hoạt hệ thống biên soạn lại tri thức. Bạn có muốn tiếp tục?"*
5. **Timeout Client:** Trong `frontend/src/lib/api.ts`, tăng `REQUEST_TIMEOUT_MS = 60_000` (60s) để đảm bảo độ tin cậy kết nối mạng.

---

## 4. Kế hoạch Kiểm Thử (Testing Plan)

1. **Unit & API Test:**
   - Test cập nhật `PATCH /api/sources/{id}` với `scope_type="user"` và danh sách `employee_ids`.
   - Kiểm tra API phản hồi nhanh `< 100ms` khi chuyển phạm vi trên tài liệu lớn.
   - Test phân quyền: user A không thể truy cập tài liệu gán cho user B.
2. **Worker Integration Test:**
   - Kiểm tra worker tháo gỡ thành công các trang wiki cũ và vector embeddings khi chạy ngầm.
3. **E2E UI Test:**
   - Thao tác chuyển đổi giữa 4 chế độ phạm vi trên modal, kiểm tra dữ liệu lưu chuẩn xác và thông báo hiển thị đúng tiếng Việt.
