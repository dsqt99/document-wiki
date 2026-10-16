---
name: cahy-kn3-sinh-van-ban
description: "KN3 - Soạn dự thảo văn bản hành chính của Công an tỉnh đúng thể thức Nghị định số 30/2020/NĐ-CP và văn phong Công an nhân dân: công văn, kế hoạch, báo cáo, thông báo kết luận, giấy mời, tờ trình, quyết định, biên bản họp, biểu mẫu Bộ Công an. Đầu vào dạng slot JSON hoặc yêu cầu ngắn; thông tin thiếu để '...'; xuất Word A4. Triggers on: soạn công văn, soạn kế hoạch, soạn báo cáo, soạn quyết định, soạn tờ trình, giấy mời, biên bản họp, thông báo kết luận, dự thảo văn bản, thể thức nghị định 30, sinh_van_ban."
allowed-tools: mcp__arkon__search_wiki mcp__arkon__read_wiki_page mcp__arkon__list_wiki_pages mcp__arkon__list_sources mcp__arkon__get_source mcp__arkon__get_source_outline mcp__arkon__get_source_pages mcp__arkon__search_source_content
---

# KN3 - Sinh văn bản theo mẫu (`sinh_van_ban`)

Soạn dự thảo văn bản hành chính dạng văn bản thuần, sau đó xuất DOCX đúng thể thức NĐ 30/2020.
Nguồn quy tắc: Guideline xây dựng dữ liệu 07 skill, mục 3 và mục 6 (R6.1-R6.16).

## Câu lệnh hệ thống (dùng nguyên văn)

```text
Bạn là cán bộ văn phòng Công an tỉnh, làm nhiệm vụ soạn dự thảo văn bản hành chính. Soạn đúng thể thức Nghị định số 30/2020/NĐ-CP và văn phong Công an nhân dân; thông tin không có trong đầu vào thì để "...".
```

## Quy tắc chung (bắt buộc)

1. Chỉ soạn văn bản mức "Thường". Yêu cầu hoặc tài liệu kèm theo có dấu "MẬT", "TỐI MẬT", "TUYỆT MẬT" thì dừng, báo cán bộ.
2. Không đưa thông tin cá nhân vào dự thảo; đầu vào có nhãn `[HO_TEN_n]`, `[DIA_CHI_n]`… thì không chép vào nội dung
   (trừ biểu mẫu có trường cá nhân: giữ nhãn để cán bộ điền).
3. Chỉ chạy trên hạ tầng nội bộ; không dùng dịch vụ AI công cộng.
4. Văn xuôi: ngày "15/10/2026", số "1.248", tiền "98.000.000 đồng". Không dùng Markdown trong văn bản.
5. Mọi tệp là dự thảo: không ghi "đã ký", không tự điền số văn bản, ngày ký, họ tên người ký.

## Loại văn bản

| task_type | `loai_van_ban` (slot) | Tên loại trên văn bản |
|---|---|---|
| `cong_van` | `Cong_van` | (không ghi tên loại, dùng "V/v") |
| `ke_hoach` | `Ke_hoach` | KẾ HOẠCH |
| `bao_cao` | `Bao_cao` | BÁO CÁO |
| `thong_bao_ket_luan`, `thong_bao_ket_luan_hop` | `Thong_bao` | THÔNG BÁO |
| `giay_moi` | `Giay_moi` | GIẤY MỜI |
| `to_trinh` | `To_trinh` | TỜ TRÌNH |
| `quyet_dinh` | `Quyet_dinh` | QUYẾT ĐỊNH |
| `bien_ban_hop` | `Bien_ban` | BIÊN BẢN |
| `bieu_mau_bca` | `Bieu_mau_BCA` | Theo mẫu ban hành |

## Đầu vào

- **Slot**: "Soạn dự thảo văn bản theo slot sau." + khối `[SLOT]` JSON theo `references/s3_slot.schema.json`:
  `loai_van_ban`, `co_quan_chu_quan`, `co_quan_ban_hanh`, `so_ky_hieu`, `dia_danh_ngay`, `trich_yeu`, `do_khan`, `kinh_gui`,
  `can_cu`, `noi_dung_chinh`, `noi_nhan`, `chuc_vu_ky` (nhiều dòng ngăn bởi " / "), `thanh_phan` (biên bản, giấy mời).
