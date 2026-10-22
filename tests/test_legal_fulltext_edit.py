"""Hand corrections of a legal document's text (OCR fixes) made on its wiki pages."""

import asyncio
import types
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routers import legal_docs
from app.routers.legal_docs import _article_body, _overview_preamble
from app.services import wiki_service
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


def test_end_section_body_preserves_edited_opening_blockquote():
    page = _page("<!-- cahy:legal-endmatter kind=notes -->\n\n> **Toàn văn văn bản**: [[luat-a|Luật A]]\n\n> Nội dung trích dẫn đã hiệu đính.\n\nNội dung tiếp theo.")
    assert legal_docs._end_section_body(page, edited=True) == "> Nội dung trích dẫn đã hiệu đính.\n\nNội dung tiếp theo."


@pytest.mark.parametrize("heading_line", [
    "### Điều 2. Nguyên tắc thực hiện",
    "**Điều 2. Nguyên tắc thực hiện**",
    "Điều 2. Nguyên tắc thực hiện",
])
def test_fulltext_shows_article_heading_once_without_changing_body(heading_line):
    body = "1. Xây dựng cơ sở dữ liệu.\n\n2. Chia sẻ dữ liệu.\n\n### Điều 3. Trích dẫn bên trong"
    content = f"{heading_line}\n\n{body}"
    # Raw parser output and the editable wiki page both contain the heading.
    assert legal_docs._fulltext_article_parts(content, "Điều 2. Nguyên tắc thực hiện") == (
        "Điều 2. Nguyên tắc thực hiện", body,
    )
    page = _page("> **Căn cứ pháp lý**: Điều 2 — Luật A\n\n" + content)
    for edited in (False, True):
        assert legal_docs._fulltext_article_parts(
            _article_body(page, edited), "Điều 2. Nguyên tắc thực hiện",
        )[1] == body
    assert page.content_md.endswith(content)  # stored wiki content stays verbatim


@pytest.mark.parametrize("content", [
    "1. Nội dung không có tiêu đề.\n\n2. Nội dung tiếp theo.",
    "### Điều 3. Trích dẫn điều khác\n\n1. Nội dung đã sửa.",
    "Điều 2 của Luật A quy định các nội dung sau:\n\n1. Nội dung.",
])
def test_fulltext_keeps_content_without_a_heading_for_the_same_article(content):
    assert legal_docs._fulltext_article_parts(content, "Điều 2. Nguyên tắc thực hiện")[1] == content


@pytest.mark.asyncio
@pytest.mark.parametrize("wiki_state", ["missing", "generated", "edited", "edited_heading"])
async def test_fulltext_api_returns_heading_once_for_raw_and_wiki_articles(wiki_state):
    from app.services import permission_engine

    original = "Điều 2. Nguyên tắc thực hiện\n1. Nội dung gốc.\n\n2. Khoản hai.\n\nGhi chú:\nGhi chú thuộc nội dung điều này."
    source = types.SimpleNamespace(
        id=uuid.uuid4(), title="Luật A", full_text=original + "\nĐiều 3. Hiệu lực\nNội dung tiếp theo.", minio_key=None,
        file_size=0, source_type="file", url=None,
    )
    page = types.SimpleNamespace(
        id=uuid.uuid4(), slug="dieu-2-luat-a", title="Điều 2: Nguyên tắc thực hiện - Luật A",
        page_type="concept", summary="Tóm tắt", content_md=(
            "> **Căn cứ pháp lý**: Điều 2 — Luật A\n\n### "
            + (original.replace("Nội dung gốc", "Nội dung đã sửa") if wiki_state == "edited" else original)
        ),
    )
    if wiki_state == "edited_heading":
        page.content_md = page.content_md.replace("Nguyên tắc thực hiện", "Nguyên tắc đã hiệu đính")
    rows = MagicMock()
    rows.scalars.return_value.all.return_value = [] if wiki_state == "missing" else [page]
    db = AsyncMock(execute=AsyncMock(return_value=rows))
    with patch.object(legal_docs, "_find_source", AsyncMock(return_value=source)), \
         patch.object(legal_docs, "_meta", return_value={}), \
         patch.object(legal_docs, "_item", return_value={"doc_slug": "luat-a"}), \
         patch.object(legal_docs, "_build_wiki_scope_filter", return_value=None), \
         patch.object(permission_engine, "can_access_document", AsyncMock(return_value=True)), \
         patch.object(legal_docs.wiki_service, "human_edited_page_ids", AsyncMock(
             return_value={page.id} if wiki_state.startswith("edited") else set(),
         )), \
         patch.object(legal_docs.doc_metadata_service, "load_doc_relations", AsyncMock(return_value={})):
        result = await legal_docs.get_legal_doc("luat-a", db=db, user=types.SimpleNamespace())
    article = result["articles"][0]
    assert article["heading"] == (
        "Điều 2. Nguyên tắc đã hiệu đính" if wiki_state == "edited_heading" else "Điều 2. Nguyên tắc thực hiện"
    )
    assert "Điều 2" not in article["content_md"]
    assert "2. Khoản hai." in article["content_md"]
    assert "Ghi chú thuộc nội dung điều này." in article["content_md"]
    assert ("Nội dung đã sửa" in article["content_md"]) == (wiki_state == "edited")


