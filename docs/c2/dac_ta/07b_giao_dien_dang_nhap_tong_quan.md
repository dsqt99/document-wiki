# 07b. Giao diện: Đăng nhập, Bảng điều khiển thống kê, Hồ sơ cá nhân, Nhật ký kiểm toán

> Tài liệu này thuộc bộ đặc tả giao diện số 07. Mục lục của bộ nằm ở `07_giao_dien.md`; các phần nền tảng dùng chung (bố cục cổng `(portal)`, thanh bên, `PageHeader`, `EmptyState`, `Button`, `Badge`, `Input`, `Label`, `Table`, hệ màu theo vai trò, biểu tượng Material Symbols Outlined, cơ chế i18n `t(key, fallback)`, client API `api()`/`apiUrl()`, `useAuth`) được định nghĩa ở `07a_giao_dien_nen_tang.md`. Ở đây chỉ mô tả các màn: `/login`, `/login/sso`, `/logout/sso`, trang chủ `/` (bảng thống kê cho quản trị), `/profile` và `/audit`, cùng các thành phần riêng của chúng. Mọi nhãn được dẫn theo khóa i18n trong `frontend/src/lib/i18n.tsx`; nhãn viết cứng (không có khóa) được trích nguyên văn trong ngoặc kép.

---

## 0. Bối cảnh chung về xác thực

### 0.1. Khóa lưu trữ trình duyệt

| Kho | Khóa | Giá trị | Ai ghi / xóa |
|---|---|---|---|
| localStorage | `arkon_token` | JWT cục bộ của Kho tri thức (chuỗi) | Ghi: `setToken` (sau đăng nhập mật khẩu hoặc SSO). Xóa: `clearToken` (đăng xuất, `/logout/sso`, hoặc khi `GET /api/auth/me` trả 401/403). |
| localStorage | `arkon_sso` | `"1"` khi phiên hiện tại đến từ SSO | Ghi: `markSsoSession()` ở `/login/sso`. Xóa: khi đăng nhập mật khẩu, khi đăng xuất, ở `/logout/sso`. |
| sessionStorage | `dw-login-round` | đối tượng JSON `{ at: number (ms epoch), hops: number }` | Module `lib/login-round.ts` (xem 0.3). |
| sessionStorage | `dw-embed-theme` | `"light"` hoặc `"dark"` | Module `lib/embed.ts` (chế độ nhúng; xem 07a). |

Mọi request qua `api()` tự gắn tiêu đề `Authorization: Bearer <arkon_token>` nếu có token. Lỗi HTTP được ném thành `ApiError` có `status` và `message` = trường `detail` của JSON lỗi, nếu không có thì `"API Error <mã>"`; quá thời gian 60 giây thì message `"Request timed out"`, `status` 0.

### 0.2. `useAuth` (hành vi liên quan đến các màn ở đây)

- Khi khởi động: nếu có `arkon_token` thì gọi `GET /api/auth/me`; không có thì `loading` = false, `user` = null ngay.
- `GET /api/auth/me` trả: `id`, `name`, `email`, `role` (`"admin"` | `"employee"`), `department_ids` (mảng chuỗi), `department_names` (mảng chuỗi), `permissions` (mảng chuỗi), `workspace_memberships` (mảng `{workspace_id, workspace_name, role}`). Lỗi 401/403 thì xóa token.
- `login(email, password)`: `POST /api/auth/login` thân `{ email, password }`, phản hồi `{ access_token, user }`; lưu token, xóa `arkon_sso`, đặt `user`.
- `logout()`: trả về boolean. Đọc cờ `arkon_sso`, xóa token và cờ. Nếu là phiên SSO thì điều hướng toàn trang tới `apiUrl("/api/auth/sso/logout")` (giữ nguyên `user` để guard của cổng không chen ngang bằng chuyển sang `/login`) và trả `true`; ngược lại đặt `user` = null và trả `false`.
- `hasPermission(perm)`: admin luôn đúng; còn lại kiểm tra `perm` có trong `permissions`.
- `canAccess(resource, action)`: admin luôn đúng; còn lại đúng khi có `resource:action:all` hoặc `resource:action:own_dept`.
- `refresh()`: gọi lại `GET /api/auth/me`.

Guard của cổng `(portal)` (định nghĩa ở 07a): khi đã tải xong mà không có `user`, chuyển tới `/login?next=<đường dẫn hiện tại kèm query, đã mã hóa URL>` (nếu đường dẫn là `/` thì chỉ `/login`). Trong iframe dùng thay thế lịch sử (replace), ngoài iframe dùng push.

### 0.3. `lib/login-round.ts` (đã có sẵn trong c2, mã của nhóm)

File `frontend/src/lib/login-round.ts` trong c2 đã có, giữ nguyên. Tóm tắt hành vi để các màn dưới dùng đúng:

| Xuất | Chữ ký | Hành vi |
|---|---|---|
| `MAX_LOGIN_HOPS` | hằng số = 4 | Số lần tối đa `/login` được tự chuyển hướng đi trong một "lượt đăng nhập". |
| `LoginRound` | kiểu `{ at: number; hops: number }` | Một lượt đăng nhập đi qua nhiều trang (wiki → chatbot/Keycloak → wiki). |
| `readLoginRound()` | không tham số, trả `LoginRound` | Đọc `dw-login-round` từ sessionStorage; hợp lệ nếu `at` là số và còn trong 3 phút kể từ `at`. Không hợp lệ, hỏng hoặc sessionStorage bị chặn thì trả lượt mới `{ at: bây giờ, hops: 0 }`. |
| `saveLoginRound(round)` | `LoginRound` → không trả | Ghi vào sessionStorage; lỗi thì bỏ qua (giới hạn không còn áp dụng). |
| `clearLoginRound()` | không tham số | Xóa khóa; lỗi thì bỏ qua. |

### 0.4. `lib/embed.ts` (đã có sẵn trong c2)

Các hàm dùng ở màn đăng nhập: `useIsEmbedded()` (hook, true khi trang chạy trong iframe; phía server luôn false), `isEmbedded()` (hàm thường, cùng ý nghĩa), `postToHost(message)` gửi `postMessage` lên trang cha với thêm trường `source: "cahy-wiki"`, chỉ khi đang nhúng. Thông điệp dùng ở đây: `{ type: "auth-required", path }`.

---

## 1. Màn `/login` — điều phối đăng nhập

### 1.1. Mục đích và quyền

- Route: `/login`, nằm ngoài nhóm `(portal)` (không có thanh bên, không có guard). Ai cũng truy cập được.
- Kho tri thức không có trang đăng nhập riêng; `/login` chỉ **điều phối**: (a) ưu tiên đăng nhập qua Trợ lý ảo AI (chatbot), (b) dự phòng SSO Keycloak (thử im lặng trước), (c) form mật khẩu cục bộ dự phòng cho quản trị.
- Trang dùng `useSearchParams` nên toàn bộ nội dung bọc trong một ranh giới Suspense với fallback rỗng (cần cho build tĩnh).

### 1.2. Tham số query

| Tham số | Ý nghĩa |
|---|---|
| `next` | Đường dẫn quay về sau đăng nhập. Được làm sạch: chỉ chấp nhận chuỗi bắt đầu bằng `/`, không bắt đầu bằng `//`, không chứa dấu gạch chéo ngược; nếu là `/login`, bắt đầu bằng `/login/` hoặc `/login?` thì thay bằng `/`. Không hợp lệ hoặc thiếu → `/`. |
| `error` | Mã lỗi do backend SSO gắn khi quay về (bảng 1.5). |
| `logged_out` | Có mặt (giá trị bất kỳ) nghĩa là vừa đăng xuất. |
| `form` | Có mặt (thường `?form=1`) để mở form mật khẩu cục bộ, chỉ có tác dụng khi cấu hình cho phép. |

