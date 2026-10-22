from types import SimpleNamespace

from app.services.legal_service import _is_auto_title, parse_legal_metadata

CANON = "Văn bản hợp nhất số 90/VBHN-VPQH của Văn phòng Quốc hội — Luật Xử lý vi phạm hành chính"


def _src(title, file_name="02. Văn bản hợp nhất số 90 Luật XLVPHC.pdf", meta=None):
    return SimpleNamespace(title=title, file_name=file_name, metadata_=meta)


def test_auto_title_cases():
    assert _is_auto_title(_src(None), CANON)
    assert _is_auto_title(_src("02. Văn bản hợp nhất số 90 Luật XLVPHC.pdf"), CANON)
    assert _is_auto_title(_src("old auto", meta={"auto_title": "old auto"}), CANON)
    # Legacy run swallowed the whole preamble into the title.
    legacy = CANON.split(" — ")[0] + " — Luật Xử Lý " + "Căn Cứ Hiến Pháp " * 30
    assert _is_auto_title(_src(legacy), CANON)


def test_user_title_is_kept():
    assert not _is_auto_title(_src("Luật XLVPHC (bản hợp nhất 2025)"), CANON)
    assert not _is_auto_title(_src(CANON.split(" — ")[0] + " — ghi chú của tôi"), CANON)


def test_vbhn_canonical_name_sentence_case():
    text = "VĂN PHÒNG QUỐC HỘI\nVĂN BẢN HỢP NHẤT\nLUẬT\nXỬ LÝ VI PHẠM HÀNH CHÍNH\nĐiều 1. Phạm vi"
    meta = parse_legal_metadata(text, "02. Văn bản hợp nhất số 90 Luật XLVPHC.pdf")
    assert "Luật Xử lý vi phạm hành chính" in meta["canonical_name"]
    assert len(meta["canonical_name"]) < 200


CONSOLIDATED_DECREE = """**CỘNG HOÀ XÃ HỘI CHỦ NGHĨA VIỆT NAM**
**NGHỊ ĐỊNH**
| Quy định xử phạt vi phạm hành chính trong lĩnh vực giao thông |
| --- |
| đường thủy nội địa |

| Nghị định số 139/2021/NĐ-CP ngày 31 tháng 12 năm 2021 của Chính phủ |
| --- |
| được sửa đổi, bổ sung bởi Nghị định số 80/2026/NĐ-CP. |
Căn cứ Luật Tổ chức Chính phủ;
"""


def test_vbhn_uses_explicit_publisher_in_footer_and_clean_markdown_title():
    text = CONSOLIDATED_DECREE + ("Nội dung điều khoản.\n" * 400)
    text += "**BỘ XÂY DỰNG XÁC THỰC VĂN BẢN HỢP NHẤT**\nSố: /VBHN-BXD Hà Nội, ngày tháng năm 2026"
    meta = parse_legal_metadata(text, "16.VBHN22.2026.pdf")
    assert meta["doc_type"] == "Văn bản hợp nhất"
    assert meta["doc_number"] == "22/VBHN-BXD"
    assert meta["issuing_authority"] == "Bộ Xây dựng"
    assert meta["issued_date"] is None  # Original decree date is not consolidation date.
    assert meta["official_title"] == "Quy định xử phạt vi phạm hành chính trong lĩnh vực giao thông đường thủy nội địa"
    assert "VPQH" not in meta["canonical_name"]
    assert "Văn phòng Quốc hội" not in meta["canonical_name"]
    assert "|" not in meta["citation"]
    assert "---" not in meta["citation"]
    assert "Căn cứ" not in meta["citation"]


def test_vbhn_unknown_publisher_stays_unknown():
    meta = parse_legal_metadata(CONSOLIDATED_DECREE, "16.VBHN22.2026.pdf")
    assert meta["issuing_authority"] is None
    assert meta["doc_number"] == "22/VBHN"
    assert "VPQH" not in meta["canonical_name"]
    assert "của" not in meta["canonical_name"].split(" — ")[0]


