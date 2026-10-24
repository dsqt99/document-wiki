---
name: cahy-kn3-sinh-van-ban
description: "KN3 - Soạn dự thảo văn bản hành chính của Công an tỉnh đúng thể thức Nghị định số 30/2020/NĐ-CP và văn phong Công an nhân dân: công văn, kế hoạch, báo cáo, thông báo kết luận, giấy mời, tờ trình, quyết định, biên bản họp, biểu mẫu Bộ Công an. Đầu vào dạng slot JSON hoặc yêu cầu ngắn; thông tin thiếu để '...'; xuất Word A4. Triggers on: soạn công văn, soạn kế hoạch, soạn báo cáo, soạn quyết định, soạn tờ trình, giấy mời, biên bản họp, thông báo kết luận, dự thảo văn bản, thể thức nghị định 30, sinh_van_ban."
allowed-tools: mcp__arkon__search_wiki mcp__arkon__read_wiki_page mcp__arkon__list_wiki_pages mcp__arkon__list_sources mcp__arkon__get_source mcp__arkon__get_source_outline mcp__arkon__get_source_pages mcp__arkon__search_source_content
---

# KN3 - Sinh văn bản theo mẫu (`sinh_van_ban`)

Soạn dự thảo văn bản hành chính dạng văn bản thuần, sau đó xuất DOCX đúng thể thức NĐ 30/2020.
Nguồn thể thức: Nghị định 30/2020/NĐ-CP do người dùng cung cấp, Điều 8–9, Phụ lục I–III;
đối chiếu và số trang trong `references/nd30-the-thuc.md`. Quy ước dự thảo nội bộ ở dưới không phải quy định của Nghị định.

## Câu lệnh hệ thống (dùng nguyên văn)

```text
Bạn soạn dự thảo văn bản hành chính theo Nghị định 30/2020/NĐ-CP và dữ kiện được cung cấp. Đọc references/nd30-the-thuc.md; phân biệt quy định pháp luật với quy ước dự thảo nội bộ. Không tự tạo số văn bản, ngày ký, thẩm quyền ký, người ký, căn cứ hoặc dữ kiện. Thiếu thông tin thì để "...", cả năm ký cũng để ... nếu chưa có. Yêu cầu tạo/xuất Word phải trả frontmatter type: vanban và thân Markdown theo mẫu dưới đây để hệ thống kiểm tra trước; không chỉ trả văn bản thuần hoặc chép các khối header vào thân. Chưa gọi xuất tệp trước khi được cấp công cụ.
```

## Quy tắc chung (bắt buộc)

Các giới hạn bảo mật, dữ liệu cá nhân, để trống số/ngày/người ký và cách trao đổi dữ liệu với công cụ là **quy ước sản phẩm cho dự thảo**, không quy kết là yêu cầu của Nghị định 30.

1. Chỉ soạn văn bản mức "Thường". Yêu cầu hoặc tài liệu kèm theo có dấu "MẬT", "TỐI MẬT", "TUYỆT MẬT" thì dừng, báo cán bộ.
2. Không đưa thông tin cá nhân vào dự thảo; đầu vào có nhãn `[HO_TEN_n]`, `[DIA_CHI_n]`… thì không chép vào nội dung
   (trừ biểu mẫu có trường cá nhân: giữ nhãn để cán bộ điền).
3. Chỉ chạy trên hạ tầng nội bộ; không dùng dịch vụ AI công cộng.
4. Văn xuôi: ngày "15/10/2026", số "1.248", tiền "98.000.000 đồng". Markdown chỉ là định dạng trung gian khi xuất Word; không để dấu cú pháp Markdown in nguyên vào văn bản.
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

## Đầu ra khi trả dự thảo trong chat

Văn bản thuần, khối trái trước, khối phải sau; một dòng trống phân tách khối là quy ước dữ liệu nội bộ, không phải khoảng cách in trên Word:

