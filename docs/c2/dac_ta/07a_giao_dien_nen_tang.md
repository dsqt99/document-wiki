# 07a. Giao diện: nền tảng, bố cục chung, module dùng chung

Tài liệu thuộc bộ đặc tả giao diện 07 (mục lục ở `07_giao_dien.md`). Phần này mô tả nền kỹ thuật của frontend, khung trang (thanh bên, chuông thông báo, menu người dùng), hệ thống thiết kế ở mức token, các primitive shadcn cần có, và **giao diện (tên export, tham số, hành vi) của các module nền** mà file loại C trong `frontend/src` của c2 đang import. Người code chỉ dựa vào tài liệu này, các file loại C và test; không mở mã nguồn gốc.

Quy ước: nhãn hiển thị ghi theo khóa i18n trong `frontend/src/lib/i18n.tsx` (file loại C, đã có). Biểu tượng ghi theo **tên ligature của bộ Google Material Symbols Outlined** (bộ biểu tượng mà giao diện gốc dùng gần như toàn bộ), kèm gợi ý tên lucide tương đương ở chỗ quan trọng.

---

## 1. Nền kỹ thuật

### 1.1 Phiên bản và công cụ

| Hạng mục | Yêu cầu |
|---|---|
| Framework | Next.js dòng 16 (App Router, thư mục `src/app`), React 19, TypeScript 5 |
| Biên dịch | Bật React Compiler (tùy chọn `reactCompiler` của Next, plugin babel React Compiler 1.0) |
| Đầu ra build | `output: standalone` để chạy bằng `node server.js` trong image Node 22 alpine, cổng 3000, host 0.0.0.0, tắt telemetry |
| CSS | Tailwind CSS 4 qua plugin PostCSS chính thức, gói `tw-animate-css` cho hiệu ứng vào/ra |
| Thư viện UI | shadcn/ui, **style "base-nova"** (biến thể dựng trên `@base-ui/react`, không phải Radix), base color `neutral`, dùng CSS variables, không prefix, icon library `lucide`. Alias: `@/components`, `@/components/ui`, `@/lib`, `@/lib/utils`, `@/hooks` |
| Tiện ích | `clsx`, `tailwind-merge`, `class-variance-authority` |
| Markdown | `react-markdown` 10, `remark-gfm`, `remark-frontmatter`, `rehype-raw` |
| Đồ thị | `react-force-graph-2d`, `d3-force`, `d3-drag` |
| So sánh văn bản | `diff` |
| Biểu tượng | Google Material Symbols Outlined (tải qua Google Fonts, trục biến thiên FILL 0..1, wght 100..700); `lucide-react` chỉ dùng bên trong primitive (dấu tích, mũi tên chọn, nút đóng) |
| Phông chữ | Manrope (Google Fonts, trọng số 200..800) làm phông giao diện và tiêu đề; phông mono hệ thống (Cascadia Code / JetBrains Mono / ui-monospace). Trang gốc có nạp thêm một phông serif cổ điển nhưng không dùng cho thành phần chính |
| Ngôn ngữ trang | Thẻ `html` có `lang="vi"` và chặn cảnh báo hydration (thuộc tính lang/class đổi ở client) |
| Metadata | Tiêu đề trang "Document Wiki — Enterprise AI Knowledge Hub"; mô tả tiếng Việt về hệ thống quản trị tri thức doanh nghiệp và máy chủ MCP cho tác tử AI |
| Logo | Một ảnh vuông `public/logo.png` (nhóm tự cung cấp, **không chép ảnh gốc**), favicon riêng |

### 1.2 Cây Provider gốc

Layout gốc (`src/app/layout.tsx`) bọc toàn bộ ứng dụng theo thứ tự từ ngoài vào trong: `AuthProvider` → `ThemeProvider` → `I18nProvider` → `TooltipProvider` → nội dung trang. Thẻ `head` nạp hai stylesheet Google Fonts (Manrope; Material Symbols Outlined) cùng `preconnect` tới hai máy chủ font.

### 1.3 Địa chỉ API, proxy và rewrite

- Biến môi trường build-time `NEXT_PUBLIC_API_URL`: tiền tố ghép trước mọi đường dẫn API ở trình duyệt. **Nếu biến được đặt (kể cả chuỗi rỗng) thì dùng nguyên giá trị**; chỉ khi hoàn toàn không đặt mới mặc định `http://localhost:5055`. Triển khai thực tế đặt rỗng để trình duyệt gọi cùng origin và đi qua rewrite.
- Biến môi trường `INTERNAL_API_URL` (mặc định `http://127.0.0.1:5055`): địa chỉ backend mà máy chủ Next proxy tới.
- Rewrite của Next (giữ nguyên đường dẫn phía sau):

| Nguồn | Đích |
|---|---|
| `/api/:path*` | `{INTERNAL_API_URL}/api/:path*` |
| `/mcp` | `{INTERNAL_API_URL}/mcp/` (thêm dấu `/` cuối) |
| `/mcp/:path*` | `{INTERNAL_API_URL}/mcp/:path*` |
| `/oauth/:path*` | `{INTERNAL_API_URL}/oauth/:path*` |
| `/.well-known/:path*` | `{INTERNAL_API_URL}/.well-known/:path*` |

- Dockerfile ba tầng (cài phụ thuộc bằng `npm ci`, build với hai ARG trên, runtime chạy bằng user không phải root, chép `public`, `.next/standalone`, `.next/static`).

### 1.4 Xác thực và lưu token