@pytest.mark.asyncio
@pytest.mark.parametrize("first", ["Điều 2.", "Điều 2 Nguyên tắc thực hiện"])
async def test_fulltext_handles_original_headings_with_different_punctuation(first):
    from app.services.legal_service import split_legal_text_by_articles

    article = split_legal_text_by_articles(first + "\n\n1. Nội dung.", "Luật A", "luat-a")["articles"][0]
    assert legal_docs._fulltext_article_parts(article["content_md"], article["heading"]) == (first, "1. Nội dung.")


def test_overview_preamble_section():
    page = _page(
        "# Luật A\n\n### Thông tin văn bản\n- **Số hiệu**: 1/2020\n\n"
        "## Căn cứ ban hành & Phần mở đầu\n\nCăn cứ Hiến pháp (đã sửa);\n\n"
        "\n## Danh mục các Điều (2 Điều)\n\n- [[luat-a-dieu-1|Điều 1]]\n"
    )
    assert _overview_preamble(page) == "Căn cứ Hiến pháp (đã sửa);"
    assert _overview_preamble(_page("# Trang khác\n\nKhông có phần mở đầu")) is None
    assert _overview_preamble(_page("## Căn cứ ban hành & Phần mở đầu\n\nNội dung mở đầu.\n\n## Phụ lục & Chú thích\n\n- [[phu-luc-i-luat-a|PHỤ LỤC I]]")) == "Nội dung mở đầu."


