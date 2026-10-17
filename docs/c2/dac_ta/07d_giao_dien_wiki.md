# 07d — Đặc tả giao diện Wiki (xem trang, cây, soạn thảo, nháp/nhánh, sơ đồ)

Tài liệu này là một phần của bộ đặc tả giao diện 07. Mục lục chung nằm ở `07_giao_dien.md`. Các nền tảng dùng chung (layout portal, xác thực phía client, `useAuth`/`hasPermission`, i18n, theme, các thành phần `components/ui`, quy ước icon Material Symbols) nằm ở `07a_giao_dien_nen_tang.md`. File này mô tả nhóm màn Wiki: `/wiki`, `/wiki/[...slug]` (xem trang và xem tài liệu nguồn), `/wiki/graph`, `/wiki/branches/[id]/rebase`, cùng toàn bộ thành phần trong `components/wiki/` và các module dùng chung `types/wiki.ts`, `lib/wiki-store.ts`, `lib/textarea-caret.ts`, `lib/hooks/use-image-resolver.ts`. Màn duyệt bản nháp `/wiki/review` và các màn văn bản pháp luật `/wiki/law...` **không** thuộc file này; xem `07e`.

Quy ước trong file:

- Nhãn hiển thị ghi theo khóa i18n trong `frontend/src/lib/i18n.tsx` khi khóa đó đã có (ví dụ `wiki.noPages`), kèm bản tiếng Việt / tiếng Anh để đối chiếu. Nhãn không có khóa được ghi nguyên văn trong ngoặc kép, và phải được hard-code đúng như vậy (một số nhãn là tiếng Anh, giữ nguyên).
- Icon ghi theo tên ligature Material Symbols (ví dụ `hub`, `fork_right`).
- Màu được mô tả theo vai trò (ví dụ "màu primary", "màu hổ phách nhạt"), không ghi mã màu. Bảng màu ngữ nghĩa ở mục 2.6 là chuẩn tham chiếu; người cài đặt tự chọn sắc độ phù hợp với theme ấm của portal.
- "Gọi API" luôn đi qua lớp fetch có xác thực của portal (xem 07a). Mọi đường dẫn API đều tương đối với gốc frontend (`/api/...`).

---

## 1. Giao diện module bắt buộc

Các module dưới đây được file loại C trong c2 hoặc được các màn khác import. Tên export, tên trường và chữ ký phải đúng chính xác.

Hiện trạng c2:

- `frontend/src/lib/wiki-store.ts` đã có và import `WikiPageDetail`, `WikiPageSummary` từ `@/types/wiki`.
- `frontend/src/app/(portal)/wiki/law/page.tsx` import `FacetGroup`, `FacetOption`, `countFacet` từ `@/components/wiki/wiki-facets` và `FormattedInlineText` từ `@/components/wiki/formatted-inline-text`.

### 1.1. `@/types/wiki` (file `frontend/src/types/wiki.ts`)

Chỉ chứa khai báo kiểu, không có giá trị runtime. Tất cả đều được export.

**`WikiPageType`** — hợp chuỗi: `entity` | `concept` | `topic` | `source` | `index` | `log` | `hot`.

**`WikiPageSummary`** — một dòng trong danh sách trang (`GET /api/wiki/pages`):

| Trường | Kiểu | Ghi chú |
|---|---|---|
| `slug` | string | định danh trang, có thể chứa dấu `/` |
| `title` | string | |
| `page_type` | `WikiPageType` | |
| `status` | `seed` \| `developing` \| `mature` \| `evergreen` | độ hoàn thiện |
| `summary` | string | |
| `knowledge_type_slugs` | string[] | |
| `source_ids` | string[] | id tài liệu nguồn |
| `scope_type` | string, tùy chọn | `global`, `department`, `project`... |
| `scope_id` | string \| null, tùy chọn | |
| `scope_name` | string \| null, tùy chọn | |
| `version` | number | |
| `updated_at` | string | ISO datetime |

**`WikiScope`** — phần tử của `GET /api/wiki/my-scopes`: `scope_type: string`, `scope_id: string | null`, `name: string`.

**`WikiPageDetail`** — mở rộng `WikiPageSummary`, thêm:

- `content_md: string`
- `backlinks: string[]` (slug các trang trỏ đến)
- `outlinks: string[]`
- `orphaned?: boolean`

**`WikiGraphNode`**:

- `slug`, `title`, `page_type`: string
- `status?: string`, `scope_type?: string`, `scope_id?: string | null`, `scope_name?: string | null`
- Trường do mô phỏng lực gắn vào: `x?`, `y?`, `vx?`, `vy?`: number; `fx?`, `fy?`: number | null

**`WikiGraphEdge`**:

- `from`, `to`: string (slug)
- `type?: string`, `label?: string`, `predicate?: string`, `weight?: number`
- `evidence?: string | null`, `target_doc_number?: string | null`
- `source?`, `target?`: `WikiGraphNode` | string (do thư viện sơ đồ gắn vào)

**`WikiGraphData`**: `nodes: WikiGraphNode[]`, `edges: WikiGraphEdge[]`, `total?: number`, `offset?: number`, `has_more?: boolean`.

**`DraftStatus`**: `pending` | `needs_revision` | `withdrawn` | `approved` | `rejected`.

**`DraftKind`**: `edit` | `create`.

**`AiCheckStatus`**: `pending` | `queued` | `running` | `passed` | `warned` | `failed` | `skipped`.

**`AiCheckItem`**:

- `id: string`
- `layer`: `L1` | `L2` | `L3` | `L4`
- `severity`: `block` | `warn`
- `status`: `pass` | `warn` | `fail` | `skipped`
- `message: string | null`
- `matches`: mảng, mỗi phần tử là string hoặc object `{ slug?: string, title?: string, score?: number, line?: number, snippet?: string }`

**`AiCheckResults`**:

- `version: number`
- `summary`: `{ pass: number, warn: number, fail: number, skipped: number }`
- `checks: AiCheckItem[]`

**`DraftSuggestedMetadata`**: `slug?: string`, `title?: string`, `page_type?: string`, `knowledge_type_slugs?: string[]`, `scope_type?: string`, `scope_id?: string | null`.

**`AuthorStats`**: `approved`, `rejected`, `needs_revision`, `total_reviewed`, `accuracy` — đều là number (`accuracy` trong khoảng 0–1).

**`SuggestedReviewer`**: `id: string`, `name: string | null`, `email: string | null`, `score: number`.

**`DraftResponse`**:

| Trường | Kiểu |
|---|---|
| `id` | string |
| `page_id` | string \| null |
| `page_slug` | string |
| `page_title` | string |
| `page_scope_type` | string |
| `page_scope_id` | string \| null |
| `page_scope_name` | string \| null |
| `page_version` | number |
| `base_version` | number \| null |
| `has_conflict` | boolean |
| `draft_kind` | `DraftKind` \| string |
| `suggested_metadata` | `DraftSuggestedMetadata` \| null |
| `author_id` | string \| null |
| `author_name` | string \| null |
| `author_stats` | `AuthorStats` \| null |
| `suggested_reviewers` | `SuggestedReviewer[]` |
| `content_md` | string |
| `note` | string \| null |
| `status` | `DraftStatus` \| string |
| `revision_round` | number |
| `last_returned_note` | string \| null |
| `ai_check_status` | `AiCheckStatus` \| string |
| `ai_check_results` | `AiCheckResults` \| null |
| `ai_checked_at` | string \| null |
| `source` | string |
| `reviewed_by_name` | string \| null |
| `reviewed_at` | string \| null |
| `reviewer_note` | string \| null |
| `created_at` | string |
| `updated_at` | string |

**`DraftRoundResponse`**: `id: string`, `round_no: number`, `content_md: string`, `author_note: string | null`, `reviewer_return_note: string | null`, `ai_check_results: AiCheckResults | null`, `submitted_at: string`.

### 1.2. `@/lib/wiki-store` (file `frontend/src/lib/wiki-store.ts`)

Một store dùng chung ở cấp module (không phải React context). Nó sống suốt phiên trình duyệt, nên vẫn còn khi người dùng chuyển trang phía client. Store giữ trạng thái UI của cây wiki và bộ nhớ đệm dữ liệu. Đây là file loại C đã có trong c2: phải giữ đúng các export dưới đây.

**Export kiểu `WikiSourceItem`**: `id: string`, `title: string`, `file_name?: string`, `status: string`, `source_type?: string`.

**Export đối tượng `wikiStore`** — các trường và giá trị mặc định:

| Trường | Mặc định | Ý nghĩa |
|---|---|---|
| `categoryFilter` | `"all"` | một trong `all` \| `articles` \| `overview` |
| `groupByDocument` | true | |
| `expandedDocuments` | Set rỗng | |
| `expandedScopes` | Set chứa `"global"` | |
| `search` | `""` | |
| `docFilter` | `""` | id tài liệu đang lọc, hoặc `"other"` |
| `collapsedSections` | Set rỗng | khóa các mục đang thu gọn trong cây |
| `sidebarScrollTop` | 0 | vị trí cuộn của cây |
| `treeCollapsed` | false | cột cây trái đang thu gọn |
| `infoCollapsed` | false | cột thông tin phải đang thu gọn |
| `pagesCache` | Map rỗng | khóa là URL danh sách, giá trị là `WikiPageSummary[]` |
| `sourcesCache` | null | `WikiSourceItem[]` hoặc null |
| `pageDetailCache` | Map rỗng | khóa chuỗi → `WikiPageDetail` |
| `sourceDataCache` | Map rỗng | id tài liệu → dữ liệu chi tiết tài liệu |

**Hàm export**:

- `subscribeWikiStore(listener: () => void): () => void` — đăng ký listener và trả về hàm hủy đăng ký.
- `notifyWikiStore(): void` — gọi lần lượt mọi listener. Lỗi trong một listener được bắt, ghi console, rồi tiếp tục với listener kế.
- `useWikiStore()` — hook React. Đăng ký vào store và render lại mỗi khi có notify. Trả về object gồm:
  - Giá trị: `categoryFilter`, `groupByDocument`, `expandedDocuments`, `expandedScopes`, `search`, `docFilter`, `collapsedSections`, `treeCollapsed`, `infoCollapsed`.
  - Setter: `setCategoryFilter(v)`, `setGroupByDocument(v | updater)`, `setSearch(v)`, `setExpandedDocuments(v | updater)`, `setExpandedScopes(v | updater)`, `setTreeCollapsed(v)`, `setInfoCollapsed(v)`, `setDocFilter(v)`, `toggleSection(key)`, `resetFilters()`.
  - Mỗi setter ghi vào `wikiStore` rồi gọi `notifyWikiStore`. Setter nhận "v | updater" chấp nhận cả giá trị lẫn hàm nhận giá trị cũ và trả giá trị mới.
  - Hai setter của Set luôn lưu một **bản sao** Set mới.
  - `toggleSection` thêm khóa vào `collapsedSections` nếu chưa có, và bỏ đi nếu đã có.
  - `resetFilters` đặt `categoryFilter = "all"`, `search = ""`, `docFilter = ""`.
- `displaySourceTitle(src: { title?: string; file_name?: string }): string` — tên hiển thị của tài liệu. Các bước:
  1. Lấy `title` đã trim; nếu rỗng thì lấy `file_name` đã trim; nếu vẫn rỗng thì trả `"Chưa đặt tên"`.
  2. Bỏ đuôi mở rộng ở cuối chuỗi, không phân biệt hoa thường: pdf, doc, docx, xls, xlsx, csv, txt, md, ppt, pptx.
  3. Thay mỗi chuỗi gạch dưới liên tiếp bằng một dấu cách.
  4. Gộp khoảng trắng liên tiếp thành một và trim.
- `getDocForPage(page: WikiPageSummary, sources: WikiSourceItem[]): WikiSourceItem | null` — tìm tài liệu nguồn "sở hữu" một trang. Danh sách nguồn rỗng thì trả null. Thứ tự ưu tiên:
  1. Phần tử đầu tiên trong `page.source_ids` có trong `sources`.
  2. Nếu tiêu đề trang có dạng "… - X": nguồn có `title` hoặc `file_name` bằng đúng X.
  3. Nguồn có `title` bằng `page.title`, hoặc có `id` bằng `page.slug`.
  4. Không có thì trả null.
- Bộ đệm:
  - `getCachedPages(url)` / `setCachedPages(url, pages)`.
  - `removeCachedPage(slug)`: lọc slug khỏi **mọi** danh sách trong `pagesCache`, và xóa mọi mục của `pageDetailCache` ứng với slug đó.
  - `getCachedSources()` / `setCachedSources(list)`.
  - `getCachedPageDetail(key)` / `setCachedPageDetail(key, detail)`.
  - `getCachedSourceData(id)` / `setCachedSourceData(id, data)`.

