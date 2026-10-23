import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import app.services.config_service
import app.services.wiki_reranker
from app.services.reranker_service import RerankerService

@pytest.mark.asyncio
async def test_reranker_service_fallback_to_settings():
    """When DB has no reranker config, from_db falls back to settings (.env)."""
    mock_db = MagicMock()
    mock_svc = MagicMock()
    # No values in DB
    mock_svc.get = AsyncMock(return_value=None)

    with patch("app.services.config_service.ConfigService", return_value=mock_svc), \
         patch("app.services.wiki_reranker.build_scorer", side_effect=Exception("No active spec")):
        
        service = await RerankerService.from_db(mock_db)
        from app.config import settings
        assert service.base_url == settings.reranker_base_url.rstrip("/")
        assert service.model == settings.reranker_model
        assert service.enabled == settings.reranker_enabled

@pytest.mark.asyncio
async def test_reranker_service_loads_from_db():
    """When DB has config (e.g. from UI), from_db uses DB values."""
    mock_db = MagicMock()
    mock_svc = MagicMock()

    async def fake_get(key):
        values = {
            "wiki_rerank_enabled": "true",
            "wiki_rerank_threshold": "0.35",
            "reranker_base_url": "https://custom-reranker.internal/v1",
            "reranker_api_key": "custom-secret-key",
            "reranker_model": "BAAI/custom-reranker",
        }
        return values.get(key)

    mock_svc.get = AsyncMock(side_effect=fake_get)

    with patch("app.services.config_service.ConfigService", return_value=mock_svc), \
         patch("app.services.wiki_reranker.build_scorer", side_effect=Exception("No active spec")):
        
        service = await RerankerService.from_db(mock_db)
        assert service.base_url == "https://custom-reranker.internal/v1"
        assert service.api_key == "custom-secret-key"
        assert service.model == "BAAI/custom-reranker"
        assert service.enabled is True
        assert service.threshold == 0.35

@pytest.mark.asyncio
async def test_reranker_service_loads_scorer_from_build_scorer():
    """When build_scorer returns an HTTPReranker, from_db attaches scorer."""
    mock_db = MagicMock()
    mock_svc = MagicMock()
    mock_svc.get = AsyncMock(return_value=None)

    from app.services.wiki_reranker import HTTPReranker
    mock_scorer = HTTPReranker(
        base_url="https://scorer-url.internal/v1",
        model="scorer-model",
        api_key="scorer-key"
    )

    with patch("app.services.config_service.ConfigService", return_value=mock_svc), \
         patch("app.services.wiki_reranker.build_scorer", return_value=mock_scorer):
        
        service = await RerankerService.from_db(mock_db)
        assert service.scorer == mock_scorer
        assert service.base_url == "https://scorer-url.internal/v1"
        assert service.model == "scorer-model"
        assert service.api_key == "scorer-key"

@pytest.mark.asyncio
async def test_reranker_service_rerank_with_scorer():
    """Test rerank method executes scorer and assigns rerank_score."""
    mock_scorer = MagicMock()
    mock_scorer.score = AsyncMock(return_value=[0.85, 0.25])

    service = RerankerService(
        base_url="https://fake-rerank.internal",
        model="fake-model",
        enabled=True,
        threshold=0.2,
        scorer=mock_scorer,
    )

    docs = [
        {"id": 1, "text": "Hồ sơ thủ tục đăng ký xe máy"},
        {"id": 2, "text": "Quy định phòng cháy chữa cháy"},
    ]

    ranked = await service.rerank("đăng ký xe", docs)
    assert len(ranked) == 2
    assert ranked[0]["id"] == 1
    assert ranked[0]["rerank_score"] == 0.85
    assert ranked[1]["id"] == 2
    assert ranked[1]["rerank_score"] == 0.25
    assert mock_scorer.score.called
