# 05 · Bug và vận hành

Ký hiệu: **[Đã xác nhận]** = đã mở code kiểm tra trực tiếp. **[Cần kiểm]** = kết quả đọc code, cần đọc lại hoặc tái hiện trước khi sửa.

## P0: sửa ngay

### BUG-01 · Nguồn có ảnh bị treo khi không có vision provider [Đã xác nhận]
- **Vị trí**: `app/worker.py`, `enqueue_post_extraction_pipeline` (dòng 56) và `caption_images_task` (dòng ~1202).
- **Cơ chế**: `enqueue_post_extraction_pipeline` chọn `caption_images_task` nếu `has_images`, nếu không thì chọn `ingest_map_reduce_task`. Bên trong `caption_images_task` có ba chỗ `return` sớm **không enqueue** `ingest_map_reduce_task`:
  - dòng ~1231: `if not source: return`
  - dòng ~1237: `if not vision_provider: ... return`
  - dòng ~1247: `if not image_records: return`
  
  Chỉ nhánh chạy hết (dòng ~1314) mới chain sang MAP-REDUCE.
- **Hậu quả**: nguồn kẹt ở `processing` → cron sweep chuyển sang `error` → người dùng retry → kẹt lại (vì `pipeline_phase` chưa sang `map`).
- **Sửa**: gom việc chain vào `finally`, hoặc tách hàm `_chain_to_mrp(source_id)` và gọi ở mọi nhánh trừ `not source`. Ngoài ra, ở `enqueue_post_extraction_pipeline`, kiểm vision provider trước khi chọn caption.
- **Test**: upload PDF có ảnh khi tắt vision → nguồn phải đi tiếp tới `plan_ready`.

### BUG-02 · Trang luật bỏ qua phạm vi phòng ban [Đã xác nhận]
- **Vị trí**: `app/services/legal_service.py:456`: `scope_type = source.scope_type or "global"`, rồi dùng cho `upsert_page`, `regenerate_index`, `append_log` (dòng 526, 575, 633, 638).
- **Cơ chế**: nhánh MRP gọi `_resolve_wiki_scopes` (`app/ai/mrp/pipeline.py:30`) để đọc `SourceDepartment`; nhánh luật thì không.
- **Hậu quả**: văn bản chỉ cấp cho một phòng ban vẫn thành trang wiki `global`, **ai cũng đọc được** qua wiki và MCP. Với ngành công an, đây là lỗi bảo mật.
- **Sửa**: dùng chung `_resolve_wiki_scopes` cho nhánh luật. Nên cân nhắc: văn bản luật công khai (luật, nghị định) để global; văn bản nội bộ (chỉ thị, kế hoạch) theo phòng ban.
- **Test**: upload văn bản luật gán 1 phòng ban → user phòng khác không thấy (qua API wiki và `search_wiki` MCP).
- **Rà soát dữ liệu**: chạy query tìm trang luật đang `global` nhưng source có `SourceDepartment` → sửa tay.

### BUG-03 · `retry_source` kiểm tra `plan_ready` sau khi đã ghi đè status [Đã xác nhận]
- **Vị trí**: `app/routers/sources.py:906`: gán `source.status = "pending"`; dòng 917 kiểm `source.status == "plan_ready"`, **luôn sai**.
- **Hậu quả**: định tuyến chỉ dựa vào `pipeline_phase`. Nguồn `plan_ready` mà `pipeline_phase` rỗng/khác thì bị chạy lại từ đầu (`ingest_file_task`), tốn LLM và có thể tạo trùng.
- **Sửa**: lưu `prev_status = source.status` trước khi gán, dùng `prev_status` để định tuyến.

### BUG-04 · Slug trang luật trùng giữa hai văn bản [Cần kiểm, rất có khả năng]
- **Vị trí**: `legal_service.py:346, 367, 466`: `doc_slug = slugify(doc_title)[:60]`, `dieu-{n}-{doc_slug}`.
- **Hậu quả**: hai văn bản cùng tiền tố tên ghi đè Điều của nhau (`upsert_page` theo slug).
- **Sửa**: xem [04 §1](04-phap-luat-va-truy-xuat.md) (slug theo số hiệu, hoặc kèm hash `source_id`).

### BUG-05 · `ARTICLE_RE` tách nhầm Điều trong phần trích sửa đổi [Cần kiểm bằng NĐ 50/2024]
- **Vị trí**: `legal_service.py:37`. Xem [04 §1](04-phap-luat-va-truy-xuat.md).

## P1: sớm