```text
CÔNG AN TỈNH HƯNG YÊN
PHÒNG THAM MƯU
Số: .../PV01-...
V/v tăng cường bảo đảm an ninh, trật tự

CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM
Độc lập - Tự do - Hạnh phúc
Hưng Yên, ngày ... tháng ... năm ...

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

## Thể thức theo Nghị định 30

- Điều 8 khoản 2 có 09 nhóm thành phần: quốc hiệu/tiêu ngữ; cơ quan; số/ký hiệu; địa danh/ngày; tên loại/trích yếu;
  nội dung; chức vụ/họ tên/chữ ký người có thẩm quyền; dấu/chữ ký số cơ quan; nơi nhận. Dự thảo chưa ký để phần ký/dấu trống; không tự tạo chữ ký, dấu hoặc ghi đã ký.
- Cơ quan ban hành dùng tên chính thức đầy đủ. Chủ quản ghi khi có, được viết tắt cụm từ thông dụng;
  hai tên IN HOA, tên dài được nhiều dòng. Ngữ cảnh sản phẩm là Công an tỉnh Hưng Yên, nhưng không đoán cơ quan ban hành hay thẩm quyền ký khi đầu vào chưa nêu.
- Quốc hiệu, tiêu ngữ đúng nguyên văn "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM" / "Độc lập - Tự do - Hạnh phúc" (gạch nối ngắn có cách).
- Viết đúng "V/v ", "Kính gửi:", "Nơi nhận:", "Lưu: VT, …". Công văn, tờ trình và báo cáo cấp dưới gửi cấp trên có cả Kính gửi và Nơi nhận.
  Kính gửi 01 nơi viết cùng dòng; không tự coi thiếu dấu chấm cuối dòng này là lỗi. Từ 02 nơi: từng dòng "- …;", nơi cuối dấu ".".
- Viết hoa theo Phụ lục II NĐ 30; không viết hoa tùy tiện danh từ chung.
- **Không sinh số, ký hiệu**: slot `"/PV01-..."` → `Số: .../PV01-...`; không có → `Số: .../...`.
- **Họ tên người ký luôn là "..."** (dòng cuối), kể cả khi đầu vào có tên hoặc nhãn `[HO_TEN_n]`.
- Địa danh, ngày giữ đúng giá trị trong slot và chuẩn hóa cách trình bày theo Nghị định; yêu cầu ngắn: "Hưng Yên, ngày ... tháng ... năm ..." (năm chỉ theo đầu vào nếu có).
- Ngày ban hành đã biết: ngày 1–9 thêm 0; tháng 1, 2 thêm 0; không bắt tháng 3–12 luôn có 2 chữ số. Không lấy ngày hiện tại làm ngày ký.
- Chức vụ ký theo slot, mỗi phần " / " một dòng; "ký thay" → "KT. <CHỨC VỤ ĐỨNG ĐẦU>" + "<CHỨC VỤ CẤP PHÓ>";
  không nêu người ký → "..." thay dòng chức vụ.

## Bố cục nghiệp vụ gợi ý theo loại

Các đề mục và số điều dưới đây là mẫu nội bộ để gợi ý, không bắt buộc mọi kế hoạch có 03 mục, mọi báo cáo có 04 mục hoặc quyết định có đúng 03 điều. Điều chỉnh theo nội dung, thẩm quyền và mẫu được cung cấp, không tự sinh tồn tại/kiến nghị để lấp mục trống.

| Loại | Bố cục gợi ý, điều chỉnh theo dữ kiện và mẫu áp dụng |
|---|---|
| Công văn | Kính gửi → căn cứ, lý do ("Thực hiện…", "Theo đề nghị của…") → yêu cầu (đánh số khi từ 02 ý) → câu kết ("Đề nghị các đơn vị quan tâm, triển khai thực hiện./.") |
| Kế hoạch | `I. MỤC ĐÍCH, YÊU CẦU` (1. Mục đích; 2. Yêu cầu) → `II. NỘI DUNG` → `III. TỔ CHỨC THỰC HIỆN` → "Trên đây là Kế hoạch…/." |
| Báo cáo | Kính gửi nếu báo cáo cấp dưới gửi cấp trên → mở đầu → kết quả; tồn tại, phương hướng, kiến nghị chỉ khi có dữ kiện |
| Thông báo kết luận | Thời gian, chủ trì, thành phần → "ý kiến kết luận như sau:" → kết luận đánh số → câu kết |
| Giấy mời | Trân trọng kính mời → nội dung → thời gian → địa điểm → đề nghị chuẩn bị (nếu có) |
| Tờ trình | Kính gửi → sự cần thiết → nội dung đề nghị → kiến nghị phê duyệt |
| Quyết định | Thẩm quyền → "Căn cứ …;" (mỗi căn cứ 01 dòng) → "Theo đề nghị của …" → `QUYẾT ĐỊNH:` → `Điều 1.`, `Điều 2.`, `Điều 3.` (điều cuối là điều khoản thi hành) |
| Biên bản | Thời gian, địa điểm → thành phần (chủ trì, thư ký, tham dự) → nội dung → kết thúc (giờ kết thúc, thông qua); chữ ký chủ trì và thư ký thay khối người ký |
| Biểu mẫu BCA | Giữ nguyên cấu trúc, tiêu đề, thứ tự mục của mẫu; chỉ điền trường, thiếu thì "..." |

## Văn phong và khớp đầu vào (R6.11-R6.14)

- Câu rõ, ngắn; không "!", không "đáng báo động", "vô cùng", "cực kỳ", "hết sức nguy hiểm", không "tôi", "chúng tôi".
- Không viết tắt (CSGT, TNGT, CA xã…), trừ chữ có trong slot hoặc thông dụng ở "Nơi nhận" ("Đ/c", "b/c", "t/h", "VT").
- Giữ nguyên dữ kiện và danh tính của slot; được chuẩn hóa chữ hoa, ngày và cách viện dẫn theo Nghị định. Mọi ngày, con số trong đầu ra phải có trong đầu vào.
  Không thêm đơn vị, thời hạn, số liệu, căn cứ, kênh gửi ("qua thư điện tử") mà đầu vào không có.
- Được viết câu mở đầu, chuyển ý, câu kết thông dụng; mỗi phần tử `noi_dung_chinh` phải được thể hiện.
- Nội dung kết thúc bằng "./.".

Văn phong, hạn chế viết tắt và câu kết trên là quy ước nội bộ. Không gán mọi từ "tôi", "chúng tôi", dấu "!" hoặc tên cơ quan chủ quản viết tắt thành vi phạm Nghị định 30.

## Căn cứ và viện dẫn

- Chỉ đưa căn cứ khi được cung cấp/được yêu cầu và đã xác minh; không tự chọn căn cứ để làm dự thảo có vẻ đầy đủ.
- Căn cứ ban hành là từng đoạn chữ nghiêng, cuối mỗi đoạn ";", đoạn cuối "." (Phụ lục I, Phần I, II.6.a).
- Luật, Pháp lệnh trong căn cứ không ghi số/ký hiệu/cơ quan ban hành; khi viện dẫn lần đầu chỉ ghi tên loại và tên.
  Các loại khác viện dẫn lần đầu đầy đủ metadata đã có; lần sau theo II.6.b. Không bịa metadata còn thiếu.
- Kiểu trình bày pháp lý được phép chuẩn hóa cách dẫn, nhưng không đổi danh tính/nội dung văn bản căn cứ.

## Dùng kho tri thức Arkon

- Tìm văn bản mẫu cùng loại, văn bản căn cứ: `search_wiki`, `search_source_content`, `get_source_pages`.
- Biểu mẫu Bộ Công an: tìm đúng số, ký hiệu văn bản ban hành biểu mẫu, giữ nguyên cấu trúc mẫu.
- Căn cứ chỉ đưa vào khi đầu vào nêu hoặc cán bộ yêu cầu; ghi đúng số, ký hiệu, ngày như văn bản trong kho.

## Terminal CAHY (xuất Word)

Khi yêu cầu có Word/DOCX, ưu tiên mẫu dữ liệu này thay ví dụ văn bản thuần ở trên. Ví dụ giả lập, không sao chép dữ kiện ví dụ:

```markdown
---
type: vanban
output: bao_cao_thu_nghiem.docx
quoc_hieu: CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM
tieu_ngu: Độc lập - Tự do - Hạnh phúc
co_quan_chu_quan: CÔNG AN TỈNH HƯNG YÊN
co_quan: PHÒNG THAM MƯU
so: .../BC-...
dia_danh: Hưng Yên
ngay: ngày ... tháng ... năm ...
loai: BÁO CÁO
trich_yeu: Kết quả kiểm tra hồ sơ thử nghiệm
kinh_gui:
  - Công an tỉnh Hưng Yên
