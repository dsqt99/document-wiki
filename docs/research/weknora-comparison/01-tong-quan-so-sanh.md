# 01 · Tổng quan so sánh

## 1. Hai triết lý

| | **WeKnora (Tencent)** | **Arkon** |
|---|---|---|
| Mô hình | RAG platform: tài liệu → chunk → vector/BM25 → chat pipeline hoặc agent ReAct | LLM-wiki: tài liệu → MAP/REDUCE → plan → viết trang wiki → người duyệt → MCP cho Claude |
| Đơn vị tri thức | Chunk (512 ký tự mặc định) | Trang wiki (khái niệm), chunk wiki, chunk verbatim |
| Người trong vòng lặp | Không | Duyệt plan (Phase 2.5), draft, branch, AI pre-review 4 lớp |
| Trả lời câu hỏi | Server-side (pipeline `rag_stream`, agent ReAct) | Không có server-side; giao cho MCP client |
| Stack | Go + docreader Python (gRPC) + asynq/Redis + ParadeDB + Neo4j (tuỳ chọn) + MinIO/S3/COS… | FastAPI + arq/Redis + pgvector (+ Milvus chỉ ghi) + MinIO + Next.js 16 |
| Frontend | Vue, có chat, quản lý chunk, gallery ảnh, wiki | Next.js, có wiki/graph/review/skills; **không có chat** |
| Quy mô code | Rất lớn (`knowledge_process.go` ~4.6k dòng) | Vừa phải |

Hai sản phẩm **không thay thế nhau**. Arkon phù hợp hơn cho dữ liệu nghiệp vụ cần kiểm duyệt (ngành công an); WeKnora là kho kỹ thuật để học.

## 2. Ma trận so sánh

Ký hiệu: ✅ tốt · 🟡 có nhưng yếu · ❌ không có

| Hạng mục | WeKnora | Arkon | Ghi chú |
|---|---|---|---|
| **Đầu vào** | | | |
| PDF có chữ: heading, thứ tự đọc | ✅ pypdfium2 + XY-cut + đoán heading theo cỡ chữ | ❌ `page.get_text()` thô | Arkon mất outline nên chunk bằng cửa sổ trượt |
| PDF: bảng | 🟡 builtin không có; MinerU/PaddleOCR-VL có | ❌ | |
| Engine parser cắm thêm | ✅ builtin / simple / anydoc / mineru / paddleocr_vl / weknoracloud | ❌ cố định | |
| Nhận diện trang scan | ✅ theo tỷ lệ diện tích ảnh (0.5) + <10 ký tự | 🟡 chỉ khi trang rỗng hoàn toàn | |
| OCR | ✅ VLM, prompt riêng cho scan, chunk `image_ocr` riêng | 🟡 GLM-OCR + dự phòng vision, không kiểm chất lượng | |
| DOCX | ✅ MarkItDown → python-docx, điền ô gộp | ❌ `mammoth.extract_raw_text` | |
| DOC | ✅ LibreOffice → antiword | ❌ từ chối | |
| PPTX | ✅ MarkItDown + media slide | 🟡 content-core, không lấy ảnh | |
| Excel/CSV | ✅ dòng `cột: giá trị`, tóm tắt bảng/cột, DuckDB | 🟡 `to_markdown` cả sheet | |
| Ảnh nhúng | ✅ PDF/DOCX/PPTX, lọc icon | 🟡 PDF/DOCX | |
| URL | ✅ Playwright + trafilatura, chống SSRF | 🟡 dự phòng lưu HTML thô | |
| Âm thanh | ✅ ASR | ❌ | Không ưu tiên |
| Chống trùng file | ✅ | ❌ | |
| **Chunking** | | | |
| Theo heading + breadcrumb | ✅ (strategy `auto`/`heading`) | 🟡 chỉ khi có `#` heading | |
| Không cắt ngang bảng/code/công thức | ✅ | ❌ | |
| Lặp header bảng trong mỗi chunk | ✅ | ❌ | |
| Parent-child | ✅ 4096/384 | ❌ | |
| Sinh câu hỏi cho chunk | ✅ | ❌ | |
| Tóm tắt tài liệu | ✅ | 🟡 (wiki thay thế) | |
| **Graph** | | | |
| Trích thực thể/quan hệ | 🟡 LLM mỗi chunk | 🟡 trích nhưng **bỏ đi** | |
| Gộp thực thể | ❌ | ✅ exact → cosine → LLM | Arkon hơn |
| Lưu trữ | Neo4j (tắt mặc định) | bảng `wiki_links` | |
| Dùng khi truy vấn | 🟡 1-hop, `CONTAINS` | ❌ | |
| **Truy xuất** | | | |
| Hybrid vector + BM25 + RRF | ✅ (ParadeDB BM25) | ✅ (tsvector `simple` + unaccent) | Arkon thiếu tách từ tiếng Việt |
| Rerank + MMR | ✅ | ❌ | |
| Query rewrite / intent | ✅ | ❌ | |
| Mở rộng query khi recall thấp | ✅ | ❌ | |
| Agent ReAct + tools | ✅ | ❌ (Claude làm qua MCP) | |
| Web search | ✅ 14 provider | ❌ | Không cần cho dữ liệu nội bộ |
| **Quản trị tri thức** | | | |
| Duyệt nội dung trước khi public | ❌ | ✅ | Arkon hơn |
| Version/revision/rollback | ❌ | ✅ | Arkon hơn |
| Branch/merge/rebase | ❌ | ✅ | Arkon hơn |
| Xử lý văn bản pháp luật | ❌ | 🟡 tách Điều, metadata | Arkon hơn, nhưng cần sâu thêm |
| Trích dẫn | 🟡 wiki có citation | 🟡 chỉ cấp trang | |
| **Vận hành** | | | |
| Trạng thái + retry + sweep | ✅ + dead-letter | ✅ sweep, 🟡 retry | |
| Chạy tiếp theo chunk | 🟡 | ✅ MAP lưu từng chunk | Arkon hơn |
| Chặn chi phí LLM | ❌ | ✅ ngưỡng 200k token | Arkon hơn |
| Trace theo bước | ✅ span + Langfuse | 🟡 trace_context | |
| Đánh giá (eval) | 🟡 BLEU/ROUGE/MRR/NDCG | ❌ | |
| Connector (Notion, Feishu…) | ✅ | ❌ | Không ưu tiên |
| Test | có `tests/` | ❌ | |
| **Phân quyền** | | | |
| Multi-tenant / RBAC | ✅ tenant, org, OIDC | ✅ phòng ban, role, token MCP theo knowledge type | Tương đương, mục tiêu khác nhau |

