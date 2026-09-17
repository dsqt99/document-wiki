# Document Wiki — ENTERPRISE AI KNOWLEDGE HUB & MCP SERVER 🌐

### Nền tảng Quản trị Tri thức Tự động, Biên tập Wiki Thông minh & Máy chủ MCP Chuẩn hóa

<p align="center">
  <img src="docs/assets/logo.png" alt="Document Wiki Logo" width="88" style="border-radius: 18px;">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Bản_quyền-Enterprise_Internal_Use-blue.svg" alt="License">
  <img src="https://img.shields.io/badge/Triển_khai-Docker_Self--Hosted-success.svg" alt="Docker Ready">
  <img src="https://img.shields.io/badge/Giao_thức-Model_Context_Protocol_(MCP)-orange.svg" alt="MCP">
  <img src="https://img.shields.io/badge/Lõi_tìm_kiếm-pgvector_+_Milvus_Hybrid-blueviolet.svg" alt="Vector Store">
  <img src="https://img.shields.io/badge/Phân_quyền-Multi--Scope_RBAC-darkblue.svg" alt="RBAC">
</p>

<p align="center">
  <img src="docs/assets/banner.png" alt="Document Wiki: Enterprise AI Knowledge Hub" width="760">
</p>

**Document Wiki** là hệ sinh thái quản trị tri thức doanh nghiệp tự lưu trữ (Self-hosted Enterprise Knowledge Hub), đóng vai trò lớp hạ tầng dữ liệu thông minh kết nối giữa kho tài liệu nội bộ (SOPs, quy trình nghiệp vụ, thông tư, chính sách, tài liệu kỹ thuật...) với các mô hình ngôn ngữ lớn (LLMs) và các ứng dụng AI đầu cuối.

Hệ thống vận hành như một **Máy chủ MCP tập trung** (Model Context Protocol) và **RAG Engine** thế hệ mới. Thay vì chỉ cắt nhỏ văn bản (chunking) rồi lưu trữ vector phân tán, Document Wiki tổng hợp và biên soạn toàn bộ tài liệu thành một **Mạng lưới Wiki tri thức liên kết (Interlinked Knowledge Wiki)** có cấu trúc, có thể truy vết nguồn gốc và phục vụ cho bất kỳ AI Client nào (Claude Desktop, AI Chatbot WebUI, AI Agents) thông qua một điểm cuối bảo mật, phân quyền nghiêm ngặt.

---

## 🚀 1. Vì sao nên sử dụng Document Wiki?

Trong hầu hết các tổ chức và doanh nghiệp, việc ứng dụng AI thường gặp phải các hạn chế lớn:
- **Ngữ cảnh phân mảnh & Trùng lặp:** Nhân sự sao chép - dán thủ công tài liệu vào chatbot dẫn tới ngữ cảnh không đồng nhất, xung đột giữa tài liệu cũ và tài liệu mới.
- **Rủi ro lộ lọt dữ liệu:** Thiếu ranh giới phân quyền bảo mật giữa các phòng ban chuyên môn (Kỹ thuật, Pháp chế, Nhân sự, Vận hành...).
- **Rào cản của RAG truyền thống:** Vector database thông thường chỉ trả về các mảnh văn bản vụn vặt (raw chunks), không phản ánh được tổng quan cấu trúc logic và tính liên kết của tài liệu nghiệp vụ.

**Document Wiki biến tri thức tổ chức thành tài nguyên AI được quản trị tập trung:**
1. **Biến tài liệu tĩnh thành Wiki sống:** Sử dụng quy trình **MRP Pipeline** để tự động biên dịch, hợp nhất thông tin và tạo liên kết chéo giữa các bài viết.
2. **Cách ly phạm vi theo phòng ban (Department Scopes):** Mỗi đơn vị có không gian tri thức riêng biệt, bên cạnh không gian chung toàn tổ chức (Global Scope).
3. **Cung cấp ngữ cảnh toàn vẹn cho AI:** Các mô hình AI truy vấn trực tiếp vào các trang wiki đã được thẩm định, nâng cao độ chính xác và giảm thiểu hiện tượng ảo giác (hallucination).

<p align="center">
  <img src="docs/assets/how-Document Wiki-works.png" alt="Nguyên lý hoạt động Document Wiki - Quy trình MRP Pipeline" width="760">
</p>

---

## ✨ 2. Tính năng cốt lõi

