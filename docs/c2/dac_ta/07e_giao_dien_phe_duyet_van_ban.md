# 07e. Giao diện phê duyệt bản thảo wiki và văn bản pháp luật

Tài liệu này thuộc bộ đặc tả giao diện 07. Mục lục chung ở `07_giao_dien.md`, nền tảng giao diện (layout portal, theme, i18n, `api`, `EmptyState`, `Button`, cách hiển thị icon Material Symbols Outlined bằng tên ligature) ở `07a_giao_dien_nen_tang.md`. Các thành phần wiki dùng chung (`WikiDraftDiff`, `WikiAiCheckPanel`, `WikiContent`, `WikiGraph`, `FormattedInlineText`, `FacetGroup`/`countFacet`) được đặc tả chi tiết ở `07d`; ở đây chỉ ghi cách các màn dưới đây dùng chúng. Phạm vi gồm ba màn: bàn duyệt bản thảo `/wiki/review`, danh sách văn bản `/wiki/law` (đã có code trong c2, chỉ ghi phụ thuộc và API) và chi tiết văn bản `/wiki/law/[key]` (chưa có trong c2, đặc tả đầy đủ).

Quy ước: "màu vai trò" nghĩa là dùng token theme (primary, muted, destructive, card, border...) hoặc một sắc màu ngữ nghĩa (xanh lục = tốt, hổ phách = cảnh báo, đỏ hồng = lỗi, xanh dương = đang chạy). Mọi màn đều là client component trong nhóm route `(portal)`, nằm trong khung portal của 07a.

---

## 1. Màn bàn duyệt bản thảo — `/wiki/review`

### 1.1 Mục đích

Bàn điều khiển ba cột cho người duyệt xử lý nhanh hàng đợi **nhánh đóng góp** (branch). Mỗi nhánh gom một hoặc nhiều bản thảo (draft) của các trang wiki. Người duyệt xem diff từng tập tin, xem kết quả AI kiểm tra sơ bộ, rồi Hợp nhất (approve & merge), Yêu cầu chỉnh sửa hoặc Từ chối. Tác giả dùng cùng màn ở chế độ "Của tôi" để theo dõi và rút lại nhánh của mình.

### 1.2 Quyền

- Trang không kiểm tra chuỗi quyền nào ở phía client; không có mục sidebar riêng. Người dùng tới đây qua liên kết (ví dụ trang rebase nhánh dẫn tới `/wiki/review?mine=true` và `/wiki/review?mine=true&draft=<branchId>`).
- Sidebar (07a) coi mọi đường dẫn `/wiki/...` là đang ở mục `nav.wiki` **trừ** `/wiki/review` (mục "Kho tri thức" không được tô sáng khi đang ở màn duyệt).
- Phân quyền thật do backend quyết định; client chỉ hiển thị thông báo lỗi trả về (xem 1.10).
- "Bản thảo của tôi" xác định bằng `author_id` của bản thảo đang chọn bằng `id` của người dùng hiện tại (lấy từ `useAuth()` trong `@/lib/auth`). Khi đúng, khu vực thao tác không hiện nút duyệt mà hiện nút Rút lại.

### 1.3 Tham số URL

Mọi trạng thái điều hướng nằm trên query string. Cập nhật bằng `router.replace` (không thêm lịch sử, không cuộn trang) về `/wiki/review?...`; khóa có giá trị rỗng hoặc null bị xóa khỏi URL; nếu không còn khóa nào thì URL là `/wiki/review`.

| Tham số | Giá trị | Mặc định | Ý nghĩa |
|---|---|---|---|
| `status` | `pending`, `needs_revision`, `approved`, `rejected` | `pending` | Bộ lọc trạng thái hàng đợi |
| `mine` | `true` hoặc vắng | vắng (chế độ "Cần duyệt") | `true` = chỉ nhánh tôi tạo |
| `draft` | id nhánh (uuid) | tự chọn nhánh đầu | Nhánh đang chọn (tên tham số là `draft` nhưng chứa id **nhánh**) |
| `scope` | `global` hoặc `<scope_type>:<scope_id>` | rỗng = mọi phạm vi | Lọc phạm vi phía client |

Đổi `status`, `mine` hoặc `scope` luôn đồng thời xóa `draft`.

### 1.4 Ánh xạ trạng thái

Bộ lọc giao diện ánh xạ sang trạng thái nhánh gửi lên API:

| Giá trị `status` trên URL | Nhãn trong ô chọn (nguồn) | Khóa i18n tương ứng trong c2 | Trạng thái nhánh gửi API |
|---|---|---|---|
| `pending` | "Pending" | `review.statusPending` (Chờ duyệt) | `pending_merge` |
| `needs_revision` | "Needs revision" | `review.statusNeedsRevision` (Cần chỉnh sửa) | `draft` |
| `approved` | "Approved" | `review.statusApproved` (Đã duyệt) | `merged` |
| `rejected` | "Rejected" | `review.statusRejected` (Đã từ chối) | `closed` |

Giá trị không nhận diện được thì dùng `pending_merge`.

Nguồn hard-code nhãn tiếng Anh; bản c2 nên dùng khóa i18n `review.*` (đã có trong `frontend/src/lib/i18n.tsx`, cả `vi` và `en`). Các nhãn tiếng Anh khác không có khóa i18n được liệt kê nguyên văn trong spec này; người làm có thể giữ nguyên hoặc dịch sang tiếng Việt, nhưng hành vi phải giữ nguyên.

Trạng thái **bản thảo** (`DraftResponse.status`) dùng trong khu vực thao tác: `pending`, `needs_revision`, và các giá trị khác (hiển thị nguyên chuỗi).

### 1.5 API

| Thời điểm | Method + path | Query/Body | Trường dùng trong response |
|---|---|---|---|
| Tải hàng đợi (khi đổi `status` hoặc `mine`, và khi bấm Làm mới) | `GET /api/wiki/branches` | `status=<trạng thái nhánh>`; thêm `mine=true` nếu chế độ "Của tôi" | Mảng nhánh: `id`, `name`, `description`, `scope_type`, `scope_id`, `author_name`, `created_at`, `has_conflict`, `draft_count` (backend sắp theo `updated_at` giảm dần) |
| Khi `draft` (id nhánh) đổi | `GET /api/wiki/branches/{id}` | — | Nhánh chi tiết: `id`, `name`, `description`, `has_conflict`, `drafts` (mảng `DraftResponse`) |
| Khi bản thảo đang xem đổi, nếu không phải bản thảo tạo mới và có `page_slug` | `GET /api/wiki/pages/{page_slug}` | `scope_type=<page_scope_type>` và `scope_id=<page_scope_id>` khi có giá trị | `content_md` (nội dung trang hiện tại để so diff) |
| Thăm dò AI (mục 1.9) | `GET /api/wiki/drafts/{draftId}` | — | `DraftResponse` mới, nhất là `ai_check_status` |
| Hợp nhất | `POST /api/wiki/branches/{id}/merge` | JSON `{ "reviewer_note": <ghi chú hoặc bỏ trường nếu rỗng> }` | không dùng |
| Từ chối / Yêu cầu chỉnh sửa / Rút lại | `POST /api/wiki/branches/{id}/close` | không có body (ghi chú **không** được gửi) | không dùng |

