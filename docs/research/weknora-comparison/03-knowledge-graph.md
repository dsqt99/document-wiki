# 03 · Knowledge Graph

## 1. Hiện trạng hai bên

### WeKnora
- **Trích xuất**: `ChunkExtractService.Handle` (`internal/application/service/extract.go:224`), mỗi chunk một lần gọi LLM, prompt `config/prompt_templates/graph_extraction.yaml`. Cấu hình few-shot, tag, chỉ dẫn riêng theo KB (`ExtractConfig`).
- **Dữ liệu**: `GraphData{Node{name, attributes, chunks}, Relation{node1, node2, type}}` (`internal/types/extract_graph.go`).
- **Lưu trữ**: Neo4j, bật bằng `NEO4J_ENABLE=true` (mặc định tắt). `repository/retriever/neo4j/repository.go`: `AddGraph`, `DelGraph`, `SearchNode`. Label theo KB + tài liệu.
- **Truy vấn**: `PluginSearchEntity` (`chat_pipeline/search_entity.go`) chạy song song với tìm chunk. Lấy thực thể từ bước hiểu câu hỏi → Cypher `n.name CONTAINS $x` → mở rộng 1 bước. Agent có tool `query_knowledge_graph`.
- **Hạn chế**: không gộp thực thể (so khớp chuỗi con), không embedding cho node, chỉ 1 bước, không community/global summary kiểu GraphRAG/LightRAG. `service/graph.go` (`graphBuilder`) không được gọi, là code chết.

**Kết luận: graph của WeKnora không đáng copy.** Chỉ học ý tưởng "graph search chạy song song với vector search rồi trộn kết quả".

### Arkon
- **Trích xuất**: MAP prompt (`app/ai/mrp/mapper.py`, `EXTRACTION_PROMPT_TEMPLATE`) yêu cầu `concepts`, `claims` (có offset), `relations`, `topics`.
  - **`relations` không được dùng ở đâu cả**, chỉ tốn token.
  - `entities` bị ép `[]`; `embedding_dedup_entities` là stub trả `[]`.
- **Gộp khái niệm** (`app/ai/mrp/reducer.py`): khớp chính xác → cosine embedding (> 0.90 gộp, 0.75–0.90 hỏi LLM) → `reconcile_with_kb` đối chiếu trang đã có. **Tốt hơn WeKnora.**
- **Graph duy nhất đang có**: wikilink `[[slug]]` → bảng `wiki_links` (`wiki_service.extract_wikilinks`, `refresh_links`; đọc qua `get_backlinks`, `get_outlinks`, `get_neighborhood`). Frontend `/wiki/graph` vẽ bằng react-force-graph-2d.
- **Không dùng graph khi tìm kiếm.**

## 2. Thiết kế đề xuất cho Arkon

Hai lớp graph, **đều trên Postgres** (không thêm Neo4j):

```
┌───────────────────────────────┐   ┌──────────────────────────────────┐
│ A. Graph khái niệm (LLM)      │   │ B. Graph pháp luật (luật cứng)   │
│  node = wiki page (concept)   │   │  node = văn bản / Điều / Khoản   │
│  edge = relations từ MAP      │   │  edge = sửa đổi, thay thế,       │
│  gộp node nhờ reducer có sẵn  │   │         dẫn chiếu, hướng dẫn     │
└──────────────┬────────────────┘   └────────────────┬─────────────────┘
               └──────────── dùng chung ─────────────┘
                   search_wiki: top-k → mở rộng 1 bước → rerank
```

### 2A. Graph khái niệm (tận dụng `relations` đã trích)

**Schema** (migration mới):
```sql
CREATE TABLE concept_relations (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    src_page_id   uuid NOT NULL REFERENCES wiki_pages(id) ON DELETE CASCADE,
    dst_page_id   uuid NOT NULL REFERENCES wiki_pages(id) ON DELETE CASCADE,
    rel_type      text NOT NULL,          -- chuẩn hoá: la_mot, thuoc, quy_dinh, ap_dung_cho, ...
    rel_label     text,                   -- nhãn gốc LLM trả về
    source_id     uuid REFERENCES sources(id) ON DELETE CASCADE,
    evidence      text,                   -- câu trích dẫn chứng
    char_start    int, char_end int,
    confidence    real,
    scope_type    text NOT NULL, scope_id uuid,
    created_at    timestamptz DEFAULT now(),
    UNIQUE (src_page_id, dst_page_id, rel_type, source_id)
);
CREATE INDEX ON concept_relations (src_page_id);
CREATE INDEX ON concept_relations (dst_page_id);
```

