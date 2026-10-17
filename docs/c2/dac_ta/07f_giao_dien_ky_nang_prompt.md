# 07f — Giao diện Thư viện kỹ năng, Đề xuất kỹ năng và Kho prompt

Tài liệu này thuộc loạt đặc tả giao diện 07 (mục lục ở `07_giao_dien.md`, nền tảng dùng chung như khung trang portal, theme, thành phần shadcn/base-ui, quy ước biểu tượng Material Symbols, hàm gọi API và ngữ cảnh xác thực ở `07a_giao_dien_nen_tang.md`). Phạm vi: trang danh sách kỹ năng `/skills`, trang chi tiết `/skills/[slug]`, đường dẫn chuyển hướng `/skills/[slug]/edit`, trình soạn đề xuất nhiều tệp (SkillEditor), trình duyệt tệp của kỹ năng (SkillFileExplorer), các hộp thoại tạo/sửa/tải/đóng góp kỹ năng, các hộp thoại quản lý thẻ (hiện chưa gắn vào trang), trang quản trị `/admin/skill-contributions`, và trang Kho prompt `/prompts` cùng hộp thoại tạo/sửa prompt. Mọi biểu tượng là tên ligature của Google Material Symbols Outlined hiển thị trong một span. Màu được mô tả theo vai trò (primary = màu nhấn thương hiệu cam đất; destructive = đỏ báo lỗi; muted = xám nền phụ…), không ghi mã màu.

---

## 0. Quy ước chung trong tài liệu

### 0.1 Quyền

- `canAccess(resource, action)` trả về đúng khi: người dùng là `admin` (trường `role` của user bằng `admin`), **hoặc** danh sách `permissions` của user chứa `{resource}:{action}:all` **hoặc** `{resource}:{action}:own_dept`. Chưa đăng nhập → sai.
- `hasPermission(perm)` kiểm tra đúng một chuỗi quyền.
- Các chuỗi quyền dùng trong phạm vi tài liệu:

| Biểu thức | Chuỗi quyền thỏa mãn |
|---|---|
| `canAccess("skill","read")` (mục menu bên) | `skill:read:own_dept`, `skill:read:all` |
| `canAccess("skill","create")` | `skill:create:all`, `skill:create:own_dept` |
| `canAccess("skill","edit")` | `skill:edit:all`, `skill:edit:own_dept` |
| `canAccess("skill","delete")` | `skill:delete:all`, `skill:delete:own_dept` |
| `canAccess("skill","review")` | `skill:review:all`, `skill:review:own_dept` |
| `hasPermission("skill:contribution:review")` | đúng chuỗi đó |

- Mục menu bên "Kỹ năng AI" (khóa `nav.skills`, biểu tượng `bolt`, đường dẫn `/skills`) chỉ hiện khi có `skill:read:own_dept` hoặc `skill:read:all` (hoặc admin). Mục "Kho prompt" (khóa `nav.prompts`, biểu tượng `chat_paste_go`, đường dẫn `/prompts`) hiện với mọi người dùng đã đăng nhập. Trang `/admin/skill-contributions` **không** có mục menu; chỉ vào bằng URL.

### 0.2 Gọi API

- Mọi lời gọi đi qua hàm `api` (JSON, kèm Bearer token) hoặc `apiUpload` (multipart, method POST, thời hạn 120 giây) mô tả ở 07a. Khi lỗi, đối tượng lỗi có `status`, `message` (= trường `detail` của JSON lỗi nếu có, nếu không là "API Error {mã}") và `data` (JSON lỗi gốc).
- "Thông báo nổi" (toast) trong tài liệu này là một khối nhỏ cố định góc dưới-phải màn hình (cách mép 24px), nền màu chữ chính (foreground), chữ màu nền (đảo màu), bo góc, bóng đổ, chữ cỡ nhỏ; tự biến mất sau 4 giây (trang kỹ năng) hoặc 3 giây (trang prompt). Mỗi lần chỉ một thông báo, thông báo mới thay thông báo cũ.
- "confirm" / "alert" / "prompt" = hộp thoại gốc của trình duyệt.

### 0.3 Thanh cuộn (hiệu ứng của tệp kiểu riêng của module kỹ năng)

- Lớp "thanh cuộn mảnh": thanh cuộn rộng/cao 5px, rãnh trong suốt, con trượt bo tròn mang màu nhấn thương hiệu rất nhạt (khoảng 10% độ đậm); khi rê chuột vào vùng cuộn con trượt đậm lên (~30%), khi rê lên chính con trượt đậm hơn nữa (~60%); có chuyển tiếp mượt.
- Lớp "ẩn thanh cuộn": vẫn cuộn được nhưng không hiển thị thanh cuộn trên mọi trình duyệt.

### 0.4 Kiểu hiển thị Markdown kiểu "GitHub" (dùng ở trang chi tiết và trình soạn)

Nội dung Markdown (hỗ trợ GFM: bảng, danh sách việc, gạch ngang) hiển thị theo phong cách README của GitHub: phông hệ thống sans-serif; H1 cỡ gấp đôi, H2 cỡ 1,5 lần, cả hai có đường kẻ mảnh phía dưới; H3 cỡ 1,25 lần; đoạn văn giãn dòng ~1,5–1,6, cách dưới 16px; danh sách có dấu chấm/số, thụt 2em; mã nội dòng có nền xám nhạt bo góc, phông monospace cỡ 85%; khối mã nền xám rất nhạt, viền mảnh, padding 16px, cuộn ngang; trích dẫn có vạch trái xám và chữ xám; bảng full-width, viền mảnh từng ô, hàng chẵn tô nền rất nhạt. Ở trang chi tiết, tiêu đề cột bảng tô nền màu nhấn thương hiệu rất nhạt và viền dùng màu viền của theme; ở trình soạn, tiêu đề cột nền xám nhạt.

### 0.5 Kiểu dữ liệu `Skill` (một phần tử danh sách)

| Trường | Kiểu | Ghi chú |
|---|---|---|
| `id` | string (UUID) | |
| `name` | string | tên hiển thị/gọi kỹ năng |
| `slug` | string | dùng trong URL |
| `description` | string \| null | danh sách thường trả null; mô tả thật nằm trong frontmatter SKILL.md |
| `department_ids` | string[] (tùy chọn) | |
| `department_names` | string[] (tùy chọn) | |
| `current_version` | number | |
| `version_hash` | string \| null (tùy chọn) | không hiển thị |
| `status` | string | `active`, `processing`, `deleting`, `error`, `failed` |
| `scope_type` | string | `global` hoặc `department` |
| `scope_id` | string \| null | |
| `is_system` | boolean | kỹ năng hệ thống (nạp sẵn) |
| `updated_at` | string ISO | |

---

## 1. Trang danh sách kỹ năng — `/skills`

### 1.1 Mục đích

Thư viện các gói kỹ năng (SKILL.md và tệp kèm) mà trợ lý AI tự đọc khi gặp đúng loại yêu cầu. Cho phép tìm, lọc theo phạm vi/phòng ban, xem chi tiết, tạo mới (soạn nhanh một tệp, soạn nhiều tệp qua đề xuất, tải gói ZIP), nhân bản, sửa nội dung, đổi tên/phạm vi, tải phiên bản mới, xóa; xem đề xuất của mình và đề xuất chờ mình duyệt.

### 1.2 Tải dữ liệu

| Thời điểm | API | Ghi chú |
|---|---|---|
| Khi vào trang | `GET /api/departments` → mảng `{id, name}` | lỗi → mảng rỗng |
| Khi vào trang và mỗi khi ô tìm kiếm đổi (trễ 200ms sau lần gõ cuối) | `GET /api/skills?q={chuỗi tìm}&limit=2000` (bỏ `q` nếu rỗng) → `{items: Skill[], total: number}` | lỗi → danh sách rỗng; tìm kiếm thực hiện ở máy chủ |
| Khi có ít nhất một kỹ năng ở trạng thái `processing` hoặc `deleting` | cứ 3 giây: `GET /api/skills?ids={id1}&ids={id2}…&limit=2000` | xem 1.3 |
| Lười cho mô tả thẻ | `GET /api/skills/{slug}/content` → dùng trường `description` | xem 1.6 |

Trường `total` được lưu nhưng không hiển thị; con số hiển thị là số thẻ sau lọc phía máy khách.

### 1.3 Thăm dò trạng thái xử lý

- Tập theo dõi = id các kỹ năng có `status` là `processing` hoặc `deleting`. Vòng thăm dò khởi động lại mỗi khi chuỗi trạng thái của danh sách thay đổi; dừng khi không còn mục nào cần theo dõi.
- Kết quả: id đang theo dõi mà **không** có trong phản hồi → coi như đã bị xóa khỏi CSDL → loại khỏi danh sách và giảm `total` tương ứng (không âm). Mục có trong phản hồi mà khác dữ liệu hiện tại → thay bằng bản mới (ví dụ chuyển `processing` → `active`). Lỗi thăm dò chỉ ghi log.

### 1.4 Bố cục

Cột dọc, khoảng cách 24px giữa các vùng:

1. **Đầu trang** (thành phần PageHeader của 07a): tiêu đề "Thư viện kỹ năng"; mô tả "Bộ hướng dẫn trợ lý AI tự đọc khi gặp đúng loại yêu cầu. Bấm vào thẻ để xem chi tiết, sửa hoặc nhân bản."; vùng hành động bên phải (chỉ khi `canAccess("skill","create")`), một hàng các nút cỡ nhỏ có thể xuống dòng:
   - Nút dạng ghost, chữ màu muted, biểu tượng `edit_square`, nhãn "Soạn nhiều tệp", tooltip "Soạn kỹ năng nhiều tệp và gửi duyệt" → mở hộp thoại Đóng góp ở chế độ tạo mới (mục 6), truyền danh sách phòng ban đã tải; khi tạo xong mở Trình soạn đề xuất (1.9).
   - Nút "Tải gói ZIP" (mục 5).
   - Nút chính (primary), biểu tượng `add`, nhãn "Tạo kỹ năng" → mở hộp thoại Tạo/Sửa kỹ năng ở chế độ tạo (mục 4).
2. **Hàng đề xuất**: lưới 1 cột, 2 cột từ màn hình lớn (≥1024px), khoảng cách 12px; tự ẩn hoàn toàn khi cả hai khối bên trong không hiển thị gì.
   - Khối "Đề xuất của tôi" (mục 8.1), làm mới mỗi khi trình soạn đề xuất được mở/đóng (thành phần được dựng lại).
   - Khối "Chờ tôi duyệt" (mục 8.2) ở chế độ được điều khiển: trang giữ danh sách và truyền xuống; thành phần tự tải lần đầu rồi đẩy dữ liệu lên trang.