### 1.3. `@/components/wiki/wiki-facets` (file `frontend/src/components/wiki/wiki-facets.tsx`)

Client component. Export:

**`FacetOption`** (kiểu): `value: string`, `label: string`, `count: number`, `color?: string`.

**`STATUS_LABEL_VI`** (hằng, map status → nhãn):

| status | nhãn |
|---|---|
| `evergreen` | "Cốt lõi ổn định" |
| `mature` | "Tương đối đầy đủ" |
| `developing` | "Đang phát triển" |
| `seed` | "Sơ khởi" |

**`STATUS_ORDER`** (hằng mảng): `evergreen`, `mature`, `developing`, `seed`, đúng thứ tự này.

**`FacetGroup`** (component). Props:

| Prop | Kiểu | Mặc định |
|---|---|---|
| `title` | string | — |
| `options` | `FacetOption[]` | — |
| `selected` | Set<string> | — |
| `onToggle` | (value: string) => void | — |
| `searchable` | boolean | false |
| `searchPlaceholder` | string | "Tìm..." |
| `defaultOpen` | boolean | true |

Hành vi:

- `options` rỗng thì không render gì (null).
- Khối là một section. Các section đứng sau section đầu có viền trên mảnh làm ngăn cách.
- **Header** là một nút chiếm cả chiều ngang, bấm để mở/đóng:
  - Bên trái là `title`, chữ nhỏ đậm.
  - Nếu số mục đang chọn lớn hơn 0: một viên tròn nhỏ ghi số đó, nền màu primary nhạt, chữ primary.
  - Bên phải là icon `expand_less` khi đang mở, `expand_more` khi đang đóng.
- **Thân** (chỉ khi mở):
  - Chỉ khi `searchable` **và** có hơn 6 option: hiện ô tìm kiếm nhỏ có icon `search` bên trái, placeholder là `searchPlaceholder`. Ô này lọc option theo `label`, không phân biệt hoa thường.
  - Khi `searchable`, danh sách có chiều cao tối đa cố định (khoảng 15rem) và cuộn dọc.
  - Mỗi option là một `label` bọc cả dòng, tooltip là `label`, có hiệu ứng nền khi hover. Trong dòng:
    - checkbox với accent màu primary; checked khi value có trong `selected`; đổi trạng thái thì gọi `onToggle(value)`;
    - nhãn cắt bớt nếu dài, in đậm vừa khi được chọn, tô màu `color` nếu option có;
    - số `count` nhỏ, màu mờ, căn phải.
  - Có từ khóa lọc mà không khớp option nào: hiện "Không có kết quả", chữ nhỏ màu mờ.

**`countFacet<T>(items: T[], keysOf: (item: T) => string[], labelOf: (value: string) => string, order?: string[]): FacetOption[]`**:

- Với mỗi item, lấy `keysOf(item)` và bỏ trùng trong phạm vi item đó, rồi cộng 1 cho mỗi khóa.
- Mỗi khóa thành một option `{ value, label: labelOf(value), count }`.
- Có `order`: sắp theo vị trí của value trong `order`. Value không có trong `order` nhận vị trí −1, nên đứng đầu.
- Không có `order`: sắp theo `count` giảm dần; bằng nhau thì theo `label` với so sánh chuỗi locale `vi`.

### 1.4. `@/components/wiki/formatted-inline-text` (file `frontend/src/components/wiki/formatted-inline-text.tsx`)

Export **`normalizeMarkup(text: string): string`**:

- Chuỗi rỗng hoặc falsy thì trả `""`.
- Chuẩn hóa thẻ HTML đơn giản có khoảng trắng thừa: bỏ khoảng trắng sau `<`, quanh `/`, và trước `>`, đồng thời đưa tên thẻ về chữ thường. Ví dụ "< mark >" thành thẻ mở mark chuẩn, "< / Mark >" thành thẻ đóng mark chuẩn.
- Trim kết quả.
- Hàm này có bản giống hệt được export lại từ `wiki-content` (mục 3.2).

Export **`FormattedInlineText({ text?: string | null, className?: string })`**:

- `text` falsy thì render null.
- Sau khi `normalizeMarkup`, nếu chuỗi **không** chứa dấu hiệu định dạng nào thì render một span thường với className, nội dung là **chuỗi gốc** chưa chuẩn hóa. Dấu hiệu định dạng là một trong: `**`, `*`, `__`, thẻ mở hoặc đóng `mark`, hoặc có cả `<` lẫn `>`.
- Nếu có dấu hiệu, render span inline-block với className, bên trong render markdown của chuỗi đã chuẩn hóa. Markdown dùng GFM và cho phép HTML thô. Cách render các phần tử:
  - đoạn văn: không bọc thẻ p (render thành fragment) để giữ nguyên dòng;
  - `mark`: nền hổ phách nhạt, bo góc nhỏ, đệm ngang rất nhỏ, chữ giữ màu kế thừa;
  - `strong`: đậm; `em`: nghiêng.
- Mục đích: hiện tiêu đề hoặc trích đoạn có đánh dấu tô sáng từ backend tìm kiếm.

### 1.5. `@/lib/textarea-caret` (file `frontend/src/lib/textarea-caret.ts`)

Export kiểu **`CaretCoords`**: `top: number`, `left: number`, `lineHeight: number`.

Export **`getTextareaCaretCoords(textarea: HTMLTextAreaElement, position: number): CaretCoords`**. Hàm trả tọa độ **viewport** của vị trí con trỏ thứ `position` trong textarea. Thuật toán bằng lời:

1. Tạo một div "gương" ẩn, đặt tuyệt đối ngoài màn hình, `visibility` hidden, rồi gắn vào body.
2. Chép sang gương các thuộc tính computed style của textarea:
   - kích thước hộp: box-sizing, width, height, overflow-x/y;
   - viền: độ dày bốn cạnh, kiểu viền;
   - padding bốn cạnh;
   - font: style, variant, weight, stretch, size, size-adjust, line-height, family;
   - chữ: text-align, text-transform, text-indent, text-decoration, letter-spacing, word-spacing, tab-size.
3. Gương xuống dòng như textarea: `white-space` pre-wrap, ngắt từ dài.
4. Đặt nội dung gương là văn bản từ đầu đến `position`. Thêm một span chứa phần còn lại của văn bản; nếu phần còn lại rỗng thì span chứa một dấu chấm.
5. Tọa độ trả về:
   - `top` = top của khung textarea + offsetTop của span − scrollTop của textarea;
   - `left` = left của khung + offsetLeft của span − scrollLeft;
   - `lineHeight` = line-height computed dạng số, hoặc font-size × 1,4 nếu không parse được.
6. Gỡ gương khỏi DOM trước khi trả.

### 1.6. `@/lib/hooks/use-image-resolver` (file `frontend/src/lib/hooks/use-image-resolver.ts`)

Export kiểu **`ImageResolverState`**:

- `resolved: Record<string, string>` — uuid → URL ảnh đã ký;
- `denied: Set<string>`;
- `loading: boolean`.

Export hook **`useImageResolver(ids: string[]): ImageResolverState`**:

- Khóa phụ thuộc là danh sách id đã bỏ trùng và sắp xếp. Effect chỉ chạy lại khi khóa này đổi, không phải khi tham chiếu mảng đổi.
- Khóa rỗng: trạng thái là `{ resolved: {}, denied: Set rỗng, loading: false }` và không gọi API.
- Khác rỗng:
  1. Đặt `loading = true`.
  2. Gọi `POST /api/wiki/images/resolve`, body `{ "ids": [...] }`. Response `{ "resolved": { uuid: url }, "denied": [uuid...] }`.
  3. Thành công: `{ resolved, denied: Set(denied), loading: false }`.
- Kết quả về muộn của một khóa cũ (hoặc sau khi unmount) thì bỏ qua.
- Lỗi mạng hoặc HTTP: `{ resolved: {}, denied: Set rỗng, loading: false }`.
- Bên gọi hiểu: id có trong `resolved` là "ok"; có trong `denied` là "bị từ chối"; khi `loading` là "đang tải"; không thuộc cả hai là "không tìm thấy".

### 1.7. Các export khác được thành phần khác import

| Module | Export | Mục |
|---|---|---|
| `@/components/wiki/wiki-page-tree` | `WikiPageTree`, `removeVietnameseTones(str): string` | 3.1 |
| `@/components/wiki/wiki-content` | `WikiContent`, `normalizeMarkup`, `preprocessWikilinks(md): string` | 3.2 |
| `@/components/wiki/wiki-image` | `WikiImage` | 3.3 |
| `@/components/wiki/wiki-editor` | `WikiEditor`, kiểu `WikiEditorProps` | 3.4 |
| `@/components/wiki/markdown-editor` | `MarkdownEditor` | 3.5 |
| `@/components/wiki/wikilink-autocomplete` | `WikilinkAutocomplete` | 3.6 |
| `@/components/wiki/wiki-create-page-dialog` | `WikiCreatePageDialog` | 3.7 |
| `@/components/wiki/wiki-draft-banner` | `WikiDraftBanner` | 3.8 |
| `@/components/wiki/wiki-draft-diff` | `WikiDraftDiff` | 3.9 |
| `@/components/wiki/wiki-ai-check-panel` | `WikiAiCheckPanel` | 3.10 |
| `@/components/wiki/wiki-backlinks` | `WikiSidebarRight`, `WikiBacklinks` (bí danh của cùng component) | 3.11 |
| `@/components/wiki/wiki-search-dialog` | `WikiSearchDialog` | 3.12 |
| `@/components/wiki/wiki-status-badge` | `WikiStatusBadge`, kiểu `WikiStatus` | 3.13 |
| `@/components/wiki/wiki-type-badge` | `WikiTypeBadge`, `wikiTypeIcon(type)`, `wikiTypeColor(type)`, `wikiTypeGroupLabel(type)` | 3.14 |
| `@/components/wiki/wiki-graph` (thư mục, `index.tsx`) | `WikiGraph`, `RELATION_COLORS`, `RELATION_LABELS` | 3.15 |
| `@/components/wiki/wiki-graph/wiki-graph-mini` | `WikiGraphMini` | 3.15 |
| `@/components/wiki/wiki-graph/types` | `GraphNode`, `GraphLink`, `EdgeInput`, `NodeInput` | 3.15 |
| `@/components/wiki/wiki-graph/utils` | `scopeColor(idx)`, `nodeRadius(degree, mini)`, `convexHull`, `hullToPath` | 3.15 |
| `@/components/shared/scope-badge` | `ScopeBadge` (dùng ở trang xem; đặc tả ở 07a) | — |

`removeVietnameseTones(str)`:

1. Chuẩn hóa Unicode NFD.
2. Bỏ toàn bộ dấu kết hợp.
3. Đổi "đ" và "Đ" thành "d".
4. Đưa về chữ thường.

Dùng cho mọi phép so khớp không dấu trong cây.

---

## 2. Màn hình

### 2.1. `/wiki` (file `app/(portal)/wiki/page.tsx`)

Không có giao diện. Vào là chuyển hướng phía server ngay sang `/wiki/law`.

### 2.2. `/wiki/[...slug]` — xem trang wiki và xem tài liệu nguồn

File `app/(portal)/wiki/[...slug]/page.tsx`. Client component.

#### 2.2.1. Route, tham số, điều hướng

- Slug là các đoạn path nối bằng `/`. Ví dụ `/wiki/a/b` cho slug `a/b`.
- Query `scopeType` và `scopeId` (camelCase trên URL của trang này):
  - Trang được coi là "có phạm vi" khi `scopeType` có giá trị và khác `global`.
  - Khi có phạm vi, mọi link nội bộ tới trang wiki khác được gắn hậu tố `?scopeType=…&scopeId=…`, gọi là "hậu tố phạm vi".
- **Chế độ tài liệu nguồn**: path gồm đúng 2 đoạn và đoạn đầu là `source` (`/wiki/source/{id}`).
- **Điều hướng nội bộ không remount**: khi bấm trang trên cây, wikilink trong nội dung, kết quả tìm kiếm hoặc link ở cột phải, màn hình:
  - gọi `history.pushState` sang `/wiki/{slug}{hậu tố phạm vi}`;
  - cập nhật slug hiện tại trong state.
- Màn hình lắng nghe `popstate` (Back/Forward) để đọc lại slug từ `location.pathname`, bỏ tiền tố `/wiki/` và giải mã URL.
- Phím tắt Ctrl+K hoặc ⌘+K, bắt ở window, mở hộp tìm kiếm (3.12) và chặn hành vi mặc định.

#### 2.2.2. Dữ liệu và quyền

