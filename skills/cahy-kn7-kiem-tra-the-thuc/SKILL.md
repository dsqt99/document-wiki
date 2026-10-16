---
name: cahy-kn7-kiem-tra-the-thuc
description: "KN7 - Rà soát thể thức dự thảo văn bản hành chính của Công an tỉnh theo Nghị định số 30/2020/NĐ-CP trước khi trình ký: phát hiện lỗi quốc hiệu, tên cơ quan, số ký hiệu, ngày tháng, trích yếu, căn cứ, bố cục, chức vụ ký, nơi nhận, viết hoa, viết tắt, chính tả, văn phong. Trả về JSON danh sách lỗi có vị trí, trích đoạn, đề xuất sửa, căn cứ; kiểm tra phông, cỡ chữ, lề trên DOCX bằng công cụ. Triggers on: kiểm tra thể thức, rà soát dự thảo, soát lỗi văn bản, nghị định 30, lỗi thể thức, trước khi trình ký, kiem_tra_the_thuc."
allowed-tools: mcp__arkon__search_wiki mcp__arkon__read_wiki_page mcp__arkon__list_sources mcp__arkon__get_source mcp__arkon__get_source_outline mcp__arkon__get_source_pages mcp__arkon__search_source_content
---

# KN7 - Kiểm tra thể thức văn bản (`kiem_tra_the_thuc`)

Rà soát dự thảo theo NĐ 30/2020, trả về danh sách lỗi để cán bộ soạn thảo sửa trước khi trình ký.
Mô hình chỉ kiểm tra nội dung **thể hiện được trên văn bản thuần**; phông, cỡ chữ, kiểu chữ, lề, khổ giấy do công cụ
kiểm tra trên tệp DOCX. Nguồn quy tắc: Guideline, mục 7.4 (R7.31-R7.39).

## Câu lệnh hệ thống (dùng nguyên văn)

```text
Bạn là cán bộ kiểm tra thể thức văn bản của Công an tỉnh. Rà soát dự thảo theo Nghị định số 30/2020/NĐ-CP, trả về đúng một đối tượng JSON liệt kê lỗi; không có lỗi thì trả về danh sách rỗng.
```

## Quy tắc chung (bắt buộc)

1. Chỉ rà soát dự thảo mức "Thường". Dự thảo có dấu "MẬT", "TỐI MẬT", "TUYỆT MẬT" thì dừng, báo cán bộ.
2. Dự thảo có thông tin cá nhân thì khử định danh trước (`[HO_TEN_n]`, `[DIA_CHI_n]`…); nhãn giữ chỗ không phải lỗi.
3. Chỉ chạy trên hạ tầng nội bộ; không dùng dịch vụ AI công cộng.
4. Chỉ báo lỗi có căn cứ; không báo lỗi với cách diễn đạt đúng văn phong hành chính.

## Đầu vào

"Rà soát thể thức dự thảo sau." + khối `[DU_THAO]`: dự thảo dạng văn bản thuần, khối trái trước, khối phải sau
(quy ước như skill `cahy-kn3-sinh-van-ban`). Cán bộ gửi tệp DOCX thì chuyển sang văn bản thuần trong Terminal CAHY trước.

## Đầu ra

```json
{
  "hop_le": false,
  "so_loi": 2,
  "loi": [
    {
      "ma_loi": "TT_TEN_LOAI_TRICH_YEU",
      "vi_tri": "ten_loai_trich_yeu",
      "trich_doan": "V/V tăng cường",
      "mo_ta": "Trích yếu công văn viết \"V/V\" thay cho \"V/v\".",
      "de_xuat_sua": "V/v tăng cường",
      "can_cu": "Phụ lục I, Nghị định số 30/2020/NĐ-CP"
    },
    {
      "ma_loi": "TT_DIA_DANH_NGAY_THANG",
      "vi_tri": "dia_danh_ngay_thang",
      "trich_doan": "ngày 5 tháng 2 năm 2026",
      "mo_ta": "Ngày nhỏ hơn 10 và tháng 2 không ghi số 0 ở trước.",
      "de_xuat_sua": "ngày 05 tháng 02 năm 2026",
      "can_cu": "Phụ lục I, Nghị định số 30/2020/NĐ-CP"
    }
  ]
}
```

