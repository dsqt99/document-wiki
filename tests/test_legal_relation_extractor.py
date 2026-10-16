import pytest
from app.database.models import LegalRelationType
from app.services.legal_relation_extractor import (
    LegalRelationExtractor,
    ExtractedRelation,
)


def test_extract_amending_and_supplementing_relations():
    """Verify extracting amendment relations to a specific article of a decree."""
    text = (
        "Điều 1. Sửa đổi, bổ sung một số điều của Nghị định số 136/2020/NĐ-CP\n"
        "1. Sửa đổi, bổ sung Điều 5 của Nghị định số 136/2020/NĐ-CP như sau:\n"
        "\"Điều 5. Điều kiện an toàn...\"\n"
        "2. Bổ sung Điều 5a vào sau Điều 5 của Nghị định số 136/2020/NĐ-CP như sau:"
    )

    extractor = LegalRelationExtractor()
    relations = extractor.extract_from_text(text, default_doc_number="50/2024/NĐ-CP")

    # Should find relations targeting 136/2020/NĐ-CP Điều 5 and Điều 5a
    sua_doi = [r for r in relations if r.relation_type == LegalRelationType.SUA_DOI]
    bo_sung = [r for r in relations if r.relation_type == LegalRelationType.BO_SUNG]

    assert len(sua_doi) >= 1
    assert any(r.target_doc_number == "136/2020/NĐ-CP" and r.target_article_number == "5" for r in sua_doi)

    assert len(bo_sung) >= 1
    assert any(r.target_doc_number == "136/2020/NĐ-CP" and r.target_article_number == "5a" for r in bo_sung)


def test_extract_repeal_relations():
    """Verify extracting repeal relations (bãi bỏ điều, khoản)."""
    text = (
        "Điều 2. Bãi bỏ một số quy định\n"
        "1. Bãi bỏ khoản 2 Điều 10 của Nghị định số 136/2020/NĐ-CP.\n"
        "2. Bãi bỏ Điểm c Khoản 3 Điều 15 của Nghị định số 136/2020/NĐ-CP."
    )

    extractor = LegalRelationExtractor()
    relations = extractor.extract_from_text(text, default_doc_number="50/2024/NĐ-CP")

    repeals = [r for r in relations if r.relation_type == LegalRelationType.BAI_BO]
    assert len(repeals) >= 2

    # Check Clause 2 Article 10
    r1 = next((r for r in repeals if r.target_article_number == "10"), None)
    assert r1 is not None
    assert r1.target_doc_number == "136/2020/NĐ-CP"
    assert r1.target_clause_number == "2"

    # Check Article 15
    r2 = next((r for r in repeals if r.target_article_number == "15"), None)
    assert r2 is not None
    assert r2.target_doc_number == "136/2020/NĐ-CP"
    assert r2.target_clause_number == "3"


def test_extract_legal_basis_relations():
    """Verify extracting legal basis (căn cứ ban hành) in document preamble."""
    preamble = (
        "Căn cứ Luật Tổ chức Chính phủ ngày 19 tháng 6 năm 2015;\n"
        "Căn cứ Luật Phòng cháy và chữa cháy số 27/2001/QH10;\n"
        "Căn cứ Luật sửa đổi, bổ sung một số điều của Luật Phòng cháy và chữa cháy số 40/2013/QH13;\n"
        "Theo đề nghị của Bộ trưởng Bộ Công an;"
    )

    extractor = LegalRelationExtractor()
    relations = extractor.extract_preamble_basis(preamble)

    can_cu = [r for r in relations if r.relation_type == LegalRelationType.CAN_CU]
    assert len(can_cu) >= 2

    doc_numbers = {r.target_doc_number for r in can_cu if r.target_doc_number}
    assert "27/2001/QH10" in doc_numbers
    assert "40/2013/QH13" in doc_numbers


def test_extract_reference_citation_relations():
    """Verify extracting citation/reference to other legal documents."""
    text = (
        "Hồ sơ, trình tự kiểm tra an toàn phòng cháy thực hiện theo quy định tại "
        "Điều 16 Nghị định số 136/2020/NĐ-CP."
    )

    extractor = LegalRelationExtractor()
    relations = extractor.extract_from_text(text)

    citations = [r for r in relations if r.relation_type == LegalRelationType.DAN_CHIEU]
    assert len(citations) >= 1
    assert citations[0].target_doc_number == "136/2020/NĐ-CP"
    assert citations[0].target_article_number == "16"


def test_doc_level_replace_and_repeal():
    """Whole-document replacement / repeal (no target article) incl. yearless numbers."""
    text = (
        "Điều 3. Hiệu lực thi hành\n"
        "1. Quyết định này thay thế Quyết định số 1520/QĐ-BTC ngày 01/08/2023.\n"
        "2. Bãi bỏ Thông tư số 12/2019/TT-BTC.\n"
        "3. Quyết định số 99/QĐ-BTC hết hiệu lực kể từ ngày ký."
    )
    relations = LegalRelationExtractor().extract_from_text(text, default_doc_number="2777/QĐ-BTC")
    doc_level = {
        (r.relation_type, r.target_doc_number)
        for r in relations
        if r.target_article_number is None
    }
    assert (LegalRelationType.THAY_THE, "1520/QĐ-BTC") in doc_level
    assert (LegalRelationType.BAI_BO, "12/2019/TT-BTC") in doc_level
    assert (LegalRelationType.BAI_BO, "99/QĐ-BTC") in doc_level
    assert all(r.target_doc_number != "2777/QĐ-BTC" for r in relations)


def test_clause_repeal_is_not_doc_level():
    text = "Bãi bỏ khoản 2 Điều 10 của Nghị định số 136/2020/NĐ-CP."
    relations = LegalRelationExtractor().extract_from_text(text, default_doc_number="50/2024/NĐ-CP")
    assert not [r for r in relations if r.target_article_number is None and r.relation_type == LegalRelationType.BAI_BO]