1. **Phạm vi của tôi**: `GET /api/wiki/my-scopes` → `WikiScope[]`. Lỗi thì coi là mảng rỗng. Phạm vi hiện tại xác định như sau:
   - phần tử khớp `scope_type` và `scope_id` từ URL;
   - nếu không có mà URL có phạm vi, tạo phạm vi `{ scope_type: scopeType, scope_id: scopeId, name: scopeType }`;
   - nếu không, dùng `{ scope_type: "global", scope_id: null, name: "Global" }`.
2. **Quyền** (lấy `user` và `hasPermission` từ hook xác thực của portal):
   - `canEdit` = user có role `admin` **hoặc** quyền `wiki:write:all`.
   - `canPropose`:
     - true nếu `canEdit`;
     - nếu phạm vi là `department`: true khi có `wiki:write:all`, hoặc khi có `wiki:write:own_dept` và `scopeId` nằm trong `user.department_ids`;
     - phạm vi khác (global): true khi có `wiki:write:own_dept` hoặc `wiki:write:all`.
   - `canReview` = `canEdit`.
3. **Chế độ tạo trang theo phạm vi**. Hàm nội bộ được truyền cho cây và hộp tạo trang, trả `direct`, `propose` hoặc null:
   - Phạm vi `department` có id:
     - `direct` nếu admin hoặc có `wiki:write:all`;
     - `propose` nếu có `wiki:write:own_dept` và id thuộc phòng ban của user;
     - ngược lại null.
   - Phạm vi khác:
     - `direct` nếu admin hoặc có `wiki:write:all`;
     - `propose` nếu có `wiki:write:own_dept`;
     - ngược lại null.
4. **Nhánh đóng góp**. Chỉ tải khi có user và (`canPropose` hoặc `canEdit`).
   - Gọi `GET /api/wiki/branches?mine=true&status=draft`. Khi có phạm vi, thêm `&scope_type=…&scope_id=…`.
   - Có kết quả: nhánh đầu tiên thành nhánh đang dùng.
   - Danh sách rỗng: tự tạo nhánh bằng `POST /api/wiki/branches`, body:
     - `name`: "Đóng góp ngày dd/mm/yyyy", ngày hiện tại theo định dạng vi-VN;
     - `description`: "Nhánh đóng góp tự động được tạo khi chỉnh sửa tài liệu.";
     - `scope_type`: phạm vi hiện tại hoặc `global`;
     - `scope_id`: phạm vi hiện tại hoặc null.
   - Nhánh mới thành danh sách một phần tử và là nhánh đang dùng.
   - Lỗi ở bất kỳ bước nào: danh sách nhánh rỗng, không báo lỗi.
5. **Tải trang** (chế độ thường):
   - Khóa cache: chuỗi gồm slug, scopeType (hoặc `global`) và scopeId (hoặc `none`), nối bằng ký tự phân cách. Ví dụ "slug:global:none".
   - Có `getCachedPageDetail(khóa)`: hiện ngay bản cache, không hiện skeleton.
   - Luôn gọi `GET /api/wiki/pages/{slug đã encode từng đoạn}`. Khi có phạm vi, thêm `?scope_type=…&scope_id=…`.
   - Thành công: lưu cache và cập nhật.
   - 404: trạng thái "không tìm thấy". Lỗi khác: giữ bản cache nếu có.
6. **Chế độ tài liệu nguồn**:
   - Lấy `getCachedSourceData(id)` nếu có.
   - Gọi `GET /api/sources/{id}` và lưu `setCachedSourceData`.
   - Dựng một "trang giả":
     - `slug` = `source/{id}`, `page_type` = `source`, `status` = `evergreen`;
     - `title` = `title`, hoặc `file_name`, hoặc "Tài liệu";
     - `content_md` rỗng, `backlinks`/`outlinks` rỗng.
7. **Trích dẫn**: với mỗi `source_ids` của trang, gọi song song `GET /api/sources/{id}`. Các lời gọi lỗi bị bỏ qua.
   - Kết quả là danh sách tài liệu tham khảo, đánh số từ 1 theo thứ tự `source_ids`.
   - Markdown hiển thị = `content_md`, rồi một đường kẻ ngang, rồi mỗi tài liệu một dòng footnote định nghĩa. Footnote thứ n trỏ link markdown có chữ là tiêu đề tài liệu tới `/wiki/source/{id}`. Nhờ vậy nội dung có thể dùng tham chiếu footnote GFM `[^n]`.
8. **Bản nháp đang mở**:
   - `GET /api/wiki/pages/{slug}/drafts`, kèm `?scope_type&scope_id` khi có phạm vi.
   - Chỉ giữ các bản có `status` là `pending` hoặc `needs_revision`.
   - Lỗi thì coi là rỗng.

#### 2.2.3. Bố cục

Ba cột, cao bằng vùng nội dung portal. Mỗi cột cuộn độc lập.

**Cột trái**: `WikiPageTree` (3.1) với:

- `activeSlug` = slug hiện tại;
- `groupByScope` bật; `activeScope` = phạm vi hiện tại; `getCreateModeForScope` = hàm ở 2.2.2 mục 3;
- `onPageSelect` = điều hướng nội bộ; `linkQueryParams` = hậu tố phạm vi;
- `onSearch` = mở hộp tìm kiếm;
- `onCreatePage(scopeType, scopeId)`: tìm phạm vi khớp trong danh sách "phạm vi của tôi", rồi mở hộp tạo trang với phạm vi đó và chế độ tương ứng;
- `onDeleted`: nếu trang vừa xóa là trang đang xem thì chuyển về `/wiki/law`.

**Cột giữa** (cuộn dọc). Khung nội dung căn giữa, rộng tối đa khoảng 54rem; ở chế độ tài liệu nguồn rộng tối đa khoảng 72rem. Từ trên xuống:

1. **Thanh breadcrumb**:
   - Bên trái: "Wiki" › nhãn nhóm loại trang (`wikiTypeGroupLabel(page_type)`), chữ nhỏ màu mờ.
   - Bên phải: nút **Chế độ đọc**:
     - Bật/tắt **đồng thời** `treeCollapsed` và `infoCollapsed` trong `wikiStore`. Bật khi cả hai đang mở; tắt thì mở lại cả hai.
     - Nhãn "Chế độ đọc" với icon `open_in_full`. Khi đang ở chế độ đọc (cả hai thu gọn): nhãn "Thoát chế độ đọc" với icon `close_fullscreen`, nút tô nền primary nhạt và chữ primary.
     - Tooltip: "Ẩn danh mục và thông tin trang để đọc rộng hơn" / "Hiện lại danh mục và thông tin trang".
2. **Hàng huy hiệu**:
   - `WikiTypeBadge`.
   - `ScopeBadge` với scope_type, scope_name của trang; không hiện ở chế độ tài liệu nguồn.
   - Huy hiệu độ hoàn thiện, chỉ cho loại khác `index`/`log`/`hot`/`source`:
     - Có `canEdit`: là nút mở dropdown, tooltip "Đổi độ hoàn thiện". Dropdown liệt kê seed, developing, mature, evergreen; mỗi mục là `WikiStatusBadge`; trạng thái hiện tại bị vô hiệu.
     - Chọn một mục: gọi `PATCH /api/wiki/pages/{slug}/status?scope_type=…&scope_id=…`, body `{ "status": "<mới>" }`. Thành công thì cập nhật trang và cache tại chỗ. Lỗi thì giữ nguyên.
     - Không có `canEdit`: chỉ là `WikiStatusBadge` tĩnh.
   - Bên phải: "v{version}" chữ mono nhỏ màu mờ, tooltip "Phiên bản".
3. **Tiêu đề**: heading cỡ 3xl, đậm.
   - Bên phải tiêu đề, khi đang xem (không sửa), không phải chế độ nguồn, và user có `canEdit` hoặc `canPropose`: nút viền, icon `edit`.
   - Nhãn "Chỉnh sửa" nếu `canEdit`, ngược lại "Đề xuất sửa". Bấm thì vào chế độ sửa.
4. **Dòng cập nhật**: "Cập nhật lúc HH:mm dd/mm/yyyy" theo `updated_at`, chữ nhỏ màu mờ.
5. **Link trích dẫn** (khi có tài liệu tham khảo):
   - Mỗi link có icon `description` và tiêu đề tài liệu.
   - Mặc định hiện 2 link. Nếu nhiều hơn: nút chữ "+N tài liệu"; khi đã mở rộng thì "Thu gọn".
   - Bấm link: điều hướng nội bộ tới `source/{id}`.
6. **Chip loại tri thức**: mỗi `knowledge_type_slugs` là một chip nhỏ nền surface, chữ mờ.
7. **Hộp tóm tắt** (khi `summary` khác rỗng): khung bo góc nền nhạt, tiêu đề nhỏ "Tóm tắt", nội dung là summary.
8. **Banner bản nháp** (`WikiDraftBanner`, 3.8). Hiện khi đang xem, không sửa bản nháp nào, và có bản nháp mở. Truyền vào:
   - `drafts`; `currentContent` = `content_md`; `currentUserId` = `user.id`;
   - `onApproved(id)`: bỏ bản nháp khỏi danh sách và tải lại trang;
   - `onRejected(id)` và `onWithdrawn(id)`: bỏ bản nháp khỏi danh sách;
   - `onChangesRequested`: tải lại danh sách bản nháp;
   - `onResubmitDraft(draft)`: mở trình sửa gửi lại cho bản nháp đó.
9. **Thân**: tùy chế độ, xem 2.2.4–2.2.6.

**Trạng thái**:

- Đang tải lần đầu (không có cache): skeleton gồm một dòng ngắn cho breadcrumb, một khối cao cho tiêu đề và 6–8 dòng văn bản.
- Không tìm thấy (404): khối căn giữa gồm
  - icon `find_in_page` lớn màu mờ;
  - tiêu đề "Page not found";
  - mô tả `No wiki page found for "{slug}". It may not have been compiled yet.`

**Cột phải** (chỉ từ breakpoint xl, khi đang xem và đã có trang):

- `infoCollapsed` = true: dải dọc hẹp khoảng 2,75rem, viền trái, có nút icon `right_panel_open`, tooltip "Mở thông tin trang". Bấm thì mở lại.
- Mở: `WikiSidebarRight` (3.11) với slug, page, hậu tố phạm vi và điều hướng nội bộ. Góc trên có nút icon `right_panel_close`, tooltip "Thu gọn thông tin trang".

#### 2.2.4. Thân ở chế độ xem trang thường

- `WikiContent` (3.2), truyền markdown đã gắn footnote, `linkSuffix` = hậu tố phạm vi, `onWikiLinkClick` = điều hướng nội bộ.
- Khi có tài liệu tham khảo: phần "Tài liệu tham khảo (N)" có tiêu đề cỡ lớn, viền trên. Bên dưới là lưới thẻ, 1 cột trên màn nhỏ và 2 cột từ md. Mỗi thẻ gồm:
  - chip nhỏ "Trích dẫn [n]" nền primary nhạt;
  - tiêu đề tài liệu (displaySourceTitle), tối đa 2 dòng;
  - dòng phụ "Liên kết Web" nếu nguồn là URL, ngược lại "File • X MB" (dung lượng MB, 2 chữ số thập phân);
  - hàng link "Xem tài liệu →" có icon `visibility`, điều hướng nội bộ tới `source/{id}`;
  - "Tải xuống" có icon `cloud_download`, link tới `download_url`, mở tab mới. Chỉ hiện khi có `download_url`.

#### 2.2.5. Thân ở chế độ tài liệu nguồn

**Thẻ thông tin** (khung viền bo góc):

- Icon `language` nếu `source_type` là url, ngược lại `description`, trên nền primary nhạt.
- Tiêu đề tài liệu.
- Chip "Verbatim" khi `preserve_verbatim` = true. Tooltip tiếng Anh giải thích tài liệu được giữ nguyên văn để tìm kiếm chính xác.
- Dòng phụ:
  - Nguồn url: link URL gốc kèm icon `open_in_new`, mở tab mới.
  - Ngược lại: "Dung lượng: X.XX MB", nối " • Đăng bởi: {tên người tải lên}" nếu có tên.
- Nút "Mở tab mới": viền, icon `open_in_new`. Mở `preview_url`, hoặc `file_url`, hoặc `download_url` trong tab mới.
- Nút "Tải tài liệu gốc": primary, icon `cloud_download`. Link tới `download_url`. Chỉ hiện khi có `download_url`.

**Vùng xem** (theo đuôi file, chữ thường):

