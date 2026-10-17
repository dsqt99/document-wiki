# 07. Đặc tả giao diện (frontend) — mục lục

Bộ đặc tả giao diện web "Document Wiki" (Next.js App Router + Tailwind + shadcn/ui style base-nova). Người viết code chỉ dựa vào các file dưới đây, các file loại C đã có trong `frontend/src` của c2 và `tests/`. Theo `QUY_TAC_DAC_TA.md`: không có đoạn code, chỉ văn xuôi và bảng. Nhãn ghi theo khóa i18n trong `frontend/src/lib/i18n.tsx`.

## 1. Danh sách file

| File | Nội dung |
|---|---|
| `07a_giao_dien_nen_tang.md` | Nền kỹ thuật (phiên bản, env, rewrite, Docker), xác thực và khóa lưu trữ, chế độ nhúng iframe, sáng/tối, i18n, layout portal, thanh bên, menu người dùng, chuông và ngăn thông báo, design token, danh sách primitive shadcn, giao diện `lib/api`, `lib/utils`, `lib/auth`, `types/notification`, `EmptyState`, `PageHeader`, `StatCard`, bảng file loại C và import của chúng |
| `07b_giao_dien_dang_nhap_tong_quan.md` | `/login`, `/login/sso`, `/logout/sso`, bảng điều khiển `/`, `/profile` (token MCP), `/audit` |
| `07c_giao_dien_tai_lieu_to_chuc.md` | `/knowledge` (thư viện tài liệu, bảng nguồn, dialog tải lên / duyệt kế hoạch / duyệt trích xuất, kiểu tri thức), `/departments`, `/employees`, `ScopeBadge`, `ScopeDialog`, `ScopeMembersDialog` |
| `07d_giao_dien_wiki.md` | `/wiki`, `/wiki/[...slug]`, `/wiki/graph`, `/wiki/branches/[id]/rebase`, các component wiki; giao diện `types/wiki`, `wiki-facets`, `formatted-inline-text`, `textarea-caret`, `use-image-resolver` |
| `07e_giao_dien_phe_duyet_van_ban.md` | `/wiki/review`, `/wiki/law` (đã có, mô tả phụ thuộc), `/wiki/law/[key]` |
| `07f_giao_dien_ky_nang_prompt.md` | `/skills`, `/skills/[slug]`, `/skills/[slug]/edit`, `/admin/skill-contributions`, `/prompts` |
| `07g_giao_dien_cai_dat.md` | `/settings` và mọi tab; giao diện `test-lab`, `model-catalog-card`, `provider-model-picker` |

Bản đồ route đầy đủ ở `07a` mục 2.5.

## 2. Thứ tự dựng gợi ý

1. Khởi tạo dự án và shadcn theo `07a` mục 1 và 4; viết `globals.css` theo token mục 3.
2. Viết `lib/api.ts`, `lib/utils.ts`, `lib/auth.tsx`, `types/notification.ts`, `components/shared/{empty-state,page-header,stat-card}.tsx` theo `07a` mục 5. Lúc này `app/logout/sso/page.tsx` và `components/shared/library-list.tsx` (loại C) đã biên dịch được.
3. Viết `types/wiki.ts`, `components/wiki/wiki-facets.tsx`, `components/wiki/formatted-inline-text.tsx` (07d) để `lib/wiki-store.ts` và `app/(portal)/wiki/law/page.tsx` (loại C) chạy.
4. Viết `components/settings/test-lab.tsx`, `model-catalog-card.tsx`, `provider-model-picker.tsx` (07g) để ba card cài đặt loại C chạy.
5. Layout gốc, layout portal, thanh bên, thông báo (07a mục 2), rồi lần lượt các trang 07b → 07g.

## 3. Điểm lệch đã biết trong bản gốc (người dựng cần quyết định)

| Chỗ | Mô tả | Khuyến nghị |
|---|---|---|
| Ngăn thông báo | Nút "đánh dấu tất cả đã đọc" dùng khóa `common.clear`, trạng thái rỗng dùng `audit.noLogs` | Giữ nguyên để giống bản gốc, hoặc thêm khóa riêng vào i18n (do nhóm sửa file loại C) |
| `/audit` phân trang | Trang gửi `size` và đọc `pages`, backend nhận `page_size` và không trả `pages` | Tính số trang từ `total` (xem 07b) |
| Quyền nhật ký | Thanh bên kiểm `org:audit:read`, backend có thể dùng chuỗi quyền khác | Đối chiếu với đặc tả RBAC backend |
| i18n | Khóa `stats.rolling` không có trong `i18n.tsx` của c2 | Dùng fallback chữ tiếng Việt hoặc bổ sung khóa |
| `/wiki/review` | Từ chối / yêu cầu sửa đều gọi đóng nhánh mà không gửi ghi chú; kết quả AI thăm dò không được hiển thị | Xem 07e |
