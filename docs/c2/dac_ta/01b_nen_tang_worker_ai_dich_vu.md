# 01b — Nền tảng backend: worker, tầng AI, dịch vụ dùng chung, tiện ích, giao diện bắt buộc

Tài liệu này tiếp nối `01a_nen_tang_cau_hinh_csdl.md`. Với các phần mà tài liệu miền đã đặc tả chi tiết, ở đây chỉ ghi điểm tham chiếu và các bổ sung.

---

## 1. `app/worker.py` — tổng quan

### 1.1. Phân bổ đặc tả

| Nội dung | Nơi đặc tả |
|---|---|
| ingest_file_task, các stage nạp, compute_source_dual_status, check_task_attempt_validity, caption_images_task, enqueue_post_extraction_pipeline, `WorkerSettings` (functions, cron, tham số) | 03 §11 (đặc biệt 11.8–11.9) |
| generate_questions_task | 03 §13 |
| Task reembed và embed theo chiều | 04 §15 |
| ai_pre_review_draft_task, sweep_stuck_ai_review_cron, relink/backfill | 05b |
| ingest_skill_task, delete_skill_task, daily_stats_rollup_cron | 06 |
| Biên dịch wiki (MRP) | 05a |

### 1.2. Phần bổ sung chỉ có ở đây

**Redis.** Hàm dựng cấu hình Redis cho arq lấy redis_host, redis_port, redis_db và redis_password từ settings; mật khẩu rỗng thì truyền None. Cả `WorkerSettings` và `SkillWorkerSettings` dùng chung cấu hình này.

**Hook vòng đời.** on_startup và on_shutdown chỉ ghi log khởi động và dừng. Không khởi tạo Langfuse ở đây; tracing tự khởi tạo lười (§3.6).

**`SkillWorkerSettings`** dành cho dịch vụ worker_skills, tách khỏi hàng đợi chính để kỹ năng nặng không chặn việc nạp tài liệu.

| Thuộc tính | Giá trị |
|---|---|
| functions | ingest_skill_task, delete_skill_task |
| queue_name | `skills_queue` |
| redis_settings | như trên |
| max_jobs | settings.worker_max_jobs |
| job_timeout | settings.worker_job_timeout |
| max_tries | 3 |
| retry_delay | 10 giây |
| health_check_interval | 30 giây |
| cron_jobs | cleanup_temp_uploads_cron, chạy ở phút 0 mỗi giờ |

Router skills phải enqueue vào `skills_queue` (06).

**`cleanup_temp_uploads_cron(ctx)`**

1. Duyệt thư mục `temp_uploads` của ứng dụng, tức thư mục được gắn volume `./temp_uploads` trong compose. Nếu thư mục không tồn tại thì trả về.
2. Xóa các file thường có thời điểm sửa cách hiện tại hơn 3600 giây.
3. Lỗi trên từng file chỉ được ghi log, sau đó tiếp tục với file khác.
4. Ghi log số file đã xóa.

**Import lười.** Các task trong worker import dịch vụ (ConfigService, ProviderRegistry, async_session_factory, storage_service, …) bên trong thân hàm, để test có thể patch biến cấp module của dịch vụ gốc.

---

## 2. Giao thức provider — `app/ai/providers/base.py` và `app/ai/agent_protocol.py`

### 2.1. `ProviderType`

Enum chuỗi gồm các giá trị google, openai, anthropic, ollama, voyage, cohere.

### 2.2. `ProviderConfig` (dataclass)

| Trường | Kiểu | Mặc định |
|---|---|---|
| provider | ProviderType | bắt buộc |
| api_key | str | rỗng |
| model_id | str | rỗng |
| base_url | str hoặc None | None |
| dimensions | int hoặc None | None |
| extra | dict | dict rỗng (mỗi instance một dict riêng) |
| spec | đối tượng spec hoặc None | None |

### 2.3. Lớp trừu tượng

Mỗi lớp khởi tạo với một `ProviderConfig` và lưu nó vào thuộc tính `config`.

