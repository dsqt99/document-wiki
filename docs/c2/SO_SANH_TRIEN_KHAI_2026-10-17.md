# So sánh triển khai song song: bản gốc (document-wiki) và c2 — 17/10/2026

| | Bản gốc | c2 |
|---|---|---|
| Frontend | http://localhost:3119 | http://localhost:3219 |
| API | http://localhost:5055 | http://localhost:5155 |
| Dữ liệu | DB gốc | Bản sao dữ liệu của DB gốc (bảng đếm khớp: 216 trang wiki, 3 tài liệu, 11 kỹ năng, 5 nhân sự…), MinIO đã mirror, **chưa** copy vector Milvus |

Phương pháp:
- So sánh API: đăng nhập cùng tài khoản admin, gọi 44 endpoint GET mà frontend dùng, rồi so mã trạng thái, cấu trúc JSON và số phần tử.
- So sánh giao diện: dùng Playwright chụp 19 màn hình ở 1440×900 (locale vi-VN), ghép ảnh cạnh nhau, đo tỉ lệ điểm ảnh khác nhau, và ghi lỗi console cùng các HTTP ≥ 400.
- Sửa lệch: mọi bản sửa cho c2 đều do agent clean-room làm, chỉ dựa trên mô tả hành vi (black-box). Agent này không đọc mã bản gốc.

## 1. Kết quả API

**Trước khi sửa:** 38/44 endpoint khớp. **Sau khi sửa:** **44/44 khớp**.

| Endpoint | Lệch trước khi sửa | Trạng thái |
|---|---|---|
| `GET /api/skills?limit=2000` | c2 trả 422 vì giới hạn `limit` ≤ 200, nên màn hình Kỹ năng AI hiện 0 kỹ năng | ✅ Đã sửa |
| `GET /api/departments` | Thứ tự khác; bản gốc sắp theo `created_at` tăng dần | ✅ Đã sửa |
| `GET /api/wiki/my-scopes` | Admin trên c2 chỉ thấy phòng ban mình thuộc về (2 mục); bản gốc thấy Global + mọi phòng ban (7 mục) | ✅ Đã sửa |
| `GET /api/admin/stats/overview` | `as_of` là datetime thay vì ngày; thiếu KPI `draft.time_to_review_avg_seconds` | ✅ Đã sửa |
| `GET /api/admin/stats/content`, `/contribution` | c2 có thừa các khoá `latest`/`latest_lists` | ✅ Đã sửa (biểu đồ vẫn có dữ liệu, lấy từ `series`) |
| `GET /api/wiki/legal-docs` | `knowledge_types[]` thừa `description`, `sort_order` | ✅ Đã sửa |
| `GET /api/settings/vision/catalog` | `specs[]` thiếu `protocol` | ✅ Đã sửa |

## 2. Kết quả theo màn hình

Tỉ lệ khác biệt điểm ảnh còn khoảng 2–6% trên phần lớn màn hình. Phần chênh này chủ yếu do khác biệt trình bày chung nêu ở mục 3, không phải do thiếu tính năng.