Trường `DraftResponse` (kiểu trong `@/types/wiki`) được màn sử dụng: `id`, `page_id`, `page_slug`, `page_title`, `page_scope_type`, `page_scope_id`, `has_conflict`, `draft_kind` (`create` hoặc `edit`), `suggested_metadata` (`slug`, `page_type`, `scope_type`, `knowledge_type_slugs`), `author_id`, `author_name`, `author_stats` (`total_reviewed`, `approved`, `rejected`, `needs_revision`, `accuracy` 0..1), `suggested_reviewers` (mảng `{id, name, email, score}`), `content_md`, `note`, `status`, `revision_round` (số nguyên, mặc định 0), `last_returned_note`, `ai_check_status`, `ai_check_results`, `created_at`.

Lỗi khi tải hàng đợi: coi như danh sách rỗng (không hiện thông báo). Lỗi khi tải chi tiết nhánh: bỏ chọn nhánh, danh sách tập tin rỗng. Lỗi khi tải trang hiện tại: nội dung trang coi là chuỗi rỗng.

### 1.6 Đồng bộ lựa chọn

- Sau khi tải hàng đợi: nếu danh sách khác rỗng và `draft` trên URL trống hoặc không thuộc danh sách thì đặt `draft` = id nhánh đầu tiên. Nếu danh sách rỗng mà URL còn `draft` thì xóa `draft`.
- Sau khi áp bộ lọc phạm vi: nếu danh sách đã lọc khác rỗng và nhánh đang chọn không thuộc danh sách đã lọc thì chọn nhánh đầu tiên của danh sách đã lọc.
- Khi tải xong chi tiết nhánh, tập tin (bản thảo) đang xem là phần tử đầu tiên của `drafts`.
- Mỗi khi bản thảo đang xem đổi (theo `id` hoặc `draft_kind`): đóng form ghi chú, xóa ghi chú và lỗi, đặt lại "So sánh với" về trang hiện tại, chọn tab giữa = `proposed` nếu `draft_kind` là `create`, ngược lại `diff`.

### 1.7 Bố cục

Lưới ba cột chiếm toàn bộ vùng nội dung portal (bù trừ padding của khung để tràn sát mép), cao hết phần còn lại, có viền trên.

| Cột | Rộng | Nền | Nội dung |
|---|---|---|---|
| Trái — hàng đợi | 320px cố định | card mờ nhẹ, viền phải | Thanh công cụ + danh sách nhánh (cuộn riêng) |
| Giữa — nội dung | phần còn lại | nền trang | Header dính trên + vùng nội dung cuộn riêng |
| Phải — thông tin & thao tác | 340px cố định | card mờ nhẹ, viền trái | Các khối thông tin + khu vực thao tác (cuộn riêng) |

#### 1.7.1 Cột trái — hàng đợi

Phần trên (có viền dưới, các phần tử cách nhau đều):

1. Dòng tiêu đề: chữ đậm cỡ nhỏ "Review queue" (khóa `review.title`); bên phải một nút nhỏ hiển thị phím `?` dạng kbd, tooltip "Keyboard shortcuts", bấm để bật/tắt hộp trợ giúp phím tắt.
2. Công tắc phân đoạn hai nút, rộng hết cột, có viền: "To review" (`review.toReview`, icon `fact_check`) và "Mine" (`review.mine`, icon `edit_note`). Nút đang chọn nền primary, chữ primary-foreground; nút còn lại chữ muted, hover nền muted. Chọn "Mine" đặt `mine=true`; chọn "To review" xóa `mine`; cả hai xóa `draft`.
3. Ô chọn trạng thái (select gốc, cao 32px, rộng hết cột, chữ cỡ xs) với 4 lựa chọn theo bảng 1.4.
4. Ô chọn phạm vi — chỉ hiện khi có **hơn một** lựa chọn phạm vi. Tooltip "Filter by scope". Lựa chọn đầu "All scopes (N)" với N = tổng số nhánh đã tải (giá trị rỗng). Các lựa chọn tiếp theo lấy từ danh sách nhánh đã tải, mỗi khóa phạm vi duy nhất một lần: khóa `global` (khi `scope_type` là `global` hoặc trống) nhãn "Global"; còn lại khóa `<scope_type>:<scope_id>` nhãn "Scope: <scope_type>". Thứ tự: `global` đứng đầu, còn lại theo nhãn A→Z.
5. Dòng trạng thái (chữ 11px, muted), trái: "Loading…" khi đang tải; nếu đang lọc phạm vi: "X of Y drafts" (Y = 1 thì "draft"); không lọc: "Y drafts"/"Y draft". Phải: nút icon `refresh`, tooltip "Refresh", bấm để tải lại hàng đợi.

Danh sách (cuộn dọc):

- Đang tải: không hiển thị gì.
- Rỗng sau lọc: `EmptyState` icon `inbox`, tiêu đề "Empty queue" (`review.emptyQueue`), mô tả: nếu đang lọc phạm vi và có nhánh ở phạm vi khác thì "No drafts in this scope. Switch to 'All scopes' to see others."; ngược lại "No drafts in <status> state." (c2 có thể dùng `review.noDraftsInStatus`).
- Có dữ liệu: danh sách phân cách bằng đường kẻ; mỗi mục là một nút rộng hết cột, căn trái:
  - Dòng 1: nếu `has_conflict` là true thì nhãn nhỏ chữ in hoa "conflict" màu destructive trên nền destructive nhạt; sau đó `name` (chữ đậm vừa, cắt bằng dấu ba chấm).
  - Dòng 2 (chữ mono 11px, muted, cắt): "<scope_type> · <draft_count> files changed".
  - Dòng 3 (11px, muted): `author_name` (hoặc "?") · thời gian tương đối của `created_at`.
  - Mục đang chọn: nền primary nhạt, viền trái 2px màu primary; mục khác viền trái trong suốt cùng độ dày; hover nền muted nhạt.
  - Bấm mục: đặt `draft` = id nhánh.

