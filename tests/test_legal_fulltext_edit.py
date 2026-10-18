"""Hand corrections of a legal document's text (OCR fixes) made on its wiki pages."""

import asyncio
import types
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routers.legal_docs import _article_body, _overview_preamble
from app.services.legal_service import finalize_legal_source


def _page(content_md):
    return types.SimpleNamespace(id=uuid.uuid4(), content_md=content_md)


def test_article_body_strips_citation_header():
    page = _page(
        "> **Căn cứ pháp lý**: Điều 1 — Luật A\r\n> **Toàn văn văn bản**: [[luat-a|Luật A]]\r\n\r\n"
        "1. Nội dung đã sửa lỗi OCR.\r\n"
    )
    assert _article_body(page, edited=True) == "1. Nội dung đã sửa lỗi OCR."
    assert _article_body(page, edited=False) == "1. Nội dung đã sửa lỗi OCR."


def test_article_body_without_header_used_only_when_edited():
    page = _page("Nội dung người dùng viết lại, đã bỏ phần trích dẫn.")
    assert _article_body(page, edited=True) == "Nội dung người dùng viết lại, đã bỏ phần trích dẫn."
    assert _article_body(page, edited=False) is None


def test_overview_preamble_section():
    page = _page(
        "# Luật A\n\n### Thông tin văn bản\n- **Số hiệu**: 1/2020\n\n"
        "## Căn cứ ban hành & Phần mở đầu\n\nCăn cứ Hiến pháp (đã sửa);\n\n"
        "\n## Danh mục các Điều (2 Điều)\n\n- [[luat-a-dieu-1|Điều 1]]\n"
    )
    assert _overview_preamble(page) == "Căn cứ Hiến pháp (đã sửa);"
    assert _overview_preamble(_page("# Trang khác\n\nKhông có phần mở đầu")) is None


@pytest.mark.asyncio
async def test_finalize_keeps_hand_edited_pages():
    source = MagicMock()
    source.id = uuid.uuid4()
    source.title = "Luật thử nghiệm"
    source.file_name = "luat.pdf"
    source.full_text = "Điều 1. Nội dung điều 1\nĐiều 2. Nội dung điều 2"
    source.knowledge_type_id = None
    edited = types.SimpleNamespace(id=uuid.uuid4(), slug="edited")

    async def _get_page(session, slug, **k):
        return edited if slug.startswith("dieu-1-") else None

    with patch("app.services.wiki_service.resolve_wiki_scopes", new_callable=AsyncMock,
               return_value=[("global", None)]), \
         patch("app.services.wiki_service.upsert_page", new_callable=AsyncMock) as mock_upsert, \
         patch("app.services.wiki_service.get_page_by_slug", side_effect=_get_page), \
         patch("app.services.wiki_service.human_edited_page_ids", new_callable=AsyncMock,
               return_value={edited.id}), \
         patch("app.services.wiki_service.regenerate_index", new_callable=AsyncMock), \
         patch("app.services.wiki_service.append_log", new_callable=AsyncMock), \
         patch("app.services.legal_service.ingest_legal_graph", new_callable=AsyncMock), \
         patch("app.services.legal_relation_extractor.relink_legal_relations", new_callable=AsyncMock), \
         patch("app.services.page_indexing.embed_and_index_pages", new_callable=AsyncMock), \
         patch("app.services.doc_metadata_service.store_document_metadata", new_callable=AsyncMock), \
         patch("app.services.source_status.update_source_dual_status", new_callable=AsyncMock):
        mock_upsert.return_value = types.SimpleNamespace(id=uuid.uuid4(), slug="x")
        await finalize_legal_source(AsyncMock(), source, AsyncMock())

    upserted = [c.kwargs["slug"] for c in mock_upsert.call_args_list]
    assert not any(s.startswith("dieu-1-") for s in upserted)
    assert any(s.startswith("dieu-2-") for s in upserted)