### 1.3. API

`GET /api/auth/sso/config` (công khai) trả:

| Trường | Kiểu | Ý nghĩa |
|---|---|---|
| `enabled` | boolean | SSO Keycloak trực tiếp đã cấu hình. |
| `chatbot_login` | boolean, có thể thiếu | Đăng nhập qua chatbot đã cấu hình (chỉ coi là bật khi đúng `true`). |
| `provider_name` | string | Tên nhà cung cấp (không hiển thị ở màn này). |
| `auto_redirect` | boolean | Không dùng ở màn này. |
| `allow_password_login` | boolean | Cho phép form mật khẩu cục bộ. |

URL chuyển hướng toàn trang (dựng bằng `apiUrl`, `next` được mã hóa URL):

| Đích | Đường dẫn |
|---|---|
| Đăng nhập qua chatbot | `GET /api/auth/sso/chatbot/login?next=<next>` ; bản im lặng thêm `&prompt=none` (chưa đăng nhập chatbot thì backend báo lỗi về thay vì hiện trang đăng nhập). |
| SSO Keycloak | `GET /api/auth/sso/login?next=<next>` ; bản im lặng thêm `&prompt=none` (không hiện form Keycloak, vì Keycloak không cho nhúng trong iframe). |

Chuyển hướng dùng thay thế lịch sử (location replace), không push.

### 1.4. Luồng xử lý

**Bước A — đã đăng nhập:** khi `useAuth` tải xong và có `user`: xóa lượt đăng nhập (`clearLoginRound`), chuyển (replace) tới `next`.

**Bước B — chưa đăng nhập:** khi tải xong và không có `user`, gọi `GET /api/auth/sso/config`, rồi:

**B1. Nếu đang nhúng trong iframe:**
1. Nếu (`chatbot_login` hoặc `enabled`) **và** không có `error`, không có `logged_out`, không có `form` → chuyển ngay tới bản **im lặng** (`prompt=none`): ưu tiên URL chatbot nếu `chatbot_login`, ngược lại URL Keycloak. Không đếm lượt.
2. Ngược lại → gửi `postToHost({ type: "auth-required", path: next })` và hiển thị thông điệp loại thông tin với văn bản của mã `sso_login_required`.

**B2. Không nhúng:**
1. Nếu có `logged_out` → xóa lượt đăng nhập trước.
2. Đọc lượt hiện tại (`readLoginRound`). Quyết định theo thứ tự ưu tiên:
   1. Nếu cả `chatbot_login` lẫn `enabled` đều tắt, **hoặc** (`form` có mặt và `allow_password_login` bật): hiển thị **form mật khẩu** nếu `allow_password_login` bật; ngược lại thông điệp lỗi của mã `sso_disabled`.
   2. Nếu có `logged_out`: thông điệp loại thông tin "Bạn đã đăng xuất khỏi Kho tri thức."
   3. Nếu có `error` và (đang dùng chatbot **hoặc** `error` khác `sso_login_required`): thông điệp lỗi theo bảng 1.5; mã không có trong bảng → "Đăng nhập không thành công." (Qua chatbot thì mọi lỗi là kết quả cuối, vì chatbot đã tự hiện trang đăng nhập khi cần.)
   4. Nếu `hops` ≥ `MAX_LOGIN_HOPS` (4): thông điệp lỗi "Không hoàn tất được đăng nhập dùng chung. Vui lòng thử lại."
   5. Nếu `chatbot_login`: chuyển tới URL chatbot (không im lặng).
   6. Còn lại (dự phòng Keycloak): chuyển tới URL Keycloak; **im lặng** trừ khi `error` = `sso_login_required` (lần im lặng trước đã thất bại vì chưa có phiên → lần này mở form Keycloak).
3. Trước mọi chuyển hướng ở bước 2.5/2.6: lưu lượt với `hops` tăng thêm 1 (`saveLoginRound`), `at` giữ nguyên.

**Lỗi khi gọi cấu hình** (mạng/5xx): nếu đang nhúng thì gửi `auth-required` lên trang cha; trong mọi trường hợp hiển thị thông điệp lỗi "Không kết nối được máy chủ Kho tri thức."

Nếu effect bị hủy (component unmount/đổi tham số) trước khi phản hồi về thì bỏ qua kết quả.

### 1.5. Bảng mã lỗi `error` → văn bản hiển thị

| Mã | Văn bản |
|---|---|
| `sso_disabled` | "Đăng nhập dùng chung chưa được cấu hình trên Kho tri thức." |
| `sso_misconfigured` | "Cấu hình đăng nhập dùng chung giữa Trợ lý ảo AI và Kho tri thức chưa khớp, liên hệ quản trị." |
| `sso_unavailable` | "Không kết nối được máy chủ đăng nhập tập trung (Keycloak)." |
| `sso_denied` | "Đăng nhập đã bị hủy hoặc bị từ chối." |
| `sso_login_required` | "Bạn chưa đăng nhập Trợ lý ảo AI." |
| `sso_state` | "Phiên đăng nhập đã hết hạn, vui lòng thử lại." |
| `sso_token` | "Không xác thực được tài khoản, vui lòng thử lại." |
| `sso_inactive` | "Tài khoản đã bị khóa trên Kho tri thức, liên hệ quản trị." |
| `sso_email_conflict` | "Email này đã gắn với một tài khoản SSO khác, liên hệ quản trị." |
| `sso_email_unverified` | "Email này đã có tài khoản Kho tri thức nhưng chưa được xác minh trên Keycloak, liên hệ quản trị." |
| (khác) | "Đăng nhập không thành công." |

### 1.6. Bố cục và trạng thái hiển thị

Toàn màn hình, nền màu nền chung, nội dung căn giữa cả hai chiều, lề ngang nhỏ (khoảng 16px); khối nội dung rộng tối đa khoảng 384px (cỡ "sm"), chiếm hết chiều ngang trên điện thoại. Có ba trạng thái:

| Trạng thái | Hiển thị |
|---|---|
| Đang chuyển (mặc định ban đầu) | Cột căn giữa: biểu tượng `progress_activity` cỡ lớn (khoảng 36px), màu nhấn chính, quay liên tục; dưới là chữ nhỏ màu chữ phụ "Đang chuyển tới trang đăng nhập…". |
| Thông điệp | Thẻ (nền thẻ, bo góc lớn, viền mảnh, đệm khoảng 24px), các phần tử xếp dọc cách nhau khoảng 16px, căn giữa chữ. (1) Đoạn văn bản: loại **lỗi** → chữ nhỏ màu đỏ cảnh báo trên nền đỏ nhạt (khoảng 10% độ đậm), bo góc, đệm nhỏ; loại **thông tin** → chữ nhỏ màu chữ chính, không nền. (2) Hành động: nếu đang nhúng → liên kết chữ nhỏ, đậm vừa, màu nhấn chính, gạch chân, mở tab mới tới `/login?next=<next>` với nhãn "Mở Kho tri thức trong tab mới để đăng nhập"; nếu không nhúng → nút chính rộng hết thẻ, nhãn "Đăng nhập lại" khi có `logged_out`, ngược lại "Thử lại". |
| Form mật khẩu | Xem 1.7. |

Nút "Thử lại"/"Đăng nhập lại": xóa lượt đăng nhập rồi tải lại toàn trang tới `/login?next=<next>` (bỏ `error`, `logged_out`, `form`), tức bắt đầu một lượt mới.

### 1.7. Form mật khẩu cục bộ (dự phòng)

Hiện khi SSO tắt và cấu hình cho phép, hoặc quản trị mở `/login?form=1` khi `allow_password_login` bật.