3. **Thanh lọc + lưới thẻ** (1.5, 1.6).
4. Thông báo nổi (0.2).
5. Các hộp thoại: Tạo/Sửa kỹ năng, Trình soạn đề xuất, Xem xét đề xuất.

Không có chế độ bảng: thành phần danh sách (tên lịch sử "SkillTable") chỉ hiển thị lưới thẻ. Các khóa i18n `skills.colSkill`, `skills.colVersion`, `skills.colVisibility`, `skills.colDepartment`, `skills.colStatus`, `skills.colUpdated` tồn tại nhưng không được dùng. Không có thao tác hàng loạt và không có thanh bên lọc thẻ (tag) trên trang này.

### 1.5 Thanh lọc — dùng `ScopeFilterBar` có sẵn trong c2

c2 đã có `frontend/src/components/shared/library-list.tsx` (mã của nhóm, phụ thuộc `cn` từ `@/lib/utils`, `Input` từ `@/components/ui/input`, và từ `@/components/ui/dropdown-menu`: `DropdownMenu`, `DropdownMenuCheckboxItem`, `DropdownMenuContent`, `DropdownMenuItem`, `DropdownMenuRadioGroup`, `DropdownMenuRadioItem` (dùng thuộc tính `closeOnClick` của base-ui), `DropdownMenuSeparator`, `DropdownMenuTrigger` (được tạo kiểu trực tiếp, không dùng asChild)). Không đặc tả lại các export đó; trang kỹ năng dùng như sau:

| Export | Cách dùng ở trang kỹ năng |
|---|---|
| `ScopeFilterBar` | `search` = giá trị ô tìm cục bộ (khởi tạo từ chuỗi tìm của trang); `onSearch` = cập nhật ô cục bộ **và** đẩy lên trang (kích hoạt tải lại sau 200ms); `placeholder` = "Tìm theo tên, mô tả..."; `scope`/`onScope` = bộ lọc phạm vi cục bộ, mặc định `all`; `counts` = `countByScope(skills, phòng ban đã chọn)`; `withPersonal` = **false** (kỹ năng không có phạm vi cá nhân, nên mục "Cá nhân" bị ẩn); `departments` = danh sách phòng ban; `department`/`onDepartment` = mảng id phòng ban đã chọn (state của trang); `total` = "{số thẻ hiển thị} kỹ năng" |
| `filterByScope` | danh sách hiển thị = `filterByScope(skills, scope, phòng ban đã chọn)` |
| `countByScope` | số đếm trên menu phạm vi |
| `LibraryCard`, `IconBtn`, `ScopeChip`, `Chip`, `fmtDate` | dựng từng thẻ (1.6) |

### 1.6 Thẻ kỹ năng

Lưới: 1 cột; 2 cột từ ≥768px; 3 cột từ ≥1280px; khoảng cách 12px. Mỗi kỹ năng một `LibraryCard`:

| Thuộc tính | Giá trị |
|---|---|
| `icon` | `verified` nếu `is_system`, ngược lại `auto_awesome` |
| `iconCls` | kỹ năng hệ thống: ô biểu tượng nền hổ phách nhạt, biểu tượng hổ phách đậm; còn lại để mặc định (nền primary nhạt, biểu tượng primary) |
| `title` | `name` |
| `description` | `description` nếu có, ngược lại mô tả tải lười |
| `onOpen` | điều hướng tới `/skills/{slug}` (kể cả khi đang `deleting`) |
| `meta` | `fmtDate(updated_at)` (dd/mm/yyyy) |

**Tải lười mô tả**: với các thẻ đang hiển thị chưa có mô tả và chưa từng được yêu cầu, lấy tối đa 60 slug, chạy 4 luồng song song, mỗi luồng tuần tự gọi `GET /api/skills/{slug}/content` (slug được mã hóa URL) và ghi `description` trả về vào bộ nhớ tạm theo slug. Lỗi bỏ qua (thẻ chỉ thiếu mô tả). Khi danh sách hiển thị đổi, các slug chưa kịp tải được hủy và có thể được yêu cầu lại.

**Nhóm thao tác** (bên phải tiêu đề, mờ 70% và rõ hẳn khi rê chuột vào thẻ; bấm không mở thẻ). Quy tắc: `editable` = `canAccess("skill","edit")` và (không phải hệ thống **hoặc** user là admin); `deletable` = `canAccess("skill","delete")` và (không phải hệ thống **hoặc** admin).

| Thứ tự | Điều kiện | Nút (`IconBtn`) | Hành động |
|---|---|---|---|
| 1 | `canAccess("skill","create")` | `library_add`, tooltip "Nhân bản" | 1.7 |
| 2 | `editable` | `edit`, "Sửa nội dung" | mở hộp thoại Tạo/Sửa ở chế độ sửa với `slug` của kỹ năng |
| 3 | `deletable` | `delete`, "Xóa", kiểu nguy hiểm (chữ đỏ khi rê) | 1.8 |
| 4 | `editable` | nút menu 28×28px, biểu tượng `more_vert` cỡ 16, tooltip và aria-label "Thao tác khác" | menu thả xuống căn phải, rộng ~208px, bo góc lớn; 2 mục (biểu tượng + chữ): `tune` "Đổi phạm vi" (nếu hệ thống) hoặc "Đổi tên / phạm vi" → hộp thoại 3.1; `upload_file` "Tải phiên bản mới (ZIP)" → hộp thoại 3.2 |

**Hàng nhãn** (chips, chữ 11px):
1. `ScopeChip` với `scopeType` = `scope_type`, `departmentNames` = `department_names`.
2. Nếu `is_system`: `Chip` biểu tượng `verified`, tông hổ phách, chữ "Hệ thống".
3. Nhãn phiên bản: chữ monospace 10px nền muted bo góc "v{current_version}".
4. Nhãn trạng thái (không hiện khi `active`):

| `status` | Chữ | Tông màu |
|---|---|---|
| `processing` | "Đang xử lý" | vàng nhạt, kèm biểu tượng `progress_activity` xoay cỡ 11 |
| `deleting` | "Đang xóa" | đỏ (destructive) nhạt, kèm biểu tượng xoay |
| `error`, `failed` | "Lỗi" | đỏ nhạt |

### 1.7 Nhân bản

`GET /api/skills/{slug}/content` → `{name, description, body}`. Mở hộp thoại Tạo kỹ năng (chế độ tạo) điền sẵn: tên = "{name gốc}-tuy-chinh" cắt còn 80 ký tự; mô tả và nội dung lấy từ phản hồi. Lỗi → alert "Không tải được nội dung: {thông điệp lỗi}".

### 1.8 Xóa

- Hộp confirm: kỹ năng hệ thống → `Gỡ kỹ năng hệ thống "{name}" khỏi thư viện? Trợ lý sẽ không dùng kỹ năng này nữa và lần khởi động sau không tự nạp lại.`; còn lại → `Xóa kỹ năng "{name}"? Trợ lý sẽ không dùng được kỹ năng này nữa.`
- Đồng ý → `DELETE /api/skills/{id}` (dùng **id**). Thành công → thông báo nổi "Đã gỡ kỹ năng hệ thống" hoặc "Đang xóa kỹ năng", tải lại danh sách (mục thường chuyển sang `deleting` và được thăm dò cho tới khi biến mất). Lỗi → alert "Xóa thất bại: {thông điệp | Lỗi không xác định}".

### 1.9 Trình soạn đề xuất (hộp thoại toàn màn hình, chế độ sửa)

Mở khi một đề xuất được tạo (từ "Soạn nhiều tệp") hoặc khi bấm một mục trong "Đề xuất của tôi".

- Khung: rộng tối đa 98% viewport (mục tiêu 1800px), cao 96% viewport, căn giữa, không padding, bo góc, viền, bóng lớn; không có nút đóng mặc định của Dialog.
- Đầu hộp thoại (nền primary rất nhạt, kẻ dưới): bên trái ô vuông 40px nền primary nhạt chứa biểu tượng `edit_note` màu primary; tiêu đề phông serif cỡ lớn "Chỉnh sửa đề xuất"; dòng phụ nhỏ "Bản nháp: gửi duyệt khi đã xong". Bên phải:
  - Nút "Gửi duyệt": cao 32px, nền màu nhấn thương hiệu, chữ trắng in hoa đậm giãn chữ, bóng. Confirm "Gửi đề xuất này để duyệt?" → `POST /api/skill-contributions/{id}/submit` → thông báo nổi "Đã gửi đề xuất để duyệt", đóng hộp thoại, tải lại danh sách kỹ năng. Lỗi → alert "Gửi thất bại: {thông điệp | Lỗi không xác định}".
  - Nút biểu tượng `delete` (ghost, đỏ khi rê), tooltip "Xóa bản nháp": confirm "Xóa bản nháp này? Không thể hoàn tác." → `DELETE /api/skill-contributions/{id}` → đóng, tải lại danh sách. Lỗi → alert "Xóa thất bại: …".
  - Nút biểu tượng `close`, tooltip "Đóng".
- Thân: Trình soạn (mục 7) với `mode` = `edit`, chiếm toàn bộ phần còn lại.
- Đóng bằng Esc/bấm ra ngoài cũng đóng hộp thoại.

### 1.10 Hộp thoại xem xét đề xuất (chế độ duyệt)

Mở khi bấm một mục trong "Chờ tôi duyệt". Khung giống 1.9.

- Đầu: biểu tượng `rate_review`; tiêu đề "Xem xét đề xuất"; dòng phụ "Người gửi: **{contributor_name}**" (tên đậm, lấy từ danh sách chờ duyệt).
- Nút "Từ chối" (ghost, biểu tượng `close`, đỏ khi rê): confirm "Từ chối đề xuất này?" → `POST /api/skill-contributions/{id}/reject` → thông báo "Đã từ chối đề xuất", đóng, bỏ mục khỏi danh sách chờ duyệt, tải lại kỹ năng.
- Nút "Duyệt & hợp nhất" (nền màu nhấn thương hiệu, chữ trắng đậm, biểu tượng `check_circle`): confirm "Duyệt và hợp nhất đề xuất này vào thư viện?" → `POST /api/skill-contributions/{id}/approve` → thông báo "Đã duyệt và hợp nhất đề xuất", đóng, bỏ khỏi danh sách chờ, tải lại kỹ năng.
- Khi duyệt/từ chối lỗi: alert "Duyệt thất bại: …" / "Từ chối thất bại: …", **vẫn** đóng hộp thoại và bỏ mục khỏi danh sách chờ.
- Vạch dọc ngăn cách, rồi nút `close` tooltip "Đóng".
- Thân: Trình soạn với `mode` = `review`; nếu trình soạn báo thay đổi trạng thái thì đóng và tải lại.

---

## 2. Trang chi tiết kỹ năng — `/skills/[slug]`

Lưu ý: nhãn trên trang này hiện là tiếng Anh cố định (giữ nguyên để tương đương).

