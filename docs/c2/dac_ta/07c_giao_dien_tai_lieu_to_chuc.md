# 07c — Giao diện: Kho tài liệu, Kiểu tri thức, Phòng ban, Nhân sự

Tài liệu này thuộc loạt đặc tả giao diện 07 (mục lục ở `07_giao_dien.md`, nền tảng chung — layout portal, sidebar, theme, i18n, các primitive shadcn "base-nova" trên @base-ui/react, quy ước icon Material Symbols Outlined, `api`/`apiUpload`, `useAuth` với `hasPermission`/`canAccess` — ở `07a_giao_dien_nen_tang.md`). Phạm vi của 07c là các màn quản trị tri thức tổ chức: `/knowledge` (tài liệu + kiểu tri thức, kèm các dialog tải lên, chỉnh sửa, duyệt kế hoạch, duyệt dung lượng và ngăn kéo danh sách Điều), `/departments`, `/employees`, cùng các thành phần dùng chung `PageHeader`, `ScopeBadge`, `ScopeDialog`, `ScopeMembersDialog`, `EmptyState`. Mọi nhãn hiển thị tiếng Việt được trích nguyên văn; khi có khóa i18n thì ghi khóa (tra trong `frontend/src/lib/i18n.tsx`). Hàm `t(key, fallback)` trả giá trị theo ngôn ngữ hiện tại, nếu thiếu thì lấy bản tiếng Anh, nếu vẫn thiếu thì trả `fallback` (hoặc chính khóa). Màu được mô tả theo vai trò (primary, destructive, muted, "xanh lục/emerald", "hổ phách/amber"...), không ghi mã màu.

---

## 0. Quy ước chung cho các màn trong tài liệu này

| Hạng mục | Quy ước |
|---|---|
| Icon | Thẻ span với class icon Material Symbols Outlined, nội dung là tên ligature (vd `upload`, `sync`). Kích thước ghi bằng px khi nguồn cố định (16/18…). Icon xoay (`progress_activity`) dùng hiệu ứng quay liên tục. |
| Lỗi API | `api`/`apiUpload` ném lỗi có `message` = trường `detail` của body JSON lỗi, hoặc "API Error {status}" / "Upload Error {status}", hoặc "Request timed out"/"Upload timed out". Màn hình hiển thị `message`; nếu lỗi không phải Error thì dùng chuỗi dự phòng ghi trong từng mục. |
| Hộp xác nhận | Các thao tác xóa dùng hộp `confirm()` gốc của trình duyệt với chuỗi ghi trong đặc tả. Hủy hộp → không gọi API. |
| Băng thông báo (banner) | Khối bo góc, nền nhạt theo tông (destructive nhạt cho lỗi, emerald nhạt cho thành công), chữ cỡ nhỏ, icon `error` hoặc `check_circle` bên trái, nút `close` bên phải (nếu có) để ẩn. |
| Trạng thái tải toàn khối | Icon `progress_activity` quay, cỡ lớn (~30px), màu muted, căn giữa, đệm dọc lớn (~64px). |
| Ô trống trong bảng | Dấu gạch dài "—" màu muted mờ. |
| Định dạng ngày | Ngày tạo: định dạng ngày theo locale `vi-VN`, dạng dd/mm/yyyy. Ngày văn bản (ban hành/hiệu lực): `formatViDate` từ `lib/legal-doc` (chuỗi YYYY-MM-DD → dd/mm/yyyy, không đổi múi giờ). |

### 0.1 Điều hướng & quyền vào màn (sidebar)

| Route | Nhãn sidebar (i18n) | Icon | Hiện khi người dùng có ít nhất một quyền |
|---|---|---|---|
| `/knowledge` | `nav.documents` | `description` | `doc:read:own_dept`, `doc:read:all` |
| `/departments` | `nav.departments` | `domain` | `org:departments:read` |
| `/employees` | `nav.employees` | `group` | `org:employees:read` |

Nhóm "Tổ chức" (`nav.organization`) chỉ hiện khi có `org:departments:read` hoặc `org:employees:read`. `hasPermission(p)` trả true nếu `user.role === "admin"` hoặc `p` nằm trong `user.permissions`. Các trang không tự chặn truy cập theo quyền (ngoài chuyện đăng nhập do layout portal xử lý) — chỉ ẩn/hiện phần tử như ghi trong từng mục.

---

## 1. Thành phần dùng chung

### 1.1 `PageHeader` (`components/shared/page-header`)

| Prop | Kiểu | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `title` | string | có | Tiêu đề trang |
| `description` | string | không | Dòng mô tả dưới tiêu đề |
| `action` | ReactNode | không | Vùng hành động bên phải |

Bố cục: trên mobile xếp dọc (khoảng cách nhỏ); từ breakpoint `sm` trở lên xếp ngang, căn đáy, hai đầu. Khối chữ có thuộc tính `data-slot="page-header-text"`; tiêu đề là thẻ h2 cỡ 3xl (lg: 4xl), tracking chặt, màu foreground; mô tả cỡ chữ nhỏ, màu muted, cách trên ~4px, rộng tối đa ~36rem. Vùng action có `data-slot="page-header-action"`, cách trên ~12px trên mobile, từ `sm` đẩy sát phải. Toàn khối có `data-slot="page-header"`. Lưu ý: màn `/knowledge` KHÔNG dùng PageHeader (tự dựng header, xem §2.2).

### 1.2 `EmptyState` (`components/shared/empty-state`)

Props: `icon: string` (tên Material Symbol), `title: string`, `description?: string`, `action?: ReactNode`. Hiển thị cột căn giữa, đệm dọc ~64px: icon rất lớn (~48px) màu muted mờ 40%, cách dưới 16px; tiêu đề h3 cỡ lg đậm vừa; mô tả cỡ nhỏ màu muted, căn giữa, rộng tối đa ~24rem; action (nếu có) cách trên 16px.

### 1.3 `ScopeBadge` (`components/shared/scope-badge`)

Export kiểu `ScopeType = "global" | "project" | "department" | "team"`.

| Prop | Kiểu | Ý nghĩa |
|---|---|---|
| `scopeType` | ScopeType \| string \| undefined | Loại phạm vi |
| `scopeId` | string \| null \| undefined | Nhận nhưng không dùng để hiển thị |
| `className` | string | Nối thêm class |

Huy hiệu dạng Badge variant `outline`, bo tròn hoàn toàn (trừ trường hợp thiếu scope), chữ ~11px đậm vừa, không xuống dòng, icon ~14px trước nhãn:

| scopeType | Icon | Nhãn (i18n) | Tông màu |
|---|---|---|---|
| (rỗng/undefined) | `public` (13px) | `scope.global` | Viền muted, chữ muted, chữ cỡ xs |
| `global` | `public` | `scope.global` | Xanh dương: viền xanh dương mờ, chữ xanh dương, nền xanh dương rất nhạt (dark mode: chữ sáng hơn, nền xanh 10%) |
| `department` | `corporate_fare` | `scope.department` | Chàm (indigo), cùng kiểu |
| `project` | `folder_special` | `scope.project` | Hổ phách (amber), cùng kiểu |
| `team` | `group` | `scope.team` | Xanh lục (emerald), cùng kiểu |
| giá trị khác (vd `personal`) | không icon | hiển thị nguyên chuỗi scopeType | Viền muted, chữ muted |

### 1.4 `ScopeDialog` (`components/shared/scope-dialog`)

Props: `open: boolean`, `onOpenChange(open)`, `label: string`, `employeeId: string` (nhận nhưng không dùng). Dialog rộng tối đa `md`. Tiêu đề cỡ lg với icon `lock` màu primary + chuỗi `t("scope.dialogTitle")` trong đó thay `{label}` bằng `label`. Thân: một đoạn chữ muted `scope.dialogPlaceholder`. Không có nút hành động (đóng bằng nút X mặc định của Dialog hoặc click nền). Là placeholder, không gọi API.

### 1.5 `ScopeMembersDialog` (`components/shared/scope-members-dialog`)

Hiện chưa được màn nào dùng, nhưng là thành phần dùng chung cần có.

| Prop | Kiểu | Ý nghĩa |
|---|---|---|
| `open` | boolean | Mở/đóng |
| `onOpenChange` | (open: boolean) => void | |
| `label` | string | Tên phạm vi hiển thị trong tiêu đề |
| `scopeType` | `"global" \| "department" \| "project"` | Dùng trong URL API |
| `scopeId` | string | Dùng trong URL API |

Hành vi:

- Khi `open` chuyển true: xóa lỗi, gọi `GET /api/scopes/{scopeType}/{scopeId}/members` → mảng `{ employee_id, employee_name, employee_email, role }`; đồng thời `GET /api/employees?page_size=200` → dùng `items[]` (`id`, `name`, `email`) làm nguồn chọn (lỗi bỏ qua). Lỗi tải thành viên: hiện lỗi (dự phòng `common.error`) và danh sách rỗng.
- Danh sách chọn chỉ gồm nhân sự chưa là thành viên.
- Thêm: `POST /api/scopes/{scopeType}/{scopeId}/members` body `{ employee_id, role }`; thành công → bỏ chọn nhân sự, tải lại thành viên. Lỗi → banner lỗi.
- Gỡ: hỏi `confirm(t("scope.removeConfirm"))`, rồi `DELETE /api/scopes/{scopeType}/{scopeId}/members/{employee_id}`, tải lại.

Bố cục (dialog rộng tối đa `xl`, tiêu đề cỡ xl = `scope.membersTitle` thay `{label}`):

1. Hộp giải thích nền xanh dương nhạt, viền xanh dương nhạt, icon `shield_person`; dòng đậm = `scope.realmOrg` nếu `scopeType === "department"`, ngược lại `scope.realmWorkspace`; dòng dưới = `scope.realmDesc`.
2. Banner lỗi (chữ destructive, nền destructive 10%) nếu có.
3. Hàng thêm: Select nhân sự chiếm hết chiều ngang (placeholder `scope.selectEmp`, mục hiển thị "{name} — {email}"); Select vai trò rộng ~8rem, mặc định `reader`, các mục `reader` (`scope.roleReader`), `contributor` (`scope.roleContributor`), `owner` (`scope.roleOwner`), `admin` (`scope.roleAdmin`); nút primary nhãn `common.create` (khi đang lưu: icon `progress_activity` quay). Nút vô hiệu khi đang lưu hoặc chưa chọn nhân sự.
4. Khung danh sách viền bo tròn: đầu khung nền muted, chữ hoa nhỏ "`dept.currentMembers` ({số})"; đang tải → spinner nhỏ; rỗng → `EmptyState` icon `group_off`, tiêu đề `scope.noMembers`, mô tả `scope.noMembersDesc`; có dữ liệu → các dòng ngăn cách, cuộn khi cao quá ~15rem, mỗi dòng: tên (đậm vừa) + email (muted) bên trái; bên phải Badge outline hiển thị `role` (viết hoa chữ đầu; viền + chữ primary nếu `admin` hoặc `owner`) và nút icon `close` (hover chuyển destructive, tooltip `common.delete`).

---

## 2. Màn `/knowledge` — Kho tri thức

### 2.1 Mục đích, dữ liệu và quyền

Quản lý tài liệu (nguồn) đã tải lên và danh mục kiểu tri thức. Trang có hai tab: "Tài liệu" và "Kiểu tri thức".