| Màn hình | Đường dẫn | Kết quả |
|---|---|---|
| Bảng điều khiển (Thống kê & Chẩn đoán) | `/` | ✅ Đủ 12 KPI, đủ 6 tab và 2 khối Khoảng trống / Đóng góp. "As of" đã chỉ còn ngày. |
| Tài liệu (Kho tri thức) | `/knowledge` | ✅ Danh sách, bộ lọc, phân trang, nút Tải lên và Xử lý nội dung khớp. ✅ Đủ các cột như bản gốc, kể cả **Hiệu lực** và **Ngày tạo**. Bảng cuộn ngang giống bản gốc (mục 2b). |
| Wiki | `/wiki` (chuyển sang `/wiki/law`) | ✅ Khớp |
| Trang wiki | `/wiki/90-vbhn-vpqh` | ✅ Nội dung, tóm tắt, mục lục và liên kết trỏ đến (148) khớp. ✅ Cây trang, dòng "Tổng quan văn bản" và danh sách liên kết 2 dòng mỗi mục đã khớp bản gốc (mục 2b). |
| Đồ thị tri thức | `/wiki/graph` | ✅ 210 pages / 414 links. Chú giải đã khớp: tiêu đề thường, có chấm màu, có số lượng scope. Bố cục đồ thị ngẫu nhiên nên vị trí cụm khác nhau. |
| Văn bản pháp luật | `/wiki/law`, `/wiki/law/1093-pv01-d4` | ✅ Khớp |
| Duyệt bản nháp | `/wiki/review` | ✅ Khớp |
| Rebase nhánh | `/wiki/branches/…/rebase` | ✅ Khớp |
| Thư viện kỹ năng | `/skills` | ✅ Đã sửa, nay hiện đủ 11 kỹ năng. ⚠️ Thứ tự và phiên bản khác về **dữ liệu**: lần đầu khởi động, c2 nạp seed mới hơn nên 7 kỹ năng `cahy-kn*` lên v2 (17/10). Đã kiểm tra: khởi động lại không tăng thêm phiên bản. |
| Chi tiết kỹ năng | `/skills/cahy-huong-dan-su-dung` | ✅ Bộ duyệt tệp, nội dung SKILL.md, trạng thái và lịch sử phiên bản khớp. Ô chọn phiên bản đã hiển thị "4" như bản gốc. |
| Đóng góp kỹ năng | `/admin/skill-contributions` | ✅ Khớp |
| Kho prompt | `/prompts` | ✅ Khớp |
| Phòng ban | `/departments` | ✅ Đã sửa thứ tự. Đủ các thao tác Thành viên / Chỉnh sửa / Xoá. |
| Nhân sự | `/employees` | ✅ Hai tab Danh sách và Ma trận RBAC, MCP "Đã kết nối" khớp. Nhãn vai trò đã viết hoa như bản gốc. |
| Nhật ký kiểm toán | `/audit` | ✅ Dữ liệu khớp từng dòng. ✅ Tiêu đề tiếng Anh "Audit Log" / "Refresh" như bản gốc. |
| Cài đặt hệ thống | `/settings` | ✅ Tab Cấu hình và Ma trận phân quyền, các engine PDF/bảng tính/OCR và khung Thử bóc tách khớp. Vùng kéo-thả đã khớp. |
| Hồ sơ | `/profile` | ✅ Khớp |
| Đăng nhập | `/login` | ✅ Đã đăng nhập thì cả hai chuyển về `/` |

## 2b. Đợt khớp giao diện theo số đo (17/10, sau khi chạy bảng trên)

Cách làm: dùng Playwright đo kích thước, vị trí, cỡ chữ, độ đậm, padding, gap và bo góc của sidebar, menu, tiêu đề, nút, tab, ô nhập, bảng, thẻ và badge trên 17 trang của cả hai bản. Sau đó agent clean-room sửa c2 cho tới khi số đo bằng bản gốc. Agent chỉ dùng số đo và ảnh chụp, không xem mã, DOM hay bundle của bản gốc.