- Token truy cập (JWT do backend cấp) lưu ở **localStorage, khóa `arkon_token`**. Mọi request gắn header `Authorization: Bearer <token>` nếu có token.
- Cờ phiên SSO: localStorage khóa `arkon_sso` = `"1"` khi phiên đến từ đăng nhập SSO (Keycloak). Đăng nhập bằng mật khẩu xóa cờ này.
- Khi tải trang: nếu có token thì gọi `GET /api/auth/me`; không có token thì coi như chưa đăng nhập ngay (không gọi API).
- `GET /api/auth/me` lỗi 401 hoặc 403 → xóa token, `user = null`. Lỗi khác → `user = null` nhưng giữ token.
- Đăng xuất: xóa token và cờ SSO. Nếu phiên là SSO → điều hướng toàn trang tới `{API_BASE}/api/auth/sso/logout` (để Keycloak kết thúc phiên) và **giữ nguyên `user` trong bộ nhớ** để guard của portal không đẩy về `/login` chen ngang. Nếu không phải SSO → `user = null`, nơi gọi tự chuyển tới `/login?logged_out=1`.
- Guard portal: xem mục 2.1.
- Trang `/logout/sso` (đã có trong c2) là đích front-channel logout của Keycloak: nếu cờ `arkon_sso` = `"1"` thì xóa token và cờ; không hiển thị gì.
- Chi tiết trang `/login`, `/login/sso` và vòng chống lặp đăng nhập (`lib/login-round.ts`, đã có) nằm ở `07b`.

### 1.5 Chế độ nhúng (iframe trong chatbot)

Đã có trong c2: `lib/embed.ts`, `lib/theme.tsx`. Tóm tắt hành vi để các trang khác tuân theo:

- "Đang nhúng" = cửa sổ không phải cửa sổ trên cùng (hoặc truy cập `window.top` bị chặn). Phía server luôn coi là không nhúng.
- Khi nhúng, `ThemeProvider` đặt thuộc tính `data-embed="1"` trên thẻ `html`. CSS toàn cục dùng thuộc tính này để: (a) đổi sang **bảng màu của chatbot** (màu nhấn đỏ sẫm, nền trắng, xám trung tính; bản tối dùng nền xám than trung tính và màu nhấn đỏ hồng nhạt); (b) **ẩn phần chữ của `PageHeader`** (vùng có `data-slot="page-header-text"`), và ẩn hẳn khối `PageHeader` (`data-slot="page-header"`) nếu nó không có vùng hành động (`data-slot="page-header-action"`), vì trang cha đã hiện tiêu đề.
- Giao diện sáng/tối khi nhúng theo trang cha: lấy từ tham số `?theme=light|dark` lần đầu, sau đó theo tin nhắn `postMessage` có `type: "cahy-host:theme"` từ cửa sổ cha; lưu ở sessionStorage khóa `dw-embed-theme`. Lựa chọn giao diện người dùng đổi khi nhúng chỉ giữ trong bộ nhớ, không ghi localStorage.
- Trang báo cho trang cha bằng `postToHost` (gửi `{source: "cahy-wiki", type, path}` với `type` là `ready` | `navigate` | `auth-required`). Đường dẫn gửi đi bỏ hai tham số `embed` và `theme` (`currentPathForHost`).
- Layout portal khi nhúng: không có thanh bên, nội dung chiếm toàn màn hình, lề nhỏ hơn (xem 2.1). Khi chưa đăng nhập, dùng `replace` thay vì `push` để không chèn lịch sử vào trang cha.

### 1.6 Giao diện sáng/tối và ngôn ngữ

- `ThemeProvider` (đã có): chủ đề `light | dark | system`, lưu localStorage khóa `dw-theme`, mặc định `system`. Áp dụng bằng cách thêm/bỏ class `dark` trên `html`; ở chế độ `system` theo dõi `prefers-color-scheme` và cập nhật khi đổi. Tailwind cấu hình biến thể `dark` theo "phần tử nằm trong `.dark`".
- `I18nProvider` (đã có): `vi | en`, lưu localStorage khóa `dw-lang`, mặc định `vi`; `t(key, fallback?)` tra từ điển ngôn ngữ hiện tại, rồi tiếng Anh, rồi fallback, cuối cùng trả chính khóa. Mọi nhãn dùng `t()`; nhiều chỗ còn chữ tiếng Việt viết cứng (được trích nguyên nhãn trong các phần 07b..07g).

---

## 2. Bố cục chung

### 2.1 Layout nhóm `(portal)`

Mọi trang trừ `/login`, `/login/sso`, `/logout/sso` nằm trong nhóm route `(portal)` và dùng layout sau:

1. **Đang tải phiên** (`loading` của auth): màn hình trống nền chính, giữa màn hình là biểu tượng `progress_activity` cỡ lớn màu nhấn quay tròn và dòng chữ nhỏ màu phụ "Loading...".
2. **Chưa đăng nhập** (hết loading, `user` rỗng): không vẽ gì; chuyển hướng tới `/login?next=<đường dẫn hiện tại + query, đã encode>`; nếu đường dẫn hiện tại là `/` thì chỉ tới `/login`. Khi nhúng dùng replace, không nhúng dùng push.
3. **Đã đăng nhập, đang nhúng**: một cột `main` cao bằng màn hình, nội dung cuộn dọc bên trong, lề trong nhỏ (khoảng 16px, 20px từ md), các khối con cách nhau khoảng 20px. Mỗi lần đăng nhập xong hoặc đổi pathname, gửi `postToHost` `ready` (lần đầu) rồi `navigate` (các lần sau).
4. **Đã đăng nhập, không nhúng**: hàng ngang cao bằng màn hình, không cuộn ở cấp trang: bên trái `Sidebar`, bên phải `main` chiếm phần còn lại; bên trong `main` là vùng cuộn dọc với lề trong rộng dần theo breakpoint (khoảng 24px → 32px ở md → 40px ở lg, nhưng lề trên luôn nhỏ khoảng 16px), các khối con cách nhau khoảng 32px, chiều rộng đầy đủ (không giới hạn max-width ở cấp layout).