### 2.1 Tải dữ liệu

| Khi | API | Kết quả dùng |
|---|---|---|
| Vào trang / đổi phiên bản đang xem | `GET /api/skills/{slug}` hoặc `GET /api/skills/{slug}?version={n}` → `Skill` | lần đầu (chưa chọn phiên bản) đặt phiên bản đang xem = `current_version` (gây tải lại một lần với tham số version) |
| Vào trang | `GET /api/skills/{slug}/versions` → mảng `{version_number, created_at, changelog?}` | danh sách phiên bản |

### 2.2 Trạng thái

- Đang tải: biểu tượng `progress_activity` xoay cỡ lớn, căn giữa, đệm dọc 96px.
- Lỗi 404: liên kết quay lại (xem dưới) + EmptyState: biểu tượng `search_off`, tiêu đề "Skill Not Found", mô tả `We couldn't find a skill with the identifier "{slug}". It might have been deleted or moved.`, nút viền "Return to Library" (in hoa, giãn chữ, cao 44px) → `/skills`.
- Lỗi khác: trang trống.

### 2.3 Bố cục

- Hàng trên: nút chữ nhỏ màu muted (rê → primary) biểu tượng `arrow_back` + "Back to Skills" → `/skills`.
- Lưới 1 cột; từ ≥1024px chia 4 cột, khoảng cách 32px:
  - **3 cột trái**: Trình duyệt tệp (mục 9) với `skillId` = `id`, `version` = phiên bản đang xem.
  - **1 cột phải**, xếp dọc:
    1. Hàng nút căn phải (hiệu ứng trượt vào từ phải):
       - Khi không phải hệ thống và `canAccess("skill","create")`: hộp thoại Đóng góp ở chế độ cải tiến (mục 6) với `skillId`, `skillName`, `versions` (nút kích hoạt mặc định "Contribute"); và nút viền nhỏ cao 36px, biểu tượng `publish` (đổi thành `progress_activity` xoay khi đang tải lên), chữ "ZIP", tooltip "Upload ZIP" — mở chọn tệp `.zip` (2.4).
       - Khi không phải hệ thống và `canAccess("skill","delete")`: nút vuông 36px kiểu destructive, biểu tượng `delete`, tooltip "Delete Skill" (2.5).
    2. Thẻ thông tin (nền card, viền, bo góc, padding 32px), hai phần có tiêu đề nhỏ in hoa màu muted:
       - "Status": huy hiệu tròn in hoa hiển thị nguyên giá trị `status`; `active` → tông xanh lục, khác → tông vàng.
       - "Version History": bên phải tiêu đề, khi phiên bản đang xem khác `current_version` hiện huy hiệu vàng "PREVIEWING OLD". Hộp chọn full-width cao 40px, placeholder "Select version", mỗi mục "Version {n}" và thêm " (Latest)" cho bản hiện hành; danh sách cuộn tối đa ~240px. Chọn mục → đổi phiên bản đang xem (tải lại kỹ năng và cây tệp). Bên dưới, khi không phải hệ thống, `canAccess("skill","edit")` và đang xem bản cũ: nút primary full-width cao 40px "Set as Official Latest" (khi đang chạy "Setting...", bị vô hiệu) (2.6).
    3. Khối "Chờ tôi duyệt" (mục 8.2) chế độ tự quản, lọc theo `skillId`; bấm mục → hộp thoại duyệt (2.8).

### 2.4 Tải ZIP phiên bản mới (trang chi tiết)

- Tên tệp phải đúng **chính xác** "{name}.zip"; sai → alert `Filename mismatch! You must upload a file named exactly "{name}.zip".` và xóa lựa chọn.
- Gửi `POST /api/skills/{slug}/reupload` (multipart, trường `file`) → `{status, message}`. `status` = `skipped` → alert `message`; khác → tải lại toàn trang. Lỗi → alert "Error: {detail trong JSON lỗi}" (hoặc "Upload failed"). Luôn xóa lựa chọn tệp sau cùng.

### 2.5 Xóa (trang chi tiết)

Confirm "Are you sure you want to delete {name}?" → `DELETE /api/skills/{slug}` (dùng **slug**) → về `/skills`. Lỗi → alert "Failed to delete skill".

### 2.6 Đặt phiên bản hiện hành

Confirm "Are you sure you want to set Version {n} as the official latest version?" → `POST /api/skills/{slug}/set-latest?version={n}` → alert "Version {n} is now the latest." rồi tải lại trang. Lỗi → alert "Failed to set latest version".

### 2.7 Hộp thoại sửa đề xuất (trang chi tiết)

Như 1.9 nhưng nhãn tiếng Anh: tiêu đề "Editing Contribution", phụ đề "Draft Mode"; nút gửi "Contribute" → confirm "Are you sure you want to submit this contribution for review?" → `POST /api/skill-contributions/{id}/submit` → alert "Contribution submitted successfully!", đóng, tải lại trang; lỗi → alert "Submit failed: {thông điệp | Unknown error}". Nút xóa tooltip "Delete Draft", confirm "Are you sure you want to delete this draft contribution? This action cannot be undone." → `DELETE /api/skill-contributions/{id}` → tải lại trang; lỗi "Delete failed: …". Nút đóng tooltip "Close Editor". Trình soạn `mode` = `edit`.

### 2.8 Hộp thoại duyệt (trang chi tiết)

Như 1.10, nhãn tiếng Anh: "Review Contribution", "Submitted by **{tên | Unknown}**", nút "Reject" và "Approve & Merge", tooltip đóng "Close Reviewer". Confirm: "Are you sure you want to APPROVE and MERGE this contribution?" / "Are you sure you want to REJECT this contribution?". Duyệt thành công → alert "Contribution approved and merged successfully!" và tải lại trang; từ chối thành công → alert "Contribution rejected.", đóng. Lỗi → alert "Approval failed: …" / "Rejection failed: …", đóng. Trình soạn không truyền `mode` (mặc định `review`).

### 2.9 `/skills/[slug]/edit`

Không hiển thị gì; thay ngay URL thành `/skills/{slug}` (replace, không thêm lịch sử).

---

## 3. Hộp thoại phụ trong lưới thẻ

### 3.1 Đổi tên / phạm vi

- Khung rộng tối đa ~448px, bo góc lớn. Tiêu đề phông serif "Đổi tên / phạm vi" (luôn chữ này, kể cả với kỹ năng hệ thống).
- Trường (nhãn nhỏ in hoa đậm màu muted):

| Nhãn | Điều khiển | Quy tắc |
|---|---|---|
| "Tên kỹ năng" | ô nhập cao 44px, placeholder "vd: Soạn công văn", giá trị đầu = `name` | bị khóa khi `is_system` (tooltip "Kỹ năng hệ thống giữ nguyên tên; hãy nhân bản nếu cần tên khác"). Hợp lệ khi không rỗng và chỉ gồm chữ cái Latin hoa/thường, chữ số, khoảng trắng, dấu gạch nối, gạch dưới và chữ tiếng Việt có dấu. Sai → viền đỏ và dòng lỗi "Tên chỉ gồm chữ, số, khoảng trắng, dấu - và _." |
| "Phạm vi" | hộp chọn cao 44px; ô hiển thị biểu tượng `public` + "Toàn hệ thống" hoặc `corporate_fare` + "Phòng ban" | mục: `public` "Toàn hệ thống (mọi phòng ban)" (giá trị `global`), `corporate_fare` "Một số phòng ban" (`department`). Giá trị đầu = `scope_type` hoặc `global` |
| "Phòng ban áp dụng" (chỉ khi `department`) | khung viền bo góc, danh sách checkbox (nhãn = tên phòng ban, rê → primary), cuộn tối đa 200px với thanh cuộn mảnh | giá trị đầu = `department_ids`. Không có phòng ban → chữ nghiêng "Chưa có phòng ban". Không bắt buộc chọn ít nhất một |

- Lỗi máy chủ: hộp đỏ nhạt có biểu tượng `error` + thông điệp (hoặc "Lưu thất bại").
- Nút: ghost "Hủy" (đóng); primary "Lưu" (vô hiệu khi đang lưu hoặc tên sai; khi lưu hiện spinner + "Đang lưu...").
- Lưu: `PATCH /api/skills/{id}` thân JSON: `name` (bỏ qua nếu hệ thống hoặc rỗng), `department_ids` (mảng đã chọn nếu `department`, ngược lại mảng rỗng), `scope_type`, `scope_id` (id phòng ban đầu tiên nếu `department` và có chọn, ngược lại null). Thành công → đóng và tải lại danh sách.

### 3.2 Tải phiên bản mới (ZIP)

- Khung ~448px. Tiêu đề serif "Tải phiên bản mới".
- Thân căn giữa: vòng tròn 80px nền primary rất nhạt chứa `cloud_upload` cỡ lớn; dòng "Cập nhật **{name}**" (tên màu primary đậm); dòng phụ "Tải gói ZIP mới để thay toàn bộ tệp hiện tại và tạo phiên bản mới."
- Nút primary full-width cao 48px: biểu tượng `upload_file` + "Chọn gói ZIP"; khi đang tải: spinner + "Đang tải lên..." (vô hiệu). Bấm → mở chọn tệp (chỉ `.zip`).
- Kiểm tra: tên tệp không kết thúc bằng ".zip" → lỗi "Hãy chọn tệp .zip".
- Gửi `POST /api/skills/{slug}/reupload` (multipart, trường `file`). Thành công → đóng, tải lại danh sách. Lỗi → hộp lỗi đỏ (biểu tượng `error`) với thông điệp hoặc "Tải lên thất bại".

---

## 4. Hộp thoại Tạo / Sửa kỹ năng (soạn nhanh một tệp SKILL.md)

### 4.1 Đầu vào

`open`, `onOpenChange`, `mode` (`create` | `edit`), `slug` (khi sửa), `initial` (tên/mô tả/nội dung điền sẵn khi nhân bản), `departments`, `onSaved(thông điệp)` — trang hiển thị thông điệp thành thông báo nổi và tải lại danh sách.

Module này còn export hàm chuyển chuỗi thành tên kỹ năng (tên gốc `toSkillName`, nhận chuỗi, trả chuỗi) được hộp thoại prompt dùng lại: thay "đ"/"Đ" bằng "d"/"D", bỏ dấu tiếng Việt, chuyển chữ thường, mọi chuỗi ký tự liên tiếp không phải chữ a–z hay chữ số thành một dấu "-", bỏ "-" ở đầu, cắt tối đa 80 ký tự. (Hệ quả: dấu gạch dưới cũng thành "-".)

### 4.2 Khi mở

