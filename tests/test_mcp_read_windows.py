"""Lossless bounded reads and explicit MCP search fallback metadata."""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import FastMCP

from app.mcp import knowledge_payloads as payloads
from app.mcp import tools


def mcp():
    app = FastMCP("read-contract")
    tools.register_tools(app)
    return app


def identity():
    return SimpleNamespace(is_admin=False, employee_id=uuid.uuid4(), department_ids=[],
        allowed_knowledge_types=[], clearance_level="INTERNAL", department_names=[])


def test_text_windows_reconstruct_and_report_continuation():
    text = "abc" * 30000
    first = payloads.text_window(text, offset=-4, max_chars=99999999)
    assert first["content"] == text[:50000]
    assert first["truncated"] and first["next_offset"] == 50000
    second = payloads.text_window(text, offset=first["next_offset"], max_chars=50000)
    assert first["content"] + second["content"] == text
    assert first['content_version'] == second['content_version']
    assert first['content_length'] == second['content_length'] == len(text)
    assert second["next_offset"] is None and not second["has_more"]
    assert payloads.text_window(text, offset=len(text)+1)["content"] == ""


def test_source_page_windows_preserve_empty_pages_and_huge_ranges_without_expansion():
    # Do not expand the requested billion-page range; intersect actual pages.
    text = "A" * 60000 + "\n\n\n\n" + "Z"
    offsets = [0, 60002, 60004]
    kwargs = dict(full_text=text, page_offsets=offsets, pages="1-999999999", max_chars=20000)
    chunks, cursor = [], {}
    for _ in range(5):
        window = payloads.source_page_window(**kwargs, **cursor)
        chunks.extend(window["pages"])
        if not window["pagination"]["has_more"]:
            break
        cursor = {"offset": window["pagination"]["next_offset"],
                  "char_offset": window["pagination"]["next_char_offset"]}
    assert "".join(p["content"] for p in chunks if p["page"] == 1) == "A" * 60000
    assert any(p["page"] == 2 and p["content"] == "" for p in chunks)
    assert chunks[-1]["page"] == 3 and chunks[-1]["content"] == "Z"
    assert all(len(p["content"]) <= 20000 for p in chunks)
    assert window["pagination"]["next_offset"] is None
    same_page = [p for p in chunks if p['page'] == 1]
    assert len({p['content_version'] for p in same_page}) == 1
    assert all(p['content_length'] == 60000 for p in same_page)


def test_source_page_window_caps_pages_and_supports_page_continuation():
    text = "\n\n".join(str(i) for i in range(30))
    offsets, pos = [], 0
    for i in range(30):
        offsets.append(pos)
        pos += len(str(i)) + 2
    first = payloads.source_page_window(text, offsets, "1-30", limit=999999)
    assert len(first["pages"]) == 20
    assert first["pagination"]["next_offset"] == 20
    second = payloads.source_page_window(text, offsets, "1-30", offset=20)
    assert len(second["pages"]) == 10 and not second["pagination"]["has_more"]


@pytest.mark.asyncio
async def test_mcp_embedding_outage_preserves_query_acl_and_reports_mode():
    db, who, allowed = AsyncMock(), identity(), {str(uuid.uuid4())}
    search = {"mode": "hybrid_fallback", "warning": "lexical warning", "threshold": None,
              "retrieval_mode": "lexical_fallback"}
    result = {"exact_match": {"content": "exact legal answer"}, "ranked_results": [],
              "search": search, "rerank_mode": "hybrid_fallback", "failed_arms": []}
    with patch.object(tools, "_get_identity", new=AsyncMock(return_value=(who, None))), \
         patch.object(tools, "_get_allowed_source_ids", new=AsyncMock(return_value=allowed)), \
         patch("app.database.async_session_factory") as factory, \
         patch("app.ai.registry.ProviderRegistry.get_embedding", new=AsyncMock(side_effect=ConnectionError("secret"))), \
         patch("app.services.retrieval_service.unified_search", new=AsyncMock(return_value=result)) as unified, \
         patch.object(payloads, "search_metadata", new=AsyncMock(return_value=([], []))):
        factory.return_value.__aenter__.return_value = db
        out = await mcp().call_tool("search_wiki", {"query": "Điều 1", "top_k": 3})
    assert unified.call_args.args[2] is None
    assert unified.call_args.kwargs["allowed_source_ids"] == allowed
    assert unified.call_args.kwargs["clearance"] == "INTERNAL"
    assert out.structured_content["search"] == search
    assert "lexical warning" in out.content[0].text
    assert "exact legal answer" in out.content[0].text