| Loại | Hiển thị |
|---|---|
| `pdf` | iframe cao 780px, nguồn là URL xem trước kèm tham số bật toolbar của trình xem PDF |
| `jpg`, `jpeg`, `png`, `gif`, `webp`, `svg` | ảnh căn giữa, cao tối đa 700px, giữ tỉ lệ |
| `docx`, `doc`, `xlsx`, `xls`, `pptx`, `ppt`, `txt`, `md`, `csv`, `json` | iframe cao 780px với `preview_url`, hoặc `download_url` |
| nguồn url | khối căn giữa: icon `language`, tiêu đề "Liên kết tài liệu gốc (Website Source)", mô tả "Đây là một liên kết ngoài. Bạn có thể mở trực tiếp trang web để đọc toàn văn tài liệu.", nút "Mở trang Web gốc" (mở URL ở tab mới) |
| đuôi khác (có file) | khối căn giữa: icon `draft`, tiêu đề "Không thể xem trước định dạng này trực tiếp", mô tả `Tài liệu "{tên}" không hỗ trợ nhúng trực tiếp. Vui lòng bấm Tải tài liệu gốc để đọc.`, nút tải xuống |
| không có gì để hiện | icon `hourglass_empty`, chữ "Tài liệu không có tệp đính kèm hoặc đang xử lý." |

#### 2.2.6. Chế độ sửa

**Sửa trang** (bấm "Chỉnh sửa" / "Đề xuất sửa"):

- Người không có `canEdit` mà có nhánh đang dùng: phía trên trình sửa hiện **thanh ngữ cảnh nhánh**. Thanh có nền màu cát/nâu xám ấm nhạt, viền cùng tông, và gồm:
  - icon `fork_right`, chữ "Đang lưu đóng góp vào nhánh: " và tên nhánh in đậm;
  - nếu có hơn 1 nhánh: một select nhỏ để đổi nhánh đang dùng;
  - nút nhỏ "Tạo nhánh mới", mở modal tạo nhánh (2.2.7).
- Bên dưới là `WikiEditor` (3.4) với:
  - `initialContent` = `content_md`;
  - `noteLabel` = "Change note";
  - `notePlaceholder` = "Briefly describe what you changed (optional)";
  - `saveLabel` = "Save Edit".
- Lưu:
  - Có `canEdit`: gọi `PUT /api/wiki/pages/{slug}?scope_type=…&scope_id=…`, body `{ "content_md": "...", "change_note": "..." }`. Thành công thì cập nhật trang và cache, rồi thoát chế độ sửa.
  - Không có `canEdit`: gọi `POST /api/wiki/pages/{slug}/drafts`, body:
    - `content_md`, `note`;
    - `scope_type` (phạm vi trang, hoặc `global`), `scope_id`;
    - `base_version` = `version` hiện tại;
    - `branch_id` = id nhánh đang dùng, hoặc null.
  - Thành công thì thoát chế độ sửa, tải lại trang và danh sách bản nháp. Trong cấu hình hiện tại, backend có thể xuất bản ngay vì bước duyệt đang tắt; giao diện chỉ cần tải lại.
  - Lỗi: ném lỗi với `detail` của response để `WikiEditor` hiện ra.
- Hủy: thoát chế độ sửa, không lưu.

**Sửa và gửi lại bản nháp** (từ banner):

- `WikiEditor` với:
  - `initialContent` = `content_md` của bản nháp;
  - `noteLabel` = "Resubmission note";
  - `notePlaceholder` = "What changed in this round?";
  - `saveLabel` = "Resubmit draft".
- Lưu: gọi `PATCH /api/wiki/drafts/{id}/content`, body `{ "content_md", "note" }`. Thành công thì thoát và tải lại danh sách bản nháp.

#### 2.2.7. Hộp thoại

- **Tìm kiếm**: `WikiSearchDialog` (3.12). `onSelectPage` = điều hướng nội bộ.
- **Tạo trang**: `WikiCreatePageDialog` (3.7). Chỉ render khi chế độ tạo của phạm vi đã chọn khác null. Truyền:
  - `mode`; `defaultScope` = phạm vi đã chọn;
  - `scopes` = phạm vi của tôi; `getCreateModeForScope`.
- **Modal tạo nhánh**: overlay tối mờ toàn màn, hộp căn giữa rộng khoảng 28rem, bo góc, đổ bóng. Gồm:
  - Header: "Tạo nhánh đóng góp mới" và nút icon `close`.
  - Trường "Tên nhánh": input, placeholder "Ví dụ: thay-doi-quy-che-lam-viec".
  - Trường "Mô tả (Không bắt buộc)": textarea 3 dòng, placeholder "Mô tả tóm tắt nội dung đợt đóng góp này...".
  - Footer: "Hủy" (đóng) và "Tạo nhánh" (primary).
  - Tên nhánh rỗng sau khi trim: bấm "Tạo nhánh" không làm gì.
  - Ngược lại gọi `POST /api/wiki/branches`, body `{ name, description, scope_type, scope_id }` theo phạm vi hiện tại. Thành công thì chèn nhánh mới vào **đầu** danh sách, chọn làm nhánh đang dùng, xóa form và đóng modal.

### 2.3. `/wiki/graph` — sơ đồ tri thức toàn cục

File `app/(portal)/wiki/graph/page.tsx`. Client component, chiếm toàn bộ vùng nội dung.

**Tham số**: query `projectId`.

- Có `projectId`: URL gốc là `/api/projects/{projectId}/wiki/graph`, nhãn là "Workspace Graph", nút quay lại về `/workspaces`.
- Không có: URL gốc là `/api/wiki/graph`, nhãn là "Knowledge Graph", nút quay lại về `/wiki/law`.

**Tải lũy tiến**:

1. Gọi lặp `{URL gốc}?offset={o}&limit=10`, bắt đầu từ o = 0.
2. Mỗi lần nhận `WikiGraphData`:
   - nối nút mới (bỏ trùng theo slug) và cạnh mới vào state;
   - cập nhật tổng số nút `total`;
   - tăng offset theo số nút nhận được.
3. Dừng khi `has_more` false, khi một trang trả 0 nút, hoặc khi lỗi (giữ dữ liệu đã có).
4. Sau lô đầu tiên, sơ đồ hiện ngay, không chờ hết các lô sau.

**Header** (một dải ngang có viền dưới):

- Nút icon `arrow_back`, tooltip "Back to Wiki".
- Icon `hub` màu primary và nhãn tiêu đề.
- Chip số liệu "{n} pages" và "{n} links", chữ nhỏ nền surface.
- Ô tìm "Find node...":
  - Có icon `search` và nút `close` để xóa khi đã gõ.
  - Khi gõ, dropdown dưới ô liệt kê tối đa 8 nút có title hoặc slug chứa từ khóa (không phân biệt hoa thường). Mỗi dòng có icon loại theo màu loại, title và slug mờ.
  - Bấm một dòng, hoặc nhấn Enter để chọn dòng đầu: nút đó được tô sáng (thành `centerSlug` của sơ đồ) và ô tìm được xóa.
- Chip lọc loại trang `entity`, `concept`, `topic`, `source`, mặc định bật hết. Mỗi chip có:
  - chấm màu loại (`wikiTypeColor`), icon `wikiTypeIcon` và nhãn `wikiTypeGroupLabel`;
  - khi bật: nền là màu loại pha rất nhạt, viền màu loại; khi tắt: mờ.
  - Bấm để bật/tắt. Sơ đồ chỉ nhận nút có loại đang bật, và cạnh có cả hai đầu thuộc tập nút đó.

**Trạng thái**:

- Đang tải lô đầu: khối căn giữa với icon `progress_activity` xoay, chữ "Building graph...".
- Tải xong mà không có nút: icon `hub` lớn mờ, tiêu đề "No wiki pages yet", mô tả "Upload and compile documents to start building the knowledge graph."
- Đang tải các lô sau:
  - thanh tiến độ mảnh ở mép trên vùng sơ đồ, độ rộng = đã tải / tổng;
  - nhãn nổi nhỏ "Loading {loaded} / {total} nodes...".

**Sơ đồ**: `WikiGraph` (3.15) chiếm hết vùng còn lại.

- `centerSlug` = nút đang tô sáng.
- `onNodeClick(slug)` mở **Sheet xem nhanh** từ bên phải, rộng 400px (540px từ breakpoint sm). Sheet gồm:
  - Tiêu đề: "Loading..." khi đang tải, sau đó là title trang.
  - Nút "View Full": điều hướng tới `/wiki/{slug}`; khi có projectId thêm `?scope_type=project&scope_id={projectId}`.
  - Nút icon `close`.
  - Thân:
    - đang tải: spinner kèm "Loading page...";
    - thành công: `WikiContent` với `content_md`;
    - lỗi: "Failed to load content.".
  - Dữ liệu từ `GET /api/wiki/pages/{slug}`, kèm `?scope_type=project&scope_id=…` khi có projectId.

### 2.4. `/wiki/branches/[id]/rebase` — giải quyết xung đột nhánh

File `app/(portal)/wiki/branches/[id]/rebase/page.tsx`. Client component.

**Tải nhánh**:

- `GET /api/wiki/branches/{id}`. Response là object nhánh (`id`, `name`, ...) với trường `drafts: DraftResponse[]`.
- Bản nháp được chọn mặc định: bản đầu tiên có `has_conflict`, nếu không có thì bản đầu tiên.
- Lỗi: chuyển hướng `/wiki/review?mine=true`.
- Đang tải: khối căn giữa, chữ "Đang tải thông tin nhánh đóng góp…".

**Tải bản chính** cho bản nháp đang chọn (bỏ qua khi `draft_kind` là `create`):

1. Gọi `GET /api/wiki/pages/{page_slug}?scope_type={page_scope_type}&scope_id={page_scope_id}`.
2. Nếu bản nháp có xung đột, ô kết quả được điền sẵn văn bản có dấu xung đột, gồm lần lượt các dòng:
   - dòng "<<<<<<< MAIN WIKI (Phiên bản mới nhất)";
   - nội dung trang chính;
   - dòng "=======";
   - nội dung bản nháp;
   - dòng ">>>>>>> NHÁNH CỦA BẠN (Bản thay đổi)".
3. Không xung đột: điền sẵn nội dung bản nháp.
4. Lỗi tải: nội dung trang chính coi như rỗng, ô kết quả điền nội dung bản nháp.

**Header**:

- Link "Quay lại danh sách nháp", icon `arrow_back`, tới `/wiki/review?mine=true`.
- Chip màu hồng đỏ nhạt "Giải quyết xung đột" và tên nhánh làm tiêu đề.
- "ID Nhánh: {id}" chữ mono nhỏ.
- Khi **không còn** bản nháp nào xung đột, bên phải hiện:
  - chip màu ngọc lục nhạt, icon `check_circle`, "Đã xử lý hết xung đột!";
  - nút primary "Gửi duyệt hợp nhất", link tới `/wiki/review?mine=true&draft={id nhánh}`.

**Thân**: lưới 2 cột, cột trái 260px.

- **Aside** "Danh sách tập tin", một dòng cho mỗi bản nháp:
  - icon `add_box` nếu là bản tạo mới, ngược lại `description`;
  - `page_title`, hoặc `page_slug`;
  - nếu xung đột: chấm tròn màu destructive nhấp nháy, tooltip "Có xung đột".
  - Dòng đang chọn có nền primary nhạt. Bấm để chọn.
- **Vùng chính**:
  - Chưa chọn gì: "Vui lòng chọn tập tin để xử lý."
  - Header có title, slug (mono, mờ) và chip trạng thái:
    - "Đang có xung đột (base v{base_version} vs main v{page_version})", nền hồng đỏ nhạt;
    - hoặc "Không có xung đột", nền ngọc lục nhạt.
  - Ba cột bằng nhau (xếp dọc trên màn hẹp), mỗi cột là khung viền có tiêu đề nhỏ:
    1. "1. Bản trên Main Wiki": khối văn bản giữ định dạng (pre-wrap, mono, cỡ nhỏ, cuộn). Rỗng thì hiện "_(Trang trống)_". Đang tải thì "Đang tải trang chính…".
    2. "2. Bản nháp của bạn": tương tự. Rỗng thì "_(Trang nháp trống)_".
    3. "3. Kết quả hợp nhất (Kết quả sửa đổi)": textarea mono có thể sửa, placeholder "Hợp nhất thủ công nội dung tại đây...". Bên dưới là dòng lỗi màu destructive (nếu có) và nút primary "Xác nhận giải quyết xung đột".
       - Khi đang gửi, nút hiện "Đang xử lý…".
       - Nút bị vô hiệu khi đang gửi hoặc khi bản nháp không có xung đột.
  - Gửi:
    - Gọi `POST /api/wiki/branches/{id}/rebase/{draftId}`, body `{ "resolved_content_md": "..." }`.
    - Thành công: tải lại nhánh. Danh sách và trạng thái xung đột cập nhật theo server; giữ lựa chọn nếu còn.
    - Lỗi: hiện `detail` của response, hoặc "Xử lý xung đột thất bại".

