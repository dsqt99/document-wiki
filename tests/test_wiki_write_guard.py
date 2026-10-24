"""Tests for the wiki write guard (app/services/wiki_write_guard.py) and its
use in the MRP merger / writer / commit phase and wiki_service.apply_update."""

import asyncio
import types
import uuid

import pytest


@pytest.mark.asyncio
async def test_machine_update_rejects_different_origin_even_with_guard_disabled():
    from unittest.mock import AsyncMock, patch
    from app.services import wiki_service as svc
    page = types.SimpleNamespace(origin_tag="extracted", source_ids=[uuid.uuid4()], content_md="Nội dung gốc.")
    with patch.object(svc, "get_page_by_slug", AsyncMock(return_value=page)):
        with pytest.raises(ValueError, match="tag"):
            await svc.apply_update(AsyncMock(), "dieu-1", "Nội dung AI.", origin_tag="generated", guard=False)
    assert page.content_md == "Nội dung gốc."


@pytest.mark.asyncio
async def test_extracted_update_rejects_another_document():
    from unittest.mock import AsyncMock, patch
    from app.services import wiki_service as svc
    page = types.SimpleNamespace(origin_tag="extracted", source_ids=[uuid.uuid4()], content_md="Bản gốc.")
    with patch.object(svc, "get_page_by_slug", AsyncMock(return_value=page)):
        with pytest.raises(ValueError, match="nguồn"):
            await svc.apply_update(AsyncMock(), "dieu-1", "Khác.", origin_tag="extracted", add_source_id=uuid.uuid4())


@pytest.mark.asyncio
async def test_origin_collision_uses_stable_suffix_without_touching_other_tag():
    from unittest.mock import AsyncMock, patch
    from app.services import wiki_origin_service as svc
    old = types.SimpleNamespace(origin_tag="extracted", source_ids=[uuid.uuid4()])
    lookup = AsyncMock(side_effect=[old, None])
    with patch("app.services.wiki_service.get_page_by_slug", lookup):
        slug = await svc.resolve_target_slug(AsyncMock(), "nguyen-tac", "generated", "department", uuid.uuid4(), uuid.uuid4())
    assert slug == "nguyen-tac-generated"
    assert lookup.await_args_list[0].kwargs["scope_type"] == "department"


@pytest.mark.asyncio
async def test_origin_collision_reuses_only_matching_tag_and_source():
    from unittest.mock import AsyncMock, patch
    from app.services import wiki_origin_service as svc
    sid = uuid.uuid4()
    page = types.SimpleNamespace(origin_tag="extracted", source_ids=[sid])
    with patch("app.services.wiki_service.get_page_by_slug", AsyncMock(return_value=page)):
        assert await svc.resolve_target_slug(AsyncMock(), "dieu-1", "extracted", "global", None, sid) == "dieu-1"
    with patch("app.services.wiki_service.get_page_by_slug", AsyncMock(side_effect=[page, None])):
        assert await svc.resolve_target_slug(AsyncMock(), "dieu-1", "extracted", "global", None, uuid.uuid4()) == "dieu-1-extracted"


