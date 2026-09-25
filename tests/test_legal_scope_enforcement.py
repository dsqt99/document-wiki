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
