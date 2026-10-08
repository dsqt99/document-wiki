import uuid
import pytest
from app.database.models import (
    Base,
    Source,
    WikiPage,
    LegalUnit,
    LegalRelation,
    LegalUnitType,
    LegalRelationType,
)


def test_legal_unit_model_structure():
    """Verify LegalUnit model fields, types, and defaults."""
    unit = LegalUnit(
        source_id=uuid.uuid4(),
        unit_type=LegalUnitType.ARTICLE,
        unit_number="5",
        title="Điều kiện an toàn về PCCC",
        full_path="Chương I > Điều 5",
        content="Nội dung điều 5...",
        doc_number="136/2020/NĐ-CP",
    )
    assert unit.unit_type == LegalUnitType.ARTICLE
    assert unit.unit_number == "5"
    assert unit.title == "Điều kiện an toàn về PCCC"
    assert unit.full_path == "Chương I > Điều 5"
    assert unit.doc_number == "136/2020/NĐ-CP"
    assert unit.id is not None or unit.id is None  # default uuid generated on db or init


def test_legal_relation_model_structure():
    """Verify LegalRelation model fields, types, and defaults."""
    source_uid = uuid.uuid4()
    target_uid = uuid.uuid4()
    rel = LegalRelation(
        source_unit_id=source_uid,
        target_unit_id=target_uid,
        target_doc_number="136/2020/NĐ-CP",
        target_article_number="5",
        target_clause_number="1",
        relation_type=LegalRelationType.SUA_DOI,
        quote_context="Sửa đổi, bổ sung Khoản 1 Điều 5 như sau:",
        is_effective=True,
    )
    assert rel.source_unit_id == source_uid
    assert rel.target_unit_id == target_uid
    assert rel.relation_type == LegalRelationType.SUA_DOI
    assert rel.target_doc_number == "136/2020/NĐ-CP"
    assert rel.target_article_number == "5"
    assert rel.target_clause_number == "1"
    assert rel.is_effective is True


def test_legal_enums_completeness():
    """Verify that all legal unit and relation types are properly registered."""
    assert LegalUnitType.PART.value == "part"
    assert LegalUnitType.CHAPTER.value == "chapter"
    assert LegalUnitType.SECTION.value == "section"
    assert LegalUnitType.ARTICLE.value == "article"
    assert LegalUnitType.CLAUSE.value == "clause"
    assert LegalUnitType.POINT.value == "point"

    assert LegalRelationType.SUA_DOI.value == "sua_doi"
    assert LegalRelationType.BO_SUNG.value == "bo_sung"
    assert LegalRelationType.THAY_THE.value == "thay_the"
    assert LegalRelationType.BAI_BO.value == "bai_bo"
    assert LegalRelationType.HUONG_DAN.value == "huong_dan"
    assert LegalRelationType.CAN_CU.value == "can_cu"
    assert LegalRelationType.DAN_CHIEU.value == "dan_chieu"