Quyền: `canManage = hasPermission("org:settings:manage")` — chỉ điều khiển hiện menu "Xử lý nội dung" ở tab Tài liệu. Các nút khác (Tải lên, Làm mới, thêm/sửa/xóa kiểu tri thức, thao tác dòng) hiển thị cho mọi người vào được trang; backend chịu trách nhiệm từ chối (lỗi hiển thị qua banner).

Kiểu dữ liệu dùng chung:

- `KnowledgeType`: `id`, `slug`, `name`, `color` (chuỗi màu hex), `description?`, `sort_order: number`, `source_count?: number`.
- `Department`: `id`, `name`.
- `Source` (mỗi dòng bảng, từ `GET /api/sources`): `id`, `title`, `file_name?`, `source_type?` (vd `"url"`), `status` (xem §2.6), `progress?` (0–100), `progress_message?`, `error_message?`, `chunk_status?`, `chunk_progress?`, `chunk_error_message?`, `wiki_status?`, `wiki_progress?`, `wiki_error_message?`, `page_count?`, `wiki_page_count?`, `extracted_token_count?`, `image_count?`, `knowledge_type_id?`, `knowledge_type_name?`, `knowledge_type_color?`, `department_ids?: string[]`, `department_names?: string[]`, `contributed_by_name?`, `scope_type?`, `scope_id?`, `preserve_verbatim?: boolean`, `pipeline_strategy?`, `pipeline_phase?`, `doc_meta?` (kiểu `DocMeta` của `types/legal-doc` cộng `validity?: Validity`, có thể null), `created_at`, `updated_at?`.
- `DocMeta` dùng các trường: `doc_type`, `doc_number`, `issuing_authority`, `official_title`, `issued_date`, `effective_date`, `expiry_date`, `field`, `doc_slug`, `manual_fields: string[]`.

### 2.2 Bố cục tổng thể (cột dọc, khoảng cách ~20px)

1. **Header** (hàng ngang, xuống dòng được, hai đầu):
   - Trái: h1 "Kho tri thức" (cỡ 2xl, đậm, tracking chặt); dưới là mô tả "Quản lý và tổ chức tài liệu và kiểu tri thức của tổ chức bạn." (cỡ nhỏ, muted).
   - Phải: nút outline cỡ sm cao ~36px "Làm mới" với icon `sync` (khi đang tải: icon `progress_activity` quay, nút vô hiệu); nút primary cỡ sm cao ~36px "Tải lên" icon `upload` → mở UploadDialog.
2. **Hàng tab + hành động ngữ cảnh** (hai đầu):
   - Trái: thanh tab kiểu "segmented" (nền muted, bo tròn, đệm 4px, `role=tablist`). Mỗi tab là nút (`role=tab`, `aria-selected`) gồm icon ~17px, nhãn, và bộ đếm dạng viên thuốc nhỏ (~11px, số tabular). Tab chọn: nền background, chữ foreground, bóng nhẹ, bộ đếm nền primary 10% chữ primary; tab không chọn: chữ muted, bộ đếm nền background mờ.

     | Tab | Nhãn | Icon | Bộ đếm |
     |---|---|---|---|
     | `documents` (mặc định) | "Tài liệu" | `description` | `total` từ API danh sách tài liệu (theo bộ lọc hiện tại) |
     | `types` | "Kiểu tri thức" | `category` | số kiểu tri thức đã tải |

   - Phải, khi tab = documents và `canManage`: DropdownMenu, nút kích hoạt viền, cao ~32px, chữ xs đậm vừa: icon `auto_fix_high` + "Xử lý nội dung" + (khi có tài liệu lỗi) huy hiệu đỏ "{n} lỗi" + icon `expand_more`. Menu căn phải, rộng tối thiểu ~18rem, chia 4 nhóm có tiêu đề, ngăn cách bằng đường kẻ. Mỗi mục có số đếm bên phải lấy từ `GET /api/sources/processing-summary` (tải khi vào trang, khi danh sách tải xong, khi mở menu và sau mỗi tác vụ). Mục tác vụ có số đếm = 0 bị vô hiệu; mục "Xem nhanh" luôn bấm được:

     | Nhóm | Mục | Icon | Số đếm | Hành động |
     |---|---|---|---|---|
     | Chạy lại | "Chạy lại tất cả tài liệu lỗi" | `replay` | `failed` | `POST /api/sources/retry-failed?only_ai_outage=false` |
     | Chạy lại | "Chỉ chạy lại lỗi do AI gián đoạn" (chỉ hiện khi 0 < `failed_ai_outage` < `failed`) | `cloud_off` | `failed_ai_outage` | `POST /api/sources/retry-failed?only_ai_outage=true` |
     | Thuộc tính văn bản | "Trích xuất thuộc tính còn thiếu" | `data_info_alert` | — | Backfill với `only_missing=true` |
     | Thuộc tính văn bản | "Trích xuất lại toàn bộ thuộc tính" | `restart_alt` | — | Backfill với `only_missing=false` |
     | Chỉ mục tìm kiếm | "Tạo vector cho trang còn thiếu" | `hub` | `pages_missing_vectors` | `POST /api/sources/reembed-missing` |
     | Chỉ mục tìm kiếm | "Tạo chunk văn bản gốc còn thiếu" | `segment` | `chunk_missing` | `POST /api/settings/embeddings/backfill-source-chunks` |
     | Xem nhanh | "Tài liệu lỗi" | `error` | `failed` | Đặt bộ lọc trạng thái `failed`, trang 1 |
     | Xem nhanh | "Đang xử lý" | `progress_activity` | `running` | Đặt bộ lọc trạng thái `running`, trang 1 |
     | Xem nhanh | "Chờ duyệt" | `fact_check` | `review` | Đặt bộ lọc trạng thái `review`, trang 1 |

   - Phải, khi tab = types: nút outline cỡ sm cao ~32px chữ xs, icon `add`, "Thêm kiểu tri thức" → mở KnowledgeTypeDialog ở chế độ tạo.
3. **Banner thông báo cấp trang** (nếu có): tông `ok` (emerald nhạt, icon `check_circle`) hoặc `error` (destructive nhạt, icon `error`), nút `close` ẩn banner.
4. **Nội dung tab**: `KnowledgeTable` (§2.4) hoặc `KnowledgeTypeCards` (§2.10).
5. Các dialog: `UploadDialog` (§2.11), `KnowledgeTypeDialog` (§2.12).

### 2.3 Tải dữ liệu, truy vấn và polling

**Truy vấn danh sách (`SourceQuery`, export từ `components/knowledge/knowledge-table`):**

| Trường | Kiểu | Mặc định (`DEFAULT_QUERY`) |
|---|---|---|
| `search` | string | "" |
| `typeId` | string | "" |
| `deptId` | string | "" |
| `status` | `StatusGroup` | "" |
| `sort` | string dạng `{field}_{asc\|desc}` | `created_desc` |
| `page` | number | 1 |
| `pageSize` | number | 20 |

**`STATUS_GROUPS`** (export cùng module; `StatusGroup = "" | "ready" | "running" | "review" | "failed"`):

| value | Nhãn trong select | Giá trị gửi lên tham số `status` |
|---|---|---|
| "" | "Tất cả trạng thái" | (không gửi) |
| `ready` | "Sẵn sàng" | `ready` |
| `running` | "Đang xử lý" | `pending,processing` |
| `review` | "Chờ duyệt" | `plan_ready,awaiting_approval` |
| `failed` | "Lỗi / một phần" | `error,partial` |

**API danh sách:** `GET /api/sources?page={page}&page_size={pageSize}&sort={sort}` cộng các tham số tùy chọn `search`, `knowledge_type_id` (= typeId), `department_id` (= deptId), `status` (danh sách phân tách bằng dấu phẩy như bảng trên) — chỉ gửi khi khác rỗng. Phản hồi: `{ items: Source[], total, page, page_size, total_pages }`. `totalPages` hiển thị = max(1, `total_pages`).

- Mỗi lần gọi mang số thứ tự; phản hồi của lần gọi cũ hơn lần gọi mới nhất bị bỏ qua (chống nhảy dữ liệu khi gõ nhanh/chuyển trang).
- Trạng thái "đang tải" = chuỗi tham số của truy vấn đang hiển thị chưa được trả lời, hoặc đang làm mới thủ công.
- Lỗi (không im lặng): xóa danh sách, `total=0`, banner lỗi cấp trang với message hoặc "Không tải được danh sách tài liệu". Ở chế độ im lặng (polling/refresh nền) lỗi bị bỏ qua.

**Metadata:** song song `GET /api/knowledge-types` → `KnowledgeType[]` và `GET /api/departments` → `Department[]`. Lỗi → cả hai mảng rỗng. Sau lần đầu (thành công hay lỗi) đánh dấu metadata đã tải (dùng cho loading của tab Kiểu tri thức).

**Polling:** khi trong trang hiện tại có ít nhất một tài liệu trạng thái `pending` hoặc `processing`, cứ 3000 ms gọi lại danh sách ở chế độ im lặng với truy vấn hiện tại; dừng khi không còn tài liệu đang chạy.

**Làm mới (nút header):** đặt cờ làm mới, gọi song song danh sách (không im lặng) và metadata, xong thì tắt cờ.

**Tác vụ trong menu Xử lý nội dung:** mọi tác vụ đều hỏi `confirm` trước, gọi POST (không body), thành công thì hiện banner ok với `message` server trả về (không có thì dùng câu mặc định), lỗi thì banner lỗi; sau đó tải lại danh sách (im lặng) và số đếm.

- **Chạy lại tất cả tài liệu lỗi:** confirm "Chạy lại {n} tài liệu lỗi hoặc xử lý một phần? Mỗi tài liệu chỉ chạy lại phần bị lỗi." Server lấy mọi tài liệu `error`/`partial` trong phạm vi người dùng được đọc (`source_read_filter`), bỏ qua tài liệu đã có tác vụ trong hàng đợi, tài liệu thiếu tệp/URL, và (với người không phải admin) tài liệu đã vượt `max_auto_recover_attempts`; admin được đặt lại bộ đếm. Mỗi tài liệu chạy lại đúng nhánh lỗi như nút "Chạy lại" ở dòng. Không thăm dò AI trước. Banner nêu số đã xếp hàng và số bị bỏ qua theo lý do.
- **Tạo vector cho trang còn thiếu:** trang wiki (trừ `_index`, `_log`, `_hot`, nội dung rỗng) thiếu vector trang hoặc vector chunk của mô hình embedding đang dùng → task `reembed_missing_pages_task` chạy nền, mỗi trang commit riêng.
- **Tạo chunk văn bản gốc còn thiếu:** tài liệu `ready`/`partial` có văn bản nhưng `chunk_status` là `pending`/`error`.

**Backfill (menu Xử lý nội dung):** hỏi `confirm` với chuỗi "Trích xuất lại số hiệu, ngày ban hành, hiệu lực... cho {nhãn}? Việc này chạy nền và có thể dùng LLM." trong đó {nhãn} = "các tài liệu còn thiếu thuộc tính" (only_missing) hoặc "toàn bộ tài liệu". Đồng ý → `POST /api/wiki/legal-docs/backfill?only_missing={true|false}&use_llm=true` (không body). Thành công → banner ok "Đã đưa vào hàng đợi. Thuộc tính văn bản sẽ cập nhật sau ít phút."; lỗi → banner lỗi message hoặc "Không chạy được trích xuất".

