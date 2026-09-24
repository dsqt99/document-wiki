# Kế Hoạch Triển Khai: Hệ Thống Phạm Vi Hiển Thị (Global / Department / Workspace) & Triệt Tiêu Timeout Khi Chuyển Đổi

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thống nhất cơ chế chọn phạm vi hiển thị tài liệu với 3 chế độ rõ ràng (Toàn hệ thống / Theo phòng ban / Theo Workspace) và chuyển toàn bộ việc tháo gỡ Wiki / xóa vector sang Background Worker để triệt tiêu lỗi `Request timed out`.

**Architecture:** Chuẩn hóa `ScopeType` (`global`, `department`, `project`) và logic lưu `source_departments` tương ứng với từng scope. Tại endpoint `PATCH /api/sources/{id}`, toàn bộ quá trình `detach_source_from_wiki`, `delete_page_cascade` và `regenerate_index` được ủy thác cho ARQ task `reassign_source_scope_task`, trả về HTTP 200 ngay lập tức (<100ms). Frontend tái cấu trúc modal chỉnh sửa thành 1 selector trực quan với 3 chế độ động, mở khóa chỉnh sửa linh hoạt và sửa thông báo xác nhận tiếng Việt.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2.0 (Async), ARQ / Redis, Next.js 14, TypeScript, Tailwind CSS / Shadcn UI.

---

### Task 1: Background Worker Task Cho Async Detach (`app/worker.py`)

**Files:**
- Modify: `app/worker.py`

- [ ] **Step 1: Viết hàm `reassign_source_scope_task` trong `app/worker.py`**
  ```python
  async def reassign_source_scope_task(
      ctx: dict,
      source_id_str: str,
      old_scopes: list[tuple[str, Optional[str]]],
  ) -> None:
      """
      Chạy ngầm trong background worker:
      1. Tháo gỡ source khỏi các trang wiki cũ và xóa cascade các trang phụ thuộc (detach_source_from_wiki).
      2. Tái tạo _index cho các scope cũ (regenerate_index).
      3. Đẩy tiếp ingest_map_reduce_task để biên soạn vào phạm vi mới.
      """
  ```
- [ ] **Step 2: Đăng ký `reassign_source_scope_task` vào danh sách hàm ARQ trong `WorkerSettings` (dòng ~1350)**
- [ ] **Step 3: Commit**
  ```bash
  git add app/worker.py
  git commit -m "feat(worker): add reassign_source_scope_task for async wiki detach and re-indexing"
  ```

---

### Task 2: Cập Nhật API Endpoint `PATCH /api/sources/{id}` Để Phản Hồi Tức Thì (`app/routers/sources.py`)

**Files:**
- Modify: `app/routers/sources.py:760-862`

- [ ] **Step 1: Cập nhật `PATCH /api/sources/{source_id}`**
  - Xóa bỏ việc gọi trực tiếp `wiki_service.detach_source_from_wiki` và `regenerate_index` đồng bộ trong request handler.
  - Khi phát hiện thay đổi phạm vi hiển thị (giữa Global, Department hoặc Project) trên tài liệu `ready`:
    - Lưu cấu hình mới vào DB.
    - Cập nhật `source.status = "processing"`, `source.progress = 0`, `source.progress_message = "Đang chuyển đổi phạm vi hiển thị..."`.
    - Enqueue job `reassign_source_scope_task` vào Redis pool.
    - Commit và trả về `SourceResponse` ngay lập tức (<100ms).
  - Không chặn thay đổi phạm vi khi tài liệu đang xử lý (`in_flight_statuses`).
- [ ] **Step 2: Commit**
  ```bash
  git add app/routers/sources.py
  git commit -m "fix(sources): delegate wiki detach and re-indexing to background worker to prevent timeout"
  ```

---

### Task 3: Cập Nhật Frontend API & Đa Ngôn Ngữ i18n

**Files:**
- Modify: `frontend/src/lib/api.ts:7`
- Modify: `frontend/src/lib/i18n.tsx:150, 593`

- [ ] **Step 1: Tăng `REQUEST_TIMEOUT_MS` trong `frontend/src/lib/api.ts` từ 30s lên 60s để tăng độ ổn định**
- [ ] **Step 2: Bổ sung và chuẩn hóa các key i18n trong `frontend/src/lib/i18n.tsx`**:
  - `knowledge.scope.global`: "Toàn hệ thống" / "Global"
  - `knowledge.scope.department`: "Theo phòng ban" / "Department"
  - `knowledge.scope.project`: "Theo Workspace" / "Workspace"
  - `knowledge.edit.scopeChangeConfirm`: "Việc thay đổi phạm vi hiển thị sẽ kích hoạt biên soạn lại tri thức bằng AI. Bạn có muốn tiếp tục?" / "Changing visibility scope will rerun AI compilation. Continue?"
- [ ] **Step 3: Commit**
  ```bash
  git add frontend/src/lib/api.ts frontend/src/lib/i18n.tsx
  git commit -m "feat(frontend): increase client timeout to 60s and add scope i18n keys"
  ```

---

### Task 4: Tái Cấu Trúc Giao Diện Modal Chỉnh Sửa Tài Liệu (`edit-source-dialog.tsx`)

**Files:**
- Modify: `frontend/src/components/knowledge/knowledge-table/edit-source-dialog.tsx`

- [ ] **Step 1: Gom mục "Phòng ban" và "Phạm vi hiển thị" thành 1 bộ chọn duy nhất với 3 chế độ**:
  - `global` (Toàn hệ thống): Biên soạn vào wiki chung, hiển thị cho mọi nhân sự.
  - `department` (Theo phòng ban): Mở danh sách checkbox chọn 1 hoặc nhiều phòng ban.
  - `project` (Theo Workspace): Mở dropdown chọn 1 Workspace mục tiêu.
- [ ] **Step 2: Đồng bộ state khi đổi chế độ**:
  - Khi chọn `global`: `scopeType = "global"`, `selectedDepts = []`, `scopeId = ""`.
  - Khi chọn `department`: `scopeType = "department"`, `scopeId = ""`.
  - Khi chọn `project`: `scopeType = "project"`, `selectedDepts = []`.
- [ ] **Step 3: Mở khóa các trường phạm vi (không disable khi `inFlight`)**
- [ ] **Step 4: Sửa hộp thoại xác nhận dùng đúng key `knowledge.edit.scopeChangeConfirm`**
- [ ] **Step 5: Kiểm tra và commit**
  ```bash
  git add frontend/src/components/knowledge/knowledge-table/edit-source-dialog.tsx
  git commit -m "feat(ui): unify scope selector into 3 intuitive modes and fix confirm dialog"
  ```

---

### Task 5: Kiểm Thử & Xác Nhận Toàn Bộ Luồng

- [ ] **Step 1: Kiểm tra build TypeScript / Next.js ở frontend**
- [ ] **Step 2: Kiểm tra cú pháp Python backend**
- [ ] **Step 3: Báo cáo kết quả và hướng dẫn nghiệm thu cho người dùng**
