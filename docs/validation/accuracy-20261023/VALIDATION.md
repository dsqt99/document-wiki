# Kiểm định Wiki ngày 23/10/2026

Phạm vi theo yêu cầu cuối: tự kiểm tra bằng setting hiện tại và giao report, không triển khai CLI sản phẩm.

## Kết quả đã đối soát

- Trích xuất: 9/9 tệp hoàn thành, 12/12 đơn vị nội dung, 26/26 giá trị trọng yếu; 0 lỗi ký tự/1.566 ký tự và 0 lỗi từ/314 từ sau chuẩn hóa đã mô tả.
- OCR: 3/4 ảnh hoàn thành; 5 lỗi ký tự/444 ký tự, 4 lỗi từ/81 từ; 14/15 giá trị trọng yếu. Ảnh mờ đổi dấu và dấu phân cách số tiền. Ảnh trắng vượt giới hạn QA 100 giây, chưa có output để chấm.
- Embedding trên corpus mẫu độc lập: top 1 đạt 7/8, top 3 đạt 8/8.
- Rerank xếp target đầu ở 8/8 câu trước lọc, nhưng ngưỡng >0,7 giữ 6/8. Thử ngưỡng chỉ trong RAM; 0,3 và 0,5 cũng chỉ giữ 6/8 trên bộ điểm quan sát.
- Service/index thật, READ ONLY, scope global: 7/7 target định trước ở hạng 1; một mã không tồn tại trả 0 kết quả. Không phải nghiệm thu API/SSO/ACL hoặc gán nhãn relevance toàn corpus.

## Bằng chứng và xác minh

Manifest và fixtures được tạo trước khi đo, có hash trong reviewed-results.json. Bản lưu release gồm manifest, fixtures, kết quả đã chấm, bảng CSV và report độc lập; log/provider response thô được giữ tại workspace nghiệm thu, không đưa vào Git. reviewed-results.json là bản kết quả đã chấm; trường as_of của nó đánh dấu thời điểm ca extract/OCR cuối, không phải thời điểm kết thúc tất cả phép đo bổ sung. Report ghi khoảng thời gian tổng thể 21:51–21:56 Asia/Bangkok.

Đã đối chiếu lỗi OCR với output thô, mẫu số, hạng target và bộ lọc. Report build thành công với runtime được xác minh. Đã xem giao diện thường và chiều rộng 390 px: không tràn ngang toàn trang; bảng cuộn bên trong. Phân trang đã hiển thị mixed.pdf: 2/2 đơn vị, CER/WER 0, thời gian 4,13 giây. Đã xuất HTML độc lập.

Không sửa cấu hình lưu, dữ liệu nguồn, index hoặc quyền tài khoản. Chưa kiểm tra file 200 MB, scan vận hành đại diện, định dạng DOC/XLS cũ, độ phủ lịch sử, câu trả lời AI, hiệu lực pháp luật hoặc export của chat agent. Mẫu nhỏ dùng chẩn đoán, không suy rộng thành độ chính xác toàn hệ thống.

## Tệp giao

- wiki-accuracy-report.html: bản report HTML độc lập.
- handover/Bao_cao_phep_do_Wiki_20261023.docx và .pdf: bản phép đo để gắn vào tài liệu bàn giao. Bản build tương tác và cache của môi trường QA không thuộc source release.
- reviewed-results.json và các CSV: bằng chứng số liệu.