@pytest.mark.asyncio
async def test_fulltext_api_keeps_end_sections_separate_and_uses_edited_wiki_body():
    from app.services import permission_engine

    original = "Điều 1. Hiệu lực\nNội dung chính.\nPHỤ LỤC I\nĐiều 9. Mẫu đính kèm\nNội dung mẫu.\nGHI CHÚ\nNội dung chú thích."
    source = types.SimpleNamespace(id=uuid.uuid4(), title="Luật A", full_text=original,
        minio_key=None, file_size=0, source_type="file", url=None)
    tail_page = types.SimpleNamespace(id=uuid.uuid4(), slug="phu-luc-i-luat-a-extracted", title="PHỤ LỤC I - Luật A",
        origin_tag="extracted", source_ids=[source.id],
        page_type="concept", summary="", content_md="<!-- cahy:legal-endmatter kind=appendix -->\n\n> **Toàn văn văn bản**: [[luat-a|Luật A]]\n\nPHỤ LỤC I\nĐiều 9. Mẫu đã sửa\nNội dung mẫu đã hiệu đính.")
    rows = MagicMock()
    legacy_article = types.SimpleNamespace(id=uuid.uuid4(), slug="dieu-1-luat-a", title="Điều 1. Hiệu lực", page_type="concept", summary="",
        content_md="> **Căn cứ pháp lý**: Điều 1 — Luật A\n\n" + original)
    incompatible_page = types.SimpleNamespace(id=uuid.uuid4(), slug="phu-luc-i-luat-a", title="Trang AI", page_type="concept", summary="", content_md="Sai nguồn", origin_tag="generated", source_ids=[source.id])
    rows.scalars.return_value.all.return_value = [legacy_article, incompatible_page, tail_page]
    db = AsyncMock(execute=AsyncMock(return_value=rows))
    with patch.object(legal_docs, "_find_source", AsyncMock(return_value=source)), \
         patch.object(legal_docs, "_meta", return_value={}), \
         patch.object(legal_docs, "_item", return_value={"doc_slug": "luat-a"}), \
         patch.object(legal_docs, "_build_wiki_scope_filter", return_value=None), \
         patch.object(permission_engine, "can_access_document", AsyncMock(return_value=True)), \
         patch.object(legal_docs.wiki_service, "human_edited_page_ids", AsyncMock(return_value={tail_page.id})), \
         patch.object(legal_docs.doc_metadata_service, "load_doc_relations", AsyncMock(return_value={})):
        result = await legal_docs.get_legal_doc("luat-a", db=db, user=types.SimpleNamespace())
    assert [a["num"] for a in result["articles"]] == ["1"]
    assert "PHỤ LỤC" not in result["articles"][0]["content_md"]
    assert [s["kind"] for s in result["end_sections"]] == ["appendix", "notes"]
    appendix = result["end_sections"][0]
    assert appendix["wiki_slug"] == tail_page.slug and appendix["edited"] is True
    assert "Mẫu đã sửa" in appendix["content_md"] and "cahy:legal-endmatter" not in appendix["content_md"]
    assert result["end_sections"][1]["wiki_slug"] is None


@pytest.mark.asyncio
async def test_finalize_keeps_hand_edited_pages():
    source = MagicMock()
    source.id = uuid.uuid4()
    source.title = "Luật thử nghiệm"
    source.file_name = "luat.pdf"
    source.full_text = "Điều 1. Nội dung điều 1\nĐiều 2. Nội dung điều 2"
    source.knowledge_type_id = None
    edited = types.SimpleNamespace(id=uuid.uuid4(), slug="edited", origin_tag="extracted", source_ids=[source.id])

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


@pytest.mark.parametrize("page_error, outage", [
    ("TimeoutError", True),
    ("UpstreamUnavailable: [ai_unavailable] Dịch vụ AI 'llm' không phản hồi.", True),
    ("ValueError: bad plan", False),
])
def test_commit_with_every_page_failed_reports_error(monkeypatch, page_error, outage):
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
            return types.SimpleNamespace(one_or_none=lambda: source)

        async def flush(self):
            pass

        async def commit(self):
            pass

        async def get(self, model, key):
            return src_row

    source = types.SimpleNamespace(id=uuid.uuid4(), title="Doc", file_name=None)
    results = [
        PageWriteResult(slug="bad", title="Bad", page_type="concept", action="CREATE",
                        content_md=make_failure_stub("Bad", page_error), summary="Bad"),
    ]
    out = asyncio.run(pipeline.run_commit_phase(_Sess(), source, results, None, None, None, None, None))
    assert out["status"] == "error"
    assert src_row.wiki_status == "error"
    assert src_row.pipeline_phase == "refine"
    # an outage keeps the marker so resume_ai_unavailable_cron picks the source up again
    assert src_row.wiki_error_message.startswith("[ai_unavailable] ") is outage


def _summary_page():
    return types.SimpleNamespace(
        id=uuid.uuid4(), slug="dieu-2-luat-a", title="Điều 2: Nguyên tắc - Luật A",
        content_md="Nội dung cũ", summary="Tóm tắt cũ bị cắt…", version=2,
    )


