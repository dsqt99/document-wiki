"""Shared runtime policy and explicit degradation, independent of live providers."""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import retrieval_service, wiki_reranker, wiki_search_service


class Savepoint:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


def session():
    db = AsyncMock()
    db.begin_nested = MagicMock(side_effect=Savepoint)
    rows = MagicMock()
    rows.scalars.return_value.all.return_value = []
    db.execute.return_value = rows
    return db


def page_hit():
    page = SimpleNamespace(id=uuid.uuid4(), title="PCCC", slug="pccc", summary="PCCC", content_md="PCCC")
    return {"page": page, "chunk_text": "PCCC", "rrf": .03, "fts_matched": True, "cosine": None}


@pytest.mark.asyncio
async def test_portal_and_combined_search_share_model_threshold_and_strict_filter():
    db, hit = session(), page_hit()
    config = {"wiki_rerank_enabled": "true", "wiki_rerank_threshold": ".7"}
    scorer = SimpleNamespace(score=AsyncMock(return_value=[.65]))
    with patch.object(wiki_reranker.ConfigService, "get", new=AsyncMock(side_effect=lambda key: config.get(key))), \
         patch.object(wiki_reranker, "build_scorer", new=AsyncMock(return_value=scorer)) as build, \
         patch("app.ai.registry.ProviderRegistry.get_embedding", new=AsyncMock()) as embedding, \
         patch("app.services.wiki_service.search_pages_hybrid", new=AsyncMock(return_value=[hit])), \
         patch("app.services.wiki_service.search_source_chunks_hybrid", new=AsyncMock(return_value=[])), \
         patch.object(retrieval_service, "route_exact_legal_query", new=AsyncMock(return_value={"content": "exact"})), \
         patch.object(retrieval_service, "expand_graph_neighbors", new=AsyncMock(return_value=[])):
        embedding.return_value.embed = AsyncMock(return_value=[.1])
        portal = await wiki_search_service.search(db, "PCCC")
        combined = await retrieval_service.unified_search(db, "PCCC", [.1])
    assert portal["items"] == []
    assert combined["ranked_results"] == []
    assert combined["exact_match"] == {"content": "exact"}
    assert portal["search"]["threshold"] == combined["search"]["threshold"] == .7
    assert build.await_count == 2


@pytest.mark.asyncio
async def test_portal_embedding_failure_runs_lexical_and_exposes_warning():
    db, hit = session(), page_hit()
    with patch.object(wiki_reranker.ConfigService, "get", new=AsyncMock(side_effect=lambda key: {"wiki_rerank_enabled": "false", "wiki_rerank_threshold": ".7"}.get(key))), \
         patch("app.ai.registry.ProviderRegistry.get_embedding", new=AsyncMock(side_effect=ConnectionError("secret"))), \
         patch("app.services.wiki_service.search_pages_hybrid", new=AsyncMock(return_value=[hit])) as hybrid:
        result = await wiki_search_service.search(db, "PCCC")
    assert len(result["items"]) == 1
    assert hybrid.call_args.args[1] is None
    assert result["search"]["retrieval_mode"] == "lexical_fallback"
    assert result["search"]["warning"] and "secret" not in result["search"]["warning"]


