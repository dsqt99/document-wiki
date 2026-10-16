import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.database.models import (
    LegalUnit,
    LegalRelation,
    LegalUnitType,
    LegalRelationType,
)
from app.services.legal_service import (
    get_legal_context_with_hierarchy,
    get_legal_unit_validity_warnings,
    format_legal_validity_warning_callout,
)


@pytest.mark.asyncio
async def test_get_legal_context_with_hierarchy():
    """Verify parent-child context expansion for a clause unit."""
    art_id = uuid.uuid4()
    clause_id = uuid.uuid4()

    art_unit = LegalUnit(
        id=art_id,
        source_id=uuid.uuid4(),
        unit_type=LegalUnitType.ARTICLE,
        unit_number="5",
        title="Điều kiện an toàn PCCC",
        full_path="Chương I > Điều 5",
        content="Điều 5. Điều kiện an toàn PCCC đối với cơ sở...",
        doc_number="136/2020/NĐ-CP",
    )

    clause_unit = LegalUnit(
        id=clause_id,
        source_id=art_unit.source_id,
        unit_type=LegalUnitType.CLAUSE,
        unit_number="1",
        full_path="Chương I > Điều 5 > Khoản 1",
        content="1. Cơ sở thuộc danh mục phải bảo đảm các điều kiện sau...",
        parent_unit_id=art_id,
        doc_number="136/2020/NĐ-CP",
    )
    clause_unit.parent = art_unit

    session = AsyncMock()
    session.get = AsyncMock(side_effect=lambda model, uid: clause_unit if uid == clause_id else art_unit)

    ctx = await get_legal_context_with_hierarchy(session, clause_id)
    assert ctx["unit_type"] == LegalUnitType.CLAUSE
    assert ctx["unit_number"] == "1"
    assert "Chương I > Điều 5 > Khoản 1" in ctx["full_path"]
    assert ctx["parent_article"] is not None
    assert ctx["parent_article"]["number"] == "5"
    assert "Điều kiện an toàn PCCC đối với cơ sở" in ctx["parent_article"]["content"]


@pytest.mark.asyncio
async def test_get_legal_unit_validity_warnings():
    """Verify detecting amendments and repeals from incoming relations."""
    target_art_id = uuid.uuid4()
    source_mod_id = uuid.uuid4()

    target_unit = LegalUnit(
        id=target_art_id,
        source_id=uuid.uuid4(),
        unit_type=LegalUnitType.ARTICLE,
        unit_number="5",
        title="Điều kiện an toàn",
        doc_number="136/2020/NĐ-CP",
    )

    mod_unit = LegalUnit(
        id=source_mod_id,
        source_id=uuid.uuid4(),
        unit_type=LegalUnitType.ARTICLE,
        unit_number="1",
        title="Sửa đổi Điều 5",
        doc_number="50/2024/NĐ-CP",
    )

    rel = LegalRelation(
        id=uuid.uuid4(),
        source_unit_id=source_mod_id,
        target_unit_id=target_art_id,
        target_doc_number="136/2020/NĐ-CP",
        target_article_number="5",
        relation_type=LegalRelationType.SUA_DOI,
        quote_context="Sửa đổi, bổ sung Điều 5 như sau:",
        is_effective=True,
    )
    rel.source_unit = mod_unit

    session = AsyncMock()
    mock_execute = MagicMock()
    mock_execute.scalars.return_value.all.return_value = [rel]
    session.execute = AsyncMock(return_value=mock_execute)

    warnings = await get_legal_unit_validity_warnings(session, target_art_id)
    assert len(warnings) == 1
    w = warnings[0]
    assert w["relation_type"] == "sua_doi"
    assert w["modifying_doc_number"] == "50/2024/NĐ-CP"
    assert w["modifying_article_number"] == "1"

    # Test markdown formatting
    callout = format_legal_validity_warning_callout(warnings)
    assert "> [!WARNING]" in callout
    assert "50/2024/NĐ-CP" in callout
    assert "sửa đổi, bổ sung" in callout.lower()


def test_format_legal_validity_warning_callout_multiple():
    """Verify formatting multiple warnings (amendment + repeal)."""
    warnings = [
        {
            "relation_type": "sua_doi",
            "modifying_doc_number": "50/2024/NĐ-CP",
            "modifying_article_number": "1",
            "quote_context": "Sửa đổi khoản 1...",
        },
        {
            "relation_type": "bai_bo",
            "modifying_doc_number": "50/2024/NĐ-CP",
            "modifying_article_number": "2",
            "quote_context": "Bãi bỏ khoản 2...",
        },
    ]
    callout = format_legal_validity_warning_callout(warnings)
    assert "> [!WARNING]" in callout
    assert "sửa đổi, bổ sung" in callout
    assert "bãi bỏ" in callout
    assert "50/2024/NĐ-CP" in callout
