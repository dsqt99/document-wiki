# 07g — Giao diện Cài đặt hệ thống (màn `/settings`)

Tài liệu này thuộc chuỗi đặc tả giao diện 07 (mục lục: `07_giao_dien.md`; nền tảng chung về layout, theme, biểu tượng, i18n, lớp gọi API: `07a_giao_dien_nen_tang.md`). Phạm vi: trang Cài đặt (route `/settings` trong nhóm route portal) và toàn bộ thành phần trong thư mục `frontend/src/components/settings/`. Ba file đã có sẵn trong c2 (loại C, do nhóm viết) là `custom-model-form.tsx`, `document-processing-settings-card.tsx`, `ocr-settings-card.tsx`; người viết code phải tạo các module còn thiếu sao cho ba file này biên dịch và chạy đúng — xem mục 2 "Giao diện module bắt buộc". Mọi biểu tượng là tên ligature của Google Material Symbols Outlined, hiển thị qua một thẻ span mang lớp biểu tượng chung (xem 07a). Màu được mô tả theo vai trò (primary, muted, destructive, "xanh lá thành công", "hổ phách cảnh báo"…), không ghi giá trị cụ thể.

---

## 1. Tổng quan và quy ước chung

### 1.1 Danh sách file

| File | Trạng thái trong c2 | Export |
|---|---|---|
| `app/(portal)/settings/page.tsx` | phải viết | export mặc định trang `SettingsPage` |
| `components/settings/test-lab.tsx` | phải viết | `TestFileDropzone`, `PreviewStudio`, `Stat`, kiểu `StudioTab` |
| `components/settings/model-catalog-card.tsx` | phải viết | kiểu `ModelSpec`, hàm `canActivate`, `ModelCatalogCard`, `ActivateBar` |
| `components/settings/provider-model-picker.tsx` | phải viết | kiểu `PickerSpec`, `ProviderMark`, `ProviderModelPicker`, `ActiveModelChip` |
| `components/settings/embedding-settings-card.tsx` | phải viết | `EmbeddingSettingsCard` |
| `components/settings/roles-permissions-card.tsx` | phải viết | `RolesPermissionsCard` |
| `components/settings/custom-model-form.tsx` | **có sẵn (loại C)** | `CustomModelKind`, `ProviderGroup`, `PROVIDER_LABELS`, `EditableModel`, `CustomModelForm`, `deleteCustomModel`, `saveCustomModelKey` |
| `components/settings/document-processing-settings-card.tsx` | **có sẵn (loại C)** | `DocumentProcessingSettingsCard` |
| `components/settings/ocr-settings-card.tsx` | **có sẵn (loại C)** | `OcrSettingsCard` |

Tất cả là client component.

### 1.2 Phụ thuộc dùng chung

| Module | Tên dùng | Ghi chú |
|---|---|---|
| `@/lib/api` | `api<T>(path, options?)` | Trả Promise của JSON đã parse. `options`: `method` (mặc định GET), `body` (object → gửi JSON; FormData → gửi multipart, không đặt Content-Type), `headers`, `timeoutMs` (mặc định 60 000 ms). Lỗi HTTP ném Error có `message` = trường `detail` của phản hồi, hoặc "API Error {status}". Các card hiển thị `message` này nguyên văn. |
| `@/lib/auth` | `useAuth()` → `user`, `hasPermission(perm)`, `logout()` | xem đặc tả xác thực |
| `@/lib/embed` | `useIsEmbedded()` → boolean | có trong c2 |
| `@/lib/i18n` | `useI18n()` → `t(key, fallback)` | có trong c2 |
| `@/components/shared/page-header` | `PageHeader` props `title` (string), `description?` (string), `action?` (node) | |
| `@/components/ui/*` | `Button` (variant `default`/`outline`/`ghost`, size `sm`…), `Input`, `Label`, `Switch` (props `checked`, `onCheckedChange`), `Badge` (variant `outline`), `Tabs`/`TabsList` (variant `line`)/`TabsTrigger`/`TabsContent` | shadcn kiểu base-nova trên @base-ui/react |
| `@/components/wiki/wiki-content` | `WikiContent` prop `markdown` (string) | bộ render Markdown dùng chung của wiki |

### 1.3 Khóa i18n liên quan (trong `frontend/src/lib/i18n.tsx`)

Trang nguồn chủ yếu dùng chuỗi tiếng Việt cố định; chỉ thẻ Embedding gọi `t("settings.embeddingTitle", …)`. Các khóa sẵn có nên dùng khi muốn i18n hóa:

| Khóa | VI | EN |
|---|---|---|
| `nav.settings` | Cài đặt hệ thống | Settings |
| `settings.title` | Cài đặt hệ thống | Settings |
| `settings.description` | Cấu hình các nhà cung cấp AI cho vector hóa, mô hình LLM và thị giác máy tính. | … |
| `settings.embeddingTitle` | Mô hình Embedding | Embedding Model |
| `settings.embeddingDesc` | Chọn mô hình vector hóa tri thức và lưu khóa API. | |
| `settings.backfillChunks` | Index chunk thô cho tài liệu cũ | Backfill raw chunks |
| `settings.backfillingChunks` | Đang xếp hàng… | Queuing… |
| `settings.backfillQueued` | Đã xếp hàng job index chunk thô | Backfill job queued |
| `settings.backfillChunksHint` | Tạo chunk thô (nhánh A) cho tài liệu tải lên trước khi có dual pipeline | |
| `settings.active` | Đang hoạt động | Active |
| `settings.llmTitle` / `settings.llmDesc` | Mô hình LLM / Sử dụng cho trích xuất thực thể, lập kế hoạch và biên soạn wiki. | LLM Model / Used for entity extraction, planning, and wiki compilation. |
| `settings.visionTitle` / `settings.visionDesc` | Mô hình Thị giác (Vision) / … phân tích và trích xuất hình ảnh … | Vision Model / Used for image analysis during document ingestion. |
| `settings.saving`, `settings.cancel`, `settings.pasteKey`, `settings.apiKeyFor`, `settings.apiKeySaved`, `settings.replaceKey` | Đang lưu… / Hủy bỏ / Dán khóa API / Khóa API cho / ✓ đã lưu / Thay đổi khóa hiện có… | |

Khi trang nguồn dùng chuỗi cứng, đặc tả trích chuỗi đó trong ngoặc kép; giữ đúng nguyên văn để test giao diện khớp.

### 1.4 Khung chung của một "card"

Mỗi card là khối nền `card`, bo góc lớn, viền mảnh, bóng nhẹ, đệm trong khoảng 24px, các phần con xếp dọc cách nhau 16–20px. Đầu card: ô biểu tượng vuông bo góc (nền là màu nhấn nhạt, biểu tượng màu nhấn), bên phải là tiêu đề (cỡ base, đậm vừa) và mô tả (cỡ xs, màu muted); với card model thì góc phải có `ActiveModelChip`.

---

## 2. Giao diện module bắt buộc

Đây là hợp đồng mà ba file loại C phụ thuộc. Tên export, tên prop, kiểu, tính bắt buộc phải đúng như dưới.

### 2.1 Từ `custom-model-form.tsx` (đã có, chỉ để tham chiếu)