(Ví dụ minh họa.) Không có lỗi: `{"hop_le": true, "so_loi": 0, "loi": []}`.

`vi_tri` là 01 trong: `quoc_hieu_tieu_ngu`, `ten_co_quan`, `so_ky_hieu`, `dia_danh_ngay_thang`, `ten_loai_trich_yeu`,
`do_khan_do_mat`, `kinh_gui`, `can_cu`, `noi_dung`, `noi_nhan`, `chuc_vu_nguoi_ky`.

## Danh mục mã lỗi và căn cứ

`can_cu` mặc định là "Phụ lục I, Nghị định số 30/2020/NĐ-CP", trừ 02 mã ghi ở cột Căn cứ.

| `ma_loi` | Nội dung | Căn cứ |
|---|---|---|
| `TT_QUOC_HIEU_TIEU_NGU` | Quốc hiệu, tiêu ngữ sai chữ, sai viết hoa, sai dấu gạch nối | Phụ lục I |
| `TT_TEN_CO_QUAN` | Tên cơ quan ban hành, chủ quản sai, viết tắt, thiếu cơ quan chủ quản | Phụ lục I |
| `TT_SO_KY_HIEU` | Số, ký hiệu sai cấu trúc, sai thứ tự chữ viết tắt | Phụ lục I |
| `TT_DIA_DANH_NGAY_THANG` | Địa danh sai; ngày nhỏ hơn 10 hoặc tháng 1, 2 không có số 0 ở trước; ghi ngày bằng "/" hoặc "-" | Phụ lục I |
| `TT_TEN_LOAI_TRICH_YEU` | Viết "V/V", "Về việc" trên công văn; tên loại văn bản không in hoa | Phụ lục I |
| `TT_CAN_CU` | Căn cứ ban hành sai thứ tự, sai dấu câu cuối dòng | Phụ lục I |
| `TT_BO_CUC_NOI_DUNG` | Bố cục sai theo loại văn bản; quyết định thiếu điều khoản thi hành | Phụ lục I |
| `TT_CHUC_VU_CHU_KY` | Sai quyền hạn ký (KT., TL., TM.), sai chức vụ người ký | Phụ lục I |
| `TT_NOI_NHAN` | Nơi nhận thiếu dòng "Lưu", sai dấu câu cuối dòng | Phụ lục I |
| `TT_DO_MAT_DO_KHAN` | Dấu mức độ khẩn sai cách ghi, sai vị trí | Phụ lục I |
| `TT_THIEU_THANH_PHAN` | Thiếu thành phần thể thức chính | **Khoản 2 Điều 8, Nghị định số 30/2020/NĐ-CP** |
| `TT_VIET_HOA` | Viết hoa sai (tên cơ quan, chức vụ, địa danh, danh từ chung) | **Phụ lục II, Nghị định số 30/2020/NĐ-CP** |
| `TT_VIET_TAT` | Viết tắt trong nội dung khi chưa ghi đầy đủ ở lần đầu | Phụ lục I |
| `CHINH_TA` | Sai chính tả | Phụ lục I |
| `VAN_PHONG` | Từ ngữ cảm xúc, khẩu ngữ, ngôi thứ nhất, dấu "!" | Phụ lục I |
| `TT_KHAC` | Lỗi thể thức khác có căn cứ, ghi rõ trong `mo_ta` | Phụ lục I |

`TT_PHONG_CO_CHU_CAN_LE` (phông, cỡ chữ, lề, khổ giấy) **không bao giờ** xuất hiện trong JSON của mô hình;
chỉ dùng trong báo cáo của công cụ `kiem-tra-docx`.

## Quy tắc gán nhãn (R7.31-R7.39)

- Lỗi liệt kê theo thứ tự xuất hiện của `trich_doan` trong dự thảo (R7.31).
- `so_loi` = số phần tử `loi`; `hop_le = true` khi và chỉ khi `so_loi = 0` (R7.32).
- Mỗi chỗ sai là 01 phần tử; cùng một lỗi lặp ở nhiều chỗ thì mỗi chỗ 01 phần tử (R7.33).
- `trich_doan` chép nguyên văn chuỗi sai, **ngắn nhất nhưng duy nhất** trong dự thảo, nằm trên 01 dòng.
  Thiếu thành phần hoặc thiếu dòng → `trich_doan` là dòng đứng ngay trước chỗ thiếu (R7.35).
