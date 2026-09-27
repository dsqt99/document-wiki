# 06 · Lộ trình triển khai

Ước lượng tính cho 1 dev backend quen code. "d" = ngày công. Mỗi sprint 1 tuần.

## Sprint 0: Nền móng (2–3d)

Không có test và không có bộ đo thì mọi cải tiến phía sau đều không chứng minh được.

- [ ] Tạo `tests/` + `pytest` + fixture DB (có thể dùng testcontainers Postgres + pgvector).
- [ ] `tests/fixtures/docs/`: 15–20 tài liệu thật đã ẩn thông tin (xem [02 §10](02-xu-ly-tai-lieu-dau-vao.md)).
- [ ] `eval/questions.yaml`: 100 câu hỏi đầu tiên + đáp án kỳ vọng (Điều/Khoản/slug).
- [ ] Script `app/eval/retrieval.py` → Recall@5/10, MRR, nDCG@10. **Chạy baseline, lưu kết quả.**

**Nghiệm thu:** `pytest` chạy được; có file baseline eval.

## Sprint 1: Bug P0 + vệ sinh đầu vào (4–5d)

| Việc | Tham chiếu | Ước lượng |
|---|---|---|
| BUG-01 chain caption → MRP | [05](05-bug-va-van-hanh.md) | 0.5d |
| BUG-02 phạm vi phòng ban cho trang luật + rà soát dữ liệu | [05](05-bug-va-van-hanh.md) | 1d |
| BUG-03 `retry_source` | [05](05-bug-va-van-hanh.md) | 0.25d |
| BUG-04 slug theo số hiệu (kèm migration đổi slug cũ + redirect) | [04 §1](04-phap-luat-va-truy-xuat.md) | 1d |
| `normalize_text` (NFC…) cho parser + câu hỏi | [02 §7](02-xu-ly-tai-lieu-dau-vao.md) | 0.5d |
| `content_hash` + giới hạn upload + đọc theo stream | [02 §8](02-xu-ly-tai-lieu-dau-vao.md) | 1d |
| `attempt_id` chống pipeline chồng nhau | [05 · bài học 1](05-bug-va-van-hanh.md) | 1d |

**Nghiệm thu:** test cho từng bug; upload trùng bị phát hiện; không còn nguồn kẹt `processing` khi tắt vision.

## Sprint 2: Parser PDF/DOCX/DOC (5d)

| Việc | Ước lượng |
|---|---|
| Interface `ParserEngine` + registry, cột `parser_engine` trên `KnowledgeType` | 1d |
| Engine `builtin`: pymupdf4llm + heuristic heading tiếng Việt + bỏ header/footer lặp | 1.5d |
| Nhận diện trang scan (diện tích ảnh + chất lượng lớp chữ) + prompt OCR tiếng Việt + kiểm tra kết quả OCR | 1d |
| DOCX → markdown (mammoth markdown hoặc markitdown) + điền ô gộp | 0.5d |
| DOC/PPT/XLS cũ qua LibreOffice (Dockerfile + subprocess có timeout) | 0.5d |
| Chạy lại eval + fixture, so sánh outline trước/sau | 0.5d |

**Nghiệm thu:** ≥ 90% PDF văn bản luật trong fixture có outline không rỗng; eval Recall@10 không giảm.

**Rủi ro:** pymupdf4llm nhận heading tiếng Việt kém → cần heuristic regex Chương/Mục/Điều (đã tính trong 1.5d). Đổi parser làm thay đổi `full_text` của nguồn cũ → **không tự reparse** nguồn cũ; thêm nút "Phân tích lại" cho admin.

## Sprint 3: Cấp bậc pháp luật + graph pháp luật (5–6d)

| Việc | Ước lượng |
|---|---|
| Parser máy trạng thái Chương/Mục/Điều/Khoản/Điểm + vùng trích dẫn + phụ lục | 2d |
| Migration `legal_documents`, `legal_units`, `legal_relations` | 0.5d |
| Regex quan hệ (sửa đổi, thay thế, bãi bỏ, hướng dẫn, căn cứ, dẫn chiếu) + job nối lại quan hệ khi văn bản đích được upload | 1.5d |
| Banner "đã sửa đổi bởi…" trên trang Điều + tình trạng hiệu lực trên trang tổng quan | 0.5d |
| Chunk theo Khoản (parent-child), trả Điều cha khi tìm | 1d |
| MCP tool `get_legal_status`, `get_related` | 0.5d |