**Callback từ thành phần con:**

- `KnowledgeTable.onRefresh` → tải lại danh sách im lặng + metadata.
- `KnowledgeTypeCards.onRefresh` → tải lại metadata + danh sách im lặng.
- `KnowledgeTypeCards.onViewDocuments(typeId)` → đặt truy vấn = DEFAULT_QUERY với `typeId`, chuyển sang tab documents.
- `UploadDialog.onUploaded` → đặt `sort=created_desc`, `page=1` (giữ bộ lọc khác), gọi danh sách im lặng với truy vấn đó, tải lại metadata.
- `KnowledgeTypeDialog.onSaved` → tải lại metadata.

### 2.4 `KnowledgeTable` (`components/knowledge/knowledge-table/index`)

Export: `KnowledgeTable`, `SourceQuery`, `StatusGroup`, `STATUS_GROUPS`, `DEFAULT_QUERY`.

Props: `sources: Source[]`, `types: KnowledgeType[]`, `departments: Department[]`, `loading: boolean`, `total: number`, `totalPages: number`, `query: SourceQuery`, `onQueryChange(patch: Partial<SourceQuery>)`, `onRefresh()`, `onUpload()`.

Bố cục cột dọc khoảng cách ~12px: hàng lọc → thanh thao tác hàng loạt → banner lỗi thao tác → khung bảng → phân trang.

#### 2.4.1 Hàng lọc (ngang, xuống dòng được, khoảng cách ~8px; mọi điều khiển cao ~32px, chữ xs, bo góc, viền border, focus có vòng primary 30%)

| Thành phần | Chi tiết |
|---|---|
| Ô tìm kiếm | Rộng toàn dòng trên mobile, ~16rem từ `sm`. Icon `search` 16px bên trái trong ô; placeholder "Tìm kiếm tài liệu..."; khi có chữ hiện nút `close` 14px bên phải (tooltip "Xóa") để xóa chữ. Debounce 350 ms: sau khi ngừng gõ, gọi `onQueryChange({ search: chuỗi đã trim, page: 1 })`. |
| Select kiểu tri thức | Select HTML gốc (không dùng primitive), mũi tên chevron xuống màu xám vẽ ở góc phải. Mục đầu "Tất cả kiểu tri thức" (giá trị rỗng), sau đó mỗi kiểu một mục theo `name`. Đổi → `{ typeId, page: 1 }`. |
| Select phòng ban | Chỉ hiện khi có ít nhất 1 phòng ban. Mục đầu "Tất cả phòng ban". Đổi → `{ deptId, page: 1 }`. |
| Select trạng thái | Các mục theo `STATUS_GROUPS`. Đổi → `{ status, page: 1 }`. |
| Nút "Xóa lọc" | Chỉ hiện khi có bộ lọc (search/typeId/deptId/status khác rỗng). Nút chữ muted, hover nền secondary, icon `filter_alt_off` 15px. Bấm → xóa ô tìm kiếm và gọi `{ search:"", typeId:"", deptId:"", status:"", page:1 }`. |
| Bộ đếm | Đẩy sát phải, chữ xs muted số tabular: "{total} tài liệu". |

#### 2.4.2 Chọn dòng và thanh thao tác hàng loạt

- Lựa chọn chỉ xét các dòng của trang hiện tại. Checkbox đầu bảng (aria-label "Chọn tất cả"): chọn hết/bỏ hết; trạng thái indeterminate khi chọn một phần. Checkbox mỗi dòng aria-label "Chọn {title}". Checkbox dùng màu nhấn primary.
- Khi có ≥1 dòng được chọn: thanh ngang viền primary 30%, nền primary 5%, chữ xs: "Đã chọn {n}" (đậm vừa), nút chữ "Bỏ chọn"; bên phải:
  - Nút outline cao ~28px icon `refresh` "Chạy lại ({k})" — chỉ hiện khi trong các dòng chọn có k dòng trạng thái `error` hoặc `partial`.
  - Nút outline chữ destructive icon `delete` "Xóa" (khi đang chạy hàng loạt: icon `progress_activity` quay). Cả hai vô hiệu khi đang chạy.
- **Xóa hàng loạt:** `confirm("Xóa {n} tài liệu đã chọn? Thao tác không thể hoàn tác.")`, sau đó tuần tự `DELETE /api/sources/{id}` từng tài liệu.
- **Chạy lại hàng loạt:** tuần tự `POST /api/sources/{id}/retry` (không tham số branch) cho các dòng error/partial đã chọn.
- Sau khi xong: bỏ chọn tất cả; nếu có lỗi, banner lỗi "{số lỗi}/{tổng} thao tác thất bại — {title}: {message hoặc 'lỗi'}" (chỉ nêu lỗi đầu tiên); luôn gọi `onRefresh`.

#### 2.4.3 Banner lỗi thao tác

Khối destructive nhạt, icon `error`, nội dung lỗi, nút `close` ẩn. Mọi thao tác dòng/hàng loạt xóa lỗi cũ trước khi chạy.

#### 2.4.4 Khung bảng — các trạng thái

Khung viền bo tròn lớn, nền card, ẩn tràn.

| Điều kiện | Hiển thị |
|---|---|
| `loading` và chưa có dòng | Spinner toàn khối |
| Không có dòng, có bộ lọc | `EmptyState` icon `search_off`, tiêu đề "Không có tài liệu phù hợp", mô tả "Thử đổi từ khóa hoặc bỏ bớt bộ lọc.", action nút outline sm "Xóa bộ lọc" (= Xóa lọc) |
| Không có dòng, không lọc | `EmptyState` icon `cloud_upload`, tiêu đề "Chưa có tài liệu nào", mô tả "Tải lên văn bản đầu tiên để bắt đầu xây dựng kho tri thức.", action nút primary sm "Tải lên tài liệu" → `onUpload` |
| Có dòng | Bảng cuộn ngang; khi `loading` (đang tải lại) bảng mờ còn ~60% |

#### 2.4.5 Cột bảng (13 cột, chữ xs)

Hàng tiêu đề nền muted 30%, cao ~40px, chữ ~10.5px IN HOA, tracking rộng, đậm, màu muted, được phép xuống dòng.

**Cột sắp xếp được** (tiêu đề là nút): bên phải chữ có icon 14px — `arrow_upward` (đang tăng), `arrow_downward` (đang giảm), `unfold_more` mờ 30% (chưa sắp theo cột này); cột đang sắp có chữ màu foreground. Bấm cột đang sắp → đảo chiều; bấm cột khác → cột `title` bắt đầu `asc`, các cột ngày bắt đầu `desc`. Gửi `onQueryChange({ sort: "{field}_{dir}", page: 1 })`. Field hợp lệ: `title`, `issued`, `effective`, `created`.

| # | Tiêu đề | Sắp xếp | Nội dung ô | Ghi chú kích thước |
|---|---|---|---|---|
| 1 | (checkbox) | — | Checkbox chọn dòng | Hẹp ~36px |
| 2 | "Tài liệu" | `title` | Ô vuông ~28px nền primary 10%, icon 16px màu primary theo đuôi tệp (bảng §2.4.7; nếu không khớp: `link` khi `source_type === "url"`, ngược lại `description`). Bên cạnh: link tiêu đề (~13px đậm vừa, cắt bằng dấu ba chấm, tooltip = title, hover chuyển primary) dẫn tới `/wiki/source/{id}`; dòng phụ ~11px muted = `doc_number` và `issuing_authority` nối bằng " · " (chỉ hiện khi có ít nhất một) | Rộng tối thiểu ~240px, tối đa ~300px |
| 3 | "Kiểu tri thức" | — | Viên thuốc bo tròn chữ ~11px đậm vừa, chữ màu = `knowledge_type_color`, viền cùng màu độ mờ ~33%, nền cùng màu độ mờ ~7%, nội dung `knowledge_type_name`; không có → "—". Nếu `preserve_verbatim`: thêm viên thuốc nhỏ nền muted chữ muted ~10px "Nguyên văn", tooltip "Giữ nguyên văn — tách theo Điều, không biên soạn lại" | Không xuống dòng |
| 4 | "Phạm vi hiển thị" | — | `ScopeBadge` với `scope_type`, `scope_id` | |
| 5 | "Phòng ban phụ trách" | — | Tên phòng ban đầu tiên (từ `department_names`, nếu trống thì tra tên từ `department_ids` qua danh sách phòng ban), nếu nhiều thêm " +{n-1}" màu muted; tooltip = tất cả tên nối ", "; trống → "—" | Tối đa ~140px, cắt chữ |
| 6 | "Số trang" | — | `page_count` hoặc "—" | Căn phải, số tabular, màu muted |
| 7 | "Wiki" | — | Khi `status === "ready"` hoặc `wiki_page_count > 0`: link "Xem wiki" (primary, đậm vừa, hover gạch chân) + icon `arrow_outward` 13px, tới `/wiki/law/{doc_meta.doc_slug hoặc id, đã mã hóa URL}`; nếu `wiki_page_count > 0` thêm nút viên thuốc ~10px số tabular hiển thị số trang wiki + icon `expand_more`/`expand_less` 12px (tooltip "Xem nhanh các Điều"), bấm để mở/đóng hàng mở rộng (§2.9); khi đang mở nút nền primary chữ primary-foreground, khi đóng nền primary 10% chữ primary. Ngược lại "—" | Không xuống dòng |
| 8 | "Người đóng góp" | — | Avatar tròn ~20px nền secondary chữ ~10px đậm = chữ cái đầu của từ CUỐI trong `contributed_by_name` (viết hoa; rỗng → "?") + tên (cắt chữ, tooltip); trống → "—" | Tối đa ~130px |
| 9 | "Trạng thái" | — | `StatusDot` (§2.6) | |
| 10 | "Ngày ban hành" | `issued` | `formatViDate(doc_meta.issued_date)` hoặc "—" | Không xuống dòng, số tabular |
| 11 | "Hiệu lực" | `effective` | Nếu `doc_meta.validity` có: viên thuốc viền bo tròn ~10px đậm với nhãn và tông màu theo `VALIDITY_INFO[validity]` (từ `lib/legal-doc`: `con_hieu_luc` "Còn hiệu lực" xanh lục; `chua_co_hieu_luc` "Chưa có hiệu lực" hổ phách; `bi_thay_the` "Bị thay thế" tím; `het_hieu_luc` "Hết hiệu lực" đỏ; `khong_xac_dinh` "Chưa xác định" xám đá), tooltip "Hiệu lực từ {dd/mm/yyyy}" khi có `effective_date`; ngược lại "—" | |
| 12 | "Ngày tạo" | `created` | `created_at` định dạng dd/mm/yyyy (vi-VN) | Màu muted, số tabular |
| 13 | (thao tác) | — | Menu `more_horiz` (§2.4.6) | Hẹp ~40px, căn phải |

Màu nền dòng: dòng đang mở rộng → nền accent 40%; dòng được chọn → nền primary 5% (thuộc tính `data-state="selected"`); còn lại hover nền secondary 30%.

#### 2.4.6 Menu thao tác dòng