| Lớp | Phương thức (async) | Ghi chú |
|---|---|---|
| `EmbeddingProvider` | `embed(text) -> list[float]`, `embed_batch(texts, concurrency=5) -> list[list[float]]`, `test_connection() -> tuple[bool, str]` | Property `dimensions` trả config.dimensions, hoặc 768 nếu None |
| `LLMProvider` | `generate(prompt, system=None, max_tokens=None, temperature=0.7) -> str`; `generate_with_tools(messages, tools, system=None, max_tokens=None, temperature=0.2) -> AssistantTurn`; `test_connection()` | Cài đặt mặc định của generate_with_tools ném NotImplementedError, với thông báo nêu tên lớp và khuyên cấu hình một provider hỗ trợ function calling |
| `VisionProvider` | `analyze_image(image_data: bytes, mime_type="image/jpeg", prompt=None, max_tokens=None) -> str`; `test_connection()` | |

### 2.4. `app/ai/agent_protocol.py` — định dạng hội thoại trung lập

Writer MRP (05a, import lười) và wiki agent dùng module này.

- **`ToolCall`** (dataclass) gồm id: str, name: str, arguments: dict.
- **`AssistantTurn`** (dataclass) gồm:
  - text: str hoặc None;
  - tool_calls: list[ToolCall], mặc định rỗng;
  - finish_reason: một trong tool_use, end_turn, max_tokens, mặc định end_turn;
  - raw_provider_content: Any, mặc định None. Trường này giữ nội dung gốc của provider để phát lại khi cần, ví dụ thought signature của Gemini.

Tin nhắn trung lập là dict:

- user: có role và content.
- assistant: có role, content (text), tool_calls (danh sách dict id, name, arguments) và có thể có khóa `_raw_content`.
- kết quả tool: role user, kèm khóa tool_results là danh sách dict id, name, content.

| Hàm | Hành vi |
|---|---|
| `assistant_message_from_turn(turn) -> dict` | Dựng tin assistant. Có khóa `_raw_content` chỉ khi raw_provider_content khác None |
| `tool_results_message(results) -> dict` | results là danh sách bộ ba (id, name, result). Result là chuỗi thì giữ nguyên, ngược lại tuần tự hóa JSON giữ ký tự Unicode (không escape ASCII) |
| `neutral_to_anthropic_messages(messages) -> list` | Tin kết quả tool thành tin user gồm các khối tool_result, mỗi khối có tool_use_id và content. Tin assistant thành danh sách khối: text (nếu có) rồi các khối tool_use (id, name, input); nếu không có khối nào thì dùng một khối text rỗng. Tin user thường giữ nguyên |
| `neutral_to_openai_messages(messages) -> list` | Mỗi kết quả tool thành một tin role "tool" với tool_call_id và content. Tin assistant có tool_calls thành tool_calls kiểu function, arguments là chuỗi JSON |
| `neutral_to_gemini_contents(messages) -> list` | Kết quả tool thành tin role user gồm các part function_response (name, response gồm result = content). Tin assistant: nếu có `_raw_content` thì phát lại nguyên nội dung đó, nếu không thì dựng role "model" gồm part text và part function_call. Tin user thành role user với một part text |
| `openai_tools_to_anthropic(tools) -> list` | Từ schema tool kiểu OpenAI (type function, kèm function chứa name, description, parameters) sang dạng gồm name, description, input_schema. Thiếu parameters thì dùng schema object không có thuộc tính |
| `openai_tools_to_gemini(tools)` | Sang FunctionDeclaration của google-genai. Schema được chuyển đệ quy với các kiểu string, number, integer, boolean, array, object; kiểu lạ thành STRING. Giữ description, properties, required, items và enum |

---

## 3. Provider cụ thể

Mọi client SDK được tạo lười ở lần gọi đầu tiên. Mọi lời gọi sinh văn bản và embedding đều ghi Langfuse qua record_generation hoặc record_embedding (§3.6), cả khi thành công lẫn khi lỗi. Khi lỗi, ghi với level ERROR kèm thông điệp rồi ném lại ngoại lệ, trừ khi bảng dưới nói khác.

### 3.1. OpenAI — `app/ai/providers/openai_provider.py`

Client là AsyncOpenAI với api_key và base_url, nên dùng được cho endpoint tương thích OpenAI và mô hình tùy chỉnh.

**`OpenAIEmbedding`**

- Chỉ gửi tham số dimensions khi config.dimensions có giá trị **và** cờ extra `send_dimensions` (mặc định True) là đúng. Mô hình tùy chỉnh đặt cờ này là False.
- `embed_batch` chia lô 100 văn bản mỗi request và sắp kết quả theo chỉ số trả về.
- `test_connection` embed chuỗi thử. Thành công trả True với thông điệp "OK — model=…, dimensions=…", thất bại trả False với "OpenAI embedding error: …".