| Export | Loại | Mô tả |
|---|---|---|
| `CustomModelKind` | kiểu | một trong `"llm"`, `"vision"`, `"embedding"`, `"ocr"` |
| `ProviderGroup` | kiểu | một trong `"anthropic"`, `"openai"`, `"google"`, `"custom"` |
| `PROVIDER_LABELS` | hằng | ánh xạ nhóm → nhãn: anthropic → "Anthropic", openai → "OpenAI", google → "Gemini", custom → "Custom" |
| `EditableModel` | kiểu | `id` string, `model_id` string, `label` string, `base_url?` string hoặc null, `protocol?` string hoặc null, `dimension?` number |
| `CustomModelForm` | component | props: `kind` (CustomModelKind, bắt buộc), `provider?` (ProviderGroup, mặc định `"custom"`), `existingModelIds?` (string[], mặc định rỗng — các model_id đã có, bị ẩn khỏi dropdown gợi ý), `initial?` (EditableModel — có = chế độ sửa), `onSaved(id: string)` (bắt buộc), `onCancel()` (bắt buộc). Gọi `POST /api/settings/custom-models`, `POST /api/settings/models/discover`, `POST /api/settings/embeddings/probe-dimension`. |
| `deleteCustomModel(kind, id)` | hàm async | `DELETE /api/settings/custom-models?kind={kind}&id={id}` |
| `saveCustomModelKey(kind, spec, apiKey)` | hàm async | `spec` gồm `id`, `model_id`, `label`, `group?`, `base_url?`, `protocol?`, `dimension?`. Gửi `POST /api/settings/custom-models` với body: `kind`, `provider` = `spec.group` (mặc định "custom"), `model_id`, `label`, `base_url`, `protocol` (mặc định "openai"), `dimension` (chỉ khi kind = embedding), `api_key` = apiKey, `original_id` = `spec.id`. |

### 2.2 `test-lab.tsx`

#### 2.2.1 `TestFileDropzone`

| Prop | Kiểu | Bắt buộc | Mặc định | Ý nghĩa |
|---|---|---|---|---|
| `file` | File hoặc null | có | — | file đang chọn |
| `onFile` | hàm (file: File) → void | có | — | gọi khi chọn hoặc thả file |
| `onClear` | hàm () → void | có | — | gọi khi bấm nút gỡ file |
| `accept` | string | có | — | chuỗi accept của input file (vd `.pdf,.docx,…` hoặc `image/png,…`) |
| `hint` | string | có | — | dòng gợi ý định dạng ở trạng thái trống |
| `thumbnailUrl` | string hoặc null | không | không có | URL ảnh thu nhỏ (object URL) hiển thị thay biểu tượng file |

Hành vi:
- Toàn khối là vùng có vai trò nút, focus được bằng Tab; Enter hoặc Space mở hộp chọn file; click cũng mở hộp chọn file (input file ẩn, chỉ lấy file đầu).
- Kéo file vào: viền nét đứt chuyển màu primary, nền primary nhạt. Rời ra: trở lại. Thả: lấy file đầu tiên, gọi `onFile`.
- Sau khi chọn qua input, giá trị input được reset để chọn lại cùng file vẫn kích hoạt.
- Trạng thái trống: vòng tròn nền primary nhạt chứa biểu tượng `upload_file` (phóng nhẹ khi hover), dòng chính "Kéo thả file hoặc bấm để chọn" (đậm, xs), dòng phụ = `hint`.
- Trạng thái có file: viền primary mờ; trái là ô 40px chứa ảnh `thumbnailUrl` (cắt phủ) hoặc biểu tượng `description` màu primary; giữa là nhãn đuôi file viết hoa (chip nhỏ font mono; màu theo đuôi: pdf → tông hồng/đỏ, xlsx/xls/csv → tông xanh lục, docx/doc → tông xanh dương, khác → tông xám), tên file (cắt bớt khi dài), dòng dưới "{dung lượng} · Nhấn để đổi file" (dung lượng ≥ 1 MB hiển thị "x.x MB", ngược lại "x.x KB"); phải là nút biểu tượng `close` (tooltip "Gỡ file") — bấm gọi `onClear` và không mở hộp chọn file.

#### 2.2.2 `StudioTab` (kiểu)

| Trường | Kiểu | Bắt buộc |
|---|---|---|
| `key` | string | có |
| `label` | string | có |
| `badge` | string | không |

#### 2.2.3 `PreviewStudio`

| Prop | Kiểu | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `title` | string | có | tiêu đề thanh công cụ |
| `icon` | string | có | tên Material Symbol cạnh tiêu đề (màu primary) |
| `loading` | boolean | có | đang chạy |
| `loadingTitle` | string | có | chữ dưới hiệu ứng quét khi loading |
| `content` | string hoặc null | có | Markdown hiển thị; **null = chưa có gì** (hiện trạng thái trống); chuỗi rỗng/chỉ khoảng trắng = có kết quả nhưng không có nội dung |
| `error` | string hoặc null | không | thông báo lỗi; có giá trị thì hiện khối lỗi |
| `successLabel` | string hoặc null | không | chip thành công cạnh tiêu đề |
| `telemetry` | node | không | nội dung thanh số liệu (thường là các `Stat`) |
| `tabs` | StudioTab[] | không | danh sách tab con; chỉ hiển thị khi có **nhiều hơn 1** tab |
| `activeTab` | string | không | key tab đang chọn |
| `onTab` | hàm (key: string) → void | không | đổi tab |
| `downloadName` | string | có | tên file khi tải .md |
| `emptyTitle` | string | có | tiêu đề trạng thái trống |
| `emptyHint` | string | có | gợi ý trạng thái trống (rộng tối đa ~300px) |

Bố cục từ trên xuống:
1. **Thanh công cụ** (nền muted nhạt, viền dưới, chữ xs, không chọn được chữ): trái = biểu tượng `icon` + `title` (đậm); nếu có `successLabel` thì chip tròn viền xanh lá có chấm tròn xanh lá + chữ. Phải = công tắc hai nút "Rendered" / "Raw" (nút đang chọn nền primary), rồi ba nút biểu tượng ghost nhỏ: sao chép (`content_copy`, đổi thành `check` trong 2 giây sau khi bấm; tooltip "Sao chép"; vô hiệu khi không có content), tải về (`download`; tooltip "Tải về .md"; vô hiệu khi không có content; tạo file Markdown UTF-8 tên `downloadName`), toàn màn hình (`open_in_full` / khi đang mở rộng là `close_fullscreen`; tooltip "Toàn màn hình" / "Thu nhỏ (Esc)").
2. **Thanh telemetry** (chỉ khi có `telemetry`): hàng ngang xuống dòng được, font mono 11px, màu muted.
3. **Thanh tab** (chỉ khi `tabs` có > 1 phần tử): hàng nút cuộn ngang; nút đang chọn (`activeTab`) nền primary, còn lại nền muted; nếu tab có `badge` thì kèm chip nhỏ font mono tông xanh dương (vd "OCR").
4. **Vùng nội dung** (cuộn dọc, cao tối đa ~520px khi không mở rộng; khung tổng cao tối thiểu ~420px), ưu tiên:
   - `loading` → ô vuông bo góc nền primary nhạt chứa biểu tượng `document_scanner` nhấp nháy và một vạch sáng chạy lên xuống (hiệu ứng quét, chu kỳ ~2 giây), dưới là `loadingTitle`.
   - `error` → khối nền destructive nhạt, biểu tượng `error`, tiêu đề "Thử nghiệm thất bại", dưới là thông báo lỗi font mono, ngắt từ mọi chỗ.
   - `content` khác null: nếu sau khi bỏ khoảng trắng còn nội dung → chế độ Rendered dùng `WikiContent` (kiểu prose cỡ nhỏ, đảo màu ở dark mode); chế độ Raw là khối pre nền tối, chữ sáng, font mono, giữ xuống dòng. Nếu rỗng → chữ giữa "Trang này không có nội dung."
   - còn lại (null) → trạng thái trống: ô biểu tượng `find_in_page` mờ, `emptyTitle` (đậm), `emptyHint`.
- **Toàn màn hình**: khung chuyển sang cố định, cách mép màn hình ~16px, nằm trên lớp phủ tối mờ; bấm lớp phủ hoặc phím Esc để thoát. Bỏ giới hạn chiều cao vùng nội dung.
- Trạng thái nội bộ (chế độ xem, đã sao chép, mở rộng) không đưa ra ngoài.