- Xóa lỗi, đặt phạm vi về "Toàn hệ thống", bỏ chọn phòng ban.
- Sửa: hiện spinner giữa thân; `GET /api/skills/{slug}/content` → `{name, description, body}`; lỗi → thông điệp hoặc "Không tải được nội dung kỹ năng".
- Tạo: tên/mô tả lấy từ `initial` (hoặc rỗng); nội dung lấy từ `initial` nếu có, nếu không dùng **khung mẫu**: một văn bản Markdown gồm bốn đề mục cấp 1 lần lượt "Mục đích", "Khi nào dùng", "Cách làm", "Định dạng trả lời", mỗi đề mục có một dòng gợi ý ngắn (cách làm gợi ý bước đầu tra cứu kho tri thức để lấy căn cứ; định dạng trả lời gợi ý trả lời tiếng Việt và nêu rõ căn cứ văn bản).

### 4.3 Bố cục

- Khung rộng tối đa ~768px, cao tối đa 92% viewport, cột dọc; đầu và chân cố định, thân cuộn.
- Đầu (kẻ dưới): tiêu đề "Sửa kỹ năng {name}" hoặc "Tạo kỹ năng"; mô tả nhỏ: sửa → "Lưu sẽ tạo phiên bản mới; các tệp đính kèm khác của kỹ năng được giữ nguyên."; tạo → "Kỹ năng là bộ hướng dẫn trợ lý AI đọc khi gặp đúng loại yêu cầu (gói SKILL.md)."
- Thân: lưới 2 cột từ ≥640px (cột nhãn ~120px, nhãn chữ nhỏ màu muted):

| Nhãn | Điều khiển | Ghi chú |
|---|---|---|
| "Tên kỹ năng" | ô nhập cao 36px, phông monospace, placeholder "vd: tom-tat-bien-ban" | mỗi lần gõ được chuẩn hóa bằng hàm ở 4.1; khóa khi sửa hoặc đang lưu. Chỉ khi tạo có dòng phụ "Chữ thường không dấu, số và “-”. Trợ lý gọi kỹ năng bằng tên này." |
| "Khi nào dùng" | vùng văn bản 2 dòng, không đổi kích thước, placeholder "vd: Dùng khi cán bộ cần tóm tắt biên bản, nêu người, việc, thời hạn." | dòng phụ "Trợ lý dựa vào mô tả này để chọn kỹ năng — viết rõ tình huống áp dụng." |
| "Phạm vi" (chỉ khi tạo) | Bộ chọn phạm vi (Phụ lục A), không có "Cá nhân" | |

  Dưới lưới: nhãn "Hướng dẫn (Markdown)"; bên phải nhãn, khi nội dung rỗng (sau khi bỏ khoảng trắng) hiện liên kết chữ primary "Chèn khung mẫu" (điền khung mẫu). Vùng văn bản cao tối thiểu ~288px, monospace 13px, giãn dòng rộng.
  Lỗi: dòng chữ đỏ nhỏ cuối thân.
- Chân: ghost "Hủy"; primary biểu tượng `save` (hoặc `progress_activity` khi lưu) + "Lưu phiên bản mới" (sửa) / "Tạo kỹ năng" (tạo).
- Không đóng được khi đang lưu.

### 4.4 Kiểm tra hợp lệ (nút lưu bị vô hiệu khi sai, đang lưu, hoặc đang tải)

- Tên (sau khi bỏ các "-" ở cuối): bắt đầu bằng chữ thường a–z hoặc chữ số, tiếp theo 1–79 ký tự chữ thường/chữ số/"-" (tổng 2–80 ký tự).
- "Khi nào dùng" không rỗng sau khi bỏ khoảng trắng.
- Nếu phạm vi "Theo phòng ban" thì phải chọn ít nhất một phòng ban.

### 4.5 Lưu

- Sửa: `PUT /api/skills/{slug}/content` thân `{description, body}` → `{status?, message?}`. Thông điệp: `skipped` → "Nội dung không đổi"; `contribution_pending` → "Đã gửi bản sửa, chờ duyệt"; khác → "Đã lưu — đang tạo phiên bản mới".
- Tạo: `POST /api/skills/compose` thân `{name (đã bỏ "-" cuối), description, body, scope_type ("department" hoặc "global"), department_ids (mảng đã chọn khi theo phòng ban, ngược lại rỗng)}` → `{results: [{status?, message?}]}`. Xét phần tử đầu: `status` `error` hoặc `rejected` → báo lỗi bằng `message` hoặc "Kho từ chối kỹ năng"; `contribution_pending` → "Đã gửi đề xuất kỹ năng, chờ duyệt"; khác → "Đã tạo kỹ năng {name}".
- Thành công → gọi `onSaved`, đóng. Lỗi → hiện thông điệp hoặc "Lưu thất bại".

---

## 5. Hộp thoại Tải gói kỹ năng ZIP

- Nút kích hoạt (chỉ khi `canAccess("skill","create")`): viền, cỡ nhỏ, biểu tượng `upload`, chữ "Tải gói ZIP", tooltip "Tải lên gói kỹ năng dạng ZIP".
- Khung ~500px, toàn bộ là một form (Enter gửi).
- Tiêu đề: khóa `skills.uploadSkill`. Mô tả: khóa `knowledge.upload.subtitle`.
- Trường:

| Nhãn | Điều khiển | Ghi chú |
|---|---|---|
| khóa `skills.selectZip` | ô chọn tệp, nhận `.zip`, chọn nhiều tệp; viền nét đứt dày, cao (đệm dọc ~32px), rê → viền primary | khi có tệp: dòng chữ primary "{số tệp} {khóa `knowledge.upload.files`}" |
| khóa `knowledge.colVisibility` | hộp chọn cao 44px; ô hiển thị `public` + khóa `scope.global` hoặc `corporate_fare` + khóa `scope.department` | mục `global` (biểu tượng `public`, khóa `scope.global`), mục `department` (`corporate_fare`, khóa `scope.department`). Đổi giá trị → bỏ chọn phòng ban |
| "Target Departments" (khi `department`) | danh sách checkbox phòng ban trong khung viền, cuộn tối đa 200px | không bắt buộc chọn |

- Xung đột (máy chủ trả 409, JSON lỗi có `detail.conflicts`: mảng tên): khung đỏ nhạt, biểu tượng `warning` + "Duplicate names detected"; dòng "Existing skills: {tên1, tên2}. Overwrite them?"; checkbox "I confirm to overwrite".
- Nút gửi (chân): "Start Upload" / khi đang gửi "Processing..."; vô hiệu khi đang gửi, chưa chọn tệp, hoặc có xung đột mà chưa tick xác nhận.
- Gửi `POST /api/skills/upload` multipart: mỗi tệp một trường `files`; `scope_type`; nếu `department` và có chọn: mỗi id một trường `department_ids` và `scope_id` = id đầu tiên; nếu đã tick ghi đè: `force` = `true`.
- Thành công → báo trang tải lại danh sách, đóng, đặt lại form. Lỗi khác 409 → alert thông điệp (hoặc khóa `common.error`). Đóng hộp thoại luôn đặt lại form (tệp, phạm vi về global, phòng ban, ghi đè, xung đột).

---

## 6. Hộp thoại Đóng góp (tạo đề xuất kỹ năng)

### 6.1 Đầu vào và chế độ

Đầu vào: `skillId?`, `skillName?`, `versions?` (mảng `{version_number}`), `onContributionCreated(id)`, `trigger?` (nút kích hoạt tùy biến), `allDepartments?`.

- Chế độ **cải tiến** (fork) khi có `skillId`; chế độ **mới** khi không có.
- Nút kích hoạt chỉ hiện khi `canAccess("skill","create")`; mặc định là nút viền chữ primary, biểu tượng `edit_square`, chữ "Contribute".
- Khi ở chế độ mới mà không được truyền `allDepartments`: tự gọi `GET /api/departments`.

### 6.2 Nội dung

- Khung ~500px, là một form.
- Tiêu đề: "Contribute to {skillName}" (cải tiến) / "Create New Skill" (mới). Mô tả: "Propose changes to improve this skill." / "Propose a brand new skill to the Arkon platform."
- Chỉ chế độ mới:
  - "Title": ô nhập bắt buộc, placeholder "e.g. SRS-writing-skill". Hợp lệ khi chỉ gồm chữ Latin, chữ số, khoảng trắng, "-", "_" và chữ tiếng Việt có dấu; sai → viền đỏ + "Title contains invalid characters. Use only letters, numbers, spaces, - and _."
  - "Visibility": hộp chọn cao 44px, ô hiển thị `public` "Global" hoặc `corporate_fare` "Department"; mục "Global (All Departments)" và "Specific Departments". Đổi → bỏ chọn phòng ban.
  - "Target Departments" (khi Department): danh sách checkbox, cuộn tối đa 160px.
- Chỉ chế độ cải tiến và có phiên bản: "Base Version": hộp chọn, placeholder "Select version", mục "Version {n}". Giá trị đầu = phần tử đầu của `versions` tại thời điểm hộp thoại được dựng (nếu danh sách phiên bản về sau thì để trống → gửi null).
- Tiêu đề ở chế độ cải tiến không hiển thị; giá trị gửi đi = "Improve {skillName}".
- Nút gửi (rộng toàn phần trên di động): "Start Improving" / "Start Creating"; khi đang xử lý "Initializing..."; vô hiệu khi đang xử lý, tiêu đề sai, hoặc phạm vi Department mà chưa chọn phòng ban.

### 6.3 Gửi

1. Chế độ mới: kiểm tra trùng bằng `GET /api/skills?q={title}&limit=1`; nếu một mục có `name` trùng tiêu đề (không phân biệt hoa thường) → hiện lớp cảnh báo (6.4) và dừng. Lỗi kiểm tra → bỏ qua.
2. `POST /api/skill-contributions` thân: `skill_id` (id kỹ năng khi cải tiến, null khi mới), `base_version` (số phiên bản đã chọn hoặc null), `title`, `scope_type` (`global` nếu có `skill_id`, ngược lại giá trị đã chọn), `scope_ids` (null nếu có `skill_id`; ngược lại mảng phòng ban khi Department hoặc mảng rỗng) → `{id}`.
3. Thành công → `onContributionCreated(id)` (trang mở Trình soạn) và đóng. Lỗi → alert thông điệp hoặc "Failed to create contribution".

### 6.4 Lớp cảnh báo trùng tên

Phủ toàn hộp thoại (nền mờ), thẻ giữa ~400px: vòng tròn vàng nhạt chứa `warning`; tiêu đề serif nghiêng đậm "Skill Already Exists"; câu "A skill named **"{tên}"** already exists. Would you like to contribute to the existing skill instead?"; nút chính "Yes, contribute to existing" → tạo đề xuất với `skill_id` = id kỹ năng trùng, `base_version` = null (phiên bản mới nhất); nút ghost "No, I'll change the name" → ẩn lớp cảnh báo.

---

## 7. Trình soạn đề xuất (SkillEditor)

### 7.1 Đầu vào