Nút kích hoạt vuông ~28px icon `more_horiz` 18px, màu muted (đậm hơn khi hover dòng). Menu căn phải, rộng tối thiểu ~12rem, icon mục 16px:

| Mục | Icon | Điều kiện hiện | Hành động / API |
|---|---|---|---|
| "Xem tài liệu" | `visibility` | Luôn | Điều hướng `/wiki/source/{id}` |
| "Mở trong Kho tri thức" | `auto_stories` | `status === "ready"` | Điều hướng `/wiki/law/{doc_slug hoặc id}` |
| "Tải tệp gốc" | `download` | `status === "ready"` và `source_type !== "url"` | `GET /api/sources/{id}` → nếu có `download_url` thì mở tab mới tới URL đó; lỗi → banner "Không tải được tệp" (hoặc message) |
| (ngăn cách) | | | |
| "Chỉnh sửa thông tin" | `edit` | Luôn | Mở `EditSourceDialog` (§2.5) |
| "Duyệt kế hoạch biên soạn" | `fact_check` (màu xanh dương) | `status === "plan_ready"` | Mở `PlanReviewDialog` (§2.7) |
| "Duyệt dung lượng trích xuất" | `scale` (màu cam) | `status === "awaiting_approval"` | Mở `ExtractionReviewDialog` (§2.8) |
| "Chạy lại phần lỗi" / "Đang chạy lại..." | `refresh` (quay khi đang chạy) | `status` là `error` hoặc `partial` | `POST /api/sources/{id}/retry` (không branch — server tự chọn nhánh lỗi) |
| `knowledge.retryChunk` | `segment` | Nhóm A (xem dưới) | `POST /api/sources/{id}/retry?branch=chunk` |
| `knowledge.retryWiki` | `auto_stories` | Nhóm A và không `preserve_verbatim` và `status` thuộc `error`/`partial`/`plan_ready` | `POST /api/sources/{id}/retry?branch=wiki` |
| `knowledge.retryAll` | `restart_alt` | Nhóm A | `POST /api/sources/{id}/retry?branch=all` |
| (ngăn cách) | | | |
| "Xóa" (chữ destructive) | `delete` | Luôn | `confirm(t("knowledge.deleteConfirm"))` rồi `DELETE /api/sources/{id}`; bỏ dòng khỏi lựa chọn; `onRefresh`; lỗi → "Không xóa được tài liệu" |

Nhóm A = `status` thuộc `error`, `partial`, `plan_ready`, `ready` VÀ (`chunk_status` có giá trị khác `pending` HOẶC `wiki_status` có giá trị khác `pending`). Các mục retry bị vô hiệu khi tài liệu đó đang chạy lại; thành công → `onRefresh`; lỗi → "Không chạy lại được".

#### 2.4.7 Icon theo đuôi tệp (`fileIcons`, `getFileExt` trong `knowledge-table/utils`)

`getFileExt(source)` = phần sau dấu chấm cuối của `file_name`, chữ thường (rỗng nếu không có).

| Đuôi | Icon |
|---|---|
| pdf | `picture_as_pdf` |
| docx, doc, rtf | `description` |
| xlsx, xls, csv | `table_chart` |
| txt, md | `article` |
| pptx, ppt | `slideshow` |

#### 2.4.8 Phân trang (chỉ khi `total > 0`)

Hàng hai đầu, chữ xs muted:

- Trái: "{from}–{to} / {total}" (from = (page−1)×pageSize+1, to = min(page×pageSize, total)); select HTML (cao ~28px, aria-label "Số dòng mỗi trang") với các mục 10, 20, 50, 100 hiển thị "{n} / trang"; đổi → `{ pageSize, page: 1 }`.
- Phải (chỉ khi `totalPages > 1`): nút outline icon `chevron_left` (vô hiệu ở trang 1), chữ "Trang {page} / {totalPages}", nút outline `chevron_right` (vô hiệu ở trang cuối).

### 2.5 `EditSourceDialog` (`knowledge-table/edit-source-dialog`)

Props: `source: Source`, `types: KnowledgeType[]`, `departments: Department[]`, `onClose()`, `onSaved()`. Luôn mở khi được render; đóng bằng nền/X chỉ khi không đang lưu.

Bố cục dialog rộng tối đa `2xl`, cao tối đa 90% viewport, không đệm, ba vùng: header cố định (viền dưới), thân cuộn, footer cố định (viền trên, nền muted 20%).

- **Header:** tiêu đề `knowledge.edit.title`; dòng phụ xs muted = `file_name` hoặc `title` (cắt chữ, tooltip).
- **Thân** gồm các Section; mỗi Section có tiêu đề cỡ nhỏ đậm với icon 17px màu primary, tùy chọn dòng gợi ý ~11px muted. Mỗi Field có nhãn xs muted; nếu khóa trường nằm trong `doc_meta.manual_fields` thì cạnh nhãn có thẻ nhỏ nền primary 10% chữ primary "thủ công" (tooltip "Đã chỉnh sửa thủ công — giữ nguyên khi trích xuất lại"). Ô nhập cao ~36px, chữ sm.

| Section | Icon | Trường |
|---|---|---|
| "Thông tin chung" | `info` | Lưới 2 cột (cột phải ~14rem): "Tiêu đề hiển thị" (input, khởi tạo = title); "Kiểu tri thức" (Select primitive: mục "Chưa phân loại" giá trị rỗng + mỗi kiểu một mục có chấm tròn ~10px màu kiểu; trigger hiển thị chấm + tên kiểu đang chọn, hoặc placeholder "Chưa phân loại") |
| "Thuộc tính văn bản" — gợi ý "Tự động trích xuất khi xử lý. Trường bạn sửa sẽ được giữ nguyên khi trích xuất lại." | `gavel` | Hàng 3 cột: "Số hiệu" (`doc_number`, placeholder "VD: 59/2020/QH14"); "Loại văn bản" (`doc_type`, input có gợi ý datalist: Luật, Bộ luật, Nghị định, Nghị quyết, Thông tư, Quyết định, Chỉ thị, Công văn, Hướng dẫn, Kế hoạch, Quy chế; placeholder "VD: Luật"); "Lĩnh vực" (`field`, Select: mục "Chưa xác định" rỗng + danh sách lĩnh vực; placeholder "Chưa xác định"). Sau đó toàn chiều ngang: "Cơ quan ban hành" (`issuing_authority`, placeholder "VD: Quốc hội"); "Trích yếu / tên chính thức" (`official_title`). Hàng 3 cột kiểu date: "Ngày ban hành" (`issued_date`), "Ngày hiệu lực" (`effective_date`), "Hết hiệu lực" (`expiry_date`) |
| `knowledge.upload.visibility` | `visibility` | `ScopePicker` (§2.5.1) với `allowPersonal`, vô hiệu khi đang lưu |

Danh sách lĩnh vực: khi mở gọi `GET /api/wiki/legal-doc-fields` → `{ fields: string[] }` (lỗi bỏ qua). Nếu giá trị `field` hiện tại không có trong danh sách thì chèn nó lên đầu.

Giá trị khởi tạo phạm vi: `personal` nếu `scope_type === "personal"`; `department` nếu `scope_type === "department"` hoặc có `department_ids`; còn lại `global`. Phòng ban chọn sẵn = `department_ids`.

**Kiểm tra khi lưu** (thông báo hiển thị ở khối lỗi destructive nhạt, icon `error`):

1. Phạm vi `department` mà chưa chọn phòng ban → `t("dept.selectAtLeastOne", "Vui lòng chọn ít nhất một phòng ban")`.
2. Có cả ngày ban hành và ngày hiệu lực, mà hiệu lực < ban hành (so chuỗi YYYY-MM-DD) → "Ngày hiệu lực không thể trước ngày ban hành".

**Xác nhận đổi phạm vi:** nếu `source.status === "ready"` và phạm vi thay đổi (mode khác ban đầu, hoặc cùng `department` nhưng tập phòng ban khác) thì không lưu ngay mà hiện khối cảnh báo nền hổ phách nhạt, viền hổ phách, icon `warning`: nội dung "Tài liệu sẽ được gỡ khỏi các trang wiki chung và chỉ người đóng góp xem được. Bạn có muốn tiếp tục?" khi mode mới là `personal`, ngược lại `knowledge.edit.scopeChangeConfirm`. Hai nút: outline `common.cancel` (ẩn khối) và nút nền hổ phách chữ trắng `common.confirm` (thực hiện lưu). Khi khối đang hiện, nút Lưu ở footer bị vô hiệu.

**API lưu:** `PATCH /api/sources/{id}` body:

| Trường | Giá trị |
|---|---|
| `title` | title đã trim, bỏ trường nếu rỗng |
| `knowledge_type_id` | id kiểu hoặc `null` |
| `scope_type` | `personal` \| `department` \| `global` |
| `scope_id` | `null` |
| `department_ids` | mảng phòng ban nếu mode `department`, ngược lại `[]` |
| `doc_meta` | Chỉ gửi khi có trường thay đổi: object chỉ gồm các khóa (`doc_number`, `doc_type`, `issuing_authority`, `official_title`, `issued_date`, `effective_date`, `expiry_date`, `field`) có giá trị đã trim khác giá trị ban đầu; giá trị rỗng gửi `null` |

Thành công → `onSaved` (bảng đóng dialog và refresh). Lỗi → message hoặc "Không lưu được thay đổi".

**Footer:** nút outline cao ~32px `common.cancel` (→ onClose; vô hiệu khi lưu); nút primary "Lưu thay đổi" icon `save` (khi lưu: icon quay + "Đang lưu..."), vô hiệu khi đang lưu hoặc khi khối xác nhận đang mở.

#### 2.5.1 `ScopePicker` (`components/knowledge/scope-picker`)

Export `ScopeMode = "global" | "department" | "personal"` và `ScopePicker`.

| Prop | Kiểu | Ý nghĩa |
|---|---|---|
| `mode` | ScopeMode | Giá trị hiện tại |
| `onModeChange` | (m) => void | |
| `departments` | `{id,name}[]` | |
| `selected` | string[] | id phòng ban đã chọn |
| `onSelectedChange` | (ids) => void | |
| `disabled` | boolean? | |
| `allowPersonal` | boolean? (mặc định false) | Cho phép lựa chọn Cá nhân |

Bố cục:

1. Nhóm radio dạng segmented (nền muted, `role=radiogroup`), các nút chia đều (`role=radio`, `aria-checked`, tooltip = gợi ý), icon 16px + nhãn xs. Thứ tự: 

   | value | Icon | Nhãn | Gợi ý |
   |---|---|---|---|
   | `personal` (chỉ khi allowPersonal) | `person` | "Cá nhân" | "Chỉ mình bạn xem được" |
   | `department` | `apartment` | "Theo phòng ban" | "Chỉ các phòng ban được chọn xem được" |
   | `global` | `public` | "Toàn hệ thống" | "Mọi cán bộ đều xem được" |

   Chọn mode khác `department` → xóa danh sách phòng ban đã chọn.
