# DOCUMENT-WIKI — HỆ THỐNG QUẢN TRỊ TRI THỨC VÀ KHO TÀI LIỆU WIKI AI 🇻🇳

### Nền tảng Biên tập Tri thức Tự động, Tra cứu RAG Đa tầng & Máy chủ MCP Server

<p align="center">
  <img src="https://img.shields.io/badge/Bản_quyền-Lưu_hành_nội_bộ-blue.svg" alt="License">
  <img src="https://img.shields.io/badge/Môi_trường-Docker_Air--Gapped_Ready-success.svg" alt="Docker Ready">
  <img src="https://img.shields.io/badge/Giao_thức-Model_Context_Protocol_(MCP)-orange.svg" alt="MCP">
  <img src="https://img.shields.io/badge/Lõi_tìm_kiếm-pgvector_+_Milvus_Hybrid-blueviolet.svg" alt="Vector Store">
  <img src="https://img.shields.io/badge/Bảo_mật-RBAC_Phòng_ban-red.svg" alt="RBAC">
</p>

<p align="center">
  <img src="docs/assets/banner.png" alt="Document Wiki Banner" width="760">
</p>

**Document-Wiki** là hệ thống quản trị tri thức cấp doanh nghiệp / cơ quan (Enterprise AI Knowledge Hub), đóng vai trò lớp trung gian kết nối kho dữ liệu văn bản nghiệp vụ (quy chế, văn bản quy phạm, hướng dẫn quy chuẩn, thông tư, quyết định...) với các tác tử AI và mô hình ngôn ngữ lớn (LLMs). 

Hệ thống hoạt động như một **MCP Server** (Model Context Protocol) và **RAG Engine** thế hệ mới, biên soạn các tài liệu phi cấu trúc thành kho tri thức Wiki liên kết chặt chẽ (interlinked knowledge wiki), phục vụ trực tiếp cho **Cổng Trợ lý ảo AI - Công an tỉnh Hưng Yên (`chatbot_local`)**, Claude Desktop và các ứng dụng AI qua endpoint bảo mật phân quyền đa cấp.

---

## 🚀 1. Tại sao cần Document-Wiki?

Trong môi trường triển khai thực tế, việc đưa tài liệu vào các hệ thống AI thường gặp các rào cản:
- **Phân mảnh & Trùng lặp**: Cán bộ sao chép, tải lên tài liệu rời rạc gây loãng ngữ cảnh, xung đột nội dung giữa các phiên bản cũ và mới.
- **Rủi ro lộ lọt thông tin**: Thiếu cơ chế phân tách phạm vi bảo mật giữa các phòng ban chuyên môn.
- **Hạn chế của RAG truyền thống**: Việc chỉ cắt nhỏ tài liệu (chunking) rồi lưu vào vector database thuần túy thường làm mất liên kết logic, không thể tổng hợp bức tranh toàn cảnh của văn bản nghiệp vụ.

**Document-Wiki giải quyết triệt để vấn đề trên bằng cách:**
1. **Biến tài liệu thô thành Wiki sống**: Sử dụng quy trình biên dịch **MRP Pipeline** để tự động tổng hợp, liên kết chéo và loại bỏ trùng lặp thông tin.
2. **Kiểm soát chặt chẽ theo đơn vị (Department Scopes)**: Đảm bảo cán bộ chỉ tiếp cận đúng tri thức thuộc thẩm quyền của phòng ban mình và phạm vi dùng chung toàn cơ quan (Global Scope).
3. **Cung cấp ngữ cảnh chuẩn xác cho AI**: AI truy xuất dữ liệu từ các trang Wiki đã được thẩm định thay vì các mảnh văn bản cắt vụn thiếu ngữ cảnh.

<p align="center">
  <img src="docs/assets/how-arkon-works.png" alt="Nguyên lý hoạt động Document-Wiki" width="740">
</p>

---

## ✨ 2. Các tính năng then chốt