---

## 3. Thành phần

### 3.1. `WikiPageTree` — cây danh mục trang

**Props** (tất cả tùy chọn):

| Prop | Kiểu | Mặc định | Ý nghĩa |
|---|---|---|---|
| `activeSlug` | string | — | trang đang xem |
| `onDeleted` | (slug) => void | — | gọi sau khi xóa thành công |
| `pagesUrl` | string | `/api/wiki/pages` | nguồn danh sách |
| `linkQueryParams` | string | `""` | hậu tố gắn vào link |
| `onPageSelect` | (slug) => void | — | điều hướng nội bộ |
| `groupByScope` | boolean | false | khi bật, loại trang phạm vi `project` |
| `activeScope` | `WikiScope` | — | phạm vi dùng khi bấm tạo trang |
| `getCreateModeForScope` | (type, id) => `direct` \| `propose` \| null | — | |
| `onCreatePage` | (type, id) => void | — | |
| `onSearch` | () => void | — | mở hộp tìm kiếm |

**Dữ liệu**:

- Trang: lấy `getCachedPages(pagesUrl)` để hiện ngay, rồi `GET {pagesUrl}` → `WikiPageSummary[]` và lưu cache.
- Nguồn: lấy `getCachedSources()`, rồi `GET /api/sources?status=ready&page_size=1000`, lấy `items`, rồi `setCachedSources`. Lỗi thì coi là rỗng.
- Trạng thái lọc (`search`, `docFilter`, `collapsedSections`, `treeCollapsed`) đọc và ghi qua `useWikiStore`, nên còn nguyên khi chuyển trang.
- Vị trí cuộn của danh sách được lưu vào `wikiStore.sidebarScrollTop` mỗi khi cuộn, và khôi phục khi mount.
- Ô lọc cập nhật store ngay, nhưng phép lọc chạy trên giá trị đã debounce 150ms.

**Tập trang gốc**: bỏ trang loại `index`, `log`, `hot`. Khi `groupByScope` bật, bỏ thêm trang có `scope_type` là `project`.

**So khớp lọc**:

- Từ khóa và các trường đều được đưa qua `removeVietnameseTones`. Trang khớp khi title, slug, summary hoặc tên tài liệu nguồn (qua `getDocForPage` + `displaySourceTitle`) chứa từ khóa.
- Quy tắc riêng cho điều luật: nếu từ khóa là một số điều (chữ số, có thể kèm một chữ cái, có thể có tiền tố "điều"/"dieu"), trang có tiêu đề bắt đầu bằng "Điều {số đó}" khớp **chính xác**. Ví dụ "12" khớp "Điều 12" và không khớp "Điều 120"; "12a" khớp "Điều 12a".

**Danh sách tài liệu để lọc**:

- Mỗi nguồn sở hữu ít nhất một trang (theo `getDocForPage`) thành một option `{ id, title: displaySourceTitle, count }`, sắp theo tên kiểu vi.
- Trang không có nguồn gom vào option `other`, nhãn "Tài liệu khác / Kiến thức chung".
- `docFilter` trỏ tới option không còn tồn tại thì coi như không lọc.

**Chia mục**:

- **Chế độ một tài liệu** (đang lọc theo một tài liệu, hoặc chỉ có ≤ 1 tài liệu). Theo thứ tự:
  1. "Tổng quan văn bản", icon `menu_book`: trang có `page_type` là `summary`, `overview` hoặc `source`.
  2. "Điều khoản": trang có tiêu đề bắt đầu bằng "Điều ".
  3. Các trang còn lại, gom theo `wikiTypeGroupLabel(page_type)`; các nhóm sắp theo nhãn kiểu vi.
- **Chế độ nhiều tài liệu**: mỗi tài liệu là một mục, theo thứ tự danh sách tài liệu. Trong mục, trang tổng quan đứng trước rồi đến điều khoản. Khi mục có id nguồn, trang tổng quan hiện nhãn "Tổng quan văn bản" thay cho tiêu đề.
- Mọi danh sách trong mục sắp theo title, so sánh locale `vi` có so số (numeric), nên "Điều 2" đứng trước "Điều 10".

**Hành vi mục**:

- Mỗi mục thu gọn/mở được: lưu khóa mục trong `collapsedSections`, chevron xoay 90° khi mở.
- Khi đang lọc theo từ khóa, mọi mục đều mở.
- Mục chứa trang `activeSlug` tự mở.
- Header mục:
  - nhãn chữ hoa cỡ nhỏ, giãn chữ, màu mờ;
  - khi hover và mục gắn với một tài liệu: icon link `open_in_new` tới `/wiki/source/{id}`, tooltip "Mở văn bản gốc";
  - số trang ở bên phải.

**Dòng trang**:

- Link tới `/wiki/{slug}{linkQueryParams}`. Bấm chuột trái không kèm phím bổ trợ: chặn mặc định và gọi `onPageSelect(slug)` nếu có prop này.
- Tooltip là summary, hoặc title.
- Bên trái là chấm trạng thái: seed màu cát, developing màu cam, mature màu xanh mòng két, evergreen màu xanh lá.
- Title cắt bớt nếu dài.
- Dòng đang xem: nền primary nhạt, chữ primary, một vạch dọc màu primary ở mép trái. Khi đổi `activeSlug`, dòng này được cuộn vào tầm nhìn (kiểu "nearest").
- **Xóa hai bước**:
  1. Khi hover, bên phải dòng hiện nút icon `delete` nhỏ, tooltip `Xóa "{title}"`. Bấm vào thì "kích hoạt" dòng.
  2. Dòng đã kích hoạt hiện nút chữ đỏ "Xóa?", tooltip `Bấm lần nữa để xóa "{title}"`. Bấm lần nữa thì gọi `DELETE /api/wiki/pages/{slug}`, kèm `?scope_type=…&scope_id=…` theo phạm vi của trang khi khác global.
  - Bấm ra ngoài dòng thì hủy kích hoạt.
  - Đang xóa: spinner thay cho nút.
  - Thành công: `removeCachedPage(slug)`, tải lại danh sách, gọi `onDeleted(slug)`.
  - Lỗi: ghi console và hủy kích hoạt.

**Header cây**, theo thứ tự:

- Link `arrow_back` "Wiki" tới `/wiki/law`, tooltip "Về Kho tri thức".
- Nút icon `search`, tooltip "Tìm kiếm (Ctrl+K)", gọi `onSearch`.
- Link icon `hub` tới `/wiki/graph`, tooltip "Xem sơ đồ".
- Nút icon `add`, chỉ khi `getCreateModeForScope(activeScope)` khác null:
  - tooltip "Tạo trang mới" (direct) hoặc "Đề xuất trang mới (cần duyệt)" (propose);
  - gọi `onCreatePage` với phạm vi active, hoặc global khi không có.
- Viên đếm:
  - khi đang lọc: "{hiển thị}/{tổng}", tooltip "{x} / {y} trang";
  - khi không lọc: tổng, tooltip "{n} trang".
- Nút icon `left_panel_close`, tooltip "Thu gọn danh mục", đặt `treeCollapsed = true`.

**Ô lọc**:

- Icon `filter_list` bên trái, placeholder "Lọc trang...".
- Esc xóa nội dung.
- Khi có nội dung: nút icon `close`, tooltip "Xóa bộ lọc".

**Chọn tài liệu**: chỉ hiện khi có hơn 1 option.

- Select gồm "Tất cả văn bản ({tổng số trang})" và các mục "{tên} ({count})".
- Khi đang chọn một tài liệu thật: icon link `open_in_new` tới `/wiki/source/{id}`.

**Trạng thái**:

- Đang tải lần đầu: 8 dòng skeleton.
- Rỗng (sau lọc):
  - icon `search_off`;
  - `wiki.noPages` ("Không tìm thấy trang nào") và `wiki.noPagesDesc` ("Thử thay đổi từ khóa hoặc bộ lọc");
  - khi đang lọc: nút icon `restart_alt` với nhãn `wiki.reset` ("Đặt lại bộ lọc"), gọi `resetFilters`.

**Kích thước**:

- Khi mở: cột rộng khoảng 16rem, 18rem từ breakpoint lớn. Có viền phải, nền surface nhạt.
- Khi `treeCollapsed`: dải dọc hẹp khoảng 2,75rem, gồm
  - nút `left_panel_open`, tooltip "Mở danh mục";
  - nút `filter_list`, tooltip "Lọc trang": mở cây và focus ô lọc.

### 3.2. `WikiContent` — hiển thị markdown wiki

Props: `markdown: string`, `onWikiLinkClick?: (slug) => void`, `linkSuffix?: string` (mặc định `""`).

**Tiền xử lý** (`preprocessWikilinks(md)`, được export):

- Cú pháp "[[slug|văn bản]]" thành link markdown có chữ là văn bản, trỏ tới `/wiki/slug`.
- "[[slug]]" thành link có chữ là slug, trỏ tới `/wiki/slug`.
- Sau đó áp `normalizeMarkup`.

**Bộ render**: markdown với GFM (bảng, footnote, gạch ngang, task list) và HTML thô. **Không** xử lý frontmatter, **không** có callout/admonition riêng: blockquote hiển thị như blockquote thường.

**Lọc URL** (áp cho link và ảnh). Chỉ giữ:

- `image://…`;
- data URI ảnh base64 kiểu png, jpeg, gif, webp, bmp;
- `http://`, `https://`, `mailto:`, `tel:`;
- liên kết bắt đầu bằng `#`, `/`, `./`, `../`.

URL khác bị thay bằng chuỗi rỗng.

**Mục lục**:

- Lấy các dòng heading cấp 2–4 trong markdown. Văn bản heading được bỏ ký hiệu định dạng inline (`*`, `_`, backtick, cú pháp link).
- id của heading: chữ thường, bỏ ký tự không phải chữ/số/khoảng trắng/gạch ngang, rồi đổi khoảng trắng thành gạch ngang. Renderer heading phải tạo **cùng** id.
- Chỉ hiện khi có ít nhất 3 heading.
- Hiện thành thẻ thu gọn được ở đầu nội dung, mặc định mở. Header có icon `toc`, "Mục lục · N", và `expand_less` / `expand_more`.
- Mỗi mục thụt lề 16px cho mỗi cấp tính từ cấp 2.
- Heading đang đọc được theo dõi bằng IntersectionObserver (lề gốc −80px phía trên, −60% phía dưới, ngưỡng 0,5). Mục tương ứng tô chữ primary và đậm.
- Bấm mục: cuộn mượt tới heading.

**Quy tắc render phần tử**:

- h1: cỡ 3xl đậm.
- h2: cỡ 2xl, viền dưới, có id và scroll-margin trên.
- h3, h4: cỡ nhỏ dần, có id và scroll-margin.
- p: cỡ chữ nhỏ (sm), giãn dòng thoáng.
- `mark`: nền hổ phách nhạt, bo góc.
- Link:
  - href bắt đầu bằng `/wiki/` và có `onWikiLinkClick`: render nút dạng link màu primary, bấm thì gọi callback với slug (phần sau `/wiki/`, đã giải mã);
  - href `/wiki/` không có callback: link nội bộ Next tới href + `linkSuffix`;
  - link ngoài (`http(s)`): mở tab mới, `rel` noopener noreferrer;
  - còn lại: thẻ a thường.
- Code inline: chữ mono màu primary trên nền surface-variant, bo góc.
- Khối code:
  - khung viền bo góc, nền surface, cuộn ngang;
  - nút sao chép ở góc trên phải, chỉ hiện khi hover: icon `content_copy`, tooltip "Copy code";
  - sau khi chép, icon thành `check` trong 2 giây.
- blockquote: viền trái màu primary, chữ nghiêng màu mờ.
- ul: chấm tròn; ol: số; li giãn dòng; hr: đường kẻ mảnh.
- strong: semibold; em: nghiêng.
- Ảnh:
  - src không phải `image://`: ảnh lazy-load, bo góc, rộng tối đa 100%;
  - src `image://{uuid}`: thu mọi uuid trong markdown, gọi `useImageResolver` một lần, rồi render `WikiImage` (3.3) với status ok, denied, loading hoặc missing theo mục 1.6.
- Bảng: dùng các thành phần Table của `components/ui`, trong khung viền bo góc cuộn ngang. Ô tiêu đề chữ hoa cỡ xs.

### 3.3. `WikiImage`

Props: `src?: string`, `alt?: string`, `status: "ok" | "loading" | "denied" | "missing"`.

