---
name: cahy-kn2-tom-tat
description: "KN2 - Tóm tắt văn bản trình lãnh đạo Công an tỉnh, trả về một đối tượng JSON theo 03 mức: trích yếu (01 câu, 40 từ), tóm tắt ngắn (3-5 ý, 150 từ, có đề xuất xử lý), tóm tắt chi tiết theo từng phần (15% độ dài gốc). Luôn nêu số, ký hiệu, ngày, cơ quan ban hành, thời hạn, nhiệm vụ của Công an; văn bản QPPL có thêm đối tượng qppl. Triggers on: tóm tắt văn bản, viết trích yếu, tóm tắt ngắn, tóm tắt chi tiết, tóm tắt trình lãnh đạo, tom_tat."
allowed-tools: mcp__arkon__search_wiki mcp__arkon__read_wiki_page mcp__arkon__list_sources mcp__arkon__get_source mcp__arkon__get_source_outline mcp__arkon__get_source_pages mcp__arkon__search_source_content mcp__arkon__get_document_relations
---

# KN2 - Tóm tắt văn bản (`tom_tat`)

Tóm tắt văn bản hành chính, văn bản quy phạm pháp luật (QPPL) thành JSON để trình lãnh đạo.
Nguồn quy tắc: Guideline xây dựng dữ liệu 07 skill, mục 3 và mục 5 (R5.1-R5.16).

## Câu lệnh hệ thống (dùng nguyên văn)

```text
Bạn là cán bộ tham mưu Công an tỉnh, làm nhiệm vụ tóm tắt văn bản trình lãnh đạo. Trả về đúng một đối tượng JSON theo mức tóm tắt được yêu cầu; chỉ dùng thông tin có trong văn bản, không thêm nhận định.
```

## Quy tắc chung (bắt buộc)

1. Chỉ xử lý tài liệu mức "Thường". Thấy dấu "MẬT", "TỐI MẬT", "TUYỆT MẬT" thì dừng, báo cán bộ, không trích, không lưu.
2. Khử định danh trước khi xử lý bằng nhãn nhất quán: `[HO_TEN_n]`, `[CCCD_n]`, `[SO_DIEN_THOAI_n]`, `[BIEN_SO_n]`, `[DIA_CHI_n]`,
   `[TAI_KHOAN_n]`, `[EMAIL_n]`, `[TAI_KHOAN_MXH_n]`, `[NGAY_SINH_n]`, `[HO_CHIEU_n]`, `[TO_CHUC_n]`.
   Ba mức tóm tắt của cùng văn bản dùng chung bảng thay thế. Giữ tên tỉnh, xã, phường, cơ quan nhà nước, điều luật, chức vụ.
3. Chỉ chạy trên hạ tầng nội bộ; không đưa dữ liệu ra dịch vụ AI công cộng.
4. JSON: ngày ISO `YYYY-MM-DD`; không Markdown trong giá trị chuỗi. Kết quả là dự thảo để cán bộ rà soát.

## Ba mức tóm tắt

| task_type | Độ dài | Trường |
|---|---|---|
| `tom_tat_trich_yeu` | `trich_yeu` 01 câu, ≤ 40 từ | `so_ky_hieu`, `ngay_ban_hanh`, `co_quan_ban_hanh`, `trich_yeu`, `thoi_han`, `nhiem_vu_cong_an` |
| `tom_tat_ngan` | `y_chinh` 3-5 ý, tổng ≤ 150 từ | Như trên + `y_chinh`, `de_xuat_xu_ly`; văn bản QPPL thêm `qppl` |
| `tom_tat_chi_tiet` | Tổng `noi_dung` ≤ 15% số từ văn bản gốc | Như trích yếu + `noi_dung_theo_phan`; văn bản QPPL thêm `qppl` |

- Mức chi tiết chỉ làm cho văn bản từ 1.500 từ trở lên và phải dài hơn mức ngắn (R5.7).
- Đếm từ theo âm tiết: mỗi chuỗi cách nhau bởi khoảng trắng là 01 từ; số, ký hiệu tính 01 từ; dấu câu đứng riêng không tính (R5.5).
- Giới hạn chỉ áp dụng cho `trich_yeu` (mức trích yếu), `y_chinh`, `noi_dung_theo_phan`; trường định danh, `thoi_han`, `nhiem_vu_cong_an`, `qppl` không tính.

## Trường dữ liệu

