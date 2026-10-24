---
name: cahy-kn2-tom-tat
description: "KN2 - Tóm tắt tài liệu được quyền đọc thành JSON theo 03 mức: trích yếu, ngắn, chi tiết. Dùng null cho số văn bản, ngày, cơ quan không có trong chính tài liệu; mã tham chiếu chỉ là nội dung. Chỉ thêm qppl khi chính tài liệu là văn bản QPPL, không thêm vì tài liệu trích dẫn một luật. Triggers on: tóm tắt văn bản, viết trích yếu, tóm tắt ngắn, tóm tắt chi tiết, tóm tắt trình lãnh đạo, tom_tat."
allowed-tools: mcp__arkon__search_wiki mcp__arkon__read_wiki_page mcp__arkon__list_sources mcp__arkon__get_source mcp__arkon__get_source_outline mcp__arkon__get_source_pages mcp__arkon__search_source_content mcp__arkon__get_document_relations
---

# KN2 - Tóm tắt văn bản (`tom_tat`)

Tóm tắt tài liệu được quyền đọc, gồm văn bản hành chính, văn bản quy phạm pháp luật (QPPL)
và tài liệu thông thường, thành JSON. Tài liệu không có số hiệu, ngày hoặc cơ quan ban hành
vẫn được tóm tắt; không từ chối chỉ vì tài liệu không phải văn bản chính thức hoặc là dữ liệu kiểm thử.
Nguồn quy tắc: Guideline xây dựng dữ liệu 07 skill, mục 3 và mục 5 (R5.1-R5.16).

## Câu lệnh hệ thống (dùng nguyên văn)

```text
Bạn tóm tắt trung thực tài liệu được cấp để cán bộ rà soát. Trả đúng một đối tượng JSON theo schema của mức được yêu cầu, không lời dẫn. Tóm tắt tài liệu thường và dữ liệu kiểm thử là hợp lệ, không biến chúng thành văn bản hành chính hoặc văn bản pháp luật. Chỉ dùng dữ kiện trong nguồn gốc. Trường không có căn cứ phải là null hoặc danh sách rỗng đúng schema; trường qppl không áp dụng thì bỏ hẳn khóa đó.
```

## Quy tắc chung (bắt buộc)

1. Chỉ xử lý tài liệu mức "Thường". Thấy dấu "MẬT", "TỐI MẬT", "TUYỆT MẬT" thì dừng, báo cán bộ, không trích, không lưu.
2. Khử định danh trước khi xử lý bằng nhãn nhất quán: `[HO_TEN_n]`, `[CCCD_n]`, `[SO_DIEN_THOAI_n]`, `[BIEN_SO_n]`, `[DIA_CHI_n]`,
   `[TAI_KHOAN_n]`, `[EMAIL_n]`, `[TAI_KHOAN_MXH_n]`, `[NGAY_SINH_n]`, `[HO_CHIEU_n]`, `[TO_CHUC_n]`.
   Ba mức tóm tắt của cùng văn bản dùng chung bảng thay thế. Giữ tên tỉnh, xã, phường, cơ quan nhà nước, điều luật, chức vụ.
3. Chỉ chạy trên hạ tầng nội bộ; không đưa dữ liệu ra dịch vụ AI công cộng.
4. JSON: ngày ISO `YYYY-MM-DD`; không Markdown trong giá trị chuỗi. Kết quả là dự thảo để cán bộ rà soát.

## Chọn đúng trường trước khi viết JSON

1. **Số của chính văn bản:** chỉ chép giá trị nguồn xác định là số, ký hiệu văn bản của chính tài liệu
   (ví dụ trường `Số: 17/BC-ABC`). Không lấy mã đối chiếu, mã hồ sơ, mã kiểm thử, mã tra cứu, UUID,
   tên tệp hoặc số của văn bản được trích dẫn làm `so_ky_hieu`. Không có số văn bản → `"so_ky_hieu": null`.
   Mã tham chiếu vẫn phải giữ nguyên trong `y_chinh` hoặc nội dung tóm tắt, không đổi vai trò của mã.
2. **Ngày và cơ quan của chính văn bản:** chỉ lấy khi nguồn nêu; thiếu trường nào thì trường đó là `null`.
   Không suy ngày từ tên tệp, mã hồ sơ hay chữ số trong tiêu đề; không lấy cơ quan của một luật được viện dẫn.
