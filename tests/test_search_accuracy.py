"""Search accuracy: keyword terms, document-number needles, reranker pin/prior/fallback."""
import re

import pytest

from app.core.vi_tokenizer import keyword_terms, term_coverage, websearch_all, websearch_any
from app.services.legal_route_service import find_doc_numbers, normalize_doc_number
from app.services.reranker_service import RerankerService
from app.services.wiki_service import _lexical_plan


def test_keyword_terms_drop_question_words_and_doc_numbers():
    assert keyword_terms("phòng cháy chữa cháy là gì") == ["phong_chay_chua_chay"]
    assert keyword_terms("quy định về nhà cao tầng như thế nào") == ["nha", "cao_tang"]
    assert all("2023" not in t for t in keyword_terms("Nghị định 13/2023/NĐ-CP quy định gì"))


def test_keyword_terms_fallback_when_all_stopwords():
    assert keyword_terms("và của các") == ["va", "cua", "cac"]


def test_websearch_any_and_all():
    terms = ["phong_chay", "nha"]
    assert websearch_all(terms) == '"phong chay" nha'
    assert websearch_any(terms) == '"phong chay" or nha'


def test_term_coverage_is_word_bounded():
    assert term_coverage(["nha"], "Nhà cao tầng") == 1.0
    assert term_coverage(["nha"], "nhanh chóng") == 0.0


def test_doc_numbers_normalized():
    assert normalize_doc_number("136/2020/NĐ–CP") == "136/2020/ND-CP"
    assert find_doc_numbers("Điều 5 Nghị định 136/2020/NĐ-CP và 50/2024/NĐ-CP") == [
        "136/2020/ND-CP", "50/2024/ND-CP",
    ]


def test_lexical_plan_doc_needle_is_bounded():
    _, needles = _lexical_plan("Nghị định 13/2023/NĐ-CP")
    (kind, rx), = [n for n in needles if n[0] == "doc"]
    assert kind == "doc"
    assert re.search(rx, "theo nghi dinh 13/2023/nd-cp ve")
    assert re.search(rx, "so 13 / 2023 / nd - cp")
    assert re.search(rx, "nghi dinh 13.2023.nd.cp - tong quan")
    assert not re.search(rx, "nghi dinh 113/2023/nd-cp")
    assert not re.search(rx, "nghi dinh 13/2023/nd-cpx")


def test_lexical_plan_quoted_phrase():
    _, needles = _lexical_plan('tìm "cơ sở kinh doanh"')
    assert ("phrase", "co so kinh doanh") in needles


@pytest.mark.asyncio
async def test_rerank_pins_exact_hits_first():
    svc = RerankerService(base_url="", enabled=True, top_n=3)
    docs = [
        {"text": "phòng cháy chữa cháy nhà cao tầng", "rrf": 0.05},
        {"text": "không liên quan", "rrf": 0.01, "exact": True},
        {"text": "phòng cháy", "rrf": 0.03},
    ]
    out = await svc.rerank("phòng cháy chữa cháy", docs, prior_key="rrf", pin_key="exact", threshold=0.0)
    assert out[0]["text"] == "không liên quan"
    assert len(out) == 3
    assert all("_rr_idx" not in d for d in out)


@pytest.mark.asyncio
async def test_rerank_keeps_retrieval_order_when_nothing_passes_threshold():
    svc = RerankerService(base_url="", enabled=True, top_n=5)
    docs = [{"text": "alpha", "rrf": 0.05}, {"text": "beta", "rrf": 0.04}, {"text": "gamma", "rrf": 0.03}]
    out = await svc.rerank("zzz qqq", docs, prior_key="rrf", threshold=0.99, degrade_floor=0.98)
    assert [d["text"] for d in out] == ["alpha", "beta", "gamma"]


def test_blend_prior_breaks_ties_by_retrieval_score():
    docs = [{"rerank_score": 0.5, "rrf": 0.01}, {"rerank_score": 0.5, "rrf": 0.05}]
    RerankerService._blend_prior(docs, "rrf")
    assert docs[0]["rrf"] == 0.05