**`OpenAILLM`**

- **Mô hình suy luận:** model_id viết thường chứa một trong gpt-5, gpt-6, o1, o3, o4. Với các mô hình này, không gửi temperature và dùng max_completion_tokens thay cho max_tokens.
- **`generate`:** gửi tin system trước (nếu có), sau đó tin user, rồi trả nội dung của lựa chọn đầu tiên (None thành chuỗi rỗng).
- **`generate_with_tools`:**
  - Chuyển tin nhắn qua neutral_to_openai_messages, chèn system lên đầu.
  - finish_reason: stop thành end_turn, tool_calls thành tool_use, length thành max_tokens, giá trị khác thành end_turn.
  - Arguments không phải JSON hợp lệ thì thành dict rỗng.
- **Langfuse:** tên generation lần lượt là "openai.generate" và "openai.generate_with_tools", kèm usage prompt/completion tokens.
- **`test_connection`:** sinh một câu trả lời rất ngắn với max_tokens 10 và temperature 0.

**`OpenAIVision`** (dùng cho cả openai và anthropic, qua endpoint tương thích OpenAI)

- Gửi ảnh dạng data URL base64 với detail auto. Temperature 0.2, trừ mô hình suy luận.
- Thử tối đa 3 lần, nghỉ 2 giây giữa các lần. Hết lượt thì trả chuỗi rỗng, không ném lỗi.
- Prompt None thì dùng prompt mặc định yêu cầu mô tả chi tiết nội dung ảnh và trích mọi chữ nhìn thấy. Viết lời mới; không chép từ nguồn.
- `test_connection` gửi một ảnh PNG 1×1 tối thiểu.

### 3.2. Anthropic — `app/ai/providers/anthropic_provider.py`

**`AnthropicLLM`**

- Client là AsyncAnthropic, có base_url nếu được cấu hình. max_tokens mặc định 16384. Truyền temperature. System đặt ở trường system riêng.
- `generate` trả text của khối nội dung đầu tiên.
- `generate_with_tools`:
  - Tin nhắn chuyển qua neutral_to_anthropic_messages, tool qua openai_tools_to_anthropic.
  - stop_reason tool_use, end_turn và max_tokens giữ nguyên; giá trị khác thành end_turn.
  - Text được ghép từ các khối text; tool_calls lấy từ các khối tool_use.
- Lỗi khi test_connection trả False với "Anthropic error: …".

### 3.3. Google — `app/ai/providers/google_provider.py`

Client là `genai.Client(api_key)` của gói google-genai.

**`GoogleEmbedding`**

- Gọi embed_content với output_dimensionality bằng dimensions.
- Số token ghi Langfuse được ước lượng bằng max(1, độ dài ký tự chia 4).
- `embed_batch` chạy song song, giới hạn bằng semaphore có dung lượng concurrency.
- **Tiền tố theo tác vụ**, lấy từ extra `task` (dùng cho họ mô hình embedding cần chỉ dẫn tác vụ):

| task | Tiền tố |
|---|---|
| search_query | nhãn "task: search result", rồi "query:" và văn bản |
| question_answering | nhãn "task: question answering", rồi "query:" và văn bản |
| fact_checking | nhãn "task: fact checking", rồi "query:" và văn bản |
| classification, clustering, similarity | nhãn task tương ứng, rồi "query:" và văn bản |
| document | "title: none", rồi "text:" và văn bản |
| khác | văn bản giữ nguyên |

- `with_task(task)` trả một bản sao cấu hình với task mới, dùng chung client.

**`GoogleLLM`**

- Gọi generate_content bất đồng bộ với system_instruction, max_output_tokens và temperature.
- Với tool, function calling ở chế độ AUTO.
- finish_reason:
  - có function call thì là tool_use;
  - lý do kết thúc của mô hình chứa MAX_TOKENS thì là max_tokens;
  - còn lại là end_turn.
- Giữ nguyên nội dung candidate vào raw_provider_content để phát lại.

**`GoogleVision`** gửi ảnh dạng part bytes kèm prompt; lỗi thì trả chuỗi rỗng.