Không có thanh header trên cùng (một component header cũ tồn tại nhưng không được dùng; mọi chức năng người dùng nằm trong menu ở đầu thanh bên). Dưới breakpoint md, thanh bên ẩn hoàn toàn.

### 2.2 Thanh bên (Sidebar)

**Kích thước và trạng thái**: rộng khoảng 240px khi mở, khoảng 60px khi thu gọn; chuyển đổi có hiệu ứng khoảng 200ms. Trạng thái thu gọn lưu localStorage khóa `sidebar-collapsed` (`"true"`/`"false"`), đọc khi mount. Phím tắt **Ctrl+B / Cmd+B** bật/tắt thu gọn (chặn hành vi mặc định). Nền thanh bên là xám slate rất nhạt (bản tối: xanh than gần đen, hơi trong), viền phải mảnh, không cho chọn chữ. Vùng điều hướng cuộn dọc riêng với thanh cuộn mảnh chỉ hiện khi rê chuột.

**Cấu trúc từ trên xuống**:

1. **Khối thương hiệu / người dùng** (ngăn dưới bằng viền mảnh):
   - Mở: nút mở menu người dùng gồm logo vuông khoảng 26px bo góc, bên phải hai dòng: "Document Wiki" (đậm, cỡ khoảng 14px) và dòng nhỏ "`{tên}` · `{vai trò}`". Bên phải khối: chuông thông báo (mục 2.3) và nút thu gọn biểu tượng `left_panel_close`, tooltip/aria `sidebar.collapse`.
   - Thu gọn: xếp dọc, căn giữa: nút logo (mở menu người dùng), nút mở rộng biểu tượng `left_panel_open` (tooltip `sidebar.expand`), chuông thông báo thu nhỏ khoảng 90%.
2. **Điều hướng**. Mục chỉ hiện khi người dùng có **ít nhất một** quyền trong danh sách quyền yêu cầu (`hasPermission`, admin luôn đạt). Nhóm chỉ hiện khi đạt điều kiện quyền của nhóm **và** còn ít nhất một mục hiện.

| Thứ tự | Nhóm (nhãn) | Mục (nhãn) | Đường dẫn | Biểu tượng Material (lucide gợi ý) | Quyền yêu cầu (một trong) |
|---|---|---|---|---|---|
| 0 | (không nhóm) | `nav.dashboard` | `/` | `dashboard` (LayoutDashboard) | Chỉ khi `user.role === "admin"` |
| 1 | `nav.orgKnowledge` (không điều kiện nhóm) | `nav.documents` | `/knowledge` | `description` (FileText) | `doc:read:own_dept`, `doc:read:all` |
| 1 | | `nav.wiki` | `/wiki/law` | `auto_stories` (BookOpen) | `wiki:read:own_dept`, `wiki:read:all`, `doc:read:own_dept`, `doc:read:all` |
| 1 | | `nav.skills` | `/skills` | `bolt` (Zap) | `skill:read:own_dept`, `skill:read:all` |
| 1 | | `nav.prompts` | `/prompts` | `chat_paste_go` (MessageSquareShare) | không yêu cầu |
| 2 | `nav.organization` (nhóm cần `org:departments:read` hoặc `org:employees:read`) | `nav.departments` | `/departments` | `domain` (Building2) | `org:departments:read` |
| 2 | | `nav.employees` | `/employees` | `group` (Users) | `org:employees:read` |
| 3 | `nav.system` (nhóm cần `org:audit:read`, `org:settings:read` hoặc `org:settings:manage`) | `nav.audit` | `/audit` | `policy` (ShieldCheck) | `org:audit:read` |
| 3 | | `nav.settings` | `/settings` | `settings` (Settings) | `org:settings:read` |

   Không có mục riêng cho `/wiki/review`, `/wiki/graph`, `/admin/skill-contributions`, `/profile`: các trang này vào từ nút trong trang khác hoặc menu người dùng.

   **Quy tắc mục đang chọn**: mục `href` là "đang chọn" khi pathname bằng `href` hoặc bắt đầu bằng `href + "/"`, **trừ khi** có một mục khác dài hơn và cụ thể hơn cũng khớp. `/` chỉ khớp đúng `/`. Riêng mục `nav.wiki` (`/wiki/law`) còn được coi là đang chọn khi: pathname là `/` và người dùng không phải admin (trang chủ của người không phải admin là kho tri thức); hoặc pathname là `/wiki`; hoặc pathname bắt đầu bằng `/wiki/` nhưng không bắt đầu bằng `/wiki/review`.

   **Hình thức mục (mở)**: hàng cao khoảng 30px, bo góc vừa, chữ khoảng 13px đậm vừa, thụt nhẹ bên trái so với tiêu đề nhóm, biểu tượng khoảng 19px nét mảnh (FILL 0, độ đậm mảnh). Mục đang chọn: nền màu nhấn rất nhạt (khoảng 10%), chữ và biểu tượng màu nhấn, biểu tượng chuyển dạng đặc (FILL 1), chữ đậm hơn, đổ bóng rất nhẹ và **chấm tròn nhỏ màu nhấn ở mép phải**. Mục thường: chữ xám slate, rê chuột thì nền xám nhạt và chữ đậm màu hơn.
   **Tiêu đề nhóm (mở)**: chữ rất nhỏ (khoảng 10px), in hoa, đậm, giãn chữ, màu xám nhạt; nhóm cách nhau khoảng 16px.
   **Thu gọn**: mỗi mục là ô vuông khoảng 40px căn giữa, chỉ có biểu tượng khoảng 20px (phóng nhẹ khi rê); mục đang chọn có thêm viền màu nhấn nhạt. Rê chuột hiện tooltip bên phải với nhãn mục. Thay cho tiêu đề nhóm là một gạch ngang ngắn khoảng 24px.