### 🧠 Biên dịch tri thức thông minh — Quy trình MRP Pipeline
Không dừng lại ở việc lưu trữ vector thông thường, Document-Wiki ứng dụng quy trình **MRP Pipeline** (**M**ap → **R**educe → **P**lan-review → **R**efine → **V**erify → Commit) để biên soạn tài liệu thành các trang Wiki chuyên đề:
- **Thẩm định kế hoạch trước khi ghi (Plan Review):** Mỗi lượt nạp tài liệu đều sinh kế hoạch chi tiết (danh sách trang wiki mới hoặc cập nhật). Cán bộ quản trị/biên tập có thể kiểm tra và yêu cầu điều chỉnh trước khi hệ thống ghi dữ liệu.
- **Hợp nhất nội dung thay vì ghi đè (Intelligent Merge):** Khi văn bản mới liên quan tới trang wiki đã có, LLM sẽ tổng hợp bổ sung tri thức mới mà không xóa bỏ nội dung lịch sử giá trị.
- **Truy vết minh bạch (Traceable Claims):** Mỗi trang wiki đều lưu lại đầy đủ nguồn tài liệu tham chiếu gốc (Source documents).
- **Hỗ trợ hình ảnh & OCR chuyên sâu:** Tích hợp mô tả hình ảnh (Vision captions) và công cụ OCR văn bản (GLM-OCR) để nhận diện chính xác bảng biểu, con dấu và trang scan.
- **Khả năng phục hồi (Resumable):** Bản nháp và tiến trình được lưu liên tục; nếu tiến trình bị gián đoạn, hệ thống tự phục hồi mà không cần xử lý lại các bước LLM tốn kém.

### 📚 Trình duyệt Wiki & Đồ thị tri thức (Knowledge Graph)
- **Giao diện 3 cột chuyên nghiệp:** Cây phân cấp trang (Page Tree), Khung hiển thị/biên tập Markdown và Cột liên kết ngược/xuôi (Backlinks & Outlinks).
- **Tìm kiếm kết hợp (Hybrid Search):** Tìm kiếm toàn văn (Full-Text Search BM25) kết hợp tìm kiếm ngữ nghĩa vector đa tầng qua PostgreSQL (pgvector) và Milvus.
- **Đồ thị tri thức tương tác 2D:** Trực quan hóa mối liên hệ đa chiều giữa các khái niệm và trang tài liệu nghiệp vụ.
- **Quy trình đề xuất chỉnh sửa:** Đề xuất bản nháp (Draft) → Thẩm định (Review) → Phê duyệt (Approve) → Xuất bản.
- **Lịch sử phiên bản & Khôi phục (Rollback):** Lưu trữ toàn bộ lịch sử chỉnh sửa từng trang và hỗ trợ hoàn tác chỉ với một thao tác.

<p align="center">
  <img src="docs/assets/arkon-wiki-ui.png" alt="Giao diện Document-Wiki" width="740">
</p>

### 🏢 Phân vùng phòng ban & Toàn cục (Department & Global Scopes)
- **Cô lập tri thức theo phòng ban:** Thiết lập các không gian riêng biệt cho từng đơn vị (ví dụ: PA08, PC06, PV01...).
- **Không gian toàn cục (Global Scope):** Lưu trữ các văn bản quy phạm pháp luật, chỉ thị, quy chuẩn và nội quy dùng chung cho toàn thể cán bộ, chiến sĩ.
- **Ràng buộc cứng tại mọi tầng:** Kiểm soát phạm vi nghiêm ngặt tại tầng API, MCP Server và công cụ tìm kiếm.

### 🛂 Phân quyền RBAC & Nhật ký kiểm vết (Audit Trail)
- **Phân vai trò chi tiết:** `Viewer` (Xem) · `Contributor` (Đóng góp) · `Editor` (Biên tập) · `Admin` (Quản trị).
- **Phân quyền chi tiết (Granular Permissions):** Cấu hình quyền hạn theo từng hành vi (`doc:read:own_dept`, `wiki:edit:all`, `org:settings:manage`...).
- **Nhật ký kiểm vết bất biến (Audit Log):** Ghi lại toàn bộ hành động đặc quyền như phê duyệt kế hoạch, đổi vai trò, cấu hình hệ thống.

