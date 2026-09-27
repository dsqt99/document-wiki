import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.database.models import (
    LegalUnit,
    LegalRelation,
    LegalUnitType,
    LegalRelationType,
    WikiPage,
)
from app.services.retrieval_service import (
    expand_graph_neighbors,
    format_graph_neighbors_section,
    unified_search,
)


@pytest.mark.asyncio
async def test_expand_graph_neighbors_incoming_amendment():
    """Verify 1-hop expansion retrieves incoming amending regulations."""
    target_art_id = uuid.uuid4()
    mod_art_id = uuid.uuid4()
    wiki_page_id = uuid.uuid4()

    target_unit = LegalUnit(
        id=target_art_id,
        wiki_page_id=wiki_page_id,
        source_id=uuid.uuid4(),
        unit_type=LegalUnitType.ARTICLE,
        unit_number="5",
        title="Điều kiện an toàn PCCC đối với cơ sở",
        doc_number="136/2020/NĐ-CP",
        content="Điều 5. Điều kiện an toàn về phòng cháy và chữa cháy...",
    )

    mod_unit = LegalUnit(
        id=mod_art_id,
        source_id=uuid.uuid4(),
        unit_type=LegalUnitType.ARTICLE,
        unit_number="1",
        title="Sửa đổi, bổ sung một số điều của Nghị định 136/2020",
        doc_number="50/2024/NĐ-CP",
        content="1. Sửa đổi, bổ sung Điều 5 như sau: ...",
    )

    rel = LegalRelation(
        id=uuid.uuid4(),
        source_unit_id=mod_art_id,
        target_unit_id=target_art_id,
        target_doc_number="136/2020/NĐ-CP",
        target_article_number="5",
        relation_type=LegalRelationType.SUA_DOI,
        quote_context="Sửa đổi, bổ sung điểm a khoản 1 Điều 5",
        is_effective=True,
    )
    rel.source_unit = mod_unit
    rel.target_unit = target_unit

    session = AsyncMock()
    # Mocking lookup of LegalUnit by wiki_page_id
    mock_units_exec = MagicMock()
    mock_units_exec.scalars.return_value.all.return_value = [target_unit]
    
    # Mocking lookup of relations
    mock_rel_exec = MagicMock()
    mock_rel_exec.scalars.return_value.all.return_value = [rel]

    session.execute = AsyncMock(side_effect=[mock_units_exec, mock_rel_exec])

    neighbors = await expand_graph_neighbors(session, page_ids=[wiki_page_id])
    assert len(neighbors) == 1
    neighbor = neighbors[0]
    assert neighbor["relation_type"] == "sua_doi"
    assert neighbor["doc_number"] == "50/2024/NĐ-CP"
    assert neighbor["article_number"] == "1"
    assert "Sửa đổi" in neighbor["title"]
    assert neighbor["direction"] == "incoming"


@pytest.mark.asyncio
async def test_expand_graph_neighbors_outgoing_guidance():
    """Verify 1-hop expansion retrieves outgoing guidance or references."""
    source_art_id = uuid.uuid4()
    wiki_page_id = uuid.uuid4()

    source_unit = LegalUnit(
        id=source_art_id,
        wiki_page_id=wiki_page_id,
        source_id=uuid.uuid4(),
        unit_type=LegalUnitType.ARTICLE,
        unit_number="7",
        title="Quy định hướng dẫn",
        doc_number="149/2020/TT-BCA",
        content="Thông tư này hướng dẫn chi tiết Nghị định 136/2020...",
    )

    rel = LegalRelation(
        id=uuid.uuid4(),
        source_unit_id=source_art_id,
        target_unit_id=None,
        target_doc_number="136/2020/NĐ-CP",
        target_article_number="15",
        relation_type=LegalRelationType.HUONG_DAN,
        quote_context="Hướng dẫn thi hành Điều 15 Nghị định 136/2020/NĐ-CP",
        is_effective=True,
    )
    rel.source_unit = source_unit
    rel.target_unit = None

    session = AsyncMock()
    mock_units_exec = MagicMock()
    mock_units_exec.scalars.return_value.all.return_value = [source_unit]

    mock_rel_exec = MagicMock()
    mock_rel_exec.scalars.return_value.all.return_value = [rel]

    session.execute = AsyncMock(side_effect=[mock_units_exec, mock_rel_exec])

    neighbors = await expand_graph_neighbors(session, page_ids=[wiki_page_id])
    assert len(neighbors) == 1
    neighbor = neighbors[0]
    assert neighbor["relation_type"] == "huong_dan"
    assert neighbor["doc_number"] == "136/2020/NĐ-CP"
    assert neighbor["article_number"] == "15"
    assert neighbor["direction"] == "outgoing"