Thời gian tương đối: dưới 60 giây "just now"; dưới 1 giờ "<n>m ago"; dưới 1 ngày "<n>h ago"; dưới 7 ngày "<n>d ago"; còn lại ngày dạng "ngày + tháng viết tắt" theo locale trình duyệt (làm tròn xuống).

#### 1.7.2 Cột giữa — nội dung bản thảo

Khi chưa có bản thảo: căn giữa, chữ nghiêng muted: "Loading…" nếu đang tải hàng đợi, ngược lại "Select a draft from the queue." (`review.selectDraftPrompt`).

Khi có bản thảo:

**Header dính trên** (viền dưới, nền trang):

1. Hàng tiêu đề: trái là nhãn nhỏ chữ in hoa nền hổ phách nhạt "Nhánh đóng góp" rồi tên nhánh (cắt); dưới là mô tả nhánh (chữ xs muted) hoặc "Không có mô tả nhánh." nếu trống. Phải: chỉ số "i / N" dạng số đều (i = vị trí nhánh đang chọn trong danh sách đã lọc, bắt đầu từ 1; N = số nhánh đã lọc).
2. Nếu nhánh `has_conflict`: hộp cảnh báo bo góc nền đỏ hồng nhạt, viền đỏ hồng, icon `warning`, văn bản: phần đậm "Xung đột phát hiện:" tiếp theo "Nhánh này có thay đổi bị xung đột với Wiki chính. Tác giả cần thực hiện rebase nhánh trước khi hợp nhất."
3. Nếu nhánh có ít nhất một bản thảo: nhãn chữ in hoa nhỏ "Tập tin thay đổi (N):" và một hàng nút (xuống dòng khi tràn), mỗi bản thảo một nút: icon `add_box` nếu `draft_kind` là `create`, ngược lại `edit`; nhãn `page_title` (hoặc `page_slug`); nếu bản thảo `has_conflict` thêm chấm tròn nhỏ màu destructive nhấp nháy. Nút đang chọn viền và chữ primary trên nền primary nhạt; còn lại viền thường, hover nền muted. Bấm để đổi tập tin đang xem (trạng thái nội bộ, không ghi URL).
4. Hàng tab: bản thảo `create` chỉ có tab "proposed"; bản thảo khác có ba tab "diff", "proposed", "Current page" (hai tab đầu hiển thị chữ hoa chữ cái đầu: "Diff", "Proposed"). Tab đang chọn nền primary, còn lại chữ muted.
5. Bộ chọn "So sánh với" — chỉ hiện khi tab `diff`, bản thảo không phải `create` và danh sách nhánh có hơn 1 phần tử. Đặt sát phải hàng tab: chữ "Compare with:" và select nhỏ (cao 24px). Lựa chọn đầu "Current page" (giá trị rỗng). Các lựa chọn tiếp theo là các phần tử của danh sách **nhánh** đã tải (không lọc phạm vi) thỏa: id khác bản thảo hiện tại, `draft_kind` khác `create`, và `page_id` bằng `page_id` bản thảo hiện tại; nhãn "Draft by <author_name hoặc ?>" kèm " (r<revision_round+1>)" khi `revision_round` > 0. Lưu ý hành vi nguồn: phần tử danh sách nhánh không mang `page_id`/`content_md`, nên trên thực tế chỉ còn lựa chọn "Current page"; khi chọn một mục không có `content_md` thì diff quay về nội dung trang hiện tại.

**Vùng nội dung** (cuộn, padding ngang rộng):

| Tình huống | Hiển thị |
|---|---|
| Tab `diff`, không phải `create`, đang tải trang hiện tại hoặc chi tiết nhánh | Chữ nghiêng muted "Loading current page…" |
| Tab `diff`, không phải `create` | `WikiDraftDiff` với văn bản cũ = nội dung trang hiện tại (hoặc `content_md` của mục "Compare with" nếu có), văn bản mới = `content_md` của bản thảo, chế độ `unified`, 3 dòng ngữ cảnh |
| Tab `proposed` hoặc bản thảo `create` | `WikiContent` render `content_md`; nếu nội dung chỉ toàn khoảng trắng thì chữ nghiêng "Empty content." |
| Tab `current` | `WikiContent` render nội dung trang hiện tại; nếu rỗng render chuỗi Markdown in nghiêng "(empty page)" |

#### 1.7.3 Cột phải — thông tin và thao tác

Khi chưa có bản thảo: chữ nghiêng xs muted "No draft selected." (`review.noDraftSelected`).

Khi có bản thảo, các khối theo thứ tự, mỗi khối có nhãn nhỏ chữ in hoa muted:

| Khối | Nhãn | Nội dung |
|---|---|---|
| Tác giả | "Author" | `author_name` (hoặc "Unknown"). Nếu `author_stats.total_reviewed` > 0: dòng số đều "<approved>✓ · <accuracy×100 làm tròn>% accuracy", tooltip "<approved> approved · <rejected> rejected" kèm " · <needs_revision> returned" khi > 0. Ngược lại chữ nghiêng "first contribution". |
| Gửi lúc | "Submitted" | Thời gian tương đối của `created_at`; dòng nhỏ "round <revision_round+1>"; nếu có `note` thì trích dẫn nghiêng trong dấu ngoặc kép cong; nếu bản thảo `needs_revision` và có `last_returned_note` thì "Reviewer asked:" (đậm vừa) + nội dung (c2 có khóa `wiki.banner.reviewerAsked`). |
| Trang đề xuất | "Suggested page" | Chỉ với bản thảo `create` có `suggested_metadata`: `slug` dạng mono; dòng "<page_type> · <scope_type>"; nếu có `knowledge_type_slugs` thì "Tags: a, b, c". |
| Người duyệt gợi ý | "Suggested reviewers" | Chỉ khi mảng khác rỗng: mỗi dòng tên (hoặc email, hoặc "?") bên trái, `score` số đều bên phải. |
| AI tiền duyệt | "AI pre-review" | `WikiAiCheckPanel` với `status` = `ai_check_status`, `results` = `ai_check_results`. |
| Thao tác | (không nhãn, có viền trên) | Xem 1.8 |

### 1.8 Khu vực thao tác

Dòng lỗi (chữ xs màu destructive) hiện ở đầu khu vực khi có lỗi. Nội dung khu vực theo thứ tự ưu tiên:

1. **Form ghi chú** (khi đang ở chế độ Từ chối hoặc Yêu cầu chỉnh sửa):
   - Nhãn: "Rejection reason" (từ chối) hoặc "What needs to change?" (yêu cầu chỉnh sửa).
   - Ô nhập nhiều dòng 4 hàng, không cho kéo giãn, placeholder "Tell the contributor why this was rejected…" hoặc "Explain what to fix before resubmission…". Tự focus khi mở form.
   - Bộ đếm "<số ký tự sau khi bỏ khoảng trắng đầu cuối>/20 characters minimum".
   - Nút căn phải: "Cancel" (outline, cỡ nhỏ, kèm kbd "Esc") đóng form; nút xác nhận cỡ nhỏ: biến thể destructive "Confirm reject" với icon `cancel`, hoặc biến thể mặc định "Send back" với icon `edit_note`. Khi đang gửi icon đổi thành `progress_activity` xoay. Nút xác nhận vô hiệu khi đang gửi hoặc ghi chú dưới 20 ký tự.
   - Kiểm tra: ghi chú (đã trim) phải ≥ 20 ký tự, nếu không hiện lỗi "Vui lòng nhập ít nhất 20 ký tự." và không gọi API.
   - Gửi: `POST /api/wiki/branches/{id}/close` (cả hai chế độ đều gọi endpoint này, không gửi ghi chú). Lỗi: hiện thông điệp lỗi từ API, mặc định "Thao tác thất bại".
2. **Bản thảo của tôi**: chữ nghiêng "This is your draft."; nếu bản thảo `pending` hoặc `needs_revision` có nút outline rộng hết cột icon `remove_circle` "Withdraw". Bấm hiện hộp xác nhận của trình duyệt "Bạn có chắc chắn muốn hủy bỏ nhánh đóng góp này không?"; đồng ý thì gọi `POST /api/wiki/branches/{id}/close`. Lỗi mặc định "Hủy nhánh thất bại".
3. **Bản thảo không ở `pending`**: chữ nghiêng "Waiting for the author to resubmit." nếu `needs_revision`, ngược lại "Draft is <status>.".
4. **Bản thảo `pending` của người khác**: ba nút rộng hết cột, nội dung căn hai đầu (icon + nhãn bên trái, kbd phím tắt bên phải):

| Nút | Biến thể | Icon | Phím | Hành động | Vô hiệu khi |
|---|---|---|---|---|---|
| "Approve & Merge" | mặc định (primary) | `check_circle` | A | `POST /api/wiki/branches/{id}/merge` với `reviewer_note` | đang gửi, hoặc nhánh `has_conflict` |
| "Request changes" | outline | `edit_note` | C | Mở form ghi chú chế độ yêu cầu chỉnh sửa | đang gửi |
| "Reject" | outline | `cancel` | R | Mở form ghi chú chế độ từ chối | đang gửi |

Lỗi hợp nhất: hiện thông điệp API, mặc định "Hợp nhất nhánh thất bại". Backend có thể trả 409 với thông điệp xung đột cụ thể (tên trang, slug, phiên bản), 403 "Bạn không có quyền hợp nhất tài liệu trong phạm vi này", 400 "Chỉ có thể hợp nhất nhánh khi đang ở trạng thái 'pending_merge'". Đóng nhánh có thể trả 403 "Bạn không có quyền đóng hoặc hủy nhánh này", 400 "Nhánh đã đóng hoặc đã được hợp nhất", 404 "Không tìm thấy nhánh đóng góp". Tải chi tiết nhánh có thể trả 404 "Không tìm thấy nhánh đóng góp này".

**Sau khi thao tác thành công** (hợp nhất, đóng, rút lại): loại nhánh vừa xử lý khỏi danh sách cục bộ (không tải lại); trong danh sách đã lọc còn lại, chọn phần tử ở cùng vị trí cũ (giới hạn về phần tử cuối); nếu không còn gì thì xóa `draft`. Đóng form, xóa ghi chú và lỗi.

### 1.9 Thăm dò kết quả AI

Khi bản thảo đang xem có `ai_check_status` là `pending`, `running` hoặc `queued`: mỗi 3000 ms gọi `GET /api/wiki/drafts/{draftId}`. Dừng khi trạng thái mới không còn thuộc ba giá trị trên, hoặc khi bản thảo đang xem đổi / rời màn. Lỗi khi thăm dò bị bỏ qua im lặng. Hành vi nguồn: bản ghi mới được lưu vào một trạng thái riêng nhưng giao diện vẫn render bản thảo gốc trong chi tiết nhánh; bản c2 nên dùng bản ghi mới nhất (nếu có) cho `WikiAiCheckPanel` để kết quả cập nhật trực tiếp.

### 1.10 Phím tắt

Lắng nghe phím trên toàn cửa sổ. Bỏ qua khi focus đang ở ô nhập, ô nhiều dòng, select hoặc phần tử contenteditable (riêng phím Esc trong các phần tử này vẫn đóng form ghi chú). Bỏ qua khi có giữ Ctrl, Alt hoặc Meta.

| Phím | Hành động | Điều kiện |
|---|---|---|
| `j` hoặc mũi tên xuống | Chọn nhánh kế tiếp trong danh sách đã lọc (dừng ở cuối) | luôn |
| `k` hoặc mũi tên lên | Chọn nhánh trước (dừng ở đầu) | luôn |
| `a` | Hợp nhất | bản thảo `pending` và chưa mở form ghi chú |
| `r` | Mở form Từ chối, xóa ghi chú, focus ô nhập | bản thảo `pending` |
| `c` | Mở form Yêu cầu chỉnh sửa, focus ô nhập | bản thảo `pending` |
| `Esc` | Đóng form ghi chú | đang mở form |
| `?` | Bật/tắt hộp trợ giúp | luôn |

Lưu ý: phím `a`/`r`/`c` không kiểm tra "bản thảo của tôi" (chỉ có nút bị ẩn); backend chặn bằng quyền.

**Hộp trợ giúp phím tắt**: lớp phủ toàn màn nền đen mờ, bấm ra ngoài để đóng. Hộp giữa màn bo góc lớn, rộng tối đa cỡ "md", có tiêu đề "Keyboard shortcuts" và nút đóng icon `close`. Danh sách hai cột (phím dạng kbd nền muted bên trái, mô tả bên phải): "j / ↓" Next draft; "k / ↑" Previous draft; "a" Approve current draft; "c" Request changes (focus note); "r" Reject (focus note); "Esc" Cancel pending action; "?" Toggle this help. Chú thích nghiêng cuối hộp: "Shortcuts disabled while focus is in a text field."

### 1.11 Thành phần dùng

