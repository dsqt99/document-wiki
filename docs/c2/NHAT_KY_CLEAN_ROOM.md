# Nhật ký clean-room

| Ngày | Mảng | Vai | Người / tác nhân | Nguồn được đọc | Đầu ra |
|---|---|---|---|---|---|
| 2026-10-16 | 01–07 | Viết đặc tả | Agent đặc tả (Claude), mỗi mảng một phiên riêng | `document-wiki` (Arkon + phần nhóm sửa) | `docs/c2/dac_ta/0*.md` |
| 2026-10-16 | Nền tảng + 5 mảng backend | Viết mã | Agent thực thi (Claude), mỗi mảng một phiên, không được đọc `document-wiki` | `docs/c2/dac_ta/`, file loại C đã duyệt, `tests/` | `app/`, `alembic/`, `tests/` — 331 passed, 30 skipped (cần Postgres) |
| 2026-10-16 | 07a–07g frontend | Viết mã | Agent thực thi frontend (Claude), không được đọc `document-wiki` | `docs/c2/dac_ta/07*.md`; shadcn/ui sinh mới từ CLI (MIT) | `frontend/` — 23 route; tsc, lint, build đạt |
| 2026-10-17 | Đo trùng | Kiểm tra | Điều phối (Claude) | c2 + snapshot Arkon `274a2d2` + `upstream/main` | Đo theo khối 40 token (`tools/do_trung_khoi.py`): 21 file từ 10% trở lên |
| 2026-10-17 | Khắc phục trùng | Viết lại | Agent khắc phục (Claude). Chỉ nhận đường dẫn file c2 và số dòng, không nhận nội dung Arkon | file c2, đặc tả, test | Viết lại cấu trúc 27 file. Giữ nguyên hành vi, tên công khai, schema CSDL và revision id. Test và build vẫn đạt |
| 2026-10-17 | Thương hiệu | Đổi tên | Điều phối (Claude) | c2 | Chữ hiển thị "Arkon" đổi thành "Document Wiki". Giữ các định danh tích hợp: tên server MCP `arkon`, `arkon://`, cookie/localStorage `arkon_*`, header `X-Arkon-Signature`, đường dẫn `/api/v1/arkon/sso/return`, collection Milvus |
| 2026-10-17 | Sửa lệch hành vi (so sánh hộp đen) | Viết mã | Agent thực thi (Claude), không đọc `document-wiki` hay snapshot Arkon | Chỉ mô tả hành vi quan sát được từ bên ngoài (request/response, giao diện) do điều phối cung cấp; file c2, đặc tả, test | API: `/api/skills` nhận `limit` tới 5000; `/api/departments` sắp theo `created_at` tăng dần; `/api/wiki/my-scopes` trả Global + mọi phòng ban cho admin; `/api/admin/stats/overview` có `as_of` dạng `YYYY-MM-DD` (ngày hiện tại) và luôn có KPI `draft.time_to_review_avg_seconds`; bỏ `latest_lists["wiki.pages.by_type"]` (content), `latest["draft.time_to_review_avg_seconds"]` và `latest_lists["draft.created.by_source"]` (contribution); `knowledge_types[]` của `/api/wiki/legal-docs` bỏ `description`, `sort_order`; `specs[]` của `/api/settings/vision/catalog` có `protocol`. Giao diện: "As of" chỉ hiện ngày; nhãn vai trò viết hoa đầu mỗi từ; ô chọn phiên bản kỹ năng chỉ hiện số; bảng Kho tri thức vừa khung 1440px; chú giải đồ thị wiki dùng tiêu đề thường, chấm màu cấp scope, số scope. Test `tests/test_api_parity_fixes.py`: 355 passed, 30 skipped; tsc, lint, build đạt |
| 2026-10-17 | Đồng bộ giao diện (đo hộp đen) | Viết mã | Agent thực thi (Claude), không đọc `document-wiki` hay snapshot Arkon | Chỉ số đo kích thước/màu/khoảng cách và ảnh chụp 1440x900 từ script đo do điều phối cung cấp (không xem mã, DOM hay bundle của bản gốc); file c2 | Chỉnh khoảng cách, cỡ chữ, độ đậm, bo góc, bóng đổ, chiều cao nút/ô nhập ở mọi màn hình: thanh bên, tiêu đề trang (`PageHeader` thêm `actionClassName`), tổng quan, kho tri thức, văn bản pháp lý, trang wiki (cây trang không tự cuộn khi tải, mục lục, liên kết ngược, bộ lọc), đồ thị wiki, hàng duyệt, xử lý xung đột nhánh, kỹ năng và chi tiết kỹ năng, phòng ban, nhân viên, nhật ký, cài đặt, hồ sơ. Số dòng lệch chỉ số 489 → 195. tsc, lint (1 cảnh báo có sẵn), build đạt; pytest 355 passed, 30 skipped |
| 2026-10-17 | Đồng bộ giao diện, vòng 2 (đo hộp đen) | Viết mã | Agent thực thi (Claude), không đọc `document-wiki` hay snapshot Arkon | Ảnh đối chiếu và chỉ số đo từ script của điều phối; file c2 | Tên thương hiệu "Document Wiki" ở thanh bên hiển thị đủ, không cắt; cây trang wiki: trang tổng quan của mỗi văn bản hiện thành dòng có biểu tượng, nhãn "Tổng quan văn bản" (không còn dòng gạch đầu dòng trùng), khung lọc có đường kẻ dưới, ô chọn văn bản cao 32px, khoảng cách dòng khớp bản gốc; bảng nhật ký kiểm toán dùng tỷ lệ cột cố định khớp độ rộng cột đo được. Số dòng lệch chỉ số 195 → 184 (audit 13 → 2); ảnh lệch wiki_page 12,06% → 8,72%, audit 5,98% → 1,53%. tsc, lint, build đạt |
| 2026-10-17 | Sửa lỗi mục lục "Toàn văn" theo báo lỗi của người dùng | Viết mã | Điều phối (Claude), không đọc `document-wiki` hay snapshot Arkon | Ảnh chụp lỗi do người dùng gửi; file c2 `law-fulltext-tab.tsx` | Mục lục không còn lộ nửa dòng thứ 3 (line-clamp chuyển vào phần chữ, không đặt trên nút có padding); thêm theo dõi điều đang đọc bằng IntersectionObserver: tô đậm mục tương ứng và chỉ cuộn danh sách mục lục để mục đó luôn nhìn thấy. tsc, lint đạt; kiểm tra Playwright ở Điều 3/17/42/56 |
| 2026-10-17 | Sửa bộ tách Điều theo báo lỗi của người dùng (VBHN 22/2026) | Viết mã | Điều phối (Claude), không đọc `document-wiki` hay snapshot Arkon | Văn bản trích xuất của nguồn c2 `eab6143e`; file c2 `legal_hierarchy_parser.py`, test | Ngoặc kép không đóng ở chú thích phần mở đầu không còn nuốt Chương I, Điều 1, Điều 2 (đóng ngoặc ở tiêu đề Chương/Điều 1 đầu tiên không lặp lại). Dòng tham chiếu bị ngắt dòng ("Điều 5; Điều 6; ...", "...</mark> Điều 41.") không còn bị nhận là tiêu đề Điều. VBHN 22: 65 → 63 Điều, đủ 1–59 + 4a/44a/44b/56a, không trùng; VBHN 90 và 75 không đổi. Test parser 6 passed |

