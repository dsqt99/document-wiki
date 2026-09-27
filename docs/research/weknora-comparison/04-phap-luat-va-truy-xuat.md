# 04 · Văn bản pháp luật và chất lượng truy xuất

## 1. Tách cấp bậc văn bản pháp luật

### Hiện trạng (`app/services/legal_service.py`)
- `is_legal_source`: nhận biết qua slug knowledge type (`lut`, `luat`, `legal`) hoặc tên chứa "luật", "legal", "pháp lý".
- `parse_legal_metadata`: regex lấy số hiệu, cơ quan, ngày, loại, trích yếu. **Có hard-code tên riêng** cho một số nghị định (136/2020, 50/2024, 105/2025, PCCC…) → không mở rộng được.
- `split_legal_text_by_articles`: **chỉ tách đến Điều** (`ARTICLE_RE`, dòng 37). Không có Chương/Mục/Khoản/Điểm; tiêu đề Chương/Mục bị dính vào nội dung Điều liền trước.
- `finalize_legal_source`: 1 trang tổng quan + 1 trang mỗi Điều, status `mature`, embed.

### Vấn đề cụ thể
1. **`ARTICLE_RE` bắt nhầm**: mọi dòng mở đầu bằng "Điều N", kể cả phần trích trong nghị định sửa đổi:
   ```
   Điều 1. Sửa đổi, bổ sung một số điều của Nghị định 136/2020/NĐ-CP
   1. Sửa đổi Điều 5 như sau:
   "Điều 5. Trách nhiệm ...     ← bị tách thành Điều 5 của văn bản sửa đổi (SAI)
   ```
   Regex hiện cho phép dấu ngoặc kép mở đầu (`(?:“|\"|”)?`), nên đúng là rơi vào trường hợp này.
2. **Slug trùng**: `doc_slug = slugify(doc_title)[:60]` (dòng 346, 466) → hai văn bản có tên giống nhau ở 60 ký tự đầu ghi đè `dieu-N-*` của nhau. Ví dụ "Nghị định quy định chi tiết một số điều và biện pháp thi hành Luật …".
3. **Phụ lục** (biểu mẫu) bị gộp vào Điều cuối.
4. Không có Khoản/Điểm nên không trích dẫn được mức "khoản 2 Điều 5", và chunk mỗi Điều dài thì embedding bị loãng.

### Thiết kế parser cấp bậc

Chạy tuần tự từng dòng, theo máy trạng thái:

```python
LEVELS = [
    ("phan",  re.compile(r"^\s*PHẦN\s+(THỨ\s+[A-ZÀ-Ỹ]+|[IVXLC]+)\b", re.I)),
    ("chuong",re.compile(r"^\s*Chương\s+([IVXLC]+|\d+)\b", re.I)),
    ("muc",   re.compile(r"^\s*Mục\s+(\d+)\b", re.I)),
    ("tieumuc",re.compile(r"^\s*Tiểu mục\s+(\d+)\b", re.I)),
    ("dieu",  re.compile(r"^\s*Điều\s+(\d+[a-z]?)\s*[\.:]\s*(.*)$")),
    ("khoan", re.compile(r"^\s*(\d+)\.\s+(?=\S)")),
    ("diem",  re.compile(r"^\s*([a-zđ])\)\s+")),
]
APPENDIX = re.compile(r"^\s*(PHỤ LỤC|Phụ lục)\b")
```

Quy tắc:
- **Vùng trích dẫn**: khi gặp dấu mở ngoặc kép `“` hoặc `"` ở đầu dòng, hoặc câu "… như sau:" → vào chế độ *quoted*; mọi Điều/Khoản trong vùng này là **nội dung được sửa đổi**, không tách thành đơn vị của văn bản hiện tại. Ghi nhận thành `legal_relations(rel_type=sua_doi, dst_unit_ref="Điều 5")` kèm nội dung mới. Thoát khi gặp `”` hoặc `"` ở cuối đoạn.
- `Khoản`/`Điểm` chỉ có nghĩa **bên trong một Điều**; ngoài Điều thì dòng "1." là danh sách thường.
- Tiêu đề Chương/Mục có thể xuống dòng (dòng kế tiếp viết hoa) → gộp.
- Gặp `PHỤ LỤC` → dừng cây Điều, phần còn lại thành đơn vị `phu_luc`.
- Kết quả lưu vào `legal_units` (xem [03 §2B](03-knowledge-graph.md)).