### 3.4. `app/ai/registry.py` — `ProviderRegistry`

Mọi phương thức là phương thức lớp hoặc tĩnh, bất đồng bộ, nhận `db` (AsyncSession). Test patch `ProviderRegistry` trong nhiều module và patch riêng `get_vision`, nên các module dùng nó phải import tên lớp ở cấp module hoặc import lười đúng tên ấy.

**Ánh xạ lớp**

| Loại | provider sang lớp |
|---|---|
| embedding | google thành GoogleEmbedding; openai thành OpenAIEmbedding |
| llm | google thành GoogleLLM; openai thành OpenAILLM; anthropic thành AnthropicLLM |
| vision | google thành GoogleVision; openai và anthropic thành OpenAIVision |

Provider khác ném ValueError với thông báo "Unsupported <loại> provider: …".

**Hằng**

- `ANTHROPIC_OPENAI_BASE_URL = "https://api.anthropic.com/v1/"`
- `DEFAULT_LLM_SPEC_ID = DEFAULT_VISION_SPEC_ID = "openai/gpt-6-luna"`
- `SUPPORTED_PROVIDERS`: dữ liệu mà `supported_providers()` trả về.

**Khóa API cũ.** Khóa bắt đầu bằng "sk-ant-" chỉ dùng được cho anthropic. Khóa khác chỉ dùng được cho provider không phải anthropic.

**Phương thức công khai**

| Phương thức | Hành vi |
|---|---|
| `get_embedding(db, task="document", spec_id=None) -> EmbeddingProvider` | Nạp cấu hình theo spec_id, hoặc theo spec đang active nếu không truyền. Đặt extra task, rồi khởi tạo lớp tương ứng |
| `get_active_embedding_spec_id(db) -> str or None` | Đọc khóa active_embedding_model_spec_id. Hợp lệ khi có trong EMBEDDING_CATALOG, hoặc là custom id trỏ tới một mô hình tùy chỉnh còn tồn tại. Không hợp lệ thì trả None |
| `get_llm(db, spec_id=None) -> LLMProvider` | |
| `get_active_llm_spec_id(db)` | (1) Giá trị lưu thuộc LLM_CATALOG, hoặc là custom hợp lệ: trả giá trị đó. (2) Nếu không, dẫn xuất từ cặp khóa cũ llm_provider và llm_model_id bằng derive_spec_id. (3) Nếu vẫn không được mà có giá trị lưu: ghi cảnh báo, trả DEFAULT_LLM_SPEC_ID. (4) Không có gì: trả None |
| `get_vision(db, spec_id=None) -> VisionProvider or None` | Trả None khi cấu hình gây ValueError |
| `get_active_vision_spec_id(db)` | Như với LLM, dùng vision_provider, vision_model_id và DEFAULT_VISION_SPEC_ID |
| `test_all(db) -> dict` | Khóa embedding, llm, vision; mỗi giá trị là bộ (bool, thông điệp). Loại nào thiếu cấu hình thì trả (False, "Not configured: <lý do>") |
| `supported_providers() -> dict` | Khóa embedding, llm, vision; mỗi khóa là danh sách provider {id, name, models}. Tên hiển thị: google "Google Gemini", openai "OpenAI", anthropic "Anthropic", ollama "Ollama", voyage "Voyage AI", cohere "Cohere". Mỗi model chỉ chứa các trường có giá trị trong số: id, model_id, label, context_window_tokens, max_output_tokens, supports_tools, supports_vision, dimension, max_input_tokens, các trường chi phí, notes |

**Nạp cấu hình**

- **Mô hình tùy chỉnh** (spec id bắt đầu "custom/", xem 04 §16–17): tra bản ghi mô hình tùy chỉnh.
  - Bản ghi đã bị xóa: ValueError "Custom model … was deleted. Pick another model in Settings."
  - provider lấy từ trường protocol của bản ghi. api_key lấy từ khóa cấu hình custom_model_api_key__<id>; rỗng thì dùng "none". base_url lấy từ bản ghi.
- **Embedding:**
  - Không có spec: ValueError "No active embedding model. Pick one in Settings → Embedding."
  - Mô hình tùy chỉnh: send_dimensions False.
  - Preset: khóa API lấy theo thứ tự embedding_api_key__<provider>, rồi khóa cũ embedding_api_key, rồi rỗng. base_url từ embedding_base_url. dimensions = spec.dimension. extra có spec_id.
