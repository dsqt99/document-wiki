# Wiki release integration

Mục tiêu: đưa các bản sửa Wiki đã triển khai/nghiệm thu vào `release/cahy`, giữ cập nhật reranker mới nhất và không sửa các checkout cũ đang có công việc riêng.

- [x] Fetch và đối chiếu `origin/release/cahy` (`838bdc9`), nhánh kiểm định và ba worktree.
- [x] Tạo nhánh tích hợp riêng từ release, merge hai commit thiết kế báo cáo còn thiếu.
- [x] Ghép mã/test/UI/KN2–KN7 của đợt sửa đã nghiệm thu; giữ reference cùng skill.
- [x] Đối chiếu toàn bộ mã Python trong image API. Giữ clearance và queue; giữ `admin_rerank.py`/`reranker_service.py` mới hơn của release. Review phát hiện rewrite sau xóa nguồn chưa giữ an toàn quyền đọc: thay bằng chặn HTTP 409 trước mọi side effect khi nguồn đang được trang dùng chung tham chiếu; không đưa worker rewrite chưa an toàn vào release.
- [x] Review và xử lý mọi lỗi chặn merge (hai lỗi quyền đọc có hồi quy RED/GREEN, review lại đạt).
- [x] Chạy pytest (882 đạt, 30 bỏ qua), frontend tests (39 đạt) và Docker production build backend/frontend trên bản tích hợp.
- [x] Commit theo nhóm mã, skill và báo cáo; kiểm tra staged diff và dữ liệu nhạy cảm.
- [x] Merge vào `release/cahy` tại `577be89`; đã push atomic nhánh tích hợp và release lên origin, không force-push.

Không đưa nguyên cây thay đổi từ worktree cũ vào release: 97 file ở checkout bàn giao đã khớp release, nhiều file khác là phiên bản cũ hơn hoặc tính năng độc lập chưa nghiệm thu (ví dụ quản trị prompt). Không xóa/reset/stash các cây đó. Các snapshot runtime, token phiên, log audit thô, cache, dependency và font binary không nằm trong commit.

Phạm vi tích hợp là source Wiki. Các thay đổi Chat/Terminal vẫn thuộc repository Chat; bằng chứng kiểm định qua Chat được lưu trong tài liệu Wiki, không thay thế việc commit repository Chat riêng.
