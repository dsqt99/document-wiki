"""Tests for closed-predicate concept relations extraction and persistence."""

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.ai.mrp.mapper import EXTRACTION_PROMPT_TEMPLATE
from app.models.concept_relation import (
    ConceptPredicate,
    ConceptRelation,
    normalize_predicate,
    collect_concept_relations,
    persist_concept_relations,
    link_concept_relations_to_pages,
)


def test_extraction_prompt_specifies_closed_predicates():
    """Verify MAP prompt template enforces closed predicate set and evidence."""
    assert "la_mot" in EXTRACTION_PROMPT_TEMPLATE
    assert "thuoc" in EXTRACTION_PROMPT_TEMPLATE
    assert "quy_dinh" in EXTRACTION_PROMPT_TEMPLATE
    assert "ap_dung_cho" in EXTRACTION_PROMPT_TEMPLATE
    assert "lien_quan" in EXTRACTION_PROMPT_TEMPLATE
    assert "evidence" in EXTRACTION_PROMPT_TEMPLATE


def test_normalize_predicate():
    """Test standardizing closed predicates with alias mapping and safe fallback."""
    assert normalize_predicate("la_mot") == "la_mot"
    assert normalize_predicate("is_a") == "la_mot"
    assert normalize_predicate("is-a") == "la_mot"
    assert normalize_predicate("thuoc") == "thuoc"
    assert normalize_predicate("part_of") == "thuoc"
    assert normalize_predicate("quy_dinh") == "quy_dinh"
    assert normalize_predicate("regulates") == "quy_dinh"
    assert normalize_predicate("ap_dung_cho") == "ap_dung_cho"
    assert normalize_predicate("applies_to") == "ap_dung_cho"
    assert normalize_predicate("lien_quan") == "lien_quan"
    assert normalize_predicate("unknown_type") == "lien_quan"
    assert normalize_predicate("") == "lien_quan"


def test_collect_concept_relations():
    """Test gathering and deduplicating concept relations from chunk extracts."""
    chunk1 = MagicMock()
    chunk1.chunk_index = 0
    chunk1.extract_json = {
        "relations": [
            {
                "from": "Cảnh sát Giao thông",
                "to": "Công an Nhân dân",
                "type": "thuoc",
                "evidence": "Cảnh sát Giao thông là lực lượng trực thuộc Công an Nhân dân.",
            },
            {
                "from": "Nghị định 100",
                "to": "Người tham gia giao thông",
                "predicate": "ap_dung_cho",
                "evidence": "Nghị định 100 áp dụng cho người tham gia giao thông đường bộ.",
            },
        ]
    }

    chunk2 = MagicMock()
    chunk2.chunk_index = 1
    chunk2.extract_json = {
        "relations": [
            # Duplicate relation with higher detail evidence
            {
                "from": "Cảnh sát Giao thông",
                "to": "Công an Nhân dân",
                "predicate": "part_of",
                "evidence": "Lực lượng Cảnh sát Giao thông là một bộ phận của Công an Nhân dân Việt Nam.",
            }
        ]
    }

    relations = collect_concept_relations([chunk1, chunk2])

    assert len(relations) == 2
    # Check deduplication merged the "thuoc" relation and kept weight
    csgt_rel = next(r for r in relations if r["source_concept"] == "Cảnh sát Giao thông")
    assert csgt_rel["target_concept"] == "Công an Nhân dân"
    assert csgt_rel["predicate"] == "thuoc"
    assert csgt_rel["weight"] >= 2.0  # weight increases with co-occurrence

    nd100_rel = next(r for r in relations if r["source_concept"] == "Nghị định 100")
    assert nd100_rel["predicate"] == "ap_dung_cho"


@pytest.mark.asyncio
async def test_persist_concept_relations():
    """Test persisting concept relations to database."""
    session = AsyncMock()
    source_id = uuid.uuid4()
    raw_relations = [
        {
            "source_concept": "Cảnh sát giao thông",
            "target_concept": "Công an nhân dân",
            "predicate": "thuoc",
            "evidence": "Là lực lượng chuyên trách",
            "weight": 1.5,
        }
    ]

    persisted = await persist_concept_relations(session, source_id, raw_relations)

    assert len(persisted) == 1
    rel = persisted[0]
    assert rel.source_id == source_id
    assert rel.source_concept == "Cảnh sát giao thông"
    assert rel.predicate == "thuoc"
    session.add.assert_called_once()


@pytest.mark.asyncio
async def test_link_concept_relations_to_pages():
    """Test linking concept relations to created wiki page IDs."""
    session = AsyncMock()
    source_id = uuid.uuid4()

    rel1 = ConceptRelation(
        id=uuid.uuid4(),
        source_id=source_id,
        source_concept="Cảnh sát giao thông",
        target_concept="Công an nhân dân",
        predicate="thuoc",
    )

    page1 = MagicMock()
    page1.id = uuid.uuid4()
    page1.title = "Cảnh sát giao thông"
    page1.slug = "canh-sat-giao-thong"

    page2 = MagicMock()
    page2.id = uuid.uuid4()
    page2.title = "Công an nhân dân"
    page2.slug = "cong-an-nhan-dan"

    mock_result_rels = MagicMock()
    mock_result_rels.scalars.return_value.all.return_value = [rel1]

    mock_result_pages = MagicMock()
    mock_result_pages.scalars.return_value.all.return_value = [page1, page2]

    session.execute.side_effect = [mock_result_rels, mock_result_pages]

    linked_count = await link_concept_relations_to_pages(session, source_id)

    assert linked_count == 1
    assert rel1.source_page_id == page1.id
    assert rel1.target_page_id == page2.id