def _summary_content():
    paragraph = "1. " + "Nội dung đã hiệu đính cần được giữ đầy đủ " * 20 + "hết khoản một."
    return (
        "> **Căn cứ pháp lý**: Điều 2 — Luật A\n\n"
        "### Điều 2. Nguyên tắc đã sửa\n\n" + paragraph + "\n\n2. Khoản tiếp theo."
    ), "Điều 2: Nguyên tắc đã sửa — " + paragraph


@pytest.mark.asyncio
async def test_direct_edit_refreshes_summary_and_persists_full_first_paragraph():
    page = _summary_page()
    content, expected = _summary_content()
    session = MagicMock(flush=AsyncMock())
    with patch.object(wiki_service, "refresh_links", AsyncMock()):
        result = await wiki_service.direct_edit_page(session, page, uuid.uuid4(), content)
    assert result.summary == expected
    assert result.content_md == content and result.version == 3
    assert session.add.call_args.args[0].content_md == content


@pytest.mark.asyncio
async def test_approve_draft_refreshes_summary_from_reviewers_final_content():
    page = _summary_page()
    content, expected = _summary_content()
    draft = types.SimpleNamespace(
        id=uuid.uuid4(), draft_kind="edit", page=page, base_version=2, content_md="Bản nháp cũ",
    )
    session = MagicMock(flush=AsyncMock(), refresh=AsyncMock())
    with patch.object(wiki_service, "_advisory_lock", AsyncMock()), \
         patch.object(wiki_service, "refresh_links", AsyncMock()):
        result = await wiki_service.approve_draft(
            session, draft, uuid.uuid4(), edited_content_md=content,
        )
    assert result.summary == expected and result.content_md == content
    assert draft.status == "approved"


@pytest.mark.asyncio
async def test_rollback_refreshes_summary_from_restored_content():
    page = _summary_page()
    content, expected = _summary_content()
    rows = MagicMock()
    rows.scalars.return_value.first.return_value = types.SimpleNamespace(content_md=content)
    session = MagicMock(flush=AsyncMock(), execute=AsyncMock(return_value=rows))
    with patch.object(wiki_service, "refresh_links", AsyncMock()):
        result = await wiki_service.rollback_to_revision(session, page, 1, uuid.uuid4())
    assert result.summary == expected and result.content_md == content


@pytest.mark.asyncio
async def test_article_with_heading_removed_uses_page_title_and_new_body():
    page = _summary_page()
    session = MagicMock(flush=AsyncMock())
    with patch.object(wiki_service, "refresh_links", AsyncMock()):
        await wiki_service.direct_edit_page(session, page, uuid.uuid4(), "1. Nội dung mới.\n\n2. Khoản hai.")
    assert page.summary == "Điều 2: Nguyên tắc — 1. Nội dung mới."


@pytest.mark.asyncio
async def test_summary_does_not_reuse_old_body_sentence_from_page_title():
    page = _summary_page()
    page.title = "Điều 2: Quyết định này có hiệu lực thi hành kể từ ngày ký. - Luật A"
    session = MagicMock(flush=AsyncMock())
    with patch.object(wiki_service, "refresh_links", AsyncMock()):
        await wiki_service.direct_edit_page(session, page, uuid.uuid4(), "Nội dung mới đã thay hoàn toàn.")
    assert page.summary == "Điều 2 — Nội dung mới đã thay hoàn toàn."


@pytest.mark.asyncio
async def test_summary_keeps_wrapped_body_on_heading_after_citation_block():
    page = _summary_page()
    content = (
        "> **Căn cứ pháp lý**: Điều 2 — Luật A\n\n"
        "### Điều 2. Quyết định này có hiệu lực thi hành\n"
        "kể từ ngày ký ban hành.\n\n2. Khoản tiếp theo."
    )
    session = MagicMock(flush=AsyncMock())
    with patch.object(wiki_service, "refresh_links", AsyncMock()):
        await wiki_service.direct_edit_page(session, page, uuid.uuid4(), content)
    assert page.summary == "Điều 2 — Quyết định này có hiệu lực thi hành kể từ ngày ký ban hành."