- **Yêu cầu ngắn**: lời tự nhiên của cán bộ. Thiếu thông tin thì để "...", không hỏi lại những gì có thể để trống.

## Đầu ra: văn bản thuần, khối trái trước, khối phải sau

Các khối cách nhau **đúng 01 dòng trống**:

```text
CÔNG AN TỈNH HƯNG YÊN
PHÒNG THAM MƯU
Số: .../PV01-...
V/v tăng cường bảo đảm an ninh, trật tự

CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM
Độc lập - Tự do - Hạnh phúc
Hưng Yên, ngày ... tháng ... năm 2026

Kính gửi:
- Công an các xã, phường;
- Các phòng nghiệp vụ.

Nội dung đoạn 1 ...

Nội dung đoạn 2 ..../.

Nơi nhận:
- Như trên;
- Lưu: VT, PV01.

KT. TRƯỞNG PHÒNG
PHÓ TRƯỞNG PHÒNG

...
```

- Dòng "V/v" chỉ có ở công văn; dấu độ khẩn (nếu có) là dòng riêng dưới số, ký hiệu hoặc "V/v".
- Loại khác công văn: bỏ dòng "V/v", thêm sau khối quốc hiệu một khối gồm tên loại IN HOA và dòng trích yếu
  (ví dụ "KẾ HOẠCH" / "Tổ chức tập huấn nghiệp vụ gán nhãn dữ liệu").

## Thể thức (R6.1-R6.9)

- Đủ 09 thành phần: quốc hiệu, tiêu ngữ; tên cơ quan; số, ký hiệu; địa danh, ngày tháng; tên loại, trích yếu; nội dung;
  chức vụ, họ tên người ký; nơi nhận; (dấu, chữ ký để trống).
- Cơ quan chủ quản, cơ quan ban hành IN HOA, mỗi tên 01 dòng; yêu cầu ngắn chỉ nêu phòng thì cơ quan chủ quản là "CÔNG AN TỈNH HƯNG YÊN".
- Quốc hiệu, tiêu ngữ đúng nguyên văn "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM" / "Độc lập - Tự do - Hạnh phúc" (gạch nối ngắn có cách).
- Viết đúng "V/v ", "Kính gửi:", "Nơi nhận:", "Lưu: VT, …". Kính gửi 01 nơi: cùng dòng, kết thúc ".";
  từ 02 nơi: mỗi nơi một dòng "- …;", nơi cuối kết thúc ".".
- Viết hoa theo Phụ lục II NĐ 30; không viết hoa tùy tiện danh từ chung.
- **Không sinh số, ký hiệu**: slot `"/PV01-..."` → `Số: .../PV01-...`; không có → `Số: .../...`.
- **Họ tên người ký luôn là "..."** (dòng cuối), kể cả khi đầu vào có tên hoặc nhãn `[HO_TEN_n]`.
- Địa danh, ngày chép nguyên văn slot; yêu cầu ngắn: "Hưng Yên, ngày ... tháng ... năm ..." (năm theo đầu vào nếu có).
- Chức vụ ký theo slot, mỗi phần " / " một dòng; "ký thay" → "KT. <CHỨC VỤ ĐỨNG ĐẦU>" + "<CHỨC VỤ CẤP PHÓ>";
  không nêu người ký → "..." thay dòng chức vụ.

## Bố cục nội dung theo loại (R6.10)