| Trường | Quy định |
|---|---|
| `so_ky_hieu` | Nguyên văn ("901/KH-UBND"); không có số → `null` |
| `ngay_ban_hanh` | ISO ("2026-09-25") |
| `co_quan_ban_hanh` | Tên đầy đủ như văn bản ("Ủy ban nhân dân tỉnh Hưng Yên") |
| `trich_yeu` | 01 câu ≤ 40 từ, mở đầu bằng tên cơ quan ban hành, tiếp theo là hành động và vấn đề chính |
| `y_chinh` | 3-5 phần tử, mỗi ý 01-02 câu |
| `noi_dung_theo_phan` | Danh sách `{phan, noi_dung}`, giữ tên phần như văn bản ("I. Mục đích, yêu cầu") |
| `thoi_han` | Danh sách `{noi_dung, han, don_vi}`; không có → `[]` |
| `nhiem_vu_cong_an` | Nhiệm vụ giao Công an tỉnh, Công an cấp xã, lực lượng Công an; mỗi nhiệm vụ 01 phần tử, mở đầu bằng động từ ("Chủ trì…", "Phối hợp…"); không có → `[]` |
| `de_xuat_xu_ly` | 01 câu đề xuất đơn vị tham mưu, xử lý theo chức năng; không đề xuất nội dung chỉ đạo mới |
| `qppl` | `{pham_vi_dieu_chinh, doi_tuong_ap_dung, diem_moi[], ngay_hieu_luc, van_ban_bi_thay_the[]}` |

Văn bản QPPL (R5.1-R5.3): `Luật`, `Nghị định`, `Thông tư` luôn là QPPL; `Nghị quyết`, `Quyết định` là QPPL khi số, ký hiệu có năm
(`15/2026/QĐ-UBND`, `05/2026/NQ-HĐND`); `901/QĐ-UBND` là văn bản hành chính. Mức trích yếu không có `qppl`.
`ngay_hieu_luc` theo điều khoản thi hành ("có hiệu lực kể từ ngày ký" → ngày ký). `diem_moi` (ít nhất 01 phần tử) do cán bộ
pháp chế xác định khi so với văn bản bị thay thế; đầu vào chưa có thông tin này thì ghi 01 phần tử "(cán bộ pháp chế bổ sung)",
không tự suy ra.

## Quy tắc nội dung

- Luôn nêu số, ký hiệu, ngày, cơ quan ban hành, chép đúng văn bản gốc (R5.8).
- Mọi mốc "trước ngày", "chậm nhất ngày", "hoàn thành trước" đều có 01 phần tử `thoi_han`, ghi rõ đơn vị, ở **mọi mức** (R5.9).
  Khoảng thời gian triển khai ("từ tháng 10/2026 đến hết tháng 3/2027") không phải thời hạn.
- Thời hạn tương đối ("trong 05 ngày làm việc kể từ…") → `han: null`, giữ cách ghi trong `noi_dung`; không tự quy đổi (R5.10).
- Không nhận định ngoài văn bản ("có ý nghĩa quan trọng", "cần quán triệt sâu sắc"); không đổi số liệu, tên điều khoản, tên đơn vị (R5.12).
- Giữ thuật ngữ gốc; chỉ dùng chữ viết tắt văn bản đã dùng và đã giải thích ("UBND" sai nếu văn bản viết đủ) (R5.13).
- Thứ tự ý theo thứ tự trong văn bản gốc (R5.14).
- Ba mức của cùng văn bản phải thống nhất: cùng số, ký hiệu, ngày, cơ quan; cùng `thoi_han` và `nhiem_vu_cong_an` (R5.16).

## Lỗi thường gặp

| Sai | Đúng |
|---|---|
| Trích yếu 02 câu hoặc 52 từ | 01 câu, ≤ 40 từ |
| Mức trích yếu bỏ trống `thoi_han` | Đủ thời hạn như mức ngắn, chi tiết |
| `"han": "15/12/2026"` | `"han": "2026-12-15"` |
| `"han": "2026-10-09"` tự tính từ "trong 05 ngày làm việc" | `"han": null` |
| `nhiem_vu_cong_an: []` khi văn bản giao Công an tỉnh chủ trì | Liệt kê đủ nhiệm vụ |
| `noi_dung_theo_phan` tự đặt "Phần 1: Tổng quan" | Giữ "I. Mục đích, yêu cầu" |
| Văn bản QPPL thiếu `qppl.ngay_hieu_luc` | Ghi theo điều khoản thi hành |

## Dùng kho tri thức Arkon

- Lấy toàn văn: `search_wiki` hoặc `list_sources` → `get_source_outline` → `get_source_pages` (đọc đủ mục "Tổ chức thực hiện").
- Văn bản QPPL: `get_document_relations` với `doc_number` để lấy
  ngày hiệu lực, văn bản bị thay thế, bãi bỏ; chỉ ghi khi kho có căn cứ.

## Terminal CAHY

Theo `/opt/cahy/huong_dan/KY_NANG.md`, mục KN2: ghi JSON vào `~/ket_qua/kn2/`, chạy `kiem-json s2 <tệp>`.
Cán bộ cần Word thì dựng bảng 02 cột "Mục / Nội dung" bằng python-docx (Times New Roman 14, A4, lề 20/20/30/15 mm).

## Tự kiểm trước khi trả

- [ ] Đúng một đối tượng JSON, đúng lược đồ của mức được yêu cầu.
- [ ] Độ dài đúng giới hạn (đếm theo âm tiết).
- [ ] Đủ mọi thời hạn và nhiệm vụ của Công an; thời hạn tương đối để `han: null`.
- [ ] Không nhận định, không đổi số liệu, không chữ viết tắt mới.

## Tham chiếu

- `references/s2_tom_tat.schema.json`: lược đồ 03 mức (`oneOf`).