#### 2.2.4 `Stat`

Props: `icon` (string, bắt buộc), `children` (node, bắt buộc). Hiển thị một cặp nội tuyến: biểu tượng cỡ ~13px rồi nội dung, cách nhau nhỏ. Dùng trong thanh telemetry.

### 2.3 `model-catalog-card.tsx`

#### 2.3.1 `ModelSpec` (kiểu — chung cho phản hồi catalog LLM và Vision)

| Trường | Kiểu | Ghi chú |
|---|---|---|
| `id` | string | id spec |
| `provider` | string | |
| `group` | string | "anthropic" / "openai" / "google" / "custom" |
| `model_id` | string | |
| `label` | string | |
| `notes` | string hoặc null | |
| `api_key_configured` | boolean | |
| `api_key_config_key` | string hoặc null | khóa app_config chứa key của preset; null với model custom |
| `custom` | boolean | |
| `base_url` | string hoặc null | |
| `protocol` | string hoặc null | |
| `context_window_tokens?` | number | LLM |
| `max_output_tokens?` | number | LLM |
| `supports_tools?` | boolean | LLM |
| `supports_vision?` | boolean | LLM |
| `cost_per_1m_input_tokens?` | number hoặc null | |
| `cost_per_1m_output_tokens?` | number hoặc null | LLM |
| `max_image_size_mb?` | number | Vision |
| `cost_per_image?` | number hoặc null | Vision |

Phản hồi catalog: `active_spec_id` (string hoặc null), `specs` (ModelSpec[]).

#### 2.3.2 `canActivate(spec)`

Tham số: object có `group` (string) và `api_key_configured` (boolean), hoặc null. Trả về true khi và chỉ khi spec khác null **và** (`group` = "custom" **hoặc** `api_key_configured` = true). Nghĩa là model custom luôn kích hoạt được (endpoint có thể không cần key); model của nhà cung cấp cần đã lưu key.

#### 2.3.3 `ActivateBar`

| Prop | Kiểu | Bắt buộc | Mặc định | Ý nghĩa |
|---|---|---|---|---|
| `willSwitch` | boolean | có | — | model đang chọn khác model đang dùng |
| `ready` | boolean | có | — | thường = `canActivate(selected)` |
| `busy` | boolean | có | — | đang gọi chuyển |
| `saved` | boolean | có | — | vừa chuyển xong |
| `error` | string | có | — | chuỗi lỗi; rỗng = không lỗi |
| `label` | string | không | — | nhãn model đang chọn, dùng trong cảnh báo |
| `onActivate` | hàm () → void | có | — | bấm nút chính |
| `actionText` | string | không | "Dùng model này" | chữ nút chính |
| `disabled` | boolean | không | false | vô hiệu thêm |
| `children` | node | không | — | chèn ngay sau nút chính (vd nút Ping của OCR) |

Hiển thị: hàng ngang xuống dòng được, viền trên mảnh, đệm trên ~12px. Thứ tự:
1. Nút chính (nền primary, chữ sm): chữ "Đang chuyển…" khi `busy`, ngược lại `actionText`. Vô hiệu khi `!willSwitch` hoặc `!ready` hoặc `busy` hoặc `disabled`.
2. `children`.
3. Nếu `willSwitch` và `!ready`: chữ hổ phách "Lưu API key của nhà cung cấp trước khi dùng {label}."
4. Nếu `!willSwitch` và `!saved` và không có lỗi: chữ muted "Model đang chọn là model đang dùng."
5. Nếu `saved`: chữ xanh lá với biểu tượng `check_circle` "Đã chuyển model".
6. Nếu có `error`: chữ destructive = error.

#### 2.3.4 `ModelCatalogCard`

| Prop | Kiểu | Bắt buộc |
|---|---|---|
| `title` | string | có |
| `description` | string | có |
| `icon` | string | có |
| `catalogUrl` | string | có |
| `switchUrl` | string | có |
| `kind` | CustomModelKind | có |
| `renderMeta` | hàm (spec: ModelSpec) → node | không |

Hành vi:
- Khi mount: gọi song song `GET {catalogUrl}` và `GET /api/settings`. Lưu catalog và settings. Model được chọn: giữ lựa chọn trước nếu id vẫn còn trong specs, ngược lại = `active_spec_id`, ngược lại = spec đầu tiên, ngược lại null. Lỗi: hiện message, mặc định "Failed to load {title}".
- Chưa có catalog: card chỉ có chữ "Loading {title viết thường}…" và dòng lỗi (nếu có).
- Đã có: đầu card (ô biểu tượng `icon` 36px, tiêu đề, mô tả, `ActiveModelChip` của spec đang dùng); `ProviderModelPicker` (truyền `kind`, `specs`, `activeId` = active_spec_id, `selectedId`, `onSelect`, `settings`, `onChanged` = hàm tải lại, `renderMeta`); `ActivateBar` (`willSwitch` = có model chọn và khác active; `ready` = canActivate(spec chọn); `label` = nhãn spec chọn).
- Kích hoạt: `POST {switchUrl}` body `{ "model_spec_id": <id chọn> }` → tải lại → `saved` = true trong 2,5 giây. Lỗi: message hoặc "Switch failed".

### 2.4 `provider-model-picker.tsx`

#### 2.4.1 `PickerSpec` (kiểu — trường tối thiểu mọi catalog trả về)

| Trường | Kiểu | Bắt buộc |
|---|---|---|
| `id` | string | có |
| `label` | string | có |
| `model_id` | string | có |
| `group` | string | có |
| `custom` | boolean | có |
| `api_key_configured` | boolean | có |
| `base_url` | string hoặc null | không |
| `protocol` | string hoặc null | không |
| `dimension` | number | không |
| `notes` | string hoặc null | không |

Một giá trị `group` không thuộc 4 nhóm được coi là "custom".

#### 2.4.2 `ProviderMark`

Props: `group` (string, bắt buộc), `className` (string, mặc định rỗng). Chip vuông nhỏ (cao ~20px, chữ 10px đậm). Nội dung: chữ cái đầu của nhãn nhà cung cấp ("A", "O", "G"); nhóm custom hiển thị biểu tượng `dns`. Màu theo nhóm: anthropic → tông cam đất; openai → tông xanh lục; google → tông xanh dương; custom → tông xám. Mỗi nhóm cũng có một "màu chấm" đậm cùng tông, dùng cho chấm báo trên tab.

#### 2.4.3 `ActiveModelChip`

Props: `spec` (PickerSpec hoặc null, bắt buộc).
- null → chữ hổ phách cỡ xs "Chưa chọn model".
- Có → chip tròn viền mảnh nền muted: `ProviderMark` cỡ nhỏ (~16px), nhãn model (đậm vừa, cắt khi dài), rồi "· {nhãn nhà cung cấp}" màu muted.

#### 2.4.4 `ProviderModelPicker` (generic theo kiểu spec mở rộng PickerSpec)

| Prop | Kiểu | Bắt buộc | Mặc định | Ý nghĩa |
|---|---|---|---|---|
| `kind` | CustomModelKind | có | — | loại model; truyền cho `CustomModelForm` và các hàm custom-model |
| `keyKind` | string | không | = `kind` | tiền tố khóa cấu hình của key nhà cung cấp |
| `specs` | S[] | có | — | danh sách model |
| `activeId` | string hoặc null | có | — | id model đang dùng |
| `selectedId` | string hoặc null | có | — | id model đang chọn (radio) |
| `onSelect` | hàm (id: string) → void | có | — | chọn model |
| `settings` | object (khóa → giá trị) | có | — | payload `GET /api/settings` (key đã che) |
| `onChanged` | hàm () → Promise | có | — | tải lại dữ liệu card sau khi lưu/xóa |
| `onProviderKeySaved` | hàm (group: ProviderGroup) → Promise | không | — | gọi sau khi lưu key nhà cung cấp, trước `onChanged` |
| `renderMeta` | hàm (spec: S) → node | không | — | dòng thông tin phụ cho model **không** custom |
| `disabled` | boolean | không | false | khóa mọi tương tác (vd embedding đang chạy job) |
| `keyFallbackHint` | string | không | — | chữ hiển thị khi nhà cung cấp không có key riêng nhưng đã có key dùng chung từ nơi khác (OCR dùng key Vision) |

