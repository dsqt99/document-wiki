"""Disposable database regressions for lifecycle linking and provenance ACL."""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.models import LegalRelation, LegalUnit, Source
from app.services.legal_relation_extractor import LegalRelationExtractor, relink_legal_relations
from app.services.legal_service import ingest_legal_graph, get_legal_unit_validity_warnings


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        # No source text, real sources or configured database are touched.
        await conn.run_sync(LegalUnit.__table__.create)
        await conn.run_sync(LegalRelation.__table__.create)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


async def ingest(db, number, text="Nội dung Điều 1"):
    source = Source(id=uuid.uuid4(), title=number)
    await ingest_legal_graph(db, source, [{"num": "1", "content_md": text}], doc_number=number)
    await db.commit()
    return source


def unit(source, number, kind="article", doc="12/2020/TT-BTC", parent=None):
    return LegalUnit(id=uuid.uuid4(), source_id=source, doc_number=doc,
                     unit_type=kind, unit_number=number, parent_unit_id=parent)


@pytest.mark.asyncio
@pytest.mark.parametrize("verb,kind", [("Bãi bỏ", "bai_bo"), ("Thay thế", "thay_the")])
async def test_document_lifecycle_links_normalized_document_root(db, verb, kind):
    target = await ingest(db, "12 / 2020 / TT–BTC")
    modifier = await ingest(db, "99/2026/TT-BTC", f"{verb} Thông tư số 12/2020/TT-BTC.")
    await relink_legal_relations(db, source_id=modifier.id)
    relation = (await db.execute(select(LegalRelation))).scalar_one()
    assert relation.relation_type == kind
    assert relation.target_unit_id is not None
    root = await db.get(LegalUnit, relation.target_unit_id)
    assert root.unit_type == "document"
    assert root.source_id == target.id


@pytest.mark.asyncio
async def test_modifier_first_relinked_when_target_arrives(db):
    modifier = await ingest(db, "99/2026/TT-BTC", "Bãi bỏ Thông tư số 12/2020/TT-BTC.")
    await relink_legal_relations(db, source_id=modifier.id)
    target = await ingest(db, "12/2020/TT-BTC")
    await relink_legal_relations(db, source_id=target.id)
    relation = (await db.execute(select(LegalRelation))).scalar_one()
    assert relation.target_unit_id is not None
    assert (await db.get(LegalUnit, relation.target_unit_id)).source_id == target.id


@pytest.mark.asyncio
async def test_ambiguous_duplicate_document_is_not_guessed(db):
    await ingest(db, "12/2020/TT-BTC")
    await ingest(db, "12/2020/TT-BTC")
    modifier = await ingest(db, "99/2026/TT-BTC", "Bãi bỏ Điều 1 của Thông tư số 12/2020/TT-BTC.")
    result = await relink_legal_relations(db, source_id=modifier.id)
    relation = (await db.execute(select(LegalRelation))).scalar_one()
    assert relation.target_unit_id is None
    assert result["ambiguous_count"] == 1


@pytest.mark.asyncio
async def test_article_and_clause_inherit_document_lifecycle_and_enforce_provenance_acl(db):
    target_source, allowed_mod, hidden_mod = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    root = unit(target_source, None, "document")
    article = unit(target_source, "1", parent=root.id)
    clause = unit(target_source, "2", "clause", parent=article.id)
    visible = unit(allowed_mod, "3", doc="99/2026/TT-BTC")
    hidden = unit(hidden_mod, "4", doc="SECRET/2026/TT-BTC")
    db.add_all([root, article, clause, visible, hidden])
    db.add_all([LegalRelation(id=uuid.uuid4(), source_unit_id=mod.id,
                 target_unit_id=root.id, target_doc_number=root.doc_number,
                 relation_type="thay_the", is_effective=True, quote_context=quote)
                for mod, quote in [(visible, "Public replacement"), (hidden, "Secret quote")]])
    await db.commit()
    for read_unit in [article, clause]:
        warnings = await get_legal_unit_validity_warnings(
            db, read_unit.id, allowed_source_ids=[str(target_source), str(allowed_mod)])
        assert len(warnings) == 1
        assert warnings[0]["modifying_doc_number"] == "99/2026/TT-BTC"
        assert "Secret" not in str(warnings)
    assert await get_legal_unit_validity_warnings(db, clause.id, allowed_source_ids=[]) == []
    assert await get_legal_unit_validity_warnings(db, clause.id, allowed_source_ids=[str(allowed_mod)]) == []