Thẻ cùng kiểu trên (không căn giữa chữ), các phần xếp dọc cách nhau khoảng 16px:

| Thứ tự | Thành phần | Chi tiết |
|---|---|---|
| 1 | Tiêu đề nhỏ | "Tài khoản cục bộ (dự phòng)", chữ nhỏ, đậm vừa. |
| 2 | Trường Email | Nhãn "Email"; ô nhập kiểu email, bắt buộc (kiểm tra HTML gốc của trình duyệt), tự lấy tiêu điểm, nền màu nền chung. |
| 3 | Trường Mật khẩu | Nhãn "Mật khẩu"; ô nhập kiểu mật khẩu, bắt buộc. |
| 4 | Lỗi (nếu có) | Khối chữ đỏ cảnh báo trên nền đỏ nhạt như trạng thái thông điệp lỗi; nội dung là `message` của lỗi API (thường là `detail` backend trả), dự phòng "Đăng nhập không thành công". |
| 5 | Nút gửi | Nút chính rộng hết thẻ, nhãn "Đăng nhập"; khi đang gửi thì vô hiệu và đổi nhãn "Đang đăng nhập…". |

Gửi form: xóa lỗi cũ → `useAuth().login(email, password)` (tức `POST /api/auth/login`) → thành công thì chuyển (push) tới `next`.

---

## 2. Màn `/login/sso` — điểm đáp callback SSO

- Route `/login/sso`, ngoài cổng, ai cũng vào được. Backend sau khi hoàn tất SSO chuyển trình duyệt về đây, đặt JWT cục bộ **trong fragment URL** (phần sau `#`, không bao giờ gửi lên máy chủ) dạng tham số `token=<jwt>` và `next=<đường dẫn>`.
- Chỉ xử lý một lần (chống chạy hai lần của Strict Mode ở môi trường dev).
- Luồng:
  1. Đọc `token` và `next` từ fragment (`next` thiếu → `/`).
  2. Ngay lập tức thay URL trên thanh địa chỉ và mục lịch sử bằng chỉ pathname (xóa fragment chứa token).
  3. Không có token → chuyển (replace) tới `/login?error=sso_token`.
  4. Có token → lưu `arkon_token`, đặt cờ `arkon_sso` = `"1"`, xóa lượt đăng nhập, gọi `refresh()` của `useAuth`; xong thì chuyển (replace) tới `next` nếu nó bắt đầu bằng `/` và không bắt đầu bằng `//`, ngược lại `/`.
- Giao diện: toàn màn hình, nền chung, căn giữa; biểu tượng `progress_activity` lớn màu nhấn chính quay; dưới là chữ nhỏ màu chữ phụ "Đang đăng nhập SSO…".

---

## 3. Màn `/logout/sso` — đăng xuất front-channel (đã có trong c2)

File `frontend/src/app/logout/sso/page.tsx` đã có sẵn trong c2 (mã của nhóm), giữ nguyên. Hành vi: Keycloak tải trang này trong iframe khi người dùng đăng xuất khỏi chatbot hoặc bất kỳ client nào trong realm; nếu `arkon_sso` = `"1"` thì xóa `arkon_token` và `arkon_sso`, không thì không làm gì. Trang không hiển thị gì (render rỗng). Đường dẫn này phải được khai báo làm front-channel logout URL của client wiki trong Keycloak.

---

## 4. Trang chủ `/` — Thống kê & Chẩn đoán (chỉ quản trị)

### 4.1. Mục đích và quyền

- Route `/` trong nhóm `(portal)` (có thanh bên, guard đăng nhập).
- Rẽ nhánh theo người dùng:
  - Chưa có `user` (đang xác định) → hiển thị **màn chuyển tiếp** (4.10).
  - `user.role` khác `"admin"` → hiển thị nguyên nội dung trang Wiki pháp luật (component trang của `/wiki/law`, đã có trong c2 tại `app/(portal)/wiki/law/page.tsx`) — trang chủ của nhân viên chính là danh sách wiki. Thanh bên đánh dấu mục `nav.wiki` là đang chọn trong trường hợp này.
  - `user.role` = `"admin"` → bảng Thống kê & Chẩn đoán dưới đây. Kiểm tra là theo **vai trò admin**, không theo chuỗi quyền. (Backend các API `/api/admin/stats/*` yêu cầu quyền `org:settings:manage`.)
- Nhãn mục điều hướng tương ứng: `nav.dashboard`.

### 4.2. Trạng thái và dữ liệu

| Trạng thái | Mặc định |
|---|---|
| Tab đang chọn | `overview` |
| Từ ngày | hôm nay trừ 30 ngày (theo UTC), dạng `YYYY-MM-DD` |
| Đến ngày | hôm qua (hôm nay trừ 1 ngày, UTC) |

Không lưu vào URL hay storage; tải lại trang về mặc định. Không có polling tự động.

**Tải dữ liệu** (khi `user` là admin và mỗi khi đổi Từ/Đến ngày; cũng chạy khi bấm Làm mới): gọi **song song** sáu API, chờ tất cả; một cái lỗi thì cả lượt coi là lỗi (dữ liệu cũ giữ nguyên). Đặt `loading` trong lúc chờ.

| API | Ghi chú |
|---|---|
| `GET /api/admin/stats/overview` | Không có tham số khoảng ngày (backend tự lấy 30 ngày gần nhất). |
| `GET /api/admin/stats/content?from=<từ>&to=<đến>` | |
| `GET /api/admin/stats/contribution?from=<từ>&to=<đến>` | |
| `GET /api/admin/stats/usage?from=<từ>&to=<đến>` | |
| `GET /api/admin/stats/gaps?from=<từ>&to=<đến>&limit=50` | |
| `GET /api/wiki/lint` | Chẩn đoán wiki. |

**Kiểu phản hồi:**

- Overview: `as_of` (string), `kpis` (đối tượng khóa → số hoặc null), `top_gap_topic` (null hoặc `{ normalized?, count?, samples?: string[] }`), `top_contributor` (null hoặc `{ name?, count?, author_id? }`).
- Content/Contribution/Usage (cùng dạng "section"): `from_date`, `to_date` (string), `series` (đối tượng khóa chỉ số → mảng điểm `{ date, value: number|null, dimensions?, items? }`), `latest` (khóa → số|null), `latest_lists` (khóa → mảng đối tượng tự do).
- Gaps: `{ items: [{ normalized: string, count: number, samples: string[], requester_ids: string[] }] }`.
- Lint: `{ dead_links: [{ from_slug, from_title, to_slug }], orphans: [{ slug, title, status }], contradictions: [{ slug, title }] }` (mỗi mảng có thể thiếu → coi là rỗng).

**Định dạng số:** null/không hữu hạn → "—"; trị tuyệt đối ≥ 1000 → định dạng có phân tách hàng nghìn theo locale trình duyệt; số nguyên → nguyên văn; còn lại → một chữ số thập phân.
**Định dạng thời lượng (giây):** 0/null/không hữu hạn → "—"; < 60 → số giây làm tròn kèm hậu tố "s"; < 3600 → phút một chữ số thập phân + "m"; < 86400 → giờ + "h"; còn lại → ngày + "d".

### 4.3. Bố cục tổng (trên xuống)

