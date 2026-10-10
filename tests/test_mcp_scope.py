"""Regression tests: MCP read tools must honour the caller's source scope."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import FastMCP
from sqlalchemy.dialects import postgresql


def _scoped_identity(dept_id=None):
    return SimpleNamespace(
        is_admin=False,
        allowed_knowledge_types=["van-ban-phap-luat"],
        allowed_source_ids=None,
        department_ids=[dept_id or uuid.uuid4()],
        department_names=[],
    )


def _text(result) -> str:
    if isinstance(result, list):
        return result[0].text
    content = getattr(result, "content", None)
    if content:
        return content[0].text
    return str(result)


def _tools_mcp() -> FastMCP:
    from app.mcp.tools import register_tools

    mcp = FastMCP("test-scope")
    register_tools(mcp)
    return mcp


# ---------------------------------------------------------------------------
# query_table: UUID primary key vs string allow-list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("in_scope", [True, False])
async def test_query_table_scoped_user(in_scope):
    from app.database.models import Source

    source_id = uuid.uuid4()
    source = Source(id=source_id, file_name="t.xlsx", minio_key="sources/t.xlsx")
    allowed = {str(source_id)} if in_scope else {str(uuid.uuid4())}
    session = AsyncMock()
    session.get.return_value = source
    mcp = _tools_mcp()

    with patch("app.mcp.tools._get_identity", new_callable=AsyncMock) as get_id, \
         patch("app.mcp.tools._get_allowed_source_ids", new_callable=AsyncMock) as get_allowed, \
         patch("app.services.storage_service.storage_service.download_file", return_value=b"") as dl, \
         patch("app.database.async_session_factory") as factory:
        get_id.return_value = (_scoped_identity(), None)
        get_allowed.return_value = allowed
        factory.return_value.__aenter__.return_value = session

        out = _text(await mcp.call_tool(
            "query_table", {"source_id": str(source_id), "sql_query": "SELECT 1"},
        ))

    assert ("Access denied" in out) is (not in_scope)
    assert dl.called is in_scope


# ---------------------------------------------------------------------------
# read_wiki_index / arkon://wiki-index: per-caller catalog, not the stored _index
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_render_scoped_index_lists_only_scoped_pages():
    from app.services import wiki_service

    dept = uuid.uuid4()
    visible = SimpleNamespace(slug="dieu-1", title="Điều 1", page_type="legal", summary=None)
    with patch.object(wiki_service, "list_pages", new_callable=AsyncMock) as lp:
        lp.return_value = [visible]
        out = await wiki_service.render_scoped_index(
            AsyncMock(), allowed_kt_slugs=["kt"], department_ids=[dept], all_scopes=False,
        )

    kwargs = lp.call_args.kwargs
    assert kwargs["allowed_kt_slugs"] == ["kt"]
    assert kwargs["department_ids"] == [dept]
    assert kwargs["all_scopes"] is False
    assert "[[dieu-1|Điều 1]]" in out


@pytest.mark.asyncio
async def test_read_wiki_index_tool_and_resource_use_caller_scope():
    from app.mcp.resources import register_resources

    identity = _scoped_identity()
    mcp = _tools_mcp()
    register_resources(mcp)

    with patch("app.mcp.tools._get_identity", new_callable=AsyncMock) as get_id, \
         patch("app.services.wiki_service.render_scoped_index", new_callable=AsyncMock) as render, \
         patch("app.services.wiki_service.get_page_by_slug", new_callable=AsyncMock) as get_page, \
         patch("app.database.async_session_factory") as factory:
        get_id.return_value = (identity, None)
        render.return_value = "# Wiki Index\n"
        factory.return_value.__aenter__.return_value = AsyncMock()

        tool_out = _text(await mcp.call_tool("read_wiki_index", {}))
        res = await mcp.read_resource("arkon://wiki-index")

    assert tool_out.startswith("# Wiki Index")
    assert render.await_count == 2
    for call in render.await_args_list:
        assert call.kwargs["allowed_kt_slugs"] == identity.allowed_knowledge_types
        assert call.kwargs["department_ids"] == identity.department_ids
        assert call.kwargs["all_scopes"] is False
    get_page.assert_not_called()  # never serves the unscoped stored _index page
    assert res is not None


# ---------------------------------------------------------------------------
# get_document_relations: scope filter + article lookup limited to ARTICLE units
# ---------------------------------------------------------------------------


def _empty_result():
    result = MagicMock()
    result.scalars.return_value.first.return_value = None
    result.scalars.return_value.all.return_value = []
    return result


@pytest.mark.asyncio
async def test_document_relations_no_scope_returns_early():
    mcp = _tools_mcp()
    session = AsyncMock()
    with patch("app.mcp.tools._get_identity", new_callable=AsyncMock) as get_id, \
         patch("app.mcp.tools._get_allowed_source_ids", new_callable=AsyncMock) as get_allowed, \
         patch("app.database.async_session_factory") as factory:
        get_id.return_value = (_scoped_identity(), None)
        get_allowed.return_value = set()
        factory.return_value.__aenter__.return_value = session

        out = _text(await mcp.call_tool(
            "get_document_relations", {"doc_number": "136/2020/NĐ-CP", "article_number": "5"},
        ))

    assert "chưa được cấp quyền" in out
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_document_relations_queries_are_scoped():
    mcp = _tools_mcp()
    allowed = {str(uuid.uuid4())}
    session = AsyncMock()
    session.execute.side_effect = lambda *a, **k: _empty_result()

    with patch("app.mcp.tools._get_identity", new_callable=AsyncMock) as get_id, \
         patch("app.mcp.tools._get_allowed_source_ids", new_callable=AsyncMock) as get_allowed, \
         patch("app.database.async_session_factory") as factory:
        get_id.return_value = (_scoped_identity(), None)
        get_allowed.return_value = allowed
        factory.return_value.__aenter__.return_value = session

        await mcp.call_tool(
            "get_document_relations", {"doc_number": "136/2020/NĐ-CP", "article_number": "5"},
        )

    sqls = [
        str(c.args[0].compile(dialect=postgresql.dialect()))
        for c in session.execute.call_args_list
    ]
    assert sqls, "expected relation queries"
    # Article lookup: scoped and restricted to ARTICLE units (clause/point "5" can't collide).
    assert "source_id IN" in sqls[0]
    assert "unit_type" in sqls[0]
    # Every statement touching legal units carries the scope filter.
    for sql in sqls:
        if "legal_units" in sql:
            assert "source_id IN" in sql, sql
