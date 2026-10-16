"""Tests for the wiki write guard (app/services/wiki_write_guard.py) and its
use in the MRP merger / writer / commit phase and wiki_service.apply_update."""

import asyncio
import types
import uuid

import pytest

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

    async def generate(self, prompt, system=None, temperature=None):
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
            return None

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
