# Sửa prompt tóm tắt Word — nghiệm thu ngày 24/10/2026

Hai lỗi mục tiêu đã được sửa và nghiệm thu trên Qwen/Qwen3.5-9B: mã đối chiếu không còn bị đưa vào số văn bản; tài liệu thử nghiệm thông thường không còn bị thêm nhánh pháp luật. Hai lượt đọc nguồn → tóm tắt → tạo và tải Word đều đạt kiểm tra nội dung. Bộ kiểm tra nguồn, schema và điều kiện xuất tệp vẫn hoạt động.

## Thay đổi đã áp dụng

- Prompt KN2 phân biệt số của chính văn bản với mã đối chiếu/hồ sơ/kiểm thử, UUID, tên tệp và số văn bản được viện dẫn. Mã đối chiếu giữ nguyên trong nội dung tóm tắt.
- Số, ngày, cơ quan không có trong nguồn dùng `null`; khi xuất Word hiển thị “Chưa có thông tin”.
- Chỉ thêm `qppl` khi chính tài liệu là văn bản quy phạm pháp luật. Báo cáo viện dẫn một luật vẫn là báo cáo; tài liệu thường bỏ hẳn khóa này.
- Thêm ba ví dụ JSON đối chiếu đầy đủ: văn bản pháp luật, báo cáo viện dẫn luật và ghi chú chỉ có mã đối chiếu. Giữ nguyên schema và các kiểm tra trước xuất.

Đã phát hành qua cơ chế quản trị skill và đồng bộ có chữ ký sang Chat: `cahy-kn2-tom-tat` **version 5**, hash `0fd1f6cb2f896b74319199f774a15c73525af6c51aac49ff00437c1027d69bc0`. Nội dung đồng bộ khớp prompt đã kiểm thử sau chuẩn hóa xuống dòng. Bằng chứng: [publish.json](publish.json), [sync.json](sync.json).

## Phép đo và kết quả

| Phép kiểm tra | Kết quả | Bằng chứng |
|---|---|---|
| Phát lại yêu cầu lỗi bằng prompt cũ | Tái hiện nhầm mã đối chiếu và thêm nhánh pháp luật | [Baseline](probe/baseline-results.json) |
| Prompt mới trên bốn tình huống giả lập | 4/4 đạt schema và các điều kiện mục tiêu về số/ngày/cơ quan, nhánh pháp luật, mã đối chiếu và kết thúc bình thường | [Kết quả probe](probe/candidate-v2-results.json) |
| Kiểm thử schema, ví dụ prompt và đồng bộ Wiki | 15 đạt, 0 lỗi | [JUnit](../summary-prompt-tests.xml) |
| Hồi quy backend trực tiếp trên mã trong image v12 | 272 đạt, 0 lỗi | [JUnit v12](composite-v12-tests.xml) |
| Tóm tắt nguồn ra Word — lượt 1 | Đạt, 51,987 giây; tải DOCX 37.148 byte | [Kiểm tra tệp](live-run1/artifact-verification.json), [Word](live-run1/qa-summary.docx) |
| Tóm tắt nguồn ra Word — lượt 2, image cuối v12 | Đạt, 27,963 giây; tải DOCX 37.150 byte | [Kiểm tra tệp](live-run2/artifact-verification.json), [Word](live-run2/qa-summary.docx) |

Bốn tình huống probe gồm yêu cầu lỗi gốc, mã hồ sơ chưa có trong ví dụ, báo cáo có số/ngày/cơ quan nhưng viện dẫn luật và văn bản pháp luật có danh tính riêng. Đây là phép kiểm tra có chủ đích cho lỗi đang sửa, không phải ước lượng độ chính xác toàn hệ thống. Một đầu ra probe vẫn diễn giải chuỗi `261023` thành ngày trong trích yếu dù trường ngày ban hành là `null`; các điều kiện probe chưa đo đầy đủ mọi suy diễn trong văn xuôi. Hai tệp Word nghiệm thu bên trên không có diễn giải ngày này. Cần tiếp tục rà soát bản dự thảo khi dùng với tài liệu nghiệp vụ.

## Đối chiếu hai tệp Word thật

Nguồn giả lập: `qa-upload-261023.txt`, ID `041d3b9c-bb3b-42b4-b82d-a6ff69a34c24`. Nội dung chỉ có tiêu đề nghiệm thu, mô tả dữ liệu giả lập và mã đối chiếu. Không cung cấp số văn bản, ngày hoặc cơ quan ban hành.

Cả hai lượt đều:

- Tìm và đọc bản gốc qua `get_source_pages`; hash nguồn khớp `bc0950d3269b1ada609c5468ac4f4312e7942d0ba6921d4b437658521711d34c`.
- Giữ nguyên `QA-UPLOAD-261023-321d948` trong ý chính.
- Hiển thị cả ba ô số, ngày và cơ quan là “Chưa có thông tin”.
- Không có nhánh/mục pháp luật tự thêm; có mục nguồn tài liệu và đúng ID nguồn.
- Dùng skill version 5; không có `validation_errors`, không cần nút phục hồi JSON trong luồng thực thi.
- Tải qua API artifact có xác thực, mở được cấu trúc ZIP và XML của DOCX; kiểm tra trực tiếp toàn bộ văn bản trong tệp.

Lượt 2: chat `5d5bb2d2-5058-44f5-8446-3cde9bf4cb44`, artifact `26c032b3-61e6-48a1-904d-56eeb994de53`. SHA-256 DOCX: `21aa5f2cedb8db0e80f6aaf9eab58c400ad288be48db18e931df5db2250188ad`.

## Bản đang chạy

Chat: `cahy-chatbot:summary-prompt-261024-v12`, healthy khi chốt kiểm tra. Image kế thừa `doc-draft-checks-261024-v3`, giữ thay đổi draft của phiên triển khai khác, đồng thời khôi phục các kiểm tra ngữ nghĩa/nguồn và xử lý lỗi tra cứu đã được nghiệm thu trước đó. Bốn file phủ trong image đang chạy khớp 4/4 SHA-256 với bản build: [runtime-verification.json](runtime-verification.json).

Không đổi model, quyền tài khoản hay schema để làm ca kiểm tra đạt. Kết quả này chốt hai lỗi mục tiêu và luồng Word trên nguồn thử nghiệm; không chứng nhận mọi tài liệu dài/OCR hoặc mọi lần sinh của model đều đúng.