@pytest.mark.asyncio
async def test_combined_reranker_failure_preserves_both_arms_and_acl_without_fake_scores():
    db, hit = session(), page_hit()
    sid, owner = uuid.uuid4(), uuid.uuid4()
    source_hit = {"source": SimpleNamespace(id=sid, title="Original"),
                  "chunk": SimpleNamespace(text="Original PCCC", chunk_index=0),
                  "rrf": .04, "fts_matched": True, "cosine": None}
    allowed = {str(sid)}
    config = {"wiki_rerank_enabled": "true", "wiki_rerank_threshold": ".7"}
    with patch.object(wiki_reranker.ConfigService, "get", new=AsyncMock(side_effect=lambda key: config.get(key))), \
         patch.object(wiki_reranker, "build_scorer", new=AsyncMock(side_effect=ConnectionError("secret"))), \
         patch("app.services.wiki_service.search_pages_hybrid", new=AsyncMock(return_value=[hit])) as wiki, \
         patch("app.services.wiki_service.search_source_chunks_hybrid", new=AsyncMock(return_value=[source_hit])) as source, \
         patch.object(retrieval_service, "route_exact_legal_query", new=AsyncMock(return_value={"content": "exact"})) as exact, \
         patch.object(retrieval_service, "expand_graph_neighbors", new=AsyncMock(return_value=[])) as graph:
        result = await retrieval_service.unified_search(db, "PCCC", None, allowed_source_ids=allowed,
            department_ids=[sid], clearance="INTERNAL", page_filter="filter", personal_owner_id=owner)
    assert {kind for kind, _, _ in result["ranked_results"]} == {"wiki", "source"}
    assert all("rerank_score" not in item for _, _, item in result["ranked_results"])
    assert result["rerank_mode"] == "hybrid_fallback"
    assert result["search"]["threshold"] is None
    assert result["search"]["retrieval_mode"] == "lexical_fallback"
    assert result["search"]["warning"] and "secret" not in result["search"]["warning"]
    assert exact.call_args.kwargs["allowed_source_ids"] == allowed
    assert source.call_args.kwargs["allowed_source_ids"] == allowed
    assert graph.call_args.kwargs["allowed_source_ids"] == allowed
    assert wiki.call_args.kwargs["page_filter"] == "filter"
    assert wiki.call_args.kwargs["personal_owner_id"] == owner
    assert wiki.call_args.kwargs["clearance"] == "INTERNAL"


@pytest.mark.asyncio
async def test_disabled_config_never_constructs_scorer():
    with patch.object(wiki_reranker.ConfigService, "get", new=AsyncMock(return_value="false")), \
         patch.object(wiki_reranker, "build_scorer", new=AsyncMock()) as build:
        result = await wiki_reranker.configured_rank_candidates(session(), "PCCC", [{"text": "PCCC"}])
    assert result.mode == "hybrid"
    assert result.threshold is None
    build.assert_not_called()


@pytest.mark.asyncio
async def test_portal_header_identifies_embedding_failure_without_claiming_reranker_failure():
    from fastapi import Response
    from app.routers import wiki
    response = Response()
    data = {"items": [], "search": {"mode": "hybrid", "retrieval_mode": "lexical_fallback",
            "warning": "embedding unavailable", "warning_codes": ["embedding_unavailable"]}}
    with patch.object(wiki_search_service, "search", new=AsyncMock(return_value=data)), \
         patch.object(wiki, "_scope_names", new=AsyncMock(return_value={})), \
         patch.object(wiki, "_page_read_filter", return_value=None), \
         patch.object(wiki, "_is_admin", return_value=True):
        await wiki.search_wiki(q="PCCC", limit=10, response=response, db=session(), user=SimpleNamespace())
    assert response.headers['X-Wiki-Retrieval-Mode'] == 'lexical_fallback'
    assert response.headers['X-Wiki-Search-Warning'] == 'embedding_unavailable'


def test_hybrid_source_eligibility_keeps_extracted_failures_and_legacy_indexed_rows():
    from sqlalchemy import create_engine, event, select
    from app.database.models import Source
    from app.services._wiki_search import _source_conditions
    engine = create_engine('sqlite://')
    event.listen(engine, 'connect', lambda connection, _: connection.create_function(
        'btrim', 2, lambda text, chars: text.strip(chars) if text is not None else None))
    rows = [
        (uuid.uuid4(), 'error', 'error', 'usable original', False),
        (uuid.uuid4(), 'processing', 'error', 'usable original', False),
        (uuid.uuid4(), 'ready', 'pending', None, False),
        (uuid.uuid4(), 'partial', 'error', None, False),
        (uuid.uuid4(), 'processing', 'ready', None, False),
        (uuid.uuid4(), 'error', 'error', ' \n\t', False),
        (uuid.uuid4(), 'pending', 'pending', None, False),
    ]
    with engine.begin() as db:
        db.exec_driver_sql('CREATE TABLE sources (id CHAR(32), status TEXT, chunk_status TEXT, full_text TEXT, preserve_verbatim BOOLEAN)')
        for sid, status, chunk, text, preserve in rows:
            db.exec_driver_sql('INSERT INTO sources VALUES (?, ?, ?, ?, ?)', (sid.hex, status, chunk, text, preserve))
        actual = set(db.execute(select(Source.id).where(*_source_conditions(None, None))).scalars())
    assert actual == {row[0] for row in rows[:5]}