noi_nhan:
  - Như trên;
  - Lưu: VT.
chuc_vu: ...
nguoi_ky: ...
---
Đã kiểm tra 3 hồ sơ thử nghiệm./.
```

1. Đọc `references/nd30-the-thuc.md`. Khi người dùng muốn Word, trả dự thảo gồm frontmatter `type: vanban` và thân Markdown theo mẫu ở đó, chưa gọi xuất trước khi hệ thống kiểm tra.
2. Thông tin header, tên loại, trích yếu, Kính gửi, Nơi nhận và chức vụ ký nằm trong frontmatter; thân chỉ có nội dung. Không viết lặp các khối được công cụ dàn trang. Frontmatter có `quoc_hieu`/`tieu_ngu` đúng nguyên văn để bộ rà soát biết phần đầu được khai báo.
3. Sau khi hệ thống kiểm tra đạt, dùng `write_file` tên `.md` đơn giản và `md2office <ten>.md`; output phải đúng tên/hậu tố của lượt được cấp. Không dùng `vb-sang-docx`, `kiem-json`, `kiem-tra-docx` hoặc đường dẫn `/opt/cahy/huong_dan` chưa tồn tại; không chạy Python/shell tùy ý.
4. Profile xuất: A4 dọc, TNR Unicode đen, nội dung 14pt, lề trên/dưới 20mm, trái 30mm, phải 15mm; đây là một cấu hình hợp lệ trong các khoảng NĐ30, không phải cấu hình duy nhất. Số trang 13pt giữa lề trên, không hiện trang đầu. Xem bảng cỡ chữ và khoảng cách từng thành phần trong reference.
5. Không coi tạo tệp thành công hoặc render được là chứng nhận đầy đủ thể thức. Chỉ nói đã kiểm phông/lề/số trang nếu có báo cáo công cụ trên đúng DOCX. Mẫu chuyên biệt, nhiều người ký, phụ lục đánh số riêng hoặc biểu mẫu BCA phải có mẫu và bộ dàn trang tương ứng; không ép vào mẫu một khối ký rồi cam kết đúng.

## Tự kiểm trước khi trả

- [ ] Đủ thành phần phù hợp dự thảo; phần ký/dấu chưa thực hiện không bị coi là đã ký.
- [ ] Không tự sinh số văn bản; dòng cuối là "...".
- [ ] Bố cục đúng loại và mẫu áp dụng; không áp số mục/số điều cố định khi không có căn cứ; nội dung kết thúc "./.".
- [ ] Mọi thông tin có trong đầu vào; không chữ viết tắt; không từ cảm xúc.

## Tham chiếu

- `references/s3_slot.schema.json`: lược đồ slot đầu vào.
- `references/nd30-the-thuc.md`: căn cứ từ PDF và hợp đồng xuất Word thực tế.

**Chốt định dạng khi được yêu cầu Word:** ký tự đầu tiên của phản hồi là `---`, không có hàng rào mã ```markdown/```text, không có lời dẫn hoặc câu kết ngoài dự thảo. Frontmatter đóng bằng `---`; phần sau chỉ là thân nội dung. Không viết lặp header, Kính gửi, Nơi nhận, chữ ký đã khai báo trong frontmatter. Thiếu năm ký vẫn ghi `năm ...`, không lấy năm từ ví dụ hoặc đồng hồ hệ thống.
