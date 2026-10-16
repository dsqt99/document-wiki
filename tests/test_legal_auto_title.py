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