`contributionId` (bắt buộc), `mode` (`edit` | `review`, mặc định `review`), `onSubmitted?`, `onStatusChange?` (được chấp nhận nhưng trình soạn không tự gọi; việc gửi/duyệt do hộp thoại bao ngoài làm).

### 7.2 API

| Mục đích | API |
|---|---|
| Siêu dữ liệu đề xuất (khi `contributionId` đổi) | `GET /api/skill-contributions/{id}` → dùng `skill_id`, `base_version`, `status`, `title` |
| Danh sách tệp | `GET /api/skill-contributions/{id}/files` → mảng `{path, size, is_text}` |
| Trạng thái khác biệt (sau mỗi lần tải danh sách tệp và sau mỗi lần lưu) | `GET /api/skill-contributions/{id}/diff-status` → đối tượng ánh xạ đường dẫn → `M` (sửa) / `A` (thêm) / `D` (xóa) |
| Nội dung tệp | `GET /api/skill-contributions/{id}/files/content?path={đường dẫn}` → `{content}` |
| Nội dung gốc để so sánh | `GET /api/skills/{skill_id}/files/content?path={đường dẫn}&version={base_version}` (bỏ `version` nếu null) |
| Lưu / tạo tệp / tạo thư mục | `PUT /api/skill-contributions/{id}/files` thân `{path, content}` |
| Tải tệp lên | `POST /api/skill-contributions/{id}/upload?path={thư mục}/{tên tệp}` multipart trường `file` |
| Xóa tệp/thư mục | `DELETE /api/skill-contributions/{id}/files?path={đường dẫn}` |
| Đổi tên | `POST /api/skill-contributions/{id}/rename?old_path={cũ}&new_path={mới}` |

Mọi đường dẫn trong query được mã hóa URL.

### 7.3 Danh sách tệp và cây

- Danh sách hiển thị: chế độ `edit` = đúng danh sách tệp; chế độ `review` = danh sách tệp cộng thêm mọi đường dẫn có trạng thái `D` chưa có trong danh sách (coi là tệp văn bản, kích thước 0) để xem được phần bị xóa.
- **Thư mục gốc** = đoạn đầu tiên (trước "/") của đường dẫn tệp đầu tiên trong danh sách hiển thị.
- Dựng cây bằng cách tách đường dẫn theo "/"; mỗi cấp xếp thư mục trước, tệp sau, cùng loại thì theo thứ tự chữ cái (so sánh theo ngôn ngữ). Nút tên ".gitkeep" bị ẩn (dùng để giữ thư mục rỗng).
- Mọi thư mục mặc định **thu gọn**; bấm dòng thư mục để mở/đóng.
- Lựa chọn ban đầu (khi chưa chọn gì): tệp có đường dẫn kết thúc bằng "skill.md" (không phân biệt hoa thường), nếu không có thì tệp đầu tiên.
- Lỗi tải danh sách: mã 400 → tải lại toàn trang; lỗi khác → thay toàn bộ trình soạn bằng màn "chỉ đọc": vòng tròn hổ phách nhạt chứa `lock`, tiêu đề "Read Only Mode", dòng "An error occurred while loading files."

### 7.4 Chọn tệp và tải nội dung

- Chọn một tệp: nếu là văn bản, hoặc có trạng thái khác biệt (tệp mới) → tải nội dung; ngược lại nội dung = rỗng-không-xem-được ("Binary file or no preview available.").
- Tệp trạng thái `D`: không gọi máy chủ, nội dung = chuỗi rỗng. Lỗi tải nội dung → chuỗi rỗng.
- Nội dung gốc (để so sánh) chỉ tải khi đã có siêu dữ liệu, đề xuất có `skill_id`, và (đề xuất đang `pending` **hoặc** người dùng là admin **hoặc** có `skill:contribution:review`). Thử trước với đường dẫn đã bỏ tiền tố "{thư mục gốc}/", thất bại thì thử đường dẫn nguyên; thất bại cả hai → không có bản gốc (tệp mới; so sánh với chuỗi rỗng).
- Mỗi lần đổi tệp: trạng thái lưu về "Ready", xóa bản gốc cũ.

### 7.5 Lưu tự động, trạng thái "bẩn", phím tắt

- "Bẩn" = nội dung hiện tại khác nội dung đã lưu gần nhất. Khi bẩn, sau 500ms không gõ thêm sẽ tự lưu `PUT …/files` với `{path: tệp đang chọn, content}`; chỉ lưu khi `mode` = `edit`. Thành công → cập nhật mốc "đã lưu", trạng thái "All Saved", tải lại bảng khác biệt. Lỗi → "Save Error".
- Ở chế độ `review` vùng văn bản vẫn gõ được nhưng **không** được lưu (chỉ báo "Ready").
- Không có nút Lưu thủ công, không có phím tắt bàn phím (không Ctrl+S), không có cảnh báo khi đóng lúc còn thay đổi chưa lưu (vì lưu tự động sau 0,5 giây).
- Chỉ báo trạng thái lưu (ở đầu vùng chính): viên nhỏ nền phụ có chấm tròn 6px + chữ in hoa 10px:

| Trạng thái | Chấm | Chữ |
|---|---|---|
| nghỉ | xám mờ | "Ready" |
| đang lưu | hổ phách, nhấp nháy | "Saving..." |
| đã lưu | xanh lục | "All Saved" |
| lỗi | đỏ | "Save Error" |

### 7.6 Bố cục

Nền card, chiếm toàn bộ chiều cao được cấp; cột trên di động, hàng ngang từ ≥1024px.

**Thanh bên trái** (rộng 320px từ ≥1024px, nền phụ rất nhạt, kẻ phải):
- Đầu: chữ in hoa nhỏ giãn rộng "Files"; bên phải nút biểu tượng `refresh` 28px tooltip "Refresh" (tải lại danh sách). Một ô chọn tệp ẩn dùng cho "Upload File".
- Thân cuộn (ẩn thanh cuộn), đệm 12px: khi tải hiện chữ mờ "Loading..."; sau đó là cây.
- **Dòng thư mục** (chữ 13px màu muted, rê → nền muted nhạt và chữ đậm màu): thụt trái 8px + 16px mỗi cấp; `chevron_right` (xoay 90° khi mở); biểu tượng `folder` / `folder_open` màu hổ phách; tên (đậm vừa, cắt bớt); huy hiệu trạng thái (7.7); nút `more_vert` 28px tooltip "Actions" chỉ hiện khi rê vào dòng. Menu (rộng ~160px, căn phải), mỗi mục có biểu tượng:
  - `add_box` "New File" (7.8)
  - `create_new_folder` "New Folder"
  - `upload_file` "Upload File"
  - `edit` "Rename" — vô hiệu với thư mục gốc
  - `delete` "Delete" (kiểu nguy hiểm) — vô hiệu với thư mục gốc
- **Dòng tệp**: thụt trái 32px + 16px mỗi cấp; biểu tượng `article` nếu tên kết thúc ".md", ngược lại `description`; tên; huy hiệu trạng thái. Đang chọn → nền primary nhạt, chữ primary đậm, nút menu luôn hiện; không chọn → nút menu chỉ hiện khi rê. Menu: `edit` "Rename", `delete` "Delete" — cả hai vô hiệu với "{thư mục gốc}/SKILL.md".
- Menu thao tác hiện ở cả hai chế độ.

**Vùng chính**:
- Chưa chọn tệp: giữa vùng, mờ 30%: biểu tượng `edit_note` rất lớn, chữ in hoa đậm "Select a file to start editing".
- Đã chọn — thanh đầu (kẻ dưới): bên trái đường dẫn trong ô monospace đậm có viền mảnh (tối đa 300px, cắt bớt). Bên phải:
  - Với tệp ".md" (không phân biệt hoa thường): nhóm phân đoạn hai nút nhỏ in hoa "Edit" | "Preview" trên nền muted; nút đang chọn có nền phụ và bóng nhẹ. Bấm bất kỳ nút nào cũng tắt chế độ Diff.
  - Chỉ chế độ `review`: nút bật/tắt "Diff" có biểu tượng `difference` (đang bật → nền phụ, bóng).
  - Chỉ báo trạng thái lưu (7.5).
- Thân theo thứ tự ưu tiên:
  1. Đang tải: chữ mờ giữa "Loading content...".
  2. Không có nội dung xem được: "Binary file or no preview available."
  3. Bật Diff: Trình xem khác biệt (7.9) giữa bản gốc (rỗng nếu không có) và nội dung hiện tại.
  4. Tệp ".md" ở "Preview": chia đôi ngang có vạch ngăn — trái là vùng văn bản monospace 13px sửa được (placeholder "Enter markdown here..."), phải là Markdown đã kết xuất (GFM, phần frontmatter YAML bị ẩn) theo kiểu 0.4; hai bên cuộn độc lập.
  5. "Edit" (mặc định): vùng văn bản monospace 13px chiếm toàn vùng, không viền, không đổi kích thước, ẩn thanh cuộn, placeholder "Enter code or markdown here...".
  6. Trường hợp còn lại (tệp không phải ".md" trong khi đang ở "Preview" từ tệp trước): Markdown kết xuất chỉ đọc, căn giữa, rộng tối đa ~896px.

### 7.7 Huy hiệu trạng thái khác biệt (chỉ chế độ `review`)

Vòng tròn 16px, chữ đậm 9px, viền, con trỏ "help", tooltip:

| Mã | Tooltip | Tông |
|---|---|---|
| `M` | "Modified" | hổ phách |
| `A` | "Added" | xanh lục |
| `D` | "Deleted" | đỏ |

Thư mục: gom trạng thái mọi tệp con cháu (tệp không có trạng thái tính là "không đổi"). Không có trạng thái thay đổi nào → không huy hiệu; đúng một loại và **mọi** tệp con cháu đều mang loại đó → huy hiệu loại đó; còn lại → `M`.

### 7.8 Thao tác tệp