2. Dòng gợi ý ~11px muted của mode hiện tại.
3. Khi mode = `department`: khung viền; đầu khung có icon `search`, ô lọc không viền placeholder "Tìm phòng ban...", và bộ đếm "Đã chọn {selected}/{tổng}"; dưới là danh sách cuộn (cao tối đa ~10rem) các nhãn checkbox theo tên phòng ban (lọc không phân biệt hoa thường theo chuỗi con). Rỗng: "Chưa có phòng ban" (khi không có phòng ban nào) hoặc "Không tìm thấy phòng ban".

### 2.6 `StatusDot` (`knowledge-table/status-dot`)

Prop: `source: Source`. Cột dọc: dòng chính (chấm tròn ~6px + nhãn xs đậm vừa, không xuống dòng) và dòng phụ tùy chọn (~10px, thụt trái, cắt chữ, rộng tối đa ~160px, tooltip đầy đủ).

Nhãn = `t("knowledge.status.{status}", nhãn dự phòng)`; trạng thái không biết dùng kiểu của `pending` và nhãn là chính chuỗi status.

| status | Chấm | Màu chữ | Nhãn dự phòng |
|---|---|---|---|
| `ready` | Xanh lục (emerald) | Xanh lục đậm | "Sẵn sàng" |
| `processing` | Hổ phách, nhấp nháy (pulse) | Hổ phách đậm | "Đang xử lý" |
| `pending` | Xám đá, nhấp nháy | Muted | "Chờ xử lý" |
| `plan_ready` | Xanh dương | Xanh dương | "Chờ duyệt kế hoạch" |
| `awaiting_approval` | Cam | Cam | "Chờ duyệt dung lượng" |
| `partial` | Hổ phách | Hổ phách đậm | "Hoàn tất một phần" |
| `error` | Destructive | Destructive | "Lỗi" |

Dòng phụ:

| status | Nội dung | Tông |
|---|---|---|
| `processing` | "{progress}%" (nếu có) và `progress_message`, nối " · " | muted |
| `pending` | `progress_message` hoặc "Đang xếp hàng" | muted |
| `error`, `partial` | ưu tiên `error_message`, rồi `wiki_error_message`, `chunk_error_message`, `progress_message`; không có thì không hiện | destructive 80% |
| `plan_ready`, `awaiting_approval` | "Cần xem xét để tiếp tục" | muted |
| `ready` | "Nguyên văn theo Điều" nếu `preserve_verbatim`; ngược lại "Wiki lỗi — chỉ có đoạn trích" (tông lỗi) nếu `wiki_status === "error"`; ngược lại "{wiki_page_count} trang wiki" nếu > 0 | muted / lỗi |

### 2.7 `PlanReviewDialog` (`knowledge-table/plan-review-dialog`)

Props: `source`, `onClose()`, `onDone()`.

Dữ liệu: `GET /api/sources/{id}/plan` → `{ id, status, plan, review_note }`; `plan` = `{ pages: PlanPage[], strategy?, compilation_notes?, estimated_page_count?, source_page_slug? }`; `PlanPage` = `{ action: "CREATE"|"UPDATE", slug, title, page_type, entity_names?: string[], priority?: number, related_kb_pages?: string[] }`. Trạng thái kế hoạch mặc định trước khi tải là `pending_review`. Lỗi tải → message hoặc `common.error`.

Polling: khi `status` kế hoạch = `regenerating`, tải lại mỗi 3000 ms cho đến khi đổi trạng thái. "Đang tạo lại" = status `regenerating` hoặc đang gửi yêu cầu regenerate.

Bố cục (dialog rộng tối đa `2xl`, cao tối đa 85% viewport, thân cuộn):

- Tiêu đề: icon `fact_check` 20px màu xanh dương + `plan.title`; dưới: `plan.subtitle` thay `{title}` bằng title tài liệu (muted).
- Đang tải: spinner. Lỗi: khối destructive nhạt.
- Đang tạo lại: khối xanh dương nhạt viền xanh dương, icon quay + `plan.regenerating`; nội dung kế hoạch mờ 50% và không tương tác.
- Hàng tóm tắt (chữ sm muted): chấm xanh lục + "{số CREATE} `plan.toCreate`"; chấm vàng + "{số UPDATE} `plan.toUpdate`"; nếu có `strategy`: icon `analytics` + chuỗi strategy.
- Nếu có `compilation_notes`: khối viền nền secondary nhạt chữ xs: "`plan.plannerNote` " (đậm) + nội dung.
- Danh sách trang (CREATE trước UPDATE, rồi sắp tăng theo `priority`, thiếu coi là 99): mỗi thẻ viền nền card gồm Badge outline nhỏ hiển thị action (CREATE viền/chữ xanh lục; UPDATE vàng), tiêu đề trang (sm đậm vừa), slug (~10px mono muted), Badge secondary nhỏ hiển thị `page_type` (giá trị `concept` hiển thị "page"; viết hoa chữ đầu); dòng dưới ~11px muted: tối đa 5 `entity_names` nối ", " cộng " +{n} more" nếu nhiều hơn.
- Ô góp ý (textarea cao ~64px, không đổi kích thước, placeholder `plan.feedbackPlaceholder`, vô hiệu khi đang tạo lại) và dòng hướng dẫn `plan.feedbackHelp`.
- Footer (viền trên, hai đầu):
  - Trái: nút outline sm icon `refresh` + `plan.regenerateBtn` (khi đang tạo lại: icon quay + `common.retrying`). Vô hiệu khi đang tải/đang gửi/đang tạo lại. Bấm: nếu ô góp ý trống (sau trim) → lỗi `plan.feedbackRequired`; ngược lại `POST /api/sources/{id}/plan/regenerate` body `{ note }`; thành công → đặt trạng thái cục bộ `regenerating` (kích hoạt polling), xóa ô góp ý, hủy trạng thái xác nhận từ chối.
  - Phải: nút ghost `common.cancel` (→ onClose; vô hiệu khi đang gửi); nút từ chối hai bước: lần đầu là nút outline chữ destructive icon `close` + `plan.rejectBtn` (chỉ chuyển sang bước xác nhận), lần hai là nút destructive icon `close` (quay khi gửi) + `plan.confirmRejectBtn` → `POST /api/sources/{id}/plan/reject` body `{ note: góp ý hoặc "Rejected via UI" }`; nút primary icon `check` (quay khi gửi) + `plan.approveBtn` → `POST /api/sources/{id}/plan/approve` body `{ note: góp ý hoặc "Approved via UI" }`. Duyệt/từ chối thành công → `onDone`; lỗi → hiện lỗi và cho thao tác lại.

### 2.8 `ExtractionReviewDialog` (`knowledge-table/extraction-review-dialog`)

Props: `source`, `onClose()`, `onDone()`. Dialog rộng tối đa ~560px.

- Tiêu đề: icon `scale` màu cam + `extraction.title`. Mô tả muted: `extraction.desc`.
- Thẻ viền: tên (title hoặc file_name, cắt chữ) và lưới 3 cột căn giữa, số lớn font mono đậm, nhãn xs muted:

  | Số | Nhãn |
  |---|---|
  | `extracted_token_count` (định dạng rút gọn) | `extraction.tokens` |
  | `page_count` | `extraction.pages` |
  | `image_count` | `extraction.images` |

  Định dạng token: ≥ 1.000.000 → chia triệu, 2 chữ số thập phân + "M"; ≥ 1.000 → chia nghìn, làm tròn + "K"; còn lại số nguyên. Giá trị thiếu coi là 0.
- Khối nền muted nhạt: tiêu đề `extraction.fitsInContext`; hai dòng cho hai cửa sổ ngữ cảnh tham chiếu — "Claude 4 / Gemini 3 / GPT-5 (1M)" (1.000.000 token) và "GPT-4o / GPT-4-turbo (128K)" (128.000 token). Ngân sách = làm tròn(cửa sổ × 0,85). Mỗi dòng: icon `check_circle` xanh lục nếu token ≤ ngân sách, ngược lại `warning` cam; chữ "{tên} — " + `extraction.budget` thay `{budget}`. Nếu token > 850.000: thêm dòng nghiêng muted `extraction.multiPassNote`.
- Lỗi: khối destructive nhạt.
- Nút (căn phải):
  - Outline: hai bước. Lần đầu nhãn `extraction.cancelDelete` (chỉ chuyển sang xác nhận, nút chuyển viền/chữ destructive, nhãn `extraction.confirmCancelDelete`); lần hai gọi `DELETE /api/sources/{id}`; khi gửi nhãn `common.loading`.
  - Primary: `extraction.approveProcess` → `POST /api/sources/{id}/approve-extraction`; khi gửi nhãn `common.loading`.
  - Cả hai vô hiệu khi đang gửi. Thành công → `onDone`; lỗi → message hoặc `common.error`.

### 2.9 `SourceArticlesDrawer` (`knowledge-table/source-articles-drawer`)

Hiển thị trong một hàng bảng chiếm toàn bộ 13 cột ngay dưới dòng tài liệu khi mở rộng (nền hàng muted ~15%, không đệm ô).

Props: `source?: { id, title, file_name? }`, `sourceId?: string`, `sourceTitle?: string`, `onClose?()`. Id hiệu lực = `source.id` hoặc `sourceId`.

Dữ liệu: `GET /api/wiki/pages?source_id={id}&limit=1000` → mảng `WikiPageSummary` (dùng `slug`, `title`, `summary`). Không phải mảng hoặc lỗi → rỗng.

Phân loại:

- **Trang tổng quan** = trang đầu tiên có tiêu đề không bắt đầu bằng "Điều " hoặc slug chứa "tong-quan".
- **Điều** = các trang tiêu đề bắt đầu "Điều ", sắp xếp theo locale `vi` có so sánh số (Điều 2 trước Điều 10).
- **Trang khác** = các trang không phải tổng quan và không bắt đầu "Điều ".
- Lọc Điều (không phân biệt hoa thường) theo tiêu đề, slug hoặc summary chứa chuỗi tìm.

Bố cục (nền muted 40%, viền trên, đệm ngang ~24px, hiệu ứng mờ dần khi xuất hiện):

- Header hai đầu: icon `menu_book` primary + "Mục lục Điều luật ({số Điều} Điều)" (xs đậm); nếu có trang tổng quan: nút-link nhỏ nền primary 10% icon `open_in_new` "Xem toàn văn Trang Tổng quan & Căn cứ" → `/wiki/{slug}`. Phải: ô lọc cao ~28px (rộng ~200–280px, icon `search`, placeholder "Lọc số Điều (VD: Điều 4, Điều 15)...", nút "✕" xóa) và nếu có `onClose`: nút icon `close` tooltip "Đóng bảng Điều".
- Đang tải: icon quay + "Đang tải danh sách Điều...".
- Không có trang nào: "Văn bản này chưa có trang Wiki Điều luật nào được bóc tách."
- Lưới Điều (1/2/3/4 cột theo breakpoint sm/md/lg, cuộn khi cao quá ~320px): mỗi ô là link tới `/wiki/{slug}`, viền nhạt nền card, chấm xanh lục nhỏ (phóng to khi hover) + tiêu đề rút gọn (phần trước " - " đầu tiên), tooltip tiêu đề đầy đủ. Nếu lọc không ra: "Không tìm thấy Điều nào khớp với \"{chuỗi}\"".
- Nếu có trang khác: ngăn cách viền trên, nhãn "Các trang tri thức liên quan ({n}):" và các chip link nền secondary tới `/wiki/{slug}`.