3. **Chân thanh bên** (viền trên mảnh): mở → chữ rất nhỏ màu xám `brand.internal`; thu gọn → biểu tượng `dns` rất nhỏ, mờ, tooltip `brand.internal`.

### 2.3 Menu người dùng (mở từ logo / tên ở đầu thanh bên)

Dropdown căn trái, rộng khoảng 224px, bo góc lớn, bóng đậm, không cho chọn chữ. Từ trên xuống:

1. Khối thông tin: tên (đậm, nhỏ) và vai trò (rất nhỏ, màu phụ, viết hoa chữ đầu). Đường phân cách.
2. Mục `user.profile` biểu tượng `person` → điều hướng `/profile`. Đường phân cách.
3. Hàng "Giao diện": nhãn `theme.title` bên trái; bên phải nhóm nút phân đoạn (nền xám nhạt, viền) gồm ba nút biểu tượng: `light_mode` (`theme.light`), `dark_mode` (`theme.dark`), `desktop_windows` (`theme.system`). Nút đang chọn có nền popover, chữ màu nhấn, viền vòng màu nhấn nhạt. Bấm nút **không đóng menu**.
4. Hàng "Ngôn ngữ": nhãn `language.title`; nhóm nút phân đoạn hai nút: cờ Việt Nam + "VI" (tooltip "Tiếng Việt"), cờ Anh + "EN" (tooltip "English"). Không đóng menu khi bấm. Đường phân cách.
5. Mục `user.signOut` biểu tượng `logout`, chữ màu đỏ cảnh báo, nền đỏ nhạt khi focus → gọi `logout()`; nếu hàm trả false (không phải SSO) thì chuyển `/login?logged_out=1`.

### 2.4 Chuông thông báo và ngăn thông báo

**Chuông**: nút tròn khoảng 36px, biểu tượng `notifications` màu phụ, aria-label/tooltip "Notifications". Huy hiệu số chưa đọc ở góc trên phải: viên tròn đỏ cảnh báo, chữ trắng rất nhỏ đậm, hiện khi > 0, quá 99 hiện "99+".

| Hành vi | API | Ghi chú |
|---|---|---|
| Đếm chưa đọc khi mount và **mỗi 30 giây** | `GET /api/notifications/unread-count` → `{count: number}` | Lỗi bỏ qua im lặng |
| Mở ngăn (bấm chuông) | `GET /api/notifications?limit=50` → mảng `NotificationItem` | Đặt loading trong lúc tải |
| Đánh dấu tất cả đã đọc | `POST /api/notifications/read-all` | Đặt `read_at` hiện tại cho mọi mục chưa đọc ở client, số chưa đọc = 0 |
| Bấm một thông báo chưa đọc | `POST /api/notifications/{id}/read` | Thành công: đặt `read_at`, giảm số chưa đọc 1 (không âm). Lỗi bỏ qua. Sau đó luôn đóng ngăn (chưa có deep-link) |

**Ngăn thông báo**: lớp phủ toàn màn hình nền đen mờ khoảng 30% (bấm vào để đóng), ngăn trượt bên phải rộng tối đa khoảng 448px, cao toàn màn hình, nền chính, viền trái, bóng lớn, role dialog, aria-label `common.notifications`.
- Đầu ngăn: biểu tượng `notifications` + tiêu đề `common.notifications`; bên phải nút chữ màu nhấn "đánh dấu đã đọc tất cả" (chỉ hiện khi có mục chưa đọc; nhãn lấy khóa `common.clear`, fallback "Mark all read") và nút đóng biểu tượng `close` (aria `common.close`).
- Thân: đang tải và chưa có mục → chữ `common.loading` giữa ngăn. Rỗng → chữ màu phụ (khóa `audit.noLogs`, fallback "No notifications yet."). Có mục → danh sách ngăn bằng đường kẻ; mỗi mục là nút toàn hàng: biểu tượng theo loại, cột giữa gồm `subject` (đậm nếu chưa đọc, màu phụ nếu đã đọc), `body` tối đa 2 dòng chữ nhỏ, thời gian tương đối; mục chưa đọc có nền màu nhấn rất nhạt và chấm tròn nhỏ màu nhấn bên phải.
- Biểu tượng/màu theo chuỗi `type` (xét theo thứ tự, "chứa chuỗi con"): `approved` → `check_circle` xanh lục; `rejected` → `cancel` đỏ cảnh báo; `changes_requested` → `edit_note` xanh dương; `resubmitted` → `refresh` (màu mặc định hổ phách); `withdrawn` → `remove_circle` màu phụ; còn lại → `inbox` màu hổ phách.
- Thời gian tương đối: dưới 60 giây "just now"; dưới 1 giờ "{n}m ago"; dưới 1 ngày "{n}h ago"; dưới 7 ngày "{n}d ago"; còn lại ngày + tháng viết tắt theo locale trình duyệt.

Kiểu `NotificationItem` (`src/types/notification.ts`, cần viết):

| Trường | Kiểu |
|---|---|
| `id` | string |
| `type` | string (vd. chứa `approved`, `rejected`, `changes_requested`, `resubmitted`, `withdrawn`) |
| `subject` | string |
| `body` | string |
| `target_type` | string |
| `target_id` | string |
| `actor_id` | string hoặc null |
| `read_at` | string ISO hoặc null |
| `created_at` | string ISO |

### 2.5 Bản đồ route

