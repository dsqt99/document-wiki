# Nghiên cứu so sánh: Arkon vs Tencent WeKnora

> Ngày: 2026-09-25 · Phiên bản WeKnora khảo sát: v0.8.2 (`temp_uploads/WeKnora`)
> Phương pháp: đọc mã nguồn cả hai repo (không chạy thử). Các mục đánh dấu **[Đã xác nhận]** đã được kiểm tra trực tiếp trong code; còn lại là kết quả đọc code, cần kiểm lại trước khi sửa.

## Mục lục

| File | Nội dung | Dùng khi |
|---|---|---|
| [01-tong-quan-so-sanh.md](01-tong-quan-so-sanh.md) | Triết lý hai sản phẩm, ma trận so sánh đầy đủ, điểm mạnh 2 chiều | Định hướng chung, trình bày với team |
| [02-xu-ly-tai-lieu-dau-vao.md](02-xu-ly-tai-lieu-dau-vao.md) | PDF, OCR, DOCX, DOC, Excel/CSV, ảnh, URL, chống trùng, chuẩn hoá Unicode | Triển khai lớp parser |
| [03-knowledge-graph.md](03-knowledge-graph.md) | Graph của 2 bên, thiết kế graph cho Arkon (quan hệ khái niệm + graph pháp luật) | Thiết kế graph |
| [04-phap-luat-va-truy-xuat.md](04-phap-luat-va-truy-xuat.md) | Tách cấp bậc Chương/Mục/Điều/Khoản/Điểm, hybrid search tiếng Việt, rerank, sinh câu hỏi, trích dẫn | Chất lượng trả lời |
| [05-bug-va-van-hanh.md](05-bug-va-van-hanh.md) | Bug P0/P1, bài học vận hành từ WeKnora (idempotency, dead-letter, span) | Sửa lỗi ngay |
| [06-lo-trinh-trien-khai.md](06-lo-trinh-trien-khai.md) | Backlog theo sprint, checklist, tiêu chí nghiệm thu, rủi ro | Lập kế hoạch |
| [07-ban-do-ma-nguon-weknora.md](07-ban-do-ma-nguon-weknora.md) | Bản đồ file WeKnora cần đọc theo từng chủ đề | Nghiên cứu sâu |

## Kết luận một đoạn

WeKnora là **nền tảng RAG tự động** (chunk → embed → truy xuất → chat/agent), mạnh ở **lớp đầu vào** (nhiều engine parser, OCR theo trang, bảng, Excel) và **lớp truy xuất** (hybrid + rerank + MMR + query rewrite + parent-child). Arkon là **LLM-wiki có người duyệt**, mạnh ở **quản trị tri thức** (duyệt plan, draft, branch, revision), **kiểm soát chi phí** và **gộp khái niệm**. Hướng đi: **giữ lõi wiki + duyệt của Arkon, học lớp parser và lớp truy xuất của WeKnora, tự xây graph pháp luật** (WeKnora không có thứ tương đương).

## 5 việc ưu tiên nhất

1. Sửa 3 bug đã xác nhận: treo pipeline khi thiếu vision provider, lộ phạm vi phòng ban ở trang luật, `retry_source` kiểm tra sai trạng thái → [05](05-bug-va-van-hanh.md).
2. Chuẩn hoá Unicode NFC + hash chống trùng file → [02 §7-8](02-xu-ly-tai-lieu-dau-vao.md).
3. PDF sang `pymupdf4llm`, DOCX sang markdown, nhận diện trang scan theo diện tích ảnh → [02 §1-3](02-xu-ly-tai-lieu-dau-vao.md).
4. Tách cấp bậc pháp luật đến Khoản/Điểm + parent-child retrieval → [04 §1](04-phap-luat-va-truy-xuat.md).
5. Thêm reranker hỗ trợ tiếng Việt → [04 §3](04-phap-luat-va-truy-xuat.md).