**Tab nhà cung cấp** (lưới 4 cột, khung viền nền muted nhạt; vai trò tablist, mỗi nút vai trò tab với aria-selected): thứ tự Anthropic, OpenAI, Gemini, Custom. Mỗi tab: `ProviderMark`, nhãn, số lượng model của nhóm (ẩn trên màn hẹp); nếu model đang dùng thuộc nhóm thì có chấm tròn nhỏ màu nhóm ở góc trên phải (tooltip "Model đang dùng thuộc nhóm này"). Tab đang chọn nền background có bóng nhẹ. Tab ban đầu = nhóm của model đang dùng, nếu không có thì nhóm của model đang chọn, nếu không thì nhóm của spec đầu, mặc định custom. Đổi tab: đóng form thêm/sửa và xóa thông báo.

**Trường hợp đặc biệt**: `kind` = embedding và tab = anthropic → thay toàn bộ nội dung bằng khung viền nét đứt có biểu tượng `info`: "Anthropic không cung cấp model embedding. Dùng OpenAI, Gemini, hoặc thêm endpoint embedding riêng (vd: Voyage AI) ở tab **Custom**."

**Khung key nhà cung cấp** (chỉ tab khác custom): khóa cấu hình = `{keyKind}_api_key__{tab}` (vd `llm_api_key__openai`, `ocr_api_key__google`). Giá trị che lấy từ `settings[khóa]` nếu là chuỗi không rỗng.
- Dòng đầu: trái "API key {Nhà cung cấp}"; phải: nếu có giá trị che → xanh lá `check_circle` "Đã lưu"; nếu không có giá trị che nhưng nhóm có ít nhất một model không custom với `api_key_configured` = true và có `keyFallbackHint` → hiện `keyFallbackHint` màu muted; còn lại → hổ phách "Chưa có key".
- Ô nhập key (xem "KeyInput" dưới) placeholder "Dán API key {Nhà cung cấp}", nút "Lưu key" (viền, nhỏ) chỉ bật khi giá trị đã trim không rỗng, không chứa ký tự che "•", không bận, không disabled.
- Chú thích: "Dùng chung cho mọi model {Nhà cung cấp} ở mục này."
- Lưu: `PUT /api/settings` body `{ "settings": { "<khóa>": "<key đã trim>" } }` → xóa giá trị đang gõ → gọi `onProviderKeySaved(tab)` (nếu có) → `onChanged()` → thông báo thành công "Đã lưu API key {Nhà cung cấp}".

**KeyInput** (nội bộ): ô nhập font mono cao ~32px. Nếu giá trị chứa "•" (đang hiện mặt nạ của key đã lưu) → kiểu text; focus vào thì xóa trống để gõ; blur khi trống thì khôi phục mặt nạ. Khi đang gõ key thật → kiểu password, có nút mắt bên phải (`visibility` / `visibility_off`, tooltip "Hiện key" / "Ẩn key").

**Danh sách model của tab** (radio, name = `{kind}-model`):
- Rỗng và không đang thêm: khung nét đứt căn giữa — tab custom: "Chưa có model custom. Thêm endpoint OpenAI-compatible (vLLM, Ollama, LiteLLM…) bên dưới."; tab khác: "Chưa có model {Nhà cung cấp}."
- Mỗi dòng là label bọc radio: viền primary + nền primary nhạt khi đang chọn. Nội dung: nhãn (sm, đậm vừa); chip "Tự thêm" nếu custom; chip xanh lá "Đang dùng" nếu là active; ở tab custom nếu không có key thì chữ nhỏ "không key". Dòng mono: `model_id`, thêm " · {base_url}" ở tab custom, thêm " · {dimension}d" khi kind = embedding và có dimension. Nếu không custom và có `renderMeta` → dòng meta. Nếu có `notes` → dòng nghiêng mờ.
- Model custom có hai nút biểu tượng bên phải: `edit` (tooltip "Sửa model"; mở `CustomModelForm` tại chỗ với `initial` = spec, `provider` = tab, `existingModelIds` = model_id các spec khác trong tab) và `delete` (tooltip "Xóa model"; vô hiệu khi là model đang dùng, khi đó tooltip "Model đang dùng — chuyển sang model khác trước khi xóa"). Xóa: hộp confirm của trình duyệt "Xóa model \"{label}\"?" → `deleteCustomModel(kind, id)` → `onChanged()` → "Đã xóa model".
- Sửa xong (`onSaved(id)`): đóng form; nếu spec đang sửa là spec đang chọn thì `onSelect(id mới)`; `onChanged()`; thông báo "Đã lưu thay đổi".
- `disabled`: radio và nút bị khóa, con trỏ "không cho phép", độ mờ giảm.

**Key riêng của model custom**: khi tab = custom và model đang chọn thuộc nhóm custom → dưới danh sách hiện "API key · {label}", KeyInput (mặt nạ "••••••••" nếu `api_key_configured`, placeholder "Bỏ trống nếu endpoint không cần key"), nút "Lưu key" (bật như trên). Lưu: `saveCustomModelKey(kind, spec, key đã trim)` → `onChanged()` → "Đã lưu API key của model".

**Thêm model**: link chữ primary có biểu tượng `add`: tab custom "Thêm model custom (base URL + API key)", tab khác "Thêm model {Nhà cung cấp}". Bấm → hiện `CustomModelForm` (`kind`, `provider` = tab, `existingModelIds` = model_id trong tab). `onSaved(id)` → đóng form, `onSelect(id)`, `onChanged()`. `onCancel` đóng form.

**Thông báo**: dòng xs cuối khối; thành công màu xanh lá, tự ẩn sau 2,5 giây; lỗi màu destructive (message hoặc "Thao tác thất bại"), không tự ẩn. Mọi thao tác đặt cờ bận để khóa các nút.

Lưu ý: picker chỉ lưu key và quản lý model custom; việc **kích hoạt** model do card cha thực hiện (mỗi loại có endpoint riêng).

---

## 3. Trang Cài đặt (`/settings`)

### 3.1 Route và quyền

- Đường dẫn `/settings`, thuộc nhóm route portal (có sidebar/topbar chung). Mục sidebar dùng khóa `nav.settings`, biểu tượng `settings`, hiện khi người dùng có `org:settings:read`.
- Trang đọc tham số truy vấn nên phải bọc trong ranh giới Suspense; fallback là spinner (biểu tượng `progress_activity` xoay, cỡ ~30px, màu muted, căn giữa, đệm dọc lớn).
- Chưa có `user` (đang tải phiên) → spinner như trên.
- Có user nhưng **không** có quyền `org:settings:manage` → khối căn giữa rộng tối đa ~448px:
  - "Tài khoản này không có quyền mở cài đặt Kho tri thức" (sm, đậm vừa)
  - "Đang đăng nhập Kho tri thức bằng **{email}**. Đăng xuất rồi đăng nhập lại bằng tài khoản quản trị (SSO) để tiếp tục." (xs, muted; email in đậm)
  - Nút primary "Đăng xuất" → `logout()`.

### 3.2 Đầu trang

`PageHeader` với title "Cài đặt" và description "Nhà cung cấp AI cho embedding, LLM, xử lý ảnh và phân quyền theo vai trò." (có thể dùng `settings.title` / `settings.description` nếu i18n hóa).