- **LLM:**
  - Không có spec: ValueError "No active LLM. Pick one in Settings → LLM."
  - Khóa API là llm_api_key__<provider>, rồi khóa cũ llm_api_key nếu phù hợp provider. base_url None. spec = spec.
- **Vision:**
  - Không có spec: ValueError "No active vision model. Pick one in Settings → Vision."
  - Khóa API lấy như LLM nhưng với vision_api_key__<provider> và vision_api_key. Riêng anthropic dùng base_url = ANTHROPIC_OPENAI_BASE_URL.

### 3.5. Danh mục mô hình

#### `app/ai/llm_catalog.py`

**`LLMModelSpec`** (dataclass bất biến) gồm id, provider, model_id, context_window_tokens, max_output_tokens, supports_tools, supports_vision, label, cost_per_1m_input_tokens, cost_per_1m_output_tokens, notes.

**`LLM_CATALOG`** là dict từ id sang spec. Mọi mục có supports_tools và supports_vision bằng True.

| id | context_window | max_output | Chi phí in/out (USD / 1M token) |
|---|---|---|---|
| openai/gpt-6-luna | 400000 | 128000 | không ghi |
| anthropic/claude-sonnet-5-5 | 1000000 | 64000 | không ghi |
| anthropic/claude-opus-5-5 | 1000000 | 64000 | không ghi |
| anthropic/claude-haiku-5-5 | 200000 | 64000 | không ghi |
| google/gemini-3.1-pro | 1000000 | 65000 | 1.25 / 10.0 |
| google/gemini-3.5-flash | 1048576 | 65536 | 0.5 / 3.0 |
| google/gemini-3.1-flash-lite | 1048576 | 65536 | 0.25 / 1.50 |

Quy ước chung: model_id là phần sau dấu "/" của id, provider là phần trước. Label là tên dễ đọc.

| Hàm | Hành vi |
|---|---|
| `get_spec(spec_id)` | Custom id ("custom/<…>/<model>") trả spec với provider "custom", context 128000, output 8192, tools True, vision False, label = model. Id lạ ném `UnknownLLMModel` (lớp con KeyError) với thông báo "Unknown LLM model spec_id=… Valid IDs: …" |
| `list_specs()` | |
| `list_specs_by_provider(provider)` | |
| `derive_spec_id(provider, model_id) -> str or None` | Ghép provider/model_id nếu kết quả có trong danh mục, ngược lại None |

#### `app/ai/vision_catalog.py`

**`VisionModelSpec`** gồm id, provider, model_id, max_image_size_mb, label, cost_per_1m_input_tokens, cost_per_image, notes.

| id | max_image_size_mb |
|---|---|
| openai/gpt-6-luna | 20 |
| anthropic/claude-sonnet-5-5 | 5 |
| anthropic/claude-haiku-5-5 | 5 |
| google/gemini-3.5-flash | 20 |
| google/gemini-3.1-flash-lite | 20 (cost_in 0.25) |

- Custom id cho spec với provider "custom" và giới hạn 20 MB. Id lạ ném `UnknownVisionModel` (KeyError).
- Có get_spec, list_specs và derive_spec_id như LLM.

#### `app/ai/embedding_catalog.py`

Xem 04 §4.1. Các điểm bổ sung:

- Label có dạng "<Nhà cung cấp> <model> (<d>d)".
- Custom id "custom/<d>/<model>" chỉ hợp lệ khi d thuộc EMBEDDING_DIMENSIONS (768, 1024, 1536, 3072). Spec của nó có max_input_tokens 8191 và label "<model> (<d>d)".
- `SUPPORTED_DIMENSIONS` là tuple các chiều trong danh mục, sắp tăng dần.
- `specs_for_dimension(d)`.

### 3.6. `app/ai/tracing.py` (loại C)

File đã có trong c2 và giống hệt bản gốc. Không viết lại; chỉ cần đảm bảo nó chạy được với các phụ thuộc sau:

- Settings: langfuse_enabled, langfuse_public_key, langfuse_secret_key, effective_langfuse_host.
- Đủ ba danh mục LLM_CATALOG, VISION_CATALOG, EMBEDDING_CATALOG cùng các trường chi phí.

Giao diện mà các module khác gọi:

