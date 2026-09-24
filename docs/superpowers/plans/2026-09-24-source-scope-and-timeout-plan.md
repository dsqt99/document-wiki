# Kế Hoạch Triển Khai: Hệ Thống Phạm Vi Hiển Thị & Triệt Tiêu Timeout Khi Chuyển Phạm Vi

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thống nhất cơ chế chọn phạm vi hiển thị tài liệu với 4 chế độ (Toàn hệ thống / Phòng ban / Workspace / Cán bộ cụ thể) và chuyển toàn bộ việc tháo gỡ Wiki / xóa vector sang Background Worker để triệt tiêu lỗi `Request timed out`.

**Architecture:** Mở rộng `ScopeType` (`global`, `department`, `project`, `user`), thêm bảng quan hệ `source_users`, cập nhật bộ lọc phân quyền RBAC và trích xuất Wiki scope. Tại endpoint `PATCH /api/sources/{id}`, toàn bộ quá trình `detach_source_from_wiki` và xóa vector được ủy thác cho ARQ task `reassign_source_scope_task`, trả về HTTP 200 ngay lập tức (<100ms). Frontend tái cấu trúc modal chỉnh sửa thành 1 selector trực quan với 4 chế độ động.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2.0 (Async), Alembic, ARQ / Redis, Next.js 14, TypeScript, Tailwind CSS / Shadcn UI.

---

### Task 1: Data Model & Migration (Bảng `source_users` & `ScopeType.USER`)

**Files:**
- Modify: `app/database/models.py:39-44`, `app/database/models.py:150-160`
- Create: `alembic/versions/add_source_users_table.py`
- Test: `tests/test_source_users_model.py`

- [ ] **Step 1: Viết test cho Model `SourceUser` và `ScopeType`**

```python
# tests/test_source_users_model.py
import pytest
from app.database.models import ScopeType, SourceUser, Source

def test_scope_type_enum():
    assert ScopeType.GLOBAL.value == "global"
    assert ScopeType.DEPARTMENT.value == "department"
    assert ScopeType.PROJECT.value == "project"
    assert ScopeType.USER.value == "user"

def test_source_user_repr():
    su = SourceUser()
    assert hasattr(su, "source_id")
    assert hasattr(su, "employee_id")
```

- [ ] **Step 2: Cập nhật `app/database/models.py`**
  - Cập nhật `ScopeType`:
    ```python
    class ScopeType(str, PyEnum):
        GLOBAL = "global"
        DEPARTMENT = "department"
        PROJECT = "project"
        USER = "user"
    ```
  - Khai báo model `SourceUser`:
    ```python
    class SourceUser(Base):
        __tablename__ = "source_users"
        id: Mapped[uuid.UUID] = mapped_column(
            UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
        )
        source_id: Mapped[uuid.UUID] = mapped_column(
            UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
        )
        employee_id: Mapped[uuid.UUID] = mapped_column(
            UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
        )
        created_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), server_default=func.now()
        )
        __table_args__ = (
            UniqueConstraint("source_id", "employee_id", name="uq_source_user"),
        )
        source: Mapped["Source"] = relationship(back_populates="users")
        employee: Mapped["Employee"] = relationship()
    ```
  - Trong model `Source`, thêm relationship `users`:
    ```python
    users: Mapped[list["SourceUser"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )
    ```

- [ ] **Step 3: Tạo migration Alembic cho bảng `source_users`**
  - Tạo file migration tạo bảng `source_users` với khóa ngoại cascade tới `sources(id)` và `employees(id)`.