### 2.10 `KnowledgeTypeCards` (`components/types/knowledge-type-cards`) — tab "Kiểu tri thức"

Props: `types: KnowledgeType[]`, `loading: boolean`, `onEdit(type)`, `onRefresh()`, `onCreate()`, `onViewDocuments(typeId)`. Chỉ được dùng ở `/knowledge`.

| Trạng thái | Hiển thị |
|---|---|
| `loading` (metadata chưa tải lần đầu) | Spinner toàn khối |
| Rỗng | Khung viền nền card chứa `EmptyState` icon `category`, tiêu đề "Chưa có kiểu tri thức", mô tả "Tạo kiểu tri thức để phân loại tài liệu, ví dụ: Văn bản luật, Quy định nội bộ.", action nút primary sm "Thêm kiểu tri thức" → onCreate |
| Có dữ liệu | Banner lỗi (nếu có) + lưới thẻ 1/2/3 cột (md/xl), khoảng cách ~12px |

Mỗi thẻ (viền, nền card, đệm ~16px, hover viền primary 30%):

- Hàng trên: ô vuông ~36px bo góc, nền = màu kiểu độ mờ ~10%, icon `folder` 20px màu kiểu; tên kiểu (sm đậm, cắt chữ) và slug (~11px mono muted); bên phải viên thuốc nền secondary "{source_count hoặc 0} tài liệu".
- Mô tả xs muted, tối đa 2 dòng (giữ chỗ tối thiểu 2 dòng); trống → "Chưa có mô tả" nghiêng mờ.
- Hàng dưới (viền trên): nút ghost chữ primary "Xem tài liệu" + icon `arrow_forward` 14px (vô hiệu khi số tài liệu = 0) → `onViewDocuments(id)`; bên phải nút icon ~28px `edit` (tooltip "Sửa") → onEdit; nút icon `delete` destructive (tooltip "Xóa").

Xóa: `confirm` với "Xóa kiểu tri thức \"{name}\"? {n} tài liệu sẽ chuyển về \"Chưa phân loại\"." khi n > 0, hoặc "Xóa kiểu tri thức \"{name}\"?" khi n = 0; rồi `DELETE /api/knowledge-types/{id}` → `onRefresh`; lỗi → banner lỗi message hoặc "Không xóa được kiểu tri thức".

### 2.11 `UploadDialog` (`components/knowledge/upload-dialog`)

Props: `open`, `onOpenChange(open)`, `types: KnowledgeType[]`, `departments: Department[]`, `onUploaded()`. Không cho đóng khi đang tải lên.

**Ràng buộc tệp:**

| Hạng mục | Giá trị |
|---|---|
| Đuôi chấp nhận | pdf, docx, doc, rtf, xlsx, xls, csv, txt, md, pptx, ppt (thuộc tính accept của input = các đuôi có dấu chấm, phân tách dấu phẩy). doc/ppt/rtf được server chuyển đổi bằng LibreOffice; nếu server thiếu LibreOffice, API trả lỗi rõ ràng |
| Kích thước tối đa | 50 MB mỗi tệp (50 × 1024 × 1024 byte) |
| Chọn nhiều | Có (input file `multiple`, kéo thả nhiều tệp) |
| Lỗi đuôi | "\"{tên tệp}\": định dạng .{đuôi hoặc ?} không được hỗ trợ" |
| Lỗi kích thước | "\"{tên tệp}\": vượt quá 50 MB" |
| Gộp lỗi | Hiển thị tối đa 2 lỗi nối "; ", nếu nhiều hơn thêm " (+{n})". Lần thêm tệp kế tiếp không lỗi sẽ xóa thông báo |
| Trùng lặp | Khóa tệp = "{tên}_{kích thước}"; tệp trùng khóa với tệp đã có bị bỏ qua |

**Trạng thái mặc định khi mở/đặt lại:** danh sách rỗng; kiểu tri thức = kiểu có slug `general` (nếu có), nếu không thì rỗng ("Chưa phân loại"); phạm vi = `personal`; không chọn phòng ban; không lỗi.

**Bố cục** (dialog rộng tối đa `2xl`, cao tối đa 90% viewport, header/thân cuộn/footer như EditSourceDialog):

- Header: `knowledge.upload.title`; dòng phụ "Tài liệu được trích xuất nội dung, tách điều khoản và biên soạn vào Kho tri thức."
- Section đánh số (vòng tròn ~20px nền primary 10% chứa số, nhãn sm đậm):
  1. **"Nguồn tài liệu"**:
     - Vùng thả: viền nét đứt 2px bo tròn lớn, bấm để mở hộp chọn tệp (không khi đang tải). Khi chưa có tệp: cao, xếp dọc căn giữa, vòng tròn icon ~44px; khi đã có tệp: gọn ngang, vòng tròn ~32px. Icon `upload_file`. Khi kéo qua: viền primary, nền primary 5%, vòng icon tô primary. Dòng chính: "Thả tài liệu vào đây" (đang kéo) / "Thêm tệp khác" (đã có tệp) / "Kéo thả tài liệu hoặc nhấp để chọn". Dòng phụ ~11px muted: "PDF, DOCX, DOC, RTF, XLSX, XLS, CSV, TXT, MD, PPTX · tối đa 50 MB/tệp".
     - Danh sách tệp (khi có, viền bo tròn, các dòng ngăn cách, cuộn khi cao quá ~14rem). Mỗi dòng: ô icon ~32px theo đuôi (pdf → `picture_as_pdf` tông hồng; docx/doc/rtf → `description` xanh dương; xlsx/xls/csv → `table_chart` xanh lục; pptx/ppt → `slideshow` hổ phách; md/txt → `article` xám đá; khác → `draft` primary), tên tệp (xs đậm vừa, cắt chữ, tooltip), dòng phụ = thông báo lỗi (màu destructive) hoặc "{kích thước} · .{ĐUÔI IN HOA}"; icon trạng thái 18px; nút `close` (tooltip "Bỏ tệp này") để bỏ tệp — chỉ hiện khi không đang tải và tệp chưa xong.

       | Trạng thái tệp | Icon | Màu |
       |---|---|---|
       | `queued` | `schedule` | muted |
       | `uploading` | `progress_activity` (quay) | primary |
       | `done` | `check_circle` | xanh lục |
       | `error` | `error` | destructive |

       Định dạng kích thước: < 1024 → "{n} B"; < 1 MB → "{x.x} KB"; còn lại "{x.x} MB".
  2. **"Phân loại & phạm vi"**: lưới 2 cột (cột nhãn ~7.5rem): nhãn "Danh mục" + Select kiểu tri thức (như EditSourceDialog: "Chưa phân loại" + chấm màu); nhãn `knowledge.upload.visibility` + `ScopePicker` có `allowPersonal`. Cả hai vô hiệu khi đang tải.
- Khối lỗi (destructive nhạt, icon `error`) nếu có.
- Footer hai đầu: trái chữ xs muted — "Chưa chọn tệp nào" khi danh sách rỗng, ngược lại "{số tệp chưa xong} tệp · {tổng dung lượng chưa xong}" và thêm " · đã xong {n}" nếu có tệp đã xong. Phải: nút outline `common.cancel` (vô hiệu khi đang tải); nút primary icon `upload` "Tải lên" (thêm " ({n})" khi > 1 tệp chưa xong), khi đang tải: icon quay + "Đang tải lên...".

**Điều kiện bật nút Tải lên:** không đang tải, có ≥1 tệp chưa xong, và không phải (phạm vi `department` mà chưa chọn phòng ban). Nếu vẫn bấm được trong trường hợp department rỗng → lỗi `t("dept.selectAtLeastOne", "Vui lòng chọn ít nhất một phòng ban")`.

**Quy trình tải lên:** tuần tự từng tệp chưa xong (cả tệp lỗi trước đó): chuyển trạng thái `uploading`, gửi `apiUpload("/api/sources/upload", FormData)` = `POST /api/sources/upload` multipart với các trường:

| Trường multipart | Giá trị |
|---|---|
| `file` | Tệp |
| `knowledge_type_id` | id kiểu (chỉ khi có chọn) |
| `scope_type` | `personal` \| `department` \| `global` |
| `department_ids` | id phòng ban nối bằng dấu phẩy (chỉ khi `department`) |

Không có thanh tiến độ phần trăm — tiến độ thể hiện bằng icon trạng thái từng tệp. Thành công → `done`; lỗi → `error` với message hoặc "Tải lên thất bại". Kết thúc: nếu có ≥1 thành công → `onUploaded`. Nếu không có lỗi → đóng dialog và đặt lại; nếu có lỗi → giữ dialog, lỗi "Tải lên {thành công}/{tổng} tệp. Kiểm tra các tệp lỗi bên dưới." (bấm Tải lên lần nữa chỉ gửi các tệp chưa xong).

### 2.12 `KnowledgeTypeDialog` (`components/types/knowledge-type-dialog`)

Props: `open`, `onOpenChange(open)`, `knowledgeType: { id, slug, name, color, description? } | null` (null = tạo mới), `onSaved()`. Chỉ được dùng ở `/knowledge`.

Mỗi lần mở (hoặc đổi đối tượng) form được đặt lại: tên, slug, màu (mặc định màu chàm/indigo của bảng màu có sẵn nếu tạo mới), mô tả từ đối tượng; slug coi như "đã sửa tay" khi đang ở chế độ sửa.

Dialog rộng tối đa `md`; tiêu đề cỡ lg: "Sửa kiểu tri thức" hoặc "Thêm kiểu tri thức". Form:

1. **Xem trước:** khung viền nét đứt nền muted nhạt: chữ "Xem trước" + viên thuốc giống cột "Kiểu tri thức" của bảng (chữ màu đã chọn, viền/nền cùng màu nhạt) với tên đã trim hoặc "Tên kiểu tri thức".
2. **"Tên kiểu tri thức"**: input bắt buộc, tự focus, placeholder "VD: Quy định nội bộ".
3. **"Mã định danh"** kèm chú thích nhỏ "(dùng trong URL/bộ lọc)": input font mono xs, placeholder "quy-dinh-noi-bo". Khi chưa sửa tay, giá trị tự sinh từ tên: bỏ dấu tiếng Việt (đ/Đ → d), chữ thường, mọi chuỗi ký tự ngoài a–z/0–9 thành một dấu gạch ngang, bỏ gạch ở hai đầu. Khi người dùng gõ: đánh dấu đã sửa tay, chuyển chữ thường và loại bỏ mọi ký tự ngoài a–z, 0–9 và "-". Ở chế độ sửa, nếu slug khác slug gốc: cảnh báo ~11px màu hổ phách "Đổi mã sẽ làm hỏng các liên kết cũ dùng mã này."
4. **"Màu"**: hàng các nút tròn ~28px cho 10 màu có sẵn theo thứ tự: xám, xanh lục (emerald), tím (violet), hổ phách, xanh dương, đỏ, hồng, xanh mòng két (teal), cam, chàm (indigo); nút đang chọn có viền 2px màu foreground và phóng to nhẹ (so sánh không phân biệt hoa thường); aria-label = mã màu. Nút cuối là vòng gradient cầu vồng với icon `add` ở giữa (tooltip "Chọn màu khác") mở bộ chọn màu gốc của trình duyệt.
5. **"Mô tả"**: textarea 2 dòng, placeholder "Loại tài liệu nào thuộc kiểu tri thức này...".
6. Lỗi: khối destructive nhạt.
7. Nút: outline "Hủy"; submit "Tạo kiểu tri thức" / "Lưu thay đổi" (khi lưu: "Đang lưu..."), vô hiệu khi đang lưu hoặc tên trống.

