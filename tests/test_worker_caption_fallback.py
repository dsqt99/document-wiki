import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import app.database
from app.worker import caption_images_task, enqueue_post_extraction_pipeline


@pytest.mark.asyncio
async def test_enqueue_post_extraction_pipeline_without_images():
    with patch("app.worker.get_arq_pool") as mock_get_pool:
        mock_pool = AsyncMock()
        mock_job = MagicMock()
        mock_job.job_id = "job_mrp_123"
        mock_pool.enqueue_job.return_value = mock_job
        mock_get_pool.return_value = mock_pool

        job_id = await enqueue_post_extraction_pipeline("source-1", has_images=False)
        assert job_id == "job_mrp_123"
        mock_pool.enqueue_job.assert_called_once_with("ingest_map_reduce_task", "source-1")


@pytest.mark.asyncio
async def test_caption_images_task_chains_to_mrp_when_no_vision_provider():
    source_id = str(uuid.uuid4())
    mock_source = MagicMock()
    mock_source.id = uuid.UUID(source_id)
    mock_source.full_text = "Sample text"

    mock_session = AsyncMock()
    mock_session.get.return_value = mock_source

    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_session
    mock_session_factory.return_value.__aexit__.return_value = False

    with patch("app.database.async_session_factory", mock_session_factory), \
         patch("app.ai.registry.ProviderRegistry.get_vision", new_callable=AsyncMock) as mock_get_vision, \
         patch("app.worker._chain_to_mrp", new_callable=AsyncMock) as mock_chain:
        
        mock_get_vision.return_value = None  # No vision provider configured!
        mock_chain.return_value = "job_mrp_456"

        await caption_images_task({}, source_id)

        # Must chain to MRP so source does not get stuck in processing!
        mock_chain.assert_called_once_with(source_id)


@pytest.mark.asyncio
async def test_caption_images_task_chains_to_mrp_when_no_images():
    source_id = str(uuid.uuid4())
    mock_source = MagicMock()
    mock_source.id = uuid.UUID(source_id)
    mock_source.full_text = "Sample text"

    mock_session = AsyncMock()
    mock_session.get.return_value = mock_source
    mock_exec_result = MagicMock()
    mock_exec_result.scalars.return_value.all.return_value = []  # No image rows!
    mock_session.execute.return_value = mock_exec_result

    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_session
    mock_session_factory.return_value.__aexit__.return_value = False

    with patch("app.database.async_session_factory", mock_session_factory), \
         patch("app.ai.registry.ProviderRegistry.get_vision", new_callable=AsyncMock) as mock_get_vision, \
         patch("app.worker._chain_to_mrp", new_callable=AsyncMock) as mock_chain:
        
        mock_get_vision.return_value = MagicMock()  # Vision provider exists
        mock_chain.return_value = "job_mrp_789"

        await caption_images_task({}, source_id)

        # Must chain to MRP even when there are no image rows in DB!
        mock_chain.assert_called_once_with(source_id)