**Nghiệm thu:** bộ NĐ 136/2020 + NĐ 50/2024 cho đúng cạnh `sua_doi` theo từng Điều; eval câu hỏi pháp luật Recall@5 tăng so với baseline.

## Sprint 4: Chất lượng truy xuất (4–5d)

| Việc | Ước lượng |
|---|---|
| Rerank provider (bge-reranker-v2-m3 qua TEI/Infinity) + MMR + dự phòng | 1.5d |
| Tách từ tiếng Việt (pyvi) + 2 cột tsvector có dấu/bỏ dấu + migration reindex | 1.5d |
| Tuyến tra cứu chính xác theo số hiệu / "Điều N" | 0.5d |
| Mở rộng 1 bước qua graph trong `search_wiki` | 1d |
| Tắt Milvus mặc định | 0.25d |

**Nghiệm thu:** eval MRR, nDCG@10 tăng so với sau Sprint 3; độ trễ `search_wiki` p95 < 1.5s.

## Sprint 5: Excel + ảnh + sinh câu hỏi (5d)

| Việc | Ước lượng |
|---|---|
| Excel: header, ô gộp, chunk theo dòng, chunk tóm tắt bảng, đường "bảng dữ liệu" bỏ qua MRP | 2d |
| MCP `query_table` (DuckDB, chỉ SELECT, timeout, giới hạn dòng) | 1d |
| Chunk riêng cho ảnh (`image_ocr`/`image_caption`) + ảnh upload lẻ + PPTX qua python-pptx | 1d |
| Sinh câu hỏi cho chunk luật (hàng đợi riêng, ngưỡng token) | 1d |

## Sprint 6: Graph khái niệm + trích dẫn + vận hành (5d)

| Việc | Ước lượng |
|---|---|
| Sửa prompt MAP (predicate danh sách đóng + evidence) + `concept_relations` + ghi ở commit | 2d |
| `/wiki/graph` hiển thị cạnh có kiểu | 1d |
| Trích dẫn nhẹ `[^sN]` cho trang tổng hợp + verifier kiểm trích dẫn | 1d |
| Dead-letter table + trang admin, `source_stage_timings`, sweep `pending` | 1d |

## Tuỳ chọn / sau này

- Pipeline chat server-side + UI chat (nếu chatbot CAHY không chạy qua Claude/MCP): 2–3 tuần.
- Engine MinerU/docling cho tài liệu phức tạp (cần GPU): 3–5d.
- ACL 1 trang nhiều phòng ban thay cho nhân bản trang (BUG-13): thiết kế riêng.
- Dọn code chết, cập nhật `docs/ARCHITECTURE.md`: 1d, làm xen kẽ.

## Tổng quan

```
S0 nền móng ─► S1 bug+vệ sinh ─► S2 parser ─► S3 pháp luật+graph ─► S4 truy xuất ─► S5 excel/ảnh/câu hỏi ─► S6 graph KN+trích dẫn
   2-3d            4-5d             5d              5-6d                 4-5d               5d                     5d
```
Tổng khoảng 6–7 tuần cho 1 người. S2 và S3 có thể chạy song song nếu có 2 người (S3 chỉ phụ thuộc NFC ở S1).

## Nguyên tắc khi triển khai

1. **Đo trước khi sửa**: mọi thay đổi parser, chunk hay search phải chạy lại eval.
2. **Không tự reparse dữ liệu cũ**: thêm nút "Phân tích lại" có duyệt, vì reparse làm thay đổi trang wiki đã duyệt.
3. **Giữ tinh thần kiểm soát chi phí**: tính năng LLM mới (sinh câu hỏi, graph) chạy sau khi nguồn `ready`, có hàng đợi riêng và ngưỡng token.
4. **Bảo mật phạm vi trước tính năng**: BUG-02 phải xong trước khi đưa thêm văn bản nội bộ vào hệ thống.
