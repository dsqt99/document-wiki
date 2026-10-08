import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from app.services.reranker_service import RerankerService, RerankResult


@pytest.mark.asyncio
async def test_local_rerank_scoring_and_ordering():
    """Verify local scoring ranks matching document higher when no remote URL configured."""
    service = RerankerService(base_url="", enabled=True)

    query = "điều kiện an toàn phòng cháy cơ sở"
    docs = [
        {"id": "doc1", "text": "Quy định về thời tiết và nhiệt độ mùa hè."},
        {"id": "doc2", "text": "Điều kiện an toàn về phòng cháy và chữa cháy đối với cơ sở sản xuất kinh doanh."},
        {"id": "doc3", "text": "Hồ sơ thủ tục đăng ký xe cơ giới đường bộ."},
    ]

    results = await service.rerank(query=query, documents=docs, text_key="text", top_n=2)
    assert len(results) == 2
    assert results[0]["id"] == "doc2"
    assert results[0]["rerank_score"] > results[1]["rerank_score"]


@pytest.mark.asyncio
async def test_http_rerank_api_mocked():
    """Verify remote HTTP rerank endpoint integration with standard TEI/Infinity payload."""
    service = RerankerService(base_url="http://mock-reranker:8080", api_key="secret", enabled=True)

    query = "tiêu chuẩn nghiệm thu PCCC"
    docs = [
        {"id": "d1", "content": "Nội dung quy định chung."},
        {"id": "d2", "content": "Tiêu chuẩn quốc gia về nghiệm thu hệ thống PCCC."},
    ]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [
            {"index": 1, "relevance_score": 0.96},
            {"index": 0, "relevance_score": 0.12},
        ]
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        results = await service.rerank(query=query, documents=docs, text_key="content", top_n=2)

        assert mock_post.called
        assert results[0]["id"] == "d2"
        assert results[0]["rerank_score"] == 0.96
        assert results[1]["id"] == "d1"
        assert results[1]["rerank_score"] == 0.12


@pytest.mark.asyncio
async def test_http_rerank_fallback_on_network_error():
    """Verify graceful fallback to original ordering when remote reranker throws error."""
    service = RerankerService(base_url="http://broken-reranker:8080", enabled=True)

    query = "kiểm định phương tiện PCCC"
    docs = [
        {"id": "d1", "text": "Tài liệu 1", "score": 0.8},
        {"id": "d2", "text": "Tài liệu 2", "score": 0.6},
    ]

    with patch("httpx.AsyncClient.post", side_effect=httpx.ConnectError("Connection refused")):
        results = await service.rerank(query=query, documents=docs, text_key="text", top_n=2)
        # Should not raise exception; falls back to original order or local score
        assert len(results) == 2
        assert results[0]["id"] in ("d1", "d2")


def test_mmr_diversification():
    """Verify MMR filters out redundant candidate items."""
    service = RerankerService()

    candidates = [
        {"id": "c1", "text": "Điều kiện an toàn PCCC nhà xưởng khu công nghiệp", "rerank_score": 0.95},
        {"id": "c2", "text": "Điều kiện an toàn PCCC nhà xưởng khu công nghiệp nhà kho", "rerank_score": 0.94},  # high overlap
        {"id": "c3", "text": "Trách nhiệm của công an cấp xã trong kiểm tra an toàn PCCC", "rerank_score": 0.82},  # diverse topic
    ]

    diversified = service.diversify_mmr(
        candidates=candidates,
        text_key="text",
        score_key="rerank_score",
        lambda_param=0.5,
        top_n=2,
    )

    assert len(diversified) == 2
    # c1 is highest scored, so it must be selected first
    assert diversified[0]["id"] == "c1"
    # c3 brings diverse coverage over near-duplicate c2
    assert diversified[1]["id"] == "c3"