- `loading`: khung nhạt, chữ "Đang tải hình ảnh…".
- `denied`: khung viền đứt, icon `lock`, chữ "Hình ảnh bị giới hạn quyền truy cập", alt in nghiêng bên dưới.
- `missing` (hoặc không có src): icon `broken_image`, chữ "Không tìm thấy hình ảnh", kèm alt.
- `ok`:
  - Một nút bọc ảnh, `aria-label` = alt hoặc "Hình ảnh wiki". Ảnh cao tối đa 480px, giữ tỉ lệ. Alt làm chú thích nhỏ bên dưới.
  - Bấm mở Dialog rộng tối đa bằng giá trị nhỏ hơn của 95vw và 1400px. Trong dialog: ảnh cao tối đa 80vh, alt, và link "Tải xuống" (icon `download`, thuộc tính download) tới src.

### 3.4. `WikiEditor`

Export kiểu `WikiEditorProps`:

- `initialContent: string`, `noteLabel: string`, `notePlaceholder?: string`, `saveLabel: string`;
- `onSave(content: string, note: string): Promise<void>`;
- `onCancel(): void`.

Bố cục từ trên xuống:

1. `MarkdownEditor` (3.5) với nội dung đang sửa.
2. Nhãn `noteLabel` và input một dòng. Placeholder là `notePlaceholder`, mặc định "Optional — describe what you changed".
3. Dòng lỗi màu destructive, nếu có.
4. Hàng nút căn phải:
   - "Cancel" (viền), gọi `onCancel`;
   - nút primary với icon `save` và `saveLabel`. Khi đang lưu: spinner và "Saving…".
   - Nút lưu vô hiệu khi nội dung rỗng sau trim hoặc đang lưu.

Lưu: gọi `onSave`. Nếu promise bị từ chối: hiện thông điệp lỗi, hoặc "Save failed".

### 3.5. `MarkdownEditor`

Props:

- `value: string`, `onChange(v: string)`;
- `placeholder?: string`, mặc định "Write markdown here...";
- `minHeightClass?`: chiều cao tối thiểu, mặc định 400px.

**Tab**: "Edit" và "Preview", với nhãn mờ "Markdown" ở bên phải. Preview là `WikiContent` của value; rỗng thì "Nothing to preview.".

**Thanh công cụ** (chỉ ở tab Edit), mỗi nút là icon với tooltip:

| Icon / nhãn | Tooltip | Hành vi |
|---|---|---|
| `format_bold` | "Bold (Ctrl+B)" | bọc vùng chọn bằng `**`; không có vùng chọn thì chèn chữ mẫu "bold text" |
| `format_italic` | "Italic (Ctrl+I)" | bọc bằng `*`, chữ mẫu "italic text" |
| `code` | "Inline code" | bọc bằng backtick, chữ mẫu "code" |
| ngăn cách | | |
| "H2" | "Heading 2" | thêm tiền tố dòng "## " |
| "H3" | "Heading 3" | thêm tiền tố "### " |
| ngăn cách | | |
| `format_list_bulleted` | "Bullet list" | tiền tố "- " |
| `format_list_numbered` | "Numbered list" | tiền tố "1. " |
| `format_quote` | "Blockquote" | tiền tố "> " |
| ngăn cách | | |
| `data_object` | "Code block" | chèn khối code rào ba backtick, con trỏ đặt ở dòng trong |
| `link` | "Link" | bọc thành link markdown: chữ là vùng chọn (mặc định "link text"), đích là "url" |
| `account_tree` | "Wikilink — type [[ to pick a page" | chèn "[[" và mở bảng chọn trang |
| `horizontal_rule` | "Horizontal rule" | chèn một dòng trống, ba gạch ngang, rồi một dòng trống |

- Tiền tố dòng áp vào đầu dòng chứa con trỏ.
- Sau khi bọc hoặc chèn chữ mẫu, phần chữ vừa chèn được chọn sẵn và textarea giữ focus.
- Phím tắt Ctrl/⌘+B và Ctrl/⌘+I trong textarea.

**Textarea**: chữ mono, có thể kéo giãn dọc, tắt kiểm tra chính tả, có placeholder.

**Tự hoàn thành wikilink**:

- Nhận diện: từ con trỏ nhìn ngược tối đa 80 ký tự tìm "[[". Dừng (không gợi ý) nếu gặp xuống dòng hoặc "]" trước khi thấy. Truy vấn là đoạn chữ giữa "[[" và con trỏ.
- Tính lại khi gõ, khi click, và khi nhả các phím mũi tên/Home/End.
- Bảng đóng 150ms sau khi textarea mất focus.
- Danh sách trang lấy một lần khi mount bằng `GET /api/wiki/pages`.
- Tọa độ bảng lấy từ `getTextareaCaretCoords` (1.5).
- Chọn một trang: thay đoạn từ "[[" đến con trỏ bằng "[[" + slug + "]]", rồi đặt con trỏ sau "]]".

### 3.6. `WikilinkAutocomplete`

Props:

- `pages: WikiPageSummary[]`, `query: string`, `caret: CaretCoords`;
- `onPick(page)`, `onClose()`.

**Kết quả**: tối đa 8.

- Truy vấn rỗng: 8 trang đầu.
- Ngược lại, chấm điểm từng trang theo slug và title (không phân biệt hoa thường), lấy điểm cao nhất của hai trường:
  - trùng khớp hoàn toàn: 100;
  - bắt đầu bằng truy vấn: 50;
  - chứa truy vấn: 20;
  - không chứa: loại.
- Sắp theo điểm giảm dần.

**Bàn phím** (bắt ở window, pha capture, nên textarea không nhận các phím này):

- ↑ / ↓: di chuyển, vòng quanh khi tới đầu/cuối;
- Enter hoặc Tab: chọn mục đang trỏ;
- Esc: đóng.

**Vị trí**: render qua portal vào body, `position: fixed`, rộng 340px, cao tối đa 280px, z-index 100.

- Mặc định đặt cách 4px dưới dòng con trỏ.
- Nếu tràn đáy viewport (chừa 16px) thì lật lên trên dòng con trỏ.
- `left` bị giới hạn không vượt quá chiều rộng viewport − 340 − 16.
- Chặn `mousedown` trên bảng để textarea không mất focus.

**Nội dung**:

- Header: "Link to page" và gợi ý "↑↓ Enter".
- Không có kết quả: `No pages match “{query}”.`
- Mỗi mục gồm:
  - icon loại (`wikiTypeIcon`) tô màu loại;
  - title;
  - dòng mono nhỏ gồm slug, cộng " · {scope_name}" nếu trang không thuộc global.
- Mục đang trỏ có nền primary nhạt. Hover cũng đổi mục trỏ.

### 3.7. `WikiCreatePageDialog`

Props:

| Prop | Kiểu | Mặc định |
|---|---|---|
| `open` | boolean | — |
| `onOpenChange` | (open: boolean) => void | — |
| `mode` | `direct` \| `propose` | — |
| `defaultScope` | `WikiScope` | — |
| `scopes` | `WikiScope[]` | — |
| `getCreateModeForScope` | (type, id) => mode \| null | tùy chọn |
| `defaultTitle` | string | `""` |

**Trạng thái**:

- Mỗi lần mở: reset form, title = `defaultTitle`, phạm vi = `defaultScope`.
- Slug tự sinh từ title cho tới khi người dùng sửa ô slug tay. Cách sinh:
  1. Chữ thường, chuẩn hóa NFKD, bỏ dấu, "đ" thành "d".
  2. Mỗi chuỗi ký tự không phải chữ/số liên tiếp thành một "-".
  3. Bỏ "-" ở đầu và cuối.
- Dropdown phạm vi chỉ liệt kê các phạm vi mà `getCreateModeForScope` khác null. Nhãn là `name`; với phạm vi khác global thêm " ({scope_type})".
- Chế độ hiệu lực = `getCreateModeForScope(phạm vi đang chọn)`, nếu không có thì là `mode`.

**Bố cục** (Dialog), theo chế độ hiệu lực:

- Tiêu đề: `wiki.createTitle` ("Tạo trang mới") cho direct, `wiki.proposeTitle` ("Đề xuất trang mới") cho propose.
- Mô tả: `wiki.createDesc` / `wiki.proposeDesc`.
- Trường:
  - `wiki.pageTitle`: input, placeholder "e.g. Fire Safety Procedure", tự focus.
  - `wiki.slugLabel`: input mono, placeholder "fire-safety-procedure".
  - `wiki.scopeLabel`: select phạm vi.
  - `wiki.contentLabel`: `MarkdownEditor` cao tối thiểu 280px. Placeholder gợi ý viết mục "# Overview" và dùng [[wikilinks]] để liên kết trang khác.
  - Chỉ ở chế độ propose: `wiki.noteForReviewer` với input placeholder `wiki.notePlaceholder`.
- Dòng lỗi.
- Footer:
  - `common.cancel`;
  - nút chính: direct là `wiki.createPageBtn` với icon `add`; propose là `wiki.submitProposalBtn` với icon `send`. Spinner khi đang gửi.

**Kiểm tra**: title, slug và content (sau trim) đều bắt buộc. Thiếu thì báo "Title, slug, and content are required.".

**Gửi**:

- Direct: `POST /api/wiki/pages`, body:
  - `slug`, `title`, `page_type` = `concept`, `content_md`;
  - `scope_type`, `scope_id`;
  - `knowledge_type_slugs` = mảng rỗng.
  - Thành công: đóng hộp và điều hướng tới `/wiki/{slug trả về}`, kèm `?scopeType=…&scopeId=…` khi phạm vi khác global.
- Propose: `POST /api/wiki/drafts/create` với cùng các trường, thêm `note` (rỗng thì null). Thành công: đóng hộp và điều hướng tới `/wiki/{slug}`.
- Lỗi: hiện `detail` của response, hoặc "Submit failed".

### 3.8. `WikiDraftBanner`

Props:

- `drafts: DraftResponse[]`;
- `currentContent?: string`, mặc định `""`;
- `currentUserId?: string | null`, mặc định null;
- `onApproved(id)`, `onRejected(id)`;
- tùy chọn: `onChangesRequested(id)`, `onResubmitDraft(draft)`, `onWithdrawn(id)`.

Hằng: độ dài ghi chú tối thiểu là **20** ký tự.

**Phân trang**:

- Banner hiện một bản nháp tại một thời điểm. Khi có hơn 1 bản: nút `chevron_left` / `chevron_right` và "i/tổng".
- Sau mỗi hành động làm bản nháp rời danh sách, chỉ số giảm 1 (không nhỏ hơn 0).

**Thăm dò AI**: khi bản đang hiện có `ai_check_status` là `pending` hoặc `running`, cứ 3000ms gọi `GET /api/wiki/drafts/{id}` và cập nhật `ai_check_status`, `ai_check_results` cục bộ. Dừng khi trạng thái khác hai giá trị trên hoặc khi unmount.

**Bảng màu**:

- `needs_revision`: tông xanh dương nhạt, icon `edit_note`.
- Còn lại: tông hổ phách nhạt, icon `pending`.

**Dòng tiêu đề**:

- Theo trạng thái:
  - `needs_revision`: `wiki.banner.waitingAuthor`;
  - `withdrawn`: `wiki.banner.withdrawn`;
  - còn lại: `wiki.banner.pendingDraft`.
  - `{name}` là `author_name`, hoặc "Unknown".
- Theo sau là " · {ngày tạo}".
- Chip:
  - "round N" khi `revision_round` > 0;
  - chip xung đột khi `has_conflict`: "conflict — page advanced past v{base_version hoặc ?} to v{page_version}", tông hồng đỏ;
  - chip thống kê tác giả khi có `author_stats`: "{approved}✓ · {accuracy×100 làm tròn}%". Tooltip "x approved · y rejected", thêm " · z returned" khi `needs_revision` > 0. Màu theo bậc:
    - cao (`total_reviewed` ≥ 10 và `accuracy` ≥ 0,9): ngọc lục;
    - khá (≥ 3 và ≥ 0,7): hổ phách;
    - còn lại: mờ.

**Dòng phụ**:

- `note` trong ngoặc kép, in nghiêng.
- `wiki.banner.reviewerAsked` + `last_returned_note`, khi có.
- `wiki.banner.suggestedReviewers` + danh sách "tên (điểm)", khi có. Tên lấy `name`, hoặc `email`.
- Bản `create`: thêm dòng "Slug: … · Type: … · Scope: …" lấy từ `suggested_metadata` (thiếu thì lấy từ bản nháp), và "Tags: …" khi có `knowledge_type_slugs`.

**Tab xem**:

- Bản `create`: chỉ có tab Proposed.
- Bản sửa: ba tab `wiki.banner.tabDiff`, `wiki.banner.tabProposed`, `wiki.banner.tabCurrent`. Mặc định là Diff.
- Ở tab Diff có select `wiki.banner.compareWith`:
  - mặc định so với trang hiện tại;
  - các option khác là những bản nháp sửa khác trong danh sách, nhãn "Draft by {tên} (round {revision_round+1})".