- Số dòng lệch về số đo: **489 → 184**. Phần còn lại chủ yếu do script đo ghép nhầm cặp phần tử giữa hai bản, nội dung dài ngắn khác nhau, hoặc nằm dưới vùng màn hình 900px.
- Đã sửa:
  - **Sidebar:** logo DW 26×26, tên "Document Wiki" hiện đủ; mục menu cao 36px; nhãn nhóm cao 23px.
  - **Bảng điều khiển:** tab, nút chọn kỳ và ô ngày theo kích thước của bản gốc; thẻ KPI cao 86px.
  - **Tài liệu:** sửa lại lần chỉnh trước (lần trước ép bảng vừa khung là sai). Bảng nay giữ đủ cột "Hiệu lực" và "Ngày tạo" với độ rộng như bản gốc và cuộn ngang. Tiêu đề cột và dòng có chiều cao như bản gốc.
  - **Nhật ký kiểm toán:** tiêu đề tiếng Anh "Audit Log" / "Refresh" như bản gốc; độ rộng cột cố định theo bản gốc.
  - **Trang wiki:**
    - Cây trang không tự cuộn tới trang đang mở.
    - Mỗi nhóm có dòng "Tổng quan văn bản" kèm icon.
    - Danh sách liên kết hiển thị 2 dòng mỗi mục.
  - **Các trang khác:** chỉnh khoảng cách ở Phòng ban, Nhân sự, Hồ sơ, Cài đặt, Kỹ năng và Kho prompt.

Tỉ lệ khác biệt điểm ảnh sau đợt này (1440×900):

| Màn hình | Trước | Sau |
|---|---|---|
| Bảng điều khiển | 4,93% | 2,07% |
| Tài liệu | 4,04% | 3,22% |
| Trang wiki | 14,55% | 9,79% |
| Đồ thị tri thức | – | 7,54% (bố cục đồ thị ngẫu nhiên) |
| Chi tiết kỹ năng | – | 4,37% |
| Thư viện kỹ năng | – | 2,54% |
| Nhân sự | – | 1,99% |
| Văn bản pháp luật / chi tiết | – | 1,50% / 1,59% |
| Nhật ký kiểm toán | 9,83% | 1,53% |
| Duyệt bản nháp, Rebase, Hồ sơ, Cài đặt, Đóng góp KN, Phòng ban, Kho prompt | – | 0,2–0,9% |

Còn lệch nhỏ:
- **Trang wiki:** khoảng cách dọc trong cột nội dung và panel liên kết lệch vài px; khối "Tóm tắt" của c2 cao hơn một chút.
- **Đồ thị:** vị trí các nút do mô phỏng lực quyết định, mỗi lần tải mỗi khác.
- **Bảng tài liệu, Nhân sự:** cột tự co theo nội dung nên lệch 10–60px.

## 3. Khác biệt trình bày chung (đã xử lý ở mục 2b)

- **Logo sidebar — ✅ đã khớp:** c2 dùng lại logo "DW" của sản phẩm Document Wiki. Đây là tài sản thương hiệu của chủ sản phẩm, không thuộc Arkon, và đã ghi vào `NGUON_GOC.csv`.
- **Mật độ hiển thị — ✅ đã khớp:** trước đây c2 hiển thị đặc hơn bản gốc. Nay kích thước và khoảng cách đã theo số đo của bản gốc (xem mục 2b).

## 4. Vấn đề môi trường phát hiện khi test

- **API key bị mã hoá — ✅ đã xử lý:** các API key copy từ DB gốc (`custom_model_api_key__*`, `ocr_api_key`) trước đây c2 không giải mã được. Đã chuyển đổi trực tiếp giữa hai container theo các bước:
  1. Giải mã bằng `SECRET_KEY` của bản gốc, ngay trong container của bản gốc.
  2. Mã hoá lại bằng khoá của c2, ngay trong container c2, và kiểm tra giải mã ngược.
  3. Ghi vào DB c2.

  Kết quả: 10/10 key chuyển thành công. Khoá không xuất hiện ở log hay terminal. Sau khi khởi động lại, log c2 không còn cảnh báo "Could not decrypt", và API vẫn khớp 44/44.
- **Vector Milvus chưa được copy:** tìm kiếm ngữ nghĩa và hỏi đáp trên c2 có thể ra kết quả khác bản gốc cho tới khi chạy backfill embedding.

## 5. Kiểm tra sau khi sửa