**Slug:** dùng số hiệu đã chuẩn hoá: `nd-136-2020-nd-cp/dieu-5`. Nếu không có số hiệu → `slugify(title)[:40] + "-" + hash8(source_id)`.

**Metadata:** bỏ hard-code tên; lấy trích yếu từ khối sau dòng loại văn bản (NGHỊ ĐỊNH / THÔNG TƯ / LUẬT) cho tới "Căn cứ". Ngày hiệu lực lấy từ Điều "Hiệu lực thi hành" (thường ở cuối): "có hiệu lực (thi hành) kể từ ngày …".

### Trang wiki và chunk
- Giữ **1 trang mỗi Điều** (đơn vị đọc hợp lý), nội dung có Khoản/Điểm dạng danh sách markdown.
- Breadcrumb đầu trang: `NĐ 136/2020/NĐ-CP › Chương II › Mục 1 › Điều 5`.
- **Chunk để embed theo Khoản** (parent-child, học WeKnora `SplitParentChild`): con = Khoản (kèm tiêu đề Điều + breadcrumb làm tiền tố embedding), cha = Điều. Tìm trúng Khoản → trả cả Điều, đánh dấu Khoản trúng.
- Điều ngắn (< 800 ký tự) → không tách, embed cả Điều.

---

## 2. Tìm kiếm lai (hybrid) cho tiếng Việt

### Hiện trạng
`wiki_service.search_pages_hybrid` / `search_source_chunks_hybrid`: kNN cosine (50) + full-text `websearch_to_tsquery('simple', f_unaccent(q))` (50) → RRF k=60 (`search_fusion.py`). MCP bỏ kết quả cosine < 0.30 trừ khi nhánh full-text cũng trúng.

### Vấn đề
- `simple` + `unaccent`: "bắt", "bật", "bất" đều thành "bat"; "phạt" và "phát" trùng nhau → nhiễu nặng với văn bản pháp luật.
- Không tách từ: "cảnh sát" là 2 token độc lập, "quản lý" khớp cả "quản" lẫn "lý" rời rạc.
- Không có trọng số BM25 thực sự (`ts_rank` không phải BM25).

### Đề xuất (chọn 1 trong 2 hướng)

**Hướng A: giữ Postgres FTS, cải thiện index**
1. Hai cột tsvector:
   - `tsv_accent`: `to_tsvector('simple', text_segmented)`, có dấu, đã tách từ (từ ghép nối bằng `_`: `cảnh_sát`, `quản_lý`).
   - `tsv_unaccent`: như trên nhưng bỏ dấu (cho người gõ không dấu).
2. Câu hỏi: nếu có dấu → ưu tiên `tsv_accent` (trọng số 1.0), `tsv_unaccent` (0.3); không dấu → chỉ `tsv_unaccent`.
3. Tách từ bằng `pyvi` (nhẹ) hoặc `underthesea` khi index (trong worker) và khi truy vấn.

**Hướng B: BM25 thật**
- ParadeDB `pg_search` (WeKnora dùng; mở rộng Postgres, có BM25) hoặc OpenSearch với plugin tiếng Việt. Tốn công vận hành hơn. Chỉ làm nếu Hướng A chưa đủ.

Ngoài ra:
- **Tra số hiệu chính xác**: câu hỏi chứa `136/2020/NĐ-CP`, "Điều 5" → lọc cứng theo `legal_units` trước khi tìm ngữ nghĩa (tuyến "tra cứu" riêng, học intent classify của WeKnora `query_understand.go`).
- **Bỏ Milvus** (chỉ ghi, không đọc) hoặc chuyển hẳn sang đọc từ Milvus. Không nên giữ cả hai.

---

## 3. Rerank

WeKnora: `internal/reranking/rerank.go`, gồm điểm rerank model → ngưỡng (tự hạ nếu loại hết) → điểm tối thiểu dự phòng → điểm tổng hợp → MMR (`mmr.go`) để đa dạng.

Đề xuất cho Arkon:
- Model: `BAAI/bge-reranker-v2-m3` (đa ngôn ngữ, tiếng Việt ổn), chạy qua TEI (text-embeddings-inference) hoặc Infinity, API tương thích `/rerank`. Thêm `rerank_provider` vào registry (cạnh embedding/vision).
- Luồng: hybrid top 30–50 → rerank → ngưỡng → MMR (λ=0.7) → top k.
- Đầu vào rerank: `breadcrumb + title + chunk` (không chỉ chunk).
- Dự phòng: rerank lỗi hoặc timeout → trả kết quả RRF như hiện tại.
- Thay ngưỡng cứng `MIN_SIM_FLOOR = 0.30` bằng ngưỡng theo điểm rerank.

