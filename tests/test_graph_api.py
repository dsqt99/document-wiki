"""Tests for /api/wiki/graph endpoint with typed relation edges and filters."""

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.routers.wiki import get_wiki_graph


@pytest.mark.asyncio
async def test_wiki_graph_returns_typed_edges():
    """Verify /api/wiki/graph returns edges with type, label, weight, and evidence."""
    mock_db = AsyncMock()

    # Mock count
    mock_count_res = MagicMock()
    mock_count_res.scalar.return_value = 2

    # Mock nodes
    mock_nodes_res = MagicMock()
    mock_nodes_res.all.return_value = [
        MagicMock(slug="page-a", title="Page A", page_type="concept", status="mature", scope_type="global", scope_id=None, scope_name=None),
        MagicMock(slug="page-b", title="Page B", page_type="concept", status="mature", scope_type="global", scope_id=None, scope_name=None),
    ]

    # Mock wikilinks
    mock_wikilinks_res = MagicMock()
    mock_wikilinks_res.all.return_value = [
        MagicMock(from_slug="page-a", to_slug="page-b")
    ]

    # Mock concept relations
    mock_concept_res = MagicMock()
    mock_concept_res.all.return_value = [
        MagicMock(
            from_slug="page-a",
            to_slug="page-b",
            predicate="la_mot",
            evidence="Page A là một dạng của Page B",
            weight=1.5,
            source_concept="Page A",
            target_concept="Page B",
        )
    ]

    # Mock legal relations
    mock_legal_res = MagicMock()
    mock_legal_res.all.return_value = [
        MagicMock(
            from_slug="page-a",
            to_slug="page-b",
            relation_type="sua_doi",
            quote_context="Sửa đổi Điều 5",
            is_effective=True,
            target_doc_number="100/2019/NĐ-CP",
        )
    ]

    mock_db.execute.side_effect = [
        mock_count_res,
        mock_nodes_res,
        mock_wikilinks_res,
        mock_concept_res,
        mock_legal_res,
    ]

    mock_user = MagicMock()
    mock_user.role = "admin"
    mock_user.department_id = None

    result = await get_wiki_graph(
        slug=None,
        depth=1,
        offset=0,
        limit=100,
        edge_type=None,
        db=mock_db,
        user=mock_user,
    )

    assert "nodes" in result
    assert "edges" in result
    edges = result["edges"]

    # Must contain wikilink, concept, and legal edges
    types = {e["type"] for e in edges}
    assert "wikilink" in types
    assert "concept" in types
    assert "legal" in types

    # Check concept edge structure
    concept_edge = next(e for e in edges if e["type"] == "concept")
    assert concept_edge["label"] == "la_mot"
    assert concept_edge["weight"] == 1.5
    assert "Page A là một dạng" in concept_edge["evidence"]

    # Check legal edge structure
    legal_edge = next(e for e in edges if e["type"] == "legal")
    assert legal_edge["label"] == "sua_doi"
    assert "Sửa đổi Điều 5" in legal_edge["evidence"]


@pytest.mark.asyncio
async def test_wiki_graph_filters_by_edge_type():
    """Verify /api/wiki/graph filters edges when edge_type query param is provided."""
    mock_db = AsyncMock()

    mock_count_res = MagicMock()
    mock_count_res.scalar.return_value = 1
    mock_nodes_res = MagicMock()
    mock_nodes_res.all.return_value = [
        MagicMock(slug="page-a", title="Page A", page_type="concept", status="mature", scope_type="global", scope_id=None, scope_name=None)
    ]
    mock_concept_res = MagicMock()
    mock_concept_res.all.return_value = [
        MagicMock(
            from_slug="page-a",
            to_slug="page-b",
            predicate="thuoc",
            evidence="Thuộc về hệ thống",
            weight=1.0,
            source_concept="Page A",
            target_concept="Page B",
        )
    ]

    mock_db.execute.side_effect = [
        mock_count_res,
        mock_nodes_res,
        mock_concept_res,
    ]

    mock_user = MagicMock()
    mock_user.role = "admin"
    mock_user.department_id = None

    result = await get_wiki_graph(
        slug=None,
        depth=1,
        offset=0,
        limit=100,
        edge_type="concept",
        db=mock_db,
        user=mock_user,
    )

    edges = result["edges"]
    assert len(edges) == 1
    assert edges[0]["type"] == "concept"
    assert edges[0]["label"] == "thuoc"