### 🔌 Cổng MCP Server cho Trợ lý ảo & AI Clients
Document-Wiki hoạt động như một **MCP Server** chuẩn hóa, cho phép Chatbot CAHY (`chatbot_local`), Claude Desktop hoặc các Agent AI giao tiếp trực tiếp qua OAuth 2.1 + PKCE hoặc API Token:
- **Nhóm công cụ Wiki:** `search_wiki`, `read_wiki_page`, `list_wiki_pages`, `read_wiki_index`.
- **Nhóm công cụ Nguồn trích dẫn:** `get_source`, `get_source_outline`, `get_source_pages`, `list_sources`.
- **Nhóm công cụ Biên tập:** `propose_wiki_edit`, `edit_wiki_page`, `list_pending_drafts`, `review_draft`, `approve_draft`, `reject_draft`.
- **Nhóm công cụ Phân loại:** `list_knowledge_types`, `get_knowledge_type_docs`.

### 🧰 Quản lý Kỹ năng AI (AI Skills Distribution)
- Đóng gói và phân phối các gói kỹ năng chuyên môn (Agent Skills gói trong file `.zip` kèm file `SKILL.md`).
- Phân bổ quyền truy cập kỹ năng theo từng phòng ban nghiệp vụ.

### 🤖 Đa dạng nguồn suy luận AI (Pluggable AI Providers)
- **Hạ tầng AI nội bộ On-premise:** Hỗ trợ kết nối máy chủ vLLM cụm GPU nội bộ (Qwen3.8-27B, Qwen3-VL, DeepSeek).
- **Mô hình thương mại (khi có kết nối):** Hỗ trợ Google Gemini, Anthropic Claude, OpenAI.
- **Lõi Vector & Embedding:** Tích hợp Milvus Vector Database & pgvector, hỗ trợ chuyển đổi mô hình nhúng trực tuyến (Online re-embed migration) không gián đoạn tìm kiếm.
- **Nhận diện văn bản OCR:** Kết nối dịch vụ OCR chuyên dụng (GLM-OCR) xử lý hồ sơ tài liệu scan.

### 🔒 An toàn thông tin & Triển khai Air-Gapped
- **Triển khai On-premise 100%:** Toàn bộ dữ liệu nằm trên hạ tầng máy chủ nội bộ.
- **Không gửi Telemetry:** Tuyệt đối không gửi dữ liệu ra ngoài Internet.
- **Mã hóa an toàn:** Khóa bí mật và API keys được mã hóa bằng thuật toán Fernet trong PostgreSQL.

---

## 🛠️ 3. Kiến trúc kỹ thuật & Cụm dịch vụ Docker

<p align="center">
  <img src="docs/assets/arkon-architecture.png" alt="Kiến trúc hệ thống Document-Wiki" width="740">
</p>

Hệ thống Document-Wiki được đóng gói và điều phối thông qua Docker Compose với các dịch vụ chuyên biệt:

| Dịch vụ Container | Vai trò & Công nghệ | Cổng nội bộ / Host |
| :--- | :--- | :---: |
| **`arkon_frontend`** | Giao diện Cổng tri thức (Next.js 16, React 19, Tailwind CSS) | `3119:3000` |
| **`arkon_api`** | Lõi xử lý Backend REST API & FastMCP Server (FastAPI) | `5055:5055` |
| **`arkon_worker`** | Worker xử lý luồng MRP Pipeline biên tập tài liệu (Python ARQ) | Nội bộ |
| **`arkon_worker_skills`** | Worker phụ trách nạp và thực thi kỹ năng AI (Python ARQ) | Nội bộ |
| **`arkon_migrator`** | Tự động nâng cấp cấu trúc cơ sở dữ liệu (Alembic) | Nội bộ |
| **`arkon_postgres`** | CSDL chính & Vector Store (PostgreSQL 16 + pgvector) | `5432` |
| **`arkon_redis`** | Quản lý hàng đợi tác vụ nền & cache phiên (Redis 7 Alpine) | `6379` |
| **`arkon_minio`** | Lưu trữ tệp tin tài liệu gốc, ảnh, đính kèm (MinIO S3) | API: `9002` \| Console: `9003` |
| **`arkon_milvus`** | Cơ sở dữ liệu Vector quy mô lớn phục vụ tìm kiếm Hybrid (Milvus 2.4) | `19530` / `9091` |
| **`arkon_etcd`** | Lưu trữ metadata cho cụm Milvus Standalone (etcd v3.5) | Nội bộ |
| **`arkon_milvus_ui`** | Giao diện đồ họa giám sát Vector Milvus (Attu UI) | `9004:3000` |