- **Thư mục cơ sở** cho tạo mới = thư mục được bấm; nếu không có thì thư mục gốc; nếu chưa có tệp nào thì dạng slug của tiêu đề đề xuất (bỏ tiền tố "Upload: "; slug = chữ thường, khoảng trắng → "-", bỏ ký tự không phải chữ/số/gạch dưới/gạch nối, gộp nhiều "-" liên tiếp); cuối cùng là "skill".
- **New File**: prompt "Enter file name inside {cơ sở}/ (e.g. src/utils.py):"; bỏ trống/hủy → không làm gì. Đường dẫn = "{cơ sở}/{tên}" (bỏ các "/" ở đầu tên; tên có thể chứa thư mục con). `PUT …/files` với nội dung rỗng → tải lại danh sách → chọn tệp mới, chuyển sang "Edit". Lỗi chỉ ghi log.
- **New Folder**: prompt "Enter folder name inside {cơ sở}/:"; tạo tệp rỗng "{cơ sở}/{tên}/.gitkeep" bằng `PUT …/files` → tải lại danh sách.
- **Upload File**: ghi nhớ thư mục đích rồi mở hộp chọn tệp (một tệp, mọi loại). Gửi `POST …/upload?path={đích}/{tên tệp}` → tải lại danh sách, chọn tệp mới. Lỗi → alert "Upload failed".
- **Delete**: thư mục gốc → alert "Cannot delete the root folder."; "{gốc}/SKILL.md" → alert "Cannot delete the SKILL.md file.". Confirm "Are you sure you want to delete this {file|folder}: {đường dẫn}?" → `DELETE …/files?path=` → tải lại; nếu tệp đang chọn là mục bị xóa hoặc nằm trong thư mục bị xóa thì bỏ chọn. Lỗi → alert "Delete failed: {thông điệp | Unknown error}".
- **Rename**: chặn thư mục gốc ("Cannot rename the root folder.") và SKILL.md gốc ("Cannot rename the SKILL.md file."). Prompt "Enter new name for {file|folder}:" với giá trị sẵn là tên cũ; rỗng hoặc không đổi → thôi. Đường dẫn mới = cùng thư mục cha + tên mới. `POST …/rename` → tải lại; cập nhật lựa chọn nếu tệp đang chọn là mục đổi tên hoặc nằm trong thư mục đổi tên. Lỗi → alert "Rename failed: …".

### 7.9 Trình xem khác biệt

- Chuẩn hóa xuống dòng CRLF thành LF ở cả hai bên, so sánh theo dòng (thư viện so khác biệt theo dòng, ví dụ gói `diff`).
- Phông monospace 13px, cuộn dọc (ẩn thanh cuộn). Hàng tiêu đề dính trên cùng, chữ in hoa 10px: cột "Line" rộng 100px | "Content".
- Mỗi dòng: ô số dòng 100px chia đôi (số dòng cũ | số dòng mới, căn phải, chữ 10px, không chọn được), rồi nội dung (giữ khoảng trắng, xuống dòng cả từ dài; dòng rỗng hiển thị một khoảng trắng):
  - Không đổi: cả hai số tăng; chữ mờ 70%, rõ khi rê.
  - Bị xóa: nền đỏ nhạt; số cũ, cột mới hiện "-"; nội dung có tiền tố "-" mờ.
  - Được thêm: nền xanh lục nhạt; cột cũ "-", số mới; tiền tố "+".

---

## 8. Khối đề xuất trên trang danh sách

### 8.1 "Đề xuất của tôi"

- Tải một lần: `GET /api/skill-contributions` → mảng `{id, title, status (draft|pending|approved|rejected), updated_at, scope_type, scope_ids}`; bỏ các mục `approved`. Lỗi chỉ ghi log. Không thăm dò định kỳ (tham số chu kỳ được nhận nhưng không dùng).
- Không có mục nào (hoặc đang tải lần đầu) → không hiển thị gì.
- Khung: viền mờ, nền trong mờ, bo góc, đệm 12px. Tiêu đề: biểu tượng `pending_actions` (primary nhạt) + "Đề xuất của tôi" + viên đếm số lượng (nền primary nhạt, chữ primary đậm).
- Mỗi dòng (ngăn bằng đường kẻ mờ):
  - Tiêu đề (cắt bớt, tooltip đầy đủ, rê → primary) — bấm để mở Trình soạn (1.9).
  - Nhãn trạng thái: `draft` "Bản nháp" (hổ phách), `pending` "Chờ duyệt" (xanh dương), `rejected` "Bị từ chối" (đỏ), `approved` "Đã duyệt" (xanh lục); giá trị lạ → hiển thị nguyên văn, tông muted.
  - Từ ≥640px: phạm vi — nếu `department` và có `scope_ids` thì nối tên các phòng ban tìm được bằng ", ", ngược lại "Toàn hệ thống" (tối đa ~160px, tooltip).
  - Từ ≥768px: thời gian sửa dạng "dd/mm/yy HH:MM" (số cách đều).
  - Nút `edit` tooltip/aria "Tiếp tục soạn" → mở Trình soạn.
  - Nút `delete` tooltip/aria "Xóa bản nháp" (đỏ khi rê): confirm "Xóa đề xuất này? Không thể hoàn tác." → `DELETE /api/skill-contributions/{id}` → tải lại khối và danh sách kỹ năng. Lỗi → alert "Delete failed".
  - (Nếu mục là `approved` thì bấm chỉ gỡ khỏi khối.)

### 8.2 "Chờ tôi duyệt"

- Chỉ tải khi `canAccess("skill","review")` hoặc `hasPermission("skill:contribution:review")`: `GET /api/admin/skill-contributions` (hoặc thêm `?skill_id={id}` khi được truyền `skillId`) → mảng `{id, title, skill_id?, contributor_name, status, created_at}`. Kết quả đẩy lên trang qua callback; nếu trang truyền danh sách thì hiển thị danh sách của trang. Tải một lần, không thăm dò.
- Rỗng → không hiển thị gì.
- Khung như 8.1. Tiêu đề: `rate_review` + "Chờ tôi duyệt" + viên đếm. Danh sách cuộn tối đa ~192px.
- Mỗi dòng là một nút → mở hộp thoại duyệt: tiêu đề (nếu có `skill_id` thì là `title`, nếu không thì "Kỹ năng mới: {title | Chưa đặt tên}"; rê → primary); từ ≥640px tên người gửi; từ ≥768px thời gian tạo theo định dạng Việt Nam "dd/mm/yyyy HH:mm" 24 giờ; biểu tượng `arrow_forward` mờ, rê → primary.

### 8.3 Vòng đời đề xuất

| Trạng thái | Ý nghĩa | Chuyển tiếp từ giao diện |
|---|---|---|
| `draft` | bản nháp, người tạo đang soạn (lưu tự động) | tạo bằng `POST /api/skill-contributions`; "Gửi duyệt" → `pending`; "Xóa bản nháp" → xóa hẳn |
| `pending` | chờ người duyệt | người có quyền duyệt: "Duyệt & hợp nhất" → `approved` (hợp nhất vào thư viện, tạo kỹ năng mới hoặc phiên bản mới); "Từ chối" → `rejected` |
| `approved` | đã hợp nhất | không hiện trong "Đề xuất của tôi" |
| `rejected` | bị từ chối | vẫn hiện trong "Đề xuất của tôi", có thể mở lại hoặc xóa |

Ngoài ra, khi người dùng không có quyền ghi trực tiếp, việc tạo/sửa nhanh (mục 4) có thể trả `contribution_pending`, tức máy chủ đã tự sinh một đề xuất chờ duyệt.

---

## 9. Trình duyệt tệp kỹ năng (SkillFileExplorer — chỉ đọc)

### 9.1 Đầu vào và API

`skillId`, `version?` (số hoặc null).

- `GET /api/skills/{skillId}/files` (thêm `?version={n}` nếu có) → mảng `{path, size, last_modified, is_text}`.
- `GET /api/skills/{skillId}/files/content?path={đường dẫn}` (thêm `&version={n}`) → `{content}`.
- Đổi `skillId`/`version` → xóa sạch trạng thái và tải lại; chỉ tải nội dung khi danh sách tệp đã khớp phiên bản đang xem.
- Lựa chọn tự động: tệp kết thúc "skill.md" (không phân biệt hoa thường) → nếu không thì tệp văn bản đầu tiên → nếu không thì không chọn.
- Xử lý nội dung trước khi hiển thị: bỏ khối frontmatter YAML ở đầu tệp (giữa hai dòng "---"), bỏ các dấu đánh dấu nội bộ dạng hai gạch nối + đúng 4 ký tự chữ/số + hai gạch nối, rồi cắt khoảng trắng hai đầu.
- Tệp văn bản lớn hơn 2 MB → không tải, hiện màn "quá lớn". Tệp không phải văn bản → màn "không xem trước". Lỗi tải nội dung → hiển thị chữ "Error loading file content.".

### 9.2 Bố cục

Thẻ nền card, viền, bo góc lớn, bóng nhẹ, **cao cố định 800px**; cột trên di động, ngang từ ≥1024px.

- **Thanh bên** (320px, nền phụ rất nhạt): đầu cao 61px có biểu tượng `account_tree` (primary nhạt) + chữ in hoa nhỏ "Skill Explorer". Thân cuộn (ẩn thanh cuộn):
  - Đang tải: 8 thanh xương 32px nhấp nháy.
  - Rỗng: mờ 40%, `folder_open` lớn + "No files available in this package."
  - Cây như 7.3/7.6 nhưng không có menu thao tác và huy hiệu; thư mục mặc định thu gọn, chevron xoay có chuyển động; biểu tượng tệp: ".md" → `article`, văn bản → `description`, nhị phân → `draft`. Tệp đang chọn: nền primary nhạt, chữ primary đậm, vạch dọc mảnh bên trái cùng màu.
- **Vùng chính**:
  - Chưa chọn: mờ 30%, vòng tròn 128px nền primary rất nhạt nhấp nháy chứa `account_tree` rất lớn; chữ serif cỡ lớn "Skill Explorer"; dòng in hoa nhỏ "Select a file from the tree to preview its content".
  - Đã chọn — đầu cao 61px: đường dẫn trong ô monospace; bên phải nút viền nhỏ in hoa `content_copy` "Copy" (khi đã có nội dung; chép nội dung đang hiển thị vào clipboard; nên ẩn ở màn "quá lớn") và kích thước tệp monospace 10px ("{n} B", "{x.x} KB", "{x.x} MB").
  - Thân (cuộn, ẩn thanh cuộn; nền card nhạt cho ".md", nền phụ cho tệp khác):
    - Đang tải: `progress_activity` xoay lớn mờ + chữ in hoa "Loading content...".
    - Quá lớn: nền vàng rất nhạt, chữ vàng; vòng tròn chứa `warning`; "File Too Large" / "This file exceeds the 2MB preview limit."
    - ".md": Markdown GFM kết xuất (kiểu 0.4), đệm lớn (40–64px), căn giữa, rộng tối đa ~896px.
    - Văn bản khác: khối preformatted 13px, giữ khoảng trắng, đệm 32px.
    - Không phải văn bản: mờ 40%, vòng tròn chứa `visibility_off`; "No Preview Available" / "Binary or non-text files cannot be previewed."

---

## 10. Trang quản trị đề xuất — `/admin/skill-contributions`