`api` (`@/lib/api`), `useAuth` (`@/lib/auth`), `DraftResponse` (`@/types/wiki`), `WikiDraftDiff` (props dùng: `oldText`, `newText`, `mode`, `contextLines`), `WikiAiCheckPanel` (props `status`, `results`), `WikiContent` (prop `markdown`), `Button` (biến thể `default`, `outline`, `destructive`, cỡ `sm`), `EmptyState` (props `icon`, `title`, `description`). Chi tiết hiển thị của các thành phần wiki xem 07d.

---

## 2. Màn danh sách văn bản — `/wiki/law` (đã có trong c2)

File `frontend/src/app/(portal)/wiki/law/page.tsx`, `frontend/src/lib/legal-doc.ts`, `frontend/src/types/legal-doc.ts` đã có trong c2 và trùng hành vi nguồn. Mục này chỉ ghi phụ thuộc để bản c2 chạy được.

### 2.1 Hành vi tóm tắt

- Header: icon `auto_stories`, tiêu đề "Kho tri thức" (cùng nội dung khóa `nav.wiki`), mô tả "Tra cứu văn bản theo số hiệu, lĩnh vực và tình trạng hiệu lực."; nút liên kết "Đồ thị tri thức" (icon `hub`) tới `/wiki/graph`.
- Hai cột: danh sách bên trái, thanh lọc "Tra cứu nhanh" bên phải (trên mobile thanh lọc lên đầu). Tìm theo hai chế độ "Tiêu đề, số hiệu" (lọc tại client theo tiêu đề, số hiệu, trích yếu, tên tệp) hoặc "Nội dung văn bản" (gọi server). Sắp xếp "Ban hành mới nhất" (mặc định), "Ban hành cũ nhất", "Hiệu lực mới nhất", "Tên A → Z". Bộ lọc facet: Kiểu tri thức (ghi trên URL `?kt=a,b`), Loại văn bản, Tình trạng hiệu lực, Lĩnh vực, Phòng ban / phạm vi, Cơ quan ban hành, Năm ban hành; OR trong nhóm, AND giữa các nhóm. Phân trang 30 mục, nút "Xem thêm (N văn bản)". Nhãn "Mới" cho văn bản tạo trong 7 ngày.
- Mỗi văn bản có các liên kết tab tới trang chi tiết: "Tài liệu gốc", "Toàn văn", "Tổng quan", "Lược đồ", "Đồ thị" (dùng `legalDocHref(doc, tab)` với tab tương ứng `source`, `fulltext`, `overview`, `schema`, `graph`), nút sao chép liên kết, và "Tải về" khi `has_file`.
- Màn này còn được trang chủ portal (`/(portal)/page.tsx`) import làm export mặc định để nhúng.

### 2.2 API

| Thời điểm | Method + path | Ghi chú |
|---|---|---|
| Khi mở màn | `GET /api/wiki/legal-docs` | Trả `LegalDocList`: `items` (mảng `LegalDoc`), `knowledge_types` (mảng `{id, name, slug, color}`). Lỗi: `EmptyState` icon `error` "Không tải được danh sách" với mô tả là thông điệp lỗi (mặc định "Không tải được danh sách văn bản"). |
| Chế độ "Nội dung văn bản", có từ khóa, chờ 400 ms sau lần gõ cuối | `GET /api/wiki/legal-docs?content_q=<từ khóa>` | Chỉ dùng tập `id` trong `items` để lọc danh sách đã tải; bỏ qua phản hồi cũ; lỗi coi như không có kết quả. |
| Bấm "Tải về" | `GET /api/sources/{id}` | Nếu có `download_url` thì mở ở tab mới; lỗi bỏ qua. |

### 2.3 Phụ thuộc phải có trong c2

| Module | Tên dùng | Ghi chú |
|---|---|---|
| `@/lib/api` | `api<T>(path, options?)` | Xem 07a |
| `@/lib/utils` | `cn(...)` | Ghép class |
| `@/components/shared/empty-state` | `EmptyState` | Props `icon`, `title`, `description` |
| `@/components/wiki/wiki-facets` | `FacetGroup`, kiểu `FacetOption`, `countFacet` | Xem 07d. `FacetGroup` nhận `title`, `options`, `selected` (tập giá trị), `onToggle(value)`, tùy chọn `searchable`, `searchPlaceholder`, `defaultOpen`. `FacetOption` có `value`, `label`, `count`, tùy chọn `color`. `countFacet(danh sách, hàm lấy khóa, hàm nhãn, thứ tự tùy chọn)` trả mảng `FacetOption`. |
| `@/components/wiki/formatted-inline-text` | `FormattedInlineText` | Prop `text`; xem 07d |
| `@/types/legal-doc` | `LegalDoc`, `LegalDocList` | Có sẵn |
| `@/lib/legal-doc` | `VALIDITY_INFO`, `VALIDITY_ORDER`, `docTypeOf`, `formatViDate`, `legalDocHref`, `validityOf` | Có sẵn |

Hiện c2 chưa có `components/wiki/*` và `lib/utils`; các module này phải được tạo theo 07a/07d trước khi màn biên dịch.

---

## 3. Màn chi tiết văn bản — `/wiki/law/[key]`

### 3.1 Mục đích và route

Xem một văn bản pháp luật/tri thức với năm tab: tệp gốc, toàn văn theo điều, tổng quan thuộc tính, lược đồ quan hệ, đồ thị liên kết.

- Tham số đường dẫn `key`: giải mã URL; là `doc_slug` của văn bản nếu có, ngược lại là id nguồn (theo `legalDocKey`). Liên kết tới màn luôn tạo bằng `legalDocHref`.
- Query `tab`: một trong `source`, `fulltext`, `overview`, `schema`, `graph`. Giá trị khác hoặc vắng thì dùng tab mặc định: `fulltext` nếu văn bản không có tệp (`has_file` false và không có `file_url`), ngược lại `source`.
- Đổi tab: giữ các query khác, đặt `tab`, `router.replace` tới `/wiki/law/<key đã mã hóa>?...`, không cuộn.
- Không kiểm tra quyền phía client. Backend trả 404 "Document not found" hoặc 403 "Access denied".

### 3.2 API

| Thời điểm | Method + path | Trường dùng |
|---|---|---|
| Khi `key` đổi | `GET /api/wiki/legal-docs/{key đã mã hóa URL}` | `LegalDocDetail` (mục 3.10) |
| Tab Tài liệu gốc mở | `GET /api/sources/{id văn bản đã mã hóa}` | `file_name`, `title`, `file_size`, `contributed_by_name`, `preview_url`, `file_url`, `download_url`, `source_type`, `url`, `preserve_verbatim`; lỗi bỏ qua (dùng dữ liệu của văn bản) |
| Tab Đồ thị mở và có `overview_slug` | `GET /api/wiki/graph?slug=<overview_slug>&depth=1` | `nodes`, `edges` (kiểu `WikiGraphData` trong `@/types/wiki`) |

