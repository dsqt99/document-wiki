# CAHY Kho tri thức (nhánh c2)

Nhánh `c2` là bản viết lại kho tri thức CAHY theo **phương án 2**: giữ nguyên stack hiện tại (Python/FastAPI + Next.js) nhưng không còn chứa mã Arkon. Mục tiêu là phát hành theo Apache 2.0.

- Nhánh mồ côi (orphan): không mang lịch sử commit của Arkon.
- Chỉ chứa (1) file nhóm tự viết, chuyển từ `document-wiki`, và (2) code viết mới theo đặc tả (clean-room).

| Tài liệu | Nội dung |
|---|---|
| [docs/c2/CHECKLIST_THUC_HIEN.md](docs/c2/CHECKLIST_THUC_HIEN.md) | Checklist thực hiện chi tiết theo từng mảng tính năng |
| [docs/c2/NGUON_GOC.csv](docs/c2/NGUON_GOC.csv) | Nguồn gốc từng file đã chuyển sang (commit nguồn, tỷ lệ trùng, phụ thuộc còn thiếu) |
| [NOTICE](NOTICE) | Thông báo bản quyền và nguồn gốc |

## Hiện trạng

Hiện kho mới có các module đã chuyển sang. Rất nhiều module vẫn còn import `app.config`, `app.database.models`, … là những module chưa viết lại, nên **chưa chạy được ứng dụng**. Chạy thử các module độc lập:

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m pytest
```

### Kết quả chạy thử (2026-10-16, Python 3.13, Windows)

**86 test xanh trên 12 file.** Các test còn lại không phải lỗi logic: chúng chỉ thiếu module nền chưa viết lại (mục 2 của checklist).

| Trạng thái | File test |
|---|---|
| Xanh toàn bộ | `test_upload_guard` (34), `test_citation_verifier` (6), `test_vi_tokenizer` (4), `test_legal_hierarchy_parser` (4), `test_text_normalizer` (3), `test_excel_parser` (3), `test_docx_parser` (2) |
| Xanh một phần | `test_wiki_write_guard` 12/21 (cần `app.ai.mrp.*`, `wiki_service`), `test_security_label` 8/16 (cần `app.database`, `mcp_auth_service`), `test_table_query` 4/5, `test_pdf_parser` 3/5, `test_libreoffice_converter` 3/4 (cần `app.config`, `kb_service`) |
| Bỏ qua | `test_audit_chain` (26), `test_source_status_pg` (3): cần Postgres |
| Lỗi khi nạp | ~40 file còn lại. Lý do chủ yếu là thiếu `app.config`, `app.database`, `app.ai.embedding_catalog`, `app.ai.providers`, `app.worker`, `app.routers.sources`, `app.services.image_service`, `kb_service`, `wiki_service`, `fastmcp` |

## Quy tắc đóng góp (bắt buộc)

1. Không mở, không chép code từ `document-wiki` hay từ Arkon trong lúc code trên nhánh này. Chỉ làm việc từ đặc tả trong `docs/c2/dac_ta/`.
2. Mỗi PR phải ghi vào nhật ký clean-room (`docs/c2/NHAT_KY_CLEAN_ROOM.md`).
3. Trước khi merge, chạy kiểm tra trùng mã (mục 10 của checklist).