### 3.3 Tab

| Thứ tự | Giá trị | Nhãn | Biểu tượng | Nội dung |
|---|---|---|---|---|
| 1 | `config` (mặc định) | "Cấu hình" | `tune` | các card cấu hình, xếp dọc cách nhau ~24px |
| 2 | `permissions` | "Ma trận phân quyền" | `admin_panel_settings` | `RolesPermissionsCard` |

- Tab ban đầu lấy từ tham số truy vấn `?tab=`; giá trị không thuộc danh sách → `config`. Không dùng hash. Khi `?tab=` đổi trong lúc trang đang mở, bộ tab phải khởi tạo lại theo giá trị mới (vd gắn khóa render theo tab ban đầu). Đổi tab bằng click không cập nhật URL.
- Thanh tab dạng gạch chân (variant `line`); khi trang chạy nhúng (`useIsEmbedded()` = true) thì **ẩn** thanh tab (nội dung tab theo URL vẫn hiển thị).
- Cả hai tab cùng yêu cầu `org:settings:manage` (đã chặn ở 3.1). Ghi chú backend: `GET /api/rbac/matrix` cần `org:employees:read`, `PUT /api/rbac/matrix` cần `org:roles:manage`.

Thứ tự card trong tab `config`:
1. `DocumentProcessingSettingsCard` (có sẵn)
2. `OcrSettingsCard` (có sẵn)
3. `EmbeddingSettingsCard`
4. `ModelCatalogCard` LLM: title "LLM Model", description "Used for entity extraction, planning, and wiki compilation." (khớp `settings.llmTitle`/`settings.llmDesc` bản EN), icon `psychology`, catalogUrl `/api/settings/llm/catalog`, switchUrl `/api/settings/llm/switch`, kind `llm`, renderMeta = meta LLM.
5. `ModelCatalogCard` Vision: title "Vision Model", description "Used for image analysis during document ingestion.", icon `visibility`, catalogUrl `/api/settings/vision/catalog`, switchUrl `/api/settings/vision/switch`, kind `vision`, renderMeta = meta Vision.

### 3.4 Định dạng meta

Định dạng số token: không có/0 → "—"; ≥ 1 000 000 → "{n}M" (số nguyên nếu chia hết, ngược lại 1 chữ số thập phân); ≥ 1 000 → "{làm tròn}k"; còn lại nguyên số. Định dạng tiền: null → "—", ngược lại "$" + 2 chữ số thập phân.

- **Meta LLM** (hàng xuống dòng được, các mục cách nhau): "Context: {token} tokens", "Out: {token}", chữ "tools" màu xanh lá nếu `supports_tools`, chữ "vision" màu xanh dương nếu `supports_vision`, "{giá in} in / {giá out} out per 1M".
- **Meta Vision**: "Max image: {max_image_size_mb} MB", "{giá in} per 1M input tokens", và "{giá} / image" nếu `cost_per_image` khác null.

---

## 4. Card "Bóc tách tài liệu" (`DocumentProcessingSettingsCard`, có sẵn)

Mô tả để đối chiếu hành vi và backend.

- Đầu card: biểu tượng `document_scanner` (tông xanh dương), tiêu đề "Bóc tách tài liệu", mô tả "Engine chuyển PDF / Excel sang Markdown và cách xử lý trang scan khi upload."
- Tải: `GET /api/settings`, đọc các khóa `pdf_parser_engine` (mặc định `pdfplumber`; giá trị cũ `pymupdf4llm`/`pymupdf` quy về `pdfplumber`, `pymupdf_plain` quy về `pdfium_plain`), `excel_parser_engine` (mặc định `openpyxl`), `ocr_mode` (mặc định `auto`), `pdf_strip_headers_footers` và `pdf_enhance_headings` (bật trừ khi giá trị là chuỗi "false"). Khi tải: spinner + "Đang tải thiết lập...".
- Cấu hình (lưới 2 cột trên màn rộng), mỗi nhóm là các nút chọn một (nút chọn có viền primary và nền primary nhạt):
  - "Engine PDF" (phạm vi ".pdf"): pdfplumber (`pdfplumber`, "Giữ bảng biểu, đề mục"), PDF2text (`pdfium_plain`, "Text thuần, nhanh nhất"), MarkItDown (`markitdown`, "Bộ chuyển Markdown của Microsoft").
  - "Engine bảng tính" (".xlsx .xls .csv"): OpenPyXL (`openpyxl`), MarkItDown (`markitdown`).
  - "OCR trang scan" ("PDF"): Tự động (`auto`), Luôn OCR (`force_ocr`), Tắt (`disabled`).
  - "Hậu xử lý PDF": hai công tắc "Bỏ header / footer", "Nhận diện đề mục".
- Chân cấu hình: lỗi; "Đã lưu" (2,5 giây); "Có thay đổi chưa lưu" (hổ phách) khi khác bản đã lưu; nút ghost "Hoàn tác"; nút "Lưu thiết lập" (biểu tượng `save`, xoay `progress_activity` khi lưu; vô hiệu khi không có thay đổi). Lưu: `PUT /api/settings` body `{ settings: { pdf_parser_engine, excel_parser_engine, ocr_mode, pdf_strip_headers_footers: "true"/"false", pdf_enhance_headings: "true"/"false" } }`.
- Khu thử "Thử bóc tách" (biểu tượng `science`; ghi chú "Dùng thiết lập đang chọn ở trên (kể cả chưa lưu)"): cột trái (4/12) `TestFileDropzone` accept `.pdf,.docx,.xlsx,.xls,.csv,.txt,.md`, hint "PDF, Word, Excel/CSV, TXT, Markdown"; chọn "Số trang xem trước" 1/3/5/10 (mặc định 3); dòng engine sẽ dùng (biểu tượng `settings_suggest`); nút "Bóc tách & xem trước" (`play_arrow`; "Đang bóc tách..." khi chạy). Cột phải (8/12) `PreviewStudio` title "Xem trước", icon `preview`, tab mỗi trang "Trang {n}" kèm badge "OCR" nếu trang OCR, telemetry: thời gian (`timer`, giây 2 số lẻ), "{xem}/{tổng} trang" (`article`), "{n} trang OCR" (`photo_camera`, nếu > 0), "{từ} từ · {ký tự} ký tự" (`format_quote`), nhãn engine ở cuối.
- API thử: `POST /api/settings/test-extraction` multipart: `file`, `max_pages`, `pdf_parser_engine`, `excel_parser_engine`, `ocr_mode`, `strip_headers_footers`, `enhance_headings`; timeout 180 giây. Phản hồi: `success`, `file_name`, `file_type`, `stats?` {`total_pages`, `preview_pages_count`, `ocr_pages_count`, `total_words`, `total_chars`, `latency_ms`}, `pages[]` {`page_number`, `content`, `is_ocr`, `char_count`, `word_count`}, `error?`.

## 5. Card "Dịch vụ OCR" (`OcrSettingsCard`, có sẵn)