API: body `{ name: tên đã trim, slug: slug hiệu lực hoặc bỏ nếu rỗng, color, description }`. Tạo: `POST /api/knowledge-types`; sửa: `PUT /api/knowledge-types/{id}`. Thành công → `onSaved` rồi đóng; lỗi → message hoặc "Không lưu được kiểu tri thức".

### 2.13 Quan hệ với `lib/wiki-store`

Các thành phần của màn `/knowledge` KHÔNG đọc/ghi `lib/wiki-store` (store đó phục vụ màn wiki: `WikiSourceItem`, `wikiStore`, `subscribeWikiStore`, `notifyWikiStore`, `useWikiStore`, `displaySourceTitle`, `getDocForPage`, `getCachedPages`/`setCachedPages`, `removeCachedPage`, `getCachedSources`/`setCachedSources`, `getCachedPageDetail`/`setCachedPageDetail`, `getCachedSourceData`/`setCachedSourceData`). Danh sách tài liệu ở đây luôn lấy trực tiếp qua `GET /api/sources`; `SourceArticlesDrawer` gọi thẳng `GET /api/wiki/pages` và không dùng cache. Hệ quả: sau khi xóa/sửa tài liệu ở `/knowledge`, cache wiki không được làm mới chủ động từ màn này.

---

## 3. Màn `/departments` — Phòng ban

### 3.1 Mục đích & quyền

Quản lý danh sách phòng ban và thành viên. Vào màn qua sidebar khi có `org:departments:read`. Màn không kiểm tra thêm quyền cho các nút tạo/sửa/xóa (backend quyết định).

Kiểu `Department` ở màn này: `id`, `name`, `description?`, `employee_count: number`.

### 3.2 Bố cục

1. `PageHeader` với `title` "Departments", `description` "Organize employees into departments and manage knowledge access." (chuỗi tiếng Anh cứng trong nguồn; bản dịch tương ứng có sẵn ở khóa `dept.title`/`dept.description` nếu muốn bản địa hóa), `action` = nút primary icon `add` + "Add Department" (tương ứng `dept.createBtn`) → mở DepartmentDialog chế độ tạo.
2. `DepartmentCards`.
3. `DepartmentDialog`.

Tải: `GET /api/departments` → `Department[]`; lỗi → mảng rỗng. Tải khi vào trang và sau khi lưu/xóa.

### 3.3 `DepartmentCards` (`components/departments/department-cards`)

Props: `departments`, `loading`, `onEdit(dept)`, `onRefresh()`.

| Trạng thái | Hiển thị |
|---|---|
| loading | Spinner toàn khối |
| Rỗng | `EmptyState` icon `business`, tiêu đề `dept.noDepts`, mô tả `dept.noDeptsDesc` (không có action) |
| Có dữ liệu | Lưới 1/2/3 cột (md/lg), khoảng cách ~20px |

Mỗi thẻ (nền card, bo tròn lớn, đệm ~24px, viền, bóng nhẹ, hover viền primary 30%, cột dọc):

- Ô vuông ~40px nền primary 10% icon `business` màu primary; tên phòng ban (cỡ base đậm); dòng xs muted "{employee_count} `dept.employees`".
- Mô tả (nếu có) sm muted tối đa 2 dòng.
- Hàng nút (đẩy xuống đáy, viền trên), nút ghost sm chữ xs có icon nhỏ:

  | Nút | Icon | Hành động |
  |---|---|---|
  | `dept.members` | `group` | Mở `DeptMembersDialog` cho phòng ban |
  | `common.edit` | `edit` | `onEdit(dept)` |
  | `common.delete` (chữ destructive) | `delete` | `confirm(t("dept.deleteConfirm"))` → `DELETE /api/departments/{id}` → `onRefresh` (lỗi không được bắt/hiển thị riêng) |

### 3.4 `DepartmentDialog` (`components/departments/department-dialog`)

Props: `open`, `onOpenChange`, `department: { id, name, description? } | null`, `onSaved()`. Mỗi lần mở/đổi đối tượng: nạp lại tên, mô tả, xóa lỗi.

Dialog rộng tối đa `md`, tiêu đề cỡ xl: `dept.editTitle` / `dept.createTitle`. Trường:

| Nhãn | Điều khiển | Ràng buộc |
|---|---|---|
| `dept.nameLabel` | Input, placeholder "e.g. Sales, Engineering" | Bắt buộc (HTML required) |
| `dept.descLabel` | Textarea 3 dòng, placeholder `type.descPlaceholder` | Tùy chọn |

Nút: outline `common.cancel`; submit primary `common.save` (sửa) / `common.create` (tạo), khi lưu hiển thị `common.loading`, vô hiệu khi lưu.

API: body `{ name, description }`; tạo `POST /api/departments`, sửa `PUT /api/departments/{id}`. Thành công → `onSaved`, đóng. Lỗi → khối destructive nhạt message hoặc `common.error`.

### 3.5 `DeptMembersDialog` (`components/departments/dept-members-dialog`)

Props: `open`, `onOpenChange`, `deptId: string`, `deptName: string`.

Khi mở: xóa lỗi, bỏ chọn; `GET /api/employees?department_id={deptId}&page_size=200` → `items[]` (thành viên; lỗi → rỗng); `GET /api/employees?page_size=500` → `items[]` (toàn bộ nhân sự; lỗi bỏ qua). Nhân sự dùng `id`, `name`, `email`, `department_ids`.

Bố cục (dialog rộng tối đa `xl`; tiêu đề cỡ xl `dept.membersTitle` thay `{name}` bằng tên phòng ban):

1. Khối lỗi (nếu có).
2. Hàng thêm: Select nhân sự chưa thuộc phòng ban (placeholder `dept.selectEmpToAdd`, mục "{name} — {email}") + nút primary `dept.addMember` (khi lưu: icon quay), vô hiệu khi lưu hoặc chưa chọn. Bấm → `POST /api/employees/{empId}/departments` body `{ department_id: deptId }` → bỏ chọn, tải lại thành viên. Lỗi → message hoặc `common.error`.
3. Khung danh sách giống ScopeMembersDialog: đầu khung "`dept.currentMembers` ({n})"; đang tải spinner; rỗng `EmptyState` icon `group_off`, `dept.noMembers`, `dept.noMembersDesc`; dòng: tên + email, nút ghost sm icon `close` (aria-label "Remove {name} from {deptName}", hover destructive) → `DELETE /api/employees/{empId}/departments/{deptId}` (không hỏi xác nhận) → tải lại.
4. Ghi chú xs muted `dept.memberMultiHint`.

---

## 4. Màn `/employees` — Nhân sự & phân quyền

### 4.1 Mục đích & quyền

Quản lý tài khoản nhân sự, phòng ban của họ, token MCP; tab thứ hai hiển thị ma trận phân quyền RBAC. Vào màn khi có `org:employees:read`. Màn không ẩn nút theo quyền.

Kiểu `Employee`: `id`, `name`, `email`, `role` (`admin` hoặc `employee`), `global_role` (`viewer` | `contributor` | `knowledge_manager` | `admin`), `department_ids: string[]`, `department_names: string[]`, `is_active: boolean`, `has_token: boolean`, `last_connected?`.

Danh sách vai trò cố định truyền cho dialog (id → tên hiển thị): `viewer` → "Viewer", `contributor` → "Contributor", `knowledge_manager` → "Knowledge Manager", `admin` → "System Admin".

### 4.2 Bố cục

1. `PageHeader` phụ thuộc tab:

   | Tab | title | description | action |
   |---|---|---|---|
   | `employees` (mặc định) | "Nhân viên & Tài khoản" | "Quản lý danh sách nhân sự, phân nhóm phòng ban và tài khoản truy cập MCP." | Nút primary icon `person_add` + "Thêm nhân viên" → EmployeeDialog chế độ tạo |
   | `rbac` | "Quản lý Phân quyền & Vai trò" | "Thiết lập quyền truy cập chi tiết (RBAC) cho từng vai trò trong toàn bộ hệ thống." | (không có) |

2. Thanh tab kiểu gạch chân (viền dưới cả hàng, cách dưới ~24px). Mỗi tab là nút chữ sm đậm vừa, icon 18px, viền dưới 2px; tab chọn: viền và chữ primary, đậm hơn; không chọn: viền trong suốt, chữ muted, hover chữ foreground và viền border.
   - Tab 1: icon `group`, "Danh sách Nhân viên", kèm viên thuốc mono ~11px nền muted hiển thị `total` khi > 0.
   - Tab 2: icon `admin_panel_settings`, "Ma trận Phân quyền (RBAC)".
3. Nội dung: tab 1 → `EmployeeTable`; tab 2 → `RolesPermissionsCard` (thành phần thuộc phần cài đặt/phân quyền, đặc tả ở tài liệu 07 tương ứng về Cài đặt; trang chỉ render nó không truyền prop).
4. `EmployeeDialog`.

Tải: `GET /api/employees?page={p}&page_size=20` cộng `search` nếu có → `{ items, total, page, page_size, total_pages }`; trang hiện tại lấy theo `page` trả về. Lỗi → danh sách rỗng. Phòng ban: `GET /api/departments` một lần khi vào trang (lỗi bỏ qua). Tìm kiếm → đặt trang 1 và tải lại. Sau lưu/thao tác → tải lại trang và từ khóa hiện tại.

### 4.3 `EmployeeTable` (`components/employees/employee-table`)

Props: `employees`, `loading`, `onEdit(emp)`, `onRefresh()`, `page`, `totalPages`, `total`, `onPageChange(p)`, `search`, `onSearch(q)`.

**Banner lỗi thao tác** (destructive nhạt, icon `error`, không có nút đóng) ở trên cùng khi có lỗi.

**Hàng tìm kiếm** (hai đầu): form chứa ô tìm cao ~36px rộng ~280px, icon `search` bên trái, placeholder `common.search`; gửi form (Enter) → `onSearch(chuỗi)` (không debounce); khi có chữ hiện nút `close` → xóa chữ và `onSearch("")`. Bên phải: "{total} `dept.employees`" (xs muted).

**Khung bảng** (nền card, bo tròn lớn, viền, bóng nhẹ):

| Điều kiện | Hiển thị |
|---|---|
| loading | Spinner toàn khối |
| Rỗng | `EmptyState` icon `badge`; tiêu đề `common.noResults` (nếu đang tìm) hoặc `emp.noEmployees`; mô tả "{common.noResults}: \"{search}\"" khi đang tìm, ngược lại rỗng |

Cột (tiêu đề ~11px IN HOA đậm muted; hàng tiêu đề không đổi nền khi hover):

