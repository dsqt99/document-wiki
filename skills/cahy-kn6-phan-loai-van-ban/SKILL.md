---
name: cahy-kn6-phan-loai-van-ban
description: "KN6 - Phân loại và đề xuất xử lý văn bản đến của Công an tỉnh: xác định loại văn bản, lĩnh vực (11 nhãn + KHAC), mức độ khẩn theo dấu trên văn bản, đề xuất đơn vị chủ trì, đơn vị phối hợp trong danh mục đơn vị và lý do 01 câu. Trả về một đối tượng JSON 06 trường. Triggers on: phân loại văn bản đến, đề xuất xử lý, giao đơn vị chủ trì, phân công xử lý văn bản, văn thư văn bản đến, độ khẩn, hỏa tốc, phan_loai_van_ban."
allowed-tools: mcp__arkon__search_wiki mcp__arkon__read_wiki_page mcp__arkon__list_sources mcp__arkon__get_source mcp__arkon__get_source_outline mcp__arkon__get_source_pages mcp__arkon__search_source_content mcp__arkon__list_knowledge_types mcp__arkon__get_knowledge_type_docs
---

# KN6 - Phân loại và đề xuất xử lý văn bản đến (`phan_loai_van_ban`)

Đọc văn bản đến, gán loại, lĩnh vực, mức độ khẩn và đề xuất đơn vị xử lý để văn thư trình lãnh đạo phân công.
Nguồn quy tắc: Guideline, mục 7.3 (R7.22-R7.28) và mục 4.3.1 (bộ nhãn lĩnh vực).

## Câu lệnh hệ thống (dùng nguyên văn)

```text
Bạn là cán bộ văn thư Công an tỉnh, làm nhiệm vụ phân loại và đề xuất xử lý văn bản đến. Trả về đúng một đối tượng JSON theo lược đồ quy định; đơn vị đề xuất lấy trong danh mục đơn vị của Công an tỉnh.
```

## Quy tắc chung (bắt buộc)

1. Chỉ xử lý văn bản mức "Thường". Văn bản có dấu "MẬT", "TỐI MẬT", "TUYỆT MẬT" thì dừng, chuyển xử lý theo quy chế bảo vệ bí mật nhà nước.
2. Văn bản phải khử định danh trước (`[HO_TEN_n]`, `[CCCD_n]`, `[DIA_CHI_n]`…); không đưa thông tin cá nhân vào `ly_do`.
3. Chỉ chạy trên hạ tầng nội bộ; không dùng dịch vụ AI công cộng.
4. Kết quả là đề xuất; lãnh đạo quyết định phân công.

## Đầu vào

"Phân loại và đề xuất xử lý văn bản đến sau." + khối `[VAN_BAN_DEN]`: toàn văn văn bản đến dạng văn bản thuần;
dấu mức độ khẩn nằm ở dòng riêng dưới số, ký hiệu hoặc trích yếu.

## Đầu ra: đủ 06 trường, đúng thứ tự

```json
{
  "loai_van_ban": "Công văn",
  "linh_vuc": "PCCC_CNCH",
  "do_khan": "KHAN",
  "don_vi_chu_tri": "Phòng Cảnh sát phòng cháy, chữa cháy và cứu nạn, cứu hộ",
  "don_vi_phoi_hop": ["Công an các xã, phường"],
  "ly_do": "Văn bản yêu cầu kiểm tra an toàn phòng cháy, chữa cháy tại các cơ sở có nguy cơ cháy, nổ cao, thuộc chức năng của Phòng Cảnh sát phòng cháy, chữa cháy và cứu nạn, cứu hộ."
}
```

(Ví dụ minh họa dữ liệu giả lập.)

## Bộ nhãn

- `loai_van_ban`: `Công văn`, `Công điện`, `Chỉ thị`, `Nghị quyết`, `Quyết định`, `Kế hoạch`, `Thông báo`, `Báo cáo`, `Giấy mời`,
  `Tờ trình`, `Biên bản`, `Hướng dẫn`, `Khác` (dùng chung với KN5).
- `do_khan`: `THUONG`, `KHAN`, `THUONG_KHAN`, `HOA_TOC`.
- `linh_vuc` và đơn vị chủ trì mặc định (tên đơn vị là minh họa, PV01 xác nhận theo cơ cấu tổ chức hiện hành):

| `linh_vuc` | Đơn vị chủ trì mặc định |
|---|---|
| `AN_CHINH_TRI` | Theo phân công (PV01 xác nhận) |
| `TOI_PHAM_HINH_SU` | Phòng Cảnh sát hình sự |
| `TOI_PHAM_KINH_TE` | Phòng Cảnh sát kinh tế |
| `TOI_PHAM_MA_TUY` | Phòng Cảnh sát điều tra tội phạm về ma túy |
| `TOI_PHAM_CONG_NGHE_CAO` | Phòng An ninh mạng và phòng, chống tội phạm sử dụng công nghệ cao |
| `TOI_PHAM_MOI_TRUONG` | Phòng Cảnh sát môi trường |
| `TTATGT` | Phòng Cảnh sát giao thông |
| `PCCC_CNCH` | Phòng Cảnh sát phòng cháy, chữa cháy và cứu nạn, cứu hộ |
| `QUAN_LY_HANH_CHINH` | Phòng Cảnh sát quản lý hành chính về trật tự xã hội |
| `KHIEU_NAI_TO_CAO` | Theo phân công (PV01 xác nhận) |
| `XAY_DUNG_LUC_LUONG` | Phòng Tổ chức cán bộ |
| `KHAC` | Phòng Tham mưu (tiếp nhận, báo cáo lãnh đạo phân công) |

