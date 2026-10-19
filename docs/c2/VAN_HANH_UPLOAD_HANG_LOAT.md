# Vận hành: upload hàng loạt và worker

Ghi chú sau sự cố ngày 2026-10-17: upload khoảng 90 file vào c2 thì gần như tất cả báo lỗi. Tài liệu này ghi nguyên nhân, những gì đã sửa, các thông số liên quan và cách kiểm tra khi gặp lại.

## 1. Sự cố 2026-10-17

### Hiện tượng

- Hàng đợi arq có khoảng 92 job, worker chỉ chạy 2 job cùng lúc (`WORKER_MAX_JOBS=2`). Có job phải chờ hơn 2 giờ (`delayed=7516s`).
- Hầu hết `ingest_file_task` thất bại ngay khi bắt đầu, sau đó bộ quét "stuck" đánh failed thêm 12 nguồn.

### Nguyên nhân

| # | Nguyên nhân | Dấu hiệu trong log worker |
|---|---|---|
| 1 | Container worker mất DNS một lúc sau khi Docker khởi động lại. `tiktoken` tải từ điển `cl100k_base` từ Internet **mỗi lần container khởi động**, nên mọi job đếm token đều lỗi. | `NameResolutionError ... openaipublic.blob.core.windows.net ... cl100k_base.tiktoken` |
| 2 | Cùng lúc đó các lời gọi OCR, vision và LLM tới endpoint vLLM cũng lỗi mạng. | `Vision call failed (attempt n/3): Connection error.` |
| 3 | `get_milvus_client()` nhớ lần kết nối thất bại đầu tiên **suốt vòng đời process**. Nếu worker khởi động trước khi Milvus sẵn sàng thì mọi lần ghi vector bị bỏ qua, nhưng nguồn vẫn báo `ready`. | Một dòng `Failed to connect to Milvus` duy nhất, sau đó không còn dòng nào về Milvus |
| 4 | `sweep_stuck_processing_cron` đánh failed mọi nguồn `processing` không cập nhật quá 60 phút, **kể cả nguồn chỉ đang chờ trong hàng đợi**. Khi hàng đợi dài, nguồn chờ hàng giờ giữa các bước (ingest → chunk → caption → map_reduce → refine) nên bị quét nhầm. | `sweep_stuck_processing_cron marked N stuck source(s) as failed` |
| 5 | Worker bị kill khi đang chạy job (exit 137 do `docker compose stop` hoặc `restart`). arq mặc định hủy job ngay khi nhận SIGTERM, và mỗi lần hủy tốn một lượt thử. Sau 3 lượt thì job hỏng hẳn. | `max retries 3 exceeded` |

### Đã sửa

| Nguyên nhân | Sửa ở đâu | Cách sửa |
|---|---|---|
| 1 | `Dockerfile`, `app/utils/tokens.py` | Tải sẵn từ điển tiktoken lúc build image (`TIKTOKEN_CACHE_DIR=/opt/tiktoken`). Nếu vẫn không tải được thì `count_tokens()` dùng `estimate_tokens()` và ghi warning thay vì làm hỏng job. |
| 3 | `app/services/milvus_service.py` | Kết nối Milvus thất bại thì thử lại sau 30 giây, không tắt Milvus vĩnh viễn nữa. |
| 4 | `app/worker.py` (`_source_ids_with_pending_jobs`) | Trước khi quét, đọc hàng đợi arq và bỏ qua mọi nguồn còn job đang chờ hoặc đang chạy (arq giữ job đang chạy trong hàng đợi cho tới khi chạy xong). Không đọc được Redis thì bỏ qua lượt quét đó. |
| 5 | `app/worker.py`, `app/config.py`, `docker-compose.yml` | Khi nhận SIGTERM, worker ngừng nhận job mới và chờ job đang chạy tối đa `WORKER_SHUTDOWN_WAIT_S` (mặc định 300 giây). `stop_grace_period: 330s` cho `worker` và `worker_skills` để Docker không SIGKILL trước khi hết thời gian chờ đó. |

Test: `tests/test_stuck_sweep.py`.

### Trạng thái sau khi restart (16:48)