@pytest.mark.asyncio
@pytest.mark.parametrize("edited_tail", [False, True])
@pytest.mark.parametrize("appendix_only", [False, True])
@pytest.mark.parametrize("final", [False, True])
async def test_finalize_separates_tail_pages_links_and_preserves_hand_edits(edited_tail, appendix_only, final):
    from contextlib import ExitStack
    from app.services.legal_service import split_legal_text_by_articles

    source = MagicMock()
    source.id = uuid.uuid4()
    source.title = "Luật A"
    source.file_name = "luat.pdf"
    source.knowledge_type_id = None
    source.full_text = (
        ("" if appendix_only else "Điều 1. Thi hành\nNội dung chính.\nCHÚ THÍCH\nGiải thích Điều 99.\n")
        + "PHỤ LỤC I\nChương I\nĐiều 1. Mẫu áp dụng\nNội dung mẫu."
    )
    doc_slug = "luat-a"
    parsed = split_legal_text_by_articles(source.full_text, source.title, doc_slug)
    # Resolve collisions against generated pages before creating the tail page.
    occupied = types.SimpleNamespace(id=uuid.uuid4(), origin_tag="generated", source_ids=[])
    edited = types.SimpleNamespace(
        id=uuid.uuid4(), slug=f"phu-luc-i-{doc_slug}-extracted", origin_tag="extracted",
        source_ids=[source.id], content_md="Nội dung phụ lục đã sửa bằng tay.",
    )

    async def get_page(session, slug, **kwargs):
        if slug == f"phu-luc-i-{doc_slug}":
            return occupied
        if edited_tail and slug == edited.slug:
            return edited
        return None

    with ExitStack() as stack:
        stack.enter_context(patch("app.services.doc_metadata_service.get_doc_meta", return_value={"doc_slug": doc_slug}))
        stack.enter_context(patch.object(wiki_service, "resolve_wiki_scopes", AsyncMock(return_value=[("global", None)])))
        stack.enter_context(patch.object(wiki_service, "get_page_by_slug", side_effect=get_page))
        stack.enter_context(patch.object(wiki_service, "human_edited_page_ids", AsyncMock(return_value={edited.id})))
        upsert = stack.enter_context(patch.object(wiki_service, "upsert_page", AsyncMock()))
        upsert.side_effect = lambda *a, **k: types.SimpleNamespace(id=uuid.uuid4(), **k)
        for name in ("regenerate_index", "append_log"):
            stack.enter_context(patch.object(wiki_service, name, AsyncMock()))
        graph = stack.enter_context(patch("app.services.legal_service.ingest_legal_graph", AsyncMock()))
        index = stack.enter_context(patch("app.services.page_indexing.embed_and_index_pages", AsyncMock()))
        stack.enter_context(patch("app.services.legal_relation_extractor.relink_legal_relations", AsyncMock()))
        stack.enter_context(patch("app.services.source_status.update_source_dual_status", AsyncMock()))
        result = await finalize_legal_source(AsyncMock(), source, AsyncMock(), refresh_metadata=False, final=final)

    assert result["status"] == ("ready" if final else "articles_ready")
    assert result["total_pages"] == (2 if appendix_only else 4)
    assert result["articles"] == (0 if appendix_only else 1)
    assert result["overview_slug"] == doc_slug
    assert result["article_slugs"] == ([] if appendix_only else ["dieu-1-luat-a"])
    assert edited.slug in result["end_section_slugs"]
    assert f"phu-luc-i-{doc_slug}" not in result["end_section_slugs"]
    writes = {c.kwargs["slug"]: c.kwargs for c in upsert.call_args_list}
    overview = writes[doc_slug]["content_md"]
    assert f"[[{edited.slug}|" in overview
    if not appendix_only:
        assert "CHÚ THÍCH" not in writes["dieu-1-luat-a"]["content_md"]
        notes_slug = next(s["slug"] for s in parsed["end_sections"] if s["kind"] == "notes")
        assert f"[[{notes_slug}|" in overview
        assert "<!-- cahy:legal-endmatter kind=notes -->" in writes[notes_slug]["content_md"]
        assert writes[notes_slug]["origin_tag"] == "extracted"
    if edited_tail:
        assert edited.slug not in writes
        assert edited in index.call_args.args[1]
        assert edited.content_md == "Nội dung phụ lục đã sửa bằng tay."
    else:
        assert "Điều 1. Mẫu áp dụng" in writes[edited.slug]["content_md"]
        assert "<!-- cahy:legal-endmatter kind=appendix -->" in writes[edited.slug]["content_md"]
    graph_articles = graph.call_args.kwargs["articles"]
    assert [a["num"] for a in graph_articles] == ([] if appendix_only else ["1"])
    assert all("PHỤ LỤC" not in a["content_md"] for a in graph_articles)