@pytest.mark.asyncio
async def test_read_wiki_page_uses_window_and_uuid_continuation():
    db, who = AsyncMock(), identity()
    page = SimpleNamespace(id=uuid.uuid4(), title="Page", slug="page", scope_type="global", scope_id=None,
                           content_md="a" * 70000)
    meta = {"id": str(page.id), "title": "Page", "summary": "summary", "url": "/wiki/page",
            "slug": "page", "scope_type": "global", "scope_id": None, "origin_tag": "generated", "source_ids": []}
    rows = MagicMock()
    rows.scalars.return_value.first.return_value = None
    db.execute.return_value = rows
    with patch.object(tools, "_get_identity", new=AsyncMock(return_value=(who, None))), \
         patch("app.database.async_session_factory") as factory, \
         patch.object(payloads, "find_pages", new=AsyncMock(return_value=[page])) as find, \
         patch.object(payloads, "page_metadata_batch", new=AsyncMock(return_value=[meta])), \
         patch("app.services.wiki_service.get_outlinks", new=AsyncMock(return_value=[])), \
         patch("app.services.wiki_service.get_backlinks", new=AsyncMock(return_value=[])):
        factory.return_value.__aenter__.return_value = db
        out = await mcp().call_tool("read_wiki_page", {"page_id": str(page.id), "max_chars": 12000})
    assert find.call_args.kwargs["page_id"] == page.id
    assert len(out.structured_content["content_md"]) == 12000
    assert out.structured_content["pagination"]["next_offset"] == 12000
    assert out.structured_content["content_truncated"] is True
    assert out.structured_content['content_offset'] == 0
    assert out.structured_content['total_chars'] == out.structured_content['content_length'] == 70000
    assert out.structured_content['content_version']
    assert str(page.id) in out.content[0].text and "offset=12000" in out.content[0].text


def test_source_metadata_reports_only_public_quality():
    source = SimpleNamespace(id=uuid.uuid4(), title="Source", file_name="s.pdf", metadata_={
        "secret": "not public", "processing_quality": {"source_index": {
            "status": "complete", "expected": 10, "indexed": 4}}})
    meta = payloads.source_metadata(source)
    assert meta['processing_quality']['source_index']['status'] == 'partial'
    assert 'secret' not in str(meta)


@pytest.mark.asyncio
async def test_source_page_tool_returns_bounded_content_and_rechecks_scope():
    db, who = AsyncMock(), identity()
    source = SimpleNamespace(id=uuid.uuid4(), title="Source", file_name="s.pdf", metadata_={},
                             full_text='x' * 60000, page_offsets=[0])
    with patch.object(tools, "_get_identity", new=AsyncMock(return_value=(who, None))), \
         patch("app.database.async_session_factory") as factory, \
         patch.object(tools, "_load_scoped_source", new=AsyncMock(return_value=(source, None))) as scoped, \
         patch.object(payloads, "load_sources", new=AsyncMock(return_value=[source])) as load:
        factory.return_value.__aenter__.return_value = db
        out = await mcp().call_tool("get_source_pages", {"source_id": str(source.id), "pages": "1"})
    assert scoped.call_args.args == (db, who, str(source.id))
    assert load.call_args.args[2] == [source.id]
    assert len(out.structured_content['pages'][0]['content']) == 20000
    assert out.structured_content['content_truncated'] is True
    assert out.structured_content['pagination']['next_char_offset'] == 20000


@pytest.mark.asyncio
async def test_both_search_arms_failure_returns_structured_error_and_modes():
    db, who = AsyncMock(), identity()
    result = {'ranked_results': [], 'failed_arms': ['wiki','source'],
              'search': {'mode': 'hybrid_fallback', 'retrieval_mode': 'lexical_fallback', 'warning': 'outage'}}
    with patch.object(tools, "_get_identity", new=AsyncMock(return_value=(who, None))), \
         patch.object(tools, "_get_allowed_source_ids", new=AsyncMock(return_value=set())), \
         patch("app.database.async_session_factory") as factory, \
         patch("app.ai.registry.ProviderRegistry.get_embedding", new=AsyncMock(side_effect=ConnectionError())), \
         patch("app.services.retrieval_service.unified_search", new=AsyncMock(return_value=result)), \
         patch.object(payloads, "search_metadata", new=AsyncMock(return_value=([], []))):
        factory.return_value.__aenter__.return_value = db
        out = await mcp().call_tool('search_wiki', {'query': 'PCCC'})
    assert out.structured_content['status'] == 'error'
    assert out.structured_content['search'] == result['search']


@pytest.mark.asyncio
@pytest.mark.parametrize('source_status', ['error', 'partial', 'processing'])
async def test_keyword_search_keeps_extracted_text_after_downstream_failure(source_status):
    from sqlalchemy.dialects import postgresql
    from app.services import mcp_auth_service
    db, who = AsyncMock(), identity()
    source = SimpleNamespace(id=uuid.uuid4(), title='Original', file_name='source.pdf', metadata_={},
        full_text='Quy định phòng cháy chữa cháy.', page_offsets=[0], status=source_status, chunk_status='error')
    result = MagicMock()
    result.scalars.return_value.all.return_value = [source]
    db.execute.return_value = result
    with patch.object(tools, '_get_identity', new=AsyncMock(return_value=(who, None))), \
         patch('app.database.async_session_factory') as factory, \
         patch.object(payloads, 'load_sources', new=AsyncMock(return_value=[source])), \
         patch.object(mcp_auth_service, 'apply_scope_filter', wraps=mcp_auth_service.apply_scope_filter) as scoped:
        factory.return_value.__aenter__.return_value = db
        out = await mcp().call_tool('search_source_content', {'query': 'phòng cháy'})
    sql = str(db.execute.call_args.args[0].compile(dialect=postgresql.dialect()))
    # Downstream failures must not gate original text that was already extracted.
    assert 'sources.status' not in str(db.execute.call_args.args[0].whereclause)
    assert 'sources.chunk_status' not in str(db.execute.call_args.args[0].whereclause)
    assert 'sources.full_text' in sql and ('btrim' in sql or '~' in sql)
    assert scoped.call_count == 1 and scoped.call_args.args[1].clearance_level == 'INTERNAL'
    assert 'security_label' in sql  # existing clearance predicate retained
    assert out.structured_content['results'][0]['source']['id'] == str(source.id)
