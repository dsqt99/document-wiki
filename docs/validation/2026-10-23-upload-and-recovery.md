# Upload clearance và retry riêng nhánh Wiki

Đã triển khai API image `cahy-wiki-backend:upload-scope-261023-cb617a4`, giữ worker hiện có và toàn bộ override trước đó. Mã sửa ở các commit `170efe1`, `cb617a4`; test multipart/URL bổ sung tại `ba58257`.

Kiểm thử chọn lọc: **91 passed** (security label, multipart/URL, upload guard/dedup, retry, MCP và legal scope). Chat có bằng chứng **6 ca upload API thật qua**, **8 ca đọc MCP khi INTERNAL qua**, **7 ca chặn đọc PUBLIC qua sau hoàn nguyên quyền** tại worktree Chat `docs/test-results/2026-10-23-pa08-acceptance/`.

Người dùng đã cho phép đổi DB tài khoản test. Đã chụp quyền ban đầu, cấp INTERNAL và contributor chỉ PA08 trong thời gian test, sau đó hoàn nguyên PUBLIC/viewer, gỡ role tạm khỏi tài khoản lẫn định nghĩa. Không thay Keycloak/role canonical hoặc cấp quản trị/toàn hệ thống. Kiểm tra proxy `/auth/me` sau hoàn nguyên không có `doc:create`.

`retry_verified_failed_sources.py` đã chạy một lần cho đúng ba nguồn lỗi được kiểm tra. Mỗi lần enqueue khóa hàng, kiểm tra lại trạng thái và queue, giữ nguyên raw text và nhánh chunk đã ready. Journal `2026-10-23-selective-recovery.json` ghi job ID ngay sau enqueue; không có assertion chống thay đổi trang sau enqueue vì worker có thể cập nhật ngay.

`snapshot_selective_recovery.py` chỉ đọc. Snapshot `2026-10-23-recovery-current.json` lúc 14:00 UTC:

| Nguồn | Trạng thái | Bản nháp / dự kiến |
|---|---|---|
| d6de6e95… | job đang chạy, lease sống, phase verify | 73 / 74 |
| b1372cdc… | queued | 79 / 79 |
| 440a3202… | queued | 5 / 58 |
| ec027731… | nguồn vốn đang chạy, refine | 79 / 106 |

Chưa coi retry là thành công: cần kiểm tra publication, slugs và search sau khi job kết thúc. Không enqueue trùng hoặc reset nguồn đang chạy. `041d3b9c…` là nguồn QA giả lập PUBLIC/personal, 167 bytes, đang chờ ingest; không chứa tài liệu nghiệp vụ.

Chưa merge release. Chat thực tế vẫn timeout router 60 giây ở câu hỏi từ nguồn và xuất Word. Chưa có artifact tải xuống hoặc bằng chứng câu trả lời AI kèm nguồn. Bản ghi triển khai chỉ là snapshot; trước rollout mới phải đối chiếu image và Compose chain hiện tại. Dockerfile patch cần `RUNTIME_BASE` rõ ràng và kiểm tra hash các hàm trước khi sửa runtime.