Mọi yêu cầu đều bỏ qua phản hồi đến muộn của `key`/`slug`/`id` cũ.

### 3.3 Trạng thái tải

| Trạng thái | Hiển thị |
|---|---|
| Chưa có phản hồi cho `key` hiện tại | Khối cao 256px, icon `progress_activity` cỡ lớn xoay, màu muted, căn giữa |
| Lỗi | Liên kết quay lại (3.4) rồi `EmptyState` icon `error`, tiêu đề "Không mở được văn bản", mô tả = thông điệp lỗi (mặc định "Không tải được văn bản") |
| Thành công | Bố cục 3.4 |

### 3.4 Bố cục chung

Cột dọc, các khối cách đều:

1. **Liên kết quay lại**: icon `arrow_back` + "Danh sách văn bản", tới `/wiki/law`, chữ nhỏ muted, hover primary, căn trái.
2. **Tiêu đề** (3.5) và **hàng huy hiệu** (chữ xs, xuống dòng khi tràn), theo thứ tự, mỗi huy hiệu dạng viên thuốc có viền:
   - `meta.doc_type` (nếu có): viền/nền/chữ primary, đậm.
   - Tình trạng hiệu lực: nhãn và màu theo `VALIDITY_INFO[validityOf(doc)]` (nền nhạt + chữ + viền cùng sắc của tình trạng).
   - `meta.doc_number` (nếu có): nền muted nhạt.
   - `knowledge_type` (nếu có): chấm tròn màu `knowledge_type.color` + `knowledge_type.name`.
   - `meta.field` (nếu có): chữ muted.
   - Nếu có `download_url`: nút liên kết đẩy sát phải, icon `download` + "Tải về", mở tab mới.
3. **Thanh tab**: viền dưới, cuộn ngang khi tràn. Mỗi tab: icon + nhãn, gạch chân 2px; tab đang chọn gạch và chữ primary; còn lại chữ muted, hover foreground.

| id | Nhãn | Icon |
|---|---|---|
| `source` | Tài liệu gốc | `description` |
| `fulltext` | Toàn văn | `article` |
| `overview` | Tổng quan | `info` |
| `schema` | Lược đồ | `account_tree` |
| `graph` | Đồ thị | `hub` |

4. Nội dung tab đang chọn.

### 3.5 Tiêu đề văn bản

Tiêu đề văn bản hợp nhất thường dài, kèm danh sách văn bản sửa đổi. Quy tắc tách:

- Tìm (không phân biệt hoa thường) lần xuất hiện đầu tiên của một trong các cụm: "Có hiệu lực kể từ", "Được sửa đổi", "Đã được sửa đổi", "Sửa đổi, bổ sung bởi" — cho phép một dấu phẩy hoặc chấm phẩy và khoảng trắng đứng trước cụm.
- Nếu không tìm thấy, hoặc vị trí bắt đầu nhỏ hơn 20 ký tự: toàn bộ là phần chính, không có phần đuôi.
- Ngược lại: phần chính = đoạn trước vị trí đó (trim); phần đuôi = đoạn từ vị trí đó, bỏ các dấu phẩy, chấm phẩy và khoảng trắng ở đầu.

Hiển thị: tiêu đề cấp 1 (cỡ lớn, đậm, tự xuống dòng, tooltip là tiêu đề đầy đủ) render phần chính bằng `FormattedInlineText`. Nếu có phần đuôi: dưới tiêu đề là nút chữ primary "Xem thông tin sửa đổi, bổ sung"; bấm sẽ hiện đoạn văn muted chứa phần đuôi (qua `FormattedInlineText`) phía trên nút, và nút đổi thành "Thu gọn".

### 3.6 Tab Tài liệu gốc (`source`)

Dữ liệu ưu tiên lấy từ `GET /api/sources/{id}`, trường nào trống thì lấy từ văn bản chi tiết. Suy ra:

- Tiêu đề hiển thị = `title` hoặc tên tệp hoặc "Tài liệu"; chỉ hiện phần chính theo quy tắc 3.5.
- Là liên kết web khi `source_type` = `url`, hoặc không có tên tệp mà có `url`.
- URL xem = `preview_url`, nếu không có thì `file_url`, nếu không có thì `download_url`.
- Có tệp khi `has_file` true hoặc có URL xem.
- Loại tệp theo phần mở rộng tên tệp (không phân biệt hoa thường): PDF = `.pdf`; ảnh = `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`, `.svg`; văn phòng/văn bản = `.docx`, `.doc`, `.xlsx`, `.xls`, `.pptx`, `.ppt`, `.txt`, `.md`, `.csv`, `.json`.

**Thanh thông tin tệp** (card bo góc, đổ bóng nhẹ, hai đầu):

- Trái: icon lớn màu primary — `language` nếu là liên kết web, `picture_as_pdf` nếu PDF, ngược lại `description`. Bên cạnh: tiêu đề (đậm, cắt khi dài quá khoảng 500px, tooltip đầy đủ) và, nếu `preserve_verbatim` true, nhãn nhỏ nền secondary "Verbatim". Dòng phụ xs muted: nếu là liên kết web có URL thì hiện URL dạng liên kết mở tab mới kèm icon `open_in_new`; ngược lại "Dung lượng: X.XX MB" (byte chia 1024², 2 chữ số thập phân) khi có `file_size`, nếu không thì tên tệp hoặc "Tài liệu số hóa". Nếu có người đóng góp: nối thêm " • Đăng bởi: <tên>".
- Phải: nút outline icon `open_in_new` "Mở tab mới" (khi có URL xem, mở URL xem ở tab mới); nút primary icon `cloud_download` "Tải tài liệu gốc" (khi có `download_url`). Hai nút phóng nhẹ khi hover, thu nhẹ khi nhấn.

**Khung xem** (bo góc lớn, viền, nền card mờ):