- Worker dừng êm: chờ đủ 300 giây, sau đó hủy 2 job `caption_images_task` và đưa chúng vào chạy lại. Không còn SIGKILL.
- Worker đang OCR 2 file "Thông tư 108.2026.TT-BCA" (134 trang) và "Thông tư 109.2026.TT-BCA" (115 trang). Hàng đợi còn khoảng 74 job.
- Nguồn: processing 27, error 12, partial 7, pending 2, ready 2. Cả 14 nguồn có `chunk_status=ready` đều đã có vector trong Milvus (`arkon_source_chunks_1024`, 808 vector).
- 4 nguồn đã được đưa lại vào hàng đợi chunk vẫn đang chờ: `4e1553d1…`, `c37eeec3…`, `776e833d…`, `09524939…`.
- Cần bấm Retry trên UI: các nguồn `error` (gồm 12 nguồn bị quét nhầm) và `440a3202-400c-48ea-8647-6c0647fcb642` (đã hết lượt thử).

## 2. Sự cố 2026-10-18: gateway AI không phản hồi

### Hiện tượng

- Worker vẫn chạy job (2–3 job cùng lúc), nhưng không job nào xong. Hàng đợi đứng ở khoảng 80 job, `j_complete=0`.
- Log worker chỉ có `Vision call failed (attempt n/3)` và các job bị hủy vì hết `WORKER_JOB_TIMEOUT`.

### Nguyên nhân

Các backend sau gateway LiteLLM/vLLM bị sập. Chỉ embedding còn chạy:

| Model | Kết quả khi gọi thử |
|---|---|
| `hunyuan-ocr` (OCR) | Lỗi 500 `OpenAIException - Connection error` sau khoảng 5 giây |
| `qwen-3.5-9b` (LLM và vision) | Timeout, kể cả request text rất ngắn (Cloudflare 524) |
| Embedding | Bình thường |

Việc này nằm ở hạ tầng AI, **phải do bên vận hành gateway khắc phục**.

Code làm sự cố nặng thêm:

| # | Lỗi | Hệ quả |
|---|---|---|
| 1 | `AsyncOpenAI` dùng timeout mặc định 600 giây và `max_retries=2`, cộng thêm 3 lượt thử trong `analyze_image`. | Một trang có thể treo tới khoảng 90 phút, lâu hơn `WORKER_JOB_TIMEOUT`. Job bị hủy và mất một lượt thử của arq (tối đa 3 lượt). |
| 2 | OCR lỗi thì PDF parser vẫn giữ text gốc (rỗng). | Nguồn scan được index rỗng nhưng vẫn báo `ready`. |
| 3 | `CAPTION_CONCURRENCY=4` lớn hơn semaphore vision (2). | Caption chờ slot cũng bị tính vào timeout 120 giây. |
| 4 | Caption làm lại cả những ảnh đã có caption. | Bị ngắt là làm lại từ đầu. |

### Đã sửa

| Sửa ở đâu | Cách sửa |
|---|---|
| `app/ai/upstream.py` (mới) | Circuit breaker cho từng model. Sau 3 lỗi mạng, timeout hoặc 5xx liên tiếp thì mọi lời gọi tới model đó báo lỗi ngay trong 120 giây, không chờ timeout nữa. Lỗi mang dấu `[ai_unavailable]`. |
| `app/config.py`, `openai_provider.py`, `ocr_service.py` | Timeout rõ ràng: vision 120 giây, LLM 300 giây. Client chỉ tự thử lại 1 lần (`AI_CLIENT_MAX_RETRIES`). |
| `app/services/parsers/pdf_parser.py` | Còn trang scan chưa OCR được vì AI sập thì báo lỗi `[ai_unavailable]`, không index tài liệu rỗng. |
| `app/ai/mrp/mapper.py` | Lưu các chunk đã trích xong trước khi báo lỗi, lần chạy sau chỉ làm phần còn lại. |
| `app/worker.py` (`caption_images_task`) | Bỏ qua ảnh đã có caption. Số caption đồng thời không vượt `VISION_MAX_CONCURRENCY`. Khi AI sập thì đánh lỗi wiki và dừng, không chuyển sang MAP. |
| `app/worker.py`, `app/tasks/wiki_tasks.py` | Job lỗi vì AI sập thì kết thúc luôn, không để arq thử lại (tránh đốt 3 lượt thử). |
| `app/services/source_retry.py` (mới) | Logic Retry dùng chung cho API, cron và script. Retry nhánh wiki còn ảnh chưa caption thì chạy lại từ bước caption. |
| `app/worker.py` (`resume_ai_unavailable_cron`) | Mỗi 5 phút: nếu có nguồn lỗi `[ai_unavailable]` thì gửi một request thử tới LLM (và OCR nếu cần). AI trả lời được thì tự đưa các nguồn đó vào hàng đợi lại. |
| `app/ai/providers/base.py` | Thay `TINY_PNG` hỏng bằng PNG hợp lệ; nút "Test connection" của vision không còn báo lỗi giả. |