---

## 💻 4. Yêu cầu tài nguyên máy chủ (Hardware Requirements)

| Quy mô triển khai | Cấu hình Thử nghiệm / Đội | Cấu hình Tiêu chuẩn (Phòng ban) | Cấu hình Mở rộng (Toàn cơ quan) |
| :--- | :---: | :---: | :---: |
| **Số lượng cán bộ** | 1 – 20 người | 20 – 100 người | 100+ người |
| **CPU** | 4 Cores | 8 Cores | 16+ Cores |
| **Bộ nhớ RAM** | 8 GB | 16 GB | 32+ GB |
| **Ổ cứng lưu trữ** | 60 GB SSD | 150 GB NVMe SSD | 300+ GB NVMe SSD |
| **Hệ điều hành** | Ubuntu 22.04+ / Debian 12+ | Ubuntu 22.04+ / Debian 12+ | Ubuntu 22.04+ / RHEL 9+ |

> [!NOTE]
> - **Bộ nhớ RAM** là yếu tố quan trọng nhất: Các worker của quy trình MRP cần tải ngữ cảnh tài liệu lớn để LLM xử lý biên soạn.
> - **Ổ cứng SSD/NVMe**: Đảm bảo tốc độ đọc/ghi cao cho chỉ mục pgvector, Milvus collections và kho tệp MinIO.
> - **GPU**: Có thể sử dụng API từ máy chủ vLLM riêng biệt hoặc dùng chung máy chủ nếu đã có cụm GPU.

---

## 🚦 5. Hướng dẫn khởi chạy nhanh (Docker Compose)

### Bước 1: Chuẩn bị mã nguồn và môi trường
Di chuyển vào thư mục dự án `document-wiki`:
```bash
cd document-wiki
```

### Bước 2: Thiết lập file cấu hình môi trường
Sao chép hoặc chỉnh sửa file `.env.docker`:
```bash
cp .env.docker.example .env.docker
```

Các biến môi trường cơ bản cần lưu ý trong `.env.docker`:
```env
# CSDL PostgreSQL & pgvector
POSTGRES_USER=arkon
POSTGRES_PASSWORD=arkon_secret
POSTGRES_DB=arkon
DATABASE_URL=postgresql+asyncpg://arkon:arkon_secret@arkon_postgres:5432/arkon

# Khóa bí mật và Pepper bảo mật token MCP
SECRET_KEY=dev-cahy-secret-key-123456
MCP_TOKEN_PEPPER=dev-cahy-pepper-123456

# Tài khoản Quản trị viên khởi tạo ban đầu
DEFAULT_ADMIN_EMAIL=admin@cahy.gov.vn
DEFAULT_ADMIN_PASSWORD=Admincahy@123456

# Dịch vụ lưu trữ MinIO
MINIO_PUBLIC_ENDPOINT=localhost:9002
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin123
MINIO_BUCKET=arkon-files

# Cấu hình Frontend
NEXT_PUBLIC_API_URL=http://localhost:5055

# Cấu hình Vector Database Milvus
MILVUS_HOST=milvus
MILVUS_PORT=19530
MILVUS_ENABLED=true

# Cấu hình dịch vụ OCR (nếu sử dụng máy chủ nhận dạng văn bản)
OCR_BASE_URL=https://unsloth.anm05.com/v1
OCR_API_KEY=sk-unsloth-9e5266991a4ce09c55ecd93232483e46
OCR_MODEL=ggml-org/GLM-OCR-GGUF:f16
```