| Điều kiện | Hiển thị |
|---|---|
| Có tệp, có URL xem, PDF | iframe cao 800px rộng hết khung, nguồn = URL xem kèm hậu tố bật thanh công cụ PDF (`#toolbar=1`), không viền |
| Có tệp, ảnh | Ảnh căn giữa trong vùng tối thiểu 400px, cao tối đa 700px, giữ tỉ lệ, bo góc, viền, đổ bóng; alt = tiêu đề |
| Có tệp, văn phòng/văn bản | iframe cao 800px, nguồn = `preview_url` hoặc `download_url` |
| Có tệp, định dạng khác | Khối căn giữa: icon `draft`; "Không thể xem trước định dạng này trực tiếp" (đậm); mô tả "Tài liệu "<tên tệp>" không hỗ trợ nhúng trực tiếp. Vui lòng bấm Tải tài liệu gốc để đọc."; nút outline `cloud_download` "Tải tài liệu gốc" nếu có `download_url` |
| Không có tệp, là liên kết web có URL | Khối căn giữa: icon `language` lớn màu primary nhạt; "Liên kết tài liệu gốc (Website Source)"; mô tả "Đây là một liên kết ngoài. Bạn có thể mở trực tiếp trang web để đọc toàn văn tài liệu."; nút outline `open_in_new` "Mở trang Web gốc" mở URL ở tab mới |
| Còn lại | Khối căn giữa: icon `description`; "Văn bản không có tệp đính kèm gốc"; mô tả "Văn bản này chỉ có nội dung đã số hóa. Bạn có thể chuyển sang tab "Toàn văn" để xem chi tiết các điều khoản." |

### 3.7 Tab Toàn văn (`fulltext`)

Lưới hai cột trên màn rộng (nội dung linh hoạt + mục lục rộng khoảng 17rem, khoảng 20rem ở màn rất rộng); một cột trên màn hẹp.

**Cột nội dung** (card bo góc, padding rộng):

- Nếu có `preamble`: render bằng `WikiContent`, cỡ chữ 15px, ngăn cách bằng đường kẻ dưới.
- Nếu không có điều nào và không có `preamble`: "Văn bản chưa có nội dung trích xuất." (muted).
- Mỗi điều (`articles[i]`) là một section có anchor `art-<i>` (chừa khoảng cuộn trên):
  - Tiêu đề chương — hiện khi điều có `chapter_title` và `chapter_num` khác điều liền trước: căn giữa, chữ in hoa đậm "Chương <chapter_num>" (bỏ trống nếu không có số), dòng dưới là `chapter_title` chữ thường đậm vừa.
  - Khối điều (đường kẻ mờ phía dưới, trừ điều cuối): tiêu đề `heading` đậm 15px qua `FormattedInlineText`; nếu có `wiki_slug` thì bên phải là icon `open_in_new` mờ, tooltip "Mở trang wiki của điều này", liên kết tới `/wiki/<wiki_slug>`. Nếu `content_md` không rỗng sau trim: render bằng `WikiContent` cỡ 15px.

**Cột mục lục** (chỉ khi có ít nhất một điều; card; dính trên ở màn rộng, cao tối đa bằng chiều cao khung nhìn trừ phần header):

- Nhãn in hoa nhỏ "Danh sách điều khoản (N)".
- Ô tìm có icon `search` bên trái, placeholder "Tìm điều khoản...". Lọc điều theo `heading` chứa chuỗi tìm (không phân biệt hoa thường, đã trim).
- Danh sách nút (cuộn; trên màn hẹp cao tối đa 60% khung nhìn), mỗi nút hiện `heading` qua `FormattedInlineText`, tối đa 2 dòng, tooltip đầy đủ, hover nền muted và chữ primary. Bấm cuộn mượt tới anchor của điều đó (căn đầu).
- Không khớp: "Không có kết quả".

### 3.8 Tab Tổng quan (`overview`)

Cột dọc rộng tối đa khoảng 5xl.

**Bảng thuộc tính** (card bo góc): lưới 2 cột trên màn vừa trở lên (1 cột trên mobile), mỗi ô là cặp nhãn (rộng cố định 10rem, nền muted nhạt, chữ muted) + giá trị (đậm vừa, tự xuống dòng); đường kẻ giữa các hàng, hàng cuối không kẻ. Thứ tự (đọc trái sang phải, trên xuống dưới):

| Nhãn | Giá trị |
|---|---|
| Số hiệu | `meta.doc_number` hoặc "—" |
| Ngày ban hành | `formatViDate(meta.issued_date)` |
| Loại văn bản | `meta.doc_type` hoặc "—" |
| Ngày hiệu lực | `formatViDate(meta.effective_date)` |
| Cơ quan ban hành | `meta.issuing_authority` hoặc "—" |
| Ngày hết hiệu lực | `formatViDate(meta.expiry_date)` |
| Lĩnh vực | `meta.field` hoặc "—" |
| Tình trạng pháp lý | Nhãn `VALIDITY_INFO[...]`, chữ đậm, màu chữ = màu đặc trưng của tình trạng |
| Nguồn thu thập | Nếu có `file_url` hoặc `url`: liên kết primary "Mở văn bản gốc" + icon `open_in_new`, mở tab mới (ưu tiên `file_url`); ngược lại `file_name` hoặc "—" |
| Bố cục | "<meta.article_count> điều" nếu có; nếu không thì "<số phần tử articles> điều" nếu > 0; ngược lại "—" |

Nếu có `meta.official_title`: thêm một hàng rộng hết bảng, có viền trên, nhãn "Trích yếu".

**Thanh tình trạng**: hộp bo góc, nền đặc bằng sắc của tình trạng (`VALIDITY_INFO[...]`), chữ trắng đậm, icon `verified` (còn hiệu lực), `schedule` (chưa có hiệu lực) hoặc `info` (khác). Văn bản xác định theo thứ tự (quy tắc sau ghi đè quy tắc trước):

1. Mặc định là nhãn tình trạng.
2. Còn hiệu lực và có ngày hiệu lực: "Còn hiệu lực từ <dd/mm/yyyy>".
3. Chưa có hiệu lực và có ngày hiệu lực: "Có hiệu lực từ <dd/mm/yyyy>".
4. Nếu `replaced_by` khác rỗng: "Bị thay thế bởi <các số hiệu nối bằng dấu phẩy>"; ngược lại nếu `repealed_by` khác rỗng: "Bị bãi bỏ bởi <...>"; ngược lại nếu hết hiệu lực và có ngày hết hiệu lực: "Hết hiệu lực từ <dd/mm/yyyy>".

**Khối tóm tắt** (card): tiêu đề đậm icon `summarize` màu primary "Tóm tắt văn bản"; nội dung `summary` render bằng `WikiContent` (15px), hoặc "Chưa có tóm tắt." Nếu có `overview_slug`: liên kết primary "Xem trang wiki tổng quan" + icon `arrow_forward` tới `/wiki/<overview_slug>`.

### 3.9 Tab Lược đồ (`schema`)

Lưới 2 cột ở màn rất rộng, 1 cột khi hẹp.