| Hàm | Chữ ký và hành vi |
|---|---|
| `get_langfuse()` | Client Langfuse khởi tạo lười. Trả None khi tắt hoặc thiếu khóa |
| `flush_langfuse()`, `shutdown_langfuse()` | Không ném lỗi |
| `trace_context(name, trace_id=None, user_id=None, session_id=None, tags=None, metadata=None, input_data=None)` | Async context manager mở một trace hoặc span cha. Chi tiết ở 06 §10.5 |
| `record_generation(name, model, input_data, output_data, start_time, end_time, usage=None, metadata=None, model_parameters=None, level=None, status_message=None)` | |
| `record_embedding(name, model, input_texts, vector_dimension, tokens=None, metadata=None, level=None, status_message=None)` | |
| `sync_all_models_to_langfuse()` | Đẩy định nghĩa giá mô hình lên Langfuse (06) |

Khi Langfuse không khả dụng, mọi hàm là no-op.

---

## 4. `app/services/config_service.py`

### 4.1. Mã hóa

- Khóa Fernet được dẫn xuất lười: lấy SHA-256 của settings.secret_key rồi mã hóa base64 urlsafe.
- Đổi SECRET_KEY làm các giá trị nhạy cảm đã lưu không giải mã được nữa (xem hành vi của get).

### 4.2. Khóa nhạy cảm — `_is_sensitive(key) -> bool`

Test import trực tiếp hàm này. Trả True khi:

- key thuộc {embedding_api_key, llm_api_key, vision_api_key, ocr_api_key, smtp_password, webhook_secret};
- key bắt đầu bằng một trong embedding_api_key__, llm_api_key__, vision_api_key__, ocr_api_key__;
- key bắt đầu bằng custom_model_api_key__.

`SENSITIVE_KEYS` là tập 4 khóa gốc embedding_api_key, llm_api_key, vision_api_key, ocr_api_key.

### 4.3. Hằng và hàm phụ

| Tên | Giá trị |
|---|---|
| ACTIVE_EMBEDDING_MODEL_KEY | active_embedding_model_spec_id |
| ACTIVE_LLM_MODEL_KEY | active_llm_model_spec_id |
| ACTIVE_VISION_MODEL_KEY | active_vision_model_spec_id |
| `embedding_api_key_for(p)`, `llm_api_key_for(p)`, `vision_api_key_for(p)` | Trả "<loại>_api_key__<p>". p có thể là chuỗi hoặc ProviderType (lấy value) |

### 4.4. `DEFAULT_CONFIG_VALUES`

| Khóa | Mặc định |
|---|---|
| ocr_prompt | Chỉ dẫn OCR tiếng Việt, độ dài phải lớn hơn 20 ký tự (test kiểm tra). Mục đích: trích toàn bộ chữ đúng nguyên văn; giữ số hiệu văn bản, ngày tháng và chữ viết tắt; dựng lại bảng thành bảng Markdown; dựng lại cấu trúc Phần/Chương/Mục/Điều/Khoản/Điểm thành tiêu đề; không thêm bình luận hay lời dẫn. Tự soạn câu chữ |
| ocr_mode | auto |
| ocr_fallback_vision | true |
| ocr_llm_refine | false |
| pdf_parser_engine | pdfplumber |
| excel_parser_engine | openpyxl |
| pdf_strip_headers_footers | true |
| pdf_enhance_headings | true |

Mọi giá trị là chuỗi.

### 4.5. `ALL_CONFIG_KEYS`

Danh sách có thứ tự; UI và get_all dựa vào thứ tự này.

1. active_embedding_model_spec_id, embedding_api_key__google, embedding_api_key__openai, embedding_base_url
2. active_llm_model_spec_id, llm_api_key__openai, llm_api_key__anthropic, llm_api_key__google, llm_api_key, llm_base_url
3. active_vision_model_spec_id, vision_api_key__openai, vision_api_key__anthropic, vision_api_key__google, vision_api_key, vision_base_url
4. ocr_base_url, ocr_api_key, ocr_api_key__openai, ocr_api_key__anthropic, ocr_api_key__google, ocr_model, ocr_prompt, ocr_mode, ocr_fallback_vision, ocr_llm_refine
5. pdf_parser_engine, excel_parser_engine, pdf_strip_headers_footers, pdf_enhance_headings
6. llm_provider, llm_model_id, vision_provider, vision_model_id (khóa cũ)
7. session_timeout_minutes, role_permissions_custom
8. embedding_provider, embedding_model_id, embedding_api_key, embedding_dimensions (khóa cũ)