- Đầu card: biểu tượng `photo_camera` (tông xanh lục), "Dịch vụ OCR", mô tả "Model đọc trang scan / ảnh chụp văn bản khi bóc tách tài liệu.", `ActiveModelChip`.
- Tải song song `GET /api/settings` và `GET /api/settings/ocr/catalog` (phản hồi `active_spec_id`, `specs[]` với `id`, `provider`, `group`, `label`, `base_url`, `model_id`, `custom`, `api_key_configured`). Đang tải: "Đang tải cấu hình OCR..."; lỗi: "Không thể tải cấu hình OCR" hoặc message.
- `ProviderModelPicker` kind `ocr`, `keyFallbackHint` "Dùng key Vision cùng nhà cung cấp", `onProviderKeySaved`: nếu model đang dùng không custom và cùng nhóm vừa lưu key → gọi lại `POST /api/settings/ocr/select` với model đó để áp key mới.
- `ActivateBar` với nút con "Ping" (outline, `network_ping`; tooltip "Gửi 1 request nhỏ tới model đang chọn") → `POST /api/settings/test-ocr-connection` body `{ model_spec_id }`, phản hồi `success`, `message`, `latency_ms`; hiển thị `check_circle`/`error` + message (cắt ~320px) + "· {ms} ms". Kích hoạt: `POST /api/settings/ocr/select` body `{ model_spec_id }`.
- "Chế độ xử lý trang scan" (radiogroup 2 thẻ): "Chỉ OCR" (`bolt`) và "OCR + LLM hiệu đính" (`auto_fix_high`); bấm lưu ngay `PUT /api/settings` `{ settings: { ocr_llm_refine: "true"/"false" } }`.
- Khu "Thử OCR": dropzone accept `image/png,image/jpeg,image/webp,.pdf` (ảnh có thumbnail); bộ chọn trang khi là PDF; ô "Hiệu đính bằng LLM"; nút "Chạy OCR"/"Chạy OCR + LLM". API `POST /api/settings/test-ocr` multipart `file`, `target_page`, `model_spec_id`, `llm_refine`; timeout 360 giây nếu hiệu đính, 180 giây nếu không. Phản hồi: `success`, `text`, `model`, `latency_ms`, `chars_count`, `words_count`, `page_number?`, `total_pages?`, `error?`, `raw_text?`, `ocr_latency_ms?`, `refine_model?`, `refine_latency_ms?`, `refine_error?`. `PreviewStudio` title "Kết quả OCR", icon `text_fields`, tab "Sau LLM"/"OCR thô" khi có `raw_text`.

---

## 6. Card Embedding (`EmbeddingSettingsCard`)

### 6.1 Dữ liệu

Khi mount và mỗi lần làm mới: gọi song song
- `GET /api/settings/embeddings/catalog` → `active_spec_id`, `specs[]`: `id`, `provider`, `group`, `model_id`, `dimension` (number), `label`, `cost_per_1m_tokens` (number hoặc null), `notes`, `api_key_configured`, `api_key_config_key`, `custom`, `base_url`.
- `GET /api/settings/embeddings/status` → `active_spec_id`, `total_pages`, `embedded_pages`, `total_sources?`, `embedded_sources?`, `wiki_chunks_count?`, `source_chunks_count?`, `current_job` (Job hoặc null), `latest_job?` (Job hoặc null).
  - Job: `id`, `model_spec_id`, `status` ∈ {`pending`, `running`, `completed`, `failed`, `cancelled`}, `total_pages`, `done_pages`, `error_message`, `started_at?`, `finished_at?`, `created_at?` (ISO).
- `GET /api/settings`.

Model chọn: giữ lựa chọn trước nếu còn tồn tại, ngược lại = `active_spec_id` (không lấy spec đầu). Lỗi tải: message hoặc "Load failed".

"Job đang bận" = `current_job` tồn tại và trạng thái `pending` hoặc `running`. **Polling**: trong lúc job bận, hoặc đang gửi yêu cầu embed lại, hoặc đang gửi backfill → làm mới toàn bộ mỗi 2 giây; dừng khi hết các điều kiện.

Chưa có catalog hoặc status → card chỉ có "Loading embedding catalog…" và dòng lỗi.

### 6.2 Bố cục (từ trên xuống)

1. **Đầu card**: ô biểu tượng `data_array`; tiêu đề `t("settings.embeddingTitle", "Embedding Model & Quản lý Vector")`; mô tả "Đánh chỉ mục vector phục vụ tìm kiếm ngữ nghĩa cho toàn bộ bài viết Wiki và Tài liệu nguồn."; `ActiveModelChip`.
2. **Ba ô số liệu** (lưới 3 cột trên màn ≥ sm, 1 cột trên điện thoại):
   - "Model Đang Dùng" (`psychology`, primary): nhãn model hoặc "Chưa kích hoạt"; dòng phụ "{dimension} chiều · {group}" hoặc "—".
   - "Bài Viết Wiki" (`menu_book`, xanh dương): "{embedded_pages} / {total_pages} trang"; dòng phụ "{wiki_chunks_count} vector chunks đã index".
   - "Tài Liệu Nguồn" (`folder_open`, tím): "{embedded_sources} / {total_sources} tài liệu"; dòng phụ "{source_chunks_count} chunk thô đã index". (Trường thiếu → 0.)
3. **Khối trạng thái job** (chỉ một trong ba):
   - Job bận → khối nền xanh dương nhạt: biểu tượng `progress_activity` xoay, "Đang tái đánh chỉ mục (Re-embedding)...", chip `model_spec_id`; nút outline nhỏ "Hủy tiến trình" → `POST /api/settings/embeddings/jobs/{id}/cancel` rồi làm mới (lỗi: "Cancel failed"; backend trả 400 "Job is {status}, cannot cancel" nếu đã kết thúc, 404 "Job not found"). Dòng "Tiến độ hoàn thành:" … "{done} / {total} trang ({%}%)" với % = làm tròn done/total×100 (0 nếu total = 0); thanh tiến độ cao ~10px.
   - Không bận và `latest_job.status` = completed → khối xanh lá `check_circle`: "**Đã hoàn tất embedding toàn bộ** theo model {model_spec_id} ({done}/{total} trang)." và thời điểm `finished_at` bên phải.
   - failed → khối đỏ `error`: "**Lần embedding gần nhất thất bại:** {error_message hoặc "Lỗi không xác định"}" và thời điểm.
   - Thời điểm định dạng theo locale vi-VN dạng giờ:phút ngày/tháng (2 chữ số).
4. **`ProviderModelPicker`** kind `embedding`, `disabled` = job bận, `renderMeta` = "${cost_per_1m_tokens}/1M tokens" nếu có giá, không thì rỗng.
5. **Thanh hành động** (viền trên): trái —
   - Nếu model chọn khác model đang dùng: nút primary (`swap_horiz`) "Chuyển sang {label} & Embed lại" ("Đang chuyển & xếp hàng…" kèm biểu tượng xoay khi gửi). Vô hiệu khi job bận, đang gửi, hoặc `!canActivate(spec chọn)`. Bấm → confirm trình duyệt: "Chuyển sang {label} sẽ embed lại toàn bộ {total_pages} trang wiki. Tiếp tục?" → `POST /api/settings/embeddings/switch` body `{ model_spec_id }` (phản hồi `job_id`) → làm mới. Lỗi: "Switch failed".
   - Ngược lại: nút outline (`restart_alt`) "Embed lại toàn bộ dữ liệu" ("Đang xếp hàng…" khi gửi); tooltip "Chạy lại vector embedding cho tất cả bài viết wiki và tài liệu nguồn theo model đang dùng". Vô hiệu khi job bận/đang gửi. Confirm: "Xác nhận chạy lại toàn bộ embedding cho {total_pages} trang wiki và {total_sources} tài liệu theo model {label}? Quá trình này sẽ chạy ngầm." → `POST /api/settings/embeddings/reindex-current` (không body) → làm mới. Lỗi: "Reindex failed".
   - Nút outline nhỏ "Kiểm tra Ping" (`network_ping`; tooltip "Embed thử 1 câu ngắn bằng model đang chọn"), vô hiệu khi đang ping hoặc chưa chọn model. Gọi API thử (6.3) với query "ping", không passage. Kết quả (chỉ hiện khi ứng với model đang chọn): chip viền — thành công và `dimension` = `expected_dimension` → xanh lá `check_circle` "OK · {dimension} chiều · {latency}ms"; thành công nhưng lệch chiều → đỏ `error` "Trả về {dimension}d (kỳ vọng {expected}d)"; thất bại → đỏ với `error`.
   - Phải: khi không đổi model → `verified` (xanh lá) "Model đang chọn là model đang hoạt động".
   - **Cảnh báo đổi số chiều**: đổi model embedding luôn kích hoạt job embed lại toàn bộ (vì số chiều/không gian vector có thể khác); số chiều hợp lệ chỉ gồm 768, 1024, 1536, 2560, 3072 (form custom chặn/thông báo khi dò thấy số khác). Trong lúc job chạy, picker bị khóa nên không đổi model hay sửa key được.