| Route | Mô tả | Đặc tả chi tiết |
|---|---|---|
| `/login` | Đăng nhập (mật khẩu, nút SSO, tự chuyển SSO) | 07b |
| `/login/sso` | Nhận token sau SSO | 07b |
| `/logout/sso` | Front-channel logout (đã có) | 07a mục 1.4, 07b |
| `/` | Bảng điều khiển (admin); người khác được chuyển về kho tri thức | 07b |
| `/profile` | Hồ sơ cá nhân, token MCP | 07b |
| `/audit` | Nhật ký kiểm toán | 07b |
| `/knowledge` | Thư viện tài liệu nguồn (tải lên, trạng thái xử lý, duyệt trích xuất/kế hoạch) | 07c |
| `/departments` | Phòng ban | 07c |
| `/employees` | Nhân sự | 07c |
| `/wiki` | Chuyển hướng server sang `/wiki/law` | 07d |
| `/wiki/[...slug]` | Trang wiki: đọc, sửa, bản nháp | 07d |
| `/wiki/graph` | Đồ thị tri thức | 07d |
| `/wiki/branches/[id]/rebase` | Gộp lại nhánh bản nháp | 07d |
| `/wiki/review` | Hàng đợi phê duyệt bản nháp | 07e |
| `/wiki/law` | Danh sách văn bản (đã có) | 07e |
| `/wiki/law/[key]` | Chi tiết văn bản pháp luật | 07e |
| `/skills`, `/skills/[slug]`, `/skills/[slug]/edit` | Thư viện kỹ năng AI, chi tiết, trình sửa | 07f |
| `/admin/skill-contributions` | Duyệt đóng góp kỹ năng | 07f |
| `/prompts` | Kho prompt | 07f |
| `/settings` | Cài đặt hệ thống (nhiều tab) | 07g |

---

## 3. Hệ thống thiết kế (mô tả ở mức token)

Định nghĩa token bằng CSS variables theo quy ước shadcn (`background`, `foreground`, `card`, `popover`, `primary`, `secondary`, `muted`, `accent`, `destructive`, `border`, `input`, `ring`, `chart-1..5`, `sidebar-*`), rồi ánh xạ sang màu Tailwind qua khối theme inline. Ngoài bộ chuẩn có thêm các token thương hiệu dùng lẻ tẻ: `sahara` (bằng màu nhấn), `sahara-foreground`, `sahara-container` (một bậc nhấn đậm hơn, dùng làm nền ô biểu tượng của `StatCard`), `sahara-muted` (nhấn nhạt), `surface`, `surface-variant`. Tên các token này giữ nguyên để class ở file loại C (nếu có tham chiếu) vẫn chạy.

### 3.1 Bảng màu theo vai trò

| Vai trò | Sáng (mặc định) | Tối | Chế độ nhúng sáng / tối |
|---|---|---|---|
| Nền trang | Xám slate cực nhạt, gần trắng | Xanh than rất tối, gần đen | Trắng / xám than trung tính |
| Thẻ, popover | Trắng | Xanh than đậm hơn nền một bậc (popover sáng hơn thẻ một chút) | Trắng / xám than sáng hơn nền một bậc |
| Chữ chính | Xanh than gần đen | Trắng ngà xanh | Đen trung tính / trắng ngà |
| Màu nhấn (`primary`, `ring`) | Xanh coban tươi | Xanh lam sáng (pastel) | Đỏ sẫm (đỏ huyết dụ) / đỏ hồng nhạt |
| Chữ trên màu nhấn | Trắng | Gần đen | Trắng / gần đen |
| Phụ (`secondary`, `muted`, `accent`) | Xám slate rất nhạt | Xanh than xám | Xám trung tính rất nhạt / xám than |
| Chữ phụ | Xám slate trung bình | Xám slate sáng | Xám trung tính trung bình |
| Cảnh báo (`destructive`) | Đỏ tươi | Đỏ san hô nhạt | Đỏ tươi / đỏ hồng nhạt |
| Viền, ô nhập | Xám slate nhạt | Xanh than xám | Xám trung tính nhạt / xám than |
| Biểu đồ 1..5 | Coban, lục lam, xanh lam, xanh lam nhạt, xám slate | Xanh lam sáng, lục lam sáng, chàm, tím nhạt, xám slate | Các sắc đỏ từ đậm đến nhạt + xám |

Màu trạng thái dùng trực tiếp thang màu Tailwind theo vai trò: thành công = ngọc lục bảo (emerald), cảnh báo/chờ = hổ phách (amber), thông tin = xanh dương, lỗi = đỏ / `destructive`, trung tính = slate. Nền huy hiệu trạng thái thường là màu đó độ đậm 10–15%, chữ màu đó bậc 600–700 (bản tối bậc 300–400).

### 3.2 Hình khối, mật độ, chữ

- **Bán kính**: một bán kính cơ sở cỡ vừa (khoảng 10px); các bậc sm/md/lg/xl/2xl/3xl/4xl là bội số của cơ sở (khoảng 0,6×, 0,8×, 1×, 1,4×, 1,8×, 2,2×, 2,6×). Thẻ và khối nội dung thường dùng bậc xl; nút, ô nhập bậc lg; huy hiệu bo tròn hẳn.
- **Đổ bóng**: rất nhẹ. Thẻ thống kê dùng bóng "nâng tinh tế" (hai lớp mờ rất nhạt, tông xanh than). Dialog và dropdown dùng vòng viền mảnh màu chữ ở độ mờ 10% thay vì viền đậm.
- **Mật độ**: gọn, kiểu công cụ doanh nghiệp. Nút mặc định cao khoảng 32px, nút `sm` khoảng 28px, `xs` khoảng 24px; ô nhập cao khoảng 32–36px; hàng bảng gọn; chữ thân phổ biến 13–14px, chữ phụ 11–12px, nhãn siêu nhỏ 10px in hoa giãn chữ cho tiêu đề nhóm.
- **Chữ**: Manrope cho cả thân và tiêu đề (h1–h4 dùng phông tiêu đề). Tiêu đề trang (`PageHeader`) cỡ lớn khoảng 30px (36px từ lg), giãn chữ âm nhẹ, độ đậm thường. Số liệu dùng chữ số đều bề rộng (tabular). Mã, khóa, ID dùng mono cỡ nhỏ.
- **Biểu tượng Material Symbols**: mặc định FILL 0, wght 400, optical size 24, line-height 1; có biến thể "đặc" (FILL 1) bật bằng một class bổ trợ `filled`. Cỡ thường gặp 13–20px trong hàng, 40–48px trong trạng thái rỗng.
- **Chuyển động**: dropdown/dialog phóng và mờ dần khoảng 100ms; sheet trượt khoảng 200ms; nút nhấn dịch xuống 1px khi active. Có một keyframe "quét" (vạch sáng chạy lên xuống) dùng cho hiệu ứng đang quét OCR/tài liệu.
- **Toàn cục**: mọi phần tử viền mặc định màu `border`, outline focus màu `ring` 50%; `body` nền `background`, chữ `foreground`, khử răng cưa.