Test: `tests/test_ai_upstream.py`, `tests/test_source_retry.py`.

### Retry hàng loạt

```bash
# Đưa lại mọi nguồn error/partial vào hàng đợi; --wait: chờ tới khi AI trả lời rồi mới đưa vào
docker exec -w /app cahy_wiki_worker python -m app.services.source_retry --wait --reset-recover

# Chỉ các nguồn lỗi do AI sập (cron cũng tự làm việc này mỗi 5 phút)
docker exec -w /app cahy_wiki_worker python -m app.services.source_retry --only-ai-outage
```

- Script bỏ qua nguồn còn job trong hàng đợi.
- `--reset-recover` đặt lại `auto_recover_count`, kể cả nguồn đã bị chặn Retry.
- Trên Git Bash (Windows) cần thêm `MSYS_NO_PATHCONV=1` trước `docker exec -w /app`.

Kiểm tra gateway AI có trả lời chưa:

```bash
docker exec -w /app cahy_wiki_worker python -c "import asyncio; from app.database import async_session_factory as f; from app.services.source_retry import ai_ready
async def m():
    async with f() as s: print(await ai_ready(s, need_ocr=True))
asyncio.run(m())"
```

### Trạng thái sau khi restart (17:33)

- Gateway vẫn sập: OCR lỗi 500, LLM và vision bị Cloudflare cắt (524) sau khoảng 100 giây.
- Breaker của `ocr` và `qwen-3.5-9b` đã mở. Job lỗi do AI kết thúc với `{'status': 'error', 'reason': 'ai_unavailable'}` và không bị arq thử lại. Ví dụ: "Thông tư 154" (4/4 trang scan) báo lỗi rõ ràng, không bị index rỗng.
- Đợt lỗi đầu tiên của mỗi model vẫn chậm, vì phải đủ 3 lần timeout (mỗi lần khoảng 100–200 giây) thì breaker mới mở.
- Đang chạy ngầm trong `cahy_wiki_worker`: `python -m app.services.source_retry --wait --reset-recover --interval 180`, log ở `/tmp/retry_all.log`. Khi AI trả lời được, script đưa mọi nguồn `error`/`partial` vào hàng đợi lại. Các nguồn còn đang `processing` nếu lỗi do AI thì `resume_ai_unavailable_cron` sẽ tự đưa lại. Script sẽ mất nếu worker restart; khi đó chạy lại lệnh ở trên.
- Hàng đợi khoảng 87 job, trong đó có khoảng 29 job cron xếp sau các job dài (`WORKER_MAX_JOBS=2`).

### Lỗi còn lại sau khi gateway hồi phục (tối 2026-10-18)

Sau khi retry, 35 nguồn xong hẳn. Còn 13 nguồn `partial` (chunk đã `ready`, tìm kiếm được, chỉ thiếu wiki) và 2 nguồn `ready` nhưng wiki còn `pending`. Nguyên nhân gốc chung: lúc hồi phục có 20 nguồn được đưa lại cùng lúc. Mỗi job MAP gọi 6 call song song, viết trang 4 call song song, chạy 2 job một lúc, nên model `qwen-3.5-9b` của gateway bị quá tải và mọi call đều chậm.

| Nhóm lỗi | Số nguồn | Nguyên nhân |
|---|---|---|
| `TimeoutError` ở REDUCE (`run_planning_call`) | 5 | Call lập kế hoạch trang (tới 300 khái niệm) chỉ có 120 giây (`PLANNING_TIMEOUT_S`). |
| `MAP phase produced no successful chunk extracts` | 3 | Mọi chunk của nguồn đều quá 300 giây (`LLM_TIMEOUT_S` của mapper). |
| `CancelledError` ở MAP/REFINE | 4 | Job chạy quá `WORKER_JOB_TIMEOUT=1800` trong `.env` (log: refine 1853–1856 giây), arq hủy job. |
| `APIConnectionError: Connection error.` | 1 | Lỗi mạng thoáng qua tới gateway. |
| `ready` + wiki `pending` | 2 | Còn sót từ sự cố 2026-10-17: nhánh wiki chưa từng chạy. Vì trạng thái tổng là `ready` nên retry hàng loạt (chỉ lấy `error`/`partial`) bỏ qua. |

