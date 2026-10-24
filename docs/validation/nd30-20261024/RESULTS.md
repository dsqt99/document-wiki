# Nghiệm thu KN3 / KN7 và xuất Word theo Nghị định 30

Ngày kiểm tra: 24/10/2026 (UTC+7). Phạm vi: đối chiếu tài liệu người dùng cung cấp, cập nhật hướng dẫn soạn/kiểm tra thể thức và kiểm chứng công cụ xuất Word cho dự thảo hành chính thông thường, một khối ký.

## Nguồn đối chiếu

- Tệp: `D:/code/dsqt/conganhungyen/chatbot_cahy/final_ban_giao/data/30_2020_ND-CP_436532.pdf`.
- 82 trang ảnh, không có lớp văn bản; SHA-256: `83f02fd0cbe988622251cf54889b6051ebd99179eb2a4848a762dc887eb32634`.
- Đã đọc ảnh và dùng OCR nội bộ hỗ trợ, tập trung Điều 8–12, Phụ lục I (PDF 21–37), Phụ lục II (PDF 41–44), các mẫu Phụ lục III. OCR không thay thế ảnh gốc; các bảng/sơ đồ và trang OCR không đủ được đối chiếu trực tiếp.

## Thay đổi đã phát hành

KN3 và KN7 đều ở **v4, active**, đã đồng bộ qua luồng có chữ ký sang Chat. Nội dung skill và toàn bộ resource khớp sau chuẩn hóa xuống dòng; schema nghiệp vụ giữ nguyên. Bản v3 và ZIP ứng viên được lưu để đối chiếu.

- KN3: dùng reference thể thức riêng; xuất đúng hợp đồng `type: vanban`; không tự sinh ngày/năm ký, số văn bản, người ký, căn cứ hoặc dữ kiện còn thiếu. Thông tin chưa có giữ dấu `...`. Loại bỏ hướng dẫn gọi các lệnh không tồn tại.
- KN7: phân biệt dự thảo với văn bản đã ban hành; chỉ kiểm những gì đầu vào cho phép quan sát; không suy ra phông/lề từ văn bản thuần. Sửa quy tắc ngày dưới 10, tháng 1–2, cách viết tên cơ quan và các nhận định từng bị gán nhầm thành yêu cầu của Nghị định.
- Word: A4, lề trên/dưới 20 mm, trái 30 mm, phải 15 mm; Times New Roman thực; nội dung 14 pt, giãn dòng 1,15 và thụt đầu dòng 1,27 cm. Sửa bố cục số/ngày cùng hàng, bề rộng bảng, đường kẻ tiêu đề, Kính gửi nhiều nơi, Nơi nhận, khối ký và số trang đầu không hiển thị.
- Chat: chỉ quảng bá công cụ xuất ở bước đã được cấp quyền; phân biệt áp dụng chuẩn thể thức với tra cứu hiệu lực pháp lý. Local KN3 kết thúc đọc công cụ sau khi đã đọc thành công đúng reference NĐ30. Đọc schema trước, custom skill và ca cần nguồn/planner/worker vẫn được đọc công cụ. Giữ nguyên gate đánh giá, xác thực nguồn, quyền và điều kiện xuất.

## Kết quả kiểm thử

| Lớp kiểm chứng | Kết quả | Bằng chứng |
|---|---:|---|
| Backend: router, hợp đồng công cụ, xuất tệp, kiểm dữ kiện | 200/200 đạt trên image v20 | `backend-tests.xml` |
| DOCX: cấu trúc, cỡ chữ, lề, số trang, bố cục | 11/11 đạt | `layout-tests.xml` |
| Đồng bộ skill có chữ ký | 6/6 đạt | `skill-sync-tests.xml` |
| Qwen 9B, các tình huống mục tiêu | 6/6 và 1/1 bổ sung đạt | `candidate-probes.json`, `candidate-probes-metadata.json` |
| Render bộ mẫu Word | 4 tài liệu, tổng 6 trang đã kiểm ảnh | `rendered/render-results.json` và PNG |

Hai regression mới đã được chạy RED trên v18: đọc schema trước và custom draft bị đóng công cụ sớm. Sau bản sửa, toàn bộ 200 kiểm thử đạt trên image cuối. Review độc lập không còn blocker trong phạm vi đã chốt.