@pytest.mark.asyncio
async def test_reconciliation_filters_generated_pages_in_each_source_scope():
    from unittest.mock import AsyncMock, patch, MagicMock
    from sqlalchemy.dialects import postgresql
    from app.ai.mrp import reducer, pipeline
    from app.services import wiki_service
    dept = uuid.uuid4()
    extracted = types.SimpleNamespace(slug="dieu-1", origin_tag="extracted", scope_type="department", scope_id=dept)
    generated = types.SimpleNamespace(slug="huong-dan", origin_tag="generated", scope_type="department", scope_id=dept)
    other_scope = types.SimpleNamespace(slug="phong-khac", origin_tag="generated", scope_type="department", scope_id=uuid.uuid4())
    search = AsyncMock(return_value=[(extracted, 0.99), (other_scope, 0.98), (generated, 0.9)])
    with patch.object(pipeline, "_resolve_wiki_scopes", AsyncMock(return_value=[("department", dept)])), \
         patch.object(reducer, "_embed_many", AsyncMock(return_value=[[0.1]])), \
         patch.object(wiki_service, "search_pages_semantic", search):
        result = await reducer.reconcile_with_kb(AsyncMock(), MagicMock(), [{"term":"Quy định"}], None, MagicMock())
    assert result[0]["kb_slug"] == "huong-dan"
    call = search.await_args.kwargs
    assert call["scope_id"] == dept
    assert "generated" in str(call["page_filter"].compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds":True}))


@pytest.mark.asyncio
async def test_private_source_keeps_personal_scope_instead_of_global_merge_pool():
    from unittest.mock import AsyncMock
    from app.services.wiki_service import resolve_wiki_scopes
    owner = uuid.uuid4()
    source = types.SimpleNamespace(id=uuid.uuid4(), scope_type="personal", scope_id=None, contributed_by_employee_id=owner)
    db = AsyncMock()
    db.get.return_value = source
    assert await resolve_wiki_scopes(db, source) == [("personal", owner)]


def test_origin_collision_remaps_sibling_links_without_changing_labels():
    from app.services.wiki_origin_service import remap_links
    assert remap_links("[[a|Nhãn A]] và [[a]] cùng [[khac]].", {"a":"a-generated"}) == "[[a-generated|Nhãn A]] và [[a-generated]] cùng [[khac]]."


@pytest.mark.asyncio
async def test_generated_update_preserves_origin_and_adds_new_source(monkeypatch):
    page = _page("Nội dung cũ.")
    page.origin_tag = "generated"
    sid = uuid.uuid4()
    svc = _patch_service(monkeypatch, page)
    await svc.apply_update(_FakeSession(), "t", "Nội dung cũ và thông tin mới.", origin_tag="generated", add_source_id=sid)
    assert page.origin_tag == "generated" and page.source_ids == [sid]


@pytest.mark.asyncio
async def test_library_origin_filter_applies_to_count_and_items():
    from unittest.mock import AsyncMock, MagicMock, patch
    from sqlalchemy.dialects import postgresql
    from app.routers import wiki
    count, rows = MagicMock(), MagicMock()
    count.scalar.return_value = 1
    rows.scalars.return_value.all.return_value = []
    db = AsyncMock(execute=AsyncMock(side_effect=[count, rows]))
    with patch.object(wiki, "_page_read_filter", return_value=None), patch.object(wiki, "_scope_names", AsyncMock(return_value={})):
        await wiki.wiki_library(q="",source_id=None,page_type=None,status=None,origin_tag="generated",limit=30,offset=0,db=db,user=MagicMock())
    for call in db.execute.await_args_list:
        assert "origin_tag = 'generated'" in str(call.args[0].compile(dialect=postgresql.dialect(),compile_kwargs={"literal_binds":True}))


@pytest.mark.asyncio
async def test_commit_rechecks_tag_before_asking_llm_to_merge():
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.ai.mrp import pipeline
    from app.ai.mrp.writer import PageWriteResult
    from app.services import wiki_service, source_status
    source = types.SimpleNamespace(id=uuid.uuid4(), title="Nguồn mới")
    old = types.SimpleNamespace(origin_tag="extracted", source_ids=[uuid.uuid4()], content_md="Bản gốc quan trọng. " * 20)
    db = AsyncMock()
    db.get.return_value = source
    db.execute.return_value = MagicMock()
    db.execute.return_value.one_or_none.return_value = source
    row = PageWriteResult(slug="same",title="Same",page_type="concept",action="UPDATE",content_md="Nội dung AI.",summary="AI")
    with patch.object(pipeline,"_resolve_wiki_scopes",AsyncMock(return_value=[("global",None)])), \
         patch.object(pipeline,"_merge_llm",AsyncMock(return_value=object())), \
         patch("app.services.wiki_origin_service.resolve_target_slug",AsyncMock(return_value="same")), \
         patch.object(wiki_service,"get_page_by_slug",AsyncMock(return_value=old)), \
         patch.object(wiki_service,"apply_update",AsyncMock()) as write, \
         patch.object(pipeline,"merge_page_content",AsyncMock()) as merge, \
         patch.object(wiki_service,"regenerate_index",AsyncMock()), \
         patch.object(wiki_service,"append_log",AsyncMock()), \
         patch.object(source_status,"update_source_dual_status",AsyncMock()):
        result = await pipeline.run_commit_phase(db,source,[row],None,None,None,None,AsyncMock())
    write.assert_not_awaited()
    merge.assert_not_awaited()
    assert result["status"] == "error" and result["pages_skipped"] == ["same"]
    assert old.content_md.startswith("Bản gốc quan trọng.")

from app.services.wiki_write_guard import (
    FAILURE_STUB_MARKER,
    check_agent_write,
    check_machine_rewrite,
    is_failure_stub,
    make_failure_stub,
    missing_row_identities,
    table_row_identities,
)


def ledger(*names: str, header: str = "| Tên | Số |") -> str:
    rows = "\n".join(f"| {n} | {i} |" for i, n in enumerate(names))
    return f"# Sổ\n\nMở đầu.\n\n{header}\n| --- | ---: |\n{rows}\n"


# ---------------------------------------------------------------------------
# table_row_identities / missing_row_identities
# ---------------------------------------------------------------------------

def test_identities_skip_header_and_delimiter():
    ids = table_row_identities(ledger("Nguyễn Văn A", "Trần B"))
    assert ids == {"nguyễn văn a", "trần b"}
    assert "tên" not in ids


def test_identities_normalize_emphasis_case_whitespace():
    md = "| H |\n|---|\n| **Nguyễn  Văn A** |\n| `X-1` |\n|  | Trần B |\n"
    assert table_row_identities(md) == {"nguyễn văn a", "x-1", "trần b"}


def test_prose_pipe_is_not_a_table():
    assert table_row_identities("a | b là phép hoặc\n\nkhông phải bảng") == set()


def test_missing_ignores_reorder_and_other_columns():
    old = ledger("A", "B", "C")
    new = "| Tên | Số tiền |\n|---|---|\n| c | 9 |\n| **A** | 7 |\n| b | 8 |\n"
    assert missing_row_identities(old, new) == set()


def test_missing_reports_lost_rows():
    assert missing_row_identities(ledger("A", "B", "C"), ledger("A")) == {"b", "c"}
    assert missing_row_identities("no table", ledger("A")) == set()


def test_crlf_content():
    old = ledger("A", "B").replace("\n", "\r\n")
    assert table_row_identities(old) == {"a", "b"}


# ---------------------------------------------------------------------------
# is_failure_stub
# ---------------------------------------------------------------------------

def test_failure_stub_detection():
    stub = make_failure_stub("Trang", "TimeoutError: boom")
    assert stub == "# Trang\n\n(Page generation failed: TimeoutError: boom)"
    assert is_failure_stub(stub)
    assert is_failure_stub("> [!warning] Mâu thuẫn\n\n" + stub)  # verifier callout
    assert not is_failure_stub("# Trang\n\nNội dung bình thường")
    assert not is_failure_stub("")
    assert not is_failure_stub(None)
    assert FAILURE_STUB_MARKER in stub


# ---------------------------------------------------------------------------
# check_machine_rewrite
# ---------------------------------------------------------------------------

def test_machine_allows_normal_rewrite_and_growth():
    old = ledger(*"ABCDE")
    assert check_machine_rewrite(old, ledger(*"ABCDEFG")) is None
    assert check_machine_rewrite("", "anything") is None
    assert check_machine_rewrite(None, "anything") is None


def test_machine_row_loss_threshold_is_strict():
    old = ledger(*"ABCDE")
    assert check_machine_rewrite(old, ledger(*"ABCD")) is None          # 1/5 = 0.20 ok
    reason = check_machine_rewrite(old, ledger(*"ABC"))                 # 2/5 = 0.40
    assert reason and "table row" in reason and "d" in reason
    assert check_machine_rewrite(old, ledger(*"ABC"), max_row_loss=0.5) is None


def test_machine_refuses_failure_stub():
    old = "# T\n\nNội dung thật."
    assert "stub" in check_machine_rewrite(old, make_failure_stub("T", "err"))
    # stub over empty page also refused
    assert check_machine_rewrite("", make_failure_stub("T", "err"))
    # replacing an old stub with a real page is fine
    assert check_machine_rewrite(make_failure_stub("T", "err"), "# T\n\nOK") is None


def test_machine_refuses_empty_and_drastic_shrink():
    old = "# T\n\n" + "Nội dung dài. " * 100
    assert "empty" in check_machine_rewrite(old, "   ")
    assert "shrank" in check_machine_rewrite(old, old[: len(old) // 3])
    assert check_machine_rewrite(old, old[: int(len(old) * 0.6)]) is None
    # small pages are not subject to the shrink check
    assert check_machine_rewrite("# T\n\nngắn " * 5, "# T") is None


# ---------------------------------------------------------------------------
# check_agent_write
# ---------------------------------------------------------------------------

def test_agent_write_any_loss_refused_vietnamese():
    old = ledger(*"ABCDEFGH")
    assert check_agent_write(old, old) is None
    assert check_agent_write(old, old.replace("| B | 1 |", "| **b** | 99 |")) is None
    msg = check_agent_write(old, ledger(*"BCDEFGH"))
    assert msg.startswith("Bản sửa làm mất 1 dòng bảng: a")
    msg = check_agent_write(old, ledger("A"))
    assert "7 dòng bảng" in msg and "b, c, d, e, f" in msg and "và 2 dòng khác" in msg
    assert check_agent_write("không có bảng", "") is None


# ---------------------------------------------------------------------------
# merger fallback
# ---------------------------------------------------------------------------

class _FakeLLM:
    def __init__(self, result=None, exc=None):
        self.result, self.exc = result, exc

    async def generate(self, prompt, system=None, temperature=None, max_tokens=None):
        if self.exc:
            raise self.exc
        return self.result


EXISTING = "# Trang\n\n" + "Nội dung cũ quan trọng. " * 10 + "\n\n" + ledger("A", "B", "C", "D", "E").split("\n\n", 2)[2]
INCOMING = "# Trang\n\nNội dung mới từ nguồn khác.\n"


def _merge(llm):
    from app.ai.mrp.merger import merge_page_content
    return asyncio.run(merge_page_content(llm, EXISTING, INCOMING, "trang"))


def test_merger_llm_failure_keeps_existing_and_appends():
    from app.ai.mrp.merger import APPEND_FALLBACK_HEADING
    out = _merge(_FakeLLM(exc=RuntimeError("down")))
    assert out.startswith(EXISTING.rstrip())
    assert APPEND_FALLBACK_HEADING in out
    assert "Nội dung mới từ nguồn khác." in out
    assert out.count("# Trang") == 1  # incoming H1 dropped
    assert check_machine_rewrite(EXISTING, out) is None


def test_merger_too_short_keeps_existing():
    out = _merge(_FakeLLM(result="# Trang\n\nngắn"))
    assert out.startswith(EXISTING.rstrip()) and "Nội dung mới" in out


def test_merger_row_loss_rejected():
    merged = EXISTING.replace("| C | 2 |\n", "").replace("| D | 3 |\n", "") + "\n" + "x" * 200
    out = _merge(_FakeLLM(result=merged))
    assert out.startswith(EXISTING.rstrip())
    assert table_row_identities(out) >= {"a", "b", "c", "d", "e"}


def test_merger_success_returns_merged():
    merged = EXISTING + "\n\nNội dung mới từ nguồn khác.\n"
    assert _merge(_FakeLLM(result=merged)) == merged.strip()


# ---------------------------------------------------------------------------
# writer pass guard
# ---------------------------------------------------------------------------

def test_writer_pass_drops_rows():
    from app.ai.mrp.writer import _pass_drops_rows
    assert not _pass_drops_rows(ledger(*"ABCDE"), ledger(*"ABCDE"))
    assert not _pass_drops_rows(ledger(*"ABCDE"), ledger(*"ABCD"))
    assert _pass_drops_rows(ledger(*"ABCDE"), ledger(*"AB"))
    assert not _pass_drops_rows("no table", "")


# ---------------------------------------------------------------------------
# wiki_service.apply_update guard
# ---------------------------------------------------------------------------

class _FakeSession:
    def __init__(self):
        self.added = []

    async def flush(self):
        pass

    def add(self, obj):
        self.added.append(obj)


def _patch_service(monkeypatch, page):
    from app.services import wiki_service

    async def fake_get(session, slug, scope_type="global", scope_id=None):
        return page

    async def fake_links(*a, **k):
        return None

    monkeypatch.setattr(wiki_service, "get_page_by_slug", fake_get)
    monkeypatch.setattr(wiki_service, "refresh_links", fake_links)
    return wiki_service


def _page(content):
    return types.SimpleNamespace(
        id=uuid.uuid4(), content_md=content, version=3, title="T", summary="s",
        status="seed", knowledge_type_slugs=[], source_ids=[],
    )


def test_apply_update_refuses_row_loss(monkeypatch):
    old = ledger(*"ABCDE")
    page = _page(old)
    svc = _patch_service(monkeypatch, page)
    sess = _FakeSession()
    sid = uuid.uuid4()
    out = asyncio.run(svc.apply_update(sess, "t", ledger("A"), title="New", add_source_id=sid))
    assert out is page
    assert page.content_md == old and page.version == 3 and page.title == "T"
    assert page.source_ids == [] and sess.added == []


def test_apply_update_refuses_stub(monkeypatch):
    page = _page("# T\n\nNội dung thật.")
    svc = _patch_service(monkeypatch, page)
    out = asyncio.run(svc.apply_update(_FakeSession(), "t", make_failure_stub("T", "e")))
    assert out is page and page.content_md == "# T\n\nNội dung thật."


def test_apply_update_allows_good_rewrite_and_guard_off(monkeypatch):
    page = _page(ledger(*"ABCDE"))
    svc = _patch_service(monkeypatch, page)
    sess = _FakeSession()
    asyncio.run(svc.apply_update(sess, "t", ledger(*"ABCDEF")))
    assert page.version == 4 and "| F |" in page.content_md and len(sess.added) == 1

    asyncio.run(svc.apply_update(sess, "t", ledger("A"), guard=False))
    assert page.version == 5 and table_row_identities(page.content_md) == {"a"}


# ---------------------------------------------------------------------------
# commit phase skips writer-failure stubs
# ---------------------------------------------------------------------------

def test_commit_phase_skips_failure_stub(monkeypatch):
    from app.ai.mrp import pipeline
    from app.ai.mrp.writer import PageWriteResult
    from app.services import source_status, wiki_chunk_service, wiki_service
    import app.ai.registry as registry_mod

    calls = []

    async def fake_scopes(session, source):
        return [("global", None)]

    def rec(name):
        async def _f(*a, **k):
            calls.append((name, k.get("slug")))
            return types.SimpleNamespace(id=uuid.uuid4())
        return _f

    async def noop(*a, **k):
        return None

    class _Reg:
        def __init__(self, s):
            pass

        async def get_llm(self):
            raise RuntimeError("no llm")

    loop_funcs = {n: rec(n) for n in ("apply_create", "apply_update")}

    async def get_none(*a, **k):
        calls.append(("get_page_by_slug", a[1] if len(a) > 1 else k.get("slug")))
        return None

    monkeypatch.setattr(pipeline, "_resolve_wiki_scopes", fake_scopes)
    monkeypatch.setattr(wiki_service, "get_page_by_slug", get_none)
    monkeypatch.setattr(wiki_service, "apply_create", loop_funcs["apply_create"])
    monkeypatch.setattr(wiki_service, "apply_update", loop_funcs["apply_update"])
    monkeypatch.setattr(wiki_service, "regenerate_index", noop)
    monkeypatch.setattr(wiki_service, "append_log", noop)
    monkeypatch.setattr(wiki_chunk_service, "index_wiki_page_chunks", noop)
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

    class _Tracker:
        async def update(self, *a, **k):
            pass

    source = types.SimpleNamespace(id=uuid.uuid4(), title="Doc", file_name=None)
    results = [
        PageWriteResult(slug="good", title="Good", page_type="concept", action="UPDATE",
                        content_md="# Good\n\nOK", summary="OK"),
        PageWriteResult(slug="bad", title="Bad", page_type="concept", action="UPDATE",
                        content_md=make_failure_stub("Bad", "TimeoutError"), summary="Bad"),
        PageWriteResult(slug="bad2", title="Bad2", page_type="concept", action="CREATE",
                        content_md=make_failure_stub("Bad2", "err"), summary="Bad2"),
    ]
    out = asyncio.run(pipeline.run_commit_phase(
        _Sess(), source, results, None, None, None, None, _Tracker(),
    ))
    touched = {slug for _, slug in calls}
    assert "good" in touched
    assert "bad" not in touched and "bad2" not in touched
    assert out["pages_skipped"] == ["bad", "bad2"]
    assert "skipped" in src_row.wiki_progress_message
