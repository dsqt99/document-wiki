---
name: cahy-kn5-trich-xuat
description: "KN5 - Trích xuất thông tin có cấu trúc từ văn bản hành chính của Công an tỉnh thành một đối tượng JSON 08 trường: số ký hiệu, ngày ban hành, cơ quan ban hành, loại văn bản, trích yếu, đơn vị được giao, thời hạn, nhiệm vụ. Chép nguyên văn, thiếu thì null, không suy diễn; lập sổ theo dõi nhiệm vụ Excel. Triggers on: trích xuất thông tin văn bản, lấy số ký hiệu, ngày ban hành, đơn vị được giao, thời hạn, nhiệm vụ, bảng theo dõi nhiệm vụ, nhập sổ văn bản, trich_xuat."
allowed-tools: mcp__arkon__search_wiki mcp__arkon__read_wiki_page mcp__arkon__list_sources mcp__arkon__get_source mcp__arkon__get_source_outline mcp__arkon__get_source_pages mcp__arkon__search_source_content
---

# KN5 - Trích xuất thông tin có cấu trúc (`trich_xuat`)

Đọc văn bản hành chính, trả về JSON để nhập sổ văn bản, lập bảng theo dõi nhiệm vụ, đôn đốc thời hạn.
Trọng tâm: **chép đúng, không suy diễn**. Nguồn quy tắc: Guideline, mục 7.2 (R7.12-R7.21).

## Câu lệnh hệ thống (dùng nguyên văn)

```text
Bạn là công cụ trích xuất thông tin văn bản của Công an tỉnh. Trả về đúng một đối tượng JSON theo lược đồ quy định; thông tin không có trong văn bản ghi null, không suy diễn.
```

## Quy tắc chung (bắt buộc)

1. Chỉ xử lý văn bản mức "Thường". Thấy dấu "MẬT", "TỐI MẬT", "TUYỆT MẬT" thì dừng, báo cán bộ, không lưu.
2. Văn bản phải khử định danh trước (`[HO_TEN_n]`, `[CCCD_n]`, `[SO_DIEN_THOAI_n]`, `[DIA_CHI_n]`…); giữ nguyên nhãn khi chép.
3. Chỉ chạy trên hạ tầng nội bộ; không dùng dịch vụ AI công cộng.
4. Ngày trong JSON theo ISO `YYYY-MM-DD`. Kết quả là dự thảo để văn thư đối chiếu.

## Đầu vào

"Trích xuất thông tin văn bản sau." + khối `[VAN_BAN]`: toàn văn văn bản dạng văn bản thuần, khối trái trước, khối phải sau
(cùng quy ước của skill `cahy-kn3-sinh-van-ban`).

## Đầu ra: đủ 08 trường, đúng thứ tự

```json
{
  "so_ky_hieu": "902/UBND-NC",
  "ngay_ban_hanh": "2026-10-02",
  "co_quan_ban_hanh": "ỦY BAN NHÂN DÂN TỈNH HƯNG YÊN",
  "loai_van_ban": "Công văn",
  "trich_yeu": "tăng cường công tác phòng cháy, chữa cháy mùa hanh khô",
  "don_vi_duoc_giao": ["Công an tỉnh", "Ủy ban nhân dân các xã, phường"],
  "thoi_han": [{"noi_dung": "Báo cáo kết quả kiểm tra", "han": "2026-11-30", "han_goc": "trước ngày 30/11/2026", "don_vi": "Công an tỉnh"}],
  "nhiem_vu": [{"don_vi": "Công an tỉnh", "noi_dung": "Báo cáo kết quả kiểm tra"},
               {"don_vi": "Ủy ban nhân dân các xã, phường", "noi_dung": "Rà soát các cơ sở có nguy cơ cháy, nổ cao"}]
}
```

(Ví dụ minh họa dữ liệu giả lập.)

`loai_van_ban` là 01 trong 13 giá trị: `Công văn`, `Công điện`, `Chỉ thị`, `Nghị quyết`, `Quyết định`, `Kế hoạch`, `Thông báo`,
`Báo cáo`, `Giấy mời`, `Tờ trình`, `Biên bản`, `Hướng dẫn`, `Khác`.

## Quy tắc trích xuất