@pytest.mark.asyncio
async def test_on_demand_pages_keep_existing_doc_slug():
    """Creating pages from the Toàn văn tab must not re-slug by doc_number (an appendix shares it)."""
    source = MagicMock()
    source.id = uuid.UUID("db1138df-0000-0000-0000-000000000000")
    source.title = "05. Quyết định số 6018/QĐ-CAT-PV01"
    source.file_name = "qd.pdf"
    source.full_text = "Điều 1. Nội dung điều 1\nĐiều 2. Nội dung điều 2"
    source.knowledge_type_id = None

    with patch("app.services.doc_metadata_service.get_doc_meta", return_value={"doc_number": "6018/QĐ-CAT-PV01"}), \
         patch("app.services.doc_metadata_service.store_document_metadata", new_callable=AsyncMock) as mock_store, \
         patch("app.services.wiki_service.resolve_wiki_scopes", new_callable=AsyncMock,
               return_value=[("global", None)]), \
         patch("app.services.wiki_service.upsert_page", new_callable=AsyncMock) as mock_upsert, \
         patch("app.services.wiki_service.get_page_by_slug", new_callable=AsyncMock, return_value=None), \
         patch("app.services.wiki_service.regenerate_index", new_callable=AsyncMock), \
         patch("app.services.wiki_service.append_log", new_callable=AsyncMock), \
         patch("app.services.legal_service.ingest_legal_graph", new_callable=AsyncMock), \
         patch("app.services.legal_relation_extractor.relink_legal_relations", new_callable=AsyncMock), \
         patch("app.services.page_indexing.embed_and_index_pages", new_callable=AsyncMock), \
         patch("app.services.source_status.update_source_dual_status", new_callable=AsyncMock):
        mock_upsert.side_effect = lambda *a, **k: types.SimpleNamespace(id=uuid.uuid4(), slug=k["slug"])
        await finalize_legal_source(AsyncMock(), source, AsyncMock(), final=False, refresh_metadata=False)

    upserted = [c.kwargs["slug"] for c in mock_upsert.call_args_list]
    assert "doc-db1138df" in upserted
    assert all("6018" not in s for s in upserted)
    mock_store.assert_not_called()


def test_commit_with_every_page_failed_reports_error(monkeypatch):
    import app.ai.registry as registry_mod
    from app.ai.mrp import pipeline
    from app.ai.mrp.writer import PageWriteResult
    from app.services import source_status, wiki_service
    from app.services.wiki_write_guard import make_failure_stub

    async def noop(*a, **k):
        return None

    class _Reg:
        def __init__(self, s):
            pass

        async def get_llm(self):
            raise RuntimeError("no llm")

    async def fake_scopes(*a, **k):
        return [("global", None)]

    monkeypatch.setattr(pipeline, "_resolve_wiki_scopes", fake_scopes)
    monkeypatch.setattr(wiki_service, "regenerate_index", noop)
    monkeypatch.setattr(wiki_service, "append_log", noop)
    monkeypatch.setattr(source_status, "update_source_dual_status", noop)
    monkeypatch.setattr(registry_mod, "ProviderRegistry", _Reg)

    src_row = types.SimpleNamespace()

    class _Sess:
        async def execute(self, *a, **k):
            return None

        async def commit(self):
            pass

        async def get(self, model, key):
            return src_row

    source = types.SimpleNamespace(id=uuid.uuid4(), title="Doc", file_name=None)
    results = [
        PageWriteResult(slug="bad", title="Bad", page_type="concept", action="CREATE",
                        content_md=make_failure_stub("Bad", "TimeoutError"), summary="Bad"),
    ]
    out = asyncio.run(pipeline.run_commit_phase(_Sess(), source, results, None, None, None, None, None))
    assert out["status"] == "error"
    assert src_row.wiki_status == "error"
    assert src_row.pipeline_phase == "refine"
