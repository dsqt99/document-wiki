import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.database.models import LegalUnit, LegalUnitType
from app.services.legal_route_service import (
    parse_legal_query_intent,
    route_exact_legal_query,
    LegalQueryIntent,
)


def test_parse_legal_query_intent():
    """Verify parsing exact article and document citations from natural query."""
    q1 = "Điều 5 Nghị định 136/2020"
    intent1 = parse_legal_query_intent(q1)
    assert intent1 is not None
    assert intent1.is_exact_legal_lookup is True
    assert intent1.article_number == "5"
    assert "136/2020" in intent1.doc_number

    q2 = "Khoản 2 Điều 15 của Nghị định số 50/2024/NĐ-CP"
    intent2 = parse_legal_query_intent(q2)
    assert intent2 is not None
    assert intent2.is_exact_legal_lookup is True
    assert intent2.article_number == "15"
    assert intent2.clause_number == "2"
    assert "50/2024" in intent2.doc_number

    q3 = "Hồ sơ đề nghị cấp phép phòng cháy chữa cháy gồm những gì?"
    intent3 = parse_legal_query_intent(q3)
    assert intent3 is None


@pytest.mark.asyncio
async def test_route_exact_legal_query_hit():
    """Verify exact legal query routes directly to LegalUnit and enriches with validity warnings."""
    unit_id = uuid.uuid4()
    mock_unit = LegalUnit(
        id=unit_id,
        source_id=uuid.uuid4(),
        unit_type=LegalUnitType.ARTICLE,
        unit_number="5",
        title="Điều kiện an toàn PCCC đối với cơ sở",
        content="Nội dung điều 5...",
        full_path="Chương I > Điều 5",
        doc_number="136/2020/NĐ-CP",
    )

    session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalars.return_value.first.return_value = mock_unit
    session.execute = AsyncMock(return_value=mock_res)

    result = await route_exact_legal_query(session, "Điều 5 Nghị định 136/2020/NĐ-CP")
    assert result is not None
    assert result["found"] is True
    assert result["unit_number"] == "5"
    assert "Điều kiện an toàn PCCC" in result["title"]
    assert "136/2020/NĐ-CP" in result["doc_number"]