---

## 4. Sinh câu hỏi cho chunk (question generation)

WeKnora: `ProcessQuestionGeneration` (`knowledge_process.go:1626`), prompt `config/prompt_templates/generate_questions.yaml`; theo lô, lấy chunk trước/sau làm ngữ cảnh; câu hỏi lưu vào metadata, index thành vector phụ trỏ về chunk.

Đề xuất cho Arkon (rất hợp với câu hỏi người dân về luật):
- Áp dụng cho **chunk Điều/Khoản pháp luật** và chunk wiki trang `mature`.
- Mỗi chunk 3–5 câu hỏi **theo văn nói**: "Không đội mũ bảo hiểm bị phạt bao nhiêu?", "Thủ tục đăng ký tạm trú cần giấy tờ gì?".
- Bảng `chunk_questions(chunk_id, question, embedding)`; khi tìm, nhánh vector tìm cả chunk lẫn câu hỏi, trùng chunk thì lấy điểm cao nhất.
- Chạy nền sau khi nguồn `ready`, hàng đợi riêng, có ngưỡng token (đúng tinh thần kiểm soát chi phí của Arkon).

---

## 5. Hiểu câu hỏi / viết lại câu hỏi

Arkon đang giao cho MCP client. Nếu chatbot CAHY có giao diện chat riêng (không qua Claude), cần pipeline server-side tương tự `rag_stream` của WeKnora:

```
LOAD_HISTORY → QUERY_UNDERSTAND (viết lại theo lịch sử + phân loại ý định:
    tra_cuu_so_hieu | hoi_quy_dinh | thu_tuc | chitchat | ngoai_pham_vi)
→ SEARCH (hybrid + graph + câu hỏi) → RERANK → MERGE/EXPAND (parent)
→ BUILD PROMPT (kèm trích dẫn) → STREAM
```
- Chuẩn hoá câu hỏi: NFC, mở rộng viết tắt ("NĐ" → "Nghị định", "TT" → "Thông tư", "CSGT", "PCCC", "CCCD"...).
- Mở rộng câu hỏi khi recall thấp (WeKnora `query_expansion.go`): nếu top-1 dưới ngưỡng → sinh 2–3 biến thể từ khoá, chạy lại nhánh keyword.
- Câu hỏi ngoài phạm vi / không đủ căn cứ → trả lời "không tìm thấy căn cứ" thay vì bịa (bắt buộc với lĩnh vực pháp luật).

---

## 6. Trích dẫn

Hiện trạng: `docs/ARCHITECTURE.md` hứa claim có `[^N]`, nhưng `writer.py` (`WRITER_SYSTEM`) cấm footnote và cấm mục Citations; `verifier.py` không kiểm trích dẫn. Provenance chỉ ở cấp trang (`WikiPage.source_ids`); `PageWriteResult.citations` thu được nhưng không hiển thị.

Đề xuất:
- **Trang luật**: trích dẫn cấp Khoản là tự nhiên (đã verbatim), chỉ cần kết quả tìm kiếm trả `so_hieu + Điều + Khoản + link`.
- **Trang wiki tổng hợp**: bật lại trích dẫn nhẹ `[^s1]` trỏ về `source_id + page_number`, dùng `claims` có offset sẵn từ MAP. Verifier kiểm: mỗi đoạn có ≥ 1 trích dẫn; trích dẫn trỏ tới source có thật.
- Cập nhật `docs/ARCHITECTURE.md` cho đúng hiện trạng.

---

## 7. Đánh giá chất lượng (eval)

WeKnora: `service/evaluation.go` + `service/metric/` (BLEU, ROUGE, MAP, MRR, NDCG, precision, recall). Kết quả chỉ lưu trong RAM.

Đề xuất cho Arkon (nhỏ nhưng bắt buộc trước khi tối ưu):
- `eval/questions.yaml`: 100–200 câu hỏi thật, mỗi câu gắn `expected`: danh sách `so_hieu + Điều (+ Khoản)` hoặc slug trang.
- Script `python -m app.eval.retrieval`: chạy `search_wiki`, tính Recall@5, Recall@10, MRR, nDCG@10.
- Tuỳ chọn: LLM-as-judge cho câu trả lời (đúng căn cứ, không bịa).
- Chạy trước/sau mỗi thay đổi parser, chunk, rerank; lưu kết quả vào `eval/results/<date>.json`.