- Vùng xem cao tối đa khoảng 18rem, cuộn:
  - Diff: `WikiDraftDiff` (3.9), mode unified, 3 dòng ngữ cảnh. Bên cũ là nội dung đem so, bên mới là bản đang hiện.
  - Proposed: `WikiContent` của bản nháp; rỗng thì `wiki.banner.emptyContent`.
  - Current: `WikiContent` của `currentContent`; rỗng thì "_(empty page)_".

**Bảng AI**: `WikiAiCheckPanel` (3.10) với trạng thái và kết quả hiện tại.

**Form ghi chú** (khi bấm Yêu cầu sửa hoặc Từ chối):

- Nhãn: `wiki.banner.requestChangesLabel` hoặc `wiki.banner.rejectLabel`.
- Textarea với placeholder `wiki.banner.requestChangesPrompt` / `wiki.banner.rejectPrompt`.
- Bộ đếm "n/20" kèm `wiki.banner.minChars`.
- Gửi khi chưa đủ 20 ký tự (sau trim): báo "Please write at least 20 characters explaining your decision.".

**Nút hành động**, theo ngữ cảnh:

- Đang mở form:
  - `common.cancel`;
  - Từ chối: `wiki.banner.confirmReject`, kiểu destructive, icon `cancel`;
  - Yêu cầu sửa: `wiki.banner.sendBack`, icon `edit_note`.
- Bản nháp của chính user (`author_id` = `currentUserId`):
  - Khi `needs_revision`: `wiki.banner.editResubmit`, gọi `onResubmitDraft(draft)`.
  - Khi chưa thu hồi: `wiki.banner.withdraw`, icon `remove_circle`. Hỏi xác nhận bằng hộp thoại xác nhận của trình duyệt: "Withdraw this draft? It will be removed from the review queue.". Đồng ý thì gọi `POST /api/wiki/drafts/{id}/withdraw`, rồi `onWithdrawn(id)`.
  - Đã thu hồi: dòng chữ `wiki.banner.withdrawnNotice`.
- Bản của người khác đang `needs_revision`: dòng chữ `wiki.banner.waitingResubmit`. Đang `withdrawn`: `wiki.banner.noLongerReview`.
- Còn lại:
  - `wiki.banner.requestChangesBtn`: mở form yêu cầu sửa;
  - `wiki.banner.rejectBtn`: mở form từ chối;
  - `wiki.banner.approveBtn`: primary, icon `check_circle`.

**Endpoint**:

| Hành động | Lời gọi | Sau khi thành công |
|---|---|---|
| Duyệt | `POST /api/wiki/drafts/{id}/approve`, body `{ "allow_conflict": true }` khi bản có xung đột, ngược lại body rỗng hoặc `allow_conflict` false | `onApproved(id)` |
| Từ chối | `POST /api/wiki/drafts/{id}/reject`, body `{ "reviewer_note": "..." }` | `onRejected(id)` |
| Yêu cầu sửa | `POST /api/wiki/drafts/{id}/request-changes`, body `{ "reviewer_note": "..." }` | `onChangesRequested(id)` |
| Thu hồi | `POST /api/wiki/drafts/{id}/withdraw` | `onWithdrawn(id)` |

Lỗi hiện `detail` của response, hoặc theo thứ tự trong bảng: "Approve failed", "Action failed", "Action failed", "Withdraw failed".

### 3.9. `WikiDraftDiff`

Props:

- `oldText: string`, `newText: string`;
- `mode?`: `unified` (mặc định) hoặc `split`;
- `contextLines?: number`, mặc định 3;
- `groupByHeading?: boolean`, mặc định true.

**So sánh**: diff theo dòng. Hai văn bản giống hệt thì hiện "No changes between the current page and the proposed content.".

**Rút gọn ngữ cảnh** (N = `contextLines`), áp cho mỗi chuỗi dòng không đổi liên tiếp:

- ở đầu văn bản: chỉ giữ N dòng cuối;
- ở cuối văn bản: chỉ giữ N dòng đầu;
- ở giữa và dài hơn 2N: giữ N dòng mỗi bên.

Phần bị lược thay bằng một dòng mờ căn giữa "··· N unchanged line(s) ···".

**Unified**: chữ mono cỡ nhỏ. Mỗi dòng có cột dấu bên trái:

- không đổi: dấu "·", chữ mờ;
- thêm: dấu "+", nền ngọc lục nhạt, chữ ngọc lục, viền trái ngọc lục;
- bớt: dấu "−", nền hồng đỏ nhạt, chữ hồng đỏ, viền trái hồng đỏ.

**Gom theo heading** (khi bật):

- Mỗi dòng không đổi là heading markdown mở một nhóm mới. Các dòng trước heading đầu tiên thuộc nhóm "không tiêu đề".
- Chỉ khi có hơn 1 nhóm, mỗi nhóm mới thu gọn được. Header nhóm gồm:
  - `chevron_right` khi đóng, `expand_more` khi mở;
  - "### {heading}" chữ mono;
  - nhãn "changed" (hổ phách) hoặc "unchanged" (mờ).
- Nhóm có thay đổi và nhóm không tiêu đề mặc định mở. Nhóm không đổi mặc định đóng.

**Split**:

- Hai cột "Current" và "Proposed". Các dòng bớt và thêm liền nhau được ghép đôi theo thứ tự (cách ghép đơn giản, không tối ưu).
- Trong mỗi cặp, so sánh mức từ (kể cả khoảng trắng):
  - phần thêm ở cột phải: nền ngọc lục;
  - phần bớt ở cột trái: nền hồng đỏ, gạch ngang.
- Dòng không có cặp hiện ô trống ở cột kia.

### 3.10. `WikiAiCheckPanel`

Props: `status: AiCheckStatus | string`, `results: AiCheckResults | null`.

**Huy hiệu trạng thái**:

| status | Nhãn | Icon | Tông |
|---|---|---|---|
| `passed` | "AI: all clear" | `check_circle` | ngọc lục |
| `warned` | "AI: needs attention" | `warning` | hổ phách |
| `failed` | "AI: critical flags" | `report` | hồng đỏ |
| `running` | "AI: running…" | `progress_activity` (xoay) | xanh dương |
| `queued` | "AI: queued" | `schedule` (xoay) | xanh dương |
| `skipped` | "AI: skipped" | `skip_next` | mờ |
| `pending` / khác | "AI: pending" | `schedule` | mờ |

**Header**:

- Huy hiệu và tóm tắt "x pass · y warn · z fail", thêm " · n skipped" khi n > 0.
- Bấm để thu gọn/mở. Mặc định mở khi có mục cảnh báo hoặc lỗi.

**Không có `results`**, theo status:

- running: "AI pre-review in progress";
- queued: "AI pre-review queued — worker will pick it up shortly";
- còn lại: "AI pre-review has not run yet".

**Mục bị gắn cờ** (status `warn` hoặc `fail`):

- Icon: `warning` hổ phách cho warn, `cancel` hồng đỏ cho fail.
- Nhãn kiểm tra in đậm, nhóm (category) mờ, `message`.
- Tối đa 5 `matches`, mỗi match định dạng như sau:
  - chuỗi: giữ nguyên;
  - object có slug và score: "slug (score×100 làm tròn%)";
  - chỉ có slug: slug;
  - có line: "L{line}: {snippet}";
  - khác: chuỗi JSON.
- Có hơn 5 match: "+N more…".
- Không có mục nào bị gắn cờ: "All checks passed.".

**Mục pass và skipped**: gói sau nút "Show N pass · M skipped" / "Hide N pass · M skipped". Icon `check_circle` cho pass, `remove_circle` cho skipped.

**Chân**: "AI checks are advisory — they do not block approval."

**Nhãn và nhóm theo `id`**:

| id | Nhãn | Nhóm |
|---|---|---|
| `pii.email` | "Email addresses" | "Sensitive data" |
| `pii.phone_vn` | "Phone numbers" | "Sensitive data" |
| `pii.cccd_vn` | "National ID numbers" | "Sensitive data" |
| `secret.api_key_sk` | "Generic API key (sk-…)" | "Sensitive data" |
| `secret.anthropic` | "Anthropic API key" | "Sensitive data" |
| `secret.aws_access` | "AWS access key" | "Sensitive data" |
| `secret.github_pat` | "GitHub personal access token" | "Sensitive data" |
| `secret.google_api` | "Google API key" | "Sensitive data" |
| `secret.jwt` | "JWT token" | "Sensitive data" |
| `secret.private_key` | "Private key block" | "Sensitive data" |
| `links.broken` | "Broken wikilinks" | "Structure" |
| `links.self` | "Self-referencing link" | "Structure" |
| `length.sanity` | "Content length" | "Structure" |
| `markdown.heading_jump` | "Heading hierarchy" | "Structure" |
| `markdown.unclosed_fence` | "Unclosed code fence" | "Structure" |
| `semantic.duplicate` | "Similar existing pages" | "Duplicates" |
| `llm.tone` | "Writing tone" | "AI judgment" |
| `llm.scope_fit` | "Topic fit" | "AI judgment" |
| `llm.factual` | "Factual concerns" | "AI judgment" |
| `runner.error` | "AI runner error" | "System" |

id lạ:

- Nhãn: lấy phần sau dấu chấm đầu tiên, đổi gạch dưới thành khoảng trắng, viết hoa chữ đầu mỗi từ.
- Nhóm: phần trước dấu chấm, đổi gạch dưới thành khoảng trắng.

### 3.11. `WikiSidebarRight` (bí danh `WikiBacklinks`)

Props: `slug: string`, `page: WikiPageDetail`, `linkSuffix?: string`, `onSelectPage?: (slug) => void`.

Cột rộng khoảng 18rem, viền trái, cuộn dọc.

**Dữ liệu**:

- Sơ đồ cục bộ: `GET /api/wiki/graph?slug={slug}&depth=1` → `WikiGraphData`. Lỗi thì coi là rỗng.
- Tiêu đề trang liên kết lấy từ danh sách đã cache của `/api/wiki/pages`; nếu chưa có cache thì gọi một lần và lưu.
- Slug không có tiêu đề: lấy đoạn cuối của slug, đổi gạch ngang thành khoảng trắng.

**Nội dung**:

- Khối "Liên kết", gồm hai mục con thu gọn được, mặc định mở:
  - "Liên kết trỏ đến" (`page.backlinks`);
  - "Liên kết đi ra" (`page.outlinks`).
  - Mỗi mục có số đếm và bị ẩn khi đếm bằng 0.
  - Mỗi dòng là tiêu đề trang. Bấm thì gọi `onSelectPage(slug)`, hoặc theo link `/wiki/{slug}{linkSuffix}`.
  - Cả hai đều rỗng: "Chưa có liên kết.".
- Khối "Sơ đồ cục bộ": `WikiGraphMini` (3.15) với slug và dữ liệu sơ đồ. Chỉ hiện khi có hơn 1 nút.

### 3.12. `WikiSearchDialog`

Props: `open: boolean`, `onOpenChange(open)`, `onSelectPage?: (slug) => void`.

**Hành vi**:

- Khi mở: lấy cache `/api/wiki/pages`, hoặc gọi `GET /api/wiki/pages` rồi lưu cache.
- Ô tìm tự focus sau 50ms. Khi đóng, xóa truy vấn.
- Truy vấn debounce 120ms.
- Bỏ trang loại `index` và `log`. Trang khớp khi title, slug hoặc summary chứa truy vấn (không phân biệt hoa thường). Truy vấn rỗng thì hiện tất cả.
- Tối đa 60 kết quả, gom nhóm theo thứ tự loại `entity`, `concept`, `topic`, `source` (loại khác xếp sau). Mỗi nhóm có header: icon loại tô màu loại và `wikiTypeGroupLabel`.
- Dòng kết quả:
  - title (đậm) và summary (mờ, một dòng);
  - slug mono nhỏ ở bên phải.
  - Có thể chọn bằng ↑/↓ và Enter, hoặc bằng click.
  - Chọn: gọi `onSelectPage(slug)` nếu có, ngược lại điều hướng tới `/wiki/{slug}`. Sau đó đóng hộp.

**Nhãn**:

- Placeholder `wiki.searchDialogPlaceholder`.
- Có truy vấn mà không có kết quả: `wiki.noSearchMatch`. Chưa có trang nào: `wiki.noSearchYet`.
- Chân hộp:
  - phím "↑↓" + `wiki.navHint`;
  - "↵" (chọn);
  - "Esc" + `wiki.closeHint`;
  - bên phải "{N} " + `wiki.pagesCount`.