**Khối quan hệ** (dùng hai lần). Mỗi khối là card có tiêu đề đậm: icon màu primary + tên + "(tổng số quan hệ)" muted. Quan hệ được nhóm theo `relation_type` theo thứ tự xuất hiện. Không có quan hệ: "Chưa ghi nhận quan hệ nào." Mỗi nhóm: nhãn in hoa nhỏ muted "<nhãn loại> (số lượng)" (nhãn lấy từ bảng nhãn tương ứng, nếu không có thì dùng nguyên mã loại), rồi danh sách có viền bo góc, phân cách bằng đường kẻ; mỗi dòng: [nhãn nguồn muted] [icon `arrow_forward` muted] [nhãn đích đậm vừa], và nếu có `quote` thì đoạn trích xs muted tối đa 2 dòng. Nhãn nguồn rỗng thì không hiện cả nhãn nguồn lẫn mũi tên.

"Mô tả đích" của một quan hệ: ghép bằng khoảng trắng các phần "Khoản <clause>" (nếu có), "Điều <article>" (nếu có), và (tùy trường hợp) `doc_number`; nếu rỗng dùng giá trị dự phòng.

| Khối | Tiêu đề | Icon | Dữ liệu | Bảng nhãn | Nhãn nguồn | Nhãn đích |
|---|---|---|---|---|---|---|
| Đi ra | "Văn bản này tác động / căn cứ" | `call_made` | `relations.outgoing` | `RELATION_LABEL_VI` | "Điều <from_article>" nếu có, ngược lại không hiện | Mô tả đích có kèm `doc_number`, dự phòng "—" |
| Đi vào | "Văn bản khác tác động" | `call_received` | `relations.incoming` | `RELATION_INCOMING_LABEL_VI` | Mô tả đích không kèm `doc_number`, dự phòng "Toàn văn bản" (phần bị tác động của văn bản này) | `doc_number` và "Điều <from_article>" nối bằng " · " (bỏ phần trống), dự phòng "—" (văn bản tác động) |

**Khối trang wiki sinh từ văn bản** — chỉ khi `wiki_pages` khác rỗng; chiếm cả 2 cột. Tiêu đề icon `auto_stories` "Trang wiki sinh từ văn bản (N)". Lưới 1/2/3 cột theo độ rộng; mỗi mục là liên kết tới `/wiki/<slug>`, hiện `title` một dòng (cắt, tooltip đầy đủ), hover nền muted và chữ primary.

### 3.10 Tab Đồ thị (`graph`)

| Điều kiện | Hiển thị |
|---|---|
| Không có `overview_slug` | `EmptyState` icon `hub`, "Chưa có đồ thị", mô tả "Văn bản chưa có trang wiki tổng quan để dựng đồ thị liên kết." |
| Đang tải | Khối cao 256px với icon `progress_activity` xoay |
| Lỗi hoặc `nodes` rỗng | `EmptyState` icon `hub`, "Chưa có đồ thị", mô tả "Không có liên kết nào quanh văn bản này." |
| Có dữ liệu | Khung bo góc có viền chứa `WikiGraph` (`@/components/wiki/wiki-graph`) với `nodes`, `edges`, `centerSlug` = `overview_slug`, `height` = 600; bấm nút đồ thị điều hướng tới `/wiki/<slug của nút>` |

### 3.11 Dữ liệu và helper (đã có trong c2)

Kiểu từ `@/types/legal-doc`: `LegalDocDetail` = `LegalDoc` cộng `preamble` (chuỗi), `articles` (mảng `LegalArticle`: `num`, `heading`, `title`, `content_md`, `chapter_num`, `chapter_title`, `wiki_slug`), `relations` (`outgoing`, `incoming`: mảng `LegalDocRelation`: `relation_type`, `doc_number`, `article`, `clause`, `from_article`, `quote`), `wiki_pages` (mảng `{slug, title, page_type, summary}`), `overview_slug`, `summary`, `download_url`, `file_url`, tùy chọn `preview_url`, `file_size`, `source_type`, `contributed_by_name`. Từ `LegalDoc` màn dùng: `id`, `title`, `file_name`, `knowledge_type`, `has_file`, `url`, `meta` (`doc_type`, `doc_number`, `issuing_authority`, `official_title`, `issued_date`, `effective_date`, `expiry_date`, `field`, `article_count`), `validity`, `replaced_by`, `repealed_by`.

Helper từ `@/lib/legal-doc`:

| Tên | Chữ ký | Dùng ở |
|---|---|---|
| `validityOf(doc)` | nhận đối tượng có `validity`, trả `Validity` (null thành `khong_xac_dinh`) | Huy hiệu, Tổng quan |
| `VALIDITY_INFO` | ánh xạ `Validity` sang `{label, color, badge, bar}` | Huy hiệu (`badge`), màu chữ tình trạng (`color`), thanh tình trạng (`bar`) |
| `formatViDate(iso)` | chuỗi `YYYY-MM-DD...` hoặc null, trả `dd/mm/yyyy` hoặc "—" | Tổng quan |
| `RELATION_LABEL_VI`, `RELATION_INCOMING_LABEL_VI` | ánh xạ mã quan hệ sang nhãn chủ động/bị động | Lược đồ |
| `legalDocKey`, `legalDocHref`, `docTypeOf`, `VALIDITY_ORDER` | — | Màn danh sách; khóa URL của màn chi tiết |

Bảng tình trạng hiệu lực (theo `VALIDITY_ORDER`):

| Mã | Nhãn | Sắc vai trò |
|---|---|---|
| `con_hieu_luc` | Còn hiệu lực | xanh lục |
| `chua_co_hieu_luc` | Chưa có hiệu lực | hổ phách |
| `bi_thay_the` | Bị thay thế | tím |
| `het_hieu_luc` | Hết hiệu lực | đỏ |
| `khong_xac_dinh` | Chưa xác định | xám đá |

Mã quan hệ: `sua_doi`, `bo_sung`, `thay_the`, `bai_bo`, `huong_dan`, `can_cu`, `dan_chieu` (nhãn có sẵn trong hai bảng của `@/lib/legal-doc`).

### 3.12 Thành phần dùng

`api`, `cn`, `Button` (biến thể `default`, `outline`), `EmptyState`, `FormattedInlineText`, `WikiContent` (prop `markdown`), `WikiGraph` (props `nodes`, `edges`, `centerSlug`, `height`, `onNodeClick(slug)`), kiểu `WikiGraphData` (`@/types/wiki`), `Link` của Next.js, `useParams`/`useRouter`/`useSearchParams`.