| Tiêu đề (i18n) | Nội dung |
|---|---|
| `emp.colEmp` | Avatar tròn ~32px chứa chữ cái đầu của tên (viết hoa, đậm); nền primary 15% chữ primary nếu `role === "admin"`, ngược lại nền accent. Bên cạnh: tên (sm đậm vừa) và email (xs muted), cắt chữ |
| `emp.colRole` | Badge nhỏ (cao ~20px, ~10px) nhãn theo `global_role`: `admin` → `emp.roleAdmin` (variant default/đặc primary), `knowledge_manager` → `emp.roleKM` (outline), `contributor` → `emp.roleContributor`, `viewer` → `emp.roleViewer` (secondary), giá trị khác → nguyên chuỗi (secondary) |
| `emp.colDept` | Các chip nhỏ nền secondary cho từng `department_names`; rỗng → "—" |
| `emp.colStatus` | Chấm ~8px + chữ xs: hoạt động → chấm xanh lục, chữ xanh lục đậm, `emp.statusActive`; không → chấm muted 40%, chữ muted, `emp.statusInactive` |
| `emp.colToken` | Nếu `has_token`: icon `vpn_key` (kiểu tô đặc) + `emp.connected` màu xanh lục; ngược lại "—" |
| (trống, căn phải, ~60px) | Menu thao tác |

Hover dòng: nền secondary 30%. Nút menu: vuông ~28px icon `more_vert`, **ẩn (trong suốt) cho đến khi hover dòng**. Menu căn phải, icon mục 16px:

| Mục | Icon | Điều kiện | API / hành động |
|---|---|---|---|
| `common.edit` | `edit` | Luôn | `onEdit(emp)` |
| `emp.statusInactive` (khi đang hoạt động) / `emp.statusActive` (khi bị khóa) | `lock` / `lock_open` | Luôn | `PATCH /api/employees/{id}/toggle` → onRefresh; lỗi "Action failed" |
| `scope.project` | `folder_shared` | Luôn | Mở `ScopeDialog` với `label` = tên, `employeeId` = id |
| (ngăn cách) | | | |
| `emp.generateToken` | `vpn_key` | Luôn | `POST /api/employees/{id}/token` → `{ token, instructions }`; mở dialog token; onRefresh; lỗi "Failed to generate token" |
| `emp.revokeToken` (destructive) | `key_off` | `has_token` | `confirm(t("emp.revokeToken"))` → `DELETE /api/employees/{id}/token` → onRefresh; lỗi "Failed to revoke token" |
| (ngăn cách) | | | |
| `common.delete` (destructive) | `delete` | Luôn | `confirm(t("common.delete"))` → `DELETE /api/employees/{id}` → onRefresh; lỗi "Failed to delete" |

**Phân trang** (chỉ khi `totalPages > 1`, hai đầu, cách trên ~16px):

- Trái: "`common.page` {page} `common.of` {totalPages}" (xs muted).
- Phải: nút outline `chevron_left` (vô hiệu trang 1); tối đa 7 nút số trang vuông ~32px (trang hiện tại variant default nền primary, còn lại outline); nút `chevron_right` (vô hiệu trang cuối). Cửa sổ 7 số: nếu tổng ≤ 7 hiện 1..tổng; nếu trang hiện tại ≤ 4 hiện 1..7; nếu trang hiện tại ≥ tổng−3 hiện (tổng−6)..tổng; còn lại (trang−3)..(trang+3).

**Dialog token MCP** (rộng tối đa `lg`): tiêu đề cỡ xl icon `vpn_key` primary + "MCP Token Generated"; đoạn muted "Copy this token and share it securely with the employee. It will not be shown again."; khối nền secondary font mono, ngắt mọi ký tự, chọn-tất-cả khi bấm, chứa `token`; nếu có `instructions` hiển thị giữ xuống dòng. Nút: outline icon `content_copy` "Copy Token" (ghi token vào clipboard); primary "Done" (đóng). Đóng dialog xóa dữ liệu token khỏi bộ nhớ.

### 4.4 `EmployeeDialog` (`components/employees/employee-dialog`)

Props: `open`, `onOpenChange`, `employee: Employee | null` (null = tạo), `departments: Department[]`, `roles?: { id, name }[]` (mặc định rỗng), `onSaved()`.

Khởi tạo mỗi lần mở/đổi đối tượng/đổi danh sách phòng ban:

- Sửa: tên, email từ nhân sự; vai trò = `global_role` hoặc `viewer`; phòng ban = `department_ids`; mật khẩu rỗng.
- Tạo: rỗng; vai trò `viewer`; phòng ban = phòng ban đầu tiên trong danh sách (nếu có).

Dialog rộng tối đa `md`; tiêu đề cỡ xl `emp.editTitle` / `emp.createTitle`. Trường:

| Nhãn | Điều khiển | Ràng buộc / ghi chú |
|---|---|---|
| `emp.name` | Input | Bắt buộc (required) |
| `emp.email` | Input type email | Bắt buộc, kiểm tra định dạng email của trình duyệt |
| `emp.password` (+ `emp.passwordEditHint` khi sửa) | Input type password; placeholder "••••••••" khi sửa, `emp.passwordMinHint` khi tạo | Tạo: bắt buộc — thiếu thì lỗi `emp.passwordRequired` (kiểm tra trên client trước khi gọi API). Sửa: để trống = giữ nguyên. Độ dài tối thiểu do server kiểm tra |
| `emp.role` (cột trái của lưới 2 cột) | Select với các mục từ `roles` | |
| `emp.departments` (cột phải) | Select "thêm" luôn có giá trị rỗng, trigger hiển thị chữ muted `emp.addDeptPlaceholder`. Mục: các phòng ban chưa chọn; một đường ngăn; mục cuối màu primary đậm vừa icon `add` + `emp.createNewDept` (giá trị đặc biệt tạo mới). Chọn phòng ban → thêm vào danh sách. Popup có thể rộng hơn trigger theo nội dung | Dưới Select: các chip nền secondary cho mỗi phòng ban đã chọn, mỗi chip có nút `close` (aria-label "Remove {tên}", hover destructive) để bỏ; rỗng → dòng nghiêng muted `emp.noDeptsHint` |

**Dialog con "Tạo phòng ban"** (mở khi chọn mục tạo mới; rộng tối đa `sm`): tiêu đề `emp.createDeptModalTitle`; nhãn `emp.createDeptModalLabel`; input tự focus, Enter để gửi; lỗi (chữ destructive) nếu có; nút outline `common.cancel`, nút primary `common.create` (khi lưu `common.loading`; vô hiệu khi lưu hoặc rỗng). Gửi `POST /api/departments` body `{ name: chuỗi đã trim, description: "" }` → phản hồi `Department` (`id`, `name`) được thêm vào danh sách phòng ban cục bộ của dialog và tự động được chọn; đóng dialog con. Lỗi → hiển thị message (hoặc chuỗi lỗi).

**API lưu:** body:

| Trường | Giá trị |
|---|---|
| `name` | tên |
| `email` | email |
| `role` | `admin` nếu vai trò chọn là `admin`, ngược lại `employee` |
| `global_role` | id vai trò đã chọn |
| `department_ids` | mảng id phòng ban đã chọn |
| `password` | chỉ gửi khi có nhập |

Tạo: `POST /api/employees`; sửa: `PUT /api/employees/{id}`. Thành công → `onSaved`, đóng. Lỗi → khối destructive nhạt message hoặc `common.error`. Nút: outline `common.cancel`; submit primary `common.save` / `common.create` (khi lưu `common.loading`).

---

## 5. Tổng hợp endpoint dùng trong 07c

| Method | Path | Tham số / body | Dùng ở |
|---|---|---|---|
| GET | `/api/sources` | `page`, `page_size`, `sort`, `search?`, `knowledge_type_id?`, `department_id?`, `status?` (CSV) | Bảng tài liệu |
| GET | `/api/sources/{id}` | — (dùng `download_url`) | Tải tệp gốc |
| PATCH | `/api/sources/{id}` | `title?`, `knowledge_type_id`, `scope_type`, `scope_id`, `department_ids`, `doc_meta?` | Chỉnh sửa tài liệu |
| DELETE | `/api/sources/{id}` | — | Xóa tài liệu / hủy ở duyệt dung lượng |
| POST | `/api/sources/{id}/retry` | `branch?` = `chunk` \| `wiki` \| `all` | Chạy lại |
| POST | `/api/sources/upload` | multipart `file`, `knowledge_type_id?`, `scope_type`, `department_ids?` | Tải lên |
| GET | `/api/sources/{id}/plan` | — | Duyệt kế hoạch |
| POST | `/api/sources/{id}/plan/approve` | `{ note }` | Duyệt kế hoạch |
| POST | `/api/sources/{id}/plan/reject` | `{ note }` | Từ chối kế hoạch |
| POST | `/api/sources/{id}/plan/regenerate` | `{ note }` | Tạo lại kế hoạch |
| POST | `/api/sources/{id}/approve-extraction` | — | Duyệt dung lượng |
| POST | `/api/wiki/legal-docs/backfill` | query `only_missing`, `use_llm=true` | Xử lý nội dung |
| GET | `/api/sources/processing-summary` | — → `{ failed, failed_ai_outage, running, review, chunk_missing, pages_missing_vectors }` | Xử lý nội dung (quyền `org:settings:manage`) |
| POST | `/api/sources/retry-failed` | query `only_ai_outage` → `{ requeued, skipped_busy, skipped_cap, skipped_other[], message }` | Xử lý nội dung (quyền `org:settings:manage`) |
| POST | `/api/sources/reembed-missing` | — → `{ job_id, candidates, message }` | Xử lý nội dung (quyền `org:settings:manage`) |
| POST | `/api/settings/embeddings/backfill-source-chunks` | query `limit?`, `force?` → `{ job_id, candidates, enqueued, message }` | Xử lý nội dung |
| GET | `/api/wiki/legal-doc-fields` | — → `{ fields }` | Chỉnh sửa tài liệu |
| GET | `/api/wiki/pages` | `source_id`, `limit=1000` | Ngăn kéo Điều |
| GET/POST | `/api/knowledge-types` | POST: `{ name, slug?, color, description }` | Kiểu tri thức |
| PUT/DELETE | `/api/knowledge-types/{id}` | PUT: như POST | Kiểu tri thức |
| GET/POST | `/api/departments` | POST: `{ name, description }` | Phòng ban, metadata |
| PUT/DELETE | `/api/departments/{id}` | PUT: `{ name, description }` | Phòng ban |
| GET | `/api/employees` | `page?`, `page_size`, `search?`, `department_id?` | Nhân sự, thành viên |
| POST | `/api/employees` | `name`, `email`, `role`, `global_role`, `department_ids`, `password` | Tạo nhân sự |
| PUT/DELETE | `/api/employees/{id}` | PUT: như POST, `password` tùy chọn | Sửa/xóa nhân sự |
| PATCH | `/api/employees/{id}/toggle` | — | Khóa/mở khóa |
| POST/DELETE | `/api/employees/{id}/token` | POST → `{ token, instructions }` | Token MCP |
| POST | `/api/employees/{id}/departments` | `{ department_id }` | Thêm thành viên phòng ban |
| DELETE | `/api/employees/{id}/departments/{deptId}` | — | Gỡ thành viên phòng ban |
| GET/POST | `/api/scopes/{scopeType}/{scopeId}/members` | POST: `{ employee_id, role }` | ScopeMembersDialog |
| DELETE | `/api/scopes/{scopeType}/{scopeId}/members/{employeeId}` | — | ScopeMembersDialog |