def test_lifecycle_extracts_normalized_separator_identifiers():
    relations = LegalRelationExtractor().extract_from_text(
        "Bãi bỏ Thông tư số 12 / 2020 / TT–BTC.", default_doc_number="99/2026/TT-BTC")
    assert len(relations) == 1
    assert relations[0].target_doc_number == "12/2020/TT-BTC"


@pytest.mark.asyncio
async def test_mcp_validity_callout_passes_source_scope():
    from app.mcp.tools import _validity_callout
    identity, session, uid = object(), object(), uuid.uuid4()
    allowed = [str(uuid.uuid4())]
    with patch("app.mcp.tools._get_allowed_source_ids", new_callable=AsyncMock, return_value=allowed), \
         patch("app.services.legal_service.get_legal_unit_validity_warnings", new_callable=AsyncMock, return_value=[]) as warnings:
        await _validity_callout(session, uid, identity=identity)
    warnings.assert_awaited_once_with(session, uid, allowed_source_ids=allowed)


@pytest.mark.asyncio
async def test_bounded_dry_run_backfill_is_idempotent_and_preserves_content(db):
    target = unit(uuid.uuid4(), "1")  # Legacy source has no document root.
    modifier = unit(uuid.uuid4(), "1", doc="99/2026/TT-BTC")
    target.content = "Original article content"
    db.add_all([target, modifier])
    relation = LegalRelation(id=uuid.uuid4(), source_unit_id=modifier.id,
        target_doc_number=target.doc_number, relation_type="bai_bo", is_effective=True)
    db.add(relation)
    await db.commit()
    preview = await relink_legal_relations(db, limit=1, dry_run=True)
    assert preview["linked_count"] == 1 and preview["roots_created"] == 1
    assert relation.target_unit_id is None
    assert len((await db.execute(select(LegalUnit))).scalars().all()) == 2
    applied = await relink_legal_relations(db, limit=1)
    assert applied["linked_count"] == 1 and applied["roots_created"] == 1
    assert (await relink_legal_relations(db, limit=1))["linked_count"] == 0
    assert target.content == "Original article content"
    assert len((await db.execute(select(LegalUnit))).scalars().all()) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("duplicate,requested,expected", [
    (False, "12 / 2020 / TT–BTC", "checked"),
    (False, "2/2020/TT-BTC", "not_found"),  # no substring match
    (True, "12/2020/TT-BTC", "ambiguous"),
])
async def test_relation_tool_requires_exact_scoped_document_identity(db, duplicate, requested, expected):
    from fastmcp import FastMCP
    from app.mcp.tools import register_tools
    source = await ingest(db, "12/2020/TT-BTC")
    allowed = [str(source.id)]
    if duplicate:
        other = await ingest(db, "12/2020/TT-BTC")
        allowed.append(str(other.id))
    app = FastMCP("legal-lifecycle-test")
    register_tools(app)
    tool = await app.get_tool("get_document_relations")
    with patch("app.mcp.tools._get_identity", new_callable=AsyncMock, return_value=(SimpleNamespace(is_admin=False), None)), \
         patch("app.mcp.tools._get_allowed_source_ids", new_callable=AsyncMock, return_value=allowed), \
         patch("app.database.async_session_factory") as factory:
        factory.return_value.__aenter__.return_value = db
        output = await tool.fn(doc_number=requested)
    assert output.structured_content["verification_status"] == expected
    assert output.structured_content["validity_known"] is False
    if expected == "checked":
        assert output.structured_content["checked_sources"] == [{"source_id": str(source.id), "doc_number": "12/2020/TT-BTC"}]
    else:
        assert output.structured_content["checked_sources"] == []