- `de_xuat_sua` là chuỗi thay thế đúng cho `trich_doan` (thay vào là sửa xong); thiếu dòng → dòng đứng trước kèm nội dung bổ sung (R7.36).
- `mo_ta` 01 câu nêu vi phạm. `can_cu` chép nguyên văn theo bảng; được thêm tên mục trong ngoặc đơn (R7.37).
- **Không phải lỗi** (R7.38): số, ngày tháng để "..." trong dự thảo; nhãn `[HO_TEN_n]`, `[DIA_CHI_n]`…; cấp bậc hàm trước họ tên;
  "Đ/c", "b/c", "t/h", "VT" trong "Nơi nhận".
- Không kết luận về phông, cỡ chữ, kiểu chữ, căn lề, khổ giấy (R7.39).

## Thứ tự rà soát gợi ý

1. Đủ 09 thành phần (Khoản 2 Điều 8): quốc hiệu, tiêu ngữ; tên cơ quan; số, ký hiệu; địa danh, ngày; tên loại, trích yếu;
   nội dung; chức vụ, họ tên người ký; nơi nhận.
2. Khối trái: tên cơ quan chủ quản, ban hành IN HOA, không viết tắt; "Số: …/…"; "V/v " (công văn); dấu độ khẩn dòng riêng.
3. Khối phải: "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM" / "Độc lập - Tự do - Hạnh phúc"; "<Địa danh>, ngày dd tháng mm năm yyyy".
4. Kính gửi, căn cứ (mỗi căn cứ 01 dòng, kết thúc ";", căn cứ cuối kết thúc ".") và bố cục theo loại (xem `cahy-kn3-sinh-van-ban`).
5. Nội dung: viết hoa, viết tắt chưa giải thích, chính tả, văn phong (không "!", không "tôi", "chúng tôi", từ cảm xúc).
6. Chức vụ, quyền hạn ký; Nơi nhận ("Nơi nhận:", mỗi nơi "- …;", dòng cuối "- Lưu: VT, ….").

## Dùng kho tri thức Arkon

Tra nguyên văn Phụ lục I, II NĐ 30 khi cần trích chi tiết cho `mo_ta`:
`search_source_content` ("Phụ lục I" "thể thức") → `get_source_pages`. Không lấy quy tắc từ nguồn ngoài kho.

## Terminal CAHY (DOCX + phiếu rà soát)

Theo `/opt/cahy/huong_dan/KY_NANG.md`, mục KN7:

1. Dự thảo DOCX: chạy `kiem-tra-docx <tệp.docx> --che-do s7` để kiểm phông, cỡ chữ, lề, khổ giấy (lỗi
   `TT_PHONG_CO_CHU_CAN_LE` nằm trong báo cáo của công cụ, không đưa vào JSON của mô hình).
2. Ghi JSON lỗi vào `~/ket_qua/kn7/`, chạy `kiem-json s7 <tệp>`.
3. Phiếu rà soát: openpyxl hoặc python-docx, cột STT, Vị trí, Trích đoạn, Lỗi, Đề xuất sửa, Căn cứ;
   thêm các dòng của `kiem-tra-docx` ở cuối, ghi nguồn "Công cụ kiểm tra DOCX".

## Tự kiểm trước khi trả

- [ ] `so_loi` = số phần tử `loi`; `hop_le` đúng.
- [ ] Mỗi `trich_doan` có nguyên văn, duy nhất, trên 01 dòng của dự thảo; thay bằng `de_xuat_sua` là hết lỗi.
- [ ] Mã lỗi thuộc 16 mã; `can_cu` đúng bảng; không có `TT_PHONG_CO_CHU_CAN_LE`.
- [ ] Không báo lỗi với "...", nhãn giữ chỗ, chữ viết tắt thông dụng trong Nơi nhận.

## Tham chiếu

- `references/s7_kiem_tra.schema.json`: lược đồ JSON đầu ra.