Các probe mục tiêu kiểm: không ép tháng 3 thành 03; không bác bỏ tên cơ quan chủ quản viết tắt hợp lệ; không coi “chúng tôi” là lỗi thể thức tự động; chấp nhận dấu trống trong dự thảo; phát hiện ngày 5 thành 05; giữ nguyên dữ kiện khi tạo Word; không báo lỗi thiếu thành phần đã có trong metadata. Đây là số ca mục tiêu, không phải phép ước lượng độ chính xác cho mọi văn bản.

## Triển khai và bảo toàn thay đổi

- Chat: `cahy-chatbot:nd30-flow-261024-v20`.
- Terminal: `cahy-open-terminal:nd30-261024-v4`.
- Chỉ ghép các vùng hàm/prompt liên quan vào nguồn runtime đã sao lưu; các sửa đổi có sẵn trong image chạy hiện tại được giữ lại. Hash và trạng thái cuối lưu trong `runtime-final.json`; bằng chứng ghép trong `backend-merge-proof.json` và `exporter-merge-proof.json`.
- Không đổi quyền tài khoản, model hoặc schema để đạt kiểm thử. Các ca thực tế chỉ tạo dữ liệu QA giả lập và tải tệp qua API Chat thông thường bằng phiên đã đăng nhập. Không lưu token trong báo cáo.

## Giới hạn

Phạm vi này kiểm chứng dự thảo hành chính thông thường, một khối ký. Biểu mẫu chuyên ngành, văn bản nhiều người ký, phụ lục có cách đánh số riêng và phát hành có chữ ký/con dấu cần mẫu và nghiệm thu tương ứng. KN7 vẫn cần người duyệt đối chiếu căn cứ chi tiết; ca phát hiện ngày đúng không chứng minh mọi trích dẫn tự sinh đều chính xác đến mục/điểm. Kiểm thể thức không xác nhận hiệu lực pháp lý hoặc thẩm quyền ban hành.

Không gộp các lượt nghiệm thu lỗi cũ vào kết quả đạt: thư mục `live`, `live-v16` và `live-audit.json` được giữ để truy vết; lượt cuối được ghi riêng bên dưới.

## Nghiệm thu Chat trên bản cuối v20

Hai yêu cầu dùng Qwen 9B và phiên đã đăng nhập, không bỏ qua các gate của hệ thống:

| Tình huống | Kết quả | Thời gian |
|---|---|---:|
| KN3 tạo báo cáo Word từ dữ kiện “đã kiểm tra 3 hồ sơ thử nghiệm”, để trống ngày/năm/số/người ký | Tạo, tải thành công; 9/9 kiểm nội dung/cấu trúc đạt | 42,588 giây |
| KN7 kiểm riêng dòng “ngày 5 tháng 02 năm 2026” | JSON hợp lệ; phát hiện `TT_DIA_DANH_NGAY_THANG`, đề xuất ngày `05` | 6,581 giây |

- Chat KN3: `20d38f93-ca16-436e-ab70-b8d150c723bc`; Chat KN7: `2eb2f516-4a0c-4c8e-8143-6accd04e5f97`.
- Bằng chứng phản hồi và kết quả: [live-results.json](live-final-v20/live-results.json).
- Tệp tải thực tế: [live-report.docx](live-final-v20/live-report.docx), 38.741 byte, SHA-256 `ead3777a0ce0dafde1ba45fdbe1d30461b4ae071af07851299a01a9c1dc1fa6e`.
- [Kiểm DOCX](live-final-v20/postflight.json): A4; lề 20/20/30/15 mm; thân bài 14 pt; giãn dòng 1,15; thụt 1,27 cm; bảng vừa vùng in; số trang trong đầu trang, trang đầu ẩn. Đã render chính tệp tải về và kiểm trực tiếp [ảnh trang 1](live-final-v20/page-1.png).
- Các trường chưa biết vẫn là dấu `...`; không tự thêm năm ký 2026, chức vụ Giám đốc, căn cứ pháp luật hay dữ kiện khác. Phản hồi hai ca không có lỗi xác thực nội dung.
- Chat v20 và Terminal v4 healthy; bốn tệp runtime khớp hash bản build, Times New Roman thực được xác nhận bằng `fc-match`.