Khóa custom_model_api_key__<id> không nằm trong danh sách này; luồng mô hình tùy chỉnh ghi riêng (04 §17).

### 4.6. `ConfigService(db)`

| Phương thức (async) | Hành vi |
|---|---|
| `get(key) -> str or None` | **(1)** Truy vấn bản ghi AppConfig theo key bằng một lần `db.execute(...)` rồi gọi `scalar_one_or_none()` trên kết quả. Test mock đúng chuỗi gọi này. Có bản ghi với value khác rỗng thì trả value, giải mã nếu key nhạy cảm; giải mã lỗi thì ghi cảnh báo rồi trả value thô. **(2)** Nếu không, settings có thuộc tính trùng tên với giá trị khác None và khác chuỗi trắng: trả dạng chuỗi. **(3)** Nếu không, có trong DEFAULT_CONFIG_VALUES: trả giá trị đó. **(4)** Còn lại trả None |
| `set(key, value)` | Key nhạy cảm và value khác rỗng thì mã hóa. Upsert bản ghi (cập nhật updated_at), rồi flush. Không commit |
| `get_all() -> dict` | get cho mọi khóa trong ALL_CONFIG_KEYS |
| `get_all_for_ui() -> dict` | Như get_all nhưng che khóa nhạy cảm: giá trị dài hơn 8 ký tự hiện 8 ký tự "•" nối 4 ký tự cuối; giá trị ngắn hơn hiện chuỗi "•" cùng độ dài. Mỗi khóa có thêm `<key>_configured` (bool) |
| `set_batch(updates: dict) -> dict[str, bool]` | Khóa không thuộc ALL_CONFIG_KEYS và không phải custom_model_api_key__… trả False. Giá trị bắt đầu bằng "••••" là giá trị đã che gửi ngược lại: bỏ qua, báo True. Khóa còn lại gọi set rồi báo True |
| `get_effective_config(db)` (tĩnh hoặc lớp) | Trả get_all của một ConfigService mới trên db |

Test patch `app.services.config_service.ConfigService`. Các module dùng ConfigService phải import lười theo đường dẫn module này hoặc import tên ở cấp module, tùy theo test của module đó (xem bảng §7).

---

## 5. Dịch vụ dùng chung khác

| Dịch vụ | Nơi đặc tả | Ghi chú nền tảng |
|---|---|---|
| `app/services/storage_service.py` (singleton `storage_service`) | 03 §4 | Client MinIO tạo lười từ settings.minio_*. Test patch `storage_service.download_file` và `storage_service.upload_stream_async`. `ensure_bucket()` được gọi trong lifespan, /health và seed_skills |
| `app/services/embedding_storage.py` | 04 §5 | |
| `app/services/auth_service.py` | 02 §4 | Xuất require_permission, JWT_EXPIRE_HOURS, create_access_token, hash_password, verify_password, get_current_user |
| `app/services/audit_service.py` | dưới đây | |

**`log_audit(db, user, action, resource_type, resource_id, decision="ALLOW", reason=None)`** (async)

- Ủy quyền cho `audit_chain.record` (06 §10) với principal_id = user.id và các trường còn lại tương ứng. resource_id được chuyển thành chuỗi.
- Ghi trong giao dịch riêng do audit_chain tự mở và commit. Tham số db được giữ để tương thích chữ ký nhưng không dùng.
- Lỗi ghi audit chỉ ghi log, không làm hỏng request gọi.

---

## 6. Tiện ích — `app/utils`

