# Wiki release — 24/10/2026

## Nội dung tích hợp

Base: `origin/release/cahy` tại `838bdc9`. Hai commit thiết kế kiểm định còn thiếu đã được merge từ `feature/wiki-quality-report-261023`.

- Giới hạn output LLM mặc định; đóng HTTP stream khi hủy; từ chối nội dung bị cắt bởi token limit; merge trang lớn dùng fallback giữ cả hai nội dung.
- Rerank thấp điểm chỉ phục hồi trên ứng viên đã được lọc quyền và có đối chiếu từ khóa/mã định danh; trả cảnh báo rõ ràng. Giữ nguyên cập nhật cấu hình reranker mới hơn của release.
- UI theo quyền tải lên, trạng thái thân thiện, nhãn “Cá nhân”; phiên SSO nhúng yêu cầu host xử lý đăng nhập.
- KN2 giữ metadata chưa biết là `null`, không đổi mã đối chiếu thành số văn bản, không tự thêm nhánh pháp luật. KN3/KN7 có reference Nghị định 30 và quy tắc dự thảo đã nghiệm thu.
- Bổ sung `clearance_level` vào phản hồi đăng nhập và source job API đã lọc quyền.

## Hai lỗi phát hiện thêm khi review

1. Xóa một nguồn của trang nhiều nguồn làm mất ràng buộc ACL trước khi nội dung cũ được loại bỏ. Bản release **trả HTTP 409 trước mọi side effect** nếu nguồn còn được trang dùng chung tham chiếu, gồm cả trang extracted. Cần xử lý các trang dùng chung trước khi xóa nguồn. Luồng rewrite bất đồng bộ chưa giữ an toàn nội dung/quyền đọc không được đưa vào release.
2. Job metadata từ Redis có thể tiết lộ tên tài liệu/trang khi nguồn đã bị bộ lọc quyền loại bỏ. Bản release bỏ hẳn các job này; job không chứng minh được nguồn đọc chỉ hiển thị khi endpoint xác nhận admin.

Hồi quy: 2 ca DELETE và 2 ca job leak đã được quan sát thất bại trước sửa; cả bộ 7 ca mới đạt sau sửa và được review độc lập lại.

## Kiểm chứng bản tích hợp

| Kiểm tra | Kết quả |
|---|---:|
| Toàn bộ pytest Wiki | 882 đạt, 30 bỏ qua, 0 lỗi |
| Node frontend tests | 39 đạt, 0 lỗi |
| Docker production build frontend | Đạt; TypeScript và sinh trang hoàn tất |
| Docker production build backend | Đạt; import router, worker, provider và job service trong image đạt, network bị tắt |
| Review độc lập | Không còn Critical/Important trong phạm vi tích hợp |
| Soát mẫu khóa/token trong bằng chứng đã chọn | Không phát hiện |

JUnit Wiki: [pytest.xml](pytest.xml). Các ca bị bỏ qua không được tính là đã nghiệm thu. Đây là kiểm thử của bản source tích hợp; không thay thế nghiệm thu LLM, OCR hay tài liệu vận hành đại diện.

Image dùng kiểm build: `cahy-wiki-backend:release-check-261024`, `cahy-wiki-frontend:release-check-261024`. Image được build để kiểm chứng, chưa dùng để thay container vận hành trong lượt merge này.

## Bằng chứng bàn giao

- [Report phép đo](../accuracy-20261023/VALIDATION.md), [HTML độc lập](../accuracy-20261023/wiki-accuracy-report.html), Word/PDF trong thư mục `handover/`.
- [Nghiệm thu tóm tắt Word](../wiki-e2e-20261023/prompt-summary-20261024/RESULTS.md): hai lượt thực tế giữ đúng mã đối chiếu và metadata thiếu.
- [Nghiệm thu KN3/KN7 và Word theo NĐ30](../nd30-20261024/RESULTS.md): hai ca Chat cuối và tệp Word tải/render thực tế.
- [Manifest hash các bằng chứng đã đưa vào Git](evidence-manifest.json).

Không commit raw audit log, token phiên, cache, bộ dependency, bản sao toàn bộ code runtime hoặc font binary. Các worktree cũ được giữ nguyên; các thay đổi cũ trùng release và các tính năng độc lập chưa nghiệm thu không được chép đè vào bản tích hợp. Repository Chat/Terminal được quản lý riêng, không nằm trong lượt push Wiki này.