def test_format_graph_neighbors_section():
    """Verify markdown formatting for graph neighbors."""
    neighbors = [
        {
            "relation_type": "sua_doi",
            "doc_number": "50/2024/NĐ-CP",
            "article_number": "1",
            "title": "Sửa đổi Điều 5",
            "quote_context": "Sửa đổi, bổ sung điểm a khoản 1 Điều 5",
            "direction": "incoming",
        },
        {
            "relation_type": "huong_dan",
            "doc_number": "149/2020/TT-BCA",
            "article_number": "7",
            "title": "Hướng dẫn thi hành",
            "quote_context": "Chi tiết tại Thông tư 149/2020",
            "direction": "outgoing",
        }
    ]

    formatted = format_graph_neighbors_section(neighbors)
    assert "🔗 **VĂN BẢN & ĐIỀU KHOẢN LIÊN QUAN TRÊN ĐỒ THỊ PHÁP LÝ**" in formatted
    assert "50/2024/NĐ-CP" in formatted
    assert "149/2020/TT-BCA" in formatted
    assert "Sửa đổi, bổ sung" in formatted


@pytest.mark.asyncio
async def test_unified_search_integration():
    """Verify unified_search orchestrates exact routing, hybrid arms, and reranking."""
    session = AsyncMock()
    page_id = uuid.uuid4()
    mock_page = WikiPage(
        id=page_id,
        slug="dieu-5-nghi-dinh-136-2020",
        title="Điều 5. Điều kiện an toàn",
        content_md="Nội dung điều 5",
        summary="Tóm tắt điều 5",
    )

    wiki_hit = {
        "page": mock_page,
        "rrf": 0.03,
        "cosine": 0.85,
        "heading_path": "Chương I > Điều 5",
        "fts_matched": True,
    }

    from unittest.mock import patch

    with patch("app.services.wiki_service.search_pages_hybrid", new_callable=AsyncMock) as mock_wp, \
         patch("app.services.wiki_service.search_source_chunks_hybrid", new_callable=AsyncMock) as mock_src, \
         patch("app.services.retrieval_service.route_exact_legal_query", new_callable=AsyncMock) as mock_route, \
         patch("app.services.retrieval_service.expand_graph_neighbors", new_callable=AsyncMock) as mock_graph:

        mock_wp.return_value = [wiki_hit]
        mock_src.return_value = []
        mock_route.return_value = {"matched": True, "doc_number": "136/2020/NĐ-CP", "article_number": "5"}
        mock_graph.return_value = [{"doc_number": "50/2024/NĐ-CP", "relation_type": "sua_doi"}]

        res = await unified_search(
            session=session,
            query="Điều 5 Nghị định 136/2020",
            query_embedding=[0.1] * 768,
            top_k=5,
            apply_reranker=True,
        )

        assert res["exact_match"] is not None
        assert res["exact_match"]["doc_number"] == "136/2020/NĐ-CP"
        assert len(res["ranked_results"]) == 1
        assert res["ranked_results"][0][0] == "wiki"
        assert len(res["graph_neighbors"]) == 1
        assert res["graph_neighbors"][0]["doc_number"] == "50/2024/NĐ-CP"