### 🧠 Quy trình biên dịch tri thức thông minh (MRP Pipeline)
Khác biệt hoàn toàn với các giải pháp RAG chỉ chia nhỏ tài liệu đơn thuần, quy trình **MRP Pipeline** (**M**ap → **R**educe → **P**lan-review → **R**efine → **V**erify → Commit) của Document Wiki biên soạn tài liệu thành một hệ thống wiki hoàn chỉnh:
- **Thẩm định kế hoạch trước khi lưu (Plan Review):** Khi nạp tài liệu, hệ thống tự động sinh kế hoạch biên tập (liệt kê các trang wiki mới sẽ tạo hoặc các trang cũ cần bổ sung). Biên tập viên có thể duyệt, sửa đổi hoặc từ chối kế hoạch trước khi hệ thống ghi dữ liệu.
- **Hợp nhất trang thông minh (Page Merge):** Khi văn bản mới liên quan tới trang wiki đã có, LLM sẽ tự động tổng hợp bổ sung tri thức mới mà không xóa bỏ hoặc ghi đè mất mát thông tin lịch sử.
- **Truy vết minh bạch (Traceable Claims):** Mỗi trang wiki đều gắn liền với danh sách tài liệu tham chiếu nguồn gốc (Source Drill-down).
- **Hỗ trợ OCR & Xử lý hình ảnh:** Tích hợp mô tả thị giác (Vision Captions) và dịch vụ OCR chuyên dụng (GLM-OCR) để nhận diện bảng biểu, lưu đồ và tài liệu scan.
- **Khả năng phục hồi tiến trình (Resumable Pipeline):** Bản nháp và trạng thái được lưu liên tục; nếu tiến trình bị gián đoạn, hệ thống tự động tiếp tục từ bước dừng lại mà không tốn chi phí gọi LLM từ đầu.

### 📚 Trình duyệt Wiki & Đồ thị tri thức (Knowledge Graph)
- **Bố cục 3 cột trực quan:** Cây phân cấp trang (Page Tree), Khung đọc & biên soạn Markdown, và Cột liên kết ngược/xuôi (Backlinks & Outlinks).
- **Tìm kiếm Hybrid đa tầng:** Kết hợp tìm kiếm toàn văn chính xác (Full-Text Search BM25) với tìm kiếm ngữ nghĩa vector đa chiều (PostgreSQL pgvector + Milvus).
- **Đồ thị tri thức tương tác 2D:** Trực quan hóa các mối liên kết chéo giữa các khái niệm và trang wiki trong từng phòng ban hoặc toàn hệ thống.
- **Quy trình phê duyệt bài viết:** Đề xuất bản nháp (Draft Proposal) → Ban biên tập thẩm định (Review) → Phê duyệt (Approve) → Xuất bản chính thức.
- **Lịch sử phiên bản & Rollback:** Theo dõi chi tiết mọi thay đổi theo thời gian và hỗ trợ khôi phục phiên bản trước đó chỉ với một click.

<p align="center">
  <img src="docs/assets/Document Wiki-ui.png" alt="Giao diện Trình duyệt Document Wiki & Đồ thị Tri thức" width="760">
</p>

### 🏢 Phân tách phạm vi Phòng ban & Toàn cục (Department & Global Scopes)
- **Cô lập tri thức phòng ban:** Thiết lập ranh giới dữ liệu cho từng phòng ban chuyên môn (Kỹ thuật, Pháp chế, Nhân sự, Kinh doanh, Vận hành...).
- **Không gian toàn cục (Global Scope):** Lưu trữ các tài liệu chính sách chung, quy chuẩn và hướng dẫn áp dụng cho toàn thể thành viên.
- **Thực thi phân quyền đa tầng:** Ràng buộc quyền truy cập chặt chẽ ở cả tầng API, tầng giao thức MCP và công cụ tìm kiếm.

### 🛂 Kiểm soát truy cập RBAC & Nhật ký kiểm vết (Audit Log)
- **Các vai trò định sẵn:** `Viewer` (Chỉ xem) · `Contributor` (Đóng góp tài liệu) · `Editor` (Biên tập, duyệt kế hoạch) · `Admin` (Quản trị hệ thống).
- **Phân quyền chi tiết (Granular Permissions):** Cấu hình quyền hạn theo từng hành vi cụ thể (`doc:read:own_dept`, `wiki:edit:all`, `org:settings:manage`...).
- **Nhật ký kiểm vết bất biến (Audit Trail):** Ghi nhận chi tiết toàn bộ các thao tác nhạy cảm (duyệt kế hoạch, sửa vai trò, thay đổi cấu hình bảo mật).