Ngoài ra nhiều lần refine kết thúc với `pages_created: 0` và cả danh sách `pages_skipped`, thời gian đúng bội số khoảng 308 giây: từng trang bị timeout 300 giây ở writer.

Đã sửa:

- Timeout và độ song song của MRP đưa ra cấu hình: `MRP_LLM_TIMEOUT_S=480` (dùng cho MAP, planning, viết trang), `MRP_MAP_PARALLEL_CALLS=3` (cũ 6), `MRP_WRITE_PARALLEL_PAGES=2` (cũ 4). `LLM_REQUEST_TIMEOUT_S` mặc định tăng lên 480 cho khớp.
- `.env`: `WORKER_JOB_TIMEOUT` 1800 → 7200 (bằng mặc định trong `.env.example`).
- Retry 13 nguồn `partial` bằng `python -m app.services.source_retry --reset-recover`. 2 nguồn wiki `pending` được đưa lại riêng bằng `requeue_source(..., branch="wiki")`. Task MAP tự tạo lại trang điều luật nếu attempt chưa có, nên không phải OCR lại.

Song song thấp hơn làm một tài liệu chạy lâu hơn, nhưng tránh được việc cả loạt call cùng timeout rồi bỏ trang. Nếu gateway có thêm GPU, có thể tăng `MRP_MAP_PARALLEL_CALLS` trở lại.

Refine bỏ hết trang (`pages_created: 0`) trước đây vẫn đánh dấu wiki `ready`, nên nguồn không có trang wiki nào và không được retry. Nay commit báo wiki `error`, phase `refine`; retry nhánh wiki sẽ chạy lại từ REFINE (`app/ai/mrp/pipeline.py`). Có hiệu lực sau khi restart worker.

### Sửa lỗi OCR trong tab "Toàn văn"

Tab Toàn văn của `/wiki/law/<văn bản>` đọc nội dung từ trang wiki của từng điều (`dieu-<N>-<doc_slug>`, bỏ khối trích dẫn `> **Căn cứ pháp lý**` ở đầu) và phần mở đầu từ trang tổng quan (`<doc_slug>`, mục "Căn cứ ban hành & Phần mở đầu"). Chưa có trang thì dùng `full_text` OCR như cũ.

- Người có `wiki:write:all` (hoặc admin) thấy nút **Sửa** ở mỗi điều và ở phần mở đầu. Bấm vào sẽ mở trang wiki ở chế độ sửa (`/wiki/<slug>?edit=1`). Lưu xong, Toàn văn hiện nội dung đã sửa kèm nhãn "Đã hiệu đính".
- Văn bản chưa có trang theo điều (loại tri thức không phải Luật, hoặc MRP đã bỏ hết trang): nút **Sửa** gọi `POST /api/wiki/legal-docs/{key}/pages` để tách văn bản thành trang tổng quan và mỗi điều một trang, nhúng vector, rồi mở trang cần sửa. API này không đổi trạng thái wiki, không gọi LLM và giữ nguyên `doc_slug`. Nếu chưa lưu `doc_slug` thì API dùng `doc-<8 ký tự đầu id>`, không tạo từ số hiệu, vì các tệp cùng một quyết định (quyết định và phụ lục) có chung số hiệu nên slug sẽ trùng nhau.
- Trang đã sửa tay (có revision `editor_edit`, `rollback` hoặc `draft_approved`) được giữ nguyên khi văn bản được xử lý lại (`finalize_legal_source`), nên bản sửa không bị OCR ghi đè.

### Worker treo cả hàng đợi (sáng 2026-10-18, khoảng 03:38–05:16 UTC)