---

## 4. Primitive shadcn cần có (`src/components/ui/*`)

Khởi tạo shadcn với style **base-nova** (base color neutral, CSS variables, icon lucide) rồi thêm các primitive dưới đây bằng CLI shadcn (mã MIT). Các file loại C và các trang dựa vào đúng tên export và hành vi base-ui sau:

| File | Export | Ghi chú hành vi mà nơi dùng phụ thuộc |
|---|---|---|
| `button.tsx` | `Button`, `buttonVariants` | `variant`: `default` (nền màu nhấn), `outline`, `secondary`, `ghost`, `destructive` (nền đỏ nhạt 10%, chữ đỏ, không phải nền đỏ đặc), `link`. `size`: `default`, `xs`, `sm`, `lg`, `icon`, `icon-xs`, `icon-sm`, `icon-lg`. Nhận mọi prop của nút, `disabled`, `title`, `className` |
| `input.tsx` | `Input` | Nhận mọi prop của thẻ input (`value`, `onChange`, `type`, `placeholder`, `maxLength`, `className`) |
| `label.tsx` | `Label` | Nhãn form, nhận `className`, `htmlFor` |
| `textarea.tsx` | `Textarea` | Như textarea gốc |
| `switch.tsx` | `Switch` | Base-ui Switch: `checked`, `onCheckedChange(checked)`, `disabled`, `size` = `default` hoặc `sm`. Bật = nền màu nhấn |
| `checkbox.tsx` | `Checkbox`, kiểu `CheckboxProps` | **Không** dùng primitive base-ui: là input checkbox gốc (forwardRef) tự vẽ ô vuông 16px viền màu nhấn, khi chọn nền màu nhấn và hiện dấu tích lucide trắng. Nhận mọi prop input trừ `onChange`, thêm `onCheckedChange(checked: boolean)` |
| `dropdown-menu.tsx` | `DropdownMenu`, `DropdownMenuPortal`, `DropdownMenuTrigger`, `DropdownMenuContent`, `DropdownMenuGroup`, `DropdownMenuLabel`, `DropdownMenuItem`, `DropdownMenuSub`, `DropdownMenuSubTrigger`, `DropdownMenuSubContent`, `DropdownMenuCheckboxItem`, `DropdownMenuRadioGroup`, `DropdownMenuRadioItem`, `DropdownMenuSeparator`, `DropdownMenuShortcut` | Base-ui Menu. `DropdownMenuTrigger` tự là một nút và được tạo kiểu trực tiếp bằng `className` (không có `asChild`). `DropdownMenuContent` nhận `align` (mặc định start), `alignOffset`, `side` (mặc định bottom), `sideOffset` (mặc định 4), tự bọc Portal. `DropdownMenuItem` có `variant` `default`/`destructive`, `onClick`. `DropdownMenuCheckboxItem`: `checked`, `onCheckedChange`. `DropdownMenuRadioGroup`: `value`, `onValueChange`. `DropdownMenuRadioItem`: `value`, và prop base-ui `closeOnClick` |
| `select.tsx` | `Select`, `SelectGroup`, `SelectValue`, `SelectTrigger`, `SelectContent`, `SelectLabel`, `SelectItem`, `SelectSeparator`, `SelectScrollUpButton`, `SelectScrollDownButton` | Base-ui Select: `value`, `onValueChange(value \| null)` (nơi dùng phải xử lý null) |
| `dialog.tsx` | `Dialog`, `DialogTrigger`, `DialogPortal`, `DialogClose`, `DialogOverlay`, `DialogContent`, `DialogHeader`, `DialogFooter`, `DialogTitle`, `DialogDescription` | `Dialog`: `open`, `onOpenChange(open)`. `DialogContent` có `showCloseButton` (mặc định true, nút X ghost góc phải), mặc định rộng tối đa cỡ "sm" từ breakpoint sm (nơi dùng nới rộng bằng className). `DialogFooter` có tùy chọn hiện nút đóng dạng outline |
| `sheet.tsx` | `Sheet`, `SheetTrigger`, `SheetClose`, `SheetPortal`, `SheetOverlay`, `SheetContent`, `SheetHeader`, `SheetFooter`, `SheetTitle`, `SheetDescription` | Dựa trên Dialog base-ui; `SheetContent` có `side` = `top`/`right`(mặc định)/`bottom`/`left`, có nút đóng |
| `tabs.tsx` | `Tabs`, `TabsList`, `TabsTrigger`, `TabsContent`, `tabsListVariants` | Base-ui Tabs: `defaultValue`/`value`, `onValueChange`, `orientation`. `TabsList` có `variant` = `default` (nền xám, tab chọn nổi) hoặc `line` (gạch chân dưới tab chọn) |
| `tooltip.tsx` | `Tooltip`, `TooltipTrigger`, `TooltipContent`, `TooltipProvider` | `TooltipProvider` mặc định độ trễ 0. `TooltipTrigger` dùng prop `render` (truyền phần tử, ví dụ Link, để làm trigger). `TooltipContent` có `side` |
| `card.tsx` | `Card`, `CardHeader`, `CardTitle`, `CardDescription`, `CardAction`, `CardContent`, `CardFooter` | Chuẩn shadcn |
| `table.tsx` | `Table`, `TableHeader`, `TableBody`, `TableFooter`, `TableRow`, `TableHead`, `TableCell`, `TableCaption` | Chuẩn shadcn |
| `badge.tsx` | `Badge`, `badgeVariants` | `variant`: `default`, `secondary`, `destructive` (nền đỏ nhạt), `outline`, `ghost`, `link`; bo tròn hẳn, cao khoảng 20px |
| `avatar.tsx` | `Avatar`, `AvatarImage`, `AvatarFallback`, `AvatarBadge`, `AvatarGroup`, `AvatarGroupCount` | Base-ui Avatar |
| `separator.tsx` | `Separator` | Base-ui Separator |