- Backend: `pytest tests` → 355 passed, 30 skipped (cần Postgres), 0 failed. Trong đó có 24 test mới ở `tests/test_api_parity_fixes.py`.
- Frontend: `tsc --noEmit` 0 lỗi. `eslint` 0 lỗi và 1 cảnh báo có sẵn từ trước. `next build` OK.
- Đo trùng khối mã với bản tham chiếu (`tools/do_trung_khoi.py 0.10`): **0/328 file vượt ngưỡng 10%**. Cao nhất là `wiki_branches.py` ở 3,7%.
- Đã rebuild và deploy lại c2 (`docker compose up -d --build`), rồi chạy lại cả hai bộ so sánh.
- Sau đợt khớp giao diện (mục 2b):
  - Frontend: `tsc` 0 lỗi; `eslint` 0 lỗi, còn 1 cảnh báo có sẵn từ trước; `next build` OK.
  - Backend: không đổi mã, `pytest` vẫn 355 passed.
  - API: vẫn khớp 44/44.
  - Đo trùng khối mã với bản tham chiếu: vẫn 0/328 file vượt ngưỡng 10%.

## 6. Thử luồng nạp tài liệu (17/10)

- **c2:** upload `02. Văn bản hợp nhất số 90 Luật XLVPHC.pdf`, gắn 4 phòng ban. Kết quả `ready 100%`, đi qua đủ các bước:
  1. bóc tách nội dung (126.579 token, giống bản gốc);
  2. dựng mục lục;
  3. tách theo từng Điều (800 Điều/Khoản/Điểm, 148 trang mỗi bộ);
  4. trích metadata;
  5. tạo 94 chunk embedding;
  6. tạo embedding và tóm tắt cho mọi trang.
- **Bản gốc (black-box):** upload `04. Nghị định 311.2026.NĐ.CP…docx`, gắn 2 phòng ban PV01 và PA08. Mỗi phòng ban có một bộ trang riêng: 10 trang, cùng `_index` và `_log`. **Hành vi này giống c2**: c2 cũng biên dịch một bộ trang cho mỗi phòng ban được gắn. Vì vậy tìm kiếm có thể trả cùng một Điều nhiều lần, mỗi lần thuộc một phòng ban. Đây là hành vi của sản phẩm, không phải lệch.
- **Dọn dữ liệu test trên bản gốc:** xoá nguồn qua `DELETE /api/sources/{id}`. Lệnh này dọn trang, Điều/Khoản, embedding và object MinIO. Riêng 4 trang `_index`/`_log` mới tạo cho PV01/PA08 vẫn còn, nên đã xoá tay. Sau khi dọn, số dòng mọi bảng trở về như trước, chỉ còn các dòng `audit_log` và `mcp_query_log` ghi lại thao tác test.
- **Dọn dữ liệu test trên c2:** xoá nguồn qua `DELETE /api/sources/{id}` thì xoá được nguồn, 447 trang trùng, Điều/Khoản, embedding và object MinIO. Một số thay đổi do lần test vẫn còn nên đã sửa tay:
  - 149 trang PC08 đã có từ trước bị biên dịch lại khi nạp nguồn test. Các trang này giữ nội dung mới, có thêm một revision và tiêu đề bị đổi chữ hoa/thường. Đã trả về revision trước và lấy lại tiêu đề từ bản gốc.
  - 6 trang `_index`/`_log` mới tạo cho PV01/PA08/PC06: đã xoá.
  - `_index`/`_log` của PC08 và trang `_index` global bị cập nhật: đã chép lại từ bản gốc.

  Sau khi dọn, 216 trang của c2 khớp từng trang với bản gốc (md5 nội dung, tiêu đề và version), và API khớp lại 44/44.
- **Ghi chú:** xoá nguồn trên c2 chưa trả các trang dùng chung về trạng thái trước khi nạp: không hoàn tác lần biên dịch lại và không xoá `_index`/`_log` của scope mới. Bản gốc cũng để lại `_index`/`_log`, nên đây không phải lệch so với bản gốc.