- [ ] **Step 4: Chạy test kiểm tra Model**
  - Run: `pytest tests/test_source_users_model.py -v`
  - Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add app/database/models.py alembic/versions/* tests/test_source_users_model.py
  git commit -m "feat(db): add source_users table and extend ScopeType with user and project"
  ```

---

### Task 2: Pydantic Schemas (`app/schemas/sources.py`)

**Files:**
- Modify: `app/schemas/sources.py`
- Test: `tests/test_source_schemas.py`

- [ ] **Step 1: Viết test cho Schemas**

```python
# tests/test_source_schemas.py
import uuid
from app.schemas.sources import SourceUpdate, SourceResponse

def test_source_update_employee_ids():
    uid = uuid.uuid4()
    update = SourceUpdate(employee_ids=[uid])
    assert update.employee_ids == [uid]
```

- [ ] **Step 2: Thêm `employee_ids` vào `SourceCreate`, `SourceUpdate`, `SourceResponse`**
  - Trong `SourceCreate`: `employee_ids: Optional[list[uuid.UUID]] = None`
  - Trong `SourceUpdate`: `employee_ids: Optional[list[uuid.UUID]] = None`
  - Trong `SourceResponse`: `employee_ids: list[uuid.UUID] = Field(default_factory=list)`

- [ ] **Step 3: Chạy test schemas**
  - Run: `pytest tests/test_source_schemas.py -v`
  - Expected: PASS

- [ ] **Step 4: Commit**
  ```bash
  git add app/schemas/sources.py tests/test_source_schemas.py
  git commit -m "feat(schemas): add employee_ids to Source schemas"
  ```

---

### Task 3: Background Worker Async Detach Task (`app/worker.py`)

**Files:**
- Modify: `app/worker.py`
- Test: `tests/test_reassign_worker.py`

- [ ] **Step 1: Viết test cho worker task `reassign_source_scope_task`**
- [ ] **Step 2: Định nghĩa hàm `reassign_source_scope_task` trong `app/worker.py`**
  ```python
  async def reassign_source_scope_task(
      ctx: dict,
      source_id_str: str,
      old_scopes: list[tuple[str, Optional[str]]],
  ) -> None:
      """
      Chạy ngầm trong background worker:
      1. Tháo gỡ source khỏi các trang wiki cũ và xóa cascade các trang phụ thuộc.
      2. Tái tạo _index cho các scope cũ.
      3. Đẩy tiếp ingest_map_reduce_task để biên soạn vào phạm vi mới.
      """
  ```
- [ ] **Step 3: Đăng ký `reassign_source_scope_task` vào danh sách hàm ARQ trong `WorkerSettings`**
- [ ] **Step 4: Chạy test worker task**
  - Expected: PASS
- [ ] **Step 5: Commit**
  ```bash
  git add app/worker.py tests/test_reassign_worker.py
  git commit -m "feat(worker): add reassign_source_scope_task for async detach and re-indexing"
  ```

---

### Task 4: API Endpoint & Phân Quyền Truy Cập (`app/routers/sources.py`)

**Files:**
- Modify: `app/routers/sources.py`
- Test: `tests/test_sources_scope_api.py`

- [ ] **Step 1: Viết test cho `PATCH /sources/{id}` và phân quyền lọc `GET /sources`**
  - Test đổi scope sang `user` với danh sách `employee_ids`.
  - Test response phản hồi ngay lập tức và status chuyển sang `processing`.
  - Test user B không xem được tài liệu có scope `user` gán cho user A.
- [ ] **Step 2: Cập nhật hàm `_to_response` và `_source_load_options`**
  - Load `Source.users` (selectinload).
  - Trả về `employee_ids = [u.employee_id for u in source.users]`.
- [ ] **Step 3: Cập nhật `PATCH /sources/{source_id}`**
  - Xóa bỏ việc gọi `wiki_service.detach_source_from_wiki` và `regenerate_index` đồng bộ.
  - Khi `scope_type`, `department_ids`, hoặc `employee_ids` thay đổi trên tài liệu `status == "ready"`:
    - Lưu các bảng liên kết `source_departments`, `source_users`.
    - Đặt `source.status = "processing"`, `source.progress = 0`, `source.progress_message = "Re-queued scope reassignment..."`.
    - Enqueue `reassign_source_scope_task` vào ARQ pool.
    - Commit và trả về response ngay lập tức.
  - Cho phép người dùng cập nhật phạm vi ngay cả khi tài liệu đang `processing`/`pending`.
- [ ] **Step 4: Cập nhật bộ lọc truy cập trong `GET /sources`**
  - Kiểm tra `scope_type == "user"`: cán bộ chỉ thấy tài liệu nếu ID của họ có trong `source_users` hoặc họ là người tải lên (`contributed_by_employee_id`) hoặc có quyền admin/`doc:edit:all`.
- [ ] **Step 5: Chạy test API**
  - Run: `pytest tests/test_sources_scope_api.py -v`
  - Expected: PASS
- [ ] **Step 6: Commit**
  ```bash
  git add app/routers/sources.py tests/test_sources_scope_api.py
  git commit -m "feat(api): async scope reassignment on PATCH /sources and user scope RBAC filter"
  ```

---

### Task 5: Pipeline Wiki Scope Resolution (`app/ai/mrp/pipeline.py`)

**Files:**
- Modify: `app/ai/mrp/pipeline.py:30-60`
- Test: `tests/test_resolve_wiki_scopes.py`

- [ ] **Step 1: Viết test cho `_resolve_wiki_scopes`**
  - Test khi `scope_type == "user"` trả về danh sách scopes tương ứng với từng `employee_id`.
- [ ] **Step 2: Cập nhật `_resolve_wiki_scopes`**
  - Xử lý nhánh `if scope_type == "user"`: lấy các `employee_id` từ `source_users` và trả về `[("user", uid) for uid in user_ids]`.
- [ ] **Step 3: Chạy test pipeline scope**
  - Run: `pytest tests/test_resolve_wiki_scopes.py -v`
  - Expected: PASS
- [ ] **Step 4: Commit**
  ```bash
  git add app/ai/mrp/pipeline.py tests/test_resolve_wiki_scopes.py
  git commit -m "feat(pipeline): support user scope resolution in MRP pipeline commit phase"
  ```

---

### Task 6: Frontend API, Types & i18n

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/components/knowledge/knowledge-table/types.ts`
- Modify: `frontend/src/lib/i18n.tsx`

- [ ] **Step 1: Tăng `REQUEST_TIMEOUT_MS` trong `frontend/src/lib/api.ts` từ 30s lên 60s**
- [ ] **Step 2: Bổ sung `employee_ids?: string[]` vào type `Source` trong `types.ts`**
- [ ] **Step 3: Bổ sung từ điển đa ngôn ngữ trong `frontend/src/lib/i18n.tsx`**:
  - `knowledge.scope.global`: "Toàn hệ thống" / "Global"
  - `knowledge.scope.department`: "Theo phòng ban" / "Department"
  - `knowledge.scope.project`: "Theo Workspace" / "Workspace"
  - `knowledge.scope.user`: "Riêng tư theo Cán bộ" / "Specific Users"
  - `knowledge.scope.usersLabel`: "Cán bộ được cấp quyền" / "Authorized Personnel"
  - `knowledge.edit.scopeChangeConfirm`: "Thay đổi phạm vi hiển thị sẽ chạy lại quá trình biên soạn AI. Bạn có muốn tiếp tục?" / "Changing visibility scope will rerun AI compilation. Continue?"
- [ ] **Step 4: Commit**
  ```bash
  git add frontend/src/lib/api.ts frontend/src/components/knowledge/knowledge-table/types.ts frontend/src/lib/i18n.tsx
  git commit -m "feat(frontend): increase client timeout, update types and i18n for 4-mode scope"
  ```

---

### Task 7: Frontend EditSourceDialog Redesign (`edit-source-dialog.tsx`)

**Files:**
- Modify: `frontend/src/components/knowledge/knowledge-table/edit-source-dialog.tsx`

- [ ] **Step 1: Tải danh sách cán bộ (`employees`) khi mở dialog qua `/api/employees`**
- [ ] **Step 2: Tái cấu trúc giao diện thành 1 selector "Phạm vi hiển thị" thống nhất**:
  - Dropdown 4 lựa chọn:
    1. 🌐 Toàn hệ thống (`global`)
    2. 🏢 Theo phòng ban (`department`)
    3. 📁 Theo Workspace (`project`)
    4. 👤 Riêng tư theo Cán bộ (`user`)
  - Khi chọn `department`: hiển thị bảng checkbox chọn phòng ban.
  - Khi chọn `project`: hiển thị dropdown chọn Workspace.
  - Khi chọn `user`: hiển thị danh sách cán bộ có tìm kiếm và multi-select badge tags.
- [ ] **Step 3: Bỏ khóa `disabled={inFlight}` trên các bộ chọn phạm vi**
- [ ] **Step 4: Sửa hộp thoại xác nhận dùng đúng key `knowledge.edit.scopeChangeConfirm`**
- [ ] **Step 5: Gửi đúng payload `scope_type`, `scope_id`, `department_ids`, `employee_ids` khi bấm Lưu**
- [ ] **Step 6: Build/lint kiểm tra frontend**:
  - Run: `npm run lint` hoặc `npm run build` trong `frontend`
- [ ] **Step 7: Commit**
  ```bash
  git add frontend/src/components/knowledge/knowledge-table/edit-source-dialog.tsx
  git commit -m "feat(ui): redesign edit source dialog with unified 4-mode scope selector"
  ```

---

### Task 8: Verification & E2E Validation

- [ ] **Step 1: Test chỉnh sửa tài liệu lớn từ Global -> Department / User**:
  - Xác nhận API trả về trong <200ms, không còn báo đỏ `Request timed out`.
- [ ] **Step 2: Test hộp thoại xác nhận**:
  - Kiểm tra text tiếng Việt hiển thị chính xác.
- [ ] **Step 3: Test chuyển sang User**:
  - Chọn các cán bộ cụ thể và lưu thành công.
- [ ] **Step 4: Commit và tổng kết**