---

## 5. Module nền bắt buộc (giao diện để file loại C chạy được)

### 5.1 Hiện trạng file trong c2 `frontend/src`

| File loại C đã có | Import mà file đó cần |
|---|---|
| `lib/i18n.tsx` | Chỉ React |
| `lib/embed.ts` | Chỉ React |
| `lib/theme.tsx` | `isEmbedded`, `useHostTheme` từ `@/lib/embed` (đã có) |
| `lib/login-round.ts` | Không |
| `lib/legal-doc.ts` | Kiểu `LegalDoc`, `Validity` từ `@/types/legal-doc` (đã có) |
| `lib/wiki-store.ts` | Kiểu `WikiPageDetail`, `WikiPageSummary` từ `@/types/wiki` (**cần viết**, đặc tả ở 07d) |
| `types/legal-doc.ts` | Không |
| `app/logout/sso/page.tsx` | `clearToken` từ `@/lib/api` (**cần viết**, mục 5.2) |
| `app/(portal)/wiki/law/page.tsx` | `api` từ `@/lib/api`; `cn` từ `@/lib/utils`; `EmptyState` từ `@/components/shared/empty-state`; `FacetGroup`, `FacetOption`, `countFacet` từ `@/components/wiki/wiki-facets` (07d); `FormattedInlineText` từ `@/components/wiki/formatted-inline-text` (07d); kiểu từ `@/types/legal-doc`; hàm từ `@/lib/legal-doc` |
| `components/shared/library-list.tsx` | `cn`; `Input` từ `@/components/ui/input`; `DropdownMenu`, `DropdownMenuCheckboxItem`, `DropdownMenuContent`, `DropdownMenuItem`, `DropdownMenuRadioGroup`, `DropdownMenuRadioItem`, `DropdownMenuSeparator`, `DropdownMenuTrigger` từ `@/components/ui/dropdown-menu` |
| `components/settings/custom-model-form.tsx` | `Button`, `Input`, `Label` (ui); `api` |
| `components/settings/document-processing-settings-card.tsx` | `Button`, `Switch` (ui); `api`; `PreviewStudio`, `Stat`, `TestFileDropzone` từ `./test-lab` (07g) |
| `components/settings/ocr-settings-card.tsx` | `Button` (ui); `api`; `ActivateBar`, `canActivate` từ `./model-catalog-card`; `ActiveModelChip`, `ProviderModelPicker` từ `./provider-model-picker`; `PreviewStudio`, `Stat`, `TestFileDropzone` từ `./test-lab` (07g) |

Các file chưa có và phải viết từ đặc tả: `lib/api.ts`, `lib/utils.ts`, `lib/auth.tsx`, `types/wiki.ts`, `types/notification.ts`, `lib/textarea-caret.ts`, `lib/hooks/use-image-resolver.ts`, toàn bộ `components/ui/*`, `components/shared/{empty-state,page-header,stat-card,scope-badge,scope-dialog,scope-members-dialog}.tsx`, `components/wiki/*`, `components/settings/{test-lab,model-catalog-card,provider-model-picker,embedding-settings-card,roles-permissions-card}.tsx`, `globals.css`, các layout và trang còn lại.

### 5.2 `@/lib/api` (cần viết)

Hằng nội bộ: gốc API theo mục 1.3; thời gian chờ mặc định 60 giây.

| Export | Chữ ký | Hành vi |
|---|---|---|
| `api` | hàm bất đồng bộ generic, tham số `path: string`, `options?: { method?: string; body?: unknown; headers?: Record<string,string>; timeoutMs?: number }`; trả `Promise<T>` (T mặc định unknown) | `method` mặc định GET, `timeoutMs` mặc định 60000. URL = gốc API + `path`. Header: `Content-Type: application/json` **trừ khi body là FormData**; `Authorization: Bearer` nếu có token; sau cùng trộn `headers` người gọi (ghi đè được). Body chỉ gửi khi có body và method khác GET: FormData gửi nguyên, còn lại JSON hóa. Hết giờ → hủy request và ném `ApiError` status 0, message "Request timed out"; lỗi mạng khác ném nguyên. Response không ok → cố đọc JSON làm `data` (lỗi đọc thì null); message = trường `detail` của JSON nếu có, không thì "API Error {status}"; ném `ApiError(status, message, data)`. Response ok: đọc text; rỗng (vd. 204) trả object rỗng; còn lại parse JSON |
| `apiUpload` | `path: string`, `formData: FormData`, `timeoutMs = 120000`; trả `Promise<T>` | Luôn POST multipart, chỉ gắn header Authorization. Hết giờ → `ApiError` status 0 "Upload timed out". Lỗi → như trên nhưng message mặc định "Upload Error {status}". Ok → parse JSON |
| `apiUrl` | `path: string` → string | Gốc API + path; dùng cho điều hướng trình duyệt (SSO), không phải fetch |
| `setToken` | `token: string` → void | Ghi localStorage `arkon_token` |
| `clearToken` | () → void | Xóa localStorage `arkon_token` |
| `ApiError` | lớp kế thừa Error, constructor `(status: number, message: string, data?: unknown)` | Thuộc tính công khai `status: number`, `data: unknown`, `message` |