### 🔌 Cổng MCP Server cho Claude Desktop & AI Clients
Document Wiki cung cấp giao thức **Model Context Protocol (MCP)** chuẩn hóa, cho phép các AI Clients (Claude Desktop, Claude.ai, Chatbot WebUI, AI Agents) kết nối nhanh chóng thông qua **OAuth 2.1 + PKCE** hoặc **Bearer Token**:
- **Nhóm công cụ tra cứu Wiki:** `search_wiki`, `read_wiki_page`, `list_wiki_pages`, `read_wiki_index`.
- **Nhóm công cụ tài liệu nguồn:** `get_source`, `get_source_outline`, `get_source_pages`, `list_sources`.
- **Nhóm công cụ quy trình biên tập:** `propose_wiki_edit`, `edit_wiki_page`, `list_pending_drafts`, `review_draft`, `approve_draft`, `reject_draft`.
- **Nhóm công cụ danh mục:** `list_knowledge_types`, `get_knowledge_type_docs`.

### 🧰 Quản lý & Phân phối AI Skills
- Đóng gói các bộ kỹ năng tác tử (Agent Skills) dưới dạng gói `.zip` chứa file chỉ dẫn `SKILL.md`.
- Phân phối linh hoạt theo từng phòng ban nghiệp vụ với quy trình đóng góp và cập nhật từ người dùng.

### 🤖 Hỗ trợ đa dạng nhà cung cấp AI (Pluggable AI Providers)
- **Hạ tầng AI cục bộ On-premise:** Tích hợp trực tiếp máy chủ vLLM, Ollama (Qwen, DeepSeek, LLaMA...).
- **Mô hình thương mại:** Hỗ trợ linh hoạt Anthropic Claude, OpenAI, Google Gemini.
- **Hạ tầng Vector & Embedding:** Tương thích pgvector và Milvus Vector Database, hỗ trợ cơ chế chuyển đổi mô hình nhúng trực tuyến (Online re-embed migration) không gián đoạn dịch vụ tìm kiếm.

### 🔒 Bảo mật & Quyền riêng tư tuyệt đối
- **100% Self-hosted:** Triển khai độc lập trên máy chủ riêng hoặc mạng nội bộ (hỗ trợ môi trường Air-Gapped cách ly).
- **Không gửi Telemetry:** Dữ liệu chỉ gửi tới mô hình AI do bạn chỉ định.
- **Mã hóa an toàn:** Toàn bộ API keys và mã bí mật được mã hóa với Fernet trong PostgreSQL.

---

## 🛠️ 3. Kiến trúc hệ thống & Cụm dịch vụ Docker

<p align="center">
  <img src="docs/assets/Document Wiki-architecture.png" alt="Kiến trúc hệ thống Document Wiki" width="760">
</p>

Hệ thống Document Wiki vận hành đồng bộ thông qua cụm 11 dịch vụ container Docker:

| Dịch vụ Container | Vai trò & Công nghệ | Cổng Host / Mạng nội bộ |
| :--- | :--- | :---: |
| **`arkon_frontend`** | Giao diện Portal người dùng (Next.js 16, React 19, Tailwind CSS) | `3119:3000` |
| **`arkon_api`** | Lõi xử lý Backend REST API & FastMCP Server (FastAPI) | `5055:5055` |
| **`arkon_worker`** | Worker xử lý luồng MRP Pipeline biên tập tài liệu (Python ARQ) | Nội bộ |
| **`arkon_worker_skills`** | Worker quản lý và thực thi AI Skills (Python ARQ) | Nội bộ |
| **`arkon_migrator`** | Tự động cập nhật lược đồ CSDL khi nâng cấp (Alembic) | Nội bộ |
| **`arkon_postgres`** | Cơ sở dữ liệu quan hệ & Vector Store (PostgreSQL 16 + pgvector) | `5432` |
| **`arkon_redis`** | Quản lý hàng đợi tác vụ nền và bộ nhớ đệm (Redis 7) | `6379` |
| **`arkon_minio`** | Lưu trữ tệp tin tài liệu gốc, hình ảnh, tài sản đính kèm (MinIO S3) | API: `9002` \| Console: `9003` |
| **`arkon_milvus`** | Cơ sở dữ liệu Vector chuyên dụng cho tìm kiếm quy mô lớn (Milvus 2.4) | `19530` / `9091` |
| **`arkon_etcd`** | Lưu trữ metadata cho cụm Milvus Standalone (etcd v3.5) | Nội bộ |
| **`arkon_milvus_ui`** | Bảng điều khiển trực quan quản lý Milvus Vector (Attu UI) | `9004:3000` |

---

## 💻 4. Yêu cầu tài nguyên máy chủ (Hardware Requirements)