3. **Có thêm `qppl` hay không:** xác định từ tiêu đề và số hiệu của chính tài liệu gốc.
   Báo cáo, ghi chú, hồ sơ, tài liệu kiểm thử không có `qppl`. Báo cáo có mục “Căn cứ” dẫn một Luật
   vẫn là báo cáo, không phải chính Luật đó. Với tài liệu thường hoặc chưa xác minh được loại văn bản,
   **bỏ hoàn toàn khóa `qppl`**, không ghi một giá trị rỗng hoặc một mục pháp luật điền “không có”.
4. Sau đó mới tóm tắt các sự kiện có trong nguồn. Không tạo thêm nhiệm vụ, thời hạn, giá trị pháp lý
   hoặc quy trình nghiệp vụ để lấp đầy biểu mẫu. Khi nguồn không giao nhiệm vụ/thời hạn, dùng `[]`.
   Ý chính chỉ nêu dữ kiện có trong nguồn, không biến các trường metadata còn thiếu thành các ý
   “không có ngày”, “không có cơ quan”, “không có phạm vi pháp luật”.

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
| `so_ky_hieu` | Số của chính văn bản ("901/KH-UBND"); chỉ có mã tham chiếu/hồ sơ thì dùng `null`, giữ mã trong nội dung |
| `ngay_ban_hanh` | ISO ("2026-09-25"); nguồn không nêu → `null`, không suy từ tên tệp hoặc mã đối chiếu |
| `co_quan_ban_hanh` | Tên đầy đủ như văn bản ("Ủy ban nhân dân tỉnh Hưng Yên"); nguồn không nêu → `null` |
| `trich_yeu` | 01 câu ≤ 40 từ; khi có cơ quan ban hành thì mở đầu bằng tên cơ quan; nếu không có, nêu trực tiếp nội dung tài liệu |
| `y_chinh` | 3-5 phần tử, mỗi ý 01-02 câu |
| `noi_dung_theo_phan` | Danh sách `{phan, noi_dung}`, giữ tên phần như văn bản ("I. Mục đích, yêu cầu") |
| `thoi_han` | Danh sách `{noi_dung, han, don_vi}`; không có → `[]` |
| `nhiem_vu_cong_an` | Nhiệm vụ giao Công an tỉnh, Công an cấp xã, lực lượng Công an; mỗi nhiệm vụ 01 phần tử, mở đầu bằng động từ ("Chủ trì…", "Phối hợp…"); không có → `[]` |
| `de_xuat_xu_ly` | 01 câu theo căn cứ trong nguồn; nếu không có căn cứ phân công thì ghi "Tài liệu không nêu đề xuất xử lý", không tự đặt đơn vị hoặc chỉ đạo mới |
| `qppl` | Chỉ có với chính văn bản QPPL đã xác minh; tài liệu thường/báo cáo chỉ dẫn luật phải bỏ khóa này |

Văn bản QPPL (R5.1-R5.3), xét **chính văn bản đang tóm tắt**, không xét các văn bản được trích dẫn:
`Luật`, `Nghị định`, `Thông tư` là QPPL khi đây là loại của chính tài liệu gốc; `Nghị quyết`, `Quyết định` là QPPL khi số, ký hiệu có năm
(`15/2026/QĐ-UBND`, `05/2026/NQ-HĐND`); `901/QĐ-UBND` là văn bản hành chính. Mức trích yếu không có `qppl`.
`ngay_hieu_luc` theo điều khoản thi hành ("có hiệu lực kể từ ngày ký" → ngày ký). `diem_moi` (ít nhất 01 phần tử) do cán bộ
pháp chế xác định khi so với văn bản bị thay thế; đầu vào chưa có thông tin này thì ghi 01 phần tử "(cán bộ pháp chế bổ sung)",
không tự suy ra.

## Quy tắc nội dung

- Luôn giữ các trường số, ký hiệu, ngày, cơ quan ban hành; có trong nguồn thì chép đúng,
  không có thì dùng `null`. Mã đối chiếu kiểm thử không tự trở thành số văn bản (R5.8).
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
- [ ] `so_ky_hieu` là số của chính văn bản, không phải mã tham chiếu hay số của văn bản được viện dẫn.
- [ ] Không có số/ngày/cơ quan trong nguồn thì giữ `null`; không sao chép dữ kiện từ các ví dụ bên dưới.
- [ ] Tài liệu thường hoặc báo cáo chỉ trích dẫn luật: không có khóa `qppl`.
- [ ] Độ dài đúng giới hạn (đếm theo âm tiết).
- [ ] Đủ mọi thời hạn và nhiệm vụ của Công an; thời hạn tương đối để `han: null`.
- [ ] Không nhận định, không đổi số liệu, không chữ viết tắt mới.

## Ví dụ đối chiếu vai trò trường — mức tóm tắt ngắn

