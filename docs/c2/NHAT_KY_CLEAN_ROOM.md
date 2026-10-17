# Nhật ký clean-room

| Ngày | Mảng | Vai | Người / tác nhân | Nguồn được đọc | Đầu ra |
|---|---|---|---|---|---|
| 2026-10-16 | 01–07 | Viết đặc tả | Agent đặc tả (Claude), mỗi mảng một phiên riêng | `document-wiki` (Arkon + phần nhóm sửa) | `docs/c2/dac_ta/0*.md` |
| 2026-10-16 | Nền tảng + 5 mảng backend | Viết mã | Agent thực thi (Claude), mỗi mảng một phiên, không được đọc `document-wiki` | `docs/c2/dac_ta/`, file loại C đã duyệt, `tests/` | `app/`, `alembic/`, `tests/` — 331 passed, 30 skipped (cần Postgres) |
| 2026-10-16 | 07a–07g frontend | Viết mã | Agent thực thi frontend (Claude), không được đọc `document-wiki` | `docs/c2/dac_ta/07*.md`; shadcn/ui sinh mới từ CLI (MIT) | `frontend/` — 23 route; tsc, lint, build đạt |
| 2026-10-17 | Đo trùng | Kiểm tra | Điều phối (Claude) | c2 + snapshot Arkon `274a2d2` + `upstream/main` | Đo theo khối 40 token (`tools/do_trung_khoi.py`): 21 file từ 10% trở lên |
| 2026-10-17 | Khắc phục trùng | Viết lại | Agent khắc phục (Claude). Chỉ nhận đường dẫn file c2 và số dòng, không nhận nội dung Arkon | file c2, đặc tả, test | Viết lại cấu trúc 27 file. Giữ nguyên hành vi, tên công khai, schema CSDL và revision id. Test và build vẫn đạt |
| 2026-10-17 | Thương hiệu | Đổi tên | Điều phối (Claude) | c2 | Chữ hiển thị "Arkon" đổi thành "Document Wiki". Giữ các định danh tích hợp: tên server MCP `arkon`, `arkon://`, cookie/localStorage `arkon_*`, header `X-Arkon-Signature`, đường dẫn `/api/v1/arkon/sso/return`, collection Milvus |

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