| Quy mô sử dụng | Môi trường Thử nghiệm / Đội nhỏ | Môi trường Phòng ban / Doanh nghiệp | Môi trường Mở rộng (Enterprise) |
| :--- | :---: | :---: | :---: |
| **Số lượng người dùng** | 1 – 20 người | 20 – 100 người | 100+ người |
| **CPU** | 4 Cores | 8 Cores | 16+ Cores |
| **RAM** | 8 GB | 16 GB | 32+ GB |
| **Lưu trữ** | 60 GB SSD | 150 GB NVMe SSD | 300+ GB NVMe SSD |
| **Hệ điều hành** | Ubuntu 22.04+ / Debian 12+ | Ubuntu 22.04+ / Debian 12+ | Ubuntu 22.04+ / RHEL 9+ |

> [!NOTE]
> - **Bộ nhớ RAM** là ưu tiên hàng đầu: Các worker của quy trình MRP cần bộ nhớ để nạp ngữ cảnh văn bản lớn trong quá trình xử lý LLM.
> - **Lưu trữ SSD/NVMe**: Đảm bảo hiệu năng truy vấn nhanh cho các chỉ mục vector (pgvector, Milvus) và kho lưu trữ MinIO.
> - **GPU**: Không bắt buộc trên máy chủ Document Wiki nếu sử dụng API suy luận từ máy chủ vLLM riêng biệt hoặc nhà cung cấp đám mây.

---

## 🚦 5. Hướng dẫn khởi chạy nhanh (Docker Compose)

### Bước 1: Chuẩn bị mã nguồn
```bash
git clone <repository-url> Document Wiki
cd Document Wiki
```

### Bước 2: Thiết lập biến môi trường
Tạo file cấu hình `.env.docker` từ mẫu:
```bash
cp .env.docker.example .env.docker
```

Các tham số cấu hình cốt lõi trong `.env.docker`:
```env
# Cơ sở dữ liệu PostgreSQL & pgvector
POSTGRES_USER=arkon
POSTGRES_PASSWORD=arkon_secret
POSTGRES_DB=arkon
DATABASE_URL=postgresql+asyncpg://arkon:arkon_secret@postgres:5432/arkon

# Khóa bí mật & Chuỗi băm bảo vệ mã token MCP
SECRET_KEY=change-me-to-a-secure-random-secret
MCP_TOKEN_PEPPER=change-me-to-a-secure-random-pepper

# Tài khoản Quản trị viên ban đầu
DEFAULT_ADMIN_EMAIL=admin@Document Wiki.local
DEFAULT_ADMIN_PASSWORD=admin123

# Kho lưu trữ tệp MinIO
MINIO_PUBLIC_ENDPOINT=localhost:9002
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin123
MINIO_BUCKET=arkon-files

# Địa chỉ API Frontend
NEXT_PUBLIC_API_URL=http://localhost:5055

# Cấu hình Vector Database Milvus
MILVUS_HOST=milvus
MILVUS_PORT=19530
MILVUS_ENABLED=true
```

### Bước 3: Khởi dựng và chạy toàn bộ dịch vụ
```bash
docker compose --env-file .env.docker up -d --build
```

Kiểm tra trạng thái sẵn sàng của các container:
```bash
docker compose ps
```