**Luồng:**
1. MAP: giữ nguyên `relations` trong `source_chunk_extracts`. Sửa prompt: yêu cầu `{subject, predicate, object, evidence_quote}` với `predicate` thuộc danh sách đóng (8–12 loại), tránh LLM đặt nhãn tuỳ ý.
2. REDUCE: sau khi gộp concept, ánh xạ `subject`/`object` sang concept đã gộp (dùng cùng bảng ánh xạ của reducer).
3. COMMIT (`run_commit_phase`): khi đã có `page_id` → ghi `concept_relations`. Xoá theo `source_id` khi xoá hoặc chạy lại nguồn.
4. Frontend `/wiki/graph`: thêm cạnh có kiểu (màu theo `rel_type`), bộ lọc theo loại cạnh.

**Chi phí:** không tốn thêm lần gọi LLM (đã trích sẵn), chỉ tốn thêm vài trăm token output mỗi chunk MAP nếu yêu cầu `evidence_quote`.

### 2B. Graph pháp luật (giá trị cao nhất cho chatbot công an)

Văn bản pháp luật Việt Nam có quan hệ **viết rõ trong câu chữ**, trích bằng regex là đủ, không cần LLM.

**Loại quan hệ:**

| Loại | Mẫu câu chữ | Ví dụ |
|---|---|---|
| `sua_doi` / `bo_sung` | "sửa đổi, bổ sung một số điều của …", "Điều X được sửa đổi như sau" | NĐ 50/2024 sửa NĐ 136/2020 |
| `thay_the` | "thay thế …", "… hết hiệu lực kể từ ngày" | |
| `bai_bo` | "bãi bỏ Điều/Khoản …" | |
| `huong_dan` | "quy định chi tiết …", "hướng dẫn thi hành …" | Thông tư hướng dẫn Luật |
| `can_cu` | Phần "Căn cứ …" ở đầu văn bản | Căn cứ Luật Tổ chức Chính phủ … |
| `dan_chieu` | "theo quy định tại Điều X (Khoản Y) (của Luật Z)" | Điều → Điều |
| `hop_nhat` | Văn bản hợp nhất (VBHN) | VBHN gộp luật gốc + các lần sửa |

**Schema:**
```sql
CREATE TABLE legal_documents (
    id            uuid PRIMARY KEY,
    source_id     uuid REFERENCES sources(id) ON DELETE CASCADE,
    so_hieu       text,                   -- 136/2020/NĐ-CP (đã chuẩn hoá)
    loai_van_ban  text,                   -- Luật, Nghị định, Thông tư, Quyết định...
    co_quan       text,
    ngay_ban_hanh date,
    ngay_hieu_luc date,
    tinh_trang    text,                   -- con_hieu_luc | het_hieu_luc | het_mot_phan
    trich_yeu     text,
    overview_page_id uuid REFERENCES wiki_pages(id)
);
CREATE UNIQUE INDEX ON legal_documents (so_hieu);

CREATE TABLE legal_units (                 -- Chương / Mục / Điều / Khoản / Điểm
    id          uuid PRIMARY KEY,
    document_id uuid REFERENCES legal_documents(id) ON DELETE CASCADE,
    parent_id   uuid REFERENCES legal_units(id) ON DELETE CASCADE,
    level       text,                      -- chuong|muc|dieu|khoan|diem
    number      text,                      -- "II", "1", "5", "2", "a"
    path        text,                      -- "Chương II > Mục 1 > Điều 5 > Khoản 2"
    title       text,
    content     text,
    page_id     uuid REFERENCES wiki_pages(id),   -- trang Điều tương ứng
    effective_status text
);

CREATE TABLE legal_relations (
    id           uuid PRIMARY KEY,
    src_doc_id   uuid REFERENCES legal_documents(id) ON DELETE CASCADE,
    src_unit_id  uuid REFERENCES legal_units(id) ON DELETE CASCADE,
    dst_so_hieu  text,                     -- có thể chưa có văn bản đích trong KB
    dst_doc_id   uuid REFERENCES legal_documents(id),
    dst_unit_ref text,                     -- "Điều 5 Khoản 2"
    dst_unit_id  uuid REFERENCES legal_units(id),
    rel_type     text,
    evidence     text
);
```