Đọc token: phía server (không có window) coi như không có token.

### 5.3 `@/lib/utils` (cần viết)

| Export | Chữ ký | Hành vi |
|---|---|---|
| `cn` | nhận danh sách giá trị class (chuỗi, mảng, object điều kiện) → string | Ghép bằng clsx rồi gộp xung đột bằng tailwind-merge |
| `slugify` | `text: string` → string | Chuyển chữ thường, cắt khoảng trắng hai đầu, thay mọi chuỗi khoảng trắng bằng một gạch ngang, bỏ mọi ký tự không phải chữ/số ASCII, gạch dưới hoặc gạch ngang (vì vậy chữ có dấu tiếng Việt bị loại bỏ), gộp nhiều gạch ngang liên tiếp thành một |

### 5.4 `@/lib/auth` (cần viết, client component)

| Export | Mô tả |
|---|---|
| `markSsoSession()` | Ghi localStorage `arkon_sso` = `"1"` (gọi ở trang `/login/sso` sau khi nhận token) |
| kiểu `WorkspaceMembership` | `{ workspace_id: string; workspace_name: string; role: string }` |
| kiểu `User` | `{ id: string; name: string; email: string; role: "admin" \| "employee"; department_ids: string[]; department_names: string[]; permissions: string[]; workspace_memberships: WorkspaceMembership[] }` |
| `AuthProvider({children})` | Context provider, hành vi theo mục 1.4 |
| `useAuth()` | Trả trạng thái dưới đây; gọi ngoài provider thì ném lỗi "useAuth must be used within AuthProvider" |

Trạng thái `useAuth()`:

| Trường | Kiểu | Hành vi |
|---|---|---|
| `user` | `User \| null` | |
| `loading` | boolean | true cho tới khi xác định xong phiên lần đầu |
| `login(email, password)` | Promise void | `POST /api/auth/login` body `{email, password}` → `{access_token, user}`; lưu token, xóa cờ SSO, đặt user. Lỗi ném `ApiError` cho trang xử lý |
| `logout()` | boolean | Xem 1.4; trả true khi tự điều hướng đi (SSO) |
| `refresh()` | Promise void | Gọi lại `GET /api/auth/me`, cập nhật user (quy tắc lỗi ở 1.4), tắt loading |
| `hasPermission(perm)` | boolean | false nếu chưa đăng nhập; true nếu admin; còn lại kiểm `permissions` chứa đúng chuỗi |
| `canAccess(resource, action)` | boolean | false nếu chưa đăng nhập; true nếu admin; còn lại true khi `permissions` chứa `{resource}:{action}:all` hoặc `{resource}:{action}:own_dept` |
| `getWorkspaceRole(workspaceId)` | string hoặc null | null nếu chưa đăng nhập; `"admin"` nếu admin; còn lại `role` của membership trùng id, không có thì null |

Chuỗi quyền có dạng `tài_nguyên:hành_động:phạm_vi` (phạm vi `own_dept` hoặc `all`) hoặc `org:<mục>:<hành động>`; danh sách đầy đủ ở 07g (ma trận vai trò).

### 5.5 Thành phần dùng chung `@/components/shared/*`

**`EmptyState`** (`empty-state.tsx`, cần viết; trang luật đã có đang dùng). Props: `icon: string` (tên Material Symbol, bắt buộc), `title: string` (bắt buộc), `description?: string`, `action?: ReactNode`. Hiển thị: khối căn giữa theo cả hai chiều, lề trên dưới rộng (khoảng 64px); biểu tượng rất lớn (khoảng 48px) màu chữ phụ mờ 40%; tiêu đề cỡ khoảng 18px đậm vừa; mô tả chữ nhỏ màu phụ căn giữa, rộng tối đa khoảng 384px (chỉ khi có); `action` đặt dưới, cách khoảng 16px (chỉ khi có).

**`PageHeader`** (`page-header.tsx`). Props: `title: string`, `description?: string`, `action?: ReactNode`. Khối ngoài mang `data-slot="page-header"`; xếp dọc trên mobile, từ breakpoint sm thành hàng ngang căn đáy, hai đầu. Vùng chữ (`data-slot="page-header-text"`): tiêu đề cấp h2 cỡ lớn (mục 3.2), mô tả chữ nhỏ màu phụ rộng tối đa khoảng 576px. Vùng hành động (`data-slot="page-header-action"`, chỉ khi có `action`) dạt phải. Ba `data-slot` này là hợp đồng với CSS chế độ nhúng (mục 1.5).

**`StatCard`** (`stat-card.tsx`). Props: `label: string`, `value: string | number`, `icon: string`, `subtitle?: string`. Thẻ nền `card`, bo xl, viền, bóng nâng tinh tế, đệm khoảng 20px; hàng trên: nhãn chữ nhỏ màu phụ bên trái, ô biểu tượng bên phải (nền token `sahara-container`, biểu tượng trắng, bo lg); dưới: giá trị cỡ khoảng 30px phông tiêu đề, phụ đề chữ rất nhỏ màu phụ.

Các thành phần chia sẻ khác (`ScopeBadge`, `ScopeDialog`, `ScopeMembersDialog`) đặc tả ở 07c; `library-list.tsx` đã có (cách dùng ở 07f).

### 5.6 Các module khác

| Module | Đặc tả ở |
|---|---|
| `@/types/wiki`, `@/components/wiki/wiki-facets`, `@/components/wiki/formatted-inline-text`, `@/lib/textarea-caret`, `@/lib/hooks/use-image-resolver` | 07d, mục "Giao diện module bắt buộc" |
| `components/settings/test-lab`, `model-catalog-card`, `provider-model-picker` | 07g, mục "Giao diện module bắt buộc" |