### Bước 4: Truy cập hệ thống
Khi các container ở trạng thái `healthy`, bạn có thể truy cập:
* 🌐 **Cổng thông tin Document Wiki Portal:** [http://localhost:3119](http://localhost:3119)
* ⚙️ **Tài liệu Swagger REST API:** [http://localhost:5055/docs](http://localhost:5055/docs)
* 🔌 **Điểm cuối máy chủ FastMCP:** `http://localhost:5055/mcp`
* 🗄️ **Bảng điều khiển MinIO Console:** [http://localhost:9003](http://localhost:9003)
* 📊 **Giao diện quản lý Vector Milvus (Attu):** [http://localhost:9004](http://localhost:9004)

Đăng nhập vào Portal bằng tài khoản quản trị mặc định và truy cập mục **Settings** để cấu hình các mô hình LLM, Embedding Model và kiểm tra kết nối.

---

## 🔗 6. Hướng dẫn tích hợp kết nối AI

### A. Tích hợp với Claude Desktop hoặc các ứng dụng MCP Client
Trong ứng dụng **Claude Desktop** (cấu hình trong `claude_desktop_config.json` hoặc giao diện Connectors):
- **Tên kết nối:** `Document Wiki`
- **URL máy chủ MCP:** `http://localhost:5055/mcp`

Tiến hành kết nối qua trình duyệt với cơ chế OAuth 2.1 hoặc nhập Bearer Token được cấp từ trang Hồ sơ cá nhân (Profile) của Document Wiki.

**Gợi ý Custom Instructions cho AI Client:**
```
Mỗi khi trả lời các câu hỏi liên quan đến chính sách, quy trình làm việc, tài liệu kỹ thuật, 
hướng dẫn nội bộ và thông tin tổ chức, hãy luôn tìm kiếm trên Document Wiki thông qua công cụ 
search_wiki trước khi dựa vào kiến thức tổng quát.
```

### B. Tích hợp với AI Chatbot WebUI & Tác tử độc lập
Hệ thống hỗ trợ tích hợp với bất kỳ nền tảng Chatbot nào thông qua:
1. **Giao thức MCP:** Khai báo URL endpoint `http://<server-ip>:5055/mcp/` kèm token bảo mật.
2. **REST API Chuẩn:** Tích hợp trực tiếp qua các endpoint `/api/wiki`, `/api/sources`, `/api/departments` theo tài liệu kỹ thuật [API.md](docs/API.md).

---

## 📖 7. Danh mục tài liệu kỹ thuật chi tiết

- **[Tài liệu Backend REST API (API.md)](docs/API.md)** — Đặc tả chi tiết các endpoint quản lý phòng ban, tài liệu, trang wiki, xác thực và tìm kiếm.
- **[Hướng dẫn cài đặt & Cấu hình (SETUP.md)](docs/SETUP.md)** — Cấu hình môi trường phát triển cục bộ và triển khai sản xuất với Docker.
- **[Hướng dẫn khởi chạy Development (HOW_TO_RUN.md)](docs/HOW_TO_RUN.md)** — Các bước chạy chi tiết từng dịch vụ (Backend FastAPI, Workers, Frontend Next.js).
- **[Quy chuẩn kết nối MCP & AI Client (MCP.md)](docs/MCP.md)** — Danh mục công cụ FastMCP, xác thực OAuth 2.1 và cơ chế cấp quyền theo token.
- **[Kiến trúc hệ thống & Quy trình MRP (ARCHITECTURE.md)](docs/ARCHITECTURE.md)** — Thiết kế chi tiết công cụ biên tập tài liệu và kiến trúc RAG.
- **[Mô hình phân quyền RBAC & Phạm vi (ACCESS-CONTROL.md)](docs/ACCESS-CONTROL.md)** — Phân tách phạm vi phòng ban, không gian toàn cục và ma trận phân quyền.
- **[Cẩm nang nghiệp vụ Wiki (WIKI.md)](docs/WIKI.md)** — Hướng dẫn tổ chức tài liệu và tối ưu cấu trúc nội dung.

---

## 🗺️ 8. Lộ trình phát triển (Roadmap)

- [x] **Quy trình MRP Pipeline:** Biên dịch tài liệu tự động, duyệt kế hoạch và hợp nhất nội dung.
- [x] **Máy chủ FastMCP Server:** Bộ công cụ MCP chuẩn hóa cho các ứng dụng AI.
- [x] **Phân vùng phòng ban & Toàn cục:** Quản lý phạm vi theo RBAC.
- [x] **Đồ thị tri thức & Trình duyệt Wiki:** Trực quan hóa liên kết 2D và quản lý bản nháp.
- [x] **Quản lý AI Skills:** Đóng gói và phân phối kỹ năng tác tử.
- [x] **Tìm kiếm kết hợp (Hybrid Search):** Tích hợp pgvector và Milvus.
- [x] **Nhận dạng văn bản OCR:** Hỗ trợ GLM-OCR xử lý tài liệu quét.
- [x] **Nhật ký kiểm vết (Audit Trail):** Ghi nhận đầy đủ thao tác hệ thống.
- [ ] **Trình kết nối dữ liệu tự động (Data Connectors):** Tự động đồng bộ từ Google Drive, SharePoint, Notion, Confluence.
- [ ] **Document Wiki CLI:** Công cụ dòng lệnh hỗ trợ thiết lập nhanh cho nhà phát triển.
- [ ] **Hệ thống cảnh báo & Thông báo đa kênh:** Hỗ trợ Webhook, Email và Slack khi có bản nháp hoặc kế hoạch cần phê duyệt.

---

## 🔒 9. An toàn thông tin & Bản quyền

Document Wiki là giải pháp quản trị tri thức tự lưu trữ phục vụ các nhu cầu nội bộ của doanh nghiệp và tổ chức.

Mọi bản quyền, mã nguồn và cấu trúc hệ thống được đóng gói để đảm bảo tính tự chủ, bảo mật và an toàn dữ liệu cao nhất.