- **Hiện tượng:** 11 nguồn nằm ở `queued` suốt gần 2 giờ. Worker ngốn khoảng 97% CPU nhưng không in log, các cron cũng không chạy.
- **Nguyên nhân:** regex `_GLUED_BOLD_ARTICLE` trong `app/services/legal_hierarchy_parser.py` có `(?:\*\*|__?|<mark>)+`. Với các dòng mẫu biểu có chuỗi `________` dài, mỗi dấu `_` có thể khớp theo nhiều cách, nên regex quay lui theo cấp số mũ. Lệnh tách điều của "Thông tư 79/2024/TT-BCA" (`fd55525c…`) chạy mãi không xong. Regex chạy trong C nên chặn luôn event loop của arq: các job khác, cron và cả health log đều đứng.
- **Đã sửa:** đổi `__?` thành `_`, để mỗi chuỗi `_` chỉ còn một cách khớp. Văn bản trên giờ tách xong trong 0,04 giây (43 điều). Test hồi quy: `test_glued_heading_split_is_fast_on_form_blanks`.
- **Lưu ý:** worker đang treo kiểu này thì không tự thoát. `docker compose restart worker` sẽ chờ hết `stop_grace_period` rồi kill.

### LLM gọi ở chế độ stream (chiều 2026-10-18)

- **Hiện tượng:** job MRP lỗi `InternalServerError: Error code: 524`. Proxy đứng trước vLLM cắt kết nối nếu trong 120 giây không nhận được byte nào. Lệnh gọi lập kế hoạch (REDUCE) và lệnh viết trang (REFINE) sinh output dài, có lúc tổng thời gian vượt 120 giây dù model vẫn đang chạy.
- **Đã sửa:** `OpenAILLM.generate` và `generate_with_tools` gọi với `stream=True` (kèm `stream_options.include_usage`). Token về liên tục nên Cloudflare không cắt; text, tool call, usage và tracing vẫn như cũ. Tắt bằng `LLM_STREAM=false` cho endpoint không hỗ trợ SSE. Test: `tests/test_openai_stream.py`.
- **Giới hạn:** stream không cứu được khi gateway quá tải hoặc sập (token đầu tiên không về trong 120 giây, hoặc `Connection error`). Chiều 2026-10-18 gateway sập nhiều lần: request 1 từ cũng timeout và embedding báo `Connection error`. Các nguồn lỗi do sập được gắn `[ai_unavailable]` và `resume_ai_unavailable_cron` tự đưa lại khi probe thành công. Lỗi 524 trước khi breaker mở thì không có nhãn này, phải requeue tay (`requeue_source(..., branch="wiki")`).

## 3. Thông số liên quan

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `WORKER_MAX_JOBS` | 3 (`.env` của c2 đang để 2) | Số job một worker chạy cùng lúc. Việc chủ yếu là chờ vLLM, nên có thể tăng lên 4–6 **nếu vLLM chịu được**. |
| `WORKER_JOB_TIMEOUT` | 7200 (`.env` c2 đã chỉnh từ 1800 lên 7200 ngày 2026-10-18) | Thời gian tối đa của một job. Ngưỡng quét stuck = `max(2 × giá trị này, 1800)` giây. |
| `VISION_MAX_CONCURRENCY` | 2 | Số lời gọi vision đồng thời trong một process, dùng chung cho OCR và caption. Đây là nút cổ chai chính với PDF scan. |
| `VISION_REQUEST_TIMEOUT_S` | 120 | Timeout một request vision. OCR dùng 120 giây cố định. |
| `LLM_REQUEST_TIMEOUT_S` | 480 | Timeout một request LLM. Khi stream thì đây là thời gian chờ tối đa giữa hai lần nhận dữ liệu. Tổng thời gian của một lời gọi do `MRP_LLM_TIMEOUT_S` giới hạn. |
| `LLM_STREAM` | true | Gọi LLM ở chế độ stream để tránh lỗi 524 của Cloudflare khi output dài. |
| `MRP_LLM_TIMEOUT_S` | 480 | Timeout mỗi call LLM của MAP, planning (REDUCE) và viết trang (REFINE). |
| `MRP_MAP_PARALLEL_CALLS` | 3 | Số chunk MAP gọi LLM song song trong một job. Nhân với `WORKER_MAX_JOBS` ra tải tối đa lên gateway. |
| `MRP_WRITE_PARALLEL_PAGES` | 2 | Số trang wiki viết song song trong một job. |
| `AI_CLIENT_MAX_RETRIES` | 1 | Số lần client OpenAI tự thử lại. Vision còn tự thử 3 lần trong app, nên không nên tăng. |
| `WORKER_SHUTDOWN_WAIT_S` | 300 | Thời gian chờ job đang chạy khi worker dừng. Phải nhỏ hơn `stop_grace_period` (330s). |
| `MAX_AUTO_RECOVER_ATTEMPTS` | 3 | Một nguồn bị quét stuck đủ số lần này thì bị chặn Retry, cần admin reset `auto_recover_count`. |

