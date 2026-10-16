"""Wiki review is disabled: a proposed draft is published right away."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services import wiki_draft_publish


@pytest.mark.asyncio
async def test_publish_draft_approves_as_author_and_reindexes():
    page = SimpleNamespace(slug="p", title="P", version=3, scope_type=None, scope_id=None)
    draft = SimpleNamespace(draft_kind="edit", page=None)
    author = SimpleNamespace(id="u1", name="An", email="an@x")
    with patch.object(wiki_draft_publish.wiki_service, "approve_draft", AsyncMock(return_value=page)) as approve, \
         patch.object(wiki_draft_publish.wiki_service, "regenerate_index", AsyncMock()) as idx, \
         patch.object(wiki_draft_publish.wiki_service, "append_log", AsyncMock()) as log, \
         patch.object(wiki_draft_publish, "index_wiki_page_chunks", AsyncMock(side_effect=RuntimeError("no embed"))) as emb:
        out = await wiki_draft_publish.publish_draft("session", draft, author)

    assert out is page and draft.page is page
    assert approve.await_args.args[2] == "u1"  # author acts as reviewer
    idx.assert_awaited_once_with("session", scope_type="global", scope_id=None)
    assert "v3" in log.await_args.args[1]
    emb.assert_awaited_once()  # embedding failure does not block publishing


@pytest.mark.asyncio
async def test_publish_draft_propagates_errors_for_caller_rollback():
    with patch.object(
        wiki_draft_publish.wiki_service, "approve_draft", AsyncMock(side_effect=ValueError("bad")),
    ):
        with pytest.raises(ValueError):
            await wiki_draft_publish.publish_draft(
                "session", SimpleNamespace(draft_kind="edit"), SimpleNamespace(id="u1"),
            )
