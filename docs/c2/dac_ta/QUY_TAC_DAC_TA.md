# Quy tắc viết đặc tả clean-room

Người viết đặc tả được đọc mã nguồn `document-wiki` (Arkon và phần nhóm sửa). Người viết code **chỉ** đọc thư mục `docs/c2/dac_ta/`, các file loại C có sẵn trong c2, và `tests/`.

## Được phép ghi

- **API:** method, đường dẫn, tham số, tên và kiểu trường JSON, giá trị mặc định, mã trạng thái, thông báo lỗi.
- **Lược đồ dữ liệu:** tên bảng và cột, kiểu, khóa, ràng buộc, index, giá trị enum, ở dạng bảng Markdown.
- **Cấu hình:** tên biến môi trường và tên khóa cấu hình.
- **Thuật toán, luồng xử lý, trạng thái và quy tắc nghiệp vụ**, viết bằng lời: từng bước, điều kiện, ngưỡng số.
- **UI:** bố cục từng màn, thành phần, nhãn hiển thị (lấy theo khóa i18n trong `frontend/src/lib/i18n.tsx`, file loại C), hành vi tương tác.
- **Tên hàm, lớp và module** mà file loại C hoặc test đang import, kèm chữ ký (tham số, kiểu trả về) và hành vi.

## Không được ghi

- Đoạn code Python, TS, TSX, SQL, CSS dưới bất kỳ hình thức nào, kể cả "giả mã" bám sát code.
- Comment, docstring, regex hay prompt LLM chép nguyên văn. Với prompt, chỉ mô tả mục đích, đầu vào, đầu ra mong muốn và các ràng buộc.
- Cấu trúc nội bộ không cần cho hành vi: tên biến cục bộ, tên hàm private không bị test dùng, thứ tự khai báo.