## 3. Arkon nên GIỮ (lợi thế thật)

1. **Người duyệt trong vòng lặp**: plan review, draft có kiểm `base_version`, branch/rebase, revision/rollback. Đây là yêu cầu cốt lõi với dữ liệu ngành.
2. **Kiểm soát chi phí**: tài liệu lớn phải duyệt; tài liệu luật đi đường verbatim không tốn LLM. WeKnora gọi LLM cho từng chunk ở 5 bước (graph, câu hỏi, caption, tóm tắt, wiki).
3. **Chạy tiếp được**: `source_chunk_extracts` lưu kết quả MAP theo chunk.
4. **Gộp khái niệm** (reducer): tốt hơn WeKnora, là nền cho graph.
5. **MCP theo token + knowledge type + log truy vấn**.
6. **Codebase gọn**, dễ tuỳ biến.

## 4. Arkon nên HỌC từ WeKnora

1. Lớp parser nhiều engine, chọn theo loại file / knowledge type.
2. Nhận diện trang scan theo diện tích ảnh; OCR tạo chunk riêng có liên kết.
3. Chunker bảo vệ bảng/code, lặp header bảng, breadcrumb heading.
4. Excel: dòng `cột: giá trị`, tóm tắt bảng, truy vấn DuckDB.
5. Parent-child retrieval.
6. Rerank + MMR + query rewrite + mở rộng query.
7. Sinh câu hỏi cho chunk.
8. Idempotency theo "lần parse" (task bị thay thế thì bỏ), dead-letter queue, span theo bước.
9. Bộ đánh giá truy xuất.

## 5. KHÔNG nên copy

- Graph Neo4j của WeKnora (nông, không gộp thực thể, tắt mặc định) → tự xây trên Postgres, xem [03](03-knowledge-graph.md).
- Chunk 512 ký tự mặc định: quá nhỏ với văn bản tiếng Việt dài.
- Gọi LLM cho mọi chunk ở mọi bước.
- 14 web search provider, IM bot, connector Trung Quốc: không phù hợp.
- Độ phức tạp của file 4.6k dòng.