6. **Khối "Tách đoạn & Index Chunk thô cho Tài liệu nguồn"** (biểu tượng `segment`; mô tả "Tạo các đoạn văn thô kèm phân cấp tiêu đề từ tài liệu tải lên để phục vụ tra cứu văn bản song song."; bên phải trên màn ≥ sm: "Đã index: **{embedded}/{total}** tài liệu").
   - Nút outline nhỏ (`play_arrow`) `settings.backfillChunks` "Index chunk thô cho tài liệu cũ" / khi gửi `settings.backfillingChunks` "Đang xếp hàng..."; vô hiệu khi đang gửi hoặc job bận.
   - Checkbox "Buộc chạy lại tất cả (Force re-index)" (mặc định tắt).
   - Gọi `POST /api/settings/embeddings/backfill-source-chunks?limit=500&force={true|false}`; phản hồi `job_id` (string hoặc null), `candidates`, `enqueued`, `message`. Sau đó hiện khung primary nhạt có `info` với `message`; nếu message rỗng: có job_id → "Đã xếp hàng job index chunk thô" (`settings.backfillQueued`), không → "Không có tài liệu nào cần xử lý". Lỗi: "Backfill failed".
7. **Khu "Thử embedding"** (`science`; bên phải "Model thử: **{label}**"): lưới 12 cột trên màn lg.
   - Trái (5/12): nhãn "Câu hỏi" + Input (mặc định câu mẫu về thủ tục đăng ký thường trú); nhãn "Đoạn văn so sánh (mỗi dòng 1 đoạn, tối đa 8)" + textarea 6 dòng (mặc định 3 đoạn mẫu: một đoạn liên quan hồ sơ đăng ký thường trú, một đoạn về phạt không đội mũ bảo hiểm, một đoạn về quyền tự do cư trú); nút "Chạy so khớp" (`compare_arrows`; "Đang embed..."), vô hiệu khi đang chạy, chưa chọn model, hoặc câu hỏi trống. Passage = tách theo dòng, trim, bỏ dòng trống, lấy tối đa 8.
   - Phải (7/12, cao tối thiểu ~220px): chưa có kết quả cho model đang chọn → `scatter_plot` mờ + "Chạy thử để xem độ tương đồng cosine giữa câu hỏi và từng đoạn."; thất bại → khung đỏ với lỗi hoặc "Embedding thất bại"; thành công → thanh `Stat`: `data_array` "{dimension} chiều" (đỏ và thêm " (cấu hình {expected})" nếu lệch), `timer` "{ms} ms", `memory` tên model (mono); danh sách passage **sắp xếp giảm dần theo điểm**, mỗi dòng: văn bản (tối đa 2 dòng; hạng 1 đậm, còn lại muted), điểm 4 chữ số thập phân bên phải, thanh ngang tỉ lệ điểm (kẹp 0–1; hạng 1 primary đậm, còn lại primary nhạt). Không passage → "Không có đoạn văn để so sánh.". Nếu `preview` có phần tử → dòng mono cuối "[v1, v2, …, …]" (4 chữ số thập phân, cắt một dòng).

### 6.3 API thử embedding

`POST /api/settings/embeddings/test` body `{ model_spec_id, query, passages: string[] }` → `success`, `model`, `dimension`, `expected_dimension`, `latency_ms`, `similarities` (number[] cùng thứ tự passages), `preview` (number[] vài giá trị đầu vector), `error` (string hoặc null). Lỗi mạng/HTTP được quy về object `success` = false với `error` = message (hoặc "Request failed"). Kết quả ping và kết quả thử được gắn với id model khi chạy; chỉ hiển thị khi id đó trùng model đang chọn.

---

## 7. Card LLM và Vision

Dùng `ModelCatalogCard` (mục 2.3.4) với props ở 3.3. API:

| Mục | Catalog | Kích hoạt |
|---|---|---|
| LLM | `GET /api/settings/llm/catalog` → `active_spec_id`, `specs` (ModelSpec) | `POST /api/settings/llm/switch` body `{ model_spec_id }` |
| Vision | `GET /api/settings/vision/catalog` | `POST /api/settings/vision/switch` body `{ model_spec_id }` |

Key nhà cung cấp lưu với khóa `llm_api_key__{nhóm}` / `vision_api_key__{nhóm}`. Model custom LLM có thêm trường "Giao thức" (OpenAI-compatible / Anthropic Messages) trong `CustomModelForm`. Không có nút "test connection" riêng ở card LLM/Vision (chỉ OCR và Embedding có Ping).

---

## 8. Card Ma trận phân quyền (`RolesPermissionsCard`)

### 8.1 API

- `GET /api/rbac/matrix` → `roles[]` {`id`, `name`, `description`}, `groups` (tên nhóm → danh sách permission), `labels` (permission → nhãn), `descriptions` (permission → mô tả), `all_permissions` (string[] theo thứ tự hiển thị), `role_permissions` (role id → permission[] hiệu lực).
- `PUT /api/rbac/matrix` body `{ role_permissions: { <role_id>: string[] } }` → `success` (boolean), `role_permissions`. Backend bỏ qua role `admin` và loại permission không hợp lệ; ghi vào cấu hình `role_permissions_custom`; ghi nhật ký kiểm toán.

### 8.2 Vai trò hệ thống (4, thứ tự cố định)

| id | Tên hiển thị (từ backend) |
|---|---|
| `viewer` | Viewer (Người xem) |
| `contributor` | Contributor (Người đóng góp) |
| `knowledge_manager` | Knowledge Manager (Quản trị tri thức) |
| `admin` | System Admin (Quản trị viên) — cố định, luôn đủ mọi quyền |

### 8.3 Danh sách permission theo nhóm

| Nhóm (khóa) | Tiêu đề hiển thị | Biểu tượng | Permission |
|---|---|---|---|
| `Documents` | Tài liệu & Văn bản (Documents) | `description` | doc:read:own_dept, doc:read:all, doc:create:own_dept, doc:create:all, doc:edit:own_dept, doc:edit:all, doc:delete:own_dept, doc:delete:all |
| `Wiki` | Wiki Tri thức (Knowledge Wiki) | `auto_stories` | wiki:read:own_dept, wiki:read:all, wiki:write:own_dept, wiki:write:all, wiki:delete:own_dept, wiki:delete:all |
| `AI Skills` | Kỹ năng AI (AI Skills) | `bolt` | skill:read:own_dept, skill:read:all, skill:create:own_dept, skill:create:all, skill:edit:own_dept, skill:edit:all, skill:delete:own_dept, skill:delete:all, skill:contribution:review |
| `Organization` | Tổ chức & Hệ thống (Organization) | `corporate_fare` | org:departments:read, org:departments:manage, org:employees:read, org:employees:manage, org:roles:read, org:roles:manage, org:settings:read, org:settings:manage, org:audit:read |
| `Workspaces` | Không gian làm việc (Workspaces) | `workspaces` | workspace:view:all |

Nhóm không có trong bảng → tiêu đề = khóa nhóm, biểu tượng `folder`. Nhãn/mô tả từng permission lấy từ `labels`/`descriptions` của API (thiếu nhãn → hiển thị chuỗi permission).