`dst_so_hieu` cho phép lưu quan hệ tới văn bản **chưa được upload**. Khi văn bản đó được upload, một job nhỏ sẽ nối lại `dst_doc_id`/`dst_unit_id`. Cũng dùng được để gợi ý admin "Thiếu văn bản gốc: 136/2020/NĐ-CP".

**Regex khởi điểm** (cần mở rộng qua dữ liệu thật):
```python
SO_HIEU = r"(\d{1,4}/\d{4}/[A-ZĐ]{1,5}(?:-[A-ZĐ]{1,10})*|\d{1,4}/[A-ZĐ]{1,5}(?:-[A-ZĐ]{1,10})+)"
REF_UNIT = re.compile(
    r"(?:(điểm)\s+([a-zđ])\s*,?\s*)?"
    r"(?:(khoản)\s+(\d+)\s*,?\s*)?"
    r"(Điều)\s+(\d+[a-z]?)"
    r"(?:\s+(?:của\s+)?(Luật|Bộ luật|Nghị định|Thông tư|Nghị quyết|Pháp lệnh)\s*(?:số\s*)?"
    + SO_HIEU + r"?)?",
    re.IGNORECASE,
)
AMEND_DOC = re.compile(r"sửa đổi,?\s*bổ sung (?:một số điều )?(?:của )?.{0,80}?" + SO_HIEU, re.I)
REPLACE   = re.compile(r"(?:thay thế|hết hiệu lực)[^.]{0,120}?" + SO_HIEU, re.I)
GUIDE     = re.compile(r"(?:quy định chi tiết|hướng dẫn(?: thi hành)?)[^.]{0,120}?" + SO_HIEU, re.I)
```
Dẫn chiếu không nêu văn bản ("theo quy định tại Điều 5") → mặc định là **cùng văn bản**. Dẫn chiếu "Luật này", "Nghị định này" → cùng văn bản.

**Tình trạng hiệu lực:** khi văn bản B `thay_the` A → `A.tinh_trang = het_hieu_luc`. B `sua_doi` Điều 5 của A → `legal_units(A, Điều 5).effective_status = da_sua_doi`, trang wiki Điều 5 hiện banner "Điều này đã được sửa đổi bởi … (xem …)".

## 3. Dùng graph khi tìm kiếm

Sửa MCP `search_wiki` / `search_source_content` (`app/mcp/tools.py`):

```
1. hybrid search (hiện có) → top 20
2. mở rộng 1 bước cho top 5:
   - legal_relations: Điều bị sửa đổi → kèm Điều sửa đổi mới nhất (ưu tiên cao)
   - dẫn chiếu: kèm Điều được dẫn chiếu (ưu tiên thấp)
   - concept_relations / wiki_links: kèm trang liên quan (ưu tiên thấp)
3. rerank toàn bộ (xem 04 §3)
4. trả kết quả, mỗi kết quả kèm "vì sao được đưa vào": direct | amended_by | referenced | related
```

Thêm MCP tool:
- `get_legal_status(so_hieu | page_slug)`: tình trạng hiệu lực + danh sách văn bản sửa đổi/thay thế.
- `get_related(page_slug, rel_types?, depth=1)`: lân cận trên graph.

Thứ tự ưu tiên: **2B (pháp luật) trước 2A (khái niệm).** 2B chắc chắn, rẻ, trả lời đúng câu hỏi "điều này còn hiệu lực không".

## 4. Về GraphRAG / LightRAG

- **GraphRAG (Microsoft)**: community detection + tóm tắt cộng đồng, hợp cho câu hỏi tổng quát ("các chủ đề chính trong kho là gì"). Chi phí index rất cao. Wiki của Arkon (`_index` + trang khái niệm) đã đóng vai trò "tóm tắt toàn cục" → **không cần**.
- **LightRAG**: truy vấn hai mức local/global trên graph thực thể. Có thể cân nhắc sau khi 2A ổn định; khi đó chỉ cần thêm embedding cho `concept_relations.evidence`.

## 5. Nghiệm thu

- Upload NĐ 136/2020 + NĐ 50/2024 → có cạnh `sua_doi` giữa 2 văn bản; các Điều bị sửa có banner.
- Hỏi "Điều X NĐ 136 quy định gì" → kết quả gồm cả nội dung đã sửa ở NĐ 50.
- `/wiki/graph` hiển thị cạnh có kiểu, lọc được.
- Xoá nguồn → xoá cạnh tương ứng (không để cạnh mồ côi).