| Mã | Quy tắc |
|---|---|
| R7.12 | Không có thông tin → `null`, kể cả trường danh sách. Không ghi `""`, `[]`, "không có", "không rõ". Danh sách có giá trị thì có ít nhất 01 phần tử |
| R7.13 | Chép nguyên văn `so_ky_hieu` (dự thảo "…/PV01-TH" vẫn chép); `co_quan_ban_hanh` IN HOA như văn bản, tên 02 dòng nối bằng 01 khoảng trắng, chỉ lấy cơ quan ban hành (không lấy cơ quan chủ quản); tên đơn vị không chuẩn hóa, không viết tắt |
| R7.14 | `trich_yeu`: công văn lấy phần sau "V/v "; loại khác lấy dòng trích yếu dưới tên loại; không rút gọn, không thêm tên loại |
| R7.15 | `ngay_ban_hanh` quy đổi ISO từ dòng "<Địa danh>, ngày … tháng … năm …"; dự thảo để trống ngày, tháng → `null` |
| R7.16 | `loai_van_ban` theo tên loại trên văn bản; không có tên loại, có "V/v" → `"Công văn"`; ngoài danh mục → `"Khác"` |
| R7.17 | `thoi_han`: mỗi mốc gắn với 01 nhiệm vụ là 01 phần tử, theo thứ tự xuất hiện. `han_goc` chép nguyên văn cụm thời hạn. `han` ISO khi đủ ngày, tháng, năm; "từ … đến …" lấy ngày kết thúc. Tương đối hoặc không đủ ngày ("trong thời hạn 05 ngày làm việc kể từ…", "trong tháng 11/2026", "hằng tháng") → `han: null`. Không có thời hạn → `thoi_han: null` |
| R7.18 | `nhiem_vu`: mỗi vế giao việc cho 01 đơn vị (ngăn bởi ";" hoặc mục đánh số) là 01 phần tử. `noi_dung` chép nguyên văn vế giao việc, bỏ tên đơn vị đứng đầu và cụm thời hạn, viết hoa chữ cái đầu, không dấu câu cuối |
| R7.19 | Mỗi đơn vị trong `don_vi_duoc_giao` có ít nhất 01 nhiệm vụ; `nhiem_vu.don_vi`, `thoi_han.don_vi` thuộc `don_vi_duoc_giao`; `thoi_han.noi_dung` trùng nguyên văn `noi_dung` của 01 nhiệm vụ cùng đơn vị |
| R7.20 | `don_vi_duoc_giao`: đơn vị được nêu đích danh là chủ thể thực hiện, theo thứ tự xuất hiện lần đầu. Không đưa nơi nhận "để biết", "để báo cáo", không đưa cụm chung "các cơ quan, đơn vị liên quan"; cơ quan ban hành tự giao việc cho mình thì vẫn ghi |
| R7.21 | Không suy ra đơn vị, thời hạn, nhiệm vụ từ chức năng hay thông lệ; không quy đổi thời hạn tương đối; không sửa lỗi chính tả của văn bản gốc |

## Lỗi thường gặp

| Sai | Đúng |
|---|---|
| `"ngay_ban_hanh": "02/10/2026"` | `"2026-10-02"` |
| `"thoi_han": []` khi không có thời hạn | `"thoi_han": null` |
| "05 ngày làm việc kể từ…" quy đổi thành `"2027-03-09"` | `"han": null`, giữ `han_goc` |
| `"so_ky_hieu": "902/UBND"` (thiếu "-NC") | `"902/UBND-NC"` |
| Thêm đơn vị không có trong văn bản | Chỉ đơn vị nêu đích danh |
| Đơn vị trong `don_vi_duoc_giao` không có nhiệm vụ | Mỗi đơn vị ít nhất 01 nhiệm vụ |
| `"trich_yeu": "Kết luận giao ban tháng 9"` (rút gọn) | Nguyên văn dòng trích yếu |

## Dùng kho tri thức Arkon

Văn bản đã có trong kho: `search_wiki` hoặc `list_sources` → `get_source_outline` → `get_source_pages` để lấy nguyên văn
phần đầu (số, ký hiệu, ngày, cơ quan) và phần giao nhiệm vụ. Chỉ trích từ nguyên văn, không từ trang wiki đã tổng hợp.

## Terminal CAHY (JSON + Excel theo dõi)

Theo `/opt/cahy/huong_dan/KY_NANG.md`, mục KN5:

1. Ghi JSON vào `~/ket_qua/kn5/`, chạy `kiem-json s5 <tệp>`.
2. Sổ theo dõi nhiều văn bản: openpyxl, mỗi nhiệm vụ một dòng gồm Số ký hiệu, Ngày, Cơ quan, Nhiệm vụ, Đơn vị, Hạn (ISO), Hạn gốc;
   cố định hàng tiêu đề (freeze panes), bật bộ lọc. Lưu mã nguồn vào `~/ket_qua/kn5/ma_nguon/`.

## Tự kiểm trước khi trả

- [ ] Đủ 08 trường, đúng thứ tự; thiếu thì `null`, không `[]`, không `""`.
- [ ] Mọi chuỗi chép nguyên văn; ngày ISO; thời hạn tương đối có `han: null`.
- [ ] Liên kết đơn vị, nhiệm vụ, thời hạn khớp nhau (R7.19).

## Tham chiếu

- `references/s5_trich_xuat.schema.json`: lược đồ JSON đầu ra.