### 8.4 Bố cục

1. **Đầu card** (viền dưới): ô biểu tượng `admin_panel_settings` tông tím; tiêu đề "Ma trận Vai trò & Phân quyền (RBAC Matrix)" kèm chip mono tím "4 System Roles"; mô tả "Cấu hình quyền hạn chi tiết cho từng vai trò người dùng (Viewer, Contributor, Knowledge Manager, Admin)." Bên phải: badge xanh lá `check_circle` "Đã lưu quyền hạn" (3 giây sau khi lưu thành công) và nút "Lưu ma trận quyền" (biểu tượng `save`, khi lưu là `progress_activity` xoay; vô hiệu khi đang lưu hoặc đang tải).
2. **Đang tải**: spinner + "Đang tải cấu hình phân quyền...". Lỗi tải: "Không thể tải ma trận phân quyền" hoặc message (khung lỗi chỉ hiện khi đã có dữ liệu; nếu tải lỗi hoàn toàn thì phần thân trống).
3. **Bốn thẻ vai trò** (lưới 1/2/4 cột theo bề rộng): tên (admin có biểu tượng `verified_user` tím và chip "Cố định"), mô tả (tối đa 2 dòng), chân "Quyền kích hoạt:" "{số đang bật} / {tổng}" (admin luôn = tổng; vai trò khác đếm theo trạng thái đang sửa, cập nhật tức thì).
4. **Tìm kiếm**: ô nhập có biểu tượng `search`, placeholder "Tìm nhanh quyền hạn (ví dụ: wiki, đọc, xóa, skills)...", rộng tối đa ~384px; bên cạnh chú thích "Nhấp vào ô tích chọn để bật/tắt quyền hạn tương ứng cho vai trò." Lọc không phân biệt hoa thường theo chuỗi permission, nhãn hoặc mô tả; nhóm không còn dòng khớp bị ẩn.
5. **Khung lỗi** (destructive nhạt, biểu tượng `error`) khi lưu lỗi: message hoặc "Lỗi khi lưu ma trận phân quyền".
6. **Bảng ma trận** (cuộn ngang, rộng tối thiểu ~700px): cột "Tên Quyền & Mô tả" (40%), "Viewer", "Contributor", "Knowledge Mgr", "Admin" (mỗi cột 15%, căn giữa).
   - **Dòng tiêu đề nhóm** (nền muted, trải 5 cột): nút thu/mở gồm biểu tượng nhóm (primary), tiêu đề, "({n} quyền)" mono, biểu tượng `expand_less` (đang mở) / `expand_more` (đang thu). Mặc định mọi nhóm mở. Bên phải: "Chọn cả nhóm:" (ẩn trên màn hẹp) và ba link gạch chân mono "viewer", "contributor", "KM" — bấm: nếu vai trò đó đã có **tất cả** permission (đang hiển thị) của nhóm thì gỡ hết, ngược lại bật hết.
   - **Dòng permission**: nhãn (đậm vừa) + chip mono chuỗi permission; dòng mô tả nhỏ bên dưới. Ba checkbox cho viewer/contributor/knowledge_manager (bật/tắt trong bộ nhớ). Cột Admin luôn là biểu tượng `check_circle` tím, không tương tác, tooltip "System Admin luôn sở hữu quyền này".
7. **Lưu**: gửi toàn bộ trạng thái đang sửa của mọi role (kể cả admin — backend bỏ qua) qua `PUT /api/rbac/matrix`. Không có hoàn tác, không chặn rời trang khi chưa lưu. Thao tác với role `admin` ở phía client luôn bị bỏ qua.

---

## 9. Tổng hợp API màn Cài đặt

| Method | Path | Body / tham số | Phản hồi chính | Dùng bởi |
|---|---|---|---|---|
| GET | `/api/settings` | — | object khóa → giá trị (key nhạy cảm đã che bằng "•") | mọi card model, bóc tách, OCR |
| PUT | `/api/settings` | `{ settings: { khóa: chuỗi } }` (cần `org:settings:manage`) | `updated` | bóc tách, OCR mode, key nhà cung cấp |
| POST | `/api/settings/test-extraction` | multipart (mục 4) | ExtractionResponse | bóc tách |
| GET | `/api/settings/ocr/catalog` | — | `active_spec_id`, `specs` | OCR |
| POST | `/api/settings/ocr/select` | `{ model_spec_id }` | — | OCR |
| POST | `/api/settings/test-ocr-connection` | `{ model_spec_id }` | `success`, `message`, `latency_ms` | OCR |
| POST | `/api/settings/test-ocr` | multipart (mục 5) | OCRResponse | OCR |
| GET | `/api/settings/embeddings/catalog` | — | catalog embedding | Embedding |
| GET | `/api/settings/embeddings/status` | — | status (mục 6.1) | Embedding |
| POST | `/api/settings/embeddings/switch` | `{ model_spec_id }` | `job_id` | Embedding |
| POST | `/api/settings/embeddings/reindex-current` | — | `job_id` | Embedding |
| POST | `/api/settings/embeddings/jobs/{job_id}/cancel` | — | Job | Embedding |
| POST | `/api/settings/embeddings/backfill-source-chunks` | query `limit` (500), `force` (bool) | `job_id`, `candidates`, `enqueued`, `message` | Embedding |
| POST | `/api/settings/embeddings/test` | `{ model_spec_id, query, passages }` | mục 6.3 | Embedding |
| POST | `/api/settings/embeddings/probe-dimension` | `{ provider, base_url?, api_key?, model_id }` | `dimension`, `supported`, `latency_ms` | CustomModelForm |
| GET | `/api/settings/llm/catalog`, `/api/settings/vision/catalog` | — | `active_spec_id`, `specs` | LLM, Vision |
| POST | `/api/settings/llm/switch`, `/api/settings/vision/switch` | `{ model_spec_id }` | — | LLM, Vision |
| POST | `/api/settings/custom-models` | `kind`, `provider`, `label?`, `base_url?`, `model_id`, `api_key?`, `protocol?`, `dimension?`, `original_id?` | `id` (và các trường model) | CustomModelForm, saveCustomModelKey |
| DELETE | `/api/settings/custom-models` | query `kind`, `id` | — | deleteCustomModel |
| POST | `/api/settings/models/discover` | `{ kind, provider, base_url?, api_key? }` | `models` (string[]) | CustomModelForm |
| GET | `/api/rbac/matrix` | — | mục 8.1 | Ma trận phân quyền |
| PUT | `/api/rbac/matrix` | `{ role_permissions }` | `success`, `role_permissions` | Ma trận phân quyền |

Mọi endpoint `/api/settings/*` (trừ `GET /api/settings` chỉ cần đăng nhập) yêu cầu `org:settings:manage`; thiếu quyền backend trả 403.

## 10. Tóm tắt trạng thái tải / rỗng / lỗi

| Thành phần | Đang tải | Rỗng | Lỗi |
|---|---|---|---|
| Trang | spinner `progress_activity` | — | khối "không có quyền" + Đăng xuất |
| Bóc tách | "Đang tải thiết lập..." | studio "Chưa có dữ liệu xem trước" | dòng lỗi ở chân cấu hình; khối lỗi trong studio |
| OCR | "Đang tải cấu hình OCR..." | studio "Chưa có kết quả OCR" | chữ lỗi thay spinner; lỗi kích hoạt trong ActivateBar |
| Embedding | "Loading embedding catalog…" | khu thử: gợi ý cosine | dòng lỗi dưới chữ loading; khung đỏ khu thử |
| LLM/Vision | "Loading {title}…" | picker: "Chưa có model …" | dòng lỗi trong ActivateBar |
| Ma trận quyền | "Đang tải cấu hình phân quyền..." | nhóm bị lọc hết → bảng trống | khung lỗi phía trên bảng |