| ID | Vấn đề | Vị trí | Hướng sửa |
|---|---|---|---|
| BUG-06 | Xoá nguồn chỉ gỡ `source_id` khỏi trang nhiều nguồn, **nội dung đã merge vẫn còn** | `detach_source_from_wiki` | Đánh dấu trang "cần biên soạn lại", đưa vào hàng đợi review; hoặc lưu phần đóng góp theo nguồn để gỡ ra |
| BUG-07 | URL source luôn `GLOBAL`, bỏ qua phòng ban | `add_url_source` | Nhận `scope_type`, `department_ids` như upload file |
| BUG-08 | URL dự phòng lưu HTML thô | `ingest_url_task` | trafilatura |
| BUG-09 | Không chống trùng file, không giới hạn dung lượng, đọc cả file vào RAM | `upload_source` (`sources.py:613`) | [02 §8](02-xu-ly-tai-lieu-dau-vao.md) |
| BUG-10 | Sweep không bắt nguồn kẹt ở `pending` (mất job khi enqueue) | `sweep_stuck_processing_cron` | Thêm điều kiện `pending` quá N phút và không có `job_id` còn sống → enqueue lại |
| BUG-11 | Trang luật embed hai lần (batch embed trang, rồi `index_wiki_page_chunks` embed lại) | `finalize_legal_source` | Bỏ một lần |
| BUG-12 | `max_tries=3` gần như vô tác dụng (bắt exception, đặt `error`, raise lại; arq chỉ retry với `Retry`/timeout) | `worker.py` | Phân loại lỗi: tạm thời (mạng, 429, 5xx LLM) → `raise Retry(defer=...)`; vĩnh viễn → `error` |
| BUG-13 | Mỗi phòng ban một bản sao trang (`_resolve_wiki_scopes`) → nhân storage, embedding, LLM merge | `pipeline.py:30` | Dài hạn: 1 trang + bảng ACL `wiki_page_departments`. Cần thiết kế lại RBAC, không làm vội |

## P2: dọn dẹp

- Code chết: `app/ai/wiki_agent.py`, `wiki_agent_tools.py`, `wiki_compiler.py`, `wiki_analyzer.py`, `kb_service.ingest_source`, `policy_engine.py`, `regenerate_hot_cache` (comment "disabled" tại `pipeline.py:202`), `scratch_page.js` ở gốc repo.
- `dedup.py` ở gốc: script xoá trang trùng `(slug, scope)`. Chuyển vào `scripts/` và tìm nguyên nhân gốc gây trùng.
- Milvus: ghi mà không đọc (`milvus_service.py`, `milvus_enabled=True`). Tắt mặc định.
- `relations` trong MAP bị bỏ: dùng (xem [03](03-knowledge-graph.md)) hoặc xoá khỏi prompt để tiết kiệm token.
- Scope `project` còn nhánh code nhưng đã bỏ workspace.
- `docs/ARCHITECTURE.md` lỗi thời (pdfplumber, html2text, citation verify, workspace).
- **Không có `tests/`**: bắt đầu bằng test cho BUG-01…05 và parser fixtures.

---

## Bài học vận hành từ WeKnora

### 1. Idempotency theo "lần parse"
WeKnora (`knowledgeService.ProcessDocument`, `knowledge_process.go:3490`) kiểm ở **đầu mỗi task**: lần parse này đã bị thay thế chưa? nguồn đang xoá hay đã huỷ? đã hoàn tất chưa? file nguồn có bị thay không?

Áp dụng cho Arkon:
- Thêm `Source.attempt_id` (uuid), sinh mới mỗi lần retry, reparse hoặc approve.
- Mọi task nhận `(source_id, attempt_id)`; nếu `source.attempt_id != attempt_id` → bỏ qua ngay.
- Giải quyết trường hợp người dùng bấm retry khi job cũ vẫn đang chạy (hai pipeline ghi đè nhau, có thể là nguyên nhân sinh trang trùng mà `dedup.py` phải dọn).

### 2. Đếm subtask để hoàn tất
WeKnora: `pending_subtasks_count` + `FinalizeSubtask`; hết subtask mới `completed`. Hữu ích khi Arkon thêm các bước nền (sinh câu hỏi, graph, OCR ảnh) chạy song song.

### 3. Dead-letter queue
WeKnora: `internal/middleware/asynqdl`, `types/task_dead_letter.go`. Arkon: bảng `task_failures(task_name, source_id, attempt_id, error, traceback, payload, created_at)` + trang admin xem/chạy lại.

### 4. Span theo bước
WeKnora: `knowledge_span_tracker.go` ghi thời gian các bước docreader / chunking / embedding / multimodal / postprocess (+ Langfuse). Arkon đã có `trace_context`; bổ sung bảng `source_stage_timings` để trang nguồn hiện "Parse 12s · OCR 3m · MAP 8m · …" và tìm điểm nghẽn.

### 5. Reset task khi khởi động
WeKnora: `internal/container/reset_pending_tasks.go`. Arkon: khi worker khởi động, nguồn `processing` không có job arq sống → enqueue lại theo `pipeline_phase`.

### 6. Timeout riêng cho parser
WeKnora: `DocReaderCallTimeout` 30 phút. Arkon: `job_timeout` 7200s cho cả task; nên có timeout riêng cho OCR mỗi trang và parse mỗi file.