def test_vbhn_explicit_number_and_publisher_override_original_law_authority():
    text = "CHÍNH PHỦ\nVĂN BẢN HỢP NHẤT\nSố: 07/VBHN-BCA\nNGHỊ ĐỊNH\nQuy định thủ tục\nCăn cứ Luật Tổ chức Chính phủ;"
    meta = parse_legal_metadata(text, "consolidated.pdf")
    assert meta["doc_number"] == "07/VBHN-BCA"
    assert meta["issuing_authority"] == "Bộ Công an"
    assert "Chính phủ" not in meta["canonical_name"]


def test_vbhn_explicit_vpqh_header_retains_law_case():
    text = "VĂN PHÒNG QUỐC HỘI\nVĂN BẢN HỢP NHẤT\nLUẬT\nXỬ LÝ VI PHẠM HÀNH CHÍNH\nĐiều 1. Phạm vi"
    meta = parse_legal_metadata(text, "02. Văn bản hợp nhất số 90 Luật XLVPHC.pdf")
    assert meta["doc_number"] == "90/VBHN-VPQH"
    assert meta["issuing_authority"] == "Văn phòng Quốc hội"
    assert "Luật Xử lý vi phạm hành chính" in meta["canonical_name"]


def test_vbhn_filename_without_content_never_invents_law_or_issuer():
    meta = parse_legal_metadata("", "VBHN22.2026.pdf")
    assert meta["doc_number"] == "22/VBHN"
    assert meta["issuing_authority"] is None
    assert meta["canonical_name"] == "Văn bản hợp nhất số 22/VBHN"



def test_vbhn_footer_detects_consolidation_without_filename_hint():
    text = CONSOLIDATED_DECREE + ("Nội dung điều khoản.\n" * 400)
    text += "BỘ XÂY DỰNG XÁC THỰC VĂN BẢN HỢP NHẤT\nSố: 22/VBHN-BXD"
    meta = parse_legal_metadata(text, "document.pdf")
    assert meta["doc_type"] == "Văn bản hợp nhất"
    assert meta["doc_number"] == "22/VBHN-BXD"
    assert meta["issuing_authority"] == "Bộ Xây dựng"


def test_vbhn_explicit_filename_code_retains_number_and_unknown_publisher():
    meta = parse_legal_metadata("", "22-VBHN-XYZ.pdf")
    assert meta["doc_type"] == "Văn bản hợp nhất"
    assert meta["doc_number"] == "22/VBHN-XYZ"
    assert meta["issuing_authority"] is None
    assert "VPQH" not in meta["canonical_name"]



def test_vbhn_date_comes_from_its_code_not_underlying_decree():
    text = CONSOLIDATED_DECREE + ("Nội dung điều khoản.\n" * 400)
    text += "BỘ XÂY DỰNG XÁC THỰC VĂN BẢN HỢP NHẤT\nSố: 22/VBHN-BXD Hà Nội, ngày 20 tháng 6 năm 2026"
    meta = parse_legal_metadata(text, "16.VBHN22.2026.pdf")
    assert meta["issued_date"] == "20/06/2026"
    assert "ngày 20/06/2026" in meta["canonical_name"]



def test_multiline_amendment_title_keeps_referenced_document_after_cua():
    text = """NGHỊ ĐỊNH
Sửa đổi, bổ sung một số điều của
Nghị định số 136/2020/NĐ-CP ngày 24 tháng 11 năm 2020 của Chính phủ
Căn cứ Luật Tổ chức Chính phủ;
"""
    meta = parse_legal_metadata(text, "amendment.pdf")
    assert meta["official_title"] == "Sửa đổi, bổ sung một số điều của Nghị định số 136/2020/NĐ-CP ngày 24 tháng 11 năm 2020 của Chính phủ"
    assert "Căn cứ" not in meta["official_title"]