Các nguồn sau đều là ví dụ giả lập để minh họa cấu trúc. Không dùng dữ kiện của ví dụ cho tài liệu khác.
Mức trích yếu/chi tiết vẫn theo schema riêng; không chép thêm trường của mức ngắn vào mức khác.

### Chính tài liệu là QPPL: được thêm `qppl`

Nguồn giả lập: “THÔNG TƯ. Số: 03/2099/TT-XX. Ngày ban hành: 2099-01-05.
Cơ quan ban hành: Cơ quan X. Phạm vi điều chỉnh: quy trình thử nghiệm.
Đối tượng áp dụng: nhóm A. Có hiệu lực từ ngày 2099-02-01.”

```json
{"so_ky_hieu":"03/2099/TT-XX","ngay_ban_hanh":"2099-01-05","co_quan_ban_hanh":"Cơ quan X","trich_yeu":"Cơ quan X ban hành thông tư về quy trình thử nghiệm áp dụng cho nhóm A.","y_chinh":["Văn bản quy định quy trình thử nghiệm.","Đối tượng áp dụng là nhóm A.","Văn bản có hiệu lực từ ngày 2099-02-01."],"thoi_han":[],"nhiem_vu_cong_an":[],"de_xuat_xu_ly":"Tài liệu không nêu đề xuất xử lý","qppl":{"pham_vi_dieu_chinh":"Quy trình thử nghiệm","doi_tuong_ap_dung":"Nhóm A","diem_moi":["(cán bộ pháp chế bổ sung)"],"ngay_hieu_luc":"2099-02-01","van_ban_bi_thay_the":[]}}
```

### Báo cáo có trích luật: giữ số báo cáo, không thêm `qppl`

Nguồn giả lập: “BÁO CÁO. Số: 24/BC-ABC. Ngày ban hành: 2026-01-12.
Cơ quan ban hành: Đơn vị B. Căn cứ Luật số 99/2099/QH99 (số hiệu ví dụ giả lập).
Đã tiếp nhận 10 hồ sơ, giải quyết 7 hồ sơ, còn 3 hồ sơ.”

```json
{"so_ky_hieu":"24/BC-ABC","ngay_ban_hanh":"2026-01-12","co_quan_ban_hanh":"Đơn vị B","trich_yeu":"Đơn vị B báo cáo tình hình tiếp nhận và giải quyết hồ sơ.","y_chinh":["Đã tiếp nhận 10 hồ sơ.","Đã giải quyết 7 hồ sơ.","Còn 3 hồ sơ."],"thoi_han":[],"nhiem_vu_cong_an":[],"de_xuat_xu_ly":"Tài liệu không nêu đề xuất xử lý"}
```

### Ghi chú chỉ có mã đối chiếu: số văn bản là `null`, không thêm `qppl`

Nguồn giả lập gồm ba dòng: “NGHIỆM THU ĐỒNG BỘ.
Đây là dữ liệu kiểm thử giả lập, không phải tài liệu nghiệp vụ.
Mã đối chiếu: CASE-714.”

```json
{"so_ky_hieu":null,"ngay_ban_hanh":null,"co_quan_ban_hanh":null,"trich_yeu":"Tài liệu nghiệm thu đồng bộ sử dụng dữ liệu kiểm thử giả lập.","y_chinh":["Tài liệu có tiêu đề NGHIỆM THU ĐỒNG BỘ.","Đây là dữ liệu kiểm thử giả lập, không phải tài liệu nghiệp vụ.","Mã đối chiếu là CASE-714."],"thoi_han":[],"nhiem_vu_cong_an":[],"de_xuat_xu_ly":"Tài liệu không nêu đề xuất xử lý"}
```

Chỉ chép số, ngày, cơ quan và nhánh `qppl` từ **nguồn đang xử lý**. Nguồn không có số văn bản
thì `so_ky_hieu` phải là `null`, kể cả khi nguồn có mã đối chiếu dài hoặc có chữ số.

Với **tóm tắt ngắn của tài liệu thường**, JSON chỉ có đúng tám khóa:
`so_ky_hieu`, `ngay_ban_hanh`, `co_quan_ban_hanh`, `trich_yeu`, `y_chinh`,
`thoi_han`, `nhiem_vu_cong_an`, `de_xuat_xu_ly`.
`y_chinh` có từ 3 đến 5 phần tử, chỉ giữ sự kiện nguồn nêu; không thêm một ý để giải thích việc bỏ trường pháp luật.

## Tham chiếu

- `references/s2_tom_tat.schema.json`: lược đồ 03 mức (`oneOf`).