- **Quyền**: khi đã có thông tin user mà `role` khác `admin` → chuyển về `/`. (Không kiểm tra quyền chi tiết khác.)
- **Tải**: `GET /api/admin/skill-contributions` → mảng `{id, skill_id, contributor_id, contributor_name, title, description, status, created_at, updated_at}`.
- **Đầu trang**: tiêu đề "Contribution Management", mô tả "Review and approve AI skill proposals from the team."
- **Khung danh sách**: thẻ nền card, viền mờ, bo góc lớn.
  - Đang tải: spinner giữa, đệm dọc 96px.
  - Rỗng: `rate_review` rất lớn mờ 20% + "No pending contributions at the moment."
  - Mỗi dòng (kẻ ngăn, đệm 24px, rê → nền muted nhạt): ô 48px nền primary nhạt chứa `edit_note`; tiêu đề serif đậm (rê dòng → primary); mô tả 1 dòng hoặc "No description provided."; hàng phụ chữ nhỏ: `person` + `contributor_name`, `calendar_today` + ngày tạo (định dạng ngày mặc định của trình duyệt), viên in hoa tông hổ phách "Pending Review" (luôn hiện). Bên phải nút viền chữ primary `visibility` "Review" → hộp thoại duyệt.
- **Hộp thoại duyệt**: khung như 1.10; tiêu đề "Review Contribution", "Submitted by **{contributor_name}**"; nút "Reject" và "Approve & Merge"; nút đóng chỉ biểu tượng `close`. Confirm/alert tiếng Anh như 2.8; thành công → đóng và tải lại danh sách; lỗi → alert, không đóng. Trình soạn chế độ mặc định `review`.

---

## 11. Trang Kho prompt — `/prompts`

### 11.1 Kiểu dữ liệu `PromptTemplate`

| Trường | Kiểu |
|---|---|
| `id` | string |
| `title` | string |
| `command` | string (lệnh gõ sau "/") |
| `description` | string \| null |
| `content` | string |
| `tags` | string[] |
| `scope_type` | `personal` \| `department` \| `global` |
| `department_ids` | string[] |
| `department_names` | string[] |
| `owner_id` | string \| null |
| `owner_name` | string \| null |
| `source` | string (vd `chatbot` khi được tạo từ chatbot) |
| `can_edit` | boolean (máy chủ tính quyền sửa/xóa) |
| `updated_at` | string ISO |

### 11.2 Tải dữ liệu

- `GET /api/prompts?limit=500&q={chuỗi tìm đã cắt khoảng trắng}` (bỏ `q` nếu rỗng), trễ 200ms sau lần gõ cuối → `{items: PromptTemplate[]}`. Lỗi → rỗng.
- `GET /api/departments` khi vào trang.

### 11.3 Bố cục

1. **Đầu trang**: tiêu đề "Kho prompt"; mô tả "Mẫu yêu cầu dùng chung cho chatbot: trong ô chat gõ / rồi chọn lệnh để chèn. Mỗi cán bộ thấy prompt cá nhân, của đơn vị mình và toàn hệ thống."; nút primary nhỏ `add` "Tạo prompt" (mọi người dùng) → hộp thoại tạo trống.
2. **`ScopeFilterBar`** (của c2): `search`/`onSearch` = state tìm của trang; `placeholder` "Tìm theo tiêu đề, lệnh, nội dung..."; `scope`/`onScope` mặc định `all`; `counts` = `countByScope(danh sách sau lọc thẻ, phòng ban đã chọn)`; `withPersonal` để mặc định (có mục "Cá nhân"); `departments`; `department`/`onDepartment`; `total` = "{số hiển thị} prompt".
3. **Hàng thẻ nhãn** (chỉ khi có ít nhất một nhãn; sát dưới thanh lọc): mọi nhãn duy nhất từ tất cả prompt, sắp chữ cái; mỗi nhãn là viên tròn có viền, chữ 11px "#{nhãn}". Bấm → chọn nhãn đó (chỉ một nhãn một lúc), bấm lại → bỏ. Đang chọn: viền primary, nền primary nhạt, chữ primary.
4. **Thứ tự lọc**: lọc theo nhãn trước → tính số đếm → `filterByScope(…, phạm vi, phòng ban)`.
5. **Nội dung**:
   - Đang tải lần đầu: spinner giữa.
   - Rỗng: EmptyState biểu tượng `chat_paste_go`; tiêu đề "Không có prompt phù hợp" (khi có tìm/nhãn/phạm vi/phòng ban) hoặc "Chưa có prompt nào"; mô tả "Tạo mẫu yêu cầu dùng lại cho các việc thường gặp: tóm tắt, soạn báo cáo, kiểm tra thể thức..."
   - Lưới thẻ 1/2/3 cột (≥768px / ≥1280px), khoảng cách 12px.
6. Hộp thoại tạo/sửa (11.5) và thông báo nổi (3 giây).

### 11.4 Thẻ prompt (`LibraryCard`, không có `onOpen` — thẻ không bấm được)

| Thuộc tính | Giá trị |
|---|---|
| `icon` | `chat_paste_go` (tông mặc định) |
| `title` | `title` |
| `badge` | "/{command}" |
| `description` | `description` |
| `meta` | "Bạn" nếu `owner_id` trùng id người dùng, ngược lại `owner_name` hoặc "—"; tiếp " · " và `fmtDate(updated_at)` |

Thao tác (`IconBtn`):

| Nút | Điều kiện | Hành động |
|---|---|---|
| `content_copy` "Sao chép nội dung" | luôn | chép `content` vào clipboard → thông báo "Đã sao chép nội dung" (bị chặn thì im lặng) |
| `library_add` "Nhân bản" | luôn | mở hộp thoại **tạo** điền sẵn từ prompt này với tiêu đề "{title} (bản sao)", lệnh "{command}-2", phạm vi `personal`, không phòng ban |
| `edit` "Sửa" | `can_edit` | mở hộp thoại sửa prompt này |
| `delete` "Xóa" (nguy hiểm) | `can_edit` | confirm `Xóa prompt "{title}" (/{command})?` → `DELETE /api/prompts/{id}` → gỡ khỏi danh sách, thông báo "Đã xóa prompt"; lỗi → alert "Xóa thất bại: {thông điệp}" |

Nhãn: `ScopeChip` (`scope_type`, `department_names`); nếu `source` = `chatbot` thêm `Chip` biểu tượng `smart_toy` tông tím "Từ chatbot"; sau đó mỗi nhãn là chữ thường "#{nhãn}".

Phần thân (children): nút xem trước nội dung, nền muted nhạt, bo góc, chữ 12px giữ xuống dòng, mặc định cắt 4 dòng; bấm → mở rộng toàn bộ (chỉ một thẻ mở rộng một lúc), bấm lại → thu gọn; tooltip "Xem đầy đủ" / "Thu gọn".

Lưu xong (từ hộp thoại): thông báo "Đã lưu prompt" (sửa) hoặc "Đã tạo prompt" (tạo); bản ghi trả về được đưa lên đầu danh sách (thay bản cũ cùng id).

### 11.5 Hộp thoại Tạo / Sửa prompt

- Đầu vào: `open`, `onOpenChange`, `prompt` (có → sửa), `initial` (điền sẵn khi tạo), `departments`, `onSaved(prompt đã lưu)`.
- Khi mở: nạp giá trị từ `prompt` hoặc `initial` (hoặc rỗng): tiêu đề, lệnh, mô tả, nội dung, nhãn (nối bằng ", "), phạm vi (mặc định `personal`), phòng ban. Lệnh coi là "đã chạm" nếu nguồn có lệnh.
- Khung rộng tối đa ~672px, cao tối đa 92% viewport; đầu/chân cố định, thân cuộn. Không đóng được khi đang lưu.
- Đầu: tiêu đề "Sửa prompt" / "Tạo prompt"; mô tả "Mẫu yêu cầu dùng lại trong chatbot: gõ /lệnh để chèn nội dung." ("/lệnh" phông monospace).
- Lưới 2 cột từ ≥640px (nhãn ~120px):

| Nhãn | Điều khiển | Hành vi |
|---|---|---|
| "Tiêu đề" | ô nhập 36px, placeholder "vd: Tóm tắt văn bản chỉ đạo" | khi lệnh chưa "chạm", mỗi lần gõ tiêu đề tự sinh lệnh = hàm chuẩn hóa tên kỹ năng (4.1) áp lên tiêu đề, cắt 60 ký tự |
| "Lệnh" | ô ghép: tiền tố "/" màu muted monospace + ô nhập monospace không viền, placeholder "tom-tat-van-ban"; khung có vòng focus | gõ → đánh dấu "đã chạm", giá trị được chuẩn hóa như tên kỹ năng và chỉ giữ chữ thường, chữ số, "_" , "-" |
| "Mô tả" | ô nhập, placeholder "Dùng khi nào (không bắt buộc)" | |
| "Nhãn" | ô nhập, placeholder "vd: văn bản, tổng hợp (cách nhau bởi dấu phẩy)" | |
| "Phạm vi" | Bộ chọn phạm vi (Phụ lục A) **có** "Cá nhân" | |

- Dưới lưới: nhãn "Nội dung"; bên phải "Chèn biến:" và ba nút nhỏ monospace nền muted: "{{nội_dung}}", "{{CLIPBOARD}}", "{{CURRENT_DATE}}" — bấm → nối biến vào cuối nội dung (thêm một dấu cách trước nếu nội dung không rỗng và không kết thúc bằng khoảng trắng hoặc xuống dòng). Vùng văn bản cao tối thiểu ~224px, placeholder ví dụ yêu cầu tóm tắt thành 5 ý chính, kết thúc bằng biến "{{nội_dung}}". Dòng phụ: "Biến {{tên}} sẽ được hỏi khi người dùng chọn prompt trong chatbot."
- Lỗi: chữ đỏ nhỏ dưới thân.
- Chân: ghost "Hủy"; primary `save` (spinner khi lưu) + "Lưu" (sửa) / "Tạo prompt" (tạo).
- **Hợp lệ**: tiêu đề không rỗng (sau cắt); lệnh (bỏ "-" cuối) bắt đầu bằng chữ thường hoặc chữ số và tiếp theo tối đa 99 ký tự chữ thường/chữ số/"_"/"-" (dài 1–100); nội dung không rỗng (sau cắt); nếu phạm vi theo phòng ban thì chọn ít nhất một.
- **Lưu**: thân JSON `{title (cắt), command (bỏ "-" cuối), description (cắt), content (nguyên văn), tags (tách theo dấu phẩy, cắt, bỏ rỗng), scope_type, department_ids (chỉ khi department, ngược lại rỗng)}`. Sửa → `PATCH /api/prompts/{id}`; tạo → `POST /api/prompts`; cả hai trả `PromptTemplate`. Thành công → `onSaved`, đóng. Lỗi → thông điệp hoặc "Lưu thất bại".

---

## 12. Thành phần kỹ năng phụ (có trong nguồn nhưng hiện **không** gắn vào trang nào)

Các thành phần dưới đây thuộc `components/skills` nhưng không trang nào hiển thị. Chỉ cần dựng nếu muốn tương đương mã nguồn đầy đủ; không ảnh hưởng hành vi các trang trên.

