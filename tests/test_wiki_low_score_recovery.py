"""Uncalibrated HTTP ranking scores must not erase corroborated retrieval."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.wiki_reranker import rank_candidates, search_metadata


def scorer(scores, semantics="ranking"):
    return SimpleNamespace(score=AsyncMock(return_value=scores),
                           score_semantics=semantics, aclose=AsyncMock())


@pytest.mark.asyncio
@pytest.mark.parametrize("query,text", [
    ("Làm sao kiểm tra bản backup có khôi phục được?",
     "Sao lưu: định kỳ kiểm tra và khôi phục dữ liệu từ bản sao lưu."),
    ("May tinh nhiem ma doc can xu ly the nao?",
     "Máy tính nhiễm mã độc cần xử lý: ngắt mạng, thông báo cán bộ phụ trách."),
])
async def test_corroborated_results_survive_low_http_scores_honestly(query, text):
    candidate = {"text": text, "rrf": .03, "source_id": "already-authorized"}
    model = scorer([.0009])
    result = await rank_candidates(query, [candidate], scorer=model, threshold=.7)
    assert result.items == [candidate]
    assert result.items[0] is candidate
    assert "rerank_score" not in result.items[0]
    assert result.mode == "hybrid_fallback" and result.threshold is None
    assert search_metadata(result)["warning_codes"] == ["rerank_below_threshold"]
    model.aclose.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("query,text", [
    ("Quy trình kiểm tra thiết bị QA-999", "QA-123: Quy trình kiểm tra thiết bị"),
    ("Luật 88/2025/QH15 quy định kiểm tra thiết bị", "Luật 99/2025/QH15 quy định kiểm tra thiết bị"),
    ("Đọc báo cáo nguy cơ trong absent.docx", "present.docx: báo cáo nguy cơ"),
    ("Quy trình xử lý cháy", "Danh sách ngày nghỉ trong năm"),
])
async def test_unknown_identifier_and_unrelated_candidates_remain_empty(query, text):
    result = await rank_candidates(query, [{"text": text}], scorer=scorer([.001]), threshold=.7)
    assert result.items == []


@pytest.mark.asyncio
async def test_calibrated_scores_remain_strict_and_passing_scores_are_unchanged():
    docs = [{"text": "Quy trình kiểm tra thiết bị"}]
    strict = await rank_candidates("Quy trình kiểm tra thiết bị", docs,
        scorer=scorer([.65], "calibrated"), threshold=.7)
    assert strict.items == [] and strict.threshold == .7
    passing = await rank_candidates("Quy trình kiểm tra thiết bị", docs,
        scorer=scorer([.8]), threshold=.7)
    assert passing.items == [{**docs[0], "rerank_score": .8}]
    assert passing.mode == "rerank" and passing.warning is None


@pytest.mark.asyncio
async def test_empty_input_does_not_call_model():
    model = scorer([])
    result = await rank_candidates("query", [], scorer=model, threshold=.7)
    assert result.items == []
    model.score.assert_not_called()