| Hàm | Chữ ký | Hành vi |
|---|---|---|
| `strip_code_fence` | `(raw: str) -> str` | Nếu chuỗi (đã cắt khoảng trắng) được bao bởi hàng rào code Markdown ba dấu backtick, có hoặc không có nhãn ngôn ngữ json/JSON, thì bỏ dòng mở và dòng đóng. Cuối cùng cắt khoảng trắng |
| `parse_json_loose` | `(raw: str) -> Any` | Bỏ hàng rào rồi parse JSON. Thất bại thì cắt chuỗi tại dấu "}" hoặc "]" xuất hiện cuối cùng (lấy vị trí lớn hơn) và parse lại. Không có dấu nào thì ném lại lỗi ban đầu |
| `slugify` | `(text: str) -> str` | Rỗng thì trả rỗng. Chuyển chữ thường. Đổi "đ" và "Đ" thành "d". Chuẩn hóa NFKD rồi bỏ dấu, chỉ giữ ASCII. Mỗi chuỗi liên tiếp ký tự ngoài a–z, 0–9 thay bằng một "-". Bỏ "-" ở hai đầu |
| `count_tokens` (`app/utils/tokens.py`) | `(text: str) -> int` | Bộ mã hóa cl100k_base của tiktoken, khởi tạo một lần, cho phép mọi special token. Chuỗi rỗng trả 0 (03 §10.4) |
| `ProgressTracker`, `WIKI_ACTIVE` (`app/utils/progress.py`) | | 03 §10.3 |

Hai hàm `strip_code_fence` và `parse_json_loose` nằm trong `app/utils/text.py`, cùng với `slugify`.

---

## 7. Giao diện bắt buộc

Các file loại C và 55 file test của c2 import những tên dưới đây. Mọi tên phải tồn tại đúng module và đúng chữ ký. Cột "Bị patch" cho biết test thay thế tên đó bằng mock, nên nơi dùng phải tra tên lúc chạy (import lười hoặc tham chiếu qua module), không được giữ bản sao lúc import.

| Module | Tên | Bị patch | Đặc tả |
|---|---|---|---|
| app.config | settings | Có (gán thuộc tính: audit_hmac_key, sso_role_global_map, …) | 01a §2 |
| app.database | get_db, async_session_factory | async_session_factory (10 chỗ) | 01a §3.1 |
| app.database.models | Base, Source, SourceDepartment, WikiPage, KnowledgeType, LegalUnit, LegalUnitType, LegalRelation, LegalRelationType, Employee, Department, EmployeeDepartment, AppConfig, Skill, AuditLog, AuditChainHead | | 01a §4, các tài liệu miền |
| app.database.repository | Repository | Có (`app.routers.sources.Repository`) | 01a §3.3 |
| app.models.task_failure | TaskFailure, SourceStageTiming, record_task_failure, record_stage_timing | | 03 §3.7–3.9 |
| app.ai.registry | ProviderRegistry (gồm get_vision, get_llm, get_embedding) | Có | 01b §3.4 |
| app.ai.embedding_catalog | get_spec, EMBEDDING_CATALOG | | 04 §4.1 |
| app.ai.llm_catalog | LLM_CATALOG | | 01b §3.5 |
| app.ai.vision_catalog | VISION_CATALOG | | 01b §3.5 |
| app.ai.tracing | record_generation | Có | 01b §3.6 |
| app.ai.agent_protocol | ToolCall, AssistantTurn và các hàm chuyển đổi | | 01b §2.4 |
| app.services.config_service | ConfigService, ALL_CONFIG_KEYS, _is_sensitive, vision_api_key_for, ACTIVE_EMBEDDING_MODEL_KEY, ACTIVE_LLM_MODEL_KEY, ACTIVE_VISION_MODEL_KEY | ConfigService | 01b §4 |
| app.services.audit_service | log_audit | Có | 01b §5 |
| app.services.embedding_storage | các hàm ở 04 §5 | | 04 §5 |
| app.services.storage_service | storage_service (download_file, upload_stream_async, ensure_bucket) | Có | 03 §4 |
| app.services.auth_service | require_permission, JWT_EXPIRE_HOURS, create_access_token | | 02 §4 |
| app.utils.text | slugify, parse_json_loose | | 01b §6 |
| app.worker | ingest_file_task, generate_questions_task, compute_source_dual_status, check_task_attempt_validity, caption_images_task, enqueue_post_extraction_pipeline | | 03 §11, §13 |
| app.main | app | | 01a §6 |
| app.mcp.tools | register_tools, forwarded_role | | 06 |
| app.mcp.resources | register_resources | | 06 |
| alembic/versions/049_audit_hash_chain.py | file nạp theo đường dẫn; upgrade, downgrade | | 06 §10.6, 01a §5.3 |

Kiểm tra hoàn thành:

- `pytest` trong c2 chạy hết 55 file test mà không lỗi import.
- Import `app.main` thành công khi không có PostgreSQL, Redis hay MinIO.
