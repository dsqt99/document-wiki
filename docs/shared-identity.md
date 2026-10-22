# Danh tính và chính sách dùng chung

Chatbot quản lý tài khoản trên Keycloak và là nơi duy nhất chỉnh sửa cán bộ, đơn vị,
vai trò, quyền và mức tiếp cận. Các mục Cán bộ, Đơn vị và Ma trận phân quyền trong
cấu hình Kho tri thức dẫn tới các màn hình quản lý chung này.

Wiki nhận bản sao qua `POST /api/internal/org-sync`, dùng chữ ký và kiểm tra chống
phát lại hiện có. Kết nối và khóa đồng bộ lấy từ môi trường triển khai.

## Bản sao tài khoản

`directory_complete=true` đi kèm toàn bộ hồ sơ `accounts`, gồm người chưa đăng nhập,
người chưa có nhóm và tài khoản đang khóa. Bên gửi kiểm tra số lượng trước/sau khi
đọc toàn bộ danh sách. Wiki tạo/liên kết Employee bằng định danh nguồn, cập nhật tên,
email, trạng thái, vai trò và đơn vị. Xung đột với một định danh khác bị từ chối.

Danh sách cán bộ chỉ gồm định danh trong bản sao chung. Tài khoản cũ không bị xóa
vật lý vì còn liên kết tác giả/tài liệu; chúng không tạo thêm quyền truy cập độc lập.
Tài khoản khôi phục cục bộ được cấu hình sẵn vẫn giữ chức năng khôi phục.

Sự kiện tạo/đổi quyền/khóa/mở khóa/xóa cập nhật ngay bản sao. Đồng bộ đầy đủ định kỳ
sửa các sự kiện bị lỡ. Khi không đọc lại được nguồn, bên gửi hoãn cấp/mở quyền;
lệnh khóa vẫn được gửi và thu hồi mã MCP.

`observed_at` được ghi trước khi đọc trạng thái nguồn. Receiver dùng khóa giao dịch
PostgreSQL, phiên bản từng tài khoản, mốc bản sao đầy đủ và dấu xóa để từ chối dữ liệu
cũ đến muộn. Một sự kiện lẻ không được dùng để khởi tạo toàn bộ danh sách nguồn.

## Phạm vi và quyền

Quản trị toàn quyền thấy toàn bộ tài khoản. Quản trị theo đơn vị thấy cán bộ trong
các đơn vị được giao và đơn vị con. Lọc phạm vi diễn ra trước đếm, tìm kiếm và phân
trang; quản lý mã MCP cũng kiểm tra phạm vi và tài khoản quản trị đích.

`role_definitions` từ chatbot quyết định quyền hiệu lực. Vai trò kế thừa được đọc từ
Keycloak riêng với vai trò gán trực tiếp để không làm sai thao tác sửa vai trò.
Wiki ánh xạ quyền nghiệp vụ sang thao tác tài liệu, Wiki và kỹ năng; quyền quản trị
theo đơn vị không trở thành quyền toàn cục. Quyền cấp tay hoặc ma trận riêng của
Wiki không bổ sung quyền cho tài khoản dùng chung.

Mỗi yêu cầu phiên, token nguồn tệp và mã MCP đều nạp lại chính sách chung. API sửa
tài khoản, thành viên và ma trận riêng bị chặn ở chế độ đồng bộ. Duyệt/đóng/hợp nhất/
rebase nhánh kiểm tra từng bản nháp, kể cả nhánh cũ có dữ liệu trộn phạm vi.

Kiểm thử hồi quy: `tests/test_shared_identity.py` (cài nhóm phụ thuộc `dev`).