Danh mục đơn vị máy đọc: `references/danh_muc_don_vi.json` (khóa `don_vi`, mỗi phần tử có `ten`, `ma`, `nhom`, `minh_hoa`).
Chỉ dùng `ten` trong danh mục; `minh_hoa: true` là tên chờ PV01 xác nhận.

## Quy tắc gán nhãn (R7.22-R7.28)

| Mã | Quy tắc |
|---|---|
| R7.22 | `loai_van_ban` theo tên loại trên văn bản; không có tên loại, có dòng "V/v" → `"Công văn"` |
| R7.23 | `linh_vuc` đúng 01 trong 12 nhãn; `KHAC` chỉ khi không thuộc 11 lĩnh vực (công tác Đảng, hợp tác quốc tế, khoa học - công nghệ, chuyển đổi số…) |
| R7.24 | Chọn lĩnh vực theo **nội dung chính và nhiệm vụ giao cho Công an tỉnh**, không theo từ khóa đơn lẻ; nhiều lĩnh vực → lĩnh vực của nhiệm vụ đầu tiên giao cho Công an tỉnh |
| R7.25 | `do_khan` chỉ theo dấu trên văn bản: "KHẨN" → `KHAN`; "THƯỢNG KHẨN" → `THUONG_KHAN`; "HỎA TỐC" → `HOA_TOC`; không có dấu → `THUONG`. Không tự đánh giá theo nội dung |
| R7.26 | `don_vi_chu_tri` là 01 đơn vị trong danh mục, mặc định theo bảng trên; văn bản giao rõ việc cho đơn vị khác thì chọn đơn vị đó và nêu căn cứ trong `ly_do` |
| R7.27 | `don_vi_phoi_hop` 01-03 đơn vị trong danh mục, khác đơn vị chủ trì, chỉ khi văn bản có nội dung cần phối hợp (nhiệm vụ của Công an cấp xã, nhiệm vụ thuộc lĩnh vực khác); không có → `null` (không ghi `[]`) |
| R7.28 | `ly_do` **01 câu**, ≤ 50 từ (đếm theo âm tiết), nêu nội dung chính làm căn cứ phân loại và chức năng của đơn vị chủ trì; kết thúc bằng "."; không chép lại toàn bộ trích yếu |

Phân biệt lĩnh vực gần nhau (R4.2): lừa đảo qua mạng → `TOI_PHAM_CONG_NGHE_CAO`; buôn lậu, hàng giả → `TOI_PHAM_KINH_TE`;
tai nạn giao thông → `TTATGT`; cháy, nổ, cứu nạn → `PCCC_CNCH`; cư trú, căn cước, vũ khí, ngành nghề kinh doanh có điều kiện
→ `QUAN_LY_HANH_CHINH`; đơn thư, tiếp công dân → `KHIEU_NAI_TO_CAO`; tổ chức cán bộ, đào tạo, thi đua → `XAY_DUNG_LUC_LUONG`.

## Lỗi thường gặp

| Sai | Đúng |
|---|---|
| Giấy mời gán `"Thông báo"` | `"Giấy mời"` |
| `do_khan: "KHAN"` vì nội dung "cấp bách" nhưng không có dấu | `"THUONG"` |
| Gán `TOI_PHAM_MA_TUY` vì có từ "ma túy" trong phần căn cứ, nhiệm vụ chính là PCCC | `PCCC_CNCH` |
| `"don_vi_phoi_hop": []` | `null` |
| Đơn vị phối hợp trùng đơn vị chủ trì, hoặc 04 đơn vị | 01-03 đơn vị khác chủ trì |
| `ly_do` 02-03 câu | 01 câu, ≤ 50 từ |

## Dùng kho tri thức Arkon

- Văn bản đến tham chiếu văn bản khác: `search_wiki`, `search_source_content` để hiểu nhiệm vụ chính; không đổi nhãn theo văn bản tham chiếu.
- Tra quy chế phân công, chức năng đơn vị (nếu kho có): `list_knowledge_types` → `get_knowledge_type_docs`.

## Terminal CAHY (lô văn bản đến)

Theo `/opt/cahy/huong_dan/KY_NANG.md`, mục KN6:

1. Ghi JSON từng văn bản vào `~/ket_qua/kn6/`, chạy `kiem-json s6 <tệp>`.
2. Sổ phân loại nhiều văn bản: openpyxl, cột STT, Số ký hiệu, Trích yếu, Loại, Lĩnh vực, Độ khẩn, Chủ trì, Phối hợp, Lý do;
   tô màu dòng `HOA_TOC`, `THUONG_KHAN`; cố định hàng tiêu đề, bật bộ lọc. Đối chiếu tên đơn vị với
   `/opt/cahy/huong_dan_tu_van_skill/cong_cu/danh_muc_don_vi.json` bằng mã, không bằng mắt.

## Tự kiểm trước khi trả

- [ ] Đủ 06 trường, đúng thứ tự, giá trị trong bộ nhãn.
- [ ] `do_khan` khớp dấu trên văn bản.
- [ ] Đơn vị chủ trì, phối hợp có trong danh mục; phối hợp 01-03 hoặc `null`.
- [ ] `ly_do` 01 câu, ≤ 50 từ, kết thúc ".".

## Tham chiếu

- `references/s6_phan_loai.schema.json`: lược đồ JSON đầu ra.
- `references/danh_muc_don_vi.json`: danh mục đơn vị (minh họa, chờ PV01 xác nhận).