### 12.1 Thẻ kỹ năng kiểu cũ

Thẻ nền card, đệm 20px, viền, bóng nhẹ, rê → viền primary nhạt; khi `deleting` con trỏ "cấm" và mờ 80%, không mở được. Trên: ô 24px chứa `auto_awesome` mờ; tên (rê → primary); hàng phụ: huy hiệu "v{n}", danh sách phòng ban (mỗi tên kèm `corporate_fare`, chữ in hoa nhỏ) hoặc `public` + khóa `scope.global`; trạng thái in hoa (`active` xanh lục, `deleting` đỏ nhấp nháy, khác vàng). Dưới (kẻ trên): ngày dd/mm/yyyy; các nút chữ nhỏ: khóa `skills.details` (mở), khóa `common.edit` (khi `canAccess("skill","edit")`), khóa `common.delete` màu đỏ (khi `canAccess("skill","delete")`); vô hiệu khi `deleting`. Kiểu `Skill` (0.5) được export từ module này và các module khác import.

### 12.2 Hộp thoại tìm kỹ năng nhanh

- Mở → `GET /api/skills?limit=1000` (dùng `items`); tự focus ô tìm sau 50ms; đóng → xóa chuỗi tìm.
- Khung ~512px, nền mờ kính. Hàng tìm: `search` primary, ô nhập không viền placeholder "Search AI skills by name, description or tags...", nút `close` xóa chuỗi khi có chữ; Esc đóng.
- Lọc phía máy khách (trễ 120ms): tên hoặc mô tả chứa chuỗi (không phân biệt hoa thường).
- Kết quả (cuộn tối đa 400px, thanh cuộn mảnh): tiêu đề nhỏ "Results ({n})"; tối đa 50 dòng: ô 40px nền primary nhạt chứa `bolt` (phóng to nhẹ khi rê), tên đậm, phòng ban đầu tiên dạng huy hiệu, mô tả 1 dòng; rê → nền primary rất nhạt và vạch trái primary. Bấm → gọi callback chọn và đóng.
- Rỗng: `search_off` + `No skills matching "{q}"` hoặc "No skills found."
- Chân: gợi ý phím "↵ select", "↑↓ navigate", "Esc close" (chỉ là chú thích; không có điều hướng bằng phím mũi tên).

### 12.3 Hộp thoại chi tiết gói kỹ năng

- Tải `GET /api/skills/{skillId}/versions`.
- Khung ~1152px, cao 85% viewport. Đầu: ô `terminal`, tiêu đề = tên kỹ năng, phụ đề "Package Explorer"; bên phải: hộp thoại Đóng góp (cải tiến) nếu admin hoặc `canAccess("skill","create")`, và huy hiệu monospace 8 ký tự đầu của id. Thân: Trình duyệt tệp (mục 9) bản hiện hành.
- Tạo đề xuất xong → chuyển sang khung ~1400px × 90% viewport: `edit_note`, "Editing Contribution", "Draft Mode", nút `close` "Close Editor"; Trình soạn chế độ `edit`.

### 12.4 Bộ lọc phòng ban dạng thanh bên

Thẻ bo góc, tiêu đề `corporate_fare` + khóa `skills.colDepartment`; danh sách cuộn tối đa 250px: mục `grid_view` khóa `skills.allDepartments` (chọn khi không lọc) và mỗi phòng ban với `corporate_fare`. Chọn một phòng ban (bấm lại → bỏ). Mục đang chọn: nền primary nhạt, chữ primary đậm, biểu tượng phóng to nhẹ.

### 12.5 Quản lý thẻ (tag)

- Nút kích hoạt viền chữ primary: `sell` + khóa `skills.manageTags`.
- Khung ~550px, cao tối đa 85% viewport. Tiêu đề `sell` + khóa `skills.manageTags`.
- Khi mở và mỗi khi đổi chuỗi tìm (trễ 300ms): `GET /api/tags?q={q}&limit=1000` → `{items: string[], total}`; mỗi lần tải bỏ chọn tất cả.
- Hàng trên: ô tìm có `search`, placeholder khóa `common.search`; nút "Thêm thẻ" (12.6).
- Khung danh sách: hàng đầu có checkbox chọn tất cả + chữ "Select All"/"Unselect All", bên phải "{đã chọn} selected of {total}". Lưới 2 cột các thẻ, mỗi ô checkbox + tên; bấm ô để chọn/bỏ. Đang tải: spinner; rỗng: chữ nghiêng khóa `common.noResults`.
- Chân: ghi chú "* Selected tags can be deleted permanently."; nút destructive `delete` + khóa `common.delete` + " ({n})", vô hiệu khi chưa chọn. Confirm "Are you sure you want to delete {n} tags?" → `DELETE /api/tags/bulk` thân `{names}` → tải lại, báo cập nhật. Lỗi → alert khóa `common.error` + thông điệp.

### 12.6 Thêm thẻ

- Nút primary cao 32px `add` "Add Tags". Khung ~400px; tiêu đề "Add New Tags"; mô tả "Enter tag names separated by commas (e.g. ai, bot, tool-1)."
- Nhãn "Tag Names", ô nhập tự focus, placeholder "tag1, tag2, tag3..."; khi gõ tự loại mọi ký tự ngoài chữ Latin, chữ số, "_", "-", dấu phẩy, khoảng trắng; ghi chú "* Allowed characters: letters, numbers, underscore, hyphen, and comma."
- Nút "Cancel" và "Save Tags" (khi lưu "Saving..."; vô hiệu khi rỗng). Lưu: tách theo dấu phẩy, cắt, bỏ rỗng → `POST /api/tags/bulk` thân `{names}` → đóng, xóa ô, báo cập nhật. Lỗi → alert "Failed to add tags: {detail | thông điệp}".

### 12.7 Gắn thẻ hàng loạt cho kỹ năng

- Đầu vào: `skillIds`, `allTags`, `open`, `onOpenChange`, `onSuccess`. Khung ~450px. Tiêu đề "Add Tags to {n} Skills"; mô tả "Enter or select tags. These will be added to all selected skills."
- Nhãn "Tags"; khung nhập dạng "chip": các thẻ đã chọn là viên tròn tông primary có nút `close` nhỏ để bỏ; ô nhập placeholder "Type to add or search..." (khi chưa có thẻ). Enter hoặc dấu phẩy → thêm giá trị đã cắt, chuyển chữ thường (nếu chưa có). Backspace khi ô rỗng → bỏ thẻ cuối. Gợi ý thả xuống: tối đa 5 thẻ trong `allTags` chứa chuỗi đang gõ và chưa chọn; bấm → chọn.
- Nút "Cancel" / "Add Tags" ("Adding..."; vô hiệu khi chưa chọn). Lưu: `POST /api/skills/bulk/tags` thân `{skill_ids, tags}` → xóa lựa chọn, `onSuccess`, đóng. Lỗi → alert "Failed to add tags to skills: …". Đóng → xóa lựa chọn.

### 12.8 Gỡ thẻ hàng loạt

- Như 12.7 nhưng tông destructive: tiêu đề `label_off` (đỏ) + "Remove Tags from {n} Skills"; mô tả "Select the tags you want to remove from all selected skills."; nhãn "Selected Tags to Remove"; placeholder "Type to search tags..."; không thêm thẻ tự do bằng Enter. Khu gợi ý luôn hiện dạng lưới huy hiệu viền (cuộn tối đa 120px): khi ô rỗng là 10 thẻ đầu; khi gõ là tối đa 10 thẻ khớp chưa chọn; huy hiệu đã chọn tô primary. Nút destructive "Remove Tags" ("Removing..."). Lưu: `POST /api/skills/bulk/tags/remove` thân `{skill_ids, tags}`. Lỗi → alert "Failed to remove tags from skills: …".

---

## Phụ lục A — Bộ chọn phạm vi (ScopePicker, dùng bởi mục 4 và 11.5)

Nếu tài liệu kho tri thức của loạt 07 đã đặc tả thành phần này thì dùng chung; tóm tắt hành vi:

- Thanh phân đoạn full-width nền muted gồm các nút (biểu tượng + chữ, tooltip là gợi ý), vai trò radio:

| Giá trị | Biểu tượng | Chữ | Gợi ý (hiện dưới thanh khi đang chọn) |
|---|---|---|---|
| `personal` (chỉ khi cho phép cá nhân) | `person` | "Cá nhân" | "Chỉ mình bạn xem được" |
| `department` | `apartment` | "Theo phòng ban" | "Chỉ các phòng ban được chọn xem được" |
| `global` | `public` | "Toàn hệ thống" | "Mọi cán bộ đều xem được" |

- Chọn giá trị khác `department` → bỏ chọn mọi phòng ban. Nút đang chọn: nền nền chính, chữ đậm màu, bóng rất nhẹ.
- Khi `department`: khung viền gồm hàng tìm (`search`, placeholder "Tìm phòng ban...", bên phải "Đã chọn {x}/{tổng}") và danh sách checkbox cuộn tối đa ~160px (lọc theo tên chứa chuỗi tìm, không phân biệt hoa thường). Rỗng: "Chưa có phòng ban" (không có phòng ban nào) hoặc "Không tìm thấy phòng ban".
- Có trạng thái vô hiệu cho toàn bộ điều khiển.

## Phụ lục B — Khóa i18n được dùng

| Khóa | Nơi dùng |
|---|---|
| `nav.skills`, `nav.prompts` | mục menu bên |
| `skills.uploadSkill` | tiêu đề hộp thoại Tải gói ZIP |
| `skills.selectZip` | nhãn ô chọn tệp ZIP |
| `knowledge.upload.subtitle` | mô tả hộp thoại Tải gói ZIP |
| `knowledge.upload.files` | hậu tố đếm tệp đã chọn |
| `knowledge.colVisibility` | nhãn "Phạm vi" trong hộp thoại Tải gói ZIP |
| `scope.global`, `scope.department` | lựa chọn phạm vi trong hộp thoại Tải gói ZIP; `scope.global` ở thẻ kiểu cũ |
| `common.error` | thông điệp lỗi dự phòng (tải ZIP, xóa thẻ) |
| `skills.details`, `common.edit`, `common.delete` | thẻ kiểu cũ (12.1); `common.delete` cả ở 12.5 |
| `skills.colDepartment`, `skills.allDepartments` | bộ lọc thanh bên (12.4) |
| `skills.manageTags`, `common.search`, `common.noResults` | quản lý thẻ (12.5) |

Mọi nhãn khác trong tài liệu là chuỗi cố định (tiếng Việt ở trang danh sách kỹ năng và Kho prompt; tiếng Anh ở trang chi tiết kỹ năng, Trình soạn, Trình duyệt tệp, hộp thoại Đóng góp, trang quản trị đề xuất và một phần hộp thoại Tải gói ZIP).