### 3.13. `WikiStatusBadge`

- Export kiểu `WikiStatus` = `seed` | `developing` | `mature` | `evergreen`.
- Component nhận `status: string` và `className?`.
- `status` được đưa về chữ thường. Giá trị không hợp lệ coi là `seed`.
- Hiển thị: viên tròn nhỏ gồm chấm màu và nhãn.

| status | Nhãn | Màu |
|---|---|---|
| seed | "Seed" | cát |
| developing | "Developing" | cam |
| mature | "Mature" | xanh mòng két |
| evergreen | "Evergreen" | xanh lá |

- Tooltip là `wiki.status.{status}`.

### 3.14. `WikiTypeBadge` và các hàm loại trang

**Cấu hình theo loại**:

| page_type | Icon | Nhãn | Màu |
|---|---|---|---|
| entity | `article` | "Page" | đất nung |
| concept | `article` | "Page" | nâu xám ấm |
| topic | `article` | "Page" | xanh xô thơm |
| source | `description` | "Source" | tím nhạt trầm |
| index | `list_alt` | "Index" | xám trung tính |
| log | `history` | "Log" | xám trung tính |
| hot | `local_fire_department` | "Hot Cache" | đất nung |

**`WikiTypeBadge({ type, className? })`**:

- Viên tròn gồm icon nhỏ và nhãn, chữ màu loại.
- Nền là màu loại ở độ đậm khoảng 10%; viền cùng màu, nhạt.
- Loại lạ hiển thị như `concept`.

**Hàm export**:

- `wikiTypeIcon(type)`: icon theo bảng; mặc định `article`.
- `wikiTypeColor(type)`: màu theo bảng; mặc định xám trung tính.
- `wikiTypeGroupLabel(type)`:
  - entity, concept, topic → "Pages";
  - source → "Sources";
  - index → "Index"; log → "Log"; hot → "Hot Cache";
  - loại khác → trả nguyên `type`.

### 3.15. `WikiGraph`, `WikiGraphMini` và tiện ích sơ đồ

Thư viện: sơ đồ lực 2D trên canvas (react-force-graph-2d) với các lực d3-force. Component được nạp động, chỉ chạy phía client.

**Kiểu** (`wiki-graph/types`):

- `NodeInput`: `slug`, `title`, `page_type`, `status?`, `scope_type?`, `scope_id?`, `scope_name?`.
- `EdgeInput`: `from`, `to`, `type?`, `label?`, `predicate?`, `weight?`, `evidence?`, `target_doc_number?`.
- `GraphNode`: node nội bộ, gồm `id` = slug, các trường của NodeInput, `degree`, và tọa độ mô phỏng.
- `GraphLink`: `source`, `target` và các trường của EdgeInput.

**Tiện ích** (`wiki-graph/utils`):

- `scopeColor(idx)`: trả lần lượt xoay vòng một trong 6 màu dịu.
- `nodeRadius(degree, mini)`:
  - mini: 3 + √degree × 1,2, kẹp trong [3, 6];
  - thường: 5 + √degree × 3, kẹp trong [5, 18].
- `convexHull(points)` và `hullToPath(hull, padding)`: bao lồi và đường viền làm tròn. Hiện chưa được sơ đồ dùng, nhưng vẫn export.

**`WikiGraphMini({ slug, nodes, edges })`** = `WikiGraph` với `centerSlug = slug`, `mini` bật, `height` 180.

**`WikiGraph({ nodes, edges, centerSlug?, mini = false, height?, onNodeClick? })`**:

Export kèm hai hằng tra cứu quan hệ:

- `RELATION_COLORS`: khóa quan hệ → màu.
- `RELATION_LABELS`: khóa quan hệ → nhãn.

| Khóa | Nhãn | Màu (vai trò) |
|---|---|---|
| `la_mot` | "Là một (is-a)" | xanh dương |
| `thuoc` | "Thuộc về (part-of)" | tím |
| `quy_dinh` | "Quy định (regulates)" | ngọc lục |
| `ap_dung_cho` | "Áp dụng cho (applies-to)" | hổ phách |
| `lien_quan` | "Liên quan (relates-to)" | xám đá |
| `sua_doi` | "Sửa đổi (amends)" | đỏ |
| `bo_sung` | "Bổ sung (supplements)" | cam |
| `thay_the` | "Thay thế (replaces)" | hồng đỏ |
| `bai_bo` | "Bãi bỏ (repeals)" | đỏ sẫm |
| `huong_dan` | "Hướng dẫn (guides)" | xanh mòng két |
| `can_cu` | "Căn cứ (basis)" | xanh da trời |
| `dan_chieu` | "Dẫn chiếu (cites)" | xám đá |
| `wikilink` | "Liên kết wiki" | xám trong mờ |
| `concept` | — | xanh dương |
| `legal` | — | đỏ |

**Nền canvas**: màu kem ấm.

**Chế độ màu nút** (mặc định "scope"):

- scope: global màu be, department màu đất nung, project màu cá hồi.
- status (Maturity): màu theo bảng status ở 3.13.

**Bộ lọc cạnh**: `all` (mặc định), `concept`, `legal`, `wikilink`. Cạnh thiếu `type` coi là `wikilink`.

**Dựng dữ liệu**:

1. Lọc cạnh theo bộ lọc, chỉ giữ cạnh có cả hai đầu tồn tại.
2. Tính bậc của nút trên tập cạnh đã lọc.
3. Tái sử dụng đối tượng nút cũ theo slug, để mô phỏng giữ vị trí khi dữ liệu tăng dần.

**Bố trí theo thành phần liên thông**:

- Tìm các thành phần liên thông và rải chúng theo trục X. Chừa lề 15% chiều rộng mỗi bên; tâm các thành phần cách đều trong khoảng còn lại.
- Đích X của mỗi nút là tâm thành phần của nó. Nút thuộc department hoặc project có đích X = 0,7 × X của cụm phạm vi + 0,3 × X của thành phần.

**Lực**:

- forceX về đích X, độ mạnh 0,1.
- forceY về 0, độ mạnh 0,05.
- Lực đẩy: mini −60, thường −120, nhân với √(degree + 1).
- Lực liên kết: khoảng cách mini 35, thường 70; độ mạnh 0,4.
- Gỡ bỏ lực center mặc định.
- Nút `centerSlug` được ghim tại (0, 0).
- Sau khi cấu hình thì làm nóng lại mô phỏng (reheat).

**Engine**:

- cooldownTicks: mini 50, thường 90.
- alphaDecay 0,06; velocityDecay 0,55.
- Zoom trong khoảng 0,2–5.
- Mini: tắt zoom, pan và kéo nút.
- Mũi tên cạnh: dài 3,5 (mini thì 0), đặt ở vị trí tương đối 0,88 dọc cạnh.

**Khớp khung**: chỉ một lần, khi engine dừng lần đầu.

- Thường, ≤ 1 nút: đưa tâm về nút, zoom 2 trong 400ms.
- Thường, nhiều nút: zoomToFit(400ms, đệm 60).
- Mini: đưa tâm về (0, 0), zoom 1,4.

**Vẽ nút**:

- Bán kính lấy từ `nodeRadius`; nút đang hover phóng 1,3 lần.
- Khi đang hover một nút, các nút không phải nút đó và không kề nó bị làm mờ (alpha 0,15).
- Nút hover có quầng sáng bán kính r × 1,8, alpha 0,12, cùng màu nút.
- Vẽ một vòng nền màu nền canvas, rồi hình tròn màu nút.
- Viền:
  - nút trung tâm: dày 2,5, màu tối;
  - nút hover: dày 2, màu nút;
  - còn lại: dày 1, gần trắng.

**Nhãn nút**:

- Không bao giờ hiện ở mini hoặc trên nút bị mờ.
- Hiện khi nút được hover, là trung tâm, khi globalScale ≥ 1,2, hoặc khi degree ≥ 4.
- Cỡ 12 đậm 600 khi hover, ngược lại 11. Alpha 0,7 trừ khi hover hoặc trung tâm.
- Tiêu đề dài hơn 24 ký tự bị cắt còn 22 ký tự + "…".
- Vẽ bên phải nút.

**Vẽ cạnh**:

- Màu: tra `RELATION_COLORS` theo `predicate`, rồi `label`, rồi `type`.
- Độ dày: weight × 1,2, kẹp trong [1, 3].
- Khi hover một nút:
  - cạnh nối với nút đó dùng màu quan hệ (hoặc màu đất nung nhấn khi không tra được), dày ×1,8;
  - cạnh khác gần như trong suốt, dày 0,8.

**Tương tác**:

- Vùng nhận chuột của nút là bán kính r + 4.
- Click nút: gọi `onNodeClick(slug)` nếu có, ngược lại điều hướng `/wiki/{slug}`.

**Điều khiển góc trên phải** (không có ở mini):

- Nhóm "Quan hệ:" gồm các nút "Tất cả", "Khái niệm", "Pháp lý", "Wiki link". Nút đang chọn tô primary.
- Nhóm chế độ màu: "Scope" và "Maturity".

**Tooltip** (theo chuột, rộng tối đa 220px):

- Title.
- Chấm màu, loại trang, "{degree} links".
- Dòng phạm vi:
  - project: icon `folder_special`, tên phạm vi hoặc "Workspace";
  - department: icon `business`, tên hoặc "Department";
  - global: icon `public`, tên hoặc "Global".

**Chú giải góc dưới trái** (không có ở mini; rộng tối đa 240px, cao tối đa 50vh, cuộn):

- Chế độ status: "Maturity Lifecycle", gồm Evergreen, Mature, Developing, Seed, mỗi mục có chấm màu và số nút.
- Chế độ scope:
  - "Scope Levels": Global, Department, Workspace, kèm icon như trên và số nút.
  - Mục "Scope": liệt kê từng phạm vi cụ thể kèm số nút. Khi có hơn 8 phạm vi:
    - ô lọc "Filter scopes…" có nút xóa;
    - danh sách cuộn;
    - không khớp: "No matching scopes.".
- Luôn có "Loại quan hệ (Edges)" với 5 mục: "Là một (is-a)", "Thuộc về (part-of)", "Quy định / Áp dụng", "Sửa đổi / Bổ sung", "Wiki link". Mỗi mục có đoạn gạch màu tương ứng.

**Nút zoom góc dưới phải** (không có ở mini):

- `add`, tooltip "Zoom In": zoom × 1,2 trong 200ms.
- `remove`, tooltip "Zoom Out": zoom ÷ 1,2.
- `fit_screen`, tooltip "Fit View": zoomToFit(400ms, 60).

---

## 4. Tổng hợp API dùng trong file này

| Method | Đường dẫn | Dùng ở |
|---|---|---|
| GET | `/api/wiki/pages` | cây, tìm kiếm, autocomplete, cột phải |
| POST | `/api/wiki/pages` | tạo trang trực tiếp |
| GET | `/api/wiki/pages/{slug}[?scope_type&scope_id]` | xem trang, sheet sơ đồ, rebase |
| PUT | `/api/wiki/pages/{slug}?scope_type&scope_id` | sửa trực tiếp |
| DELETE | `/api/wiki/pages/{slug}[?scope_type&scope_id]` | xóa từ cây |
| PATCH | `/api/wiki/pages/{slug}/status?scope_type&scope_id` | đổi độ hoàn thiện |
| GET/POST | `/api/wiki/pages/{slug}/drafts` | danh sách / gửi bản nháp sửa |
| POST | `/api/wiki/drafts/create` | đề xuất trang mới |
| GET | `/api/wiki/drafts/{id}` | thăm dò kiểm tra AI |
| PATCH | `/api/wiki/drafts/{id}/content` | gửi lại bản nháp |
| POST | `/api/wiki/drafts/{id}/approve` \| `reject` \| `request-changes` \| `withdraw` | banner |
| GET | `/api/wiki/my-scopes` | trang xem |
| GET/POST | `/api/wiki/branches` | nhánh đóng góp |
| GET | `/api/wiki/branches/{id}` | rebase |
| POST | `/api/wiki/branches/{id}/rebase/{draftId}` | rebase |
| GET | `/api/wiki/graph[?slug&depth][&offset&limit]` | sơ đồ toàn cục, sơ đồ cục bộ |
| GET | `/api/projects/{id}/wiki/graph?offset&limit` | sơ đồ workspace |
| POST | `/api/wiki/images/resolve` | ảnh `image://` |
| GET | `/api/sources?status=ready&page_size=1000` | cây |
| GET | `/api/sources/{id}` | trích dẫn, xem tài liệu nguồn |

Mọi lỗi API hiển thị cho người dùng đều lấy trường `detail` của body lỗi khi có, nếu không thì dùng thông điệp dự phòng nêu ở từng mục.