### Bước 3: Khởi dựng và chạy cụm container
```bash
docker compose --env-file .env.docker up -d --build
```

Kiểm tra trạng thái toàn bộ các container:
```bash
docker compose ps
```

### Bước 4: Truy cập các cổng dịch vụ
Sau khi các container ở trạng thái `healthy`, bạn có thể truy cập:
* 🌐 **Cổng quản trị tri thức Document-Wiki**: [http://localhost:3119](http://localhost:3119)
* ⚙️ **Backend REST API Swagger Docs**: [http://localhost:5055/docs](http://localhost:5055/docs)
* 🔌 **Điểm cuối máy chủ MCP**: `http://localhost:5055/mcp`
* 🗄️ **Bảng điều khiển MinIO Console**: [http://localhost:9003](http://localhost:9003) (User: `minioadmin` / Pass: `minioadmin123`)
* 📊 **Giao diện quản lý Vector Milvus (Attu)**: [http://localhost:9004](http://localhost:9004)

Đăng nhập vào Portal Document-Wiki bằng tài khoản quản trị viên:
- **Email:** `admin@cahy.gov.vn`
- **Mật khẩu:** `Admincahy@123456`

Truy cập mục **Cài đặt (Settings)** trên giao diện để cấu hình mô hình LLM, Embedding Model và kiểm tra kết nối.

---

## 🔗 6. Hướng dẫn tích hợp kết nối

### A. Tích hợp trực tiếp với Cổng Trợ lý ảo AI CAHY (`chatbot_local`)
Trong file cấu hình `docker-compose.yaml` của hệ thống `chatbot_local`, thiết lập liên kết mạng nội bộ `cahy-internal` và khai báo:

```yaml
# Kết nối REST API sang Document-Wiki
ARKON_API_URL: http://arkon_api:5055/api
ARKON_UI_URL: http://localhost:3119

# Đăng ký Document-Wiki thành công cụ MCP của Chatbot
TOOL_SERVER_CONNECTIONS: >-
  [{"url":"http://arkon_api:5055/mcp/","path":"","type":"mcp","auth_type":"bearer","key":"${ARKON_MCP_TOKEN}","config":{"enable":true,"function_name_filter_list":"search_wiki,read_wiki_page,read_wiki_index,get_source,get_source_outline,get_source_pages"},"info":{"id":"document_wiki","name":"Document Wiki Hub"}}]
```

Khi đó, cán bộ hội thoại trên giao diện Chatbot có thể kích hoạt các công cụ tra cứu tri thức Wiki tự động theo thời gian thực.

### B. Tích hợp với Claude Desktop hoặc các ứng dụng MCP Client
Trong ứng dụng **Claude Desktop** (mục `claude_desktop_config.json` hoặc giao diện Kết nối Connector):
- **Tên kết nối:** `Document Wiki`
- **URL MCP Server:** `http://localhost:5055/mcp` (hoặc domain triển khai nội bộ)

Đăng nhập xác thực thông qua trình duyệt (OAuth 2.1 PKCE) hoặc cung cấp Bearer Token được cấp từ trang Hồ sơ cá nhân của Document-Wiki.

**Chỉ dẫn hệ thống khuyến nghị cho AI Client:**
```
Khi trả lời các câu hỏi liên quan đến quy trình nghiệp vụ, văn bản quy phạm, thông tư, 
quy chế và thông tin tổ chức, luôn ưu tiên tra cứu trên Document-Wiki bằng công cụ 
search_wiki trước khi suy luận tổng quát.
```

---

## 📖 7. Danh mục tài liệu kỹ thuật chi tiết

Các tài liệu kỹ thuật chuyên sâu được lưu trữ tại thư mục [docs/](file:///d:/code/dsqt/conganhungyen/chatbot_cahy/document-wiki/docs/):

- **[Tài liệu Backend REST API (API.md)](docs/API.md)** — Chi tiết toàn bộ các endpoint: Quản lý phòng ban, tài liệu, trang wiki, xác thực và phân loại dữ liệu.
- **[Hướng dẫn cài đặt & phát triển cục bộ (SETUP.md)](docs/SETUP.md)** — Cấu hình môi trường dev, hot-reload frontend/backend và các tham số môi trường chi tiết.
- **[Hướng dẫn khởi chạy Development (HOW_TO_RUN.md)](docs/HOW_TO_RUN.md)** — Hướng dẫn từng bước chạy backend uvicorn, worker arq và frontend Next.js.
- **[Quy chuẩn kết nối MCP & AI Client (MCP.md)](docs/MCP.md)** — Đặc tả kỹ thuật các công cụ FastMCP, xác thực OAuth 2.1 và cơ chế cấp quyền theo token.
- **[Kiến trúc hệ thống & Quy trình MRP (ARCHITECTURE.md)](docs/ARCHITECTURE.md)** — Sơ đồ luồng biên dịch tài liệu, thuật toán gom nhóm và kiểm định kế hoạch wiki.
- **[Mô hình kiểm soát truy cập & Phân quyền (ACCESS-CONTROL.md)](docs/ACCESS-CONTROL.md)** — Phân tách phạm vi dữ liệu phòng ban, toàn cục và danh sách quyền chi tiết.
- **[Hướng dẫn nghiệp vụ Wiki (WIKI.md)](docs/WIKI.md)** — Cẩm nang sử dụng giao diện, cách tổ chức thư mục tài liệu và tối ưu cấu trúc bài viết.

---

## 🗺️ 8. Lộ trình tính năng (Roadmap)

- [x] **Quy trình MRP Pipeline**: Biên soạn tài liệu tự động, thẩm định kế hoạch, hợp nhất trang và phục hồi lỗi.
- [x] **Cổng FastMCP Server**: Cung cấp bộ công cụ chuẩn hóa cho AI Agent.
- [x] **Phân vùng phòng ban & Toàn cục**: Cách ly dữ liệu theo RBAC.
- [x] **Đồ thị tri thức & Trình duyệt Wiki**: Đồ thị liên kết tương tác 2D và quản lý bản nháp.
- [x] **Quản lý AI Skills**: Đóng gói và điều phối kỹ năng tác tử.
- [x] **Tìm kiếm Hybrid pgvector + Milvus**: Kết hợp tìm kiếm từ khóa và tìm kiếm ngữ nghĩa.
- [x] **Tích hợp OCR nhận diện văn bản scan**: Hỗ trợ GLM-OCR trích xuất dữ liệu ảnh/PDF.
- [x] **Nhật ký kiểm vết (Audit Trail)**: Giám sát toàn bộ thao tác cấu hình hệ thống.
- [ ] **Bổ sung đầu đọc tài liệu nâng cao**: Mở rộng trình trích xuất tự động cho bảng tính Excel phức tạp, file nén và tài liệu audio/video.
- [ ] **Bộ kết nối dữ liệu tự động (Connectors)**: Tự động đồng bộ tài liệu từ các kho lưu trữ dùng chung nội bộ.
- [ ] **Hệ thống cảnh báo & Thông báo**: Thông báo qua Email/Webhook khi có bản nháp hoặc kế hoạch cần phê duyệt.

---

## 🔒 9. Bản quyền & An toàn thông tin

Tài liệu và mã nguồn hệ thống Document-Wiki được xây dựng, tinh chỉnh và tối ưu hóa phục vụ công tác nội bộ trong hệ sinh thái Trợ lý ảo AI.

Nghiêm cấm sao chép, phân phối hoặc cung cấp dịch vụ ra bên ngoài khi chưa có sự đồng ý của đơn vị quản lý.

---

## 📬 10. Bộ phận Quản trị & Vận hành

**Hệ thống Trợ lý ảo AI — Phân hệ Quản trị Tri thức (Document-Wiki)**  
*Đơn vị quản trị:* Bộ phận Kỹ thuật & Quản trị Hệ thống AI — Công an tỉnh Hưng Yên  
*Tài khoản quản trị mặc định:* `admin@cahy.gov.vn`  
*Địa chỉ máy chủ nội bộ:* Mạng máy tính nghiệp vụ nội bộ Công an tỉnh Hưng Yên