Hệ quả của `WORKER_SHUTDOWN_WAIT_S`: `docker compose stop` hoặc `restart worker` có thể mất tới khoảng 5 phút khi đang có job dài. Job chạy quá 300 giây vẫn bị hủy và tự chạy lại (tốn một lượt thử).

## 4. Kiểm tra nhanh

Các lệnh chạy từ thư mục `document-wiki-c2`.

```bash
# Trạng thái container
docker ps --format '{{.Names}}\t{{.Status}}' | grep cahy_wiki

# Tiến độ hàng đợi (dòng "recording health" in mỗi khoảng 30 giây)
docker logs --tail 50 cahy_wiki_worker 2>&1 | grep -E "recording health| ! | ← "

# Thống kê trạng thái nguồn
docker exec cahy_wiki_postgres psql -U arkon -d arkon -c "select status, chunk_status, wiki_status, count(*) from sources group by 1,2,3 order by 4 desc"

# DNS và mạng từ bên trong worker
docker exec cahy_wiki_worker python -c "import socket; [print(h, socket.gethostbyname(h)) for h in ['vllm','langfuse','milvus','redis']]"

# Worker đã nối được Milvus chưa
docker exec cahy_wiki_worker python -c "from app.services.milvus_service import get_milvus_client as g; c=g(); print(c.list_collections() if c else 'NO MILVUS')"
```

Khi log có `Failed to connect to Milvus` lúc khởi động: kiểm tra những nguồn được báo `ready` trong khoảng thời gian đó có vector trong `arkon_source_chunks_1024` không. Nguồn nào thiếu thì đưa lại vào hàng đợi bằng `worker.commit_and_enqueue_chunk_branch(session, source)`, hoặc chạy `backfill_source_chunks_task` với `force=True`.

## 5. Upload hàng loạt: lưu ý

- Upload theo đợt khoảng 10–20 file, đợi hàng đợi gần hết (`queued` trong `recording health`) rồi mới upload tiếp.
- PDF scan rất chậm: mỗi trang là một lời gọi OCR, tối đa 2 lời gọi cùng lúc. Một file 130 trang có thể chạy hơn 10 phút. Trong lúc đó worker trông như "đứng" vì không in log theo từng trang.
- Không tắt hoặc restart stack giữa đợt nếu không cần. Nếu cần thì dùng `docker compose stop` / `restart` để worker kịp dừng êm, không dùng `docker kill`.
- Sau khi stack khởi động lại, kiểm tra DNS và Milvus trong worker (mục 3) trước khi upload.

## 6. Còn tồn tại (chưa sửa)

| Vấn đề | Ảnh hưởng | Hướng sửa |
|---|---|---|
| Chỉ có một hàng đợi cho mọi loại job. | Job chunk/embedding (1–3 giây) phải chờ sau caption và map_reduce (1–3 phút), nên tài liệu rất lâu mới tìm kiếm được. | Tách hàng đợi riêng cho chunk/embedding, có worker riêng. |
| Circuit breaker nằm trong từng process. | Worker và API mỗi bên tự đếm lỗi riêng. | Đủ dùng hiện tại; nếu nhiều worker thì chuyển trạng thái sang Redis. |
| Vision lỗi 3 lần nhưng không phải do gateway sập (ví dụ lỗi 4xx) thì ảnh không có caption, không báo lỗi. | Ảnh thiếu mô tả. | Retry nhánh wiki sẽ caption lại các ảnh còn thiếu. |
| Retry hàng loạt chỉ lấy nguồn `error`/`partial`. | Nguồn `ready` mà wiki còn `pending` (không phải verbatim) bị bỏ sót. | Hiện xử lý tay bằng `requeue_source(..., branch="wiki")`; nếu lặp lại thì thêm điều kiện này vào `retry_failed_sources`. |
