import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.database.models import (
    LegalUnit,
    LegalRelation,
    LegalUnitType,
    LegalRelationType,
    Source,
    WikiPage,
)
from app.services.legal_service import ingest_legal_graph
from app.services.legal_hierarchy_parser import LegalHierarchyParser


@pytest.mark.asyncio
async def test_ingest_legal_graph_creates_units_and_relations():
    """Verify that ingest_legal_graph creates hierarchical units and extracts relations."""
    source_id = uuid.uuid4()
    source = Source(
        id=source_id,
        title="Nghị định 50/2024/NĐ-CP",
        status="processing",
    )

    doc_text = (
        "Điều 1. Sửa đổi, bổ sung một số điều của Nghị định số 136/2020/NĐ-CP\n"
        "1. Sửa đổi, bổ sung Điều 5 như sau:\n"
        "\"Điều 5. Điều kiện an toàn PCCC\"\n"
        "2. Bổ sung Điều 5a như sau:\n"
        "\"Điều 5a. Kiểm định PCCC\"\n"
        "Điều 2. Hiệu lực thi hành\n"
        "Nghị định này có hiệu lực từ 15/5/2024."
    )

    parser = LegalHierarchyParser()
    tree = parser.parse(doc_text)
    articles_data = []
    for art in tree.get_all_articles():
        articles_data.append({
            "num": art.number,
            "title": art.title,
            "heading": f"Điều {art.number}. {art.title}",
            "content_md": art.content,
            "slug": f"dieu-{art.number}-slug",
            "clauses": [
                {
                    "number": c.number,
                    "content": c.content,
                    "points": [{"letter": p.letter, "content": p.content} for p in c.points],
                }
                for c in art.clauses
            ],
        })

    # Mock AsyncSession
    added_objects = []
    session = AsyncMock()
    session.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))
    session.execute = AsyncMock()

    result = await ingest_legal_graph(
        session=session,
        source=source,
        articles=articles_data,
        preamble="Căn cứ Luật Phòng cháy và chữa cháy số 27/2001/QH10;",
        doc_number="50/2024/NĐ-CP",
        art_page_map={"dieu-1-slug": uuid.uuid4(), "dieu-2-slug": uuid.uuid4()},
    )

    units = [obj for obj in added_objects if isinstance(obj, LegalUnit)]
    relations = [obj for obj in added_objects if isinstance(obj, LegalRelation)]

    assert len(units) >= 2  # At least Điều 1 and Điều 2
    assert any(u.unit_number == "1" and u.unit_type == LegalUnitType.ARTICLE for u in units)
    assert any(u.unit_number == "2" and u.unit_type == LegalUnitType.ARTICLE for u in units)

    # Relations extracted from Điều 1: Sửa đổi Điều 5, Bổ sung Điều 5a
    assert len(relations) >= 1
    assert any(r.relation_type in (LegalRelationType.SUA_DOI, LegalRelationType.BO_SUNG) for r in relations)