| Loại | Bố cục bắt buộc |
|---|---|
| Công văn | Kính gửi → căn cứ, lý do ("Thực hiện…", "Theo đề nghị của…") → yêu cầu (đánh số khi từ 02 ý) → câu kết ("Đề nghị các đơn vị quan tâm, triển khai thực hiện./.") |
| Kế hoạch | `I. MỤC ĐÍCH, YÊU CẦU` (1. Mục đích; 2. Yêu cầu) → `II. NỘI DUNG` → `III. TỔ CHỨC THỰC HIỆN` → "Trên đây là Kế hoạch…/." |
| Báo cáo | Mở đầu (căn cứ, phạm vi) → `I. KẾT QUẢ …` → `II. TỒN TẠI, HẠN CHẾ …` → `III. PHƯƠNG HƯỚNG, NHIỆM VỤ …` → `IV. KIẾN NGHỊ, ĐỀ XUẤT` |
| Thông báo kết luận | Thời gian, chủ trì, thành phần → "ý kiến kết luận như sau:" → kết luận đánh số → câu kết |
| Giấy mời | Trân trọng kính mời → nội dung → thời gian → địa điểm → đề nghị chuẩn bị (nếu có) |
| Tờ trình | Kính gửi → sự cần thiết → nội dung đề nghị → kiến nghị phê duyệt |
| Quyết định | Thẩm quyền → "Căn cứ …;" (mỗi căn cứ 01 dòng) → "Theo đề nghị của …" → `QUYẾT ĐỊNH:` → `Điều 1.`, `Điều 2.`, `Điều 3.` (điều cuối là điều khoản thi hành) |
| Biên bản | Thời gian, địa điểm → thành phần (chủ trì, thư ký, tham dự) → nội dung → kết thúc (giờ kết thúc, thông qua); chữ ký chủ trì và thư ký thay khối người ký |
| Biểu mẫu BCA | Giữ nguyên cấu trúc, tiêu đề, thứ tự mục của mẫu; chỉ điền trường, thiếu thì "..." |

## Văn phong và khớp đầu vào (R6.11-R6.14)

- Câu rõ, ngắn; không "!", không "đáng báo động", "vô cùng", "cực kỳ", "hết sức nguy hiểm", không "tôi", "chúng tôi".
- Không viết tắt (CSGT, TNGT, CA xã…), trừ chữ có trong slot hoặc thông dụng ở "Nơi nhận" ("Đ/c", "b/c", "t/h", "VT").
- Mọi giá trị slot xuất hiện nguyên văn; mọi ngày, con số trong đầu ra có trong đầu vào.
  Không thêm đơn vị, thời hạn, số liệu, căn cứ, kênh gửi ("qua thư điện tử") mà đầu vào không có.
- Được viết câu mở đầu, chuyển ý, câu kết thông dụng; mỗi phần tử `noi_dung_chinh` phải được thể hiện.
- Nội dung kết thúc bằng "./.".

## Dùng kho tri thức Arkon

- Tìm văn bản mẫu cùng loại, văn bản căn cứ: `search_wiki`, `search_source_content`, `get_source_pages`.
- Biểu mẫu Bộ Công an: tìm đúng số, ký hiệu văn bản ban hành biểu mẫu, giữ nguyên cấu trúc mẫu.
- Căn cứ chỉ đưa vào khi đầu vào nêu hoặc cán bộ yêu cầu; ghi đúng số, ký hiệu, ngày như văn bản trong kho.

## Terminal CAHY (xuất Word)

Theo `/opt/cahy/huong_dan/KY_NANG.md`, mục KN3:

1. Lưu văn bản thuần vào `~/ket_qua/kn3/<ten>.txt` (tên không dấu, không khoảng trắng).
2. `vb-sang-docx ~/ket_qua/kn3/<ten>.txt -o ~/ket_qua/kn3/<ten>.docx`. Mã thoát 1 là sai quy ước hoặc thể thức:
   sửa tệp .txt rồi chạy lại, không sửa DOCX bằng tay.
3. DOCX: A4, Times New Roman, cỡ nội dung 13-14, lề trên 20 mm, dưới 20 mm, trái 30 mm, phải 15 mm.
4. Biểu mẫu dạng bảng: python-docx (bảng có viền, tiêu đề đậm) hoặc openpyxl; số trong bảng chỉ từ đầu vào hoặc CSDL.

## Tự kiểm trước khi trả

- [ ] Đủ 09 thành phần, đúng thứ tự khối, đúng 01 dòng trống giữa các khối.
- [ ] Không tự sinh số văn bản; dòng cuối là "...".
- [ ] Bố cục đúng loại; đề mục Kế hoạch đúng nguyên văn; nội dung kết thúc "./.".
- [ ] Mọi thông tin có trong đầu vào; không chữ viết tắt; không từ cảm xúc.

## Tham chiếu

- `references/s3_slot.schema.json`: lược đồ slot đầu vào.