def test_opaque_wiki_tail_chunks_retain_short_headings_and_nested_articles():
    from app.services.wiki_chunk_service import build_wiki_chunks

    content = "<!-- cahy:legal-endmatter kind=appendix -->\nPHỤ LỤC I\n## Chương I\n### Điều 1. Mẫu\nX."
    page = types.SimpleNamespace(
        slug="phu-luc-i-luat-a", title="Phụ lục I - Luật A", origin_tag="extracted", source_ids=[uuid.uuid4()],
    )
    chunks = build_wiki_chunks(content, page=page)
    assert len(chunks) == 1
    assert chunks[0].text == content.split("\n", 1)[1]
    assert chunks[0].heading_path == page.title


@pytest.mark.parametrize("origin,slug,source_ids", [
    ("generated", "phu-luc-i-luat-a", ["source"]),
    ("extracted", "bai-viet-thuong", ["source"]),
    ("extracted", "phu-luc-i-luat-a", []),
])
def test_endmatter_marker_cannot_change_generic_wiki_chunking(origin, slug, source_ids):
    from app.services.wiki_chunk_service import build_wiki_chunks

    content = "<!-- cahy:legal-endmatter kind=appendix -->\n## Mục một\n" + "Văn bản. " * 20 + "\n## Mục hai\n" + "Văn bản khác. " * 20
    page = types.SimpleNamespace(slug=slug, title="Trang", origin_tag=origin, source_ids=source_ids)
    assert build_wiki_chunks(content, page=page) == build_wiki_chunks(content)


