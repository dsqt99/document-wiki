import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.legal_service import finalize_legal_source


@pytest.mark.asyncio
async def test_legal_service_respects_department_scope():
    """Verify that a legal document assigned to a department is scoped to that department, not global."""
    dept_id = uuid.uuid4()
    source_id = uuid.uuid4()

    mock_source = MagicMock()
    mock_source.id = source_id
    mock_source.title = "Nghị định thử nghiệm"
    mock_source.file_name = "nghidinh136.pdf"
    mock_source.full_text = "Điều 1. Nội dung điều 1\nĐiều 2. Nội dung điều 2"
    mock_source.knowledge_type_id = None
    mock_source.scope_type = "department"
    mock_source.scope_id = dept_id

    mock_session = AsyncMock()
    mock_tracker = AsyncMock()

    # resolve_wiki_scopes returns department scope
    with patch("app.services.wiki_service.resolve_wiki_scopes", new_callable=AsyncMock) as mock_resolve, \
         patch("app.services.wiki_service.upsert_page", new_callable=AsyncMock) as mock_upsert, \
         patch("app.services.wiki_service.regenerate_index", new_callable=AsyncMock) as mock_regen, \
         patch("app.services.wiki_service.append_log", new_callable=AsyncMock) as mock_log, \
         patch("app.services.legal_service.ProviderRegistry") as mock_registry_cls:
        
        mock_resolve.return_value = [("department", dept_id)]
        mock_registry_inst = MagicMock()
        mock_registry_inst.get_active_embedding_spec_id = AsyncMock(return_value=None)
        mock_registry_cls.return_value = mock_registry_inst

        fake_page = MagicMock()
        fake_page.slug = "dieu-1"
        fake_page.title = "Điều 1"
        mock_upsert.return_value = fake_page

        await finalize_legal_source(mock_session, mock_source, mock_tracker)

        # Ensure resolve_wiki_scopes was called
        mock_resolve.assert_called_once_with(mock_session, mock_source)

        # Check every call to upsert_page used department scope
        assert mock_upsert.call_count >= 2  # overview + at least 1 article
        for call in mock_upsert.call_args_list:
            kwargs = call.kwargs
            assert kwargs.get("scope_type") == "department", f"Expected department scope, got {kwargs.get('scope_type')}"
            assert kwargs.get("scope_id") == dept_id, f"Expected dept_id {dept_id}, got {kwargs.get('scope_id')}"

        # Check regenerate_index was called for department scope
        mock_regen.assert_called_with(mock_session, scope_type="department", scope_id=dept_id)


@pytest.mark.asyncio
async def test_legal_finalize_stops_embedding_after_consecutive_failures():
    """An embedding outage must not burn the job timeout one page at a time,
    and the legal graph must already be committed before embedding starts."""
    mock_source = MagicMock()
    mock_source.id = uuid.uuid4()
    mock_source.title = "Luật thử nghiệm"
    mock_source.file_name = "luat.pdf"
    mock_source.full_text = "\n".join(f"Điều {i}. Nội dung điều {i}" for i in range(1, 11))
    mock_source.knowledge_type_id = None

    events = []
    mock_session = AsyncMock()
    mock_session.commit.side_effect = lambda: events.append("commit")

    async def _graph(*a, **k):
        events.append("graph")

    async def _chunks(*a, **k):
        events.append("chunk")
        raise RuntimeError("Connection error")

    provider = MagicMock()
    provider.embed_batch = AsyncMock(side_effect=RuntimeError("Connection error"))

    with patch("app.services.wiki_service.resolve_wiki_scopes", new_callable=AsyncMock, return_value=[("global", None)]), \
         patch("app.services.wiki_service.upsert_page", new_callable=AsyncMock) as mock_upsert, \
         patch("app.services.wiki_service.regenerate_index", new_callable=AsyncMock), \
         patch("app.services.wiki_service.append_log", new_callable=AsyncMock), \
         patch("app.services.legal_service.ingest_legal_graph", side_effect=_graph), \
         patch("app.services.legal_relation_extractor.relink_legal_relations", new_callable=AsyncMock), \
         patch("app.services.legal_service.get_spec", return_value=MagicMock(id="spec")), \
         patch("app.services.legal_service.index_wiki_page_chunks", side_effect=_chunks), \
         patch("app.services.legal_service.ProviderRegistry") as mock_registry_cls, \
         patch("app.services.source_status.update_source_dual_status", new_callable=AsyncMock):
        registry = MagicMock()
        registry.get_active_embedding_spec_id = AsyncMock(return_value="spec")
        registry.get_embedding = AsyncMock(return_value=provider)
        mock_registry_cls.return_value = registry
        mock_upsert.side_effect = lambda *a, **k: MagicMock(slug=k["slug"], title=k["title"], id=uuid.uuid4())

        result = await finalize_legal_source(mock_session, mock_source, AsyncMock())

    assert result["status"] == "ready"
    # 11 pages = 1 batch of page embeddings; the breaker trips after 3 failures in total.
    assert provider.embed_batch.await_count == 1
    assert events.count("chunk") == 2
    # Graph is committed before any embedding call.
    g = events.index("graph")
    assert "commit" in events[g:events.index("chunk")]
