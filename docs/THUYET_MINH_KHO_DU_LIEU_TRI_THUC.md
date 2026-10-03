# TÀI LIỆU THUYẾT MINH KỸ THUẬT & PHƯƠNG ÁN TRIỂN KHAI

## GÓI: TƯ VẤN, CHUẨN HÓA VÀ XÂY DỰNG KHO DỮ LIỆU TRI THỨC

---

| Thông tin | Chi tiết |
| :--- | :--- |
| **Tên gói công việc** | **Tư vấn, chuẩn hóa và xây dựng Kho dữ liệu tri thức** |
| **Đơn vị tính** | Gói |
| **Số lượng** | 01 |
| **Đối tượng thụ hưởng/ứng dụng** | Hệ thống Trợ lý ảo / Chatbot phục vụ nghiệp vụ và tiếp công dân |
| **Mục tiêu chính** | Thiết lập nền tảng dữ liệu tri thức chuẩn hóa, bảo mật, tự động hóa cao, phục vụ truy vấn và huấn luyện AI đặc thù ngành Công an |

---

## MỤC LỤC
1. [TỔNG QUAN VÀ MỤC TIÊU](#1-tổng-quan-và-mục-tiêu)
2. [HẠNG MỤC 1: TƯ VẤN VÀ XÂY DỰNG QUY TRÌNH HƯỚNG DẪN (GUIDELINE)](#2-hạng-mục-1-tư-vấn-và-xây-dựng-quy-trình-hướng-dẫn-guideline)
   - 2.1. Khảo sát và phân loại nguồn dữ liệu
   - 2.2. Bộ quy chuẩn gán nhãn dữ liệu đặc thù (Data Annotation Guideline)
   - 2.3. Quy trình làm sạch và chuẩn hóa (Data Cleaning & Normalization)
   - 2.4. Quy định an toàn thông tin và bảo mật dữ liệu nhạy cảm
3. [HẠNG MỤC 2: XÂY DỰNG VÀ CHUẨN HÓA DATASET](#3-hạng-mục-2-xây-dựng-và-chuẩn-hóa-dataset)
   - 3.1. Phạm vi số hóa và cấu trúc hóa dữ liệu
   - 3.2. Đặc tả định dạng dữ liệu (JSON Schema, Parquet)
   - 3.3. Kỹ thuật tiền xử lý văn bản quy phạm pháp luật & hồ sơ mẫu
   - 3.4. Quản lý phiên bản dữ liệu (Data Versioning)
4. [HẠNG MỤC 3: THIẾT LẬP QUY TRÌNH TỰ ĐỘNG (DATA PIPELINE)](#4-hạng-mục-3-thiết-lập-quy-trình-tự-động-data-pipeline)
   - 4.1. Kiến trúc tổng thể luồng xử lý dữ liệu
   - 4.2. Các phân hệ chức năng trong Pipeline
   - 4.3. Cơ chế kiểm soát chất lượng (Quality Gates & Validation)
   - 4.4. Đưa dữ liệu vào Kho tri thức (Knowledge Base Ingestion)
5. [DANH MỤC SẢN PHẨM BÀN GIAO (DELIVERABLES)](#5-danh-mục-sản-phẩm-bàn-giao-deliverables)
6. [KẾ HOẠCH VÀ TIÊU CHÍ NGHIỆM THU](#6-kế-hoạch-và-tiêu-chí-nghiệm-thu)

---

## 1. TỔNG QUAN VÀ MỤC TIÊU

### 1.1. Bối cảnh
Dữ liệu trong ngành Công an mang tính đặc thù cao: có cấu trúc văn bản pháp quy nghiêm ngặt, tính chính xác tuyệt đối, chứa nhiều thuật ngữ nghiệp vụ, thủ tục hành chính công và các cấp độ bảo mật thông tin khác nhau. Việc xây dựng một hệ sinh thái Trợ lý ảo/AI hỗ trợ cán bộ chiến sĩ và người dân đòi hỏi Kho dữ liệu tri thức phải được chuẩn hóa từ gốc, loại bỏ sai lệch và có khả năng cập nhật tự động.

### 1.2. Mục tiêu cụ thể
- **Chuẩn hóa tri thức**: Chuyển đổi toàn bộ văn bản pháp luật, biểu mẫu nghiệp vụ, hồ sơ thủ tục hành chính từ dạng phi cấu trúc (PDF, Word, bản scan) sang các định dạng máy học đọc - hiểu được.
- **Xây dựng khung quy trình chuẩn (Guideline)**: Ban hành cẩm nang phân loại, gán nhãn, làm sạch phù hợp với nghiệp vụ ngành.
- **Tự động hóa luồng tiếp nhận (Data Pipeline)**: Xây dựng hệ thống tự động tiếp nhận, kiểm tra tính hợp lệ, làm sạch, tách đoạn (chunking), đánh chỉ mục và cập nhật vào Kho tri thức mà không cần thao tác thủ công phức tạp.
- **Đảm bảo an toàn thông tin**: Tuân thủ Luật Bảo vệ bí mật nhà nước và Nghị định số 13/2023/NĐ-CP về bảo vệ dữ liệu cá nhân.

---

## 2. HẠNG MỤC 1: TƯ VẤN VÀ XÂY DỰNG QUY TRÌNH HƯỚNG DẪN (GUIDELINE)

### 2.1. Khảo sát và phân loại nguồn dữ liệu
Tiến hành khảo sát thực trạng dữ liệu tại đơn vị, phân định thành 4 nhóm dữ liệu cốt lõi:
1. **Văn bản quy phạm pháp luật**: Luật, Nghị định, Thông tư liên quan trực tiếp đến an ninh trật tự, an toàn giao thông, cư trú, PCCC, quản lý xuất nhập cảnh, hình sự, tố tụng hình sự.
2. **Quy trình - Thủ tục hành chính công**: Hướng dẫn thủ tục, danh mục giấy tờ, biểu mẫu hồ sơ, thời hạn giải quyết, lệ phí (dịch vụ công trực tuyến cấp tỉnh/huyện/xã).
3. **Tài liệu hướng dẫn nghiệp vụ & Câu hỏi thường gặp (FAQ)**: Các tình huống xử lý thực tế, cẩm nang hỏi đáp nhanh về căn cước, định danh điện tử VNeID, xử phạt vi phạm giao thông,...
4. **Hồ sơ mẫu và biểu mẫu chuẩn**: Đơn từ, tờ khai mẫu đã được lược bỏ thông tin định danh cá nhân (PII).

### 2.2. Bộ quy chuẩn gán nhãn dữ liệu đặc thù (Data Annotation Guideline)
Xây dựng tài liệu hướng dẫn kỹ thuật chi tiết cho đội ngũ chuyên gia/người kiểm duyệt:
- **Gán nhãn thực thể nghiệp vụ (Named Entity Recognition - NER)**:
  - `[LAW_ARTICLE]`: Điều, khoản, điểm, văn bản trích dẫn.
  - `[PROCEDURE]`: Tên thủ tục hành chính.
  - `[AUTHORITY]`: Cơ quan thẩm quyền xử lý (Công an tỉnh, huyện, xã, Phòng chức năng).
  - `[FEE]`: Lệ phí, mức phạt tiền.
  - `[DEADLINE]`: Thời hạn giải quyết, thời hạn khiếu nại.
  - `[DOCUMENT_REQ]`: Thành phần hồ sơ bắt buộc.
- **Gán nhãn ngữ nghĩa & Ý định (Intent & Slot Tagging)**:
  - Phân loại ý định tra cứu (ví dụ: `tra_cuu_thu_tuc_cap_ho_chieu`, `tra_cuu_muc_phat_nong_do_con`, `huong_dan_kich_hoat_vneid`).
  - Gán nhãn cặp Hỏi - Đáp chuẩn (Q&A Pairs / Instruction-Response Pairs) phục vụ đánh giá RAG và tinh chỉnh mô hình.

### 2.3. Quy trình làm sạch và chuẩn hóa (Data Cleaning & Normalization)
Quy chuẩn hóa các bước xử lý lỗi dữ liệu thô:
- **Xử lý mã hóa và chính tả**: Chuẩn hóa toàn bộ về bộ mã `UTF-8 Unicode dựng sẵn`; chuẩn hóa dấu câu tiếng Việt chuẩn (kiểu gõ chuẩn quốc gia); loại bỏ lỗi dính chữ/vỡ chữ do OCR.
- **Chuẩn hóa cấu trúc điều khoản**: Định dạng đồng nhất tiêu đề văn bản, cấu trúc "Điều -> Khoản -> Điểm" giúp thuật toán chunking giữ trọn vẹn ngữ nghĩa pháp lý.
- **Loại bỏ trùng lặp (Deduplication)**: Nhận diện và lọc các phiên bản văn bản sửa đổi, bổ sung; gắn cờ trạng thái hiệu lực (Còn hiệu lực, Hết hiệu lực, Bị bãi bỏ một phần/toàn bộ).

### 2.4. Quy định an toàn thông tin và bảo mật dữ liệu nhạy cảm
- **Bộ lọc làm mờ dữ liệu cá nhân (PII Masking Rule)**:
  - Tự động phát hiện và che giấu/mã hóa số CCCD/CMND, số điện thoại, biển số xe, địa chỉ cụ thể cá nhân trong các hồ sơ mẫu.
- **Phân loại cấp độ bảo mật (Classification)**:
  - Nhãn `Công khai`: Phục vụ trả lời người dân qua Cổng dịch vụ công/Chatbot công khai.
  - Nhãn `Nội bộ`: Chỉ truy vấn trong mạng nội bộ phục vụ cán bộ chiến sĩ.
  - Ngăn chặn tuyệt đối việc đưa tài liệu thuộc danh mục bí mật nhà nước vào kho dữ liệu mô hình công khai.

---

## 3. HẠNG MỤC 2: XÂY DỰNG VÀ CHUẨN HÓA DATASET

### 3.1. Phạm vi số hóa và cấu trúc hóa dữ liệu
- Chuyển đổi toàn diện kho tài liệu từ dạng văn bản giấy scan/ảnh scan sang văn bản điện tử chất lượng cao thông qua OCR nâng cao kết hợp hậu kiểm soát thủ công.
- Tái cấu trúc văn bản thành dạng phân cấp (Hierarchical Tree Structure): Mỗi văn bản bao gồm Chương -> Mục -> Điều -> Khoản -> Điểm.

### 3.2. Đặc tả định dạng dữ liệu (JSON Schema, Parquet)
Dữ liệu sau khi xử lý được đóng gói thành hai định dạng tiêu chuẩn phục vụ các mục đích chuyên biệt:

#### a. Định dạng JSON / JSONL (Phục vụ Ingestion RAG & Quản lý tri thức)
Mỗi bản ghi đại diện cho một phân đoạn kiến thức hoàn chỉnh (Knowledge Chunk):
```json
{
  "id": "CAHY-PL-GT-2024-ND100-D05",
  "document_code": "100/2019/NĐ-CP",
  "title": "Nghị định quy định xử phạt vi phạm hành chính trong lĩnh vực giao thông đường bộ và đường sắt",
  "category": "Giao thông",
  "scope": "public",
  "status": "active",
  "effective_date": "2020-01-01",
  "hierarchy": {
    "chapter": "II",
    "section": "1",
    "article": "5",
    "article_title": "Xử phạt người điều khiển xe ô tô và các loại xe tương tự xe ô tô vi phạm quy tắc giao thông đường bộ"
  },
  "content": "Phạt tiền từ 2.000.000 đồng đến 3.000.000 đồng đối với người điều khiển xe thực hiện hành vi sử dụng điện thoại di động khi đang điều khiển xe chạy trên đường.",
  "metadata": {
    "keywords": ["ô tô", "dùng điện thoại", "phạt tiền", "mức phạt giao thông"],
    "legal_references": ["Khoản 4 Điều 5 Nghị định 100/2019/NĐ-CP"],
    "target_roles": ["can_bo_xu_ly", "nguoi_dan"]
  }
}
```

#### b. Định dạng Parquet (Phục vụ truy vấn phân tích dung lượng lớn & Vector Pipeline)
- Dữ liệu dạng bảng nén theo cột (Columnar format), tối ưu dung lượng lưu trữ tới 70-80% so với văn bản gốc.
- Các cột chuẩn: `chunk_id` (string), `doc_hash` (string), `text` (string), `embedding_vector` (array<float>), `metadata_json` (string), `updated_at` (timestamp).
- Cho phép nạp siêu tốc vào các hệ thống tính toán phân tán, cơ sở dữ liệu Vector và kiểm thử mô hình đánh giá (Benchmarking).

### 3.3. Kỹ thuật tiền xử lý văn bản quy phạm pháp luật (Legal Chunking Strategy)
- Không áp dụng phương pháp cắt đoạn ngẫu nhiên theo số ký tự cố định (fixed character chunking) để tránh việc câu lệnh mức phạt bị chia cắt khỏi tên hành vi vi phạm.
- **Chiến lược Semantic Legal Chunking**:
  - Đơn vị chia cắt tối thiểu là 01 Khoản/Điểm trọn vẹn ý nghĩa pháp lý.
  - Luôn đính kèm ngữ cảnh nguồn (Tên Điều + Tên Văn bản) vào phần đầu của mỗi chunk trước khi vector hóa.

### 3.4. Quản lý phiên bản dữ liệu (Data Versioning)
- Ứng dụng quy tắc DVC (Data Version Control) hoặc Semantic Versioning (`v1.0.0`, `v1.1.0`).
- Mỗi thay đổi về văn bản luật (sửa đổi, bổ sung) đều được gắn cờ theo dõi phiên bản, lưu lại vết sửa đổi (Changelog) nhằm đảm bảo hệ thống có thể truy vết nguồn gốc tri thức tại từng mốc thời gian.

---

## 4. HẠNG MỤC 3: THIẾT LẬP QUY TRÌNH TỰ ĐỘNG (DATA PIPELINE)

### 4.1. Kiến trúc tổng thể luồng xử lý dữ liệu

```
[Nguồn Dữ Liệu Đầu Vào]
(PDF / DOCX / Web Cổng DVC / Scan)
         │
         ▼
┌──────────────────────────────────────────────┐
│       PHÂN HỆ THU THẬP & TIẾP NHẬN          │
│ - Tự động theo dõi thư mục (Folder Watcher)  │
│ - API Ingestion / Webhook Upload             │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│       PHÂN HỆ TIỀN XỬ LÝ & BẢO VỆ DỮ LIỆU    │
│ - Chuyển đổi định dạng & OCR Engine          │
│ - PII Masking (Lọc thông tin cá nhân)        │
│ - Chuẩn hóa font, ngữ nghĩa, cấu trúc        │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│       CỔNG KIỂM TRA CHẤT LƯỢNG (VALIDATION)   │
│ - Schema Validator (JSON/Parquet)            │
│ - Kiểm tra trùng lặp (Deduplication Check)   │
│ - Duyệt tự động & Hàng đợi chuyên gia soát xét│
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│       PHÂN HỆ CHUNK & VECTOR HÓA TRI THỨC    │
│ - Semantic Legal Chunking Engine             │
│ - Sinh Embedding đa ngôn ngữ / tiếng Việt    │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│           KHO DỮ LIỆU TRI THỨC               │
│ ┌──────────────────────┐ ┌─────────────────┐ │
│ │ Vector Database      │ │ Document Store  │ │
│ │ (Tra cứu ngữ nghĩa)  │ │ (Văn bản gốc)   │ │
│ └──────────────────────┘ └─────────────────┘ │
└──────────────────────────────────────────────┘
```

### 4.2. Các phân hệ chức năng trong Pipeline
1. **Phân hệ Tiếp nhận (Ingestion Service)**:
   - Cung cấp giao diện tải tệp và Webhook API hỗ trợ nhận đa định dạng (`.pdf`, `.docx`, `.json`, `.csv`, `.xlsx`).
   - Tự động xếp hàng đợi tác vụ xử lý thông qua Message Queue (Celery/RabbitMQ/Redis).
2. **Phân hệ Phân tích & Tách đoạn (Parser & Chunking Service)**:
   - Trích xuất bảng biểu, cấu trúc văn bản hành chính theo đúng chuẩn thể thức văn bản nhà nước (Nghị định 30/2020/NĐ-CP).
   - Áp dụng bộ parser chuyên biệt nhận diện chính xác các cấp mục: "Phần -> Chương -> Mục -> Điều -> Khoản -> Điểm".
3. **Phân hệ Vector hóa & Đánh chỉ mục (Embedding & Indexing Engine)**:
   - Tích hợp mô hình sinh vector đại diện phù hợp nhất với tiếng Việt pháp lý (Vietnamese Bi-Encoder / Multilingual-e5).
   - Tự động nạp chỉ mục vào cơ sở dữ liệu Vector (ChromaDB / Qdrant / Milvus / PostgreSQL pgvector).

### 4.3. Cơ chế kiểm soát chất lượng (Quality Gates & Validation)
- **Kiểm định tính hợp lệ**: Tự động chặn các tài liệu thiếu tiêu đề, thiếu số hiệu văn bản hoặc ngày ban hành.
- **Hàng đợi hậu kiểm (Human-in-the-loop Review)**: Những tài liệu scan có độ tin cậy OCR dưới 90% hoặc chứa thông tin nghi vấn nhạy cảm sẽ được chuyển sang danh sách chờ Cán bộ phụ trách duyệt trước khi hòa nhập vào Kho tri thức chính thức.

### 4.4. Giám sát và Báo cáo (Monitoring & Audit Log)
- Ghi nhật ký chi tiết lịch sử cập nhật: Ai đưa tài liệu lên, thời gian, kết quả xử lý, số lượng chunks được sinh ra.
- Cung cấp Dashboard thống kê số lượng văn bản, dung lượng kho tri thức, tỷ lệ thành công của pipeline.

---

## 5. DANH MỤC SẢN PHẨM BÀN GIAO (DELIVERABLES)

| STT | Tên sản phẩm / Tài liệu | Định dạng bàn giao | Nội dung bàn giao chi tiết |
| :---: | :--- | :--- | :--- |
| **01** | **Bộ Quy trình Hướng dẫn (Guideline)** | File tài liệu (`.pdf`, `.docx`) | - Cẩm nang phân tích, gán nhãn dữ liệu nghiệp vụ Công an.<br>- Quy trình làm sạch, khử trùng lặp và bảo vệ dữ liệu nhạy cảm.<br>- Bộ tiêu chuẩn mã hóa danh mục hành chính. |
| **02** | **Bộ Dữ liệu chuẩn hóa (Dataset)** | Kho lưu trữ (`.json`, `.parquet`) | - Toàn bộ dữ liệu văn bản pháp luật, thủ tục hành chính, biểu mẫu đã được chuẩn hóa.<br>- File Dataset Parquet tối ưu nạp mô hình AI.<br>- Tập mẫu câu hỏi - đáp (FAQ) kiểm thử hệ thống. |
| **03** | **Module Luồng xử lý tự động (Data Pipeline)** | Mã nguồn & Cấu hình Docker | - Toàn bộ Source code các script/module thu thập, trích xuất, làm sạch và chunking.<br>- Bộ kiểm tra tự động Schema Validation & PII Filter.<br>- Container Docker đóng gói triển khai sẵn. |
| **04** | **Kho Dữ liệu tri thức hoàn chỉnh (Knowledge Base)** | Database & Vector DB | - Cấu trúc lưu trữ văn bản hoàn chỉnh gắn chỉ mục tìm kiếm văn bản đầy đủ (Full-text Search).<br>- Chỉ mục Vector ngữ nghĩa (Vector Index) đã nạp đầy đủ tri thức nghiệm thu. |
| **05** | **Tài liệu Hướng dẫn vận hành & Chuyển giao** | File tài liệu kỹ thuật | - Hướng dẫn vận hành Pipeline tự động khi có văn bản mới.<br>- Hướng dẫn sao lưu (Backup) và phục hồi dữ liệu tri thức. |

---

## 6. KẾ HOẠCH VÀ TIÊU CHÍ NGHIỆM THU

### 6.1. Tiêu chí chất lượng dữ liệu
1. **Độ chính xác nội dung**: 100% văn bản quy phạm pháp luật không bị sai lệch số hiệu, điều khoản hoặc mất ý do lỗi xử lý văn bản.
2. **Tuân thủ định dạng**: 100% tệp JSON/Parquet vượt qua bài kiểm tra tính hợp lệ của JSON Schema đã ban hành.
3. **An toàn thông tin**: 100% hồ sơ mẫu kiểm thử không lộ lọt dữ liệu định danh cá nhân nhạy cảm thực tế.

### 6.2. Tiêu chí kỹ thuật của Pipeline
1. **Tính tự động**: Chỉ cần đưa tệp nguồn vào hệ thống tiếp nhận, toàn bộ chu trình trích xuất -> lọc -> làm sạch -> chunking -> vector hóa diễn ra tự động hoàn toàn.
2. **Thời gian xử lý**: Tốc độ xử lý trung bình dưới 30 giây cho một tài liệu văn bản quy chuẩn 20 trang.
3. **Khả năng mở rộng**: Dễ dàng tích hợp thêm các nguồn dữ liệu văn bản mới mà không ảnh hưởng tới dữ liệu tri thức đang hoạt động.