def test_article_replacement_is_not_whole_document_replacement():
    relations = LegalRelationExtractor().extract_from_text(
        "Thay thế Điều 1 của Thông tư số 12/2020/TT-BTC.", default_doc_number="99/2026/TT-BTC")
    assert len(relations) == 1
    assert relations[0].relation_type == "thay_the"
    assert relations[0].target_article_number == "1"


def test_article_implicit_target_with_multiple_documents_is_unresolved():
    relations = LegalRelationExtractor().extract_from_text(
        "Văn bản 12/2020/TT-BTC và 13/2020/TT-BTC.\nSửa đổi Điều 1 như sau:")
    assert len(relations) == 1
    assert relations[0].target_doc_number is None


def test_maintenance_cli_is_dry_run_and_bounded_by_default():
    from app.scripts.relink_legal_relations import parser
    options = parser().parse_args([])
    assert options.apply is False and options.limit == 100
    with pytest.raises(SystemExit):
        parser().parse_args(["--limit", "1001"])


@pytest.mark.asyncio
async def test_article_relation_tool_includes_root_effect_and_hides_modifier(db):
    from fastmcp import FastMCP
    from app.mcp.tools import register_tools
    target = await ingest(db, "12/2020/TT-BTC")
    public = await ingest(db, "99/2026/TT-BTC", "Thay thế Thông tư số 12/2020/TT-BTC.")
    hidden = await ingest(db, "98/2026/TT-BTC", "Bãi bỏ Thông tư số 12/2020/TT-BTC.")
    await relink_legal_relations(db)
    app = FastMCP("legal-root-effect")
    register_tools(app)
    tool = await app.get_tool("get_document_relations")
    with patch("app.mcp.tools._get_identity", new_callable=AsyncMock, return_value=(SimpleNamespace(is_admin=False), None)), \
         patch("app.mcp.tools._get_allowed_source_ids", new_callable=AsyncMock, return_value=[str(target.id), str(public.id)]), \
         patch("app.database.async_session_factory") as factory:
        factory.return_value.__aenter__.return_value = db
        output = await tool.fn(doc_number="12/2020/TT-BTC", article_number="1")
    data = output.structured_content
    assert data["verification_status"] == "checked"
    assert len(data["relations"]) == 1
    assert data["relations"][0]["source_id"] == str(public.id)
    assert "98/2026" not in str(data) and str(hidden.id) not in str(data)


@pytest.mark.asyncio
async def test_relation_tool_marks_unresolved_graph_incomplete(db):
    from fastmcp import FastMCP
    from app.mcp.tools import register_tools
    source = await ingest(db, "99/2026/TT-BTC", "Bãi bỏ Thông tư số 12/2020/TT-BTC.")
    app = FastMCP("legal-unresolved")
    register_tools(app)
    tool = await app.get_tool("get_document_relations")
    with patch("app.mcp.tools._get_identity", new_callable=AsyncMock, return_value=(SimpleNamespace(is_admin=False), None)), \
         patch("app.mcp.tools._get_allowed_source_ids", new_callable=AsyncMock, return_value=[str(source.id)]), \
         patch("app.database.async_session_factory") as factory:
        factory.return_value.__aenter__.return_value = db
        output = await tool.fn(doc_number="99/2026/TT-BTC")
    data = output.structured_content
    assert data["verification_status"] == "unresolved" and data["unresolved_count"] == 1
    assert data["checked_sources"] == [{"source_id": str(source.id), "doc_number": "99/2026/TT-BTC"}]