1. **PageHeader**: tiêu đề `stats.title`, mô tả `stats.description`; vùng hành động bên phải (xếp dưới tiêu đề trên màn hẹp) gồm hai nút viền (outline) cạnh nhau:
   - Nút **Làm mới**: biểu tượng `refresh` (quay khi đang tải) + nhãn `stats.refresh`; vô hiệu khi đang tải; bấm → tải lại toàn bộ.
   - Nút **Tổng hợp**: biểu tượng `calculate` (quay khi đang chạy) + nhãn `stats.rollup` nối một khoảng trắng và giá trị "Đến ngày" (ví dụ "Tổng hợp dữ liệu 2026-10-15"); khi đang chạy nhãn đổi thành khóa `stats.rolling` (khóa này chưa có trong `i18n.tsx` c2; nhãn dự phòng "Computing…" — có thể bổ sung khóa với nghĩa "Đang tính…"); vô hiệu khi đang chạy. Bấm → `POST /api/admin/stats/rollup?target=<Đến ngày>` (không thân), thành công thì tải lại toàn bộ; lỗi thì hiện ở khối lỗi (backend trả 400 "target must be ISO date YYYY-MM-DD" nếu ngày sai).
2. **Thanh lọc** (cách header khoảng 16px): thẻ viền mảnh, nền thẻ, bo góc lớn, đệm khoảng 12px; các phần tử nằm ngang, căn đáy, tự xuống dòng khi hẹp, cách nhau khoảng 12px:
   - Ô "Từ ngày": nhãn chữ rất nhỏ in hoa giãn chữ màu chữ phụ (`stats.from`), dưới là ô nhập kiểu ngày cao khoảng 36px.
   - Ô "Đến ngày": tương tự với `stats.to`.
   - Nhóm tab (đẩy sang phải): sáu nút nhỏ cao khoảng 36px, viền, cách nhau rất hẹp, theo thứ tự `stats.tabOverview`, `stats.tabContent`, `stats.tabContribution`, `stats.tabUsage`, `stats.tabGaps`, `stats.tabLinter` (tương ứng các tab overview, content, contribution, usage, gaps, diagnostics). Tab đang chọn: nền màu chữ chính, chữ màu nền (đảo màu); tab khác: nền chung, khi rê chuột tối nhẹ.
   - Không có nút "Áp dụng": đổi ngày là tải lại ngay.
3. **Khối lỗi** (nếu có): chữ nhỏ màu đỏ cảnh báo trên nền đỏ nhạt, bo góc, đệm vừa, biểu tượng `error` đứng trước; nội dung là message lỗi, dự phòng "Failed to load statistics" (tải) hoặc "Backfill failed" (tổng hợp).
4. **Nội dung tab** (cách khoảng 16px).

**Khung xương (skeleton)** dùng chung cho mọi tab khi dữ liệu tab đó chưa có: lưới 2 cột (từ cỡ md: 4 cột), 8 ô cao khoảng 96px, viền, nền thẻ, bo góc lớn, nhấp nháy mờ.

### 4.4. Thẻ KPI (thành phần cục bộ của trang)

Thẻ viền, bo góc lớn, đệm khoảng 12px. Dòng 1: biểu tượng nhỏ (khoảng 14px) + nhãn, chữ rất nhỏ (khoảng 11px) in hoa giãn chữ, màu chữ phụ. Dòng 2: giá trị chữ lớn (cỡ 2xl), đậm bán phần, chữ số đều độ rộng. Dòng 3 (tùy chọn): gợi ý chữ rất nhỏ màu phụ. Ba tông:

| Tông | Màu |
|---|---|
| mặc định | viền thường, nền thẻ |
| warn | viền hổ phách nhạt, nền hổ phách rất nhạt |
| good | viền xanh lục ngọc nhạt, nền xanh lục rất nhạt |

### 4.5. Tab Tổng quan (`overview`)

Chưa có dữ liệu → skeleton. Có dữ liệu, xếp dọc cách nhau khoảng 24px:

**(a) Lưới KPI** 2 cột (md: 4 cột), khe khoảng 12px, 12 thẻ theo thứ tự:

| # | Nhãn | Khóa KPI trong `kpis` | Định dạng | Biểu tượng | Tông warn khi |
|---|---|---|---|---|---|
| 1 | `stats.kpiTotalPages` | `wiki.pages.total` | số | `auto_stories` | — |
| 2 | `stats.kpiStalePages` | `wiki.pages.stale_30d` | số | `hourglass_empty` | giá trị > 0 |
| 3 | `stats.kpiOrphanPages` | `wiki.pages.orphan` | số | `link_off` | giá trị > 0 |
| 4 | `stats.kpiPagesUpdatedToday` | `wiki.pages.updated` | số | `edit_note` | — |
| 5 | `stats.kpiDraftsPending` | `draft.pending` | số | `rate_review` | — |
| 6 | `stats.kpiAvgTimeToReview` | `draft.time_to_review_avg_seconds` | thời lượng | `schedule` | — |
| 7 | `stats.kpiPlansAwaitingReview` | `compile_plan.pending_review` | số | `task_alt` | — |
| 8 | `stats.kpiDeniedAccess` | `audit.denied` | số | `block` | giá trị > 0 |
| 9 | `stats.kpiMcpActiveUsers` | `mcp.active_users` | số | `person` | — |
| 10 | `stats.kpiMcpWau` | `mcp.weekly_active_users` | số | `group` | — |
| 11 | `stats.kpiMcpQueries` | `mcp.queries.total` | số | `search` | — |
| 12 | `stats.kpiZeroResultQueries` | `mcp.queries.zero_result` | số | `search_off` | giá trị > 0 |

**(b) Hai thẻ nổi bật** (lưới 1 cột, md: 2 cột, khe khoảng 16px), mỗi thẻ viền, nền thẻ, bo góc lớn, đệm khoảng 16px, tiêu đề chữ nhỏ đậm vừa:
- Thẻ trái — tiêu đề `stats.topGapTitle`. Có `top_gap_topic`: dòng chữ lớn vừa (lg) là `normalized` (thiếu → "—"); dòng chú thích chữ rất nhỏ màu phụ: "Asked {count} times. Sample: “{samples[0]}”". Không có → chữ nhỏ màu phụ `stats.noGapNotice`.
- Thẻ phải — tiêu đề `stats.topContributorTitle`. Có `top_contributor`: dòng lớn là `name` (thiếu → "—"), chú thích "{count} drafts submitted". Không có → `stats.noContributorNotice`.

**(c) Dòng chân** chữ rất nhỏ màu phụ: "As of {as_of}".

### 4.6. Thẻ biểu đồ (thành phần cục bộ) và nút xuất CSV

- **Thẻ biểu đồ**: viền, nền thẻ, bo góc lớn, đệm khoảng 16px; hàng đầu gồm tiêu đề (chữ nhỏ, đậm vừa) bên trái và vùng hành động tùy chọn bên phải; nội dung dưới cách khoảng 12px.
- **Nút "Export CSV"**: nút dạng chữ rất nhỏ màu phụ, rê chuột đổi màu chữ chính và gạch chân. Bấm → nếu không có `arkon_token` thì không làm gì; ngược lại tải `GET /api/admin/stats/export/{section}.csv?from=<từ>&to=<đến>` với tiêu đề Bearer, nhận nội dung nhị phân và cho trình duyệt lưu tệp tên `stats_{section}_{từ}_{đến}.csv`. `section` ∈ `content`, `contribution`, `usage`, `gaps`. Không có thông báo thành công/thất bại.
- Chuỗi điểm cho biểu đồ đường lấy từ `series[<khóa>]`, chỉ giữ `date` và `value`; thiếu khóa → mảng rỗng.

Màu đường (theo vai trò, mô tả để dựng tương đương): **xanh dương** (mặc định của biểu đồ), **cam đất**, **đỏ trầm**, **tím nhạt**, **xanh lá**.

### 4.7. Tab Nội dung (`content`)

Chưa có dữ liệu → skeleton. Hai lưới (1 cột; md: 2 cột; khe khoảng 16px), cách nhau khoảng 16px:

| Lưới | Tiêu đề thẻ (viết cứng) | Loại | Nguồn | Màu |
|---|---|---|---|---|
| 1 | "Pages updated per day" | đường | `series["wiki.pages.updated"]` | xanh dương |
| 1 | "Revisions per day" | đường | `wiki.revisions.daily` | cam đất |
| 1 | "Stale pages (>30d, snapshot)" | đường | `wiki.pages.stale_30d` | đỏ trầm |
| 1 | "Orphan pages (snapshot)" | đường | `wiki.pages.orphan` | tím |
| 2 | "Pages by type" | thanh | `latest_lists["wiki.pages.by_type"]`: nhãn = `dimensions.page_type`, nếu không có thì `page_type`, nếu không có thì "—"; giá trị = `count` (thiếu → 0) | xanh dương |
| 2 | "Top edited pages" + nút Export CSV (`content`) | thanh | `latest_lists["wiki.top_pages"]`: nhãn = `title`, không có thì `slug`; giá trị = `revisions` | xanh dương |

### 4.8. Tab Đóng góp (`contribution`)

Lưới 1 (1 cột; md: 2 cột):

| Tiêu đề | Nội dung |
|---|---|
| "Drafts created per day" | đường `draft.created`, xanh dương |
| "Drafts approved / rejected" | **hai** biểu đồ đường xếp chồng dọc trong cùng thẻ: `draft.approved` màu xanh lá có nhãn phụ "Approved"; `draft.rejected` màu đỏ trầm có nhãn phụ "Rejected" |
| "Pending drafts (snapshot)" | đường `draft.pending`, cam đất |
| "Avg time-to-review (seconds)" | đường `draft.time_to_review_avg_seconds`, xanh dương |

Lưới 2 (1 cột; md: 3 cột):

| Tiêu đề | Nội dung |
|---|---|
| "Top contributors" + Export CSV (`contribution`) | thanh từ `latest_lists["draft.top_contributors"]`, nhãn `name`, giá trị `count` |
| "Top reviewers" | thanh từ `draft.top_reviewers`, nhãn `name`, giá trị `count` |
| "By source" | thanh từ `draft.created.by_source`: nhãn `dimensions.source` (thiếu → "—"), giá trị `count` |

### 4.9. Tab Sử dụng (`usage`)

Lưới 1 (md: 2 cột): "MCP queries per day" (`mcp.queries.total`, xanh dương); "Zero-result queries" (`mcp.queries.zero_result`, đỏ trầm); "Daily active users" (`mcp.active_users`, xanh lá); "Avg latency (ms)" (`mcp.latency_ms_avg`, tím).
Lưới 2 (md: 2 cột): "Queries by tool" + Export CSV (`usage`) — thanh từ `latest_lists["mcp.queries.by_tool"]`, nhãn `tool_name`, giá trị `count`; "Top employees by query count" — thanh từ `mcp.top_employees`, nhãn `name`, giá trị `count`.

### 4.10. Tab Khoảng trống (`gaps`)

- Chưa có dữ liệu → skeleton.
- `items` rỗng → thẻ viền, nền thẻ, đệm lớn (khoảng 32px), chữ nhỏ màu phụ căn giữa: "No zero-result queries in this window — your KB is covering what people search for."
- Có dữ liệu → thẻ viền bo góc, tràn ẩn:
  - Thanh tiêu đề (đệm ngang 16px, dọc 12px, viền dưới): trái "Top knowledge gaps (zero-result queries)" (chữ nhỏ, đậm vừa); phải nút Export CSV (`gaps`).
  - Bảng rộng hết, chữ nhỏ. Đầu bảng: chữ rất nhỏ in hoa giãn chữ màu phụ, nền xám rất nhạt.

| Cột | Căn | Nội dung |
|---|---|---|
| "Topic (normalized)" | trái | `normalized`, đậm vừa |
| "Count" | phải | `count`, chữ số đều độ rộng |
| "Sample queries" | trái | tối đa 2 mẫu đầu của `samples`, mỗi mẫu một dòng, đặt trong ngoặc kép cong, chữ rất nhỏ màu phụ, cắt bằng dấu ba chấm khi quá khoảng 420px |
| "Action" | phải | liên kết "Create draft →" tới `/wiki?new=1&title=<samples[0] hoặc normalized, mã hóa URL>`; chữ rất nhỏ, rê chuột gạch chân |

  Mỗi hàng có viền trên, rê chuột tối rất nhẹ.

### 4.11. Tab Chẩn đoán (`diagnostics`)

- Đang tải toàn trang hoặc chưa có dữ liệu lint → skeleton.
- **Hàng 3 thẻ tóm tắt** (1 cột; md: 3 cột; khe 16px), mỗi thẻ cùng kiểu thẻ KPI nhưng đệm khoảng 16px, biểu tượng khoảng 16px:

| Thẻ | Biểu tượng (màu) | Nhãn | Giá trị | Mô tả (chữ rất nhỏ màu phụ) | Tô màu khi > 0 |
|---|---|---|---|---|---|
| 1 | `link_off` (hổ phách) | "Dead Links" | số `dead_links` | "Broken internal links pointing to non-existent wiki pages." | viền và nền hổ phách nhạt |
| 2 | `article` (hổ phách) | "Orphan Pages" | số `orphans` | "Wiki pages that have no incoming links from other pages." | viền và nền cam đất nhạt |
| 3 | `warning` (đỏ) | "Contradictions" | số `contradictions` | "Wiki pages containing logical conflicts identified by AI Verifier." | viền và nền đỏ nhạt |

- **Tổng = 0** → khối chúc mừng: viền xanh lục nhạt, nền xanh lục rất nhạt, đệm lớn, căn giữa, chữ xanh lục đậm: biểu tượng `check_circle` lớn (khoảng 36px) xanh lục; dòng đậm "Knowledge Base is perfectly healthy!"; dòng phụ chữ rất nhỏ, rộng tối đa khoảng 448px: "No dead links, orphan pages, or logical contradictions were detected in your flat wiki workspace."
- **Tổng > 0** → các bảng chi tiết, xếp dọc cách 24px, chỉ hiện bảng có dữ liệu. Mỗi bảng: thẻ viền bo góc tràn ẩn; thanh đầu (đệm 16/12px, viền dưới, nền nhạt theo màu nhóm) gồm biểu tượng 18px, tiêu đề chữ nhỏ đậm vừa màu nhóm đậm, và huy hiệu viên thuốc bên phải (chữ đơn cách, rất nhỏ, đậm, nền nhạt màu nhóm). Đầu bảng như tab Khoảng trống; hàng có viền dưới, đệm dọc khoảng 12px, rê chuột tối rất nhẹ.

**Bảng Dead Links** (màu nhóm: hổ phách; biểu tượng `link_off`; huy hiệu "{n} errors"):

| Cột | Nội dung |
|---|---|
| "Source Page" | liên kết `from_title` tới `/wiki/{from_slug}` (đậm vừa, rê chuột gạch chân); dòng dưới chữ cực nhỏ đơn cách màu phụ "slug: {from_slug}" |
| "Broken Target Link" | chữ đơn cách rất nhỏ đậm màu đỏ cảnh báo, hiển thị `to_slug` bọc trong cặp ngoặc vuông kép kiểu wikilink |
| "Action" (căn phải) | liên kết biểu tượng `edit` + "Edit Source →" tới `/wiki/{from_slug}?edit=1` |

**Bảng Orphan Pages** (màu nhóm: cam đất; biểu tượng `article`; huy hiệu "{n} pages"):

| Cột | Nội dung |
|---|---|
| "Page Title" | liên kết `title` tới `/wiki/{slug}` + dòng "slug: {slug}" |
| "Status" | huy hiệu trạng thái wiki (`WikiStatusBadge` với `status`; định nghĩa ở phần giao diện wiki) |
| "Action" | biểu tượng `visibility` + "View Page →" tới `/wiki/{slug}` |