def test_long_opaque_note_wiki_pages_use_bounded_windows_and_keep_the_tail():
    from app.services.chunk_budget import CHUNK_TARGET_TOKENS, estimate_tokens
    from app.services.wiki_chunk_service import build_wiki_chunks

    body = "CHÚ THÍCH\n## Chương I\n### Điều 90. Nội dung tham chiếu\n" + "Giải thích bổ sung. " * 2000 + "KẾT THÚC."
    content = "<!-- cahy:legal-endmatter kind=notes -->\n" + body
    page = types.SimpleNamespace(
        slug="chu-thich-1-luat-a-extracted", title="Chú thích - Luật A", origin_tag="extracted", source_ids=[uuid.uuid4()],
    )
    chunks = build_wiki_chunks(content, page=page)
    assert len(chunks) > 1
    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))
    assert all(chunk.heading_path == page.title for chunk in chunks)
    assert all(estimate_tokens(chunk.text) <= CHUNK_TARGET_TOKENS + 2 for chunk in chunks)
    assert chunks[0].text.startswith("CHÚ THÍCH\n## Chương I\n### Điều 90.")
    assert chunks[-1].text.endswith("KẾT THÚC.")


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["exact_move", "altered_article", "missing_tail", "edited_article", "edited_tail", "no_auto_header"])
async def test_legacy_article_tail_move_requires_saved_exact_copies_and_records_revision(case):
    from contextlib import ExitStack
    from app.database.models import WikiPage, WikiPageRevision
    from app.services.wiki_write_guard import check_machine_rewrite

    main = "Điều 1. Thi hành\n1. Nội dung chính."
    tail = "PHỤ LỤC I\n| Mã | Nội dung |\n| --- | --- |\n| A | " + "Dữ liệu mẫu " * 50 + "|\n| B | Hàng hai |"
    source = types.SimpleNamespace(
        id=uuid.uuid4(), title="Luật A", file_name="luat.pdf", full_text=main + "\n\n" + tail,
        knowledge_type_id=None, metadata_={}, wiki_attempt_id=None,
    )
    header = "> **Căn cứ pháp lý**: Điều 1 — Luật A\n> **Toàn văn văn bản**: [[luat-a|Luật A]]\n\n"
    old_content = ("" if case == "no_auto_header" else header) + source.full_text
    if case == "altered_article":
        old_content += "\nGhi thêm chưa có trong tài liệu nguồn."
    article = WikiPage(
        id=uuid.uuid4(), slug="dieu-1-luat-a", title="Điều 1 - Luật A", content_md=old_content,
        source_ids=[source.id], origin_tag="extracted", scope_type="department", scope_id=uuid.uuid4(),
        knowledge_type_slugs=["legal"], version=3,
    )
    pages = {article.slug: article}
    edited_ids = {article.id} if case == "edited_article" else set()
    if case in ("missing_tail", "edited_tail"):
        tail_page = WikiPage(
            id=uuid.uuid4(), slug="phu-luc-i-luat-a", title="Phụ lục I", origin_tag="extracted",
            source_ids=[source.id], scope_type=article.scope_type, scope_id=article.scope_id,
            content_md="| Mã | Nội dung |\n| --- | --- |\n| PROTECTED | Bản phụ lục khác |",
            knowledge_type_slugs=["legal"], version=2,
        )
        pages[tail_page.slug] = tail_page
        if case == "edited_tail":
            edited_ids.add(tail_page.id)
    saved = []
    events = []

    def add(obj):
        saved.append(obj)
        if isinstance(obj, WikiPage):
            pages[obj.slug] = obj
            events.append(obj.slug)
        elif isinstance(obj, WikiPageRevision) and obj.page_id == article.id:
            events.append("article_revision")

    async def get_page(session, slug, **kwargs):
        return pages.get(slug)

    session = types.SimpleNamespace(add=add, flush=AsyncMock(), commit=AsyncMock())
    assert check_machine_rewrite(old_content, header + main) is not None
    with ExitStack() as stack:
        stack.enter_context(patch("app.services.doc_metadata_service.get_doc_meta", return_value={"doc_slug": "luat-a"}))
        stack.enter_context(patch.object(wiki_service, "get_page_by_slug", side_effect=get_page))
        stack.enter_context(patch.object(wiki_service, "human_edited_page_ids", AsyncMock(return_value=edited_ids)))
        stack.enter_context(patch.object(wiki_service, "resolve_wiki_scopes", AsyncMock(return_value=[(article.scope_type, article.scope_id)])))
        for name in ("_advisory_lock", "refresh_links", "regenerate_index", "append_log"):
            stack.enter_context(patch.object(wiki_service, name, AsyncMock()))
        stack.enter_context(patch("app.services.legal_service.ingest_legal_graph", AsyncMock()))
        stack.enter_context(patch("app.services.legal_relation_extractor.relink_legal_relations", AsyncMock()))
        stack.enter_context(patch("app.services.page_indexing.embed_and_index_pages", AsyncMock()))
        stack.enter_context(patch("app.services.source_status.update_source_dual_status", AsyncMock()))
        await finalize_legal_source(session, source, AsyncMock(), refresh_metadata=False)

    revisions = [obj for obj in saved if isinstance(obj, WikiPageRevision) and obj.page_id == article.id]
    if case == "exact_move":
        assert article.content_md.endswith(main + "\n")
        assert "PHỤ LỤC" not in article.content_md
        assert article.version == 4
        assert len(revisions) == 1 and revisions[0].content_md == article.content_md
        assert events.index("phu-luc-i-luat-a") < events.index("article_revision")
        assert pages["phu-luc-i-luat-a"].content_md.endswith(tail + "\n")
    else:
        assert article.content_md == old_content
        assert article.version == 3 and revisions == []