## Kết quả đo trùng (2026-10-17)

### Đo theo khối (tiêu chí chính)

`python -I tools/do_trung_khoi.py 0.10 <arkon_274a2d2> <arkon_upstream>`, K=40 token, bỏ qua chú thích, import và `components/ui` (shadcn, MIT).

| Thời điểm | Số file từ 10% trở lên |
|---|---:|
| Trước khi khắc phục | 21 |
| Sau khi khắc phục | **0** (327 file) |

### Đo theo dòng (`tools/do_trung_ma.py`, mỗi dòng có nghĩa từ 25 ký tự)

Có 142/352 file vượt 10%. Trong đó:

- **17 file** là shadcn/ui. Cả hai kho cùng sinh từ CLI MIT, nên trùng 100%.
- **Các file còn lại** trùng ở những dòng bị giao diện ép buộc:
  - decorator route và đường dẫn API;
  - tên cột, tên trường, chữ ký hàm;
  - chuỗi lỗi mà frontend và chatbot đang so khớp;
  - thành ngữ thông dụng của FastAPI, SQLAlchemy và React.

Thước đo này đếm từng dòng riêng lẻ, nên không phân biệt được trùng tên với chép cấu trúc. Vì vậy nó chỉ dùng để tham khảo. Tiêu chí quyết định là đo theo khối.

## Khác biệt đã biết so với bản gốc (giữ nguyên để tương đương)

- Frontend gọi `/api/scopes/{type}/{id}/members` (GET/POST/DELETE) và `/api/projects/{id}/wiki/graph`. Bản gốc cũng không có hai route này: `scopes.py` không được mount và import model không tồn tại. Gọi vào sẽ nhận 404, giống hệt bản gốc.

## Việc pháp lý còn mở

- `NOTICE`: điền tên chủ sở hữu bản quyền.
- Xác nhận lịch sử: nhóm chưa ký hay nhận giấy phép nào ràng buộc với Bitsness.
- Thương hiệu Open WebUI phía `chatbot_local` là một sản phẩm riêng, cần rà theo giấy phép của Open WebUI.
- Luật sư rà soát trước khi bán.