**Bảng Knowledge Contradictions** (màu nhóm: đỏ; biểu tượng `warning`; tiêu đề "Knowledge Contradictions"; huy hiệu "{n} issues"):

| Cột | Nội dung |
|---|---|
| "Conflicted Page" | liên kết `title` tới `/wiki/{slug}` + dòng "slug: {slug}" |
| "Error Details" | câu chữ rất nhỏ màu đỏ nhạt: "Detected a [!contradiction] alert badge pinned on this page by the AI Verifier." trong đó cụm `[!contradiction]` hiển thị như mã nội dòng (nền đỏ rất nhạt, viền đỏ nhạt, chữ đơn cách cực nhỏ) |
| "Action" | biểu tượng `rule` + "Review Contradiction →" tới `/wiki/{slug}` |

### 4.12. Màn chuyển tiếp (khi chưa có `user`)

Khung cao tối thiểu khoảng 60% chiều cao màn hình, căn giữa. Một thẻ bo góc rất lớn, viền trắng rất mờ, nền tối trong suốt có làm mờ hậu cảnh và đổ bóng lớn, phía sau có quầng sáng chuyển màu từ màu nhấn chính sang tím (mờ, nhòe). Trong thẻ: vòng quay tròn khoảng 48px (vòng nền mờ, hai cạnh trên/phải màu nhấn chính, quay khoảng 0,8 giây/vòng); tiêu đề "Resolving Workspace Scope" (chữ lg, đậm bán phần, nhấp nháy mờ); dòng phụ chữ rất nhỏ màu phụ, rộng tối đa khoảng 280px: "Loading data and resolving workspace scope...".

### 4.13. Biểu đồ dùng chung — `components/stats/charts.tsx`

Không dùng thư viện biểu đồ; vẽ bằng SVG thuần. Xuất hai component:

**`LineChart`** — props: `data` (mảng `{ date: string, value: number|null }`, bắt buộc), `height` (số, mặc định 120), `color` (chuỗi màu, mặc định xanh dương), `label` (chuỗi, tùy chọn).
- `data` rỗng → khung cao 120px, căn giữa chữ rất nhỏ màu phụ mờ "No data".
- Có `label` → dòng chữ rất nhỏ màu phụ phía trên biểu đồ.
- Hệ tọa độ logic rộng 600 × `height`, co giãn theo chiều rộng khung (giữ tỉ lệ). Lề trong: trái 28, phải 8, trên 8, dưới 18.
- Trục Y: giá trị null coi là 0; max = lớn nhất giữa 1 và các giá trị; min = nhỏ nhất giữa 0 và các giá trị. Các điểm cách đều theo chiều ngang.
- Vẽ: 3 đường lưới ngang mảnh (ở 25%, 50%, 75% chiều cao vùng vẽ, màu chữ với độ mờ rất cao); vùng tô dưới đường (màu đường, độ đậm khoảng 8%); đường gấp khúc nét 1,5; chấm tròn bán kính 2 tại mỗi điểm, rê chuột hiện tooltip gốc "{date}: {value}".
- Nhãn: góc trên trái là max (làm tròn), góc dưới trái là min; dưới trục X chỉ ghi ngày đầu (căn trái) và ngày cuối (căn phải). Cỡ chữ nhãn khoảng 9, màu chữ độ mờ khoảng 45%.

**`BarList`** — props: `items` (mảng đối tượng tự do, bắt buộc), `valueKey` (mặc định `"count"`), `labelKey` (mặc định `"name"`), `emptyText` (mặc định "No data"), `color` (mặc định xanh dương), `maxItems` (mặc định 10).
- Rỗng → chữ rất nhỏ màu phụ mờ là `emptyText`.
- Lấy tối đa `maxItems` phần tử đầu; tỉ lệ mỗi thanh = giá trị / max (max tối thiểu 1).
- Mỗi hàng là lưới hai cột (thanh co giãn | số): thanh cao khoảng 24px, bo góc nhẹ, nền xám rất nhạt; phần tô từ trái theo tỉ lệ phần trăm, màu `color` độ đậm khoảng 18%, có chuyển động khi đổi; nhãn (thiếu → "—") chữ khoảng 12px đè lên thanh, cắt dấu ba chấm. Cột số bên phải chữ khoảng 12px, chữ số đều độ rộng, màu phụ, căn phải, rộng tối thiểu 3 ký tự. Các hàng cách nhau khoảng 6px.

### 4.14. Thành phần `components/dashboard/*` và `StatCard` (có trong nguồn, hiện không được trang nào dùng)

Các thành phần dưới đây tồn tại trong nguồn nhưng không được import ở đâu. Có khóa i18n `dash.*` tương ứng trong c2. Có thể dựng lại để tương đương đầy đủ (tùy chọn).

**`McpConnectionCard`** (không props): thẻ nền "surface-variant" (nền biến thể bề mặt), viền, bo góc lớn, đệm 24px. Tiêu đề chữ xl `dash.mcpConnection`; mô tả chữ rất nhỏ màu phụ `dash.mcpDesc`. Khối mã nền nâu sẫm, chữ kem, đơn cách, cuộn ngang, hiển thị một đoạn cấu hình JSON gồm đối tượng `mcpServers` → `arkon` với `url` = origin hiện tại của trình duyệt nối `/mcp` (phía server: `https://your-server/mcp`) và `headers.Authorization` = `Bearer <your-mcp-token>`. Nút ghost nhỏ, chữ màu nhấn chính: biểu tượng `content_copy` + `dash.copyConfig`; bấm → chép đoạn cấu hình vào clipboard, trong 2 giây đổi thành biểu tượng `check` + `dash.copied`.

**`RecentSourcesCard`** (không props): gọi `GET /api/sources?limit=5` một lần khi gắn (mảng `{ id, title, status, knowledge_type_name?, knowledge_type_color?, created_at }`; lỗi → coi như rỗng). Thẻ nền thẻ, viền, bóng nhẹ thương hiệu, đệm 24px; tiêu đề chữ xl `dash.recentDocs` có viền dưới. Đang tải: biểu tượng `progress_activity` quay ở giữa. Rỗng: `EmptyState` với biểu tượng `description`, tiêu đề `dash.noRecentDocs`, mô tả `dash.uploadFirstDoc`. Có dữ liệu: danh sách dọc, mỗi hàng (rê chuột nền phụ nhạt) gồm trái biểu tượng `description` + tiêu đề (cắt ba chấm) + ngày tạo (định dạng ngày theo locale); phải: huy hiệu viền theo màu `knowledge_type_color` hiển thị `knowledge_type_name` (nếu có) và viên trạng thái: `ready` xanh lá nhạt, `processing` vàng nhạt, `error` đỏ cảnh báo nhạt, khác/`pending` nền phụ chữ phụ; nội dung là giá trị `status` nguyên văn.

**`SystemHealthCard`** (không props): gọi `GET /api/health` một lần (phản hồi `{ api, database, worker }`, mỗi trường là chuỗi; đúng `"healthy"` thì là khỏe, khác là lỗi; gọi lỗi → cả ba lỗi). Tiêu đề `dash.healthTitle`; bên phải trạng thái tổng: cả ba khỏe → biểu tượng `check_circle` + `dash.healthOnline` màu nhấn chính; ngược lại `warning` + `dash.healthDegraded` màu đỏ cảnh báo. Lưới 3 ô: `dash.healthApi`, `dash.healthDb`, `dash.healthWorker`; mỗi ô có biểu tượng và màu theo trạng thái: khỏe = `check_circle` (đặc) xanh lá trên nền xanh lá nhạt; lỗi = `error` đỏ trên nền đỏ nhạt; đang tải = `progress_activity` quay, màu phụ trên nền phụ.

