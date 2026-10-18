# Rà soát các chỗ cắt nội dung (truncation) — 2026-10-18

Bắt đầu từ lỗi ô **Tóm tắt** của trang Điều bị cắt giữa chữ ("…kiểm tra kiến thức pháp luật về"). Đã rà toàn bộ `app/` (127 chỗ cắt chuỗi `[:N]`, `max_chars`, `_truncate`) và `frontend/src`, rồi đếm trên DB (`wiki_pages`, `legal_relations`, `sources`) xem thực tế bao nhiêu bản ghi bị mất chữ.

**Cập nhật 2026-10-18:** đã sửa mục 1–5 và chạy lại dữ liệu, xem [Kết quả sửa đợt 1–3](#kết-quả-sửa-đợt-13-mục-15). Mục 6–9 chưa sửa.

## Tóm tắt

| # | Chỗ cắt | Ảnh hưởng thực tế (DB) | Mức |
|---|---|---|---|
| 1 | Tóm tắt trang Điều: đoạn đầu cắt cứng 180 ký tự | **659 / 1499** trang Điều, mất TB 135 ký tự/trang | Cao |
| 2 | Tiêu đề Điều lấy cả câu nội dung khi Điều không có tên | 98 trang có tiêu đề > 150 ký tự | Trung bình |
| 3 | `quote_context` quan hệ pháp lý cắt 250 ký tự **đầu dòng** | **211 / 588** quan hệ chạm giới hạn | Cao |
| 4 | Tóm tắt trang MRP cắt 300 ký tự | 115 trang dừng giữa chữ | Trung bình |
| 5 | Tóm tắt trang tổng quan / nguyên văn cắt 280 | 4 trang dừng giữa câu | Thấp |
| 6 | Trích yếu (`official_title`) cắt 250 | 2 văn bản | Thấp |
| 7 | Kết quả `search` cho chatbot: ưu tiên tóm tắt thay vì đoạn khớp, cắt 300/200 | Mọi lượt tìm kiếm | Trung bình |
| 8 | Sinh câu hỏi tìm kiếm chỉ cho 15 Điều/đoạn đầu mỗi văn bản | Văn bản > 15 Điều | Trung bình |
| 9 | Rerank dùng 1500 ký tự đầu trang khi trang không có chunk | Trang chưa có chunk | Thấp |

Phần cuối liệt kê các chỗ cắt đã xem và **không cần sửa**.

---

## 1. Tóm tắt trang Điều — cắt cứng 180 ký tự (lỗi trong ảnh)

`app/services/legal_service.py:645-654`

```python
page_summary = f"Điều {art_num}" + (f": {art_title}" if art_title else "")
if first_para:
    page_summary += f" — {first_para[:180]}"
```

- Chỉ lấy **dòng** đầu tiên của thân Điều rồi cắt ở ký tự 180, không theo ranh giới từ/câu, không có dấu "…" → người đọc không biết là bị cắt.
- Dòng đầu bắt đầu bằng gạch đầu dòng thì ra "— - Quyết định số 97/…" (lặp dấu gạch).
- Ví dụ: `dieu-1-216-2026-nd-cp` mất đoạn "…lịch tư pháp để xây dựng cơ sở dữ liệu lý lịch tư pháp, lập lý lịch tư pháp, cậ…".
- Tóm tắt được hiển thị ở ô **Tóm tắt**, trong kết quả `search`/`list_wiki_pages` của chatbot, và được đưa vào vector nhúng của trang (`page_indexing.py:44`).

**Đề xuất**
- Viết một hàm chung `clip_text(text, limit)`: gộp các dòng đầu của thân Điều, cắt ở cuối câu gần nhất (`.`, `;`, `:`) trong giới hạn, nếu không có thì cắt ở ranh giới từ, thêm "…" khi có cắt. Bỏ ký tự gạch đầu dòng ở đầu.
- Nâng giới hạn lên khoảng 400 ký tự (ô Tóm tắt đủ chỗ, xem ảnh).
- Chạy lại tóm tắt cho các trang Điều **chưa được sửa tay** bằng script (không gọi LLM, không đổi nội dung trang); nhúng lại vector trang nếu muốn tóm tắt mới tác động đến tìm kiếm.

## 2. Tiêu đề Điều là cả câu nội dung

`app/services/legal_service.py` — `split_legal_text_by_articles` coi phần sau "Điều N." trên cùng dòng là tên Điều.

- Với Quyết định, Điều thường không có tên: "Điều 2. Quyết định này có hiệu lực thi hành kể từ ngày ký. Quyết định này bãi bỏ và thay thế:" → thành `art_title`, nên tiêu đề trang và tóm tắt đều chứa câu dài này (đúng như ảnh).
- 98 trang có phần tiêu đề trong tóm tắt > 150 ký tự.

**Đề xuất:** nếu "tên" dài hơn ~120 ký tự hoặc chứa dấu chấm câu giữa chừng / kết thúc bằng ":" thì coi đó là thân Điều, để `art_title = None` (tiêu đề trang là "Điều 2 - <văn bản>"). Đổi tiêu đề không đổi slug, nên không vỡ liên kết.

## 3. Trích dẫn quan hệ pháp lý (`quote_context`) — có thể mất chính văn bản được dẫn

`app/services/legal_relation_extractor.py:135, 152, 171, 196, 223, 261` — `quote_context=line_str[:250]`

- Lấy 250 ký tự **đầu dòng**, không phải đoạn quanh chỗ khớp. Với dòng dài (thường gặp ở "bãi bỏ… Quyết định số…"), số hiệu văn bản được dẫn có thể nằm sau ký tự 250 → trích dẫn không chứa chính căn cứ của quan hệ.
- **211 / 588** quan hệ đang chạm đúng 250 ký tự.
- Sau đó còn bị cắt thêm khi hiển thị:
  - `legal_service.py:968` — trang tổng quan: 150 ký tự, **luôn** thêm "...";
  - `retrieval_service.py:174` — context đồ thị cho chatbot: 180 ký tự, **luôn** thêm "..." kể cả khi trích dẫn ngắn;
  - `mcp/tools.py:522` — 300 ký tự;
  - `frontend/src/components/law/law-schema-tab.tsx:63` — `line-clamp-2` (chỉ hiển thị, có thể giữ).

**Đề xuất**
- Lưu cửa sổ quanh chỗ khớp (ví dụ 200 ký tự trước, 300 sau, cắt theo ranh giới từ, "…" ở đầu/cuối khi có cắt), tối đa ~600 ký tự.
- Bỏ các lần cắt thứ hai (150/180) hoặc dùng cùng `clip_text`, chỉ thêm "…" khi thật sự cắt.
- Chạy lại `relink_legal_relations` cho các văn bản hiện có (regex, không gọi LLM).

## 4. Tóm tắt trang MRP — cắt 300 ký tự

`app/ai/mrp/writer.py:276` (`make_summary`) và `writer.py:401` (tóm tắt LLM trả về)

- Cả tóm tắt LLM viết cũng bị cắt cứng ở 300, không theo từ/câu. **115** trang có tóm tắt dài đúng 300 và dừng giữa chữ (ví dụ `luat-ly-lich-tu-phap-2025`: "…về việc xây dựng, quản lý và ").

**Đề xuất:** dùng `clip_text(…, 300)`; trong prompt của writer nói rõ tóm tắt ≤ 300 ký tự. Sửa dữ liệu cũ: script cắt lại về ranh giới câu/từ + "…" (không cần LLM).

## 5. Tóm tắt trang tổng quan / nguyên văn — cắt 280

- `legal_service.py:602` — `preamble[:280]` khi văn bản không có trích yếu.
- `verbatim_page_service.py:92` — dòng đầu `[:280]`.
- 4 trang dừng giữa câu. **Đề xuất:** dùng `clip_text`.

## 6. Trích yếu văn bản — cắt 250

`legal_service.py:234-238` — khối tiêu đề trước "Căn cứ" bị cắt ở 250 ký tự (có "…" theo ranh giới từ).

- 2 văn bản bị cắt: `b1372cdc` ("…được sửa đổi, bổ…"), `812cfc24` ("…ngày 28 tháng 12 năm 2021 của…") — mất phần cơ quan sửa đổi.
- **Đề xuất:** nâng lên 500 (khối đã tự dừng ở "Căn cứ"); hai văn bản này sửa tay được trong phần Thông tin văn bản (`official_title` là trường sửa được).

## 7. Kết quả tìm kiếm trả cho chatbot (MCP `search`)

`app/mcp/tools.py:426-429` (`_summary_of`), `:456`, `:1157`

- Với kết quả wiki, công cụ hiện **tóm tắt trang** (đã bị cắt ở mục 1/4) thay vì đoạn chunk khớp truy vấn (`chunk_text`), rồi cắt thêm ở 300. Kết quả nguyên văn chỉ hiện 200 ký tự.
- Không mất dữ liệu (chatbot vẫn gọi `read_wiki_page` để đọc đủ), nhưng chatbot quyết định có đọc trang hay không dựa trên đoạn này, nên dễ bỏ sót hoặc phải gọi thêm công cụ.

**Đề xuất:** hiện đoạn khớp (`chunk_text`) khoảng 600–800 ký tự cắt theo từ, kèm tóm tắt một dòng; kết quả nguyên văn lên ~500 ký tự. Cân nhắc độ dài context của model qwen-3.5-9b khi chọn con số.

## 8. Câu hỏi tìm kiếm chỉ sinh cho 15 Điều đầu

`app/tasks/retrieval_tasks.py:266` — `max_provisions: int = 15`, áp dụng cả cho `LegalUnit` (`.limit(max_provisions)`, dòng 297) và chunk nguyên văn (dòng 320).

- Văn bản dài (ví dụ Luật nhiều chục Điều) chỉ có câu hỏi gợi ý cho 15 Điều đầu; các Điều sau không được hưởng phần tìm kiếm theo câu hỏi.
- **Đề xuất:** bỏ giới hạn hoặc nâng lên (ví dụ 200) với chi phí 1 lượt LLM mỗi Điều; hoặc chọn Điều theo độ dài thay vì thứ tự tạo.

## 9. Rerank khi trang không có chunk

`app/services/retrieval_service.py:352` — `chunk_text = body[:1500]`

- Chỉ xảy ra khi trang chưa có chunk (chunk index lỗi). Nội dung sau 1500 ký tự không được rerank xét tới.
- **Đề xuất:** giữ nguyên, nhưng theo dõi các trang thiếu chunk và nhúng lại các trang đó.

---

## Đã xem, không cần sửa

| Chỗ | Lý do |
|---|---|
| `page_indexing.py:44` (4000), `embedding_storage.py:45` (8000), `milvus_service.py:108` (12000) | Giới hạn đầu vào vector nhúng trang/Milvus. Toàn bộ nội dung vẫn được nhúng theo chunk; nội dung đọc từ Postgres, không từ Milvus |
| `verbatim_page_service.py` (`verbatim_page_max_chars` 40000) | Chia thành nhiều trang "Phần i", không bỏ chữ |
| `mcp/tools.py` `WIKI_CONTENT_MAX_CHARS` | Từ chối ghi trang > 50.000 ký tự (báo lỗi), không cắt im lặng; `read_wiki_page` trả đủ nội dung |
| `mcp/tools.py:740` `_truncate` (skill 60000) | Có ghi chú "(truncated: N more characters)" |
| `doc_metadata_service.py:181` (5000), `legal_service.py:87/148/173` (4000/30000) | Chỉ để trích số hiệu/ngày/cơ quan từ phần đầu văn bản |
| `mrp/reducer.py`, `mrp/verifier.py`, `ai_review/*`, `question_generator.py` | Giới hạn đầu vào LLM nội bộ, không lưu ra dữ liệu. Lưu ý: AI review chỉ xét 8000 ký tự đầu trang |
| `ocr_service.py:142` | Chỉ cắt vòng lặp lặp chữ ở cuối trang OCR; trang bị `finish_reason=length` được gắn cờ "truncated" |
| Thông báo lỗi/tiến độ (`[:200]`), audit, notification, tên, slug, tag | Trường hiển thị/kỹ thuật, có giới hạn cột |
| Frontend `line-clamp` ở danh sách | Chỉ hiển thị, bấm vào xem đủ; ô Tóm tắt của trang hiển thị đủ chuỗi |

**Chưa rà:** phía chatbot (`chatbot_v065`, Open WebUI) — cách nó cắt kết quả công cụ MCP trước khi đưa vào prompt.

## Thứ tự sửa đề xuất

1. Hàm `clip_text` dùng chung + sửa mục 1, 4, 5 + script chạy lại tóm tắt (bỏ qua trang đã sửa tay).
2. Mục 2 (tên Điều) — làm cùng đợt 1 vì cùng chạy lại trang Điều.
3. Mục 3 (`quote_context`) + `relink_legal_relations`.
4. Mục 7, 8 — cần thống nhất con số theo context của model và chi phí LLM.

---

## Kết quả sửa đợt 1–3 (mục 1–5)

### Code

- `app/utils/text.py`: thêm `clip_text(text, limit)` (gộp khoảng trắng, ưu tiên cắt ở cuối câu/mệnh đề, không cắt giữa chữ, luôn thêm "…" khi có cắt) và `clip_around(text, start, end)` (lấy đoạn quanh vị trí khớp, "…" ở phía bị cắt).
- **Mục 1** — `legal_service.article_summary()`: tóm tắt Điều = `Điều N[: tên] — <tên/câu đầu + các dòng nội dung>`, tối đa 400 ký tự qua `clip_text`; bỏ dòng trích dẫn `>`, dòng tiêu đề Điều, gạch đầu dòng thừa (hết lỗi "— -").
- **Mục 2** — `is_body_sentence()`: tên Điều là câu nội dung khi kết thúc bằng ":", có dấu chấm giữa câu ("… ngày ký. Quyết định này …"), hoặc dạng "<văn bản> này có/được/quy định/thay thế/bãi bỏ …". Khi đó tên Điều = rỗng, câu đó thành đoạn mở đầu (`lead`): tiêu đề trang `Điều N - <văn bản>`, mục lục `Điều N — <câu đầu, 100 ký tự>`. **Slug không đổi.** Tên Điều dài thật (vd. Điều 10, 14 Nghị định 136/2020, ~190–330 ký tự) vẫn giữ — không dùng độ dài làm tiêu chí.
- **Mục 3** — `legal_relation_extractor`: `quote_context` = đoạn quanh chỗ khớp (200 ký tự trước, 300 sau), với "thay thế/bãi bỏ/hết hiệu lực" thì kéo tới đúng số hiệu văn bản đích; Căn cứ = cả dòng, tối đa 500. Bỏ lần cắt thứ hai khi hiển thị (`legal_service` 150 → `clip_text` 300, `retrieval_service` 180 → 300, MCP `relations` 300 → 500), không còn "..." cứng.
- **Mục 4** — MRP `writer.py`: tóm tắt qua `clip_text(…, 300)`.
- **Mục 5** — tổng quan (`clip_text(preamble, 280)`), nguyên văn (`verbatim_page_service._summary`).
- Test: `tests/test_text_clipping.py` (8 test). Toàn bộ: 425 passed, 30 skipped.

### Chạy lại dữ liệu (không gọi LLM)

Script `python -m app.scripts.backfill_clip_text [apply]` (chạy trong container api, không có `apply` = chạy thử), bỏ qua trang có revision `editor_edit` / `rollback` / `draft_approved` (hiện chưa có trang nào) và bỏ qua 11 văn bản đang `queued` trong worker. Bản sao trước khi sửa: bảng `bak_clip_20261018_pages`, `bak_clip_20261018_units`, `bak_clip_20261018_rels`.

| Hạng mục | Đã cập nhật |
|---|---|
| Tóm tắt trang Điều | 934 + 98 trang Điều slug cũ (không còn liên kết legal unit) |
| Tiêu đề trang Điều (bỏ câu nội dung) | 10 trang, 10 legal unit (kèm `full_path` của khoản/điểm con) |
| Mục lục trang tổng quan | 2 trang |
| Tóm tắt MRP / nguyên văn dừng giữa chữ | 120 trang → cắt lùi về ranh giới chữ/câu + "…" (phần sau 300 ký tự đã mất từ lúc sinh, không khôi phục được) |
| `quote_context` | 126 quan hệ |
| Embedding trang (title + summary) | 1154 lượt embed lại |

| Chỉ số | Trước | Sau |
|---|---|---|
| Độ dài TB tóm tắt Điều | 205 | 288 |
| Tóm tắt Điều có "— -" | 7 | 2 (thuộc văn bản đang queued / trang mồ côi) |
| `quote_context` đúng 250 ký tự | 211 | 88 (đều thuộc 11 văn bản đang queued) |
| Tóm tắt 280/300 dừng giữa chữ | 118 | 2 (văn bản đang queued) |

### Còn lại

- ~~11 văn bản `queued` chạy bằng code cũ~~: worker đã restart (chiều 18/10) với code mới + LLM stream; `backfill_clip_text apply` chạy lại cho kết quả 0 thay đổi. Script đã thêm 2 chặn:
  - `skip_dup_slug`: văn bản có 2 "Điều N" trùng số (điều được trích trong luật sửa đổi) thì bỏ qua, không ghép tên điều này với thân điều kia.
  - `skip_mismatch` (15 trang): trang mang slug của Điều nhưng nội dung không chứa tên Điều đó (vd. `dieu-3-36-2024-qh15` đang giữ Điều 3 được trích "Đấu giá biển số xe") thì giữ nguyên.
  - Quan hệ trùng khoá giữ `quote_context` hiện tại nếu vẫn có trong bản trích mới, nên chạy lại không đảo qua lại.
- 10 trang tạo trong lúc gateway embedding lỗi bị thiếu vector, đã embed lại (`index_wiki_page_chunks`), còn 0.
- 12 văn bản `error` do gateway LLM sập (10 có `[ai_unavailable]` để cron tự requeue; `776e833d`, `b95c9a51` lỗi "All N page(s) failed" không có marker nên phải requeue tay). Khi gateway sống lại thì requeue toàn bộ.
- Trang Điều slug cũ (vd. `dieu-4-nghi-dinh-94-ve-dao-tao-sat-hach-lai-xe` bên cạnh `…-4cbeb1ba`) là bản thừa từ lần đổi slug trước — nên xem xét xoá riêng.