**`StatCard`** (`components/shared/stat-card.tsx`) — props: `label` (string, bắt buộc), `value` (string | number, bắt buộc), `icon` (tên Material Symbol, bắt buộc), `subtitle` (string, tùy chọn). Thẻ nền thẻ, viền, bóng nhẹ, bo góc lớn, đệm khoảng 20px. Hàng trên: nhãn chữ nhỏ đậm vừa màu phụ bên trái; bên phải ô biểu tượng (nền "container" thương hiệu, chữ tương phản trên màu chính, bo góc, đệm nhỏ). Dưới: giá trị chữ 3xl font tiêu đề; phụ đề chữ rất nhỏ màu phụ.

---

## 5. Màn `/profile` — Hồ sơ cá nhân

### 5.1. Mục đích và quyền

- Route `/profile` trong cổng. Mọi người dùng đã đăng nhập; không kiểm tra quyền. Chưa có `user` → không hiển thị gì.
- Lối vào: mục `user.profile` trong menu tài khoản ở thanh bên/đầu trang (07a).

### 5.2. Bố cục

1. **PageHeader**: tiêu đề "Profile", mô tả "Manage your account settings."; hành động: nút **destructive** (đỏ) biểu tượng `logout` + "Logout" → gọi `useAuth().logout()` (phiên SSO sẽ điều hướng sang `/api/auth/sso/logout`; phiên mật khẩu xóa `user`, guard cổng chuyển về `/login`).
2. **Lưới** 1 cột; từ cỡ lg: 2 cột; khe khoảng 24px:
   - Ô trái: thẻ **Thông tin tài khoản**.
   - Ô phải: thẻ **Đổi mật khẩu**.
   - Hàng dưới, trải 2 cột (lg): thẻ **MCP Token** (`McpTokenCard`).

Các thẻ thông tin và đổi mật khẩu: nền thẻ, viền, bóng nhẹ thương hiệu, bo góc lớn, đệm 24px; tiêu đề chữ lg đậm bán phần, cách nội dung khoảng 16px.

### 5.3. Thẻ Thông tin tài khoản

- Tiêu đề "Account Information".
- Hàng đầu: avatar tròn khoảng 56px, nền màu nhấn chính khoảng 10%, chữ màu nhấn chính, đậm, cỡ xl, hiển thị chữ cái đầu của `name` viết hoa; bên phải: `name` (chữ lg đậm bán phần) và `email` (chữ nhỏ màu phụ).
- Dưới, có viền trên, lưới 2 cột:
  - "Role": nhãn chữ rất nhỏ màu phụ; huy hiệu viền hiển thị `role` viết hoa chữ đầu (`admin`/`employee`).
  - "Department" (hoặc "Departments" nếu có nhiều hơn 1): danh sách `department_names` nối bằng ", " (chữ nhỏ đậm vừa); rỗng → "—".

### 5.4. Thẻ Đổi mật khẩu

Tiêu đề "Change Password". Form dọc, khe 16px:

| Trường | Nhãn | Kiểu | Ràng buộc |
|---|---|---|---|
| Mật khẩu hiện tại | "Current Password" (chữ rất nhỏ) | password | bắt buộc |
| Mật khẩu mới | "New Password" | password | bắt buộc, tối thiểu 6 ký tự (kiểm tra HTML gốc), placeholder "Min 6 characters" |

- Khối lỗi (nếu có): chữ đỏ cảnh báo trên nền đỏ nhạt; nội dung = message API, dự phòng "Failed".
- Khối thành công (nếu có): chữ xanh lá trên nền xanh lá nhạt: "Password changed successfully".
- Nút gửi (màu chính, không giãn hết chiều ngang, căn trái): "Update Password"; đang gửi → vô hiệu, nhãn "Saving...".
- Gửi: xóa lỗi/thông báo cũ → `POST /api/auth/change-password` thân `{ current_password, new_password }` → thành công: hiện thông báo thành công, xóa trắng hai ô.
- Lỗi backend có thể gặp: 400 "No password set. Contact admin." (tài khoản SSO không có mật khẩu cục bộ); 401 "Current password is incorrect"; 400 "New password must be at least 6 characters". Phản hồi thành công: `{ message: "Password changed successfully" }`.

### 5.5. Thẻ MCP Token — `components/profile/mcp-token-card.tsx`

Component `McpTokenCard` (không props). Thẻ nền biến thể bề mặt, viền, bo góc lớn, đệm 24px.

- Đầu thẻ: biểu tượng `vpn_key` màu nhấn chính; tiêu đề chữ lg đậm bán phần `profile.mcpTokenTitle`; mô tả chữ rất nhỏ màu phụ `profile.mcpTokenDesc`.
- Khi gắn: `GET /api/my/mcp-token/status` → `{ has_token: boolean }`; lỗi thì bỏ qua (coi như chưa có).

Ba trạng thái:

| Trạng thái | Điều kiện | Hiển thị |
|---|---|---|
| Vừa tạo | có giá trị token trong bộ nhớ (chỉ ngay sau khi tạo) | Khối mã nền nâu sẫm, chữ kem, đơn cách, tự ngắt dòng mọi chỗ, hiện toàn bộ token. Dưới: nút viền nhỏ `content_copy` + `profile.copyToken` (bấm chép vào clipboard; trong 2 giây đổi thành `check` + `dash.copied`); nút ghost nhỏ chữ đỏ `vpn_key_off` + `profile.revokeToken`. |
| Đã có | `has_token` = true nhưng không có giá trị | Hộp thông báo xanh lá (chữ xanh lá, nền xanh lá nhạt, viền xanh lá nhạt) với biểu tượng `check_circle` và văn bản `profile.mcpTokenActive`. Dưới: nút viền nhỏ `refresh` + `profile.regenerateToken` (đang chạy: `common.loading`, vô hiệu); nút ghost đỏ `vpn_key_off` + `profile.revokeToken`. |
| Chưa có | ngược lại | Một nút màu chính `profile.generateToken` (đang chạy: `common.loading`, vô hiệu). |

Hành động:
- **Tạo / Tạo lại**: `POST /api/my/mcp-token` (không thân) → phản hồi có `token` (cùng `employee_name`, `instructions` không dùng). Mỗi lần gọi phát hành token mới và vô hiệu token cũ. Lưu token vào bộ nhớ (không lưu storage), `has_token` = true. Lỗi → hộp `alert` gốc của trình duyệt với message lỗi, dự phòng `common.error`.
- **Thu hồi**: hộp `confirm` gốc với văn bản `profile.revokeConfirm`; đồng ý → `DELETE /api/my/mcp-token` (phản hồi `{ revoked: true }`) → xóa token khỏi bộ nhớ, `has_token` = false. Lỗi → `alert` như trên.
- Tải lại trang sau khi tạo: token không còn hiển thị (chỉ trạng thái "Đã có").

---

## 6. Màn `/audit` — Nhật ký kiểm toán

### 6.1. Mục đích và quyền

- Route `/audit` trong cổng. Mục điều hướng `nav.audit`, biểu tượng `policy`, thuộc nhóm `nav.system`; chỉ hiện ở thanh bên khi `hasPermission("org:audit:read")` (admin luôn thấy). Bản thân trang **không** tự kiểm tra quyền; truy cập trực tiếp không đủ quyền thì API trả lỗi và hiện ở khối lỗi.
- Backend `GET /api/audit/log` yêu cầu quyền `audit.read`.

### 6.2. API

`GET /api/audit/log` với tham số:

| Tham số | Kiểu | Mặc định | Ghi chú |
|---|---|---|---|
| `page` | int ≥ 1 | 1 | |
| `page_size` | int 1..200 | 50 | Xem ghi chú bên dưới. |
| `principal_id`, `action`, `decision`, `resource_type` | string | — | Bộ lọc backend hỗ trợ; giao diện hiện **không** dùng. |

Phản hồi: `items` (mảng mục), `total` (int), `page` (int), `page_size` (int). Sắp theo `timestamp` giảm dần. Mỗi mục: `id`, `timestamp` (ISO), `principal_id`, `principal_type`, `principal_name?`, `principal_email?`, `action`, `resource_type`, `resource_id`, `decision`, `reason?`, `seq`, `trace_id`, `event_hash`. Giao diện dùng: `id`, `timestamp`, `principal_id`, `principal_name`, `principal_email`, `action`, `resource_type`, `resource_id`, `decision`, `reason`.

> Ghi chú khác biệt nguồn: bản gốc gửi `size=20` và đọc trường `pages`, trong khi backend nhận `page_size` và không trả `pages` — hệ quả là mỗi trang 50 mục và thanh phân trang không bao giờ hiện. Bản dựng lại nên gửi `page_size=20` và tính tổng số trang = làm tròn lên (`total` / `page_size`), tối thiểu 1; trang hiện tại lấy từ `page` trong phản hồi.

### 6.3. Bố cục và hành vi

1. **PageHeader**: tiêu đề "Audit Log" (khóa tương đương có sẵn: `audit.title`), mô tả "Review access control decisions and policy evaluations across the system." (khóa tương đương: `audit.description`; nên dùng khóa). Hành động: nút viền biểu tượng `refresh` (quay khi đang tải) + "Refresh" (có thể dùng `stats.refresh`); vô hiệu khi đang tải; bấm → tải trang 1.
2. **Khối lỗi** (nếu có): như ở 4.3, biểu tượng `error`, nội dung message hoặc "Failed to load audit logs"; cách nội dung dưới khoảng 24px.
3. **Cột nội dung** (khe 16px): bảng `AuditTable`, rồi thanh phân trang (chỉ khi tổng số trang > 1).

Khi gắn: tải trang 1. Không polling. Trong lúc tải, bảng chuyển sang trạng thái đang tải.

**Thanh phân trang**: thẻ nền thẻ, viền, bo góc lớn, đệm 16/12px; trái chữ nhỏ màu phụ "Page {page} of {totalPages}"; phải hai nút viền nhỏ "Previous" (vô hiệu khi trang ≤ 1 hoặc đang tải; bấm tải trang trước) và "Next" (vô hiệu khi trang ≥ tổng hoặc đang tải; bấm tải trang sau).

### 6.4. `AuditTable` — `components/audit/audit-table.tsx`

Xuất component `AuditTable` với props `logs` (mảng `AuditLogEntry`) và `loading` (boolean), và kiểu `AuditLogEntry` gồm: `id`, `timestamp`, `action`, `principal_id`, `principal_name?`, `principal_email?`, `resource_type`, `resource_id?`, `decision`, `reason?` (đều string).

Vỏ ngoài mọi trạng thái: thẻ nền thẻ, viền, bóng nhẹ thương hiệu, bo góc lớn.

| Trạng thái | Hiển thị |
|---|---|
| Đang tải | Biểu tượng `progress_activity` khoảng 30px màu phụ quay, căn giữa, đệm dọc lớn (khoảng 64px). |
| Rỗng | `EmptyState`: biểu tượng `policy`, tiêu đề `audit.noLogs`, mô tả `audit.noLogsDesc`. |
| Có dữ liệu | Bảng (thành phần `Table` nền tảng), tràn ẩn. Đầu cột chữ rất nhỏ in hoa giãn chữ; hàng đầu không đổi nền khi rê; hàng dữ liệu rê chuột nền phụ nhạt. |

Các cột:

| Cột (nhãn) | Nội dung |
|---|---|
| `audit.colTimestamp` | `timestamp` định dạng ngày giờ theo locale trình duyệt, chữ rất nhỏ màu phụ, không xuống dòng. |
| `audit.colPrincipal` | Hai dòng: `principal_name` (chữ nhỏ đậm vừa; thiếu → "System/Unknown"); dưới chữ rất nhỏ màu phụ: `principal_email`, thiếu thì 8 ký tự đầu của `principal_id` nối "...". |
| `audit.colAction` | Huy hiệu viền chữ đơn cách rất nhỏ, độ đậm thường, hiển thị `action` nguyên văn. Màu theo `action` (không phân biệt hoa thường): `create` → xanh lá (viền, chữ, nền nhạt); `delete` → đỏ; khác → xanh dương. |
| `audit.colResource` | Hai dòng: `resource_type` (chữ nhỏ, viết hoa chữ đầu); nếu có `resource_id`: chữ rất nhỏ đơn cách màu phụ, dài hơn 20 ký tự thì rút còn 8 ký tự đầu + "...". |
| `audit.colDecision` | Cột dọc căn trái: huy hiệu viền chữ rất nhỏ hiển thị `decision` viết HOA toàn bộ; `allow` (không phân biệt hoa thường) → xanh lá, khác → đỏ. Nếu có `reason`: dòng chữ rất nhỏ màu phụ, rộng tối đa khoảng 200px, cắt ba chấm, rê chuột hiện đầy đủ qua tooltip gốc. |

---

## 7. Tổng hợp khóa i18n dùng trong tài liệu này

| Nhóm | Khóa |
|---|---|
| Điều hướng | `nav.dashboard`, `nav.audit`, `nav.system`, `nav.wiki`, `user.profile` |
| Chung | `common.loading`, `common.error` |
| Thống kê | `stats.title`, `stats.description`, `stats.refresh`, `stats.rollup`, `stats.rolling` (chưa có trong c2), `stats.from`, `stats.to`, `stats.tabOverview`, `stats.tabContent`, `stats.tabContribution`, `stats.tabUsage`, `stats.tabGaps`, `stats.tabLinter`, `stats.kpiTotalPages`, `stats.kpiStalePages`, `stats.kpiOrphanPages`, `stats.kpiPagesUpdatedToday`, `stats.kpiDraftsPending`, `stats.kpiAvgTimeToReview`, `stats.kpiPlansAwaitingReview`, `stats.kpiDeniedAccess`, `stats.kpiMcpActiveUsers`, `stats.kpiMcpWau`, `stats.kpiMcpQueries`, `stats.kpiZeroResultQueries`, `stats.topGapTitle`, `stats.noGapNotice`, `stats.topContributorTitle`, `stats.noContributorNotice` |
| Dashboard (thành phần chưa dùng) | `dash.mcpConnection`, `dash.mcpDesc`, `dash.copyConfig`, `dash.copied`, `dash.recentDocs`, `dash.noRecentDocs`, `dash.uploadFirstDoc`, `dash.healthTitle`, `dash.healthOnline`, `dash.healthDegraded`, `dash.healthApi`, `dash.healthDb`, `dash.healthWorker` |
| Hồ sơ | `profile.mcpTokenTitle`, `profile.mcpTokenDesc`, `profile.mcpTokenActive`, `profile.generateToken`, `profile.regenerateToken`, `profile.copyToken`, `profile.revokeToken`, `profile.revokeConfirm` |
| Kiểm toán | `audit.title`, `audit.description`, `audit.colTimestamp`, `audit.colPrincipal`, `audit.colAction`, `audit.colResource`, `audit.colDecision`, `audit.noLogs`, `audit.noLogsDesc` |

Nhãn viết cứng trong nguồn (màn đăng nhập bằng tiếng Việt; phần lớn nhãn trong các tab Nội dung/Đóng góp/Sử dụng/Khoảng trống/Chẩn đoán, trang Profile và Audit bằng tiếng Anh) được trích nguyên văn ở các mục trên. Bản dựng lại có thể giữ nguyên hoặc chuyển sang khóa i18n mới, miễn hiển thị tương đương.
